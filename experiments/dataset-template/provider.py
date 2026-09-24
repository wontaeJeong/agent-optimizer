"""Copy this file to experiments/<team>/ and implement dataset preparation."""
from agent_optimizer.contracts import UnavailableError


class Provider:
    def describe(self):
        return {"name": "team_dataset", "task_form": "custom", "evaluator": "team_evaluator"}

    def prepare(self, cache, *, offline=False):
        raise UnavailableError(
            "team_dataset requires a real importer and evaluator before it can be prepared"
        )

    def doctor(self, cache):
        # Replace with read-only checks of verified local sources, hashes and evaluator runtime.
        return [{"id": "dataset.team_dataset.assets", "area": "dataset", "status": "error",
                 "message": "Team dataset preparation is not implemented",
                 "remedy": "Implement and verify team_dataset preparation and its evaluator"}]
