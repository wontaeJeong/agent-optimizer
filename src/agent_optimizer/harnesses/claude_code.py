from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

from agent_optimizer.contracts import ExecutionResult, RunRequest, UnavailableError
from agent_optimizer.harnesses.command import CommandHarness


class ClaudeCodeHarness(CommandHarness):
    def argv(self, request: RunRequest) -> list[str]:
        if request.profile.get("runtime", {}).get("kind", "local") != "local":
            raise UnavailableError("claude_code requires a local runtime")
        return ["claude", "-p", request.prompt, "--output-format", "stream-json",
                "--verbose", "--max-turns", "8", "--strict-mcp-config",
                "--tools", "Read,Write,Edit", "--allowedTools", "Read,Write,Edit"]

    def run(self, request: RunRequest) -> ExecutionResult:
        # Reject unsupported runtimes before probing a host CLI.
        self.argv(request)
        request.logs.mkdir(parents=True, exist_ok=True)

        def unavailable(detail: str) -> ExecutionResult:
            return ExecutionResult("infrastructure_error", None, 0.0,
                                   str(request.logs / "stdout.log"), str(request.logs / "stderr.log"),
                                   {"agent_tokens": None, "agent_cost_usd": None,
                                    "harness_reported_io_tokens": None,
                                    "harness_reported_cost_usd": None}, detail)

        try:
            version = subprocess.run(["claude", "--version"], capture_output=True,
                                     text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return unavailable("Claude Code CLI version unavailable; check installation")

        observed = version.stdout.strip().split(" ", 1)[0]
        if version.returncode or not observed or (request.profile.get("required_cli_version")
                                                   and request.profile["required_cli_version"] != observed):
            return unavailable("Claude Code CLI version unavailable or mismatched")
        (request.logs / "cli-version.txt").write_text(observed + "\n", encoding="utf-8")

        result = super().run(request)
        if result.status != "completed":
            if result.status != "timeout":
                result.status = "infrastructure_error"
                result.detail = "Claude Code process failed; see raw trace"

        finals: list[dict] = []
        invalid = 0
        saw_error = False
        try:
            with Path(result.stdout_path).open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        invalid += 1
                        continue
                    if not isinstance(event, dict):
                        invalid += 1
                    elif event.get("type") == "result":
                        finals.append(event)
                    elif event.get("type") == "error" or (event.get("type") == "auth_status" and event.get("error")):
                        saw_error = True
        except OSError:
            result.status = "infrastructure_error"
            result.detail = "Claude Code trace unavailable"

        final = finals[0] if len(finals) == 1 else {}
        usage = final.get("usage") if isinstance(final.get("usage"), dict) else {}
        tokens = [usage.get(key) for key in ("input_tokens", "output_tokens")]
        valid_tokens = all(type(value) is int and value >= 0 for value in tokens)
        cost = final.get("total_cost_usd")
        try:
            valid_cost = type(cost) in (int, float) and math.isfinite(cost) and cost >= 0
        except OverflowError:
            valid_cost = False
        result.metrics.update(harness_reported_io_tokens=sum(tokens) if valid_tokens else None,
                              harness_reported_cost_usd=cost if valid_cost else None,
                              unparsed_event_lines=float(invalid))
        if (not invalid and not saw_error and final.get("subtype") == "error_max_turns"
                and final.get("is_error") is True and result.returncode is not None
                and result.status in {"completed", "infrastructure_error"}):
            result.status = "agent_incomplete"
            result.detail = "Claude Code reached its turn limit before completing the task"
        if result.status == "completed" and (invalid or not final or final.get("subtype") != "success"
                                              or final.get("is_error") is not False or saw_error):
            result.status = "infrastructure_error"
            result.detail = "Claude Code did not emit a successful result; see raw trace"
        return result
