"""ACE native의 CID/row/pin·private 평가·활성 표면 정책. 제품 경로/저장은 공통 코어 소비."""
import importlib.util
import json
import os
import stat
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

from agent_optimizer.app_paths import app_path
from agent_optimizer.config import identifier, positive, read_toml
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.registry import NATIVE_DEPENDENCIES
from agent_optimizer.setup_wizard import _literal, _section, write_experiment
from agent_optimizer.results import write_json
from agent_optimizer.workspace import safe_path

CIDS = {'cid002', 'cid004', 'cid007', 'cid016'}


def diagnose_selection(spec, *, retry, prepare):
    """Static native checks reuse the product's structured check/probe contract."""
    from agent_optimizer.readiness import Runner, check
    from agent_optimizer import diagnostics
    profile = spec['_profiles'][0]
    native = profile.get('native', {})
    checks = []
    try:
        verify_native_selection(spec, profile, prepare=prepare)
        checks.append(check('native.selection', 'native', True, '고정 CID/row·private 평가·활성 surface 계약을 확인했습니다', ''))
    except (ConfigurationError, OSError, ValueError, KeyError, TypeError) as exc:
        checks.append(check('native.selection', 'native', False, 'native 선택 계약을 확인할 수 없습니다',
                            '고정 dataset·선택 CID/row·split·candidate/active target을 복원하세요',
                            cause=diagnostics.summarize_exception(exc), retry=retry))
    for agent in spec['_agents']:
        source = agent.source.path if agent.source and agent.source.kind == 'local' else Path('/missing-native-source')
        for row in prepare.readiness(source, native.get('python', sys.executable))['checks']:
            checks.append(check(row['id'], 'native', row['ready'], 'native pin/asset/interpreter·의존성 정적 검사',
                                '고정 upstream 자산과 Python 3.12·yaml/pydantic_settings 환경을 준비하세요',
                                cause=row.get('reason'), retry=retry))
    runner = Runner(spec['_root'], 'native')
    runner.add('native.ps', bool(shutil.which('ps')), 'native child cleanup에 필요한 ps 확인',
               'ps 실행 파일을 준비하세요', cause='ps 실행 파일 없음', retry=retry)
    evaluator = native.get('evaluator', spec.get('evaluator_config', {}))
    repo = Path(evaluator.get('repo', '/missing-native-evaluator'))
    python = Path(evaluator.get('python', '/missing-native-python'))
    present = (repo / 'run_benchmark.py').is_file()
    runner.add('native.evaluator.assets', present, '공식 CVDP evaluator 자산 확인',
               '고정 CVDP checkout과 평가 driver를 준비하세요', cause='run_benchmark.py 누락', retry=retry)
    if present:
        outcome = runner.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'])
        runner.add('native.evaluator.pin', outcome.succeeded and outcome.stdout.strip() == '8e894cf74414ab1eaea1e2b4e80a02f123df07b6',
                   '공식 CVDP 고정 pin 확인', '검토된 CVDP commit을 복원하세요',
                   cause='CVDP 고정 commit 불일치' if outcome.succeeded else diagnostics.summarize_failure(outcome), retry=retry)
    runner.add('native.evaluator.python', python.is_file(), 'CVDP driver interpreter 확인',
               'CVDP Python 3.12 driver의 절대경로를 지정하세요', cause='driver interpreter 없음', retry=retry)
    runner.probe('native.evaluator.dependencies', [str(python), '-I', '-B', '-c',
                 'import sys; import yaml, requests, pydantic, openai, dotenv, psutil, nltk, tabulate, numpy, colorama, ruamel.yaml, tiktoken; assert sys.version_info[:2] == (3, 12); print("ok")'],
                 'CVDP driver Python 3.12·필수 의존성 확인', '고정 driver lock으로 별도 평가 환경을 준비하세요',
                 requires=('native.evaluator.python',), expected='ok', retry=retry)
    runner.add('native.docker', bool(shutil.which('docker')), 'OSS simulator runtime 확인',
               'Docker 실행 파일과 로컬 OSS 평가 이미지를 준비하세요', cause='Docker 실행 파일 없음', retry=retry)
    image, identity = evaluator.get('sim_image'), evaluator.get('sim_image_id')
    runner.add('native.simulator.lock', bool(image and identity), 'OSS_SIM 이미지 identity 선언 확인',
               '검증한 sim_image와 sim_image_id를 지정하세요', cause='OSS_SIM image/identity 미지정', retry=retry)
    if runner.ok('native.docker') and runner.ok('native.simulator.lock'):
        outcome = runner.run(['docker', 'image', 'inspect', image])
        try:
            matched = outcome.succeeded and json.loads(outcome.stdout)[0]['Id'] == identity
        except (ValueError, KeyError, TypeError, IndexError):
            matched = False
        runner.add('native.simulator.identity', matched, '로컬 OSS_SIM 이미지 identity 확인',
                   '준비한 평가 image identity를 복원하세요. offline miss는 다운로드로 대체하지 않습니다',
                   cause=None if matched else diagnostics.summarize_failure(outcome) if not outcome.succeeded else '로컬 image identity 불일치', retry=retry)
    return checks + runner.checks


def validate_profile(profile):
    from agent_optimizer.config import only_keys
    native = profile.get('native', {})
    if not isinstance(native, dict):
        raise ConfigurationError('native 설정은 객체여야 합니다')
    only_keys(native, {'python', 'dataset', 'max_iterations', 'llm_timeout', 'evaluator_timeout', 'evaluator'}, 'native')
    for key in ('python', 'dataset'):
        if key in native and (not isinstance(native[key], str) or not Path(native[key]).is_absolute() or '\0' in native[key]):
            raise ConfigurationError(f'native.{key}에는 절대경로가 필요합니다')
    if type(native.get('max_iterations', 3)) is not int or not 1 <= native.get('max_iterations', 3) <= 30:
        raise ConfigurationError('native.max_iterations는 1~30 정수여야 합니다')
    for key in ('llm_timeout', 'evaluator_timeout'):
        positive(native.get(key, 60), f'native.{key}')
    evaluator = native.get('evaluator', {})
    if not isinstance(evaluator, dict):
        raise ConfigurationError('native.evaluator는 객체여야 합니다')
    only_keys(evaluator, {'repo', 'python', 'sim_image', 'sim_image_id'}, 'native.evaluator')
    if not all(isinstance(value, str) and value for value in evaluator.values()):
        raise ConfigurationError('native.evaluator에는 비어 있지 않은 문자열이 필요합니다')


def validate_product_options(*, metric, direction, prompt_file, max_tasks, rows):
    if (metric != 'passed' or direction != 'maximize' or prompt_file not in {'prompts/system.md', 'native/guidance.md'} or
            max_tasks not in {9, len(rows)}):
        raise ConfigurationError('native는 passed/maximize·활성 guidance·명시 row 전체를 사용합니다. max_tasks는 row 수와 같아야 합니다')


def validate_field(field, value):
    if field == 'rows' and (not isinstance(value, dict) or not all(isinstance(split, str) and split in {'train', 'validation', 'test'} for split in value.values())):
        raise ConfigurationError('row ID → train/validation/test JSON 객체가 필요합니다')
    if field == 'evaluator' and (not isinstance(value, dict) or set(value) - {'repo', 'python', 'sim_image', 'sim_image_id'}):
        raise ConfigurationError('native evaluator에는 repo/python/sim_image/sim_image_id만 허용합니다')
    if field not in {'cids', 'rows', 'evaluator'} and value and not Path(value).is_absolute():
        raise ConfigurationError('native 자산 경로는 절대경로로 입력하세요')


def execution_evidence(candidate, task, profile):
    try:
        file = safe_path(candidate.path, 'native/source-lock.json')
        with os.fdopen(os.open(file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), encoding='utf-8') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ConfigurationError('native source lock는 일반 파일이어야 합니다')
            lock = json.loads(stream.read(1024 * 1024 + 1))
        lock = lock if isinstance(lock, dict) else {}
    except (ConfigurationError, OSError, ValueError, RecursionError):
        lock = {}
    return {'generated_targets': task.evaluation.get('targets', []),
            'source_revision': lock.get('revision', ''), 'source_hash': lock.get('source_hash', '')}


def preparation(root: Path):
    file = safe_path(root, 'examples/ace-rtl/native_prepare.py')
    spec = importlib.util.spec_from_file_location('_product_native_prepare', file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_selection(cids, rows, optimizer):
    if not isinstance(cids, (list, tuple, set)) or not cids or not all(isinstance(cid, str) for cid in cids) or not set(cids) <= CIDS:
        raise ConfigurationError('native CID를 cid002/cid004/cid007/cid016 중 명시적으로 선택하세요')
    if not isinstance(rows, dict) or not rows or not all(isinstance(key, str) and key and isinstance(value, str) and value in {'train', 'validation', 'test'} for key, value in rows.items()):
        raise ConfigurationError('native row ID → train/validation/test를 명시하세요')
    for key in rows:
        identifier(key)
    if 'validation' not in rows.values() or optimizer != 'baseline' and 'train' not in rows.values():
        raise ConfigurationError('validation row와 연구 Optimizer의 train row가 필요합니다')
    if optimizer not in {'gepa', 'meta_harness', 'baseline'}:
        raise ConfigurationError('native는 GEPA/Meta-Harness/Baseline만 연결됐습니다')


def native_stage_config(optimizer, options=None):
    options = {} if options is None else options
    if optimizer == 'baseline':
        if options:
            raise ConfigurationError('baseline에는 Optimizer 설정을 지정할 수 없습니다')
        return {}
    if optimizer not in {'gepa', 'meta_harness'}:
        raise ConfigurationError('native Optimizer가 지원되지 않습니다')
    defaults = ({'file': 'native/guidance.md', 'metric': 'passed', 'direction': 'maximize',
                 'iterations': 3, 'batch_size': 4, 'merge': False} if optimizer == 'gepa' else
                {'file': 'native/orchestration.py', 'metric': 'passed', 'direction': 'maximize',
                 'iterations': 3, 'required_symbol': 'guidance'})
    allowed = set(defaults) | {'request_timeout_seconds'} | ({'seed'} if optimizer == 'gepa' else set())
    if not isinstance(options, dict) or set(options) - allowed:
        raise ConfigurationError('native Optimizer 설정 키를 확인하세요')
    config = {**defaults, **options}
    if (config['file'] != defaults['file'] or config['metric'] != 'passed' or config['direction'] != 'maximize' or
            optimizer == 'gepa' and config['merge'] is not False or
            optimizer == 'meta_harness' and config['required_symbol'] != 'guidance'):
        raise ConfigurationError('native의 실제 활성 guidance/orchestration 계약만 선택하세요')
    for key in ('iterations', 'batch_size', 'seed'):
        if key in config and (type(config[key]) is not int or (config[key] < 0 if key == 'seed' else not 1 <= config[key] <= 100)):
            raise ConfigurationError(f'native {key} 범위를 확인하세요')
    if 'request_timeout_seconds' in config:
        positive(config['request_timeout_seconds'], 'request_timeout_seconds')
    return config


def inspect_selection(root, cids, rows, dataset, *, prepare=None):
    prep = prepare or preparation(Path(root))
    cvdp = prep.sibling('native_cvdp')
    pinned = cvdp.load_pinned_rows(Path(dataset))
    by_id = {row['id']: row for row in pinned if set(row['categories']).intersection(cids)}
    verdicts = []
    for row_id in rows:
        if row_id not in by_id:
            raise ConfigurationError(f'선택 CID에 없는 native row: {row_id}')
        verdict = cvdp.inspect_row(by_id[row_id])
        if not verdict['supported']:
            raise ConfigurationError(f'{row_id}: {verdict["reason"]}')
        verdicts.append(verdict)
    return verdicts


def available_rows(root, dataset, cids, *, prepare=None):
    if not cids or not set(cids) <= CIDS:
        raise ConfigurationError('CID를 먼저 명시적으로 선택하세요')
    cvdp = (prepare or preparation(Path(root))).sibling('native_cvdp')
    return [cvdp.inspect_row(row) for row in cvdp.load_pinned_rows(Path(dataset))
            if set(row['categories']).intersection(cids)]


def verify_native_selection(spec, profile=None, *, prepare=None):
    """실행 직전 public descriptor·trusted 평가 row를 고정 원본과 재대조한다."""
    for profile in ([profile] if profile is not None else spec['_profiles']):
        if profile['adapter'] != 'ace_native':
            continue
        dataset = profile.get('native', {}).get('dataset')
        if not dataset:
            raise ConfigurationError('native 고정 dataset 경로가 필요합니다')
        validate_profile(profile)
        cvdp = (prepare or preparation(spec['_root'])).sibling('native_cvdp')
        by_id = {row['id']: row for row in cvdp.load_pinned_rows(dataset)}
        for task in spec['_tasks']:
            raw = by_id.get(task.id)
            if raw is None or not cvdp.inspect_row(raw)['supported']:
                raise ConfigurationError('native 고정 원본에 없는/미지원 과제입니다')
            public = cvdp.public_row(raw)
            expected_evaluation = {'row': {**raw, 'output': public['output']},
                                   'targets': list(public['output']['context'])}
            files = dict(public['input']['context'])
            for name in public['output']['context']:
                files.setdefault(name, '')
            descriptor = json.loads(task.files.get('native-task.json', '{}'))
            actual_files = {key: value for key, value in task.files.items() if key != 'native-task.json'}
            if (task.evaluation != expected_evaluation or actual_files != files or
                    task.prompt != public['input']['prompt'] or descriptor != {**public, 'split': task.split}):
                raise ConfigurationError('native public 과제/평가 기준이 고정 원본과 다릅니다; private 평가 자료 수정은 허용하지 않습니다')


def native_trial_budget(optimizer, rows, options=None):
    config = native_stage_config(optimizer, options)
    train = sum(split == 'train' for split in rows.values())
    validation = sum(split == 'validation' for split in rows.values())
    tests = sum(split == 'test' for split in rows.values())
    allowance = 0 if optimizer == 'baseline' else train + config['iterations'] * (train + validation)
    return validation + allowance + 2 * tests


def write_native_selection(root: Path, optimizer: str, *, cids, rows, dataset: Path,
                           source: Path | None = None, upstream: Path | None = None,
                           python: Path | None = None, evaluator: dict | None = None,
                           name: str | None = None, options=None, max_trials=None,
                            wall_time=3600, trial_timeout=600, offline=False, prepare=None) -> Path:
    validate_selection(cids, rows, optimizer)
    app_path('experiments')
    config = native_stage_config(optimizer, options)
    positive(wall_time, 'max_wall_time_seconds')
    positive(trial_timeout, 'trial_timeout_seconds')
    minimum = native_trial_budget(optimizer, rows, options)
    if max_trials is not None and (type(max_trials) is not int or max_trials < minimum):
        raise ConfigurationError(f'native max_trials는 최소 {minimum}이어야 합니다')
    if evaluator is not None:
        if (not isinstance(evaluator, dict) or set(evaluator) - {'repo', 'python', 'sim_image', 'sim_image_id'} or
                not all(isinstance(value, str) and value and '\0' not in value for value in evaluator.values())):
            raise ConfigurationError('native evaluator에는 비밀 없는 repo/python/sim_image/sim_image_id 문자열만 허용합니다')
        for key in ('repo', 'python'):
            if key in evaluator and not Path(evaluator[key]).is_absolute():
                raise ConfigurationError(f'native evaluator.{key}에는 절대경로가 필요합니다')
        if any('://' in evaluator.get(key, '') for key in ('sim_image', 'sim_image_id')):
            raise ConfigurationError('native evaluator image에는 URL·자격증명을 지정할 수 없습니다')
    root = root.absolute()
    manifest = read_toml(safe_path(root, 'examples/ace-rtl/source-native.toml'))
    profile_template = read_toml(safe_path(root, 'examples/ace-rtl/harness-native.toml'))
    if (manifest.get('supported_harnesses') != ['ace_native'] or profile_template.get('adapter') != 'ace_native' or
            manifest.get('prompt_file') != 'native/guidance.md' or
            set(manifest.get('editable', [])) != {'native/guidance.md', 'native/orchestration.py'}):
        raise ConfigurationError('C native manifest/profile의 활성 계약이 일치하지 않습니다')
    source_timeout = manifest.get('source', {}).get('timeout_seconds', 60)
    positive(source_timeout, 'native source timeout_seconds')
    prep = prepare or preparation(root)
    dataset = Path(dataset).absolute()
    # Hash and row eligibility are checked before publishing source/config artifacts.
    inspect_selection(root, cids, rows, dataset, prepare=prep)
    if (source is None) == (upstream is None):
        raise ConfigurationError('준비된 --native-source 또는 로컬 고정 --native-upstream 하나를 지정하세요')
    if source is None:
        source = app_path('assets') / ('ace-native-' + uuid.uuid4().hex[:12])
        safe_path(source, '.')
        source.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='native-stage-', dir=source.parent) as directory:
            staged = Path(directory) / 'source'
            prep.prepare_source(Path(upstream).absolute(), staged)
            prep.verify_source(staged)
            if source.exists() or source.is_symlink():
                raise ConfigurationError('native source 게시 경로가 이미 있습니다')
            staged.rename(source)
    source = Path(source).absolute()
    prep.verify_source(source)
    for path in ('native/guidance.md', 'native/orchestration.py'):
        if not safe_path(source, path).is_file():
            raise ConfigurationError(f'native 활성 수정 파일이 없습니다: {path}')
    # Parse, never execute user-editable orchestration at generation time.
    import ast
    try:
        tree = ast.parse(safe_path(source, 'native/orchestration.py').read_text())
    except SyntaxError:
        raise ConfigurationError('native orchestration Python 구문이 잘못됐습니다') from None
    if not any(isinstance(node, ast.FunctionDef) and node.name == 'guidance' for node in tree.body):
        raise ConfigurationError('native orchestration의 guidance 함수가 없습니다')
    with tempfile.TemporaryDirectory() as directory:
        benchmark = Path(directory) / 'tasks.json'
        document = prep.prepare_dataset(dataset, benchmark, cids=cids, splits=rows)
        document['tasks'] = [task for task in document['tasks'] if task['id'] in rows]
        document['native']['selected_rows'] = dict(rows)
        write_json(benchmark, document)
        train = sum(split == 'train' for split in rows.values())
        validation = sum(split == 'validation' for split in rows.values())
        allowance = train + config.get('iterations', 0) * (train + validation)
        stages = [] if optimizer == 'baseline' else [{'id': optimizer, 'optimizer': optimizer,
                  'max_trials': allowance, 'config': config}]
        evaluator = dict(evaluator or {'repo': str(app_path('assets') / 'external/cvdp_benchmark'),
                                      'python': str(app_path('assets') / 'external/cvdp-venv/bin/python')})
        plugins = {'harnesses': {'ace_native': 'examples/ace-rtl/native_adapter.py:ACENative'},
                   'evaluators': {'cvdp_native': 'examples/ace-rtl/native_evaluator.py:NativeCVDPEvaluator'}}
        dependencies = {'harnesses/ace_native': NATIVE_DEPENDENCIES,
                        'evaluators/cvdp_native': NATIVE_DEPENDENCIES}
        folder = app_path('experiments') / ((identifier(name) if name else 'native') + '-' + uuid.uuid4().hex[:12])
        target = write_experiment(folder, agent=source, agent_id=manifest['id'],
            harness={'adapter': profile_template['adapter'], 'id': profile_template['id']},
            dataset={'benchmark': str(benchmark), 'evaluator': 'cvdp_native', 'evaluator_config': evaluator},
            stages=stages, plugins=plugins, dependencies=dependencies, name=name or 'ace-native-' + optimizer.replace('_', '-'),
            editable=manifest['editable'], prompt_file=manifest['prompt_file'],
            max_tasks=len(rows), project_root=root, max_trials=max_trials if max_trials is not None else native_trial_budget(optimizer, rows, options),
            wall_time=wall_time, trial_timeout=trial_timeout)
        try:
            source_lines = ['schema_version = 2', *[f'{key} = {_literal(manifest[key])}'
                for key in ('id', 'description', 'supported_harnesses', 'prompt_file', 'editable') if key in manifest], '',
                *_section('source', {'kind': 'local', 'path': str(source), 'timeout_seconds': source_timeout})]
            (folder / 'agent.toml').write_text('\n'.join(source_lines), encoding='utf-8')
            profile = folder / 'harness.toml'
            lines = [profile.read_text(), *_section('native', {
                'python': str(Path(python or sys.executable).absolute()), 'dataset': str(dataset),
                **{key: value for key, value in profile_template.get('native', {}).items()
                   if key in {'max_iterations', 'llm_timeout', 'evaluator_timeout'}}, 'evaluator': evaluator}),
                *_section('compatibility', {**{key: value for key, value in profile_template.get('compatibility', {}).items()
                    if key in {'execution_mode', 'agent_ids', 'dataset_ids', 'model_fields', 'roles', 'live_verification'}},
                    'reviewed_cids': sorted(cids)})]
            profile.write_text('\n'.join(lines), encoding='utf-8')
            from agent_optimizer.config import load_experiment
            generated = load_experiment(target)
            validate_profile(generated['_profiles'][0])
            return target
        except Exception:
            shutil.rmtree(folder)
            raise
