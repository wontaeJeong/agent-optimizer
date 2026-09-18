from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from agent_optimizer.contracts import ExecutionResult, RunRequest, UnavailableError
from agent_optimizer.process import execute


class CommandHarness:
    def argv(self, request: RunRequest) -> list[str]:
        docker = request.profile.get("runtime", {}).get("kind") == "docker"
        base = Path("/work") if docker else request.workspace
        values = {"python": "python3" if docker else sys.executable,
                  "agent_dir": str(base / "agent"), "task_dir": str(base / "task"),
                  "request_file": str(base / "request.json"), "seed": str(request.seed)}
        command = request.profile.get("command", [])
        if not command:
            raise UnavailableError("command adapter requires an argv list")
        # Deliberately no shell. Only replace documented literal placeholders.
        for key, value in values.items():
            command = [arg.replace("{" + key + "}", value) for arg in command]
        return command

    def run(self, request: RunRequest) -> ExecutionResult:
        (request.workspace / "request.json").write_text(json.dumps({
            "schema_version": 1, "prompt": request.prompt, "seed": request.seed,
            "task_dir": "task", "agent_dir": "agent",
        }), encoding="utf-8")
        result = execute(self.argv(request), request.workspace, request.logs,
                         request.timeout_seconds, request.profile.get("runtime", {}))
        result.metrics.update(agent_tokens=None, agent_cost_usd=None)
        return result


class FixtureHarness(CommandHarness):
    """Executes an explicitly synthetic deterministic agent for infrastructure tests."""

    def argv(self, request: RunRequest) -> list[str]:
        return [sys.executable, str(request.agent_dir / "src" / "fixture_agent.py"),
                str(request.task_dir)]

