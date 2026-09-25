"""Acquire selected, pinned integration files into a user-owned workspace."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from agent_optimizer.catalog import INTEGRATIONS
from agent_optimizer.config import read_toml
from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.datasets import acquire_pinned_git
from agent_optimizer.results import write_json
from agent_optimizer.workspace import safe_path


ACE_DIRECTORIES = ("examples/ace-rtl", "examples/rtl-debugger", "examples/benchmarks",
                   "experiments/simple-feedback")
ACE_FILES = ("src/agent_optimizer/models.py",)
DATASET_FILES = {
    "cvdp": ("examples/benchmarks/cvdp.py", "examples/ace-rtl/prepare.py",
             "examples/ace-rtl/environment/setup.py", "examples/ace-rtl/evaluator.py",
             "examples/ace-rtl/environment/network_driver.py",
             "examples/ace-rtl/environment/requirements-cvdp-py312.txt"),
    "verilog-spec": ("examples/benchmarks/verilog_eval.py",
                     "examples/benchmarks/verilog_evaluator.py",
                     "examples/benchmarks/Dockerfile.iverilog12"),
    "verilog-completion": ("examples/benchmarks/verilog_eval.py",
                           "examples/benchmarks/verilog_evaluator.py",
                           "examples/benchmarks/Dockerfile.iverilog12"),
}


def selected_files(source: Path, integration_id: str) -> list[Path]:
    if integration_id == "ace-rtl":
        paths = []
        for directory in ACE_DIRECTORIES:
            folder = safe_path(source, directory)
            if not folder.is_dir():
                raise ConfigurationError(f"선택한 연동 디렉터리가 없습니다: {directory}")
            paths.extend(folder.rglob("*"))
        paths += [source / name for name in ACE_FILES]
    elif integration_id in DATASET_FILES:
        paths = [source / name for name in DATASET_FILES[integration_id]]
    else:
        raise ConfigurationError(f"지원하지 않는 선택형 연동: {integration_id}")
    files = []
    for path in sorted(paths):
        relative = path.relative_to(source).as_posix()
        safe_path(source, relative)
        if path.is_dir():
            continue
        if not path.is_file() or path.is_symlink():
            raise ConfigurationError(f"연동 파일이 일반 파일이 아닙니다: {relative}")
        if path.name == ".env" or path.name.startswith(".env."):
            continue
        files.append(path)
    if not files:
        raise ConfigurationError(f"선택한 연동 파일이 없습니다: {integration_id}")
    return files


def acquire_integration(workspace: Path, integration_id: str, *, offline: bool = False,
                        source_url: str | None = None, revision: str | None = None,
                        cache_dir: Path | None = None) -> dict:
    if integration_id not in INTEGRATIONS:
        raise ConfigurationError(f"지원하지 않는 선택형 연동: {integration_id}")
    if (source_url is None) != (revision is None):
        raise ConfigurationError("개발용 연동 출처와 전체 commit을 함께 지정하세요")
    if workspace.is_symlink():
        raise ConfigurationError("실험 작업공간은 symlink일 수 없습니다")
    workspace = workspace.resolve()
    safe_path(workspace, ".")
    if not workspace.is_dir():
        raise ConfigurationError(f"실험 작업공간이 없습니다: {workspace}")
    stage_root = safe_path(workspace, ".agent-opt")
    source_info = INTEGRATIONS[integration_id]
    url = source_url or source_info["url"]
    commit = revision or source_info["revision"]
    cache_home = Path(os.environ["XDG_CACHE_HOME"]).expanduser() if os.environ.get("XDG_CACHE_HOME") else Path.home() / ".cache"
    cache = cache_dir or cache_home / "agent-optimizer/integrations"
    source = acquire_pinned_git(cache / commit, url, commit, offline=offline)
    originals = selected_files(source, integration_id)
    for original in originals:
        relative = original.relative_to(source).as_posix()
        destination = safe_path(workspace, relative)
        if destination.exists() and (not destination.is_file()
                                     or hashlib.sha256(destination.read_bytes()).digest()
                                     != hashlib.sha256(original.read_bytes()).digest()):
            raise ConfigurationError(f"사용자 파일과 연동 파일이 충돌합니다: {relative}")
    stage_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="staging-", dir=stage_root) as directory:
        staged = Path(directory)
        for original in originals:
            relative = original.relative_to(source)
            destination = staged / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, destination)
        for original in originals:
            relative = original.relative_to(source).as_posix()
            destination = safe_path(workspace, relative)
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".pending")
            if temporary.exists() or temporary.is_symlink():
                raise ConfigurationError(f"임시 연동 파일이 이미 있습니다: {relative}")
            shutil.copyfile(staged / relative, temporary)
            temporary.replace(destination)
    return {"url": url, "revision": commit,
            "paths": [path.relative_to(source).as_posix() for path in originals]}


def write_pending_experiment(workspace: Path, integration_id: str) -> Path:
    if integration_id != "ace-rtl":
        raise ConfigurationError(f"실험 프로필을 지원하지 않습니다: {integration_id}")
    if workspace.is_symlink():
        raise ConfigurationError("실험 작업공간은 symlink일 수 없습니다")
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    path = safe_path(workspace, "experiment.toml")
    if path.exists() or path.is_symlink():
        raise ConfigurationError(f"실험 선언이 이미 있습니다: {path}")
    revision = INTEGRATIONS[integration_id]["revision"]
    content = ('schema_version = 1\n[integration]\n'
               f'id = "{integration_id}"\nrevision = "{revision}"\n'
               'contract = 1\nconfig = "examples/ace-rtl/experiment.toml"\n')
    temporary = safe_path(workspace, "experiment.toml.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ConfigurationError(f"임시 실험 선언이 이미 있습니다: {temporary}")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    return path


def read_pointer(path: Path) -> tuple[Path, dict]:
    path = path.resolve()
    data = read_toml(path)
    if set(data) != {"schema_version", "integration"} or data["schema_version"] != 1:
        raise ConfigurationError("선택형 연동 실험 선언 형식이 올바르지 않습니다")
    integration = data["integration"]
    if not isinstance(integration, dict) or set(integration) != {"id", "revision", "contract", "config"}:
        raise ConfigurationError("선택형 연동 ID·pin·계약 형식이 올바르지 않습니다")
    selected = INTEGRATIONS.get(integration["id"])
    if (selected is None or integration["revision"] != selected["revision"]
            or integration["contract"] != selected["contract"]
            or integration["config"] != "examples/ace-rtl/experiment.toml"
            or integration["id"] != "ace-rtl"):
        raise ConfigurationError("선택형 연동의 고정 출처/계약이 설치된 카탈로그와 다릅니다")
    return path.parent, integration


def verified_integration(workspace: Path) -> dict | None:
    marker = safe_path(workspace, ".agent-opt/integration-ready.json")
    if not marker.exists():
        return None
    try:
        ready = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ConfigurationError("연동 준비 기록을 읽을 수 없습니다") from None
    if not isinstance(ready, dict) or ready.get("id") not in INTEGRATIONS:
        raise ConfigurationError("연동 준비 기록의 ID가 올바르지 않습니다")
    expected = INTEGRATIONS[ready["id"]]
    if (ready.get("revision") != expected["revision"] or ready.get("ready") is not True
            or ready.get("url") != expected["url"] or ready.get("contract") != expected["contract"]):
        raise ConfigurationError("연동 준비 기록의 ID·pin이 실험 선언과 다릅니다")
    files = ready.get("files")
    if not isinstance(files, dict) or not files:
        raise ConfigurationError("연동 준비 파일 목록이 없습니다")
    for relative, digest in files.items():
        if (not isinstance(relative, str) or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ConfigurationError("연동 파일 해시가 올바르지 않습니다")
        selected = safe_path(workspace, relative)
        if not selected.is_file() or hashlib.sha256(selected.read_bytes()).hexdigest() != digest:
            raise ConfigurationError(f"준비된 연동 파일이 변경됐습니다: {relative}")
    return ready


def integration_plugins(integration_id: str) -> tuple[dict, dict]:
    if integration_id in {"ace-rtl", "cvdp"}:
        return ({"datasets": {"cvdp": "examples/benchmarks/cvdp.py:Provider"},
                 "evaluators": {"cvdp": "examples/ace-rtl/evaluator.py:CVDPEvaluator"}},
                {"datasets/cvdp": ["examples/ace-rtl/prepare.py",
                                   "examples/ace-rtl/environment/setup.py"],
                 "evaluators/cvdp": ["examples/ace-rtl/environment/network_driver.py"]})
    if integration_id in {"verilog-spec", "verilog-completion"}:
        symbol = "Provider" if integration_id == "verilog-spec" else "CompletionProvider"
        return ({"datasets": {integration_id: f"examples/benchmarks/verilog_eval.py:{symbol}"},
                 "evaluators": {"verilog_eval":
                                "examples/benchmarks/verilog_evaluator.py:VerilogEvaluator"}},
                {"datasets/" + integration_id: ["examples/benchmarks/Dockerfile.iverilog12"],
                 "evaluators/verilog_eval": ["examples/benchmarks/verilog_eval.py"]})
    raise ConfigurationError(f"지원하지 않는 선택형 연동: {integration_id}")


def resolve_pointer(path: Path) -> Path:
    workspace, integration = read_pointer(path)
    ready = verified_integration(workspace)
    if ready is None:
        raise UnavailableError(f"연동 준비가 필요합니다: agent-opt prepare {path}")
    if ready["id"] != integration["id"] or ready["revision"] != integration["revision"]:
        raise ConfigurationError("연동 준비 기록이 선택한 실험과 다릅니다")
    return safe_path(workspace, integration["config"])


def prepare_pointer(path: Path, *, offline: bool = False) -> dict:
    workspace, integration = read_pointer(path)
    obtained = acquire_integration(workspace, integration["id"], offline=offline)
    if (obtained["url"] != INTEGRATIONS[integration["id"]]["url"]
            or obtained["revision"] != integration["revision"]):
        raise ConfigurationError("연동 출처가 선택한 고정 버전과 다릅니다")
    lifecycle_file = safe_path(workspace, "examples/ace-rtl/environment/lifecycle.py")
    if not lifecycle_file.is_file():
        raise ConfigurationError("선택한 ACE lifecycle이 없습니다")
    loaded = importlib.util.spec_from_file_location("ace_prepared_lifecycle", lifecycle_file)
    if loaded is None or loaded.loader is None:
        raise ConfigurationError("ACE lifecycle을 불러올 수 없습니다")
    lifecycle = importlib.util.module_from_spec(loaded)
    loaded.loader.exec_module(lifecycle)
    lifecycle.prepare(workspace, offline=offline)
    report = lifecycle.inspect(workspace)
    if not report["ready"]:
        raise UnavailableError("ACE 평가 실행환경을 준비하지 못했습니다")
    publish_marker(workspace, integration["id"], obtained)
    return {"experiment": path.resolve(), "profile": integration["id"], "ready": True}


def publish_marker(workspace: Path, integration_id: str, obtained: dict) -> None:
    source = INTEGRATIONS[integration_id]
    if obtained["url"] != source["url"] or obtained["revision"] != source["revision"]:
        raise ConfigurationError("준비된 연동 출처가 카탈로그와 다릅니다")
    fingerprint = {relative: hashlib.sha256(safe_path(workspace, relative).read_bytes()).hexdigest()
                   for relative in obtained["paths"]}
    marker = safe_path(workspace, ".agent-opt/integration-ready.json")
    write_json(marker, {"ready": True, "id": integration_id,
                        "revision": source["revision"], "contract": source["contract"],
                        "url": obtained["url"], "files": fingerprint})


def prepare_catalog_dataset(workspace: Path, selection: str, *, offline: bool = False) -> dict:
    from agent_optimizer.registry import Registry

    if selection not in {"cvdp", "verilog-spec", "verilog-completion"}:
        raise ConfigurationError(f"지원하지 않는 데이터셋: {selection}")
    workspace = workspace.resolve()
    obtained = acquire_integration(workspace, selection, offline=offline)
    plugins, dependencies = integration_plugins(selection)
    registry = Registry()
    from agent_optimizer.registry import plugin_files
    plugin_files(workspace, plugins, dependencies)
    registry.load_plugins(workspace, plugins)
    provider = registry.resolve("datasets", selection)()
    result = provider.prepare(workspace / "external/datasets" / selection, offline=offline)
    if result.get("evaluator") not in plugins["evaluators"]:
        raise ConfigurationError("선택한 데이터셋의 평가기 등록이 일치하지 않습니다")
    registry.resolve("evaluators", result["evaluator"])
    checks = provider.doctor(workspace / "external/datasets" / selection)
    if not checks or any(row.get("status") != "ok" for row in checks):
        raise UnavailableError(f"데이터셋 준비 진단 실패: {selection}")
    publish_marker(workspace, selection, obtained)
    return {**result, "dataset_provider": selection}
