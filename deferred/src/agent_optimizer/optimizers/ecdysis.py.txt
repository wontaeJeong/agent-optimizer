"""Team implementation slot: ecdysis. No synthetic fallback."""
from agent_optimizer.contracts import UnavailableError

class Optimizer:
    def optimize(self, context, seeds, config):
        raise UnavailableError("ecdysis is not implemented; connect the team's algorithm here")
