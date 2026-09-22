from __future__ import annotations

import math
from typing import Any

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.config import validate_objective


def select(rows: list[dict[str, Any]], objective: dict) -> list[dict[str, Any]]:
    validate_objective(objective)
    metrics = objective["metrics"]
    eligible = []
    for row in rows:
        if row.get("valid") is False or row.get("partial", False):
            continue
        values = row["metrics"]
        keys = [m["name"] for m in metrics]
        if any(values.get(k) is None or not math.isfinite(values[k]) for k in keys):
            continue
        vector = tuple(values[m["name"]] * (1 if m["direction"] == "maximize" else -1)
                       for m in metrics)
        eligible.append((row, vector))
    return [row for row, _ in sorted(eligible, key=lambda item: item[1], reverse=True)[:1]]


def aggregate(records: list[dict], metric_specs: list[dict]) -> dict[str, float | None]:
    result = {}
    for spec in metric_specs:
        op = spec.get("aggregate", "mean")
        if op not in {"mean", "sum"}:
            raise ConfigurationError("Advanced metric aggregates are deferred; use mean or sum")
        name, source = spec["name"], spec.get("source", spec["name"])
        values = [r["metrics"].get(source) for r in records]
        if not values or any(v is None or not math.isfinite(v) for v in values):
            result[name] = None
            continue
        if op == "mean":
            result[name] = sum(values) / len(values)
        else:
            result[name] = sum(values)
    return result
