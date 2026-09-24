"""Example command adapter that reports its own observed integration metric."""
from agent_optimizer.harnesses.command import CommandHarness


class Harness(CommandHarness):
    def run(self, request):
        result = super().run(request)
        result.metrics["sample_adapter"] = 1.0
        return result
