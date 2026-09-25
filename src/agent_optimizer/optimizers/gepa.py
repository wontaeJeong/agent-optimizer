"""Reflective text evolution with per-task validation Pareto selection."""
from __future__ import annotations

import math
import random

from agent_optimizer.config import only_keys, positive
from agent_optimizer.contracts import ConfigurationError, OptimizationResult, UnavailableError
from agent_optimizer.optimizers.research import propose_text


def dominates(left: tuple[float, ...], right: tuple[float, ...]) -> bool:
    return all(a >= b for a, b in zip(left, right)) and any(a > b for a, b in zip(left, right))


def vector(view: dict, metric: str, direction: str) -> tuple[float, ...]:
    if not view["valid"]:
        raise UnavailableError("GEPA requires valid validation tasks")
    scores = []
    for row in sorted(view["tasks"], key=lambda task: task["task_id"]):
        value = row["metrics"].get(metric)
        if not row["valid"] or type(value) not in (float, int) or not math.isfinite(value):
            raise UnavailableError(f"GEPA requires a finite per-task {metric} score")
        scores.append(float(value) * (1 if direction == "maximize" else -1))
    return tuple(scores)


class GEPAOptimizer:
    def optimize(self, context, seeds, config) -> OptimizationResult:
        only_keys(config, {"file", "iterations", "request_timeout_seconds", "metric", "direction",
                           "merge", "batch_size", "seed"}, "GEPA optimizer")
        if config.get("merge", False) is not False:
            raise UnavailableError("GEPA merge는 보류 중입니다: validation 수치를 모델 수정 근거로 전달하지 않도록 재설계가 필요합니다")
        if len(seeds) != 1 or not config.get("file"):
            raise ConfigurationError("GEPA requires one seed and an editable file")
        iterations = config.get("iterations", 3)
        if type(iterations) is not int or not 1 <= iterations <= 100:
            raise ConfigurationError("GEPA iterations must be an integer from 1 to 100")
        timeout = config.get("request_timeout_seconds", 60)
        positive(timeout, "GEPA request timeout")
        direction = config.get("direction", "maximize")
        if direction not in {"maximize", "minimize"}:
            raise ConfigurationError("GEPA direction must be maximize or minimize")
        metric = config.get("metric", "passed")
        batch_size = config.get("batch_size", 4)
        if type(batch_size) is not int or batch_size < 1:
            raise ConfigurationError("GEPA batch_size must be a positive integer")
        seed_value = config.get("seed", 0)
        if type(seed_value) is not int or seed_value < 0:
            raise ConfigurationError("GEPA seed must be a nonnegative integer")
        rng = random.Random(seed_value)
        seed = seeds[0]
        context.evaluate(seed)
        train_ids = context.train_task_ids()
        frontier = [(seed, vector(context.evaluate_validation(seed), metric, direction))]
        records = []
        for iteration in range(1, iterations + 1):
            parent = frontier[(iteration - 1) % len(frontier)][0]
            context.emit("optimizer_iteration_started", iteration=iteration, total=iterations,
                         candidate_id=parent.id)
            evidence = [{"task_id": row["task_id"], "metrics": row["metrics"],
                         "feedback": row.get("feedback", "")[:2000]}
                        for row in context.history() if row["candidate_id"] == parent.id]
            candidate = propose_text(
                context, parent, config["file"], evidence,
                "GEPA reflection: diagnose recurring errors in the training traces, then mutate "
                "the textual Agent parameter without copying task-specific answers.", timeout)
            batch = rng.sample(train_ids, min(batch_size, len(train_ids)))
            context.evaluate_batch(candidate, batch)
            score = vector(context.evaluate_validation(candidate), metric, direction)
            accepted = not any(dominates(existing, score) or existing == score
                               for _, existing in frontier)
            if accepted:
                frontier = [(item, existing) for item, existing in frontier
                            if not dominates(score, existing)]
                frontier.append((candidate, score))
            records.append({"iteration": iteration, "candidate_id": candidate.id,
                            "parent": parent.id, "accepted": accepted, "validation": score,
                            "train_batch": batch})
            context.emit("optimizer_iteration_completed", iteration=iteration, total=iterations,
                         candidate_id=candidate.id, accepted=accepted)
        merges = []
        if config.get("merge", False) and len(frontier) >= 2:
            first, second = sorted(frontier, key=lambda pair: (-sum(pair[1]), pair[0].id))[:2]
            parent, first_scores = first
            other, second_scores = second
            context.emit("optimizer_merge_started", parents=[parent.id, other.id])
            merged = propose_text(
                context, parent, config["file"],
                {"second_file": (other.path / config["file"]).read_text(encoding="utf-8")[:32000],
                 "first_scores": first_scores, "second_scores": second_scores},
                "GEPA merge: combine complementary validation strengths from the two distinct "
                "candidates into one generalizable text parameter.", timeout)
            batch = rng.sample(train_ids, min(batch_size, len(train_ids)))
            context.evaluate_batch(merged, batch)
            score = vector(context.evaluate_validation(merged), metric, direction)
            accepted = not any(dominates(existing, score) or existing == score
                               for _, existing in frontier)
            if accepted:
                frontier = [(item, existing) for item, existing in frontier
                            if not dominates(score, existing)]
                frontier.append((merged, score))
            merges.append({"candidate_id": merged.id, "parents": [parent.id, other.id],
                           "accepted": accepted, "validation": score})
            context.emit("optimizer_merge_completed", candidate_id=merged.id,
                         parents=[parent.id, other.id], accepted=accepted)
        return OptimizationResult([item for item, _ in frontier],
                                  {"iterations": records, "merges": merges,
                                   "frontier": [item.id for item, _ in frontier]})
