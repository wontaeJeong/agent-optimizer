"""고정 upstream run_attempt를 public processor·trusted evaluator·제품 모델에 연결한다.

독립 worker 안에서만 사용한다. in-process candidate Python은 OS 보안 격리가 아니다.
"""
import argparse
import hashlib
import importlib
import importlib.util
import json
import math
import sys
import threading
import time
import types
from contextlib import contextmanager
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, Task
from agent_optimizer.models import ModelSettings, complete
from agent_optimizer.results import write_json
from agent_optimizer.workspace import digest, safe_path


def sibling(name):
    spec = importlib.util.spec_from_file_location('_ace_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cvdp = sibling('native_cvdp')
prepare = sibling('native_prepare')


class NativeCallError(BaseException):
    # Upstream role helpers catch Exception and fabricate heuristic guidance on
    # provider errors. A control-flow exception makes those paths fail closed.
    def __init__(self, message, status='api_error'):
        super().__init__(message)
        self.status = status


def positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ConfigurationError(f'native {name}은 유한한 양수여야 합니다')
    return value


class RoleTransport:
    def __init__(self, request, settings, completion=complete):
        self.request = request
        self.settings = settings
        self.completion = completion
        self.requests = []
        self.deadline = time.monotonic() + positive(request.timeout_seconds, 'outer timeout')
        self.llm_timeout = positive(request.profile.get('native', {}).get('llm_timeout', 60), 'LLM timeout')
        self.text = safe_path(request.agent_dir, 'native/guidance.md').read_text()
        code = safe_path(request.agent_dir, 'native/orchestration.py')
        # Compile source rather than reusing timestamp-based pyc caches between candidates.
        self.surface = types.ModuleType('native_candidate_orchestration')
        self.surface.__file__ = str(code)
        exec(compile(code.read_text(), str(code), 'exec'), self.surface.__dict__)
        if not callable(getattr(self.surface, 'guidance', None)):
            raise ConfigurationError('native orchestration.guidance 함수 누락')
        self.surface_hashes = {'guidance': hashlib.sha256(self.text.encode()).hexdigest(),
                               'orchestration': hashlib.sha256(code.read_bytes()).hexdigest()}

    def call(self, role, prompt, system=''):
        if role not in {'generator', 'reflector', 'coordinator'}:
            raise ConfigurationError('native 미허용 모델 역할')
        timeout = min(self.llm_timeout, self.deadline - time.monotonic())
        if timeout <= 0:
            raise NativeCallError('native outer timeout', 'timeout')
        record = {'request_id': f'r{len(self.requests) + 1:06d}', 'role': role, 'model': self.settings.model,
                  'status': 'started', 'duration_seconds': None, 'input_tokens': None, 'output_tokens': None, 'cost_usd': None}
        self.requests.append(record)
        self.flush()
        started = time.monotonic()
        try:
            guidance = self.surface.guidance(role, self.text)
            if not isinstance(guidance, str):
                raise ConfigurationError('native guidance 반환 형식 오류')
            response = self.completion([{'role': 'system', 'content': role + '\n' + system + '\n' + guidance},
                                        {'role': 'user', 'content': prompt}], settings=self.settings, timeout=timeout)
            content = response['choices'][0]['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise ValueError('invalid content')
            usage = response.get('usage') or {}
            for key, source in [('input_tokens', 'prompt_tokens'), ('output_tokens', 'completion_tokens')]:
                value = usage.get(source)
                record[key] = value if type(value) is int and value >= 0 else None
            record['status'] = 'completed'
            return content
        except Exception as exc:
            record['status'] = 'timeout' if isinstance(exc, TimeoutError) or 'total timeout' in str(exc) else 'api_error'
            # Never put provider error text/endpoint/key/prompt in metadata.
            status = 'timeout' if time.monotonic() >= self.deadline else 'api_error'
            raise NativeCallError('native 모델 요청 실패; 자동 대체 없음', status) from None
        finally:
            record['duration_seconds'] = time.monotonic() - started
            self.flush()

    def flush(self):
        write_json(self.request.logs / 'native-requests.json', self.requests)


@contextmanager
def snapshot_imports(agent_dir):
    prefixes = ('ace_cvdp_native', 'ace_rtl_agent', 'src')
    def owned(name):
        return any(name == p or name.startswith(p + '.') for p in prefixes)
    saved = {k: v for k, v in sys.modules.items() if owned(k)}
    paths = sys.path[:]
    previous_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    for name in saved:
        del sys.modules[name]
    sys.path.insert(0, str(agent_dir / 'skills/ace-rtl/scripts'))
    try:
        yield importlib.import_module('ace_cvdp_native.cli')
    finally:
        for name in list(sys.modules):
            if owned(name):
                del sys.modules[name]
        sys.modules.update(saved)
        sys.path[:] = paths
        sys.dont_write_bytecode = previous_bytecode


def safe_native_result(evaluation):
    if evaluation.status == 'passed' and evaluation.metrics.get('passed') == 1:
        return {'tests': [{'result': 0}]}
    if evaluation.status == 'failed' and evaluation.metrics.get('passed') == 0:
        return {'tests': [{'result': 1}]}
    return {'tests': [{'result': 127, 'error_msg': 'official evaluator infrastructure error'}]}


def run_native(request, row, *, evaluator=None, settings=None, completion=complete):
    lock = prepare.verify_source(request.agent_dir)
    verdict = cvdp.inspect_row(row)
    if not verdict['supported']:
        raise ConfigurationError(verdict['reason'])
    public = cvdp.public_row(row)
    targets = list(public['output']['context'])
    if evaluator is None:
        evaluator = sibling('native_evaluator').NativeCVDPEvaluator(request.profile.get('native', {}).get('evaluator', {})).evaluate
    transport = RoleTransport(request, settings or ModelSettings.from_env(), completion)
    config = request.profile.get('native', {})
    iterations = config.get('max_iterations', 3)
    if type(iterations) is not int or not 1 <= iterations <= 30:
        raise ConfigurationError('native max_iterations는 1~30 정수여야 합니다')
    eval_timeout = positive(config.get('evaluator_timeout', 120), 'evaluator timeout')
    started = time.monotonic()
    evidence = request.logs / 'native'
    evidence.mkdir(exist_ok=False)
    row_jsonl = evidence / 'public-row.jsonl'
    row_jsonl.write_text(json.dumps(public, ensure_ascii=False) + '\n')
    inner = []
    progress_attempts = []
    generated_roots = []
    with snapshot_imports(request.agent_dir) as cli:
        from ace_rtl_agent.utils.llm_client import LLMClient
        from ace_rtl_agent.fresh_start_coordinator import FreshStartCoordinator
        from ace_rtl_agent.focused_debugger import FocusedDebugger
        from ace_cvdp_native.llm import AceIterationModel

        # No NVIDIA backend construction, retries, or caught-error fallback.
        LLMClient._setup_client = lambda self, api_key=None: None
        LLMClient.call_llm = lambda self, prompt, **kw: transport.call(getattr(self, '_native_role', 'reflector'), prompt)
        FreshStartCoordinator._build_immutable_harness_context = lambda self, **kw: ''
        focused_init = FocusedDebugger.__init__
        coordinator_init = FreshStartCoordinator.__init__
        def new_focused(self, *args, **kwargs):
            focused_init(self, *args, **kwargs)
            self.llm_client._native_role = 'reflector'
        def new_coordinator(self, *args, **kwargs):
            coordinator_init(self, *args, **kwargs)
            self.client._native_role = 'coordinator'
        FocusedDebugger.__init__ = new_focused
        FreshStartCoordinator.__init__ = new_coordinator

        class SafeIterationModel(AceIterationModel):
            def prompt(self, prompt, schema=None, prompt_log='', files=None, timeout=60, category=None):
                if list(files or []) != targets:
                    raise ConfigurationError('public target 계약 불일치')
                self.iteration_dir.mkdir(parents=True, exist_ok=True)
                instructions = '\n'.join(['공개 과제:\n' + prompt, 'Target files: ' + ', '.join(targets),
                                           'Coordinator:\n' + self.coordinator, 'Reflector:\n' + self.reflection,
                                           'Previous candidate:\n' + json.dumps(self.previous_candidate or {})])
                content = transport.call('generator', instructions,
                    '모든 선언 target의 완전한 RTL을 반환하세요. Markdown 코드 펜스·설명문은 금지합니다. '
                    '단일 target은 원문 RTL만, 다중 target은 각 파일 앞에 정확히 '
                    '// TARGET_FILE: <path>를 넣고 모든 선언 경로를 한 번씩 제출하세요.')
                try:
                    outputs = cvdp.parse_outputs(content, targets)
                except ConfigurationError:
                    raise NativeCallError('native 모델 출력 계약 위반; target/Markdown 형식을 확인하세요',
                                          'agent_incomplete') from None
                for name, text in outputs.items():
                    path = safe_path(self.iteration_dir / 'candidate', name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text)
                    self.generated_files[name] = str(path)
                generated_roots[:] = [self.iteration_dir / 'candidate']
                return ({'direct_text': outputs[targets[0]]} if len(targets) == 1 else
                        {'code': [{p: outputs[p]} for p in targets]}), True

        class PublicProcessor:
            def __init__(self, filename, golden, threads, debug, host, prefix, **kwargs):
                self.prefix = Path(prefix)
            def process_json(self):
                pass
            def prepare(self, issue, model):
                prompt = public['input']['prompt'] + '\n' + '\n'.join(f'# Context: {name}\n{text}' for name, text in public['input']['context'].items())
                model.prompt(prompt, files=targets)
                return public['id'], {}, types.SimpleNamespace(issue_path=str(model.iteration_dir / 'public-context'))
            def run(self, id, obj, repo, model):
                directory = model.iteration_dir / 'inner-output'
                outputs = cvdp.read_outputs(model.iteration_dir / 'candidate', targets)
                for name, text in outputs.items():
                    path = safe_path(directory, name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text)
                remaining = transport.deadline - time.monotonic()
                if remaining <= 0:
                    raise NativeCallError('native outer timeout', 'timeout')
                tick = time.monotonic()
                task = Task(row['id'], config.get('task_split', 'validation'), public['input']['prompt'], {}, {'row': row, 'targets': targets})
                evaluation = evaluator(task, directory, min(eval_timeout, remaining))
                raw_evidence = []
                raw_result = evaluation.artifacts.get('raw_result')
                if raw_result:
                    try:
                        relative = Path(raw_result).absolute().relative_to(request.logs.absolute()).as_posix()
                        if safe_path(request.logs, relative).is_file():
                            raw_evidence.append(relative)
                    except (ValueError, ConfigurationError):
                        pass
                inner.append({'purpose': 'native_inner', 'iteration': len(inner) + 1, 'status': evaluation.status,
                              'wall_time_seconds': time.monotonic() - tick, 'evidence_paths': raw_evidence})
                # Preserve official evidence only at owned private paths. Never copy
                # its feedback/log contents or implementation paths into model inputs.
                result = safe_native_result(evaluation)
                iteration = int(model.iteration_dir.name.removeprefix('iter_'))
                generated_files = [{'path': name, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
                                    'evidence_path': Path(model.generated_files[name]).relative_to(request.logs).as_posix()}
                                   for name, text in outputs.items()]
                progress_attempts.append({'attempt': 1, 'iteration': iteration, 'status': cvdp.classify_result(result)[0],
                                          'generated_files': generated_files,
                                          'evidence_path': f'native/attempt_1/iter_{iteration:02d}/real_evaluator_result.json'})
                write_json(request.logs / 'native-progress.json', {'attempts': progress_attempts, 'evaluations': inner})
                return result

        src = types.ModuleType('src')
        src.dataset_processor = types.SimpleNamespace(GenerationProcessor=PublicProcessor)
        sys.modules['src'] = src
        cli.AceIterationModel = SafeIterationModel
        cli.role_api_key = lambda: None
        cli.install_native_harness_patch = lambda: None
        cli.build_reflector_harness_context = lambda *a, **kw: ''
        cli.build_evaluator_error_report = lambda result, summary: cvdp.classify_result(result)[1]
        cli.summarize_result = lambda result: cvdp.classify_result(result)[1]
        cli.result_passed = lambda result: cvdp.classify_result(result)[0] == 'passed'
        cli.primary_failure_from_summary = lambda result, summary: {
            'stage': 'PASS' if cvdp.classify_result(result)[0] == 'passed' else
                     'INFRA_SETUP' if cvdp.classify_result(result)[0] == 'infrastructure_error' else 'FUNCTIONAL',
            'message': cvdp.classify_result(result)[1], 'signature': cvdp.classify_result(result)[0]}
        args = argparse.Namespace(max_iterations=iterations, cid=verdict['cid'], llm_timeout=transport.llm_timeout,
                                  evaluator_timeout=eval_timeout, generator_model=transport.settings.model,
                                  reflector_model=transport.settings.model, coordinator_model=transport.settings.model)
        result = cli.run_attempt(workspace=request.agent_dir, cvdp_repo=evidence / 'no-private-repo', row=public,
                                 row_jsonl=row_jsonl, attempt_root=evidence / 'attempt_1', attempt_index=1,
                                 args=args, stop_event=threading.Event())
    attempts = []
    for h in result.get('history', []):
        files = []
        for name, path in h.get('generated_files', {}).items():
            relative = Path(path).relative_to(request.logs).as_posix()
            candidate = safe_path(request.logs, relative)
            files.append({'path': name, 'sha256': hashlib.sha256(candidate.read_bytes()).hexdigest(), 'evidence_path': relative})
        attempts.append({'attempt': 1, 'iteration': h['iteration'], 'status': cvdp.classify_result(h['result'])[0],
                         'generated_files': files, 'evidence_path': f'native/attempt_1/iter_{h["iteration"]:02d}/real_evaluator_result.json'})
    if generated_roots:
        outputs = cvdp.read_outputs(generated_roots[0], targets)
        for name, text in outputs.items():
            path = safe_path(request.task_dir, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    sidecar = {'schema_version': 1, 'execution_mode': 'native', 'source_revision': lock['revision'],
               'source_hash': lock['source_hash'], 'profile': request.profile['id'], 'task_id': row['id'],
               'candidate_hash': digest(request.agent_dir), 'status': result['status'], 'attempts': attempts,
               'requests': transport.requests, 'generated_files': attempts[-1]['generated_files'] if attempts else [],
               'evidence_paths': ['native', *[p for e in inner for p in e['evidence_paths']]],
               'native_wall_time_seconds': time.monotonic() - started,
               'usage_status': 'partial' if any(r['input_tokens'] is not None or r['output_tokens'] is not None for r in transport.requests) else 'unreported',
               'active_surface_hashes': transport.surface_hashes, 'evaluations': inner,
               'outer_evaluation': {'purpose': 'trusted_final', 'owner': 'GroupRunner.trial', 'count': None, 'wall_time_seconds': None}}
    if inner and inner[-1]['status'] == 'timeout':
        sidecar['status'] = 'timeout'
    write_json(request.logs / 'native-execution.json', sidecar)
    return sidecar
