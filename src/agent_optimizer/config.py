from __future__ import annotations

import json
import math
import re
import tomllib
from pathlib import Path

from agent_optimizer.contracts import AgentSpec, ConfigurationError, SourceSpec, Task
from agent_optimizer.sources import validate_source
from agent_optimizer.workspace import safe_path


def read_toml(path: Path) -> dict:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", value):
        raise ConfigurationError(f"Invalid identifier: {value!r}")
    return value


def only_keys(data: dict, keys: set[str], label: str) -> None:
    unknown = set(data) - keys
    if unknown:
        raise ConfigurationError(f"Unknown {label} keys: {sorted(unknown)}")


def positive(value, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ConfigurationError(f"{label} must be a finite positive number")


def validate_runtime(runtime: dict) -> None:
    only_keys(runtime, {"kind", "image", "network", "cpus", "memory", "env_passthrough"}, "runtime")
    if runtime.get("kind", "local") not in {"local", "docker"}:
        raise ConfigurationError("runtime.kind must be local or docker")
    if runtime.get("kind") == "docker" and not runtime.get("image"):
        raise ConfigurationError("Docker runtime requires image")
    if runtime.get("network", "none") not in {"none", "bridge"}:
        raise ConfigurationError("Starter runtime supports none/bridge networks only")
    positive(runtime.get("cpus", 2), "runtime.cpus")
    for key in runtime.get("env_passthrough", []):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", key):
            raise ConfigurationError("Invalid environment variable name")


def load_agent(path: Path) -> AgentSpec:
    data = read_toml(path)
    only_keys(data, {"schema_version", "id", "description", "source", "supported_harnesses",
                     "editable", "prompt_file", "build"}, "agent")
    if data.get("schema_version") != 2:
        raise ConfigurationError("Agent manifest requires schema_version=2; see docs/adding-components.md")
    root = path.parent.resolve()
    raw_source = data["source"]
    only_keys(raw_source, {"kind", "path", "url", "revision", "subdir", "include", "exclude", "timeout_seconds"}, "source")
    positive(raw_source.get("timeout_seconds", 60), "source.timeout_seconds")
    for key in ["include", "exclude"]:
        if key in raw_source and (not isinstance(raw_source[key], list) or not all(isinstance(p, str) for p in raw_source[key])):
            raise ConfigurationError(f"source.{key} must be a string list")
    source = SourceSpec(**{**raw_source,
                          **({"path": (root / raw_source["path"]).resolve()} if "path" in raw_source else {}),
                          **{k: tuple(raw_source[k]) for k in ["include", "exclude"] if k in raw_source}})
    validate_source(source)
    prompt_file = data.get("prompt_file", "prompts/system.md")
    safe_path(Path("/schema-validation"), prompt_file)
    editable = data.get("editable", [])
    if not editable or not all(isinstance(p, str) for p in editable):
        raise ConfigurationError("Agent editable must be a nonempty string list")
    build = data.get("build", [])
    if not isinstance(build, list) or not all(isinstance(p, str) for p in build):
        raise ConfigurationError("Agent build must be an argv string list")
    return AgentSpec(identifier(data["id"]), root, None, data.get("description", ""),
                     tuple(data["supported_harnesses"]), tuple(editable), prompt_file, tuple(build), source)


def load_tasks(path: Path) -> tuple[list[Task], dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ConfigurationError("Unsupported benchmark schema_version")
    tasks, ids, families = [], set(), {}
    for item in data["tasks"]:
        task = Task(**item)
        identifier(task.id)
        if task.id in ids:
            raise ConfigurationError(f"Duplicate task id: {task.id}")
        ids.add(task.id)
        if task.split not in {"train", "validation", "test"}:
            raise ConfigurationError(f"Invalid split: {task.split}")
        # Same family may appear multiple times within one split, never across splits.
        if task.family and families.setdefault(task.family, task.split) != task.split:
            raise ConfigurationError(f"Task family leaks across splits: {task.family}")
        if not task.files or not task.prompt or not isinstance(task.evaluation, dict):
            raise ConfigurationError(f"Incomplete task: {task.id}")
        for rel in task.files:
            safe_path(Path("/validation-only"), rel)
        tasks.append(task)
    if not tasks or not any(t.split == "validation" for t in tasks):
        raise ConfigurationError("Benchmark requires at least one validation task")
    return tasks, {k: v for k, v in data.items() if k != "tasks"}


def validate_objective(objective: dict) -> None:
    only_keys(objective, {"mode", "metrics", "keep"}, "objective")
    if objective.get("mode", "lexicographic") != "lexicographic":
        raise ConfigurationError("Advanced objective modes are deferred; use lexicographic")
    if not objective.get("metrics"):
        raise ConfigurationError("At least one objective metric is required")
    names = set()
    for metric in objective["metrics"]:
        only_keys(metric, {"name", "source", "direction", "aggregate"}, "metric")
        name = identifier(metric["name"])
        if name in names:
            raise ConfigurationError(f"Duplicate metric name: {name}")
        names.add(name)
        if metric.get("direction") not in {"maximize", "minimize"}:
            raise ConfigurationError("Metric direction must be maximize/minimize")
        if metric.get("aggregate", "mean") not in {"mean", "sum"}:
            raise ConfigurationError("Advanced metric aggregates are deferred; use mean or sum")
    if type(objective.get("keep", 1)) is not int or objective.get("keep", 1) != 1:
        raise ConfigurationError("Multiple-winner selection is deferred; objective.keep must be 1")


def validate_stages(data: dict) -> None:
    known = {"baseline"}
    for stage in data.get("stages", []):
        only_keys(stage, {"id", "optimizer", "inputs", "config", "when"}, "stage")
        sid = identifier(stage["id"])
        if sid in known:
            raise ConfigurationError(f"Duplicate/reserved stage id: {sid}")
        if stage.get("inputs", ["baseline"]) != ["baseline"]:
            raise ConfigurationError("Stage chaining is deferred; inputs must be [\"baseline\"]")
        if "when" in stage:
            raise ConfigurationError("Validation gates are deferred; remove stage.when")
        known.add(sid)
    if not set(data.get("final_stages", ["baseline"])) <= known:
        raise ConfigurationError("Unknown final stage")


def load_experiment(path: Path) -> dict:
    data = read_toml(path)
    only_keys(data, {"schema_version", "name", "project_root", "agents", "harnesses", "benchmark",
                    "evaluator", "evaluation_runtime", "objective", "budget", "stages",
                    "repetitions", "seed", "final_test", "final_stages", "output_dir", "plugins",
                    "plugin_dependencies"}, "experiment")
    if data.get("schema_version") != 1:
        raise ConfigurationError("Unsupported experiment schema_version")
    identifier(data["name"])
    root = (path.parent / data.get("project_root", "../..")).resolve()
    data["_root"] = root
    data["_source"] = path.resolve()
    agents = [load_agent(safe_path(root, p)) for p in data["agents"]]
    if not agents or len({a.id for a in agents}) != len(agents):
        raise ConfigurationError("Agent IDs must be present and unique")
    data["_agents"] = agents
    profiles = []
    for filename in data["harnesses"]:
        profile = read_toml(safe_path(root, filename))
        only_keys(profile, {"id", "adapter", "command", "model_env", "agent", "runtime",
                           "allow_local", "notes"}, "harness profile")
        identifier(profile["id"])
        validate_runtime(profile.get("runtime", {}))
        if "command" in profile and (not isinstance(profile["command"], list) or
                                    not all(isinstance(v, str) for v in profile["command"])):
            raise ConfigurationError("command must be an argv string list")
        kind = profile.get("runtime", {}).get("kind", "local")
        if kind not in {"local", "docker"}:
            raise ConfigurationError("runtime.kind must be local or docker")
        if kind == "docker" and not profile["runtime"].get("image"):
            raise ConfigurationError("Docker runtime requires image")
        if kind == "local" and profile["adapter"] != "fixture" and not profile.get("allow_local"):
            raise ConfigurationError("Real local execution requires allow_local=true; Docker is recommended")
        profiles.append(profile)
    if not profiles or len({h["id"] for h in profiles}) != len(profiles):
        raise ConfigurationError("Harness profile IDs must be present and unique")
    for agent in agents:
        for profile in profiles:
            if profile["adapter"] not in agent.supported_harnesses:
                raise ConfigurationError(f"{agent.id} does not support {profile['adapter']}")
    data["_profiles"] = profiles
    validate_runtime(data.get("evaluation_runtime", {}))
    tasks, metadata = load_tasks(safe_path(root, data["benchmark"]))
    data["_tasks"], data["_benchmark_metadata"] = tasks, metadata
    if data.get("final_test", False) and not any(t.split == "test" for t in tasks):
        raise ConfigurationError("final_test requires test tasks")
    for key, default in [("repetitions", 1), ("seed", 0)]:
        if type(data.get(key, default)) is not int or data.get(key, default) < (1 if key == "repetitions" else 0):
            raise ConfigurationError(f"Invalid {key}")
    validate_objective(data["objective"])
    budget = data.setdefault("budget", {})
    only_keys(budget, {"max_trials", "max_wall_time_seconds", "trial_timeout_seconds"}, "budget")
    for key, default in [("max_trials", 100), ("max_wall_time_seconds", 3600), ("trial_timeout_seconds", 120)]:
        positive(budget.get(key, default), key)
    if type(budget.get("max_trials", 100)) is not int:
        raise ConfigurationError("max_trials must be an integer")
    validate_stages(data)
    return data
