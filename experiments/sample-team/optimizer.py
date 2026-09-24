"""Explicitly synthetic no-op optimizer for wiring tests, not a search method."""
from agent_optimizer.contracts import OptimizationResult


class Optimizer:
    def optimize(self, context, seeds, config):
        return OptimizationResult(list(seeds), {"kind": "synthetic_example"})
