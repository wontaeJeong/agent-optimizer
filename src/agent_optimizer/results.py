from __future__ import annotations

import json
import html
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from agent_optimizer.contracts import ConfigurationError, jsonable
from agent_optimizer.locale import current_language, human
from agent_optimizer.workspace import safe_path


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



def _cell(value, limit=180) -> str:
    rendered = "null" if value is None else str(value)
    rendered = " ".join(rendered.split())
    if limit is not None and len(rendered) > limit:
        rendered = rendered[:limit] + "…"
    rendered = html.escape(rendered, quote=False)
    return re.sub(r"([\\`*_{}\[\]()#!|~])", r"\\\1", rendered)


def _table_row(*values) -> str:
    return "| " + " | ".join(_cell(value) for value in values) + " |"


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _relative_link(root: Path, relative: str, label: str) -> str | None:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        return None
    try:
        target = safe_path(root, relative)
    except (ConfigurationError, OSError, ValueError):
        return None
    if not target.is_file():
        return None
    return f"[{_cell(label)}]({quote(relative, safe='/')})"


def write_report(root: Path, summary: dict, report: dict | None = None,
                 *, language: str | None = None) -> None:
    language = language or summary.get("report_language") or current_language()
    def label(item):
        return human(item, lang=language)

    def header(*items):
        return _table_row(*(phrase("방향", "Direction") if item == "Direction" else
                            phrase("값", "Value") if item == "Value" else label(item)
                            for item in items))

    if report is None:
        from agent_optimizer.report_model import build_report
        report = build_report(root, summary)
    def phrase(ko, en):
        return ko if language == "ko" else en

    identity = report["identity"]
    groups = report["groups"]
    evidence = report.get("evidence") or {}
    lines = [f"# {label('Experiment report')}", "", f"{label('Status')}: {_cell(identity.get('status'))}",
             f"{label('Synthetic')}: {_cell(identity.get('synthetic'))}"]
    if "run_wall_time_seconds" in identity:
        lines.append(f"{label('Observed run wall time')}: {_cell(identity['run_wall_time_seconds'])} s")
    lines += ["", f"**{phrase('근거 상태', 'Evidence status')}: {_cell(evidence.get('status', 'unknown'))}**"]
    warning_labels = {
        "events_missing": phrase("이벤트 파일 없음", "event file missing"),
        "events_invalid_lines": phrase("읽지 못한 이벤트 줄", "unreadable event lines"),
        "group_trial_count_mismatch": phrase("그룹 평가 건수 불일치", "group evaluation count mismatch"),
        "reserved_completed_gap": phrase("예약 예산과 완료 평가의 차이 (유실 단정 불가)",
                                         "reserved/completed gap (not necessarily missing records)"),
    }
    for warning in evidence.get("warnings", []):
        scope = f" {_cell(warning['group_key'])}" if warning.get("group_key") else ""
        numbers = (f" ({phrase('기록', 'expected')} {_cell(warning['expected'])} / "
                   f"{phrase('관측', 'observed')} {_cell(warning['observed'])})"
                   if warning.get("expected") is not None else "")
        lines.append(f"- {_cell(warning_labels.get(warning['code'], warning['code']))}{scope}{numbers}")
    if evidence.get("status") == "unknown":
        lines.append(phrase("- 완료 평가의 원본 대조 기준이 부족합니다.",
                            "- The source count for completed evaluations is unavailable."))
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
    lines += ["", f"## {phrase('기준 → 선택 검증', 'Baseline → selected validation')}", "",
              header('Agent', 'Harness', 'Candidate', 'Metric', 'Direction', 'Baseline', 'Selected', 'Delta', 'Trend'),
              "|---|---|---|---|---|---|---|---|---|"]
    incomparable = []
    for group in groups:
        selected = next((row for row in group["selected"] if isinstance(row, dict)
                         and row.get("split") == "validation" and row.get("valid") is True
                         and not row.get("partial", False)
                         and row.get("agent_id") == group["agent_id"]
                         and row.get("harness_id") == group["harness_id"]), None)
        for item in group["comparison"] or [None]:
            lines.append(_table_row(group["agent_id"], group["harness_id"],
                                    selected.get("candidate_id") if selected else "—",
                                    item["name"] if item else "—",
                                    item["direction"] if item else "—",
                                    item["baseline"] if item else None,
                                    item["selected"] if item else None,
                                    item["delta"] if item else None,
                                    item["trend"] if item else "unknown"))
        invalid = [row.get("candidate_id") for row in group["selected"] if isinstance(row, dict)
                   and row is not selected]
        if invalid:
            incomparable.append(phrase("비교 불가 선택 기록: ", "Recorded incomparable selection: ")
                                + _cell(group["key"]) + " · "
                                + _cell(", ".join(str(identifier) for identifier in invalid)))
    if incomparable:
        lines += ["", *incomparable]
    lines += ["", f"## {phrase('최종 테스트', 'Final test')}", "",
              phrase("검증 선택을 확정한 뒤 기록된 별도 test 집계입니다.",
                     "Separate test aggregates recorded after validation selection."), "",
              header('Agent', 'Harness', 'Candidate', 'Split', 'Metric', 'Value', 'Completed'),
              "|---|---|---|---|---|---|---|"]
    for group in groups:
        for row in group["final_test"]:
            if not isinstance(row, dict):
                continue
            metrics = row.get("metrics") or {}
            if not isinstance(metrics, dict):
                continue
            for metric, number in metrics.items():
                lines.append(_table_row(group["agent_id"], group["harness_id"],
                                        row.get("candidate_id"), row.get("split"), metric,
                                        number, row.get("trial_count")))
    if lines[-1] == "|---|---|---|---|---|---|---|":
        lines += ["", phrase("기록된 최종 테스트 없음", "No recorded final test")]
    lines += ["", f"## {label('Agent usage (Harness-reported partial; not complete totals)')}", "",
               header('Agent', 'Harness', 'Candidate', 'Split', 'IO tokens', 'Cost USD'), "|---|---|---|---|---|---|"]
    for group in groups:
        for usage in group["agent_usage"]:
            lines.append(_table_row(group["agent_id"], group["harness_id"],
                                    usage["candidate_id"], usage["split"],
                                    _json(usage["harness_reported_io_tokens"]),
                                    _json(usage["harness_reported_cost_usd"])))
    lines += ["", f"## {label('Optimization')}", "", header('Agent', 'Harness', 'Stage', 'Status', 'Candidate'),
               "|---|---|---|---|---|"]
    for group in groups:
        for stage in group["stages"]:
            lines.append(_table_row(group["agent_id"], group["harness_id"], stage["id"],
                                     stage["status"], ", ".join(str(row.get("candidate_id"))
                                                               for row in stage.get("selected", [])
                                                               if isinstance(row, dict)) or "—"))
    for group in groups:
        links = [_relative_link(root, f"{group['key']}/stages/{stage.get('id')}.json",
                                f"{stage.get('id')}.json") for stage in group["stages"]]
        lines += ["", f"{_cell(group['key'])}: " + " · ".join(link for link in links if link),
                  phrase("단계별 선택·체크포인트 원본: 위 링크 또는 report.json.",
                         "Stage selections and checkpoints: links above or report.json.")]
        for candidate in group["candidates"]:
            link = _relative_link(root, candidate.get("diff_path"), "changes.diff")
            if link:
                lines.append(f"- {_cell(candidate['candidate_id'])}: {link}")
        structure = group["structure"]
        if structure["units"] or structure["edges"]:
            lines += ["", f"{label('Structure')} ({_cell(group['key'])}): {_cell(structure['kind'])}"]
            for unit in structure["units"]:
                lines.append(f"- {_cell(unit['unit_type'])}: {_cell(unit['label'] or unit['unit_id'])}"
                             + (f" ← {_cell(unit['parent_unit_id'])}" if unit['parent_unit_ref'] else ""))
            for edge in structure["edges"]:
                lines.append(f"- {_cell(edge['candidate_id'])} ← {_cell(', '.join(edge['parents']))}")
        for evaluation in group["evaluations"]:
            link = _relative_link(root, f"{group['key']}/trials/{evaluation['trial_id']}/result.json",
                                  evaluation["trial_id"]) if isinstance(evaluation.get("trial_id"), str) else None
            lines.append(f"- {phrase('평가', 'Evaluation')} "
                         + (link or _cell(evaluation.get("trial_id")))
                         + f": {_cell(evaluation.get('split'))} · {_cell(evaluation.get('status'))}"
                         + (f" · {evaluation['failure']['category']}"
                            if evaluation.get("failure") else ""))
        for failure in group["failures"]:
            evaluation = next((row for row in group["evaluations"]
                               if row["id"] == failure["evaluation_ref"]), None)
            trial_id = evaluation.get("trial_id") if evaluation else None
            link = (_relative_link(root, f"{group['key']}/trials/{trial_id}/result.json", trial_id)
                    if isinstance(trial_id, str) else None)
            lines.append(f"- {label('Failure')} {link or _cell(failure['evaluation_ref'])}: {failure['category']}"
                          f" — {_cell(failure['message']) if failure['message'] else label('not reported')}")
    if identity.get("failure"):
        lines.append(f"{label('Run failure')}: {_cell(identity['failure']['category'])} — "
                     f"{_cell(identity['failure'].get('message') or label('not reported'))}")
    provenance = report["provenance"]
    lines += ["", f"## {label('Reproducibility')}", "",
               f"{label('Dataset')}: {_cell(provenance.get('benchmark', {}).get('id', label('not recorded')))}",
               f"{label('Benchmark SHA-256')}: {_cell(provenance.get('benchmark_sha256', label('not recorded')))}",
               f"{label('Objective')}: " + ", ".join(
                   f"{_cell(metric.get('name'))} ({_cell(metric.get('direction'))})"
                   for metric in (report['objective'].get('metrics') or []) if isinstance(metric, dict)),
               f"{label('Budget')}: {_cell((report['configuration'].get('budget') or {}).get('max_trials'))}"]
    source_links = [_relative_link(root, name, name) for name in
                    ("summary.json", "events.jsonl", "manifest.json", "report.json")]
    lines.append(phrase("원본·전체 파생 자료: ", "Source and full derived data: ")
                 + " · ".join(link for link in source_links if link))
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
