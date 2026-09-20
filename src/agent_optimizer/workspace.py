from __future__ import annotations

import difflib
import fnmatch
import hashlib
import json
import shutil
import stat
from pathlib import Path, PurePosixPath

from agent_optimizer.contracts import AgentSpec, Candidate, ConfigurationError


def safe_path(root: Path, relative: str) -> Path:
    part = PurePosixPath(relative)
    if not relative or part.is_absolute() or ".." in part.parts or "\\" in relative:
        raise ConfigurationError(f"Unsafe relative path: {relative!r}")
    # Check the controlled boundary and its components, not host ancestors such
    # as macOS /var -> /private/var. Missing components may be created later.
    current = root
    components = [root]
    for name in part.parts:
        current = current / name
        components.append(current)
    for index, component in enumerate(components):
        try:
            mode = component.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise ConfigurationError(f"Symlinks are not supported in workspaces: {component}")
        if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise ConfigurationError(f"Special files are not supported in workspaces: {component}")
        if (index == 0 or index < len(components) - 1) and not stat.S_ISDIR(mode):
            raise ConfigurationError(f"Workspace component is not a directory: {component}")
    path = root.joinpath(*part.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ConfigurationError(f"Path escapes workspace: {relative!r}")
    return path


def regular_files(root: Path):
    safe_path(root, ".")
    if not root.is_dir():
        raise ConfigurationError(f"Workspace directory does not exist: {root}")
    for entry in sorted(root.iterdir()):
        path = safe_path(root, entry.name)
        if path.is_dir():
            yield from regular_files(path)
        else:
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
    safe_path(target, ".")
    if target.exists():
        list(regular_files(target))
    shutil.copytree(source, target, dirs_exist_ok=True)


class CandidateStore:
    def __init__(self, root: Path, agent: AgentSpec):
        if agent.bundle is None:
            raise ConfigurationError("Materialize the external Agent source before creating candidates")
        self.root = root
        self.agent = agent
        safe_path(root, ".")
        root.mkdir(parents=True, exist_ok=True)
        self._counter = 0
        self._issued: dict[str, Candidate] = {}

    def verify(self, candidate: Candidate) -> None:
        if self._issued.get(candidate.id) != candidate:
            raise ConfigurationError("Candidate metadata does not match a candidate issued by this store")
        safe_path(self.root, candidate.path.relative_to(self.root).as_posix())
        if digest(candidate.path) != candidate.content_hash:
            raise ConfigurationError("Candidate snapshot was mutated; create a new candidate")

    def create(
        self, parent: Candidate | None = None, edits: dict[str, str] | None = None,
        producer: str = "baseline",
    ) -> Candidate:
        if parent is not None:
            self.verify(parent)
        self._counter += 1
        candidate_id = f"c{self._counter:04d}"
        dest = safe_path(self.root, f"{candidate_id}/bundle")
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
        safe_path(dest.parent, "changes.diff").write_text("".join(patches), encoding="utf-8")
        value = Candidate(candidate_id, self.agent.id, dest, digest(dest),
                          (parent.id,) if parent else (), producer)
        safe_path(dest.parent, "candidate.json").write_text(json.dumps({
            "schema_version": 1, "id": value.id, "agent_id": value.agent_id,
            "content_hash": value.content_hash, "parents": value.parents,
            "producer": producer, "changed_files": list(edits),
        }, indent=2), encoding="utf-8")
        self._issued[value.id] = value
        return value


def collect_outputs(source: Path, target: Path) -> None:
    """Copy only regular task output files; never follow links into agent/host data."""
    files = list(regular_files(source))
    safe_path(target, ".")
    outputs = [safe_path(target, path.relative_to(source).as_posix()) for path in files]
    for out in outputs:
        if out.is_dir():
            raise ConfigurationError(f"Output file destination is a directory: {out}")
    target.mkdir(parents=True, exist_ok=True)
    for path, out in zip(files, outputs):
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)
