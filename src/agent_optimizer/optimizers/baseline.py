from agent_optimizer.contracts import OptimizationResult


class BaselineOptimizer:
    def optimize(self, context, seeds, config):
        return OptimizationResult(list(seeds), {"kind": "no_op"})

