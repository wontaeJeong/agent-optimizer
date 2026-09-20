"""Team-owned integration slot, not a Meta-Harness algorithm implementation."""
from typing import Any

from agent_optimizer.contracts import (
    Candidate, OptimizationContext, OptimizationResult, UnavailableError,
)


class Optimizer:
    def optimize(
        self, context: OptimizationContext, seeds: list[Candidate], config: dict[str, Any]
    ) -> OptimizationResult:
        raise UnavailableError(
            "Team optimizer template is not implemented; supply team code using "
            "the train-only OptimizationContext contract (see experiments/optimizer-template/README.md)"
        )
