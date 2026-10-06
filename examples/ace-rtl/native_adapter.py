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


def descendants(pid, *, timeout=.1):
    result = subprocess.run(['ps', '-axo', 'pid=,ppid='], capture_output=True, text=True, timeout=timeout, shell=False)
    pairs = [tuple(map(int, line.split())) for line in result.stdout.splitlines() if len(line.split()) == 2]
    found = {pid}
    while True:
        children = {child for child, parent in pairs if parent in found}
        if children <= found:
            return found - {pid}
        found.update(children)


def run_worker(argv, cwd, logs, timeout, *, env=None, cancel=None, cleanup_deadline=None):
    logs.mkdir(parents=True, exist_ok=True)
    stdout, stderr = logs / 'stdout.log', logs / 'stderr.log'
    started = time.monotonic()
    execution_deadline = started + timeout
    cleanup_deadline = cleanup_deadline if cleanup_deadline is not None else execution_deadline + .3
    proc = None
    owned = set()
    status, code = 'infrastructure_error', None
    with stdout.open('wb') as out, stderr.open('wb') as err:
        try:
            proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                    start_new_session=True, shell=False)
            while True:
                remaining = execution_deadline - time.monotonic()
                if remaining <= 0:
                    status = 'timeout'
                    break
                try:
                    owned.update(descendants(proc.pid, timeout=min(.1, remaining)))
                except subprocess.TimeoutExpired:
                    pass
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
                    remaining = cleanup_deadline - time.monotonic()
                    if remaining > 0:
                        owned.update(descendants(proc.pid, timeout=min(.05, remaining)))
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
                    proc.wait(timeout=max(.001, min(.1, cleanup_deadline - time.monotonic())))
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
                try:
                    code = proc.wait(timeout=max(.001, cleanup_deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    code = proc.poll()
            write_json(logs / 'cleanup.json', {'process_group_terminated': proc is not None,
                       'status': 'completed' if proc is None or proc.poll() is not None else 'incomplete',
                       'descendant_pids': sorted(owned)})
    return ExecutionResult(status, code, time.monotonic() - started, str(stdout), str(stderr))


def cleanup_evaluators(logs, *, deadline):
    records = []
    for file in (logs / 'native').rglob('native-owned-network.json'):
        try:
            relative = file.relative_to(logs).as_posix()
            marker = safe_path(logs, relative)
            ownership = json.loads(marker.read_text())
            network = ownership['network']
            if not re.fullmatch(r'agent-opt-cvdp-[0-9a-f]{32}', network):
                continue
            if ownership.get('status') == 'completed':
                records.append({'network': network, 'status': 'completed', 'skipped': True})
                continue
            result = sibling('native_cleanup').cleanup_network(network, marker.parent / 'outer-cleanup', deadline=deadline)
            ownership.update(status=result['status'], cleanup_reason=result['reason'])
            write_json(marker, ownership)
            records.append(result)
        except (OSError, ValueError, KeyError, ConfigurationError):
            continue
    return {'status': 'completed' if all(r['status'] == 'completed' for r in records) else 'incomplete', 'networks': records}


class ACENative:
    execution_mode = 'native'

    @staticmethod
    def native_evidence(candidate, task, profile):
        return sibling('native_selection').execution_evidence(candidate, task, profile)

    @staticmethod
    def validate_experiment(spec, profile):
        from agent_optimizer.native_selection import verify_native_selection
        verify_native_selection(spec, profile)

    def __init__(self, config=None):
        self.config = config or {}

    def run(self, request):
        started = time.monotonic()
        request.logs.mkdir(parents=True, exist_ok=True)
        initial = {'schema_version': 1, 'execution_mode': 'native', 'source_revision': None,
                   'source_hash': None, 'profile': request.profile.get('id'), 'task_id': None,
                   'candidate_hash': None, 'status': 'started', 'attempts': [], 'requests': [],
                   'generated_files': [], 'evidence_paths': [], 'native_wall_time_seconds': None,
                   'usage_status': 'unreported', 'readiness_checks': [], 'cleanup': {'status': 'not_started', 'networks': []}}
        write_json(request.logs / 'native-execution.json', initial)
        def blocked(status, detail, error_type=None):
            initial.update(status=status, diagnostic=detail, native_wall_time_seconds=time.monotonic() - started)
            if error_type:
                initial['error_type'] = error_type
            write_json(request.logs / 'native-execution.json', initial)
            return ExecutionResult(status, None, time.monotonic() - started, '', '',
                                   metrics={'agent_tokens': None, 'agent_cost_usd': None}, detail=detail)
        try:
            if isinstance(request.timeout_seconds, bool) or not math.isfinite(request.timeout_seconds) or request.timeout_seconds <= 0:
                raise ConfigurationError('native outer timeout 오류')
            deadline = started + request.timeout_seconds
            execution_deadline = deadline - min(1, request.timeout_seconds * .1)
            config = {**request.profile.get('native', {}), **self.config}
            python = Path(config.get('python', sys.executable)).absolute()
            prep = sibling('native_prepare')
            ready = prep.readiness(request.agent_dir, python, timeout_seconds=max(.001, min(10, execution_deadline - time.monotonic())))
            initial['readiness_checks'] = ready.get('checks', [])
            if any(c.get('id') == 'native_source' and c.get('ready') for c in initial['readiness_checks']) or ready['ready']:
                lock = prep.verify_source(request.agent_dir)
                initial.update(source_revision=lock['revision'], source_hash=lock['source_hash'], candidate_hash=digest(request.agent_dir))
            if not ready['ready']:
                return blocked('timeout' if time.monotonic() >= execution_deadline else 'infrastructure_error', 'native pin/asset/Python 의존성 진단 실패')
            dataset = config.get('dataset')
            if not dataset:
                raise ConfigurationError('trusted native dataset 경로 필요')
            public = json.loads(safe_path(request.task_dir, 'native-task.json').read_text())
            split = public.pop('split', 'validation')
            if split not in {'train', 'validation', 'test'}:
                raise ConfigurationError('native public task split 오류')
            config['task_split'] = split
            cvdp = sibling('native_cvdp')
            rows = cvdp.load_pinned_rows(dataset)
            row = next((r for r in rows if r['id'] == public.get('id')), None)
            if row is None or cvdp.public_row(row) != public:
                raise ConfigurationError('native public descriptor 불일치')
            initial['task_id'] = row['id']
            verdict = cvdp.inspect_row(row)
            if not verdict['supported']:
                return blocked('unsupported', verdict['reason'])
            if time.monotonic() >= execution_deadline:
                return blocked('timeout', 'native 준비 중 outer timeout')
        except (ConfigurationError, OSError, ValueError, KeyError, TypeError) as exc:
            return blocked('infrastructure_error', 'native 준비 실패; sidecar 진단 확인', type(exc).__name__)
        write_json(request.logs / 'native-execution.json', initial)
        # Payload contains only public paths/config; private row is looked up by
        # the trusted worker, never delivered to the candidate surface or models.
        payload = {'workspace': str(request.workspace), 'agent_dir': str(request.agent_dir), 'task_dir': str(request.task_dir),
                   'prompt': request.prompt, 'seed': request.seed, 'timeout_seconds': max(0.001, execution_deadline - time.monotonic()),
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
                                request.workspace, request.logs, max(0.001, execution_deadline - time.monotonic()), env=environment,
                                cleanup_deadline=deadline)
            return result
        finally:
            cleanup = cleanup_evaluators(request.logs, deadline=deadline)
            process_cleanup = safe_path(request.logs, 'cleanup.json')
            cleanup['process_status'] = None
            if process_cleanup.is_file():
                try:
                    cleanup['process_status'] = json.loads(process_cleanup.read_text()).get('status')
                except (OSError, ValueError):
                    cleanup['process_status'] = 'unreported'
            if cleanup['process_status'] == 'incomplete':
                cleanup['status'] = 'incomplete'
            elif cleanup['process_status'] is None and cleanup['status'] == 'completed':
                cleanup['status'] = 'unreported'
            sidecar = json.loads((request.logs / 'native-execution.json').read_text())
            sidecar = sibling('native_artifacts').finalize(request.logs,
                status=(result.status if result else 'interrupted') if sidecar['status'] == 'started' else None,
                elapsed=(result.wall_time_seconds if result else None) if sidecar['status'] == 'started' else None)
            sidecar['cleanup'] = cleanup
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
