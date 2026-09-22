from __future__ import annotations

import argparse
import csv
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
    args = parser.parse_args(argv)
    registry = Registry()
    try:
        os.environ.update(network_environment())
        if args.command == "plugins":
            show(registry.describe())
        elif args.command == "doctor":
            show(doctor())
        elif args.command == "agents":
            show([load_agent(p) for p in sorted(args.root.rglob("agent.toml"))])
        elif args.command in {"validate", "plan", "run"}:
            spec = load_experiment(args.experiment.resolve())
            if args.command == "run":
                root, summary = run_experiment(spec, registry, args.output)
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
