from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from agent_optimizer.contracts import jsonable
from agent_optimizer.locale import current_language, human


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(jsonable(value), indent=2, ensure_ascii=False,
                                    allow_nan=False), encoding="utf-8")
    temporary.replace(path)


class EventStore:
    def __init__(self, path: Path, on_event=None):
        self.path = path
        self.lock = threading.Lock()
        self.on_event = on_event

    def append(self, value) -> None:
        with self.lock, self.path.open("a", encoding="utf-8") as stream:
            record = {"schema_version": 1, "timestamp": datetime.now(timezone.utc).isoformat(),
                      **jsonable(value)}
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
        if self.on_event is not None:
            self.on_event(record)



def _cell(value) -> str:
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _table_row(*values) -> str:
    return "| " + " | ".join(_cell(value) for value in values) + " |"


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def write_report(root: Path, summary: dict, report: dict | None = None,
                 *, language: str | None = None) -> None:
    language = language or summary.get("report_language") or current_language()
    def label(item):
        return human(item, lang=language)

    def header(*items):
        return _table_row(*(label(item) for item in items))

    if report is None:
        from agent_optimizer.report_model import build_report
        report = build_report(root, summary)
    identity = report["identity"]
    groups = report["groups"]
    lines = [f"# {label('Experiment report')}", "", f"{label('Status')}: {_cell(identity.get('status'))}",
             f"{label('Synthetic')}: {identity.get('synthetic')}", "",
             header('Agent', 'Harness', 'Candidate', 'Split', 'Metrics'), "|---|---|---|---|---|"]
    if "run_wall_time_seconds" in identity:
        lines.insert(4, f"{label('Observed run wall time')}: {identity['run_wall_time_seconds']} s")
    for group in groups:
        for row in [group["baseline"], *group["selected"], *group["final_test"]]:
            if row is not None:
                lines.append(_table_row(group["agent_id"], group["harness_id"],
                                        row["candidate_id"], row["split"], _json(row["metrics"])))
    counts = report["counts"]
    lines += ["", f"## {label('Group comparison and completed evaluations')}", "",
              f"{label('Reserved trials')}: {_json(counts['trials_used'])}; {label('completed evaluations')}: {counts['completed_evaluations']}", "",
              header('Agent', 'Harness', 'Trend', 'Completed', 'Passed', 'Failed', 'Metric', 'Baseline', 'Selected', 'Delta'),
              "|---|---|---|---|---|---|---|---|---|---|"]
    for group in groups:
        measured = group["comparison"] or [None]
        for item in measured:
            lines.append(_table_row(group["agent_id"], group["harness_id"],
                                    group["comparison_trend"],
                                    f"{group['counts']['completed_evaluations']} {label('Completed')}",
                                    group["counts"]["passed_evaluations"],
                                    group["counts"]["failed_evaluations"],
                                    item["name"] if item else "—",
                                    _json(item["baseline"]) if item else "null",
                                    _json(item["selected"]) if item else "null",
                                    _json(item["delta"]) if item else "null"))
    lines += ["", f"## {label('Agent usage (Harness-reported partial; not complete totals)')}", "",
               header('Agent', 'Harness', 'Candidate', 'Split', 'IO tokens', 'Cost USD'), "|---|---|---|---|---|---|"]
    for group in groups:
        for usage in group["agent_usage"]:
            lines.append(_table_row(group["agent_id"], group["harness_id"],
                                    usage["candidate_id"], usage["split"],
                                    _json(usage["harness_reported_io_tokens"]),
                                    _json(usage["harness_reported_cost_usd"])))
    lines += ["", f"## {label('Optimization')}", "", header('Agent', 'Harness', 'Stage', 'Status', 'Checkpoint'),
              "|---|---|---|---|---|"]
    for group in groups:
        for stage in group["stages"]:
            lines.append(_table_row(group["agent_id"], group["harness_id"], stage["id"],
                                    stage["status"], _json(stage.get("checkpoint", {}))))
    for group in groups:
        lines += ["", f"{label('Optimizer usage')} ({_cell(group['agent_id'])}/{_cell(group['harness_id'])}):",
                   "```json", json.dumps(group["optimizer_usage"], indent=2, ensure_ascii=False), "```",
                   label("Candidate changes: see this group's candidates/*/changes.diff.")]
        structure = group["structure"]
        if structure["units"] or structure["edges"]:
            lines += ["", f"{label('Structure')} ({_cell(group['key'])}): {_cell(structure['kind'])}"]
            for unit in structure["units"]:
                lines.append(f"- {_cell(unit['unit_type'])}: {_cell(unit['label'] or unit['unit_id'])}")
            for edge in structure["edges"]:
                lines.append(f"- {_cell(edge['candidate_id'])} ← {_cell(', '.join(edge['parents']))}")
        for failure in group["failures"]:
            lines.append(f"- {label('Failure')} {_cell(failure['evaluation_ref'])}: {_cell(failure['category'])}"
                         f" — {_cell(failure['message']) if failure['message'] else label('not reported')}")
    if identity.get("failure"):
        lines.append(f"{label('Run failure')}: {_cell(identity['failure']['category'])} — "
                     f"{_cell(identity['failure'].get('message') or label('not reported'))}")
    provenance = report["provenance"]
    lines += ["", f"## {label('Reproducibility')}", "",
               f"{label('Dataset')}: {_cell(provenance.get('benchmark', {}).get('id', label('not recorded')))}",
               f"{label('Benchmark SHA-256')}: {_cell(provenance.get('benchmark_sha256', label('not recorded')))}",
               f"{label('Objective')}: {_cell(_json(report['objective']))}",
               f"{label('Budget')}: {_cell(_json(report['configuration'].get('budget')))}"]
    lines += ["", label("Missing metrics are null, not zero. Empty usage lists mean unreported usage, not free execution."),
               label("Harness-reported usage can be partial. Compare only identical datasets, models and budgets.")]
    (root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report_artifacts(root: Path, summary: dict, *, language: str | None = None) -> Path:
    from agent_optimizer.html_report import write_html_report
    from agent_optimizer.report_model import build_report

    report = build_report(root, summary)
    write_json(root / "report.json", report)
    write_report(root, summary, report=report, language=language)
    return write_html_report(root, summary, report=report, language=language)
