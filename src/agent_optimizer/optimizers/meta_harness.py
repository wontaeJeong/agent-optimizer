"""Isolated runtime-harness scaffold evolution against fixed Agent tasks."""
from __future__ import annotations

import ast
import math

from agent_optimizer.config import only_keys, positive
from agent_optimizer.contracts import ConfigurationError, OptimizationResult, UnavailableError
from agent_optimizer.optimizers.research import propose_text
from agent_optimizer.workspace import safe_path


def _score(view: dict, metric: str) -> float:
    if not view["valid"]:
        raise UnavailableError("Meta-Harness requires valid validation tasks")
    values = [task["metrics"].get(metric) for task in view["tasks"]]
    if not values or any(type(value) not in (int, float) or not math.isfinite(value)
                         for value in values):
        raise UnavailableError(f"Meta-Harness requires finite per-task {metric} scores")
    return sum(values) / len(values)


class MetaHarnessOptimizer:
    def optimize(self, context, seeds, config) -> OptimizationResult:
        only_keys(config, {"file", "iterations", "metric", "request_timeout_seconds",
                           "required_symbol"}, "Meta-Harness optimizer")
        filename = config.get("file")
        if len(seeds) != 1 or not isinstance(filename, str) or not filename.endswith(".py"):
            raise ConfigurationError("Meta-Harness requires one seed and an editable .py harness file")
        iterations = config.get("iterations", 3)
        if type(iterations) is not int or not 1 <= iterations <= 100:
            raise ConfigurationError("Meta-Harness iterations must be an integer from 1 to 100")
        timeout = config.get("request_timeout_seconds", 60)
        positive(timeout, "Meta-Harness request timeout")
        required = config.get("required_symbol")
        if required is not None and (not isinstance(required, str) or not required.isidentifier()):
            raise ConfigurationError("Meta-Harness required_symbol must be a Python identifier")
        metric = config.get("metric", "passed")
        current = seeds[0]
        context.evaluate(current)
        best = _score(context.evaluate_validation(current), metric)
        records = []
        for iteration in range(1, iterations + 1):
            context.emit("optimizer_iteration_started", iteration=iteration, total=iterations,
                         candidate_id=current.id)
            evidence = [{"task_id": record["task_id"], "status": record["status"],
                         "metrics": record["metrics"], "feedback": record.get("feedback", "")[:2000]}
                        for record in context.history() if record["candidate_id"] == current.id]
            candidate = propose_text(
                context, current, filename, evidence,
                "Meta-Harness: evolve the runtime scaffold around the fixed task model. "
                "Keep its public execution interface compatible; use the training traces to fix "
                "general failure modes rather than embedding answers.", timeout)
            try:
                tree = ast.parse(safe_path(candidate.path, filename).read_text(encoding="utf-8"))
                if required and not any(isinstance(node, (ast.ClassDef, ast.FunctionDef,
                                                           ast.AsyncFunctionDef)) and node.name == required
                                        for node in tree.body):
                    raise SyntaxError("Required harness symbol missing")
                compile(tree, filename, "exec")
            except (SyntaxError, ValueError):
                records.append({"iteration": iteration, "candidate_id": candidate.id,
                                "status": "invalid_interface", "accepted": False})
                context.emit("optimizer_iteration_completed", iteration=iteration, total=iterations,
                             candidate_id=candidate.id, status="invalid_interface")
                continue
            context.evaluate(candidate)
            score = _score(context.evaluate_validation(candidate), metric)
            accepted = score > best
            if accepted:
                current, best = candidate, score
            records.append({"iteration": iteration, "candidate_id": candidate.id,
                            "status": "accepted" if accepted else "rejected", "accepted": accepted,
                            "validation_score": score})
            context.emit("optimizer_iteration_completed", iteration=iteration, total=iterations,
                         candidate_id=candidate.id, accepted=accepted)
        return OptimizationResult([current], {"iterations": records, "frontier": [current.id],
                                              "validation_score": best})
