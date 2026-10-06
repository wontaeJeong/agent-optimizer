"""제품의 native 연동 출처를 해석하고 선택값을 예제 helper에 전달하는 thin 연결."""
import importlib.util
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.registry import NATIVE_DEPENDENCIES, is_source_checkout
from agent_optimizer.workspace import safe_path


def resolve_native_project(root: Path) -> Path:
    root = Path(root).absolute()
    if safe_path(root, 'examples/ace-rtl/native_prepare.py').is_file():
        return root
    source_checkout = Path(__file__).resolve().parents[2]
    if is_source_checkout(source_checkout) and safe_path(source_checkout, 'examples/ace-rtl/native_prepare.py').is_file():
        return source_checkout
    from importlib.metadata import PackageNotFoundError, distribution
    try:
        installed = distribution('agent-optimizer')
        declared = {Path(installed.locate_file(file)).resolve() for file in installed.files or ()}
        for file in installed.files or ():
            if str(file).replace('\\', '/').endswith('share/agent-optimizer/examples/ace-rtl/native_prepare.py'):
                origin = Path(installed.locate_file(file)).resolve().parents[2]
                if all(safe_path(origin, name).is_file() and safe_path(origin, name).resolve() in declared
                       for name in [*NATIVE_DEPENDENCIES, 'examples/ace-rtl/native_adapter.py']):
                    return origin
    except PackageNotFoundError:
        pass
    raise ConfigurationError('native 연동 파일이 없습니다. 고정 작업공간/설치 배포가 필요합니다; 기존 coding pin으로 대체하지 않습니다')


def preparation(root: Path):
    file = safe_path(resolve_native_project(root), 'examples/ace-rtl/native_prepare.py')
    spec = importlib.util.spec_from_file_location('_product_native_prepare', file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selection_policy(root: Path):
    prepare = preparation(root)
    return prepare.sibling('native_selection'), prepare


def validate_selection(cids, rows, optimizer, *, root=None):
    policy, _ = selection_policy(root or Path.cwd())
    return policy.validate_selection(cids, rows, optimizer)


def validate_product_options(root, **options):
    policy, _ = selection_policy(root)
    return policy.validate_product_options(**options)


def validate_field(root, field, value):
    policy, _ = selection_policy(root)
    return policy.validate_field(field, value)


def native_stage_config(optimizer, options=None, *, root=None):
    policy, _ = selection_policy(root or Path.cwd())
    return policy.native_stage_config(optimizer, options)


def inspect_selection(root, cids, rows, dataset):
    policy, prepare = selection_policy(root)
    return policy.inspect_selection(root, cids, rows, dataset, prepare=prepare)


def available_rows(root, dataset, cids):
    policy, prepare = selection_policy(root)
    return policy.available_rows(root, dataset, cids, prepare=prepare)


def verify_native_selection(spec, profile=None):
    policy, prepare = selection_policy(spec['_root'])
    return policy.verify_native_selection(spec, profile, prepare=prepare)


def diagnose_native_selection(spec, *, retry):
    policy, prepare = selection_policy(spec['_root'])
    return policy.diagnose_selection(spec, retry=retry, prepare=prepare)


def native_trial_budget(optimizer, rows, options=None, *, root=None):
    policy, _ = selection_policy(root or Path.cwd())
    return policy.native_trial_budget(optimizer, rows, options)


def write_native_selection(root: Path, optimizer: str, **selection) -> Path:
    root = resolve_native_project(root)
    policy, prepare = selection_policy(root)
    return policy.write_native_selection(root, optimizer, prepare=prepare, **selection)
