"""Explicit dataset selection and copyable user experiment generation."""
from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

from agent_optimizer.catalog import load_extensions
from agent_optimizer.config import identifier, load_experiment, load_tasks
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.datasets import CustomDataset
from agent_optimizer.registry import Registry
from agent_optimizer.results import write_json


def component_inventory(project_root: Path, extensions: Path | None = None):
    plugins, dependencies = {}, {}
    manifests = [project_root / "examples/benchmarks/extensions.toml"]
    if extensions is not None:
        manifests.append(extensions if extensions.is_absolute() else project_root / extensions)
    for manifest in manifests:
        if not manifest.is_file():
            if extensions is not None or manifest != manifests[0]:
                raise ConfigurationError(f"Extension manifest missing: {manifest}")
            continue
        registration = load_extensions(manifest, project_root)
        for kind, values in registration.get("plugins", {}).items():
            target = plugins.setdefault(kind, {})
            if set(target).intersection(values):
                raise ConfigurationError(f"Duplicate extension names for {kind}")
            target.update(values)
        for key, values in registration.get("plugin_dependencies", {}).items():
            if key in dependencies:
                raise ConfigurationError(f"Duplicate extension dependency: {key}")
            dependencies[key] = values
    registry = Registry()
    registry.load_plugins(project_root, plugins)
    return registry, plugins, dependencies


def prepare_selection(project_root: Path, selection: str, *, extensions: Path | None = None,
                      evaluator: str | None = None, offline: bool = False):
    registry, plugins, dependencies = component_inventory(project_root, extensions)
    if selection in registry.factories["datasets"]:
        result = registry.resolve("datasets", selection)().prepare(
            project_root / "external" / "datasets" / selection, offline=offline)
        found = next((name for name, reference in plugins.get("evaluators", {}).items()
                      if reference == result["evaluator"]), None)
        if found is None:
            raise ConfigurationError(f"Dataset {selection} requires a registered evaluator")
        result = {**result, "evaluator": found, "dataset_provider": selection}
    elif Path(selection).is_file():
        if not evaluator:
            raise ConfigurationError("Custom dataset requires an explicit evaluator")
        if ":" in evaluator:
            plugins.setdefault("evaluators", {})["user_evaluator"] = evaluator
            result_name = "user_evaluator"
        else:
            registry.resolve("evaluators", evaluator)
            result_name = evaluator
        result = CustomDataset(Path(selection), evaluator=result_name).prepare(
            project_root / "external" / "datasets" / "custom", offline=offline)
    else:
        raise ConfigurationError(f"Unknown dataset {selection!r}; use datasets list or a local tasks.json")
    return result, plugins, dependencies


def _literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _section(name, mapping):
    return [f"[{name}]", *(f"{json.dumps(key)} = {_literal(value)}" for key, value in mapping.items()), ""]


def _bounded_tasks(document: dict, max_tasks: int) -> dict:
    tasks = document["tasks"]
    if len(tasks) <= max_tasks:
        return document
    names = [split for split in ("train", "validation", "test") if any(t["split"] == split for t in tasks)]
    if max_tasks < len(names):
        raise ConfigurationError(f"max_tasks requires at least {len(names)} split representatives")
    grouped = {name: sorted((t for t in tasks if t["split"] == name), key=lambda t: t["id"])
               for name in names}
    chosen = [grouped[name].pop(0) for name in names]
    pool = sorted((task for items in grouped.values() for task in items), key=lambda t: t["id"])
    chosen.extend(pool[:max_tasks - len(chosen)])
    return {**document, "tasks": chosen, "sampled_from": len(tasks)}


def write_experiment(config_root: Path, *, agent: Path | str, harness: dict, dataset: dict,
                     stages: list[dict], plugins: dict, dependencies: dict, name: str,
                     editable: list[str], prompt_file: str = "prompts/system.md",
                     max_tasks: int = 9) -> Path:
    """Create only run-owned configuration; never modify the original Agent."""
    identifier(name)
    if config_root.exists():
        raise ConfigurationError(f"Generated configuration already exists: {config_root}")
    if not editable or not all(isinstance(value, str) and value for value in editable):
        raise ConfigurationError("At least one editable Agent file is required")
    if not harness.get("command"):
        raise ConfigurationError("Agent execution argv is required")
    if type(max_tasks) is not int or max_tasks < 1:
        raise ConfigurationError("max_tasks must be positive")
    project_root = config_root.parents[2]
    benchmark = Path(dataset["benchmark"])
    if not benchmark.is_absolute():
        benchmark = project_root / benchmark
    document = _bounded_tasks(json.loads(benchmark.read_text(encoding="utf-8")), max_tasks)
    if not any(task["split"] == "validation" for task in document["tasks"]):
        raise ConfigurationError("Selected dataset needs validation tasks")
    source_kind = "git" if "revision" in harness else "local"
    if source_kind == "local" and (not isinstance(agent, Path) or not (agent / prompt_file).is_file()):
        raise ConfigurationError(f"Agent prompt file missing: {prompt_file}")
    config_root.mkdir(parents=True)
    write_json(config_root / "tasks.json", document)
    agent_lines = ["schema_version = 2", f"id = {_literal(name)}",
                   f"supported_harnesses = {_literal([harness.get('adapter', 'command')])}",
                   f"editable = {_literal(editable)}", f"prompt_file = {_literal(prompt_file)}", "",
                   "[source]", f"kind = {_literal(source_kind)}"]
    if source_kind == "local":
        agent_lines.append(f"path = {_literal(str(agent.absolute()))}")
    else:
        agent_lines += [f"url = {_literal(str(agent))}",
                        f"revision = {_literal(harness['revision'])}"]
    (config_root / "agent.toml").write_text("\n".join(agent_lines) + "\n", encoding="utf-8")
    harness_lines = [f"id = {_literal(harness.get('id', 'user-command'))}",
                     f"adapter = {_literal(harness.get('adapter', 'command'))}",
                     f"command = {_literal(harness['command'])}", "allow_local = true", "",
                     "[runtime]", 'kind = "local"']
    (config_root / "harness.toml").write_text("\n".join(harness_lines) + "\n", encoding="utf-8")
    root_prefix = config_root.relative_to(project_root).as_posix()
    groups = len([t for t in document["tasks"] if t["split"] == "validation"])
    tests = len([t for t in document["tasks"] if t["split"] == "test"])
    reserved = groups + sum(s["max_trials"] for s in stages) + 2 * tests
    lines = ["schema_version = 1", f"name = {_literal(name)}",
             f"project_root = {_literal(os.path.relpath(project_root, config_root))}",
             f"agents = {_literal([root_prefix + '/agent.toml'])}",
             f"harnesses = {_literal([root_prefix + '/harness.toml'])}",
             f"benchmark = {_literal(root_prefix + '/tasks.json')}",
             f"evaluator = {_literal(dataset['evaluator'])}",
             f"final_test = {_literal(bool(tests))}",
             f"final_stages = {_literal([s['id'] for s in stages] or ['baseline'])}",
             'output_dir = "runs"', ""]
    lines += _section("budget", {"max_trials": max(80, reserved),
                                 "max_wall_time_seconds": 3600, "trial_timeout_seconds": 120})
    lines += ["[objective]", 'mode = "lexicographic"', "keep = 1", "",
              "[[objective.metrics]]", 'name = "solve_rate"', 'source = "passed"',
              'direction = "maximize"', 'aggregate = "mean"', ""]
    for stage in stages:
        lines += ["[[stages]]", f"id = {_literal(stage['id'])}",
                  f"optimizer = {_literal(stage['optimizer'])}",
                  f"max_trials = {stage['max_trials']}", "inputs = [\"baseline\"]", ""]
        lines += _section("stages.config", stage["config"])
    for kind, entries in plugins.items():
        if entries:
            lines += _section(f"plugins.{kind}", entries)
    if dependencies:
        lines += _section("plugin_dependencies", dependencies)
    if "evaluation_runtime" in dataset:
        lines += _section("evaluation_runtime", dataset["evaluation_runtime"])
    target = config_root / "experiment.toml"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    load_experiment(target)
    return target


def wizard_arguments(project_root: Path, extensions: Path | None = None) -> list[str]:
    """Interactive choices, rendered from the live catalog rather than a fixed menu."""
    registry, _, _ = component_inventory(project_root, extensions)

    def ask(label):
        print(f"  {label}: ", end="", file=sys.stderr, flush=True)
        return input().strip()

    print("\n╭─────────────────────────────────────────────────────────╮", file=sys.stderr)
    print("│  Agent Optimizer   ·   new optimization experiment     │", file=sys.stderr)
    print("╰─────────────────────────────────────────────────────────╯", file=sys.stderr)
    name = ask("Experiment name")
    agent = ask("Agent source directory or pinned Git URL")
    revision = ask("Git commit (leave blank for local source)") if "://" in agent else ""
    command = shlex.split(ask("Agent execution argv (e.g. python agent.py {task_dir})"))
    editable = [item.strip() for item in ask("Editable files (comma separated)").split(",") if item.strip()]
    choices = sorted(registry.factories["datasets"])
    print("\n  Choose a dataset; there is no automatic recommendation:", file=sys.stderr)
    for index, key in enumerate(choices, 1):
        info = registry.factories["datasets"][key]().describe()
        print(f"    {index}. {key} · {info.get('task_form', 'custom')}", file=sys.stderr)
    dataset_choice = ask("Dataset number or local tasks.json path")
    dataset = (choices[int(dataset_choice) - 1] if dataset_choice.isdigit()
               and 1 <= int(dataset_choice) <= len(choices) else dataset_choice)
    evaluator = ask("Evaluator file.py:Symbol or registered name") if dataset not in choices else ""
    optimizers = sorted(registry.factories["optimizers"])
    print("\n  Select optimizer algorithms:", file=sys.stderr)
    for index, key in enumerate(optimizers, 1):
        print(f"    {index}. {key}", file=sys.stderr)
    numbers = ask("Optimizer numbers (comma separated)")
    try:
        selected = [optimizers[int(index.strip()) - 1] for index in numbers.split(",")]
    except (ValueError, IndexError):
        raise ConfigurationError("Choose one or more listed optimizer numbers") from None
    if not selected or not all(item in optimizers for item in selected):
        raise ConfigurationError("Choose one or more listed optimizers")
    if any(item in {"meta_harness", "ecdysis"} for item in selected) and not any(
            value.endswith(".py") for value in editable):
        raise ConfigurationError("A harness optimizer requires an editable .py scaffold")
    print(f"\n  Agent: {agent}\n  Dataset: {dataset}\n  Optimizers: {', '.join(selected)}",
          file=sys.stderr)
    if ask("Prepare dataset and run? [y/N]").lower() not in {"y", "yes"}:
        raise ConfigurationError("Experiment cancelled without preparing data")
    arguments = ["init", "--project-root", str(project_root), "--name", name,
                 "--agent", agent, "--dataset", dataset, "--argv", *command,
                 "--editable", editable[0], "--yes"]
    for item in editable[1:]:
        arguments += ["--editable", item]
    for optimizer in selected:
        arguments += ["--optimizer", optimizer]
    if evaluator:
        arguments += ["--evaluator", evaluator]
    if revision:
        arguments += ["--revision", revision]
    if extensions is not None:
        arguments += ["--extensions", str(extensions)]
    return arguments
