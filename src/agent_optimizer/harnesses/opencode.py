from __future__ import annotations

import json
import os
from pathlib import Path

from agent_optimizer.contracts import RunRequest, UnavailableError
from agent_optimizer.harnesses.command import CommandHarness


class OpenCodeHarness(CommandHarness):
    def argv(self, request: RunRequest) -> list[str]:
        model_env = request.profile.get("model_env", "AGENT_OPT_MODEL")
        model = os.environ.get(model_env)
        if not model:
            raise UnavailableError(f"Set {model_env} to a provider/model identifier")
        command = ["opencode", "run", "--format", "json", "--model", model]
        if request.profile.get("agent"):
            command += ["--agent", request.profile["agent"]]
        command += [request.prompt]
        return command

    def run(self, request: RunRequest):
        result = super().run(request)
        reported_tokens = 0.0
        reported_cost = 0.0
        saw_tokens = saw_cost = False
        invalid = 0
        with Path(result.stdout_path).open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    invalid += 1
                    continue
                if not isinstance(event, dict):
                    invalid += 1
                    continue
                if event.get("type") == "error":
                    result.status = "infrastructure_error"
                    result.detail = "OpenCode emitted an error event; see raw trace"
                if event.get("type") == "step_finish":
                    part = event.get("part", {})
                    tokens = part.get("tokens", {})
                    # Keep this explicitly partial: child sessions may not be in this stream.
                    if all(isinstance(tokens.get(k), (int, float)) for k in ("input", "output")):
                        reported_tokens += tokens["input"] + tokens["output"]
                        saw_tokens = True
                    if isinstance(part.get("cost"), (int, float)):
                        reported_cost += part["cost"]
                        saw_cost = True
        result.metrics.update(harness_reported_io_tokens=reported_tokens if saw_tokens else None,
                              harness_reported_cost_usd=reported_cost if saw_cost else None,
                              unparsed_event_lines=float(invalid))
        # Complete agent totals intentionally remain unavailable until child-session accounting
        # is verified for a pinned OpenCode version. Never report a partial total as complete.
        return result

