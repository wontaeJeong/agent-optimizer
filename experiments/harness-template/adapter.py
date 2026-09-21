"""Copy to a team-owned plugin and implement the selected CLI's actual contract."""
from agent_optimizer.contracts import RunRequest, ExecutionResult, UnavailableError


class Harness:
    def run(self, request: RunRequest) -> ExecutionResult:
        raise UnavailableError("Team Harness is not implemented; connect argv, authentication and result parsing")
