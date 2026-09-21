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
