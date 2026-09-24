"""저장된 v1 실행 증거를 렌더러 공통 리포트 모델로 정규화한다."""
from __future__ import annotations

import json
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.workspace import safe_path


DIFF_PREVIEW_LIMIT = 2000


def _reject_constant(value: str):
    raise ValueError(f"잘못된 JSON 숫자: {value}")


def _read_json(path: Path, fallback: dict) -> dict:
    if not path.is_file():
        return fallback
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (ValueError, UnicodeError):
        return fallback
    return value if isinstance(value, dict) else fallback


def _read_events(root: Path) -> list[dict]:
    path = safe_path(root, "events.jsonl")
    if not path.is_file():
        return []
    events = []
    with path.open("rb") as stream:
        for line in stream:
            try:
                event = json.loads(line.decode("utf-8"), parse_constant=_reject_constant)
            except (ValueError, UnicodeError):
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def _qualified(key: str, identifier: str | None) -> str | None:
    return f"{key}/{identifier}" if isinstance(identifier, str) else None


def _relative_path(root: Path, relative: str) -> Path | None:
    try:
        return safe_path(root, relative)
    except ConfigurationError:
        return None


def _candidate(root: Path, key: str, candidate_id: str) -> dict | None:
    relative = f"{key}/candidates/{candidate_id}"
    metadata_path = _relative_path(root, f"{relative}/candidate.json")
    if metadata_path is None:
        return None
    metadata = _read_json(metadata_path, {})
    if metadata.get("id") not in (None, candidate_id):
        metadata = {}
    parents = metadata.get("parents", [])
    if not isinstance(parents, list):
        parents = []
    diff_relative = f"{relative}/changes.diff"
    diff_path = _relative_path(root, diff_relative)
    preview = None
    if diff_path is not None and diff_path.is_file():
        with diff_path.open(encoding="utf-8", errors="replace") as stream:
            preview = stream.read(DIFF_PREVIEW_LIMIT)
    else:
        diff_relative = None
    snapshot_relative = f"{relative}/bundle"
    snapshot = _relative_path(root, snapshot_relative)
    return {"id": _qualified(key, candidate_id), "candidate_id": candidate_id,
            "group_key": key, "parents": parents,
            "parent_refs": [_qualified(key, parent) for parent in parents if isinstance(parent, str)],
            "producer": metadata.get("producer"), "changed_files": metadata.get("changed_files", []),
            "content_hash": metadata.get("content_hash"),
            "snapshot_path": snapshot_relative if snapshot is not None and snapshot.is_dir() else None,
            "diff_path": diff_relative, "diff_preview": preview, "metadata": metadata}


def _candidate_ids(root: Path, key: str, group: dict, events: list[dict]) -> list[str]:
    ids = set()
    rows = [group.get("baseline"), *group.get("selected", []), *group.get("final_test", [])]
    for stage in group.get("stages", []):
        rows.extend(stage.get("selected", []))
        rows.extend(stage.get("evaluated", []))
    rows.extend(event for event in events if event.get("event") == "trial_completed")
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("candidate_id"), str):
            ids.add(row["candidate_id"])
    directory = _relative_path(root, f"{key}/candidates")
    if directory is not None and directory.is_dir():
        ids.update(entry.name for entry in directory.iterdir() if entry.is_dir() and not entry.is_symlink())
    return sorted(ids)


def _evaluation(key: str, event: dict) -> dict:
    trial_id = event.get("trial_id")
    return {"id": _qualified(key, trial_id), "trial_id": trial_id,
            "group_key": key, "candidate_ref": _qualified(key, event.get("candidate_id")),
            "candidate_id": event.get("candidate_id"),
            **{name: event.get(name) for name in (
                "stage_id", "task_id", "dataset", "split", "repeat", "seed_requested",
                "status", "valid", "metrics", "timestamp", "feedback", "execution",
                "artifacts", "error_type", "error")}}


def _evaluation_counts(evaluations: list[dict]) -> dict:
    passed = sum(row["status"] == "passed" for row in evaluations)
    return {"completed_evaluations": len(evaluations), "passed_evaluations": passed,
            "failed_evaluations": sum(row["status"] is not None and row["status"] != "passed"
                                      for row in evaluations)}


def _group(root: Path, group: dict, events: list[dict]) -> dict:
    agent_id, harness_id = group["agent_id"], group["harness_id"]
    key = f"{agent_id}/{harness_id}"
    group_events = [event for event in events if event.get("agent_id") == agent_id
                    and event.get("harness_id") == harness_id]
    evaluations = [_evaluation(key, event) for event in group_events
                   if event.get("event") == "trial_completed"]
    candidates = [_candidate(root, key, identifier)
                  for identifier in _candidate_ids(root, key, group, group_events)]
    candidates = [candidate for candidate in candidates if candidate is not None]
    return {"key": key, "agent_id": agent_id, "harness_id": harness_id,
            "baseline": group.get("baseline"), "selected": group.get("selected", []),
            "final_test": group.get("final_test", []), "stages": group.get("stages", []),
            "optimizer_usage": group.get("optimizer_usage", []), "status": group.get("status"),
            "candidates": candidates, "evaluations": evaluations,
            "structure": {"kind": None, "label": None, "units": []}, "comparison": [],
            "counts": {"candidates": len(candidates), **_evaluation_counts(evaluations)}}


def _counts(groups: list[dict], summary: dict) -> dict:
    return {"groups": len(groups), "trials_used": summary.get("trials_used"),
            "candidates": sum(group["counts"]["candidates"] for group in groups),
            **{name: sum(group["counts"][name] for group in groups) for name in (
                "completed_evaluations", "passed_evaluations", "failed_evaluations")}}


def build_report(root: Path, summary: dict) -> dict:
    """집계와 선택은 그대로 두고 trial별 근거만 별도로 보존한다."""
    manifest = _read_json(safe_path(root, "manifest.json"), {})
    events = _read_events(root)
    groups = [_group(root, group, events) for group in summary.get("groups", [])]
    experiment = manifest.get("experiment", {})
    identity = {name: summary.get(name) for name in ("run_id", "status", "synthetic")}
    identity.update({name: summary[name] for name in ("error_type", "error") if name in summary})
    return {"report_schema_version": 1,
            "identity": identity,
            "configuration": experiment, "provenance": manifest,
            "objective": experiment.get("objective", {}),
            "counts": _counts(groups, summary), "groups": groups, "events": events}
