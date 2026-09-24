from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import os
import re
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
                                          _bounded_tasks, choose_editable_file, wizard_arguments,
                                          write_experiment)
from agent_optimizer.terminal_report import ProgressDisplay
from agent_optimizer.results import write_json
from agent_optimizer.readiness import collect_dataset, collect_plan


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
    if argv and argv[0] == "doctor":
        previous = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            return _main(argv)
        finally:
            sys.dont_write_bytecode = previous
    return _main(argv)


def _main(argv):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "rerank":
        print("error: rerank is deferred; configure the objective for a new run. "
              "Stored reports and frozen selections remain available; see deferred/README.md", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(
        description="Multi-agent optimization experiment workbench",
        epilog=('From a checkout: make setup ARGS="--core"; then agent-opt datasets list and '
                'agent-opt tui (TTY), or agent-opt init --help for a noninteractive run. '
                'See README.md for a model-free fixture.'))
    sub = parser.add_subparsers(dest="command", required=True)
    plugins = sub.add_parser("plugins", help="List implemented integrations")
    plugins.add_argument("--project-root", type=Path, default=Path.cwd(), help="Checkout root (default: current directory)")
    diagnostic = sub.add_parser(
        "doctor", help="Inspect binaries, a selected dataset, or an experiment plan",
        description=("Read-only binary inventory by default. --dataset ID and --plan PATH check "
                     "selected assets without installation, Agent execution, or model calls. "
                     "--model requires --plan and explicitly probes the model API."))
    selected = diagnostic.add_mutually_exclusive_group()
    selected.add_argument("--dataset", metavar="ID", help="Inspect one selected registered dataset (read-only)")
    selected.add_argument("--plan", type=Path, metavar="PATH", help="Inspect a prepared experiment.toml (read-only)")
    diagnostic.add_argument("--project-root", type=Path, default=Path.cwd(), help="Checkout root for --dataset (default: current directory)")
    diagnostic.add_argument("--json", action="store_true", help="Emit one machine-readable readiness report")
    diagnostic.add_argument("--model", action="store_true", help="Explicitly probe the model API for a plan")
    datasets = sub.add_parser("datasets", help="List and explicitly prepare benchmark datasets")
    dataset_actions = datasets.add_subparsers(dest="dataset_action", required=True)
    for action in ("list", "prepare"):
        item = dataset_actions.add_parser(
            action, help=("List registered datasets" if action == "list" else "Prepare an explicitly selected dataset"))
        item.add_argument("--project-root", type=Path, default=Path.cwd(), help="Checkout root (default: current directory)")
        if action == "prepare":
            item.add_argument("name", nargs="?", help="Registered dataset ID or local tasks.json")
            item.add_argument("--evaluator", help="Required for local tasks.json: file.py:Symbol")
            item.add_argument("--offline", action="store_true", help="Reuse only verified cached assets")
    init = sub.add_parser("init", help="Create a user experiment with an explicit dataset",
                          description="Create a prepared experiment from a local or pinned Git Agent and a chosen dataset.")
    init.add_argument("--project-root", type=Path, default=Path.cwd(), help="Checkout root (default: current directory)")
    init.add_argument("--agent", help="Local source path or Git URL (use --revision for Git)")
    init.add_argument("--revision", help="Full commit hash required for a Git Agent")
    init.add_argument("--name", help="Experiment name; configs are written under runs/configs/")
    init.add_argument("--argv", nargs="+", help="Agent argv; use {python}, {agent_dir}, {task_dir} placeholders")
    init.add_argument("--command-json", help="JSON argv array, including dash-prefixed Agent options")
    init.add_argument("--editable", action="append", help="Editable Agent path/glob (repeat to add paths)")
    init.add_argument("--prompt-file", default="prompts/system.md", help="Agent prompt path (default: prompts/system.md)")
    init.add_argument("--dataset", action="append", help="Select a dataset explicitly: registered ID or local tasks.json (repeatable)")
    init.add_argument("--evaluator", help="Required for local tasks.json: file.py:Symbol")
    init.add_argument("--metric", default="passed", help="Evaluator metric source; default: passed")
    init.add_argument("--direction", choices=("maximize", "minimize"), default="maximize")
    init.add_argument("--harness", default="command", help="Registered Harness ID (default: command)")
    init.add_argument("--optimizer", action="append", help="Registered Optimizer ID (repeatable; default: gepa)")
    init.add_argument("--optimizer-config", help="JSON mapping from Optimizer ID to options")
    init.add_argument("--scaffold-file", help="Editable Python file for Meta-Harness/Ecdysis")
    init.add_argument("--target-file", help="Exact editable text file for a research optimizer")
    init.add_argument("--max-tasks", type=int, default=9, help="Maximum tasks sampled per dataset (default: 9)")
    init.add_argument("--max-trials", type=int, help="Maximum trial budget")
    init.add_argument("--max-wall-time-seconds", type=float, default=3600, help="Run deadline in seconds (default: 3600)")
    init.add_argument("--trial-timeout-seconds", type=float, default=120, help="Per-trial timeout in seconds (default: 120)")
    init.add_argument("--offline", action="store_true", help="Reuse only verified cached dataset assets")
    init.add_argument("--yes", action="store_true", help="Confirm preparation without a TTY")
    tui = sub.add_parser("tui", help="Interactive setup and live run progress",
                         description="TTY required. Select an Agent, its editable files, and a dataset before running.")
    tui.add_argument("--project-root", type=Path, default=Path.cwd(), help="Checkout root (default: current directory)")
    session = sub.add_parser("run-session", help="Run each selected dataset with its own evaluator")
    session.add_argument("session", type=Path, help="session.json created by init with multiple --dataset choices")
    session.add_argument("--output", type=Path, help="Override session output directory")
    agents = sub.add_parser("agents", help="List independently registered agent targets")
    agents.add_argument("--root", type=Path, default=Path("examples"), help="Agent manifest directory (default: examples)")
    for name, description in (("validate", "Validate a prepared experiment schema and integrations"),
                              ("plan", "Inspect a prepared experiment matrix without running it"),
                              ("run", "Run a prepared experiment and write reports")):
        item = sub.add_parser(name, help=description)
        item.add_argument("experiment", type=Path, help="Path to experiment.toml")
        if name == "run":
            item.add_argument("--output", type=Path, help="Override run output directory")
    report = sub.add_parser("report", help="Read a run summary or regenerate HTML")
    report.add_argument("run_dir", type=Path, help="Run directory printed by agent-opt run")
    report.add_argument("--csv", type=Path, help="Export trial metrics to this CSV path")
    report.add_argument("--html", action="store_true", help="Regenerate a standalone HTML report")
    args = parser.parse_args(argv)
    registry = Registry()
    try:
        if args.command != "doctor" or not (args.dataset or args.plan):
            os.environ.update(network_environment())
        if args.command == "plugins":
            registry.load_project(args.project_root.absolute())
            show(registry.describe())
        elif args.command == "datasets":
            root = args.project_root.absolute()
            inventory, _, _ = component_inventory(root)
            if args.dataset_action == "list":
                show([{**factory().describe(), "name": name}
                      for name, factory in sorted(inventory.factories["datasets"].items())])
            else:
                if not args.name:
                    raise ConfigurationError("Choose a dataset name or a local tasks.json")
                result, _, _ = prepare_selection(root, args.name, evaluator=args.evaluator,
                                                  offline=args.offline)
                show(result)
        elif args.command == "init":
            if not args.dataset:
                raise ConfigurationError("Select a dataset explicitly with --dataset")
            if not args.agent or not (args.argv or args.command_json) or not args.editable:
                raise ConfigurationError("--agent, --argv (or --command-json), and --editable are required")
            if args.argv and args.command_json:
                raise ConfigurationError("Choose either --argv or --command-json")
            command = json.loads(args.command_json) if args.command_json else args.argv
            if not isinstance(command, list) or not command or not all(
                    isinstance(part, str) and part for part in command):
                raise ConfigurationError("Agent argv must be a nonempty JSON string array")
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
            inventory, _, _ = component_inventory(root)
            chosen = args.optimizer or ["gepa"]
            custom_configs = json.loads(args.optimizer_config) if args.optimizer_config else {}
            if (not isinstance(custom_configs, dict)
                    or not all(isinstance(name, str) and isinstance(options, dict)
                               for name, options in custom_configs.items())):
                raise ConfigurationError("--optimizer-config must be a JSON mapping of optimizer names to options")
            for optimizer in chosen:
                inventory.resolve("optimizers", optimizer)
            inventory.resolve("harnesses", args.harness)
            target = (choose_editable_file(agent, args.editable, explicit=args.target_file)
                      if "gepa" in chosen else None)
            scaffold = (choose_editable_file(agent, args.editable, suffix=".py",
                                             explicit=args.scaffold_file)
                        if any(o in {"meta_harness", "ecdysis"} for o in chosen) else None)
            if args.revision:
                harness = {"adapter": args.harness, "command": command,
                           "revision": args.revision}
            else:
                harness = {"adapter": args.harness, "command": command}
            experiments = []
            multiple = len(args.dataset) > 1
            for index, dataset_name in enumerate(args.dataset):
                data, plugins, dependencies = prepare_selection(
                    root, dataset_name, evaluator=args.evaluator, offline=args.offline)
                document = _bounded_tasks(json.loads(Path(data["benchmark"]).read_text(encoding="utf-8")),
                                          args.max_tasks)
                train = sum(t["split"] == "train" for t in document["tasks"])
                validation = sum(t["split"] == "validation" for t in document["tasks"])
                if train == 0 and any(o in {"gepa", "meta_harness", "ecdysis"} for o in chosen):
                    raise ConfigurationError("Research optimizers require at least one train task")
                stages = []
                for stage_index, optimizer in enumerate(chosen):
                    if optimizer == "gepa":
                        config = {"file": target, "iterations": 3, "batch_size": 4,
                                  "metric": args.metric, "direction": args.direction}
                    elif optimizer in {"meta_harness", "ecdysis"}:
                        config = {"file": scaffold, **({"rounds": 3} if optimizer == "ecdysis"
                                                      else {"iterations": 3}),
                                  "direction": args.direction}
                        if optimizer == "ecdysis":
                            config.update(score_metric="solve_rate" if args.metric == "passed" else args.metric,
                                          failure_metric=args.metric)
                        else:
                            config["metric"] = args.metric
                    else:
                        config = custom_configs.get(optimizer, {})
                    config.update(custom_configs.get(optimizer, {}))
                    if optimizer == "gepa":
                        iterations, batch_size = config.get("iterations"), config.get("batch_size")
                        if (type(iterations) is not int or iterations < 1
                                or type(batch_size) is not int or batch_size < 1):
                            raise ConfigurationError("GEPA iterations and batch_size must be positive integers")
                        batch = min(train, batch_size) + validation
                        limit = train + iterations * batch + (batch if config.get("merge") else 0)
                    elif optimizer == "meta_harness":
                        iterations = config.get("iterations")
                        if type(iterations) is not int or iterations < 1:
                            raise ConfigurationError("Meta-Harness iterations must be positive")
                        limit = train + iterations * (train + validation)
                    elif optimizer == "ecdysis":
                        rounds = config.get("rounds")
                        if type(rounds) is not int or rounds < 1:
                            raise ConfigurationError("Ecdysis rounds must be positive")
                        limit = (rounds + 1) * train + validation
                    else:
                        limit = train * 3 + validation * 3
                    stages.append({"id": f"opt-{stage_index}-{optimizer.replace('_', '-')}",
                                   "optimizer": optimizer, "config": config,
                                   "max_trials": max(1, limit)})
                label = re.sub(r"[^a-zA-Z0-9_.-]", "-", Path(dataset_name).stem)
                experiment_name = f"{name}-{index + 1}-{label}" if multiple else name
                folder = (root / "runs" / "configs" / name / f"{index + 1}-{label}" if multiple
                          else root / "runs" / "configs" / name)
                experiment = write_experiment(folder, agent=agent, harness=harness, dataset=data,
                                              stages=stages, plugins=plugins, dependencies=dependencies,
                                              name=experiment_name, editable=args.editable,
                                              prompt_file=args.prompt_file, max_tasks=args.max_tasks,
                                              project_root=root,
                                              max_trials=args.max_trials,
                                              wall_time=args.max_wall_time_seconds,
                                              trial_timeout=args.trial_timeout_seconds,
                                              objective_source=args.metric,
                                              objective_direction=args.direction)
                experiments.append({"dataset": dataset_name, "experiment": str(experiment)})
            if multiple:
                target = root / "runs" / "configs" / name / "session.json"
                write_json(target, {"schema_version": 1, "name": name, "experiments": experiments})
                show({"session": target, "experiments": experiments})
            else:
                show({"experiment": experiments[0]["experiment"], "dataset": args.dataset[0],
                      "stages": [s["id"] for s in stages]})
        elif args.command == "tui":
            if not sys.stdin.isatty() or not sys.stderr.isatty():
                raise ConfigurationError("TUI requires a TTY for both input and output")
            try:
                init_args = wizard_arguments(args.project_root.absolute())
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
            prepared = json.loads(output.getvalue())
            if "session" in prepared:
                return main(["run-session", prepared["session"]])
            experiment = Path(prepared["experiment"])
            spec = load_experiment(experiment)
            with ProgressDisplay() as progress:
                progress.configure_budget(spec.get("budget", {}).get("max_trials", 100))
                root, summary = run_experiment(spec, Registry(), on_event=progress)
            show({"run_dir": root, "status": summary["status"], "trials_used": summary["trials_used"],
                  "report_html": root / "report.html"})
            return 0 if summary["status"] == "completed" else 3
        elif args.command == "run-session":
            data = json.loads(args.session.read_text(encoding="utf-8"))
            if (data.get("schema_version") != 1 or not isinstance(data.get("experiments"), list)
                    or len(data["experiments"]) < 2):
                raise ConfigurationError("run-session requires at least two prepared experiments")
            base = args.output or args.session.parent.parents[1] / "sessions"
            import time
            import uuid
            session_root = base / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                                   + "-" + uuid.uuid4().hex[:8])
            session_root.mkdir(parents=True, exist_ok=False)
            entries = []
            with ProgressDisplay() as progress:
                for item in data["experiments"]:
                    previous = set((session_root / "runs").iterdir()) if (session_root / "runs").exists() else set()
                    try:
                        spec = load_experiment(Path(item["experiment"]))
                        progress.configure_budget(spec.get("budget", {}).get("max_trials", 100))
                        run, result = run_experiment(spec, Registry(), session_root / "runs",
                                                     on_event=progress)
                        entries.append({"dataset": item["dataset"], "status": result["status"],
                                        "report": "runs/" + run.name + "/report.html",
                                        "trials_used": result["trials_used"]})
                    except (ConfigurationError, UnavailableError, OSError, ValueError) as exc:
                        current = set((session_root / "runs").iterdir()) if (session_root / "runs").exists() else set()
                        new_runs = current - previous
                        candidate = next(iter(new_runs)) if len(new_runs) == 1 else None
                        report = ("runs/" + candidate.name + "/report.html" if candidate is not None
                                  and (candidate / "report.html").is_file() else None)
                        entries.append({"dataset": item["dataset"], "status": "error",
                                        "error": str(exc), "report": report})
            from agent_optimizer.html_report import write_session_index
            index = write_session_index(session_root, entries)
            status = "completed" if all(e["status"] == "completed" for e in entries) else "partial"
            write_json(session_root / "summary.json", {"status": status, "experiments": entries})
            show({"session_dir": session_root, "status": status, "index_html": index,
                  "reports": [session_root / e["report"] for e in entries if e["report"]]})
            return 0 if status == "completed" else 3
        elif args.command == "doctor":
            if args.model and not args.plan:
                raise ConfigurationError("--model requires --plan")
            if args.dataset or args.plan:
                report = (collect_dataset(args.project_root, args.dataset, registry) if args.dataset else
                          collect_plan(args.plan, registry, model=args.model))
                if args.json:
                    show(report)
                else:
                    print(f"{report['scope']} readiness: {'ready' if report['ready'] else 'not ready'}")
                    for row in report["checks"]:
                        print(f"[{row['status']}] {row['id']}: {row['message']}")
                        if row["remedy"]:
                            print(f"  Remedy: {row['remedy']}")
                return 0 if report["ready"] else 2
            show(doctor())
        elif args.command == "agents":
            show([load_agent(p) for p in sorted(args.root.rglob("agent.toml"))])
        elif args.command in {"validate", "plan", "run"}:
            spec = load_experiment(args.experiment.resolve())
            if args.command == "run":
                with ProgressDisplay() as progress:
                    progress.configure_budget(spec.get("budget", {}).get("max_trials", 100))
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
