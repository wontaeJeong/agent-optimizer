"""Cross-task failure evidence, collaborative review and strict train acceptance."""
from __future__ import annotations

import ast
import math

from agent_optimizer.config import only_keys, positive
from agent_optimizer.contracts import ConfigurationError, OptimizationResult, UnavailableError
from agent_optimizer.optimizers.research import propose_text, review_spec
from agent_optimizer.workspace import safe_path


def group_failures(records: list[dict], *, threshold: float, metric: str,
                   direction: str = "maximize") -> list[dict]:
    grouped = {}
    for record in records:
        value = record["metrics"].get(metric)
        if not record.get("valid", True) or type(value) not in (int, float) or not math.isfinite(value):
            raise UnavailableError(f"Ecdysis needs valid per-task {metric} scores")
        if ((direction == "maximize" and value >= threshold)
                or (direction == "minimize" and value <= threshold)):
            continue
        pattern = f"{record['status']}:{metric}"
        group = grouped.setdefault(pattern, {"pattern": pattern, "task_ids": set(), "examples": [],
                                             "failure_count": 0})
        group["task_ids"].add(record["task_id"])
        group["failure_count"] += 1
        if len(group["examples"]) < 8:
            group["examples"].append({"task_id": record["task_id"],
                                      "feedback": str(record.get("feedback", ""))[:2000]})
    return sorted(({**group, "task_ids": sorted(group["task_ids"]),
                    "distinct_tasks": len(group["task_ids"])} for group in grouped.values()),
                  key=lambda group: (-group["distinct_tasks"], -group["failure_count"], group["pattern"]))


def _train_score(row: dict, metric: str, direction: str = "maximize") -> float:
    value = row.get("metrics", {}).get(metric)
    if not row.get("valid") or type(value) not in (int, float) or not math.isfinite(value):
        raise UnavailableError(f"Ecdysis requires a valid finite train {metric} score")
    return float(value) * (1 if direction == "maximize" else -1)


class EcdysisOptimizer:
    def optimize(self, context, seeds, config) -> OptimizationResult:
        only_keys(config, {"file", "rounds", "refinement_passes", "failure_threshold",
                           "failure_metric", "score_metric", "request_timeout_seconds",
                           "direction"}, "Ecdysis optimizer")
        filename = config.get("file")
        if len(seeds) != 1 or not isinstance(filename, str) or not filename.endswith(".py"):
            raise ConfigurationError("Ecdysis requires one seed and an editable .py harness file")
        rounds = config.get("rounds", 3)
        passes = config.get("refinement_passes", 2)
        if type(rounds) is not int or not 1 <= rounds <= 100:
            raise ConfigurationError("Ecdysis rounds must be an integer from 1 to 100")
        if type(passes) is not int or not 1 <= passes <= 8:
            raise ConfigurationError("Ecdysis refinement_passes must be an integer from 1 to 8")
        threshold = config.get("failure_threshold", 1.0)
        if type(threshold) not in (int, float) or not math.isfinite(threshold):
            raise ConfigurationError("Ecdysis failure_threshold must be finite")
        timeout = config.get("request_timeout_seconds", 60)
        positive(timeout, "Ecdysis request timeout")
        failure_metric = config.get("failure_metric", "passed")
        score_metric = config.get("score_metric", "solve_rate")
        direction = config.get("direction", "maximize")
        if direction not in {"maximize", "minimize"}:
            raise ConfigurationError("Ecdysis direction must be maximize or minimize")
        current = seeds[0]
        current_score = _train_score(context.evaluate(current), score_metric, direction)
        history = []
        for round_number in range(1, rounds + 1):
            context.emit("optimizer_iteration_started", iteration=round_number, total=rounds,
                         candidate_id=current.id)
            records = [r for r in context.history() if r["candidate_id"] == current.id]
            groups = group_failures(records, threshold=threshold, metric=failure_metric,
                                    direction=direction)
            if not groups:
                history.append({"round": round_number, "status": "no_failures", "groups": [],
                                "accepted": False, "retained_score": current_score})
                context.emit("optimizer_iteration_completed", iteration=round_number, total=rounds,
                             status="no_failures", candidate_id=current.id)
                continue
            specification = ""
            for number in range(passes):
                role = "analyst" if number == 0 else "moderator" if number == passes - 1 else "critic"
                context.emit("optimizer_review_started", iteration=round_number,
                             pass_number=number + 1, role=role)
                specification = review_spec(context, groups, specification, role, timeout)
            candidate = propose_text(context, current, filename,
                                     {"groups": groups, "specification": specification},
                                     "Ecdysis editor: implement the reviewed cross-task failure repair in "
                                     "the runtime harness. Preserve its interface and avoid one-task accommodations.",
                                     timeout)
            try:
                tree = ast.parse(safe_path(candidate.path, filename).read_text(encoding="utf-8"))
                compile(tree, filename, "exec")
            except SyntaxError:
                history.append({"round": round_number, "candidate_id": candidate.id,
                                "groups": groups, "specification": specification,
                                "status": "invalid_interface", "accepted": False,
                                "retained_score": current_score})
                continue
            candidate_score = _train_score(context.evaluate(candidate), score_metric, direction)
            accepted = candidate_score > current_score
            if accepted:
                current, current_score = candidate, candidate_score
            history.append({"round": round_number, "candidate_id": candidate.id,
                            "groups": groups, "specification": specification,
                            "candidate_score": candidate_score, "retained_score": current_score,
                            "status": "accepted" if accepted else "rejected", "accepted": accepted})
            context.emit("optimizer_iteration_completed", iteration=round_number, total=rounds,
                         candidate_id=candidate.id, accepted=accepted)
        return OptimizationResult([current], {"rounds": history,
                                              "retained_candidate": current.id,
                                              "retained_train_score": (current_score if direction == "maximize"
                                                                       else -current_score)})
