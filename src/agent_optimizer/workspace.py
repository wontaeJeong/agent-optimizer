from __future__ import annotations

import difflib
import fnmatch
import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath

from agent_optimizer.contracts import AgentSpec, Candidate, ConfigurationError


def safe_path(root: Path, relative: str) -> Path:
    part = PurePosixPath(relative)
    if not relative or part.is_absolute() or ".." in part.parts or "\\" in relative:
        raise ConfigurationError(f"Unsafe relative path: {relative!r}")
    path = root.joinpath(*part.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ConfigurationError(f"Path escapes workspace: {relative!r}")
    return path


def regular_files(root: Path):
    for path in sorted(root.rglob("*")):
        if any(part in {"__pycache__", ".git", ".venv", ".pytest_cache"}
               for part in path.relative_to(root).parts) or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ConfigurationError(f"Symlinks are not supported in snapshots: {path}")
        if path.is_file():
            yield path


def digest(root: Path) -> str:
    result = hashlib.sha256()
    for path in regular_files(root):
        result.update(path.relative_to(root).as_posix().encode() + b"\0")
        result.update(hashlib.sha256(path.read_bytes()).digest())
        result.update(str(path.stat().st_mode & 0o111).encode())
    return result.hexdigest()


def copy_tree(source: Path, target: Path) -> None:
    list(regular_files(source))
    shutil.copytree(source, target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", ".git", ".venv", ".pytest_cache", "*.pyc"))


class CandidateStore:
    def __init__(self, root: Path, agent: AgentSpec):
        if agent.bundle is None:
            raise ConfigurationError("Materialize the external Agent source before creating candidates")
        self.root = root
        self.agent = agent
        root.mkdir(parents=True, exist_ok=True)
        self._counter = 0

    def create(
        self, parent: Candidate | None = None, edits: dict[str, str] | None = None,
        producer: str = "baseline",
    ) -> Candidate:
        self._counter += 1
        candidate_id = f"c{self._counter:04d}"
        dest = self.root / candidate_id / "bundle"
        if parent and parent.agent_id != self.agent.id:
            raise ConfigurationError("Cross-agent candidate transfer needs an explicit translator")
        edits = edits or {}
        for rel in edits:
            safe_path(dest, rel)
            if not any(fnmatch.fnmatchcase(rel, pat) for pat in self.agent.editable):
                raise ConfigurationError(f"Not in the editable search space: {rel}")
        copy_tree(parent.path if parent else self.agent.bundle, dest)
        patches = []
        for rel, contents in edits.items():
            path = safe_path(dest, rel)
            previous = path.read_text(encoding="utf-8") if path.exists() else ""
            patches.extend(difflib.unified_diff(previous.splitlines(keepends=True), contents.splitlines(keepends=True), fromfile="a/"+rel, tofile="b/"+rel))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
        (dest.parent / "changes.diff").write_text("".join(patches), encoding="utf-8")
        value = Candidate(candidate_id, self.agent.id, dest, digest(dest),
                          (parent.id,) if parent else (), producer)
        (dest.parent / "candidate.json").write_text(json.dumps({
            "schema_version": 1, "id": value.id, "agent_id": value.agent_id,
            "content_hash": value.content_hash, "parents": value.parents,
            "producer": producer, "changed_files": list(edits),
        }, indent=2), encoding="utf-8")
        return value


def collect_outputs(source: Path, target: Path) -> None:
    """Copy only regular task output files; never follow links into agent/host data."""
    target.mkdir(parents=True, exist_ok=True)
    for path in regular_files(source):
        rel = path.relative_to(source).as_posix()
        out = safe_path(target, rel)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)
