"""Explicit inventories for trusted, team-owned file integrations."""
from __future__ import annotations

import tomllib
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.registry import plugin_files
from agent_optimizer.workspace import safe_path


def load_extensions(path: Path, project_root: Path) -> dict:
    root = project_root.absolute()
    try:
        relative = path.absolute().relative_to(root)
    except ValueError as exc:
        raise ConfigurationError("Extension manifest must be inside the project root") from exc
    manifest = safe_path(root, relative.as_posix())
    with manifest.open("rb") as stream:
        value = tomllib.load(stream)
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ConfigurationError("Extension schema_version must be 1")
    if set(value) - {"schema_version", "plugins", "plugin_dependencies"}:
        raise ConfigurationError("Unknown extension manifest keys")
    plugins = value.get("plugins", {})
    plugin_files(root, plugins, value.get("plugin_dependencies", {}))
    return value
