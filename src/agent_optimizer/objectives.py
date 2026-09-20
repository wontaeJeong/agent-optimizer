from __future__ import annotations

import math
from typing import Any

from agent_optimizer.contracts import ConfigurationError


def select(rows: list[dict[str, Any]], objective: dict) -> list[dict[str, Any]]:
    mode = objective.get("mode", "lexicographic")
    if mode == "pareto" and "keep" in objective:
        raise ConfigurationError("Pareto returns the whole frontier; objective.keep is not supported")
    metrics = objective["metrics"]
    eligible = []
    for row in rows:
        if row.get("valid") is False or row.get("partial", False):
            continue
        values = row["metrics"]
        keys = [m["name"] for m in metrics] + [c["metric"] for c in objective.get("constraints", [])]
        if any(values.get(k) is None or not math.isfinite(values[k]) for k in keys):
            continue
        if any(("min" in c and values[c["metric"]] < c["min"]) or
               ("max" in c and values[c["metric"]] > c["max"])
               for c in objective.get("constraints", [])):
            continue
        vector = tuple(values[m["name"]] * (1 if m["direction"] == "maximize" else -1)
                       for m in metrics)
        eligible.append((row, vector))
    if mode == "pareto":
        return [row for i, (row, vec) in enumerate(eligible)
                if not any(i != j and all(a >= b for a, b in zip(other, vec))
                           and any(a > b for a, b in zip(other, vec))
                           for j, (_, other) in enumerate(eligible))]
    if mode == "weighted":
        def key(item):
            return sum(v * m.get("weight", 1) / m.get("scale", 1)
                       for v, m in zip(item[1], metrics))
    elif mode == "lexicographic":
        def key(item):
            return item[1]
    else:
        raise ConfigurationError(f"Unknown objective mode: {mode}")
    return [r for r, _ in sorted(eligible, key=key, reverse=True)[:objective.get("keep", 1)]]


def aggregate(records: list[dict], metric_specs: list[dict]) -> dict[str, float | None]:
    result = {}
    for spec in metric_specs:
        name, source = spec["name"], spec.get("source", spec["name"])
        values = [r["metrics"].get(source) for r in records]
        if not values or any(v is None or not math.isfinite(v) for v in values):
            result[name] = None
            continue
        op = spec.get("aggregate", "mean")
        if op == "mean":
            result[name] = sum(values) / len(values)
        elif op == "sum":
            result[name] = sum(values)
        elif op == "max":
            result[name] = max(values)
        elif op == "p95":
            result[name] = sorted(values)[math.ceil(0.95 * len(values)) - 1]
        else:
            raise ConfigurationError(f"Unknown aggregation: {op}")
    return result
