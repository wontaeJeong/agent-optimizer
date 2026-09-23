from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from agent_optimizer.config import load_agent, load_experiment
from agent_optimizer.contracts import ConfigurationError, UnavailableError, jsonable
from agent_optimizer.runner import preflight, run_experiment
from agent_optimizer.registry import Registry
from agent_optimizer.network import network_environment
from agent_optimizer.setup_wizard import (component_inventory, prepare_selection,
                                          wizard_arguments, write_experiment)
from agent_optimizer.terminal_report import ProgressDisplay


def show(value):
    print(json.dumps(jsonable(value), indent=2, ensure_ascii=False, allow_nan=False))


def doctor():
    result = {}
    for binary, flag in [("python3", "--version"), ("git", "--version"), ("docker", "--version"), ("opencode", "--version")]:
        path = shutil.which(binary)
        row = {"available": bool(path), "path": path}
        if path:
            try:
                proc = subprocess.run([path, flag], capture_output=True, text=True, timeout=10)
                row["version"] = (proc.stdout or proc.stderr).splitlines()[:2]
            except (OSError, subprocess.TimeoutExpired) as exc:
                row["error"] = str(exc)
        result[binary] = row
    return result


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "rerank":
        print("error: rerank is deferred; configure the objective for a new run. "
              "Stored reports and frozen selections remain available; see deferred/README.md", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description="Multi-agent optimization experiment workbench")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plugins", help="List implemented integrations")
    sub.add_parser("doctor", help="Inspect installed binaries; does not install anything")
    datasets = sub.add_parser("datasets", help="List and explicitly prepare benchmark datasets")
    dataset_actions = datasets.add_subparsers(dest="dataset_action", required=True)
    for action in ("list", "prepare"):
        item = dataset_actions.add_parser(action)
        item.add_argument("name", nargs="?" if action == "prepare" else "*", default=None)
        item.add_argument("--project-root", type=Path, default=Path.cwd())
        item.add_argument("--extensions", type=Path)
        if action == "prepare":
            item.add_argument("--evaluator")
            item.add_argument("--offline", action="store_true")
    init = sub.add_parser("init", help="Create a user experiment with an explicit dataset")
    init.add_argument("--project-root", type=Path, default=Path.cwd())
    init.add_argument("--agent")
    init.add_argument("--revision")
    init.add_argument("--name")
    init.add_argument("--argv", nargs="+")
    init.add_argument("--editable", action="append")
    init.add_argument("--prompt-file", default="prompts/system.md")
    init.add_argument("--dataset")
    init.add_argument("--evaluator")
    init.add_argument("--harness", default="command")
    init.add_argument("--optimizer", action="append")
    init.add_argument("--optimizer-config")
    init.add_argument("--scaffold-file")
    init.add_argument("--extensions", type=Path)
    init.add_argument("--max-tasks", type=int, default=9)
    init.add_argument("--offline", action="store_true")
    init.add_argument("--yes", action="store_true", help="Confirm preparation without a TTY")
    tui = sub.add_parser("tui", help="Interactive setup and live run progress")
    tui.add_argument("--project-root", type=Path, default=Path.cwd())
    tui.add_argument("--extensions", type=Path)
    agents = sub.add_parser("agents", help="List independently registered agent targets")
    agents.add_argument("--root", type=Path, default=Path("examples"))
    for name in ["validate", "plan", "run"]:
        item = sub.add_parser(name)
        item.add_argument("experiment", type=Path)
        if name == "run":
            item.add_argument("--output", type=Path)
    report = sub.add_parser("report")
    report.add_argument("run_dir", type=Path)
    report.add_argument("--csv", type=Path)
    report.add_argument("--html", action="store_true", help="Regenerate a standalone HTML report")
    args = parser.parse_args(argv)
    registry = Registry()
    try:
        os.environ.update(network_environment())
        if args.command == "plugins":
            show(registry.describe())
        elif args.command == "datasets":
            root = args.project_root.absolute()
            inventory, plugins, _ = component_inventory(root, args.extensions)
            if args.dataset_action == "list":
                show([{"name": name, **factory().describe() | {"name": name}}
                      for name, factory in sorted(inventory.factories["datasets"].items())])
            else:
                if not args.name:
                    raise ConfigurationError("Choose a dataset name or a local tasks.json")
                result, _, _ = prepare_selection(root, args.name, extensions=args.extensions,
                                                  evaluator=args.evaluator, offline=args.offline)
                show(result)
        elif args.command == "init":
            if not args.dataset:
                raise ConfigurationError("Select a dataset explicitly with --dataset")
            if not args.agent or not args.argv or not args.editable:
                raise ConfigurationError("--agent, --argv and --editable are required")
            if not args.yes:
                raise ConfigurationError("Inspect the choices then pass --yes to confirm preparation")
            root = args.project_root.absolute()
            agent = args.agent if args.revision else Path(args.agent)
            if isinstance(agent, Path) and not agent.is_absolute():
                agent = (root / agent).resolve()
            if args.revision and not args.revision.strip():
                raise ConfigurationError("A pinned Git Agent requires a revision")
            name = args.name or (agent.name if isinstance(agent, Path) and agent.is_dir() else "agent")
            name = name.lower().replace(" ", "-")
            inventory, _, _ = component_inventory(root, args.extensions)
            chosen = args.optimizer or ["gepa"]
            custom_configs = json.loads(args.optimizer_config) if args.optimizer_config else {}
            for optimizer in chosen:
                inventory.resolve("optimizers", optimizer)
            inventory.resolve("harnesses", args.harness)
            data, plugins, dependencies = prepare_selection(
                root, args.dataset, extensions=args.extensions,
                evaluator=args.evaluator, offline=args.offline)
            document = json.loads(Path(data["benchmark"]).read_text(encoding="utf-8"))
            train = sum(t["split"] == "train" for t in document["tasks"])
            validation = sum(t["split"] == "validation" for t in document["tasks"])
            stages = []
            for index, optimizer in enumerate(chosen):
                if optimizer == "gepa":
                    target = args.editable[0]
                    config = {"file": target, "iterations": 3, "batch_size": 4}
                    limit = train + 3 * (min(train, 4) + validation) + validation
                elif optimizer in {"meta_harness", "ecdysis"}:
                    scaffold = args.scaffold_file or next((f for f in args.editable if f.endswith(".py")), None)
                    if not scaffold:
                        raise ConfigurationError(f"{optimizer} requires an editable .py scaffold file")
                    config = {"file": scaffold, **({"rounds": 3} if optimizer == "ecdysis"
                                                  else {"iterations": 3})}
                    limit = train * 4 + validation * 4
                else:
                    config = custom_configs.get(optimizer, {})
                    limit = train * 3 + validation * 3
                stages.append({"id": f"opt-{index}-{optimizer.replace('_', '-')}",
                               "optimizer": optimizer, "config": config,
                               "max_trials": max(1, limit)})
            if args.revision:
                harness = {"adapter": args.harness, "command": args.argv,
                           "revision": args.revision}
            else:
                harness = {"adapter": args.harness, "command": args.argv}
            experiment = write_experiment(root / "runs" / "configs" / name, agent=agent,
                                          harness=harness, dataset=data, stages=stages, plugins=plugins,
                                          dependencies=dependencies, name=name, editable=args.editable,
                                          prompt_file=args.prompt_file, max_tasks=args.max_tasks)
            show({"experiment": experiment, "dataset": args.dataset, "stages": [s["id"] for s in stages]})
        elif args.command == "tui":
            if not sys.stdin.isatty() or not sys.stderr.isatty():
                raise ConfigurationError("TUI requires a TTY for both input and output")
            try:
                init_args = wizard_arguments(args.project_root.absolute(), args.extensions)
            except EOFError:
                print("TUI cancelled: input ended", file=sys.stderr)
                return 2
            except KeyboardInterrupt:
                print("\nTUI interrupted", file=sys.stderr)
                return 130
            print("\n  Preparing the selected dataset…", file=sys.stderr, flush=True)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(init_args)
            if code:
                return code
            experiment = Path(json.loads(output.getvalue())["experiment"])
            spec = load_experiment(experiment)
            with ProgressDisplay() as progress:
                root, summary = run_experiment(spec, Registry(), on_event=progress)
            show({"run_dir": root, "status": summary["status"], "trials_used": summary["trials_used"],
                  "report_html": root / "report.html"})
            return 0 if summary["status"] == "completed" else 3
        elif args.command == "doctor":
            show(doctor())
        elif args.command == "agents":
            show([load_agent(p) for p in sorted(args.root.rglob("agent.toml"))])
        elif args.command in {"validate", "plan", "run"}:
            spec = load_experiment(args.experiment.resolve())
            if args.command == "run":
                with ProgressDisplay() as progress:
                    root, summary = run_experiment(spec, registry, args.output, on_event=progress)
                show({"run_dir": root, "status": summary["status"], "trials_used": summary["trials_used"]})
                return 0 if summary["status"] == "completed" else 3
            available, detail = True, ""
            try:
                preflight(spec, registry)
            except UnavailableError as exc:
                available, detail = False, str(exc)
            show({"valid": True, "integrations_ready": available, "detail": detail,
                  "matrix": [{"agent": a.id, "harness": h["id"]} for a in spec["_agents"] for h in spec["_profiles"]],
                  "sources": {a.id: a.source for a in spec["_agents"]},
                  "stages": spec.get("stages", []), "objective": spec["objective"],
                  "tasks_by_split": {s: sum(t.split == s for t in spec["_tasks"]) for s in ["train", "validation", "test"]},
                  "note": "Schema/registry validation only. Run doctor and environment checks before real execution."})
        elif args.command == "report":
            data = json.loads((args.run_dir / "summary.json").read_text())
            if args.html:
                from agent_optimizer.html_report import write_html_report
                target = write_html_report(args.run_dir, data)
                show({"html": target, "status": data["status"]})
                return 0
            if args.csv:
                records = [json.loads(s) for s in (args.run_dir / "events.jsonl").read_text().splitlines()]
                records = [r for r in records if r.get("event") == "trial_completed"]
                keys = sorted({k for r in records for k in r["metrics"]})
                fixed = ["agent_id", "harness_id", "candidate_id", "task_id", "split", "repeat", "status"]
                args.csv.parent.mkdir(parents=True, exist_ok=True)
                with args.csv.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.DictWriter(stream, fieldnames=fixed + keys)
                    writer.writeheader()
                    for r in records:
                        writer.writerow({**{k: r[k] for k in fixed}, **r["metrics"]})
            show(data)
    except (ConfigurationError, UnavailableError, KeyError, TypeError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0
