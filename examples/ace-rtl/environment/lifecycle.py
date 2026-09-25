"""Example-local preparation and execution entry points for a selected ACE profile."""

import importlib.util
import os
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.network import demo_environment, network_environment
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


def inspect(root: Path, *, platform: str | None = None,
            environment: dict[str, str] | None = None) -> dict:
    root = root.resolve()
    diagnostics = load_example(root, "examples/ace-rtl/environment/diagnostics.py",
                               "ace_lifecycle_diagnostics")
    values = demo_environment(environment)
    values["PATH"] = str(root / ".cache/uv/bin") + os.pathsep + values.get("PATH", os.defpath)
    values.update(network_environment(values))
    checks = diagnostics.collect_checks(root, platform, environment=values)
    ready = all(row["status"] == "ok" for row in checks if row["area"] == "evaluation")
    lock = None
    image = None
    if ready:
        setup = load_example(root, "examples/ace-rtl/environment/setup.py", "ace_lifecycle_inspect")
        lock = setup.read_environment_lock(root / "external/environment-lock.json")
        image = setup.verified_sim_image(lock)
    return {"ready": ready, "checks": checks, "lock": lock,
            "platform": lock["platform"] if lock else platform, "sim_image": image}


def run(root: Path, *, iterations: int | None = None, platform: str | None = None) -> int:
    root = root.resolve()
    previous = os.environ.copy()
    try:
        setup = load_example(root, "examples/ace-rtl/environment/setup.py", "ace_lifecycle_run_setup")
        setup.validate_live()
        os.environ.update(demo_environment())
        os.environ.update(network_environment())
        report = inspect(root, platform=platform)
        if not report["ready"]:
            failures = [check["id"] for check in report["checks"]
                        if check["area"] == "evaluation" and check["status"] != "ok"]
            raise UnavailableError("ACE 평가 실행환경 미준비: " + ", ".join(failures))
        os.environ["DOCKER_DEFAULT_PLATFORM"] = report["platform"]
        os.environ["OSS_SIM_IMAGE"] = report["sim_image"]
        checks = load_example(root, "examples/ace-rtl/environment/checks.py",
                              "ace_lifecycle_run_checks")
        return checks.live(report["lock"], iterations=iterations)
    finally:
        os.environ.clear()
        os.environ.update(previous)
