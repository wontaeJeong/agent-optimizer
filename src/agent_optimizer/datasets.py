"""Verified source acquisition shared by opt-in dataset providers."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.results import write_json


def _git(*args: str, timeout: float = 180) -> str:
    try:
        process = subprocess.run(["git", *args], capture_output=True, text=True,
                                 timeout=timeout, check=False, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UnavailableError(f"Dataset Git operation unavailable: {type(exc).__name__}") from None
    if process.returncode:
        raise UnavailableError("Dataset Git checkout failed; check source availability and pin")
    return process.stdout.strip()


def _verify(path: Path, revision: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ConfigurationError("Dataset cache is not a regular directory")
    try:
        actual = _git("-C", str(path), "rev-parse", "HEAD")
        dirty = _git("-C", str(path), "status", "--porcelain", "--untracked-files=all")
    except UnavailableError as exc:
        raise ConfigurationError("Dataset cache is not a valid pinned checkout") from exc
    if actual != revision or dirty:
        raise ConfigurationError("Dataset cache differs from pinned revision; preserve it and repair cache")


def acquire_pinned_git(target: Path, url: str, revision: str, *, offline: bool = False) -> Path:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ConfigurationError("Dataset Git revision must be a full commit SHA")
    if target.is_symlink():
        raise ConfigurationError("Dataset cache cannot be a symlink")
    if target.exists():
        _verify(target, revision)
        return target
    if offline:
        raise UnavailableError(f"Pinned dataset checkout unavailable offline: {target.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dataset-checkout-", dir=target.parent) as temporary:
        staged = Path(temporary) / "source"
        _git("clone", "--quiet", "--no-checkout", url, str(staged))
        _git("-C", str(staged), "checkout", "--quiet", "--detach", revision)
        _verify(staged, revision)
        if target.exists():
            _verify(target, revision)
        else:
            staged.rename(target)
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

    def prepare(self, cache: Path, *, offline: bool = False) -> dict:
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
        output = cache / "custom" / (self.source.stem + ".json")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".json", delete=False) as stream:
            temporary = Path(stream.name)
        from agent_optimizer.config import load_tasks
        try:
            write_json(temporary, document)
            load_tasks(temporary)
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
        return {"benchmark": str(output), "evaluator": self.evaluator,
                "provenance": {"source": str(self.source), "sha256": document["source_sha256"]}}
