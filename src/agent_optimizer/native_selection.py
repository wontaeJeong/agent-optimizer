"""CLI/TUI가 공유하는 명시 native 선택·준비·설정 생성. 알고리즘은 예제 소유."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

from agent_optimizer.app_paths import app_path
from agent_optimizer.config import identifier, positive, read_toml
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.registry import NATIVE_DEPENDENCIES, is_source_checkout
from agent_optimizer.setup_wizard import _literal, _section, write_experiment
from agent_optimizer.results import write_json
from agent_optimizer.workspace import safe_path

CIDS = {'cid002', 'cid004', 'cid007', 'cid016'}


def resolve_native_project(root: Path) -> Path:
    """명시 작업공간 우선, 설치 배포가 선언한 native 예제 자산만 대체 출처로 소비한다."""
    root = Path(root).absolute()
    if safe_path(root, 'examples/ace-rtl/native_prepare.py').is_file():
        return root
    source_checkout = Path(__file__).resolve().parents[2]
    if is_source_checkout(source_checkout) and safe_path(source_checkout, 'examples/ace-rtl/native_prepare.py').is_file():
        return source_checkout
    from importlib.metadata import PackageNotFoundError, distribution
    try:
        installed = distribution('agent-optimizer')
        suffix = 'share/agent-optimizer/examples/ace-rtl/native_prepare.py'
        for file in installed.files or ():
            if str(file).replace('\\', '/').endswith(suffix):
                origin = Path(installed.locate_file(file)).resolve().parents[2]
                required = [*NATIVE_DEPENDENCIES, 'examples/ace-rtl/native_adapter.py']
                if all(safe_path(origin, name).is_file() for name in required):
                    return origin
    except PackageNotFoundError:
        pass
    raise ConfigurationError('native 연동 파일이 없습니다. native 예제를 포함한 고정 작업공간/설치 배포가 필요합니다; 기존 coding pin으로 대체하지 않습니다')


def preparation(root: Path):
    file = safe_path(resolve_native_project(root), 'examples/ace-rtl/native_prepare.py')
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
    from agent_optimizer.preset_tui import ace_stage_config, ACE_GUIDANCE, ACE_SCAFFOLD
    native_file = 'native/guidance.md' if optimizer == 'gepa' else 'native/orchestration.py'
    options = dict(options or {})
    if 'file' in options and options['file'] != native_file:
        raise ConfigurationError('native의 실제 활성 guidance/orchestration 파일만 선택하세요')
    if 'required_symbol' in options and options['required_symbol'] != 'guidance':
        raise ConfigurationError('native Meta-Harness는 guidance symbol을 사용합니다')
    if 'file' in options:
        options['file'] = ACE_GUIDANCE if optimizer == 'gepa' else ACE_SCAFFOLD
    if 'required_symbol' in options:
        options['required_symbol'] = 'prepare_task'
    config = ace_stage_config(optimizer, options)
    if optimizer != 'baseline':
        config['file'] = native_file
    if optimizer == 'meta_harness':
        config['required_symbol'] = 'guidance'
    return config


def inspect_selection(root, cids, rows, dataset):
    prep = preparation(Path(root))
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


def available_rows(root, dataset, cids):
    if not cids or not set(cids) <= CIDS:
        raise ConfigurationError('CID를 먼저 명시적으로 선택하세요')
    cvdp = preparation(Path(root)).sibling('native_cvdp')
    return [cvdp.inspect_row(row) for row in cvdp.load_pinned_rows(Path(dataset))
            if set(row['categories']).intersection(cids)]


def verify_native_selection(spec):
    """실행 직전 public descriptor·trusted 평가 row를 고정 원본과 재대조한다."""
    for profile in spec['_profiles']:
        if profile['adapter'] != 'ace_native':
            continue
        dataset = profile.get('native', {}).get('dataset')
        if not dataset:
            raise ConfigurationError('native 고정 dataset 경로가 필요합니다')
        cvdp = preparation(spec['_root']).sibling('native_cvdp')
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
                           wall_time=3600, trial_timeout=600, offline=False) -> Path:
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
    root = resolve_native_project(root)
    manifest = read_toml(safe_path(root, 'examples/ace-rtl/source-native.toml'))
    profile_template = read_toml(safe_path(root, 'examples/ace-rtl/harness-native.toml'))
    if (manifest.get('supported_harnesses') != ['ace_native'] or profile_template.get('adapter') != 'ace_native' or
            manifest.get('prompt_file') != 'native/guidance.md' or
            set(manifest.get('editable', [])) != {'native/guidance.md', 'native/orchestration.py'}):
        raise ConfigurationError('C native manifest/profile의 활성 계약이 일치하지 않습니다')
    source_timeout = manifest.get('source', {}).get('timeout_seconds', 60)
    positive(source_timeout, 'native source timeout_seconds')
    prep = preparation(root)
    dataset = Path(dataset).absolute()
    # Hash and row eligibility are checked before publishing source/config artifacts.
    inspect_selection(root, cids, rows, dataset)
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
            load_experiment(target)
            return target
        except Exception:
            shutil.rmtree(folder)
            raise
