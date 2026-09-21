from __future__ import annotations

import json
import threading
from pathlib import Path

from agent_optimizer.contracts import jsonable


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(jsonable(value), indent=2, ensure_ascii=False,
                                    allow_nan=False), encoding="utf-8")
    temporary.replace(path)


class EventStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()

    def append(self, value) -> None:
        with self.lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(jsonable(value), ensure_ascii=False, allow_nan=False) + "\n")



def write_report(root, summary):
    lines = ["# Experiment report", "", f"Status: {summary['status']}",
             f"Synthetic: {summary['synthetic']}", "",
             "| Agent | Harness | Candidate | Split | Metrics |", "|---|---|---|---|---|"]
    for group in summary["groups"]:
        for row in [group["baseline"], *group["selected"], *group["final_test"]]:
            if row is None:
                continue
            metrics = json.dumps(row["metrics"], ensure_ascii=False)
            lines.append(f"| {group['agent_id']} | {group['harness_id']} | {row['candidate_id']} | {row['split']} | {metrics} |")
    events_path = root / "events.jsonl"
    trials = [json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
    trials = [r for r in trials if r.get("event") == "trial_completed"]
    lines += ["", "## Agent usage (Harness-reported partial; not complete totals)", "",
              "| Agent | Harness | Candidate | Split | IO tokens | Cost USD |", "|---|---|---|---|---|---|"]
    for group in summary["groups"]:
        rows = [group["baseline"], *group["selected"], *group["final_test"]]
        rows = {(r["candidate_id"], r["split"]): r for r in rows if r is not None}
        for (candidate, split), row in rows.items():
            matching = [r for r in trials if (r["agent_id"], r["harness_id"], r["candidate_id"], r["split"]) ==
                        (group["agent_id"], group["harness_id"], candidate, split)]
            usage = []
            for key in ("harness_reported_io_tokens", "harness_reported_cost_usd"):
                values = [r["metrics"].get(key) for r in matching]
                known = (values and len(values) == row.get("trial_count") and all(v is not None for v in values)
                         and all(r.get("valid", True) for r in matching))
                usage.append(json.dumps(sum(values) if known else None))
            lines.append(f"| {group['agent_id']} | {group['harness_id']} | {candidate} | {split} | {' | '.join(usage)} |")
    lines += ["", "## Optimization", "", "| Agent | Harness | Stage | Status | Checkpoint |",
              "|---|---|---|---|---|"]
    for group in summary["groups"]:
        for stage in group.get("stages", []):
            lines.append(f"| {group['agent_id']} | {group['harness_id']} | {stage['id']} | "
                         f"{stage['status']} | {json.dumps(stage.get('checkpoint', {}))} |")
        lines += ["", f"Optimizer usage ({group['agent_id']}/{group['harness_id']}):",
                  "```json", json.dumps(group.get("optimizer_usage", []), indent=2), "```",
                  "Candidate changes: see this group's candidates/*/changes.diff."]
    lines += ["", "Missing metrics are null, not zero. Empty usage lists mean unreported usage, not free execution.",
              "Harness-reported usage can be partial. Compare only identical datasets, models and budgets."]
    (root / "report.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
