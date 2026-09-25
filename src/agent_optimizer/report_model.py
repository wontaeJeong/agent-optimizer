"""저장된 v1 실행 증거를 렌더러 공통 리포트 모델로 정규화한다."""
from __future__ import annotations

import json
import math
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
    if metadata.get("id") != candidate_id:
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
    rows.extend(event for event in events if event.get("event") in (
        "trial_completed", "candidate_evaluated", "candidate_created", "optimizer_merge_completed"))
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("candidate_id"), str):
            ids.add(row["candidate_id"])
    for event in events:
        if event.get("event") == "report_unit" and isinstance(event.get("candidate_ids"), list):
            ids.update(value for value in event["candidate_ids"] if isinstance(value, str))
    directory = _relative_path(root, f"{key}/candidates")
    if directory is not None and directory.is_dir():
        for entry in directory.iterdir():
            if not entry.is_dir() or entry.is_symlink():
                continue
            metadata_path = _relative_path(root, f"{key}/candidates/{entry.name}/candidate.json")
            if metadata_path is not None and _read_json(metadata_path, {}).get("id") == entry.name:
                ids.add(entry.name)
    return sorted(ids)


def _evaluation(key: str, event: dict) -> dict:
    trial_id = event.get("trial_id")
    row = {"id": _qualified(key, trial_id), "trial_id": trial_id,
           "group_key": key, "candidate_ref": _qualified(key, event.get("candidate_id")),
           "candidate_id": event.get("candidate_id"),
           **{name: event.get(name) for name in (
               "stage_id", "task_id", "dataset", "split", "repeat", "seed_requested",
               "status", "valid", "metrics", "timestamp", "feedback", "execution",
               "artifacts", "error_type", "error")}}
    row["failure"] = _failure(row["status"], row["execution"], row["error_type"],
                              row["error"], row["feedback"])
    return row


def _failure(status, execution=None, error_type=None, error=None, feedback=None) -> dict | None:
    if status in {None, "passed", "completed"}:
        return None
    execution = execution if isinstance(execution, dict) else {}
    causes = {"infrastructure_error": "infrastructure", "timeout": "timeout",
              "unsupported": "unsupported", "interrupted": "interrupted",
              "process_error": "execution",
              "error": "run_error", "source_error": "run_error",
              "budget_exhausted": "interrupted"}
    execution_status = execution.get("status")
    category = causes.get(execution_status) or causes.get(status)
    if category == "run_error" and error_type == "TimeoutError":
        category = "timeout"
    if category is None:
        category = ("timeout" if error_type == "TimeoutError" else
                    "run_error" if error_type else
                    "scored_failure" if status == "failed" else None)
    if category is None:
        return None
    message = (error or (execution.get("detail") if execution_status != "completed" else None)
               or feedback)
    return {"category": category, "message": message if isinstance(message, str) and message else None}


def _finite_number(value) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # An integer can exceed the range of a float.
        return False


def _metric_value(row, key: str, name: str):
    if (not isinstance(row, dict) or row.get("split") != "validation"
            or row.get("valid") is not True or row.get("partial", False)):
        return None
    if row.get("agent_id") != key[0] or row.get("harness_id") != key[1]:
        return None
    metrics = row.get("metrics")
    value = metrics.get(name) if isinstance(metrics, dict) else None
    return value if _finite_number(value) else None


def _trend(before, after, direction):
    if before is None or after is None:
        return "unknown"
    if after == before:
        return "unchanged"
    return "improved" if (after > before) == (direction == "maximize") else "regressed"


def _comparison(group: dict, objective: dict) -> tuple[list[dict], str]:
    key = group["agent_id"], group["harness_id"]
    selected = next((row for row in group.get("selected", [])
                     if isinstance(row, dict) and row.get("split") == "validation"
                     and row.get("valid") is True and not row.get("partial", False) and
                     (row.get("agent_id"), row.get("harness_id")) == key), None)
    if selected is None:
        return [], "unknown"
    comparison = []
    overall = "unchanged"
    for metric in objective.get("metrics", []):
        name, direction = metric["name"], metric["direction"]
        before = _metric_value(group.get("baseline"), key, name)
        after = _metric_value(selected, key, name)
        try:
            difference = after - before if before is not None and after is not None else None
        except OverflowError:
            difference = None
        delta = difference if _finite_number(difference) else None
        trend = _trend(before, after, direction) if delta is not None else "unknown"
        item = {"name": name, "direction": direction, "baseline": before, "selected": after,
                "delta": delta, "trend": trend}
        if (metric.get("source") == "passed" and metric.get("aggregate", "mean") == "mean"
                and before is not None and after is not None
                and 0 <= before <= 1 and 0 <= after <= 1):
            item["delta_pp"] = (after - before) * 100
        comparison.append(item)
        if overall == "unchanged" and trend != "unchanged":
            overall = trend
    return comparison, overall if comparison else "unknown"


def _evaluation_counts(evaluations: list[dict]) -> dict:
    passed = sum(row["status"] == "passed" for row in evaluations)
    return {"evaluations": len(evaluations), "completed_evaluations": len(evaluations),
            "passed_evaluations": passed,
            "failed_evaluations": sum(row["failure"] is not None for row in evaluations)}


def _agent_usage(group: dict, events: list[dict]) -> list[dict]:
    rows = [group.get("baseline"), *group.get("selected", []), *group.get("final_test", [])]
    distinct = {(row["candidate_id"], row["split"]): row for row in rows
                if isinstance(row, dict) and "candidate_id" in row and "split" in row}
    usage = []
    for (candidate_id, split), row in distinct.items():
        matching = [item for item in events if item.get("event") == "trial_completed"
                    and item.get("candidate_id") == candidate_id and item.get("split") == split]
        entry = {"candidate_id": candidate_id, "split": split}
        for name in ("harness_reported_io_tokens", "harness_reported_cost_usd"):
            values = [(item.get("metrics") or {}).get(name) for item in matching]
            complete = (bool(values) and len(values) == row.get("trial_count")
                        and all(item.get("valid", True) for item in matching)
                        and all(_finite_number(value) for value in values))
            total = sum(values) if complete else None
            entry[name] = total if _finite_number(total) else None
        usage.append(entry)
    return usage


def _structure(key: str, candidates: list[dict], evaluations: list[dict], events: list[dict]) -> dict:
    by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
    units = []
    seen = {}
    explicit = {}
    conflicting_parents = set()

    def add_references(unit, event):
        references = event.get("evaluation_refs")
        if isinstance(references, list):
            unit.setdefault("_references", []).extend(
                (reference, event.get("split")) for reference in references
                if isinstance(reference, str))

    for event in events:
        name = event.get("event")
        candidate_id = event.get("candidate_id")
        candidate = by_id.get(candidate_id) if isinstance(candidate_id, str) else None
        if candidate is not None and name == "candidate_created":
            parent = event.get("parent_id")
            if not candidate["metadata"]:
                candidate["parents"] = [parent] if isinstance(parent, str) else []
                candidate["parent_refs"] = [_qualified(key, value) for value in candidate["parents"]]
                candidate["producer"] = event.get("producer")
        elif candidate is not None and name == "optimizer_merge_completed":
            parents = event.get("parents")
            if isinstance(parents, list) and all(isinstance(p, str) for p in parents):
                candidate["parents"] = parents
                candidate["parent_refs"] = [_qualified(key, value) for value in parents]

        if name == "report_unit":
            unit_id = event.get("unit_id")
            unit_type = event.get("unit_type")
            if not isinstance(unit_id, str) or not isinstance(unit_type, str):
                continue
            stage_id = event.get("stage_id")
            parent_id = event.get("parent_unit_id")
            scope = f"{key}/{stage_id}/report_unit" if isinstance(stage_id, str) else None
            ids = event.get("candidate_ids", [])
            if not isinstance(ids, list):
                ids = []
            ids = list(dict.fromkeys(value for value in ids if isinstance(value, str)))
            identity = (stage_id if isinstance(stage_id, str) else None, unit_id)
            if identity in explicit:
                existing = explicit[identity]
                add_references(existing, event)
                existing["candidate_ids"].extend(value for value in ids
                                                 if value not in existing["candidate_ids"])
                if existing["parent_unit_id"] != parent_id:
                    existing["parent_unit_id"] = None
                    conflicting_parents.add(identity)
                continue
            unit = {"unit_id": unit_id, "unit_ref": f"{scope}/{unit_id}" if scope else None,
                    "stage_id": stage_id, "parent_unit_id": parent_id,
                    "parent_unit_ref": None, "unit_type": unit_type,
                    "label": event.get("label"), "candidate_ids": ids}
            add_references(unit, event)
            explicit[identity] = unit
            units.append(unit)
        elif name in ("optimizer_iteration_started", "optimizer_iteration_completed"):
            iteration = event.get("iteration")
            stage_id = event.get("stage_id")
            if type(iteration) is not int or not isinstance(stage_id, str):
                continue
            identifier = f"{stage_id}/iteration-{iteration}"
            if identifier not in seen:
                seen[identifier] = {"unit_id": identifier, "unit_ref": f"{key}/{identifier}",
                                    "stage_id": stage_id, "parent_unit_id": None,
                                    "parent_unit_ref": None, "unit_type": "iteration",
                                    "label": f"Iteration {iteration}", "candidate_ids": []}
                units.append(seen[identifier])
            if isinstance(candidate_id, str) and candidate_id not in seen[identifier]["candidate_ids"]:
                seen[identifier]["candidate_ids"].append(candidate_id)
            add_references(seen[identifier], event)

    for (stage_id, unit_id), unit in explicit.items():
        parent_id = unit["parent_unit_id"]
        if ((stage_id, unit_id) not in conflicting_parents and isinstance(stage_id, str)
                and isinstance(parent_id, str) and parent_id != unit_id
                and (stage_id, parent_id) in explicit):
            unit["parent_unit_ref"] = explicit[(stage_id, parent_id)]["unit_ref"]
    by_evaluation = {}
    for evaluation in evaluations:
        if isinstance(evaluation["id"], str):
            by_evaluation.setdefault(evaluation["id"], []).append(evaluation)
    for unit in units:
        unit["candidate_refs"] = [_qualified(key, value) for value in unit["candidate_ids"]]
        unit["evaluation_refs"] = []
        for reference, split in unit.pop("_references", []):
            matches = by_evaluation.get(reference, [])
            if len(matches) != 1:
                continue
            evaluation = matches[0]
            if (not isinstance(unit["stage_id"], str) or
                    evaluation["stage_id"] != unit["stage_id"] or
                    evaluation["split"] not in ("train", "validation") or
                    (split is not None and evaluation["split"] != split) or
                    evaluation["candidate_id"] not in unit["candidate_ids"]):
                continue
            if reference not in unit["evaluation_refs"]:
                unit["evaluation_refs"].append(reference)
    edges = [{"candidate_id": candidate["candidate_id"], "candidate_ref": candidate["id"],
              "parents": candidate["parents"], "parent_refs": candidate["parent_refs"]}
             for candidate in candidates if candidate["parents"]]
    kinds = {unit["unit_type"] for unit in units}
    kind = next(iter(kinds)) if len(kinds) == 1 else "mixed" if kinds else "lineage" if edges else None
    return {"kind": kind, "label": None, "units": units, "edges": edges}


def _objective_vector(metrics, objective):
    if not isinstance(metrics, dict):
        return None
    specs = objective.get("metrics", []) if isinstance(objective, dict) else []
    if not specs:
        return None
    vector = []
    for metric in specs:
        if not isinstance(metric, dict) or metric.get("direction") not in ("maximize", "minimize"):
            return None
        number = metrics.get(metric.get("name"))
        if not _finite_number(number):
            return None
        vector.append(number if metric["direction"] == "maximize" else -number)
    return tuple(vector)


def _visualization(group: dict, events: list[dict], evaluations: list[dict], objective: dict) -> dict:
    key = f'{group["agent_id"]}/{group["harness_id"]}'
    selected = {row["candidate_id"] for row in group.get("selected", [])
                if isinstance(row, dict) and isinstance(row.get("candidate_id"), str)
                and row.get("split") == "validation" and row.get("valid") is True
                and not row.get("partial", False)
                and row.get("agent_id") == group["agent_id"]
                and row.get("harness_id") == group["harness_id"]}
    baseline = group.get("baseline") if isinstance(group.get("baseline"), dict) else {}
    progress, best_vector, best_metrics = [], None, None
    for event in events:
        if event.get("event") != "candidate_evaluated" or event.get("split") != "validation":
            continue
        candidate_id = event.get("candidate_id")
        if not isinstance(candidate_id, str):
            continue
        vector = (_objective_vector(event.get("metrics"), objective)
                  if event.get("valid") is True and not event.get("partial", False) else None)
        if vector is None:
            improvement = "invalid"
        elif best_vector is None or vector > best_vector:
            improvement = (("baseline" if candidate_id == baseline.get("candidate_id") else "first")
                           if best_vector is None else "improved")
            best_vector, best_metrics = vector, event["metrics"]
        else:
            improvement = "equal" if vector == best_vector else "regressed"
        progress.append({"candidate_id": candidate_id, "stage_id": event.get("stage_id"),
                         "metrics": event.get("metrics"), "best_metrics": best_metrics,
                         "improvement": improvement, "selected": candidate_id in selected,
                         "source": "candidate_evaluated", "timestamp": event.get("timestamp"),
                         "trial_refs": [_qualified(key, trial) for trial in event.get("trial_ids", [])
                                        if isinstance(trial, str)]
                         if isinstance(event.get("trial_ids"), list) else []})

    timeline = []
    outcomes = {}
    for row in evaluations:
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        duration = metrics.get("task_wall_time_seconds")
        category = (row["failure"]["category"] if row.get("failure") else row.get("status") or "unknown")
        outcomes[category] = outcomes.get(category, 0) + 1
        timeline.append({"trial_id": row["trial_id"], "candidate_id": row["candidate_id"],
                         "stage_id": row["stage_id"], "task_id": row["task_id"],
                         "split": row["split"], "status": row["status"], "category": category,
                         "duration_seconds": duration if _finite_number(duration) and duration >= 0 else None,
                         "evaluation_ref": row["id"]})

    tasks = []
    specs = objective.get("metrics", []) if isinstance(objective, dict) else []
    if (selected and baseline.get("valid") is True and
            any(metric.get("source") == "passed" and metric.get("aggregate", "mean") == "mean"
                for metric in specs if isinstance(metric, dict))):
        winner = next(iter(selected))
        grouped = {}
        for row in evaluations:
            if row.get("split") == "validation" and row.get("candidate_id") in (baseline.get("candidate_id"), winner):
                grouped.setdefault((row.get("task_id"), row["candidate_id"]), []).append(row)

        def task_state(rows):
            if not rows or any(row.get("valid") is not True for row in rows):
                return "unknown"
            values = [(row.get("metrics") or {}).get("passed") for row in rows]
            if any(not _finite_number(number) or number not in (0, 1) for number in values):
                return "unknown"
            return "passed" if all(number == 1 for number in values) else "failed" if all(number == 0 for number in values) else "mixed"

        for task_id in sorted({name for name, candidate in grouped if candidate == baseline.get("candidate_id")
                               and (name, winner) in grouped if isinstance(name, str)}):
            before = grouped[(task_id, baseline["candidate_id"])]
            after = grouped[(task_id, winner)]
            if len(before) != len(after) or {r["repeat"] for r in before} != {r["repeat"] for r in after}:
                continue
            tasks.append({"task_id": task_id, "baseline": task_state(before),
                          "selected": task_state(after)})
    return {"progress": progress, "trial_timeline": timeline, "task_comparison": tasks,
            "outcomes": outcomes}


def _group(root: Path, group: dict, events: list[dict], objective: dict) -> dict:
    agent_id, harness_id = group["agent_id"], group["harness_id"]
    key = f"{agent_id}/{harness_id}"
    group_events = [event for event in events if event.get("agent_id") == agent_id
                    and event.get("harness_id") == harness_id]
    evaluations = [_evaluation(key, event) for event in group_events
                   if event.get("event") == "trial_completed"]
    candidates = [_candidate(root, key, identifier)
                  for identifier in _candidate_ids(root, key, group, group_events)]
    candidates = [candidate for candidate in candidates if candidate is not None]
    comparison, overall = _comparison(group, objective)
    failures = [{"evaluation_ref": row["id"], **row["failure"]}
                for row in evaluations if row["failure"] is not None]
    structure = _structure(key, candidates, evaluations, group_events)
    return {"key": key, "agent_id": agent_id, "harness_id": harness_id,
            "baseline": group.get("baseline"), "selected": group.get("selected", []),
            "final_test": group.get("final_test", []), "stages": group.get("stages", []),
            "optimizer_usage": group.get("optimizer_usage", []), "status": group.get("status"),
            "agent_usage": _agent_usage(group, group_events),
            "candidates": candidates, "evaluations": evaluations, "failures": failures,
             "structure": structure,
             "visualization": _visualization(group, group_events, evaluations, objective),
             "comparison": comparison, "comparison_trend": overall,
            "counts": {"candidates": len(candidates), "trials_used": group.get("trials_used"),
                       **_evaluation_counts(evaluations)}}


def _counts(groups: list[dict], summary: dict) -> dict:
    return {"groups": len(groups), "trials_used": summary.get("trials_used"),
            "candidates": sum(group["counts"]["candidates"] for group in groups),
            **{name: sum(group["counts"][name] for group in groups) for name in (
                 "evaluations", "completed_evaluations", "passed_evaluations", "failed_evaluations")}}


def build_report(root: Path, summary: dict) -> dict:
    """집계와 선택은 그대로 두고 trial별 근거만 별도로 보존한다."""
    manifest = _read_json(safe_path(root, "manifest.json"), {})
    events = _read_events(root)
    experiment = manifest.get("experiment", {})
    objective = experiment.get("objective", {})
    groups = [_group(root, group, events, objective) for group in summary.get("groups", [])]
    identity = {name: summary.get(name) for name in ("run_id", "status", "synthetic")}
    elapsed = summary.get("run_wall_time_seconds")
    if _finite_number(elapsed) and elapsed >= 0:
        identity["run_wall_time_seconds"] = elapsed
    identity.update({name: summary[name] for name in ("error_type", "error") if name in summary})
    run_failure = _failure(summary.get("status"), error_type=summary.get("error_type"),
                           error=summary.get("error"))
    if run_failure is not None:
        identity["failure"] = run_failure
    return {"report_schema_version": 2,
            "identity": identity,
            "configuration": experiment, "provenance": manifest,
            "objective": objective,
            "counts": _counts(groups, summary), "groups": groups, "events": events}
