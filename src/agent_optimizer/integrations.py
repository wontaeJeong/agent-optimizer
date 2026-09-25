"""Acquire selected, pinned integration files into a user-owned workspace."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path

from agent_optimizer.catalog import INTEGRATIONS
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.datasets import acquire_pinned_git
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
    cache = cache_dir or Path.home() / ".cache/agent-optimizer/integrations"
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
