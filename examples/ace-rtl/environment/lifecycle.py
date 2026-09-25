"""Example-local preparation and execution entry points for a selected ACE profile."""

import importlib.util
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.results import write_json
from agent_optimizer.workspace import safe_path


def load_example(root: Path, relative: str, name: str):
    path = safe_path(root, relative)
    if not path.is_file():
        raise ConfigurationError(f"ACE 연동 파일이 없습니다: {relative}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ConfigurationError(f"ACE 연동 파일을 불러올 수 없습니다: {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(root: Path, *, offline: bool = False, platform: str | None = None) -> Path:
    root = root.resolve()
    setup = load_example(root, "examples/ace-rtl/environment/setup.py", "ace_lifecycle_setup")
    importer = load_example(root, "examples/ace-rtl/prepare.py", "ace_lifecycle_import")
    demo = load_example(root, "examples/ace-rtl/environment/demo.py", "ace_lifecycle_demo")
    dataset, lock = setup.prepare_environment(offline=offline, platform=platform)
    target = root / "datasets/ace-demo/tasks.json"
    manifest = importer.prepare_dataset(dataset, target.with_name("all-tasks.json"), lock)
    write_json(target, demo.select_tasks(manifest))
    return target
