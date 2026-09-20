from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from agent_optimizer.contracts import AgentSpec, ConfigurationError, SourceSpec, UnavailableError
from agent_optimizer.workspace import digest, safe_path
from agent_optimizer.results import write_json


IGNORED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".vscode", ".idea"}
DEVELOPER_PARTS = {".claude", ".codex", ".cursor", ".opencode"}
CREDENTIAL_FILES = {"auth.json", "auth.jsonc", "credentials", "credentials.json",
                    ".credentials.json", ".netrc", "_netrc", ".git-credentials"}


def validate_source(source: SourceSpec) -> None:
    if source.kind not in {"local", "git"}:
        raise ConfigurationError("source.kind must be local or git")
    safe_path(Path("/schema-validation"), source.subdir)
    if source.kind == "local":
        if source.path is None or source.url or source.revision:
            raise ConfigurationError("local source requires path and does not accept url/revision")
    else:
        if source.path or not source.url or not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", source.revision or ""):
            raise ConfigurationError("git source requires url and a full commit SHA; branch/tag names are not accepted")
        url = source.url
        if url.startswith("-") or "\n" in url or "\r" in url or "\0" in url:
            raise ConfigurationError("Invalid Git source locator")
        if "://" in url:
            parsed = urlsplit(url)
            if parsed.scheme not in {"https", "ssh", "file"}:
                raise ConfigurationError("Git source supports https, ssh or local filesystem URLs")
            if parsed.query or parsed.fragment or parsed.password or (parsed.scheme == "https" and parsed.username):
                raise ConfigurationError("Do not embed credentials/query/fragment in Git URLs; use SSH or a credential helper")
        elif ":" in url and not re.fullmatch(r"(?:[\w.-]+@)?[\w.-]+:[^\s]+", url):
            raise ConfigurationError("Invalid SCP-style Git URL")


def selected(relative: str, source: SourceSpec) -> bool:
    path = Path(relative)
    if (any(part in IGNORED_PARTS or part.startswith(".env") or part in CREDENTIAL_FILES
            for part in path.parts) or path.suffix == ".pyc"
            or any(fnmatch.fnmatchcase(relative, pat) for pat in source.exclude)):
        return False
    developer_prefixes = ["/".join(path.parts[:index + 1]) + "/"
                          for index, part in enumerate(path.parts) if part in DEVELOPER_PARTS]
    return any(fnmatch.fnmatchcase(relative, pattern)
               and all(pattern.startswith(prefix) for prefix in developer_prefixes)
               for pattern in source.include)


def _git(cwd: Path, args: list[str], deadline: float, env: dict | None = None) -> bytes:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise UnavailableError("Agent source resolution timed out")
    try:
        result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=cwd,
                                env={**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})},
                                capture_output=True, timeout=remaining, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UnavailableError(f"Git source command failed: {type(exc).__name__}") from exc
    if result.returncode:
        # Credential helpers or remotes may put sensitive diagnostics in stderr.
        raise UnavailableError(f"Git {args[0]} failed (exit {result.returncode}); verify source access and pinned commit")
    return result.stdout


def _export_git(repo: Path, tree: str, dest: Path, source: SourceSpec, deadline: float) -> None:
    listing = _git(repo, ["ls-tree", "-rz", "--full-tree", tree], deadline)
    for record in listing.split(b"\0"):
        if not record:
            continue
        meta, raw_name = record.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        name = raw_name.decode("utf-8")
        if not selected(name, source):
            continue
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ConfigurationError(f"Unsupported Git entry (symlink/submodule): {name}")
        out = safe_path(dest, name)
        content = _git(repo, ["cat-file", "blob", oid], deadline)
        if content.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
            raise ConfigurationError(f"Git LFS pointer requires a pre-materialized local source: {name}")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(content)
        out.chmod(0o755 if mode == "100755" else 0o644)


def materialize_agent(agent: AgentSpec, target: Path) -> tuple[AgentSpec, dict]:
    """Never checks out, edits, commits or pushes the original source repository."""
    source = agent.source
    if source is None:
        raise ConfigurationError("Agent source is missing; migrate to manifest schema_version=2")
    validate_source(source)
    deadline = time.monotonic() + source.timeout_seconds
    bundle = target / "bundle"
    target.mkdir(parents=True, exist_ok=False)
    bundle.mkdir()
    info = {"kind": source.kind, "subdir": source.subdir,
            "include": source.include, "exclude": source.exclude}
    try:
        if source.kind == "local":
            root = safe_path(source.path, source.subdir)
            if not root.is_dir():
                raise ConfigurationError(f"Local Agent source does not exist: {root}")
            if target.resolve().is_relative_to(root.resolve()):
                raise ConfigurationError("Run output must not be inside the Agent source")
            info["path"] = str(source.path)
            # Record checkout metadata only when the chosen source itself is a Git root.
            if (source.path / ".git").exists():
                try:
                    info["observed_commit"] = _git(source.path, ["rev-parse", "HEAD"], deadline).decode().strip()
                    info["dirty"] = bool(_git(source.path, ["status", "--porcelain"], deadline))
                except UnavailableError:
                    info["observed_commit"] = None
            for path in sorted(root.rglob("*")):
                name = path.relative_to(root).as_posix()
                if not selected(name, source):
                    continue
                if time.monotonic() >= deadline:
                    raise UnavailableError("Local source snapshot timed out")
                safe_path(root, name)
                if path.is_file():
                    out = safe_path(bundle, name)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, out)
        else:
            url = source.url
            if "://" not in url and ":" not in url:
                url = str((agent.root / url).resolve())
            with tempfile.TemporaryDirectory(prefix="agent-opt-git-") as temporary:
                repo = Path(temporary)
                fmt = "sha256" if len(source.revision) == 64 else "sha1"
                _git(repo, ["init", "--quiet", f"--object-format={fmt}"], deadline)
                _git(repo, ["fetch", "--quiet", "--no-tags", "--depth=1", "--", url, source.revision], deadline)
                resolved = _git(repo, ["rev-parse", "FETCH_HEAD^{commit}"], deadline).decode().strip()
                if resolved.lower() != source.revision.lower():
                    raise ConfigurationError("Fetched commit differs from requested revision")
                tree = resolved if source.subdir == "." else f"{resolved}:{source.subdir}"
                if _git(repo, ["cat-file", "-t", tree], deadline).strip() not in {b"commit", b"tree"}:
                    raise ConfigurationError("source.subdir is not a Git tree")
                _export_git(repo, tree, bundle, source, deadline)
                info.update(url=source.url, requested_commit=source.revision, resolved_commit=resolved)
        if not safe_path(bundle, agent.prompt_file).is_file():
            raise ConfigurationError(f"Source snapshot is missing prompt_file: {agent.prompt_file}")
        info["content_hash"] = digest(bundle)
        write_json(target / "source-lock.json", {"schema_version": 1, "agent_id": agent.id, **info})
        return replace(agent, bundle=bundle), info
    except Exception:
        shutil.rmtree(target)
        raise
