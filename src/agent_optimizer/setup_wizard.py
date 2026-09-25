"""Explicit dataset selection and copyable user experiment generation."""
from __future__ import annotations

import json
import math
import os
import shlex
import shutil
import sys
import contextlib
import fnmatch
import itertools
from pathlib import Path

from agent_optimizer.config import identifier, load_experiment, load_tasks, positive
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.datasets import CustomDataset
from agent_optimizer.harnesses.command import CommandHarness, FixtureHarness
from agent_optimizer.harnesses.opencode import OpenCodeHarness
from agent_optimizer.registry import PROJECT_COMPONENTS, PROJECT_DEPENDENCIES, Registry
from agent_optimizer.results import write_json
from agent_optimizer.terminal_report import PreparationStatus
from agent_optimizer.terminal_style import style
from agent_optimizer.workspace import safe_path


def component_inventory(project_root: Path) -> tuple[Registry, dict, dict]:
    registry = Registry()
    registry.load_project(project_root)
    return registry, PROJECT_COMPONENTS, PROJECT_DEPENDENCIES


def requires_command(adapter: type) -> bool:
    return (isinstance(adapter, type) and issubclass(adapter, CommandHarness)
            and adapter.argv is CommandHarness.argv)


def supports_generated_profile(adapter: type) -> bool:
    return requires_command(adapter) or adapter in {FixtureHarness, OpenCodeHarness}


def prepare_selection(project_root: Path, selection: str, *, evaluator: str | None = None,
                      offline: bool = False) -> tuple[dict, dict, dict]:
    registry, _, _ = component_inventory(project_root)
    plugins, dependencies = {}, {}
    if selection in registry.factories["datasets"]:
        with PreparationStatus(selection), contextlib.redirect_stdout(sys.stderr):
            result = registry.resolve("datasets", selection)().prepare(
                project_root / "external" / "datasets" / selection, offline=offline)
        evaluator_id = result["evaluator"]
        if not isinstance(evaluator_id, str) or ":" in evaluator_id:
            raise ConfigurationError("Registered dataset provider must return a registered evaluator ID")
        registry.resolve("evaluators", evaluator_id)
        result = {**result, "evaluator": evaluator_id, "dataset_provider": selection}
    elif Path(selection).is_file():
        if not evaluator:
            raise ConfigurationError("Custom dataset requires an explicit evaluator")
        if ":" in evaluator:
            plugins.setdefault("evaluators", {})["user_evaluator"] = evaluator
            result_name = "user_evaluator"
        else:
            registry.resolve("evaluators", evaluator)
            result_name = evaluator
        with PreparationStatus(Path(selection).name):
            result = CustomDataset(Path(selection), evaluator=result_name).prepare(
                project_root / "external" / "datasets" / "custom", offline=offline)
    else:
        raise ConfigurationError(f"Unknown dataset {selection!r}; use datasets list or a local tasks.json")
    return result, plugins, dependencies


def _literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_literal(item) for item in value) + "]"
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return "{ " + ", ".join(f"{_literal(key)} = {_literal(item)}"
                                for key, item in value.items()) + " }"
    raise ConfigurationError("Experiment options must contain only TOML-compatible values")


def _section(name, mapping):
    return [f"[{name}]", *(f"{json.dumps(key)} = {_literal(value)}" for key, value in mapping.items()), ""]


def choose_editable_file(agent: Path | str, editable: list[str], *, suffix: str = "",
                         explicit: str | None = None) -> str:
    if explicit:
        safe_path(Path("/schema-only"), explicit)
        if suffix and not explicit.endswith(suffix):
            raise ConfigurationError(f"Editable target must end with {suffix}")
        if not any(fnmatch.fnmatchcase(explicit, pattern) for pattern in editable):
            raise ConfigurationError("Target file must be inside the declared editable paths")
        return explicit
    if not isinstance(agent, Path) or not agent.is_dir():
        raise ConfigurationError("Pinned Git Agent requires --target-file or --scaffold-file")
    matches = set()
    for pattern in editable:
        safe_path(agent, pattern)
        candidates = (itertools.chain(agent.glob(pattern), agent.glob(pattern + "/*"))
                      if pattern.endswith("/**") else agent.glob(pattern))
        for path in candidates:
            if path.is_file() and not path.is_symlink() and (not suffix or path.suffix == suffix):
                relative = path.relative_to(agent).as_posix()
                safe_path(agent, relative)
                matches.add(relative)
    if len(matches) != 1:
        raise ConfigurationError("Editable target is ambiguous or missing; pass --target-file "
                                 "(or --scaffold-file for a runtime harness)")
    return matches.pop()


def _bounded_tasks(document: dict, max_tasks: int) -> dict:
    tasks = document["tasks"]
    if len(tasks) <= max_tasks:
        return document
    names = [split for split in ("train", "validation", "test") if any(t["split"] == split for t in tasks)]
    if max_tasks < len(names):
        raise ConfigurationError(f"max_tasks requires at least {len(names)} split representatives")
    grouped = {name: sorted((t for t in tasks if t["split"] == name), key=lambda t: t["id"])
               for name in names}
    chosen = []
    while len(chosen) < max_tasks and any(grouped.values()):
        for name in names:
            if len(chosen) >= max_tasks:
                break
            if grouped[name]:
                chosen.append(grouped[name].pop(0))
    return {**document, "tasks": chosen, "sampled_from": len(tasks)}


def write_experiment(config_root: Path, *, agent: Path | str, harness: dict, dataset: dict,
                     stages: list[dict], plugins: dict, dependencies: dict, name: str,
                     editable: list[str], prompt_file: str = "prompts/system.md",
                     max_tasks: int = 9, project_root: Path | None = None,
                     max_trials: int | None = None, wall_time: float = 3600,
                     trial_timeout: float = 120, objective_source: str = "passed",
                     objective_direction: str = "maximize") -> Path:
    """Create only run-owned configuration; never modify the original Agent."""
    identifier(name)
    if config_root.exists():
        raise ConfigurationError(f"Generated configuration already exists: {config_root}")
    if not editable or not all(isinstance(value, str) and value for value in editable):
        raise ConfigurationError("At least one editable Agent file is required")
    if harness.get("adapter", "command") == "command" and not harness.get("command"):
        raise ConfigurationError("Agent execution argv is required")
    if type(max_tasks) is not int or max_tasks < 1:
        raise ConfigurationError("max_tasks must be positive")
    identifier(objective_source)
    if objective_direction not in {"maximize", "minimize"}:
        raise ConfigurationError("Objective direction must be maximize or minimize")
    project_root = project_root or config_root.parents[2]
    benchmark = Path(dataset["benchmark"])
    if not benchmark.is_absolute():
        benchmark = project_root / benchmark
    document = _bounded_tasks(json.loads(benchmark.read_text(encoding="utf-8")), max_tasks)
    if "provenance" in dataset:
        document["dataset_provenance"] = dataset["provenance"]
    if "dataset_provider" in dataset:
        document["dataset_provider"] = dataset["dataset_provider"]
    if not any(task["split"] == "validation" for task in document["tasks"]):
        raise ConfigurationError("Selected dataset needs validation tasks")
    source_kind = "git" if "revision" in harness else "local"
    if source_kind == "local" and (not isinstance(agent, Path) or not (agent / prompt_file).is_file()):
        raise ConfigurationError(f"Agent prompt file missing: {prompt_file}")
    root_prefix = config_root.relative_to(project_root).as_posix()
    groups = len([t for t in document["tasks"] if t["split"] == "validation"])
    tests = len([t for t in document["tasks"] if t["split"] == "test"])
    reserved = groups + sum(s["max_trials"] for s in stages) + 2 * tests
    if max_trials is not None and (type(max_trials) is not int or max_trials < reserved):
        raise ConfigurationError(f"max_trials must reserve at least {reserved} baseline/stage/test trials")
    positive(wall_time, "max_wall_time_seconds")
    positive(trial_timeout, "trial_timeout_seconds")
    config_root.mkdir(parents=True)
    try:
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
                         f"adapter = {_literal(harness.get('adapter', 'command'))}"]
        if "command" in harness:
            harness_lines.append(f"command = {_literal(harness['command'])}")
        harness_lines += ["allow_local = true", "", "[runtime]", 'kind = "local"']
        (config_root / "harness.toml").write_text("\n".join(harness_lines) + "\n", encoding="utf-8")
        lines = ["schema_version = 1", f"name = {_literal(name)}",
                 f"project_root = {_literal(os.path.relpath(project_root, config_root))}",
                 f"agents = {_literal([root_prefix + '/agent.toml'])}",
                 f"harnesses = {_literal([root_prefix + '/harness.toml'])}",
                 f"benchmark = {_literal(root_prefix + '/tasks.json')}",
                 f"evaluator = {_literal(dataset['evaluator'])}",
                 f"final_test = {_literal(bool(tests))}",
                 f"final_stages = {_literal([s['id'] for s in stages] or ['baseline'])}",
                 'output_dir = "runs"', ""]
        lines += _section("budget", {"max_trials": max_trials if max_trials is not None else max(80, reserved),
                                     "max_wall_time_seconds": wall_time,
                                     "trial_timeout_seconds": trial_timeout})
        lines += ["[objective]", 'mode = "lexicographic"', "keep = 1", "",
                  "[[objective.metrics]]",
                  f"name = {_literal('solve_rate' if objective_source == 'passed' else objective_source)}",
                  f"source = {_literal(objective_source)}",
                  f"direction = {_literal(objective_direction)}", 'aggregate = "mean"', ""]
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
        if "evaluator_config" in dataset:
            lines += _section("evaluator_config", dataset["evaluator_config"])
        target = config_root / "experiment.toml"
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        load_experiment(target)
        return target
    except Exception:
        shutil.rmtree(config_root)
        raise


def wizard_arguments(project_root: Path) -> list[str]:
    """Interactive choices, rendered from the live catalog rather than a fixed menu."""
    registry, _, _ = component_inventory(project_root)

    def ask(label):
        print("  " + style(f"{label}:", "warning", stream=sys.stderr) + " ",
              end="", file=sys.stderr, flush=True)
        return input().strip()

    print("\n╭─────────────────────────────────────────────────────────╮", file=sys.stderr)
    print(style("│  Agent Optimizer   ·   new optimization experiment     │", "heading",
                stream=sys.stderr), file=sys.stderr)
    print("╰─────────────────────────────────────────────────────────╯", file=sys.stderr)
    name = ask("Experiment name")
    agent = ask("Agent source directory or pinned Git URL")
    revision = ask("Git commit (leave blank for local source)") if "://" in agent else ""
    editable = [item.strip() for item in ask("Editable files (comma separated)").split(",") if item.strip()]
    choices = sorted(registry.factories["datasets"])
    print("\n  " + style("Choose a dataset; there is no automatic recommendation:", "heading",
                           stream=sys.stderr), file=sys.stderr)
    for index, key in enumerate(choices, 1):
        info = registry.factories["datasets"][key]().describe()
        print(f"    {style(f'{index}.', 'heading', stream=sys.stderr)} "
              f"{key} · {info.get('task_form', 'custom')}", file=sys.stderr)
    dataset_choice = ask("Dataset numbers or local tasks.json paths (comma separated)")
    selected_datasets = []
    for item in dataset_choice.split(","):
        item = item.strip()
        selected_datasets.append(choices[int(item) - 1] if item.isdigit()
                                 and 1 <= int(item) <= len(choices) else item)
    evaluator = (ask("Evaluator file.py:Symbol or registered name")
                 if any(dataset not in choices for dataset in selected_datasets) else "")
    metric = (ask("Evaluator score metric (Enter for passed)") or "passed") if evaluator else "passed"
    direction = (ask("Score direction maximize/minimize (Enter for maximize)") or "maximize"
                 if evaluator else "maximize")
    if direction not in {"maximize", "minimize"}:
        raise ConfigurationError("Score direction must be maximize or minimize")
    optimizers = sorted(registry.factories["optimizers"])
    print("\n  " + style("Select optimizer algorithms:", "heading", stream=sys.stderr),
          file=sys.stderr)
    for index, key in enumerate(optimizers, 1):
        print(f"    {style(f'{index}.', 'heading', stream=sys.stderr)} {key}", file=sys.stderr)
    numbers = ask("Optimizer numbers (comma separated)")
    try:
        selected = [optimizers[int(index.strip()) - 1] for index in numbers.split(",")]
    except (ValueError, IndexError):
        raise ConfigurationError("Choose one or more listed optimizer numbers") from None
    if not selected or not all(item in optimizers for item in selected):
        raise ConfigurationError("Choose one or more listed optimizers")
    harnesses = sorted(registry.factories["harnesses"])
    print("\n  " + style("Select an Agent harness:", "heading", stream=sys.stderr), file=sys.stderr)
    for index, key in enumerate(harnesses, 1):
        print(f"    {style(f'{index}.', 'heading', stream=sys.stderr)} {key}", file=sys.stderr)
    number = ask("Harness number")
    if not number.isdigit() or not 1 <= int(number) <= len(harnesses):
        raise ConfigurationError("Choose a listed harness number")
    harness = harnesses[int(number) - 1]
    adapter = registry.resolve("harnesses", harness)
    if not supports_generated_profile(adapter):
        raise ConfigurationError("전용 하네스 프로필이 필요합니다. 기존 experiment.toml을 사용하세요")
    command = (shlex.split(ask("Agent execution argv (e.g. python agent.py {task_dir})"))
               if requires_command(adapter) else None)
    if command is not None and not command:
        raise ConfigurationError("Agent 실행 명령을 입력하세요")
    scaffold = (ask("Active runtime harness .py file (Enter to auto-detect one match)")
                if any(item in {"meta_harness", "ecdysis"} for item in selected) else "")
    target_file = (ask("Editable text target (Enter to auto-detect one match)")
                   if "gepa" in selected else "")
    print(f"\n  Agent: {agent}\n  Datasets: {', '.join(selected_datasets)}\n  Harness: {harness}"
          f"\n  Optimizers: {', '.join(selected)}",
          file=sys.stderr)
    if ask("Prepare dataset and run? [y/N]").lower() not in {"y", "yes"}:
        raise ConfigurationError("Experiment cancelled without preparing data")
    arguments = ["init", "--project-root", str(project_root), "--name", name,
                 "--agent", agent, *[part for dataset in selected_datasets
                                     for part in ("--dataset", dataset)],
                 "--editable", editable[0], "--harness", harness, "--yes"]
    if command is not None:
        arguments += ["--command-json", json.dumps(command)]
    for item in editable[1:]:
        arguments += ["--editable", item]
    for optimizer in selected:
        arguments += ["--optimizer", optimizer]
    if evaluator:
        arguments += ["--evaluator", evaluator, "--metric", metric, "--direction", direction]
    if scaffold:
        arguments += ["--scaffold-file", scaffold]
    if target_file:
        arguments += ["--target-file", target_file]
    if revision:
        arguments += ["--revision", revision]
    return arguments
