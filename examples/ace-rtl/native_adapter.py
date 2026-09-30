"""기존 RunRequest → 독립 Python native worker. coding binary/session 불필요."""
import importlib.util
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, ExecutionResult
from agent_optimizer.results import write_json
from agent_optimizer.workspace import digest, safe_path


def sibling(name):
    spec = importlib.util.spec_from_file_location('_ace_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def descendants(pid):
    result = subprocess.run(['ps', '-axo', 'pid=,ppid='], capture_output=True, text=True, timeout=2, shell=False)
    pairs = [tuple(map(int, line.split())) for line in result.stdout.splitlines() if len(line.split()) == 2]
    found = {pid}
    while True:
        children = {child for child, parent in pairs if parent in found}
        if children <= found:
            return found - {pid}
        found.update(children)


def run_worker(argv, cwd, logs, timeout, *, env=None, cancel=None):
    logs.mkdir(parents=True, exist_ok=True)
    stdout, stderr = logs / 'stdout.log', logs / 'stderr.log'
    started = time.monotonic()
    proc = None
    owned = set()
    status, code = 'infrastructure_error', None
    with stdout.open('wb') as out, stderr.open('wb') as err:
        try:
            proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                    start_new_session=True, shell=False)
            while True:
                owned.update(descendants(proc.pid))
                code = proc.poll()
                if code is not None:
                    status = 'completed' if code == 0 else 'process_error'
                    break
                if cancel and cancel():
                    status = 'interrupted'
                    break
                if time.monotonic() - started >= timeout:
                    status = 'timeout'
                    break
                time.sleep(0.03)
        except OSError:
            status = 'infrastructure_error'
        except BaseException:
            status = 'interrupted'
            raise
        finally:
            if proc is not None:
                # Evaluator drivers may start new sessions, so kill both the
                # native process group and observed descendants, then reap.
                try:
                    owned.update(descendants(proc.pid))
                except (OSError, subprocess.TimeoutExpired):
                    pass
                for pid in owned:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=0.3)
                except subprocess.TimeoutExpired:
                    pass
                for pid in owned:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                code = proc.wait()
            write_json(logs / 'cleanup.json', {'process_group_terminated': proc is not None, 'descendant_pids': sorted(owned)})
    return ExecutionResult(status, code, time.monotonic() - started, str(stdout), str(stderr))


def cleanup_evaluators(logs):
    for file in (logs / 'native').rglob('native-owned-network.json'):
        try:
            relative = file.relative_to(logs).as_posix()
            marker = safe_path(logs, relative)
            network = json.loads(marker.read_text())['network']
            if not re.fullmatch(r'agent-opt-cvdp-[0-9a-f]{32}', network):
                continue
            sibling('evaluator').cleanup_network(network, marker.parent / 'outer-cleanup')
        except (OSError, ValueError, KeyError, ConfigurationError):
            continue


class ACENative:
    def __init__(self, config=None):
        self.config = config or {}

    def run(self, request):
        started = time.monotonic()
        if not math.isfinite(request.timeout_seconds) or request.timeout_seconds <= 0:
            raise ConfigurationError('native outer timeout은 유한한 양수여야 합니다')
        deadline = started + request.timeout_seconds
        request.logs.mkdir(parents=True, exist_ok=True)
        config = {**request.profile.get('native', {}), **self.config}
        python = Path(config.get('python', sys.executable)).absolute()
        ready = sibling('native_prepare').readiness(request.agent_dir, python, timeout_seconds=min(10, request.timeout_seconds))
        if not ready['ready']:
            return ExecutionResult('timeout' if time.monotonic() >= deadline else 'infrastructure_error', None,
                                   time.monotonic() - started, '', '', detail='native pin/asset/Python 의존성 진단 실패')
        dataset = config.get('dataset')
        if not dataset:
            raise ConfigurationError('trusted native dataset 경로가 필요합니다')
        public = json.loads(safe_path(request.task_dir, 'native-task.json').read_text())
        split = public.pop('split', 'validation')
        if split not in {'train', 'validation', 'test'}:
            raise ConfigurationError('native public task split이 유효하지 않습니다')
        config['task_split'] = split
        cvdp = sibling('native_cvdp')
        rows = cvdp.load_pinned_rows(dataset)
        row = next((r for r in rows if r['id'] == public.get('id')), None)
        if row is None or cvdp.public_row(row) != public:
            raise ConfigurationError('native public descriptor가 trusted pinned row와 다릅니다')
        verdict = cvdp.inspect_row(row)
        if not verdict['supported']:
            return ExecutionResult('unsupported', None, 0, '', '', detail=verdict['reason'])
        lock = sibling('native_prepare').verify_source(request.agent_dir)
        if time.monotonic() >= deadline:
            return ExecutionResult('timeout', None, time.monotonic() - started, '', '', detail='native 준비 중 outer timeout')
        initial = {'schema_version': 1, 'execution_mode': 'native', 'source_revision': lock['revision'],
                   'source_hash': lock['source_hash'], 'profile': request.profile['id'], 'task_id': row['id'],
                   'candidate_hash': digest(request.agent_dir), 'status': 'started', 'attempts': [], 'requests': [],
                   'generated_files': [], 'evidence_paths': ['native'], 'native_wall_time_seconds': None, 'usage_status': 'unreported'}
        write_json(request.logs / 'native-execution.json', initial)
        # Payload contains only public paths/config; private row is looked up by
        # the trusted worker, never delivered to the candidate surface or models.
        payload = {'workspace': str(request.workspace), 'agent_dir': str(request.agent_dir), 'task_dir': str(request.task_dir),
                   'prompt': request.prompt, 'seed': request.seed, 'timeout_seconds': max(0.001, deadline - time.monotonic()),
                   'profile': {**request.profile, 'native': config}, 'logs': str(request.logs), 'task_id': row['id']}
        write_json(request.logs / 'native-request.json', payload)
        home = safe_path(request.logs, 'native-home')
        home.mkdir(exist_ok=True)
        environment = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
                       'HOME': str(home), 'XDG_CACHE_HOME': str(home / 'cache'),
                       'PYTHONPATH': os.pathsep.join(str(Path(p).absolute()) for p in sys.path)}
        result = None
        try:
            result = run_worker([str(python), str(Path(__file__).with_name('native_worker.py')), str(request.logs / 'native-request.json')],
                                request.workspace, request.logs, max(0.001, deadline - time.monotonic()), env=environment)
            return result
        finally:
            cleanup_evaluators(request.logs)
            sidecar = json.loads((request.logs / 'native-execution.json').read_text())
            if sidecar['status'] == 'started':
                requests = request.logs / 'native-requests.json'
                sidecar['requests'] = json.loads(requests.read_text()) if requests.exists() else []
                for record in sidecar['requests']:
                    if record['status'] == 'started':
                        record['status'] = 'interrupted'
                sidecar['status'] = result.status if result else 'interrupted'
                sidecar['native_wall_time_seconds'] = result.wall_time_seconds if result else None
                sidecar['usage_status'] = 'partial' if any(r['input_tokens'] is not None or r['output_tokens'] is not None for r in sidecar['requests']) else 'unreported'
                write_json(request.logs / 'native-execution.json', sidecar)
            progress = request.logs / 'native-progress.json'
            if progress.exists() and not sidecar['attempts']:
                sidecar.update(json.loads(progress.read_text()))
                sidecar['generated_files'] = sidecar['attempts'][-1]['generated_files'] if sidecar['attempts'] else []
                sidecar['evidence_paths'] = ['native', *[p for e in sidecar.get('evaluations', []) for p in e.get('evidence_paths', [])]]
                write_json(request.logs / 'native-execution.json', sidecar)
            if result is not None:
                if sidecar['status'] in {'infra_error', 'infrastructure_error'}:
                    result.status = 'infrastructure_error'
                # Native failure with valid output still goes through the outer
                # trusted evaluator. Inner pass is never a final score.
                if sidecar['status'] == 'api_error':
                    result.status = 'infrastructure_error'
                if sidecar['status'] == 'timeout':
                    result.status = 'timeout'
                result.metrics = {'agent_tokens': None, 'agent_cost_usd': None,
                                  'native_inner_evaluation_count': float(len(sidecar.get('evaluations', [])))}
                result.wall_time_seconds = time.monotonic() - started
