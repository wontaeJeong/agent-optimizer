"""Create a small research experiment from an explicitly selected CVDP provider."""
from __future__ import annotations

import argparse
import itertools
import json
import re
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.results import write_json
from agent_optimizer.setup_wizard import prepare_selection, write_experiment


ROOT = Path(__file__).resolve().parents[2]
NAME = "model-rtl-research"


def _public_rtl(task: dict) -> bool:
    targets = task.get("evaluation", {}).get("targets")
    if not isinstance(targets, list) or len(targets) != 1 or not isinstance(targets[0], str):
        return False
    target = targets[0]
    return (bool(re.fullmatch(r"rtl/[A-Za-z0-9_./-]+\.(?:v|sv)", target))
            and all(part not in {"", ".", ".."} for part in target.split("/"))
            and isinstance(task.get("family"), str) and bool(task["family"])
            and target in task.get("files", {}))


def _subset(document: dict) -> dict:
    eligible = sorted((task for task in document["tasks"] if _public_rtl(task)),
                      key=lambda task: task["id"])
    trains = [task for task in eligible if task["split"] == "train"]
    validations = [task for task in eligible if task["split"] == "validation"]
    for first, second in itertools.combinations(trains, 2):
        if first["family"] == second["family"]:
            continue
        validation = next((task for task in validations
                           if task["family"] not in {first["family"], second["family"]}), None)
        if validation is not None:
            return {**document, "tasks": [first, second, validation]}
    if len({task["family"] for task in trains}) < 2:
        raise ConfigurationError("CVDP needs two distinct public RTL train families")
    raise ConfigurationError("CVDP needs a public RTL validation family distinct from train")


def prepare(project_root: Path, *, dataset: str, offline: bool = False) -> Path:
    if dataset != "cvdp":
        raise ConfigurationError("Select the cvdp dataset explicitly")
    project_root = project_root.resolve()
    config_root = project_root / "runs/configs" / NAME
    if config_root.exists():
        raise ConfigurationError(f"Generated configuration already exists: {config_root}")

    prepared, plugins, dependencies = prepare_selection(project_root, "cvdp", offline=offline)
    if prepared["evaluator"] != "cvdp":
        raise ConfigurationError("CVDP provider must return the cvdp evaluator")
    benchmark = Path(prepared["benchmark"])
    if not benchmark.is_absolute():
        benchmark = project_root / benchmark
    selected = _subset(json.loads(benchmark.read_text(encoding="utf-8")))
    subset_path = project_root / "external/datasets/cvdp-research/subset.json"
    write_json(subset_path, selected)

    stages = [
        {"id": "gepa", "optimizer": "gepa", "max_trials": 5,
         "config": {"file": "prompts/system.md", "iterations": 1, "batch_size": 2,
                    "request_timeout_seconds": 60}},
        {"id": "meta", "optimizer": "meta_harness", "max_trials": 4,
         "config": {"file": "src/agent.py", "iterations": 1, "required_symbol": "main",
                    "request_timeout_seconds": 60}},
        {"id": "ecdysis", "optimizer": "ecdysis", "max_trials": 4,
         "config": {"file": "src/agent.py", "rounds": 1, "refinement_passes": 2,
                    "request_timeout_seconds": 60}},
    ]
    return write_experiment(
        config_root, project_root=project_root, name=NAME,
        agent=project_root / "examples/model-rtl-agent/agent",
        harness={"id": "model-rtl-command", "adapter": "model_rtl_command",
                 "command": ["{python}", "{agent_dir}/src/agent.py", "{task_dir}"]},
        dataset={**prepared, "benchmark": str(subset_path)}, stages=stages,
        plugins={**plugins, "harnesses": {**plugins.get("harnesses", {}),
                                          "model_rtl_command":
                                          "examples/model-rtl-agent/adapter.py:ModelRTLCommand"}},
        dependencies=dependencies, editable=["prompts/system.md", "src/agent.py"],
        max_tasks=3, max_trials=16, wall_time=3600, trial_timeout=180,
        objective_source="passed", objective_direction="maximize",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="선택한 CVDP 공개 과제로 연구 실험 설정 생성")
    parser.add_argument("--dataset", required=True, choices=["cvdp"])
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        output = prepare(args.project_root, dataset=args.dataset, offline=args.offline)
    except ConfigurationError as exc:
        parser.error(str(exc))
    print(output)


if __name__ == "__main__":
    main()
