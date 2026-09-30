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
        only_keys(stage, {"id", "optimizer", "inputs", "config", "when", "max_trials"}, "stage")
        sid = identifier(stage["id"])
        if sid in known:
            raise ConfigurationError(f"Duplicate/reserved stage id: {sid}")
        if stage.get("inputs", ["baseline"]) != ["baseline"]:
            raise ConfigurationError("Stage chaining is deferred; inputs must be [\"baseline\"]")
        if "when" in stage:
            raise ConfigurationError("Validation gates are deferred; remove stage.when")
        if "max_trials" in stage and (type(stage["max_trials"]) is not int or stage["max_trials"] < 1):
            raise ConfigurationError("stage.max_trials must be a positive integer")
        known.add(sid)
    if not set(data.get("final_stages", ["baseline"])) <= known:
        raise ConfigurationError("Unknown final stage")


def selected_pairs(spec: dict) -> list[tuple[AgentSpec, dict]]:
    agents, profiles = spec["_agents"], spec["_profiles"]
    agent_ids = [identifier(agent.id) for agent in agents]
    profile_ids = [identifier(profile.get("id")) for profile in profiles]
    if not agents or len(set(agent_ids)) != len(agents):
        raise ConfigurationError("Agent IDs must be present and unique")
    if not profiles or len(set(profile_ids)) != len(profiles):
        raise ConfigurationError("Harness profile IDs must be present and unique")
    if "pairs" not in spec:
        pairs = [(agent, profile) for agent in agents for profile in profiles]
    else:
        raw = spec["pairs"]
        if not isinstance(raw, list) or not raw:
            raise ConfigurationError("pairs must be a nonempty list")
        by_agent = {agent.id: agent for agent in agents}
        by_profile = {profile["id"]: profile for profile in profiles}
        pairs = []
        seen = set()
        for item in raw:
            if not isinstance(item, dict):
                raise ConfigurationError("Each pair must declare agent and harness IDs")
            only_keys(item, {"agent", "harness"}, "pair")
            key = (item.get("agent"), item.get("harness"))
            if any(type(value) is not str or not value for value in key):
                raise ConfigurationError("pair.agent and pair.harness require IDs")
            if key in seen or key[0] not in by_agent or key[1] not in by_profile:
                raise ConfigurationError("Duplicate or unknown Agent–Harness pair")
            seen.add(key)
            pairs.append((by_agent[key[0]], by_profile[key[1]]))
        if ({agent.id for agent, _ in pairs} != set(by_agent)
                or {profile["id"] for _, profile in pairs} != set(by_profile)):
            raise ConfigurationError("Remove unselected agents and harnesses")
    for agent, profile in pairs:
        if profile["adapter"] not in agent.supported_harnesses:
            raise ConfigurationError(f"{agent.id} does not support {profile['adapter']}")
    return pairs


def load_experiment(path: Path) -> dict:
    data = read_toml(path)
    if "integration" in data:
        from agent_optimizer.integrations import resolve_pointer
        return load_experiment(resolve_pointer(path))
    only_keys(data, {"schema_version", "name", "project_root", "config_root", "agents", "harnesses", "pairs", "benchmark",
                    "evaluator", "evaluation_runtime", "objective", "budget", "stages",
                    "repetitions", "seed", "final_test", "final_stages", "output_dir", "plugins",
                    "plugin_dependencies", "evaluator_config", "candidate_seed_files", "candidate_seed_root",
                    "preset_selection"}, "experiment")
    if data.get("schema_version") != 1:
        raise ConfigurationError("Unsupported experiment schema_version")
    identifier(data["name"])
    root = (path.parent / data.get("project_root", "../..")).resolve()
    config_root = root
    if 'config_root' in data:
        value = data['config_root']
        if not isinstance(value, str) or not value or '\0' in value:
            raise ConfigurationError('config_root는 유효한 설정 디렉터리 경로여야 합니다')
        declared = Path(value).expanduser()
        config_root = declared if declared.is_absolute() else path.parent / declared
        safe_path(config_root, '.')
        config_root = config_root.resolve()
    data["_root"] = root
    data["_config_root"] = config_root
    if data.get('candidate_seed_root', 'project') not in ('project', 'config'):
        raise ConfigurationError('candidate_seed_root는 project 또는 config여야 합니다')
    data['_seed_root'] = config_root if data.get('candidate_seed_root') == 'config' else root
    data["_source"] = path.resolve()
    agents = [load_agent(safe_path(config_root, p)) for p in data["agents"]]
    if not agents or len({a.id for a in agents}) != len(agents):
        raise ConfigurationError("Agent IDs must be present and unique")
    data["_agents"] = agents
    profiles = []
    for filename in data["harnesses"]:
        profile = read_toml(safe_path(config_root, filename))
        only_keys(profile, {"id", "adapter", "command", "model_env", "agent", "runtime",
                            "allow_local", "notes", "required_cli_version", "native", "compatibility"}, "harness profile")
        for key in ('native', 'compatibility'):
            if key in profile and not isinstance(profile[key], dict):
                raise ConfigurationError(f'{key}는 객체여야 합니다')
        if 'compatibility' in profile:
            compatibility = profile['compatibility']
            only_keys(compatibility, {'agent_ids', 'dataset_ids', 'reviewed_cids', 'execution_mode', 'model_fields', 'roles', 'live_verification'}, 'compatibility')
            for key in ('agent_ids', 'dataset_ids', 'reviewed_cids', 'model_fields', 'roles'):
                if key in compatibility and (not isinstance(compatibility[key], list) or not all(isinstance(v, str) and v for v in compatibility[key])):
                    raise ConfigurationError(f'compatibility.{key}에는 문자열 목록이 필요합니다')
            if compatibility.get('execution_mode') not in (None, 'native', 'coding'):
                raise ConfigurationError('compatibility.execution_mode 오류')
        required = profile.get("required_cli_version")
        if required is not None and (not isinstance(required, str) or not required.strip()):
            raise ConfigurationError("required_cli_version must be a nonempty string")
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
    data["_profiles"] = profiles
    selected_pairs(data)
    validate_runtime(data.get("evaluation_runtime", {}))
    if not isinstance(data.get("evaluator_config", {}), dict):
        raise ConfigurationError("evaluator_config must be a mapping")
    tasks, metadata = load_tasks(safe_path(config_root, data["benchmark"]))
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
