"""Team implementation slot: gepa. No synthetic fallback."""
from agent_optimizer.contracts import UnavailableError

class Optimizer:
    def optimize(self, context, seeds, config):
        raise UnavailableError("gepa is not implemented; connect the team's algorithm here")
