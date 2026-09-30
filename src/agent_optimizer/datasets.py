"""Verified source acquisition shared by opt-in dataset providers."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from agent_optimizer import diagnostics
from agent_optimizer.app_paths import app_path
from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.results import write_json
from agent_optimizer.workspace import safe_path


def _git(*args: str, timeout: float = 180) -> str:
    command = _git_label(args)
    try:
        process = subprocess.run(["git", *args], capture_output=True, text=True,
                                 timeout=timeout, check=False, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        outcome = diagnostics.CommandOutcome(
            command, None,
            str(getattr(exc, "output", "") or ""),
            str(getattr(exc, "stderr", "") or ""),
            timed_out=isinstance(exc, subprocess.TimeoutExpired),
            error_kind=("missing" if isinstance(exc, FileNotFoundError) else
                        "permission" if isinstance(exc, PermissionError) else
                        "timeout" if isinstance(exc, subprocess.TimeoutExpired) else
                        type(exc).__name__.lower()),
        )
        raise _git_failure(diagnostics.summarize_failure(outcome),
                           "Check Git, network access, and the pinned source commit.") from None
    if process.returncode:
        outcome = diagnostics.CommandOutcome(command, process.returncode,
                                             process.stdout or "", process.stderr or "")
        raise _git_failure(diagnostics.summarize_failure(outcome),
                           "Check source availability and preserve the pinned commit.") from None
    return process.stdout.strip()


def _git_label(args: tuple[str, ...]) -> str:
    for index, argument in enumerate(args):
        if argument == "-C":
            continue
        if index and args[index - 1] == "-C":
            continue
        if not argument.startswith("-"):
            return f"git {argument}"
    return "git"


def _git_failure(cause: str, fix: str) -> UnavailableError:
    error = UnavailableError(cause)
    error.failure_diagnostic = {
        "stage": "dataset Git checkout",
        "cause": cause,
        "log": None,
        "fix": fix,
        "retry": "agent-opt datasets prepare",
    }
    return error


def _verify(path: Path, revision: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ConfigurationError("Dataset cache is not a regular directory")
    try:
        actual = _git("-C", str(path), "rev-parse", "HEAD")
        dirty = _git("-C", str(path), "status", "--porcelain", "--untracked-files=all")
    except UnavailableError as exc:
        error = ConfigurationError("Dataset cache is not a valid pinned checkout")
        error.failure_diagnostic = getattr(exc, "failure_diagnostic", {
            "stage": "dataset Git checkout", "cause": diagnostics.summarize_exception(exc),
            "log": None, "fix": "Preserve the cache and repair the pinned source checkout.",
            "retry": "agent-opt datasets prepare",
        })
        raise error from None
    if actual != revision or dirty:
        raise ConfigurationError("Dataset cache differs from pinned revision; preserve it and repair cache")


def acquire_pinned_git(target: Path, url: str, revision: str, *, offline: bool = False) -> Path:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ConfigurationError("Dataset Git revision must be a full commit SHA")
    safe_path(target.parent, target.name)
    if target.is_symlink():
        raise ConfigurationError("Dataset cache cannot be a symlink")
    if target.exists():
        _verify(target, revision)
        return target
    if offline:
        error = UnavailableError("Pinned dataset checkout unavailable offline")
        error.failure_diagnostic = {
            "stage": "dataset Git checkout",
            "cause": "offline cache miss: pinned Git checkout is missing",
            "log": None,
            "fix": "Prepare the pinned source checkout while online before using offline mode.",
            "retry": "agent-opt datasets prepare",
        }
        raise error
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dataset-checkout-", dir=target.parent) as temporary:
        staged = Path(temporary) / "source"
        _git("clone", "--quiet", "--no-checkout", url, str(staged))
        _git("-C", str(staged), "checkout", "--quiet", "--detach", revision)
        _verify(staged, revision)
        if target.exists():
            _verify(target, revision)
        else:
            try:
                staged.rename(target)
            except OSError:
                if not target.exists() and not target.is_symlink():
                    raise
                _verify(target, revision)
    return target


def split_families(families: list[str]) -> dict[str, str]:
    ordered = sorted(set(families), key=lambda name: (hashlib.sha256(name.encode()).hexdigest(), name))
    if len(ordered) < 3:
        raise ConfigurationError("At least three distinct task families are required for train/validation/test")
    train_count = min(max(1, int(len(ordered) * 0.7)), len(ordered) - 2)
    validation_count = max(1, (len(ordered) - train_count) // 2)
    return {family: ("train" if index < train_count else
                     "validation" if index < train_count + validation_count else "test")
            for index, family in enumerate(ordered)}


class CustomDataset:
    def __init__(self, source: Path, *, evaluator: str):
        self.source = source
        self.evaluator = evaluator

    def describe(self) -> dict:
        return {"name": self.source.stem, "task_form": "custom", "evaluator": self.evaluator}

    def prepare(self, cache: Path | None = None, *, offline: bool = False) -> dict:
        if not self.evaluator:
            raise ConfigurationError("Custom dataset requires a registered evaluator")
        raw = self.source.read_bytes()
        data = json.loads(raw)
        if data.get("schema_version") != 1 or not isinstance(data.get("tasks"), list) or not data["tasks"]:
            raise ConfigurationError("Custom dataset requires schema_version=1 and nonempty tasks")
        tasks = data["tasks"]
        if any("split" not in task for task in tasks):
            if any("split" in task or not task.get("family") for task in tasks):
                raise ConfigurationError("Custom dataset needs every task family for automatic split")
            splits = split_families([task["family"] for task in tasks])
            tasks = [{**task, "split": splits[task["family"]]} for task in tasks]
        document = {**data, "tasks": tasks, "source_sha256": hashlib.sha256(raw).hexdigest()}
        filename = self.source.stem + '.json'
        if cache is None:
            cache = app_path('cache') / 'datasets'
            filename = self.source.stem + '-' + document['source_sha256'][:16] + '.json'
        output = safe_path(cache, 'custom/' + filename)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".json", delete=False) as stream:
            temporary = Path(stream.name)
        from agent_optimizer.config import load_tasks
        try:
            write_json(temporary, document)
            load_tasks(temporary)
            try:
                os.link(temporary, output)
            except FileExistsError:
                safe_path(cache, 'custom/' + filename)
                if output.read_bytes() != temporary.read_bytes():
                    raise ConfigurationError('준비된 사용자 데이터셋 파일이 변경됐습니다. 기존 파일을 보존하세요') from None
        finally:
            temporary.unlink(missing_ok=True)
        return {"benchmark": str(output), "evaluator": self.evaluator,
                "provenance": {"source": str(self.source), "sha256": document["source_sha256"]}}
