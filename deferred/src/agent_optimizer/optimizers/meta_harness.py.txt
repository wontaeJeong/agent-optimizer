"""Team implementation slot: meta_harness. No synthetic fallback."""
from agent_optimizer.contracts import UnavailableError

class Optimizer:
    def optimize(self, context, seeds, config):
        raise UnavailableError("meta_harness is not implemented; connect the team's algorithm here")
