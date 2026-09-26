from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.contracts import ExecutionResult, RunRequest, UnavailableError
from agent_optimizer.harnesses.claude_code import ClaudeCodeHarness


SUCCESS = {"type": "result", "subtype": "success", "is_error": False,
           "usage": {"input_tokens": 12, "output_tokens": 3}, "total_cost_usd": 0.01}


class ClaudeCodeContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.logs = self.root / "logs"
        self.request = RunRequest(self.workspace, self.workspace / "agent", self.workspace / "task",
                                  "prompt ; $(ignored)", 5, 3, {"runtime": {"kind": "local"}}, self.logs)
        self.harness = ClaudeCodeHarness()

    def run_events(self, events, *, status="completed", returncode=0, version="2.1.261 (Claude Code)\n"):
        self.logs.mkdir(exist_ok=True)
        output, err = self.logs / "stdout.log", self.logs / "stderr.log"
        output.write_text("\n".join(json.dumps(event) if not isinstance(event, str) else event
                                    for event in events), encoding="utf-8")
        err.write_text("", encoding="utf-8")
        fixture = ExecutionResult(status, returncode, 0.1, str(output), str(err))
        with patch("agent_optimizer.harnesses.claude_code.subprocess.run",
                   return_value=subprocess.CompletedProcess(["claude", "--version"], 0, version, "")), \
             patch("agent_optimizer.harnesses.command.execute", return_value=fixture):
            return self.harness.run(self.request)

    def test_argv_keeps_prompt_separate_and_refuses_docker(self):
        self.assertEqual(self.harness.argv(self.request),
                         ["claude", "-p", self.request.prompt, "--output-format", "stream-json",
                          "--verbose", "--max-turns", "8", "--allowedTools", "Read,Write,Edit"])
        docker = RunRequest(self.workspace, self.request.agent_dir, self.request.task_dir,
                            self.request.prompt, 5, 3, {"runtime": {"kind": "docker"}}, self.logs)
        with self.assertRaises(UnavailableError):
            self.harness.argv(docker)
        with patch("agent_optimizer.harnesses.claude_code.subprocess.run") as version:
            with self.assertRaises(UnavailableError):
                self.harness.run(docker)
            version.assert_not_called()

    def test_success_records_only_partial_usage_and_observed_version(self):
        result = self.run_events([SUCCESS])
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.metrics["harness_reported_io_tokens"], 15)
        self.assertEqual(result.metrics["harness_reported_cost_usd"], 0.01)
        self.assertEqual(result.metrics["unparsed_event_lines"], 0)
        self.assertIsNone(result.metrics["agent_tokens"])
        self.assertIsNone(result.metrics["agent_cost_usd"])
        self.assertEqual((self.logs / "cli-version.txt").read_text(), "2.1.261\n")
        self.assertTrue((self.workspace / "request.json").exists())

    def test_missing_bad_or_ambiguous_result_is_infrastructure_error(self):
        cases = {
            "missing": [],
            "execution_error": [{**SUCCESS, "subtype": "error_during_execution"}],
            "is_error": [{**SUCCESS, "is_error": True, "result": "secret model output"}],
            "malformed": ['{"type":"result",', "not json"],
            "duplicate": [SUCCESS, SUCCESS],
            "model_error": [{"type": "error", "error": {"message": "private credential"}}, SUCCESS],
            "auth_error": [{"type": "auth_status", "error": "private credential"}, SUCCESS],
        }
        for label, events in cases.items():
            with self.subTest(label=label):
                result = self.run_events(events)
                self.assertEqual(result.status, "infrastructure_error")
                self.assertNotIn("secret model output", result.detail)
                self.assertNotIn("private credential", result.detail)
                if label == "malformed":
                    self.assertEqual(result.metrics["unparsed_event_lines"], 2)

    def test_bad_cost_and_incomplete_usage_remain_unreported(self):
        for cost in (-0.1, float("nan"), True, "0.01", 10**1000):
            with self.subTest(cost=cost):
                result = self.run_events([{**SUCCESS, "total_cost_usd": cost}])
                self.assertEqual(result.status, "completed")
                self.assertIsNone(result.metrics["harness_reported_cost_usd"])
        for usage in ({"input_tokens": 12}, {"input_tokens": -1, "output_tokens": 3},
                      {"input_tokens": True, "output_tokens": 3},
                      {"input_tokens": float("nan"), "output_tokens": 3}):
            with self.subTest(usage=usage):
                result = self.run_events([{**SUCCESS, "usage": usage}])
                self.assertEqual(result.status, "completed")
                self.assertIsNone(result.metrics["harness_reported_io_tokens"])

    def test_process_failure_stays_noncompleted_and_timeout_stays_timeout(self):
        for status, code in (("process_error", 1), ("timeout", -9), ("infrastructure_error", None)):
            with self.subTest(status=status):
                result = self.run_events([SUCCESS], status=status, returncode=code)
                self.assertNotEqual(result.status, "completed")
                self.assertEqual(result.status, "infrastructure_error" if status == "process_error" else status)

    def test_version_mismatch_and_failed_probe_are_nullable_infrastructure_results(self):
        self.request.profile["required_cli_version"] = "2.1.261"
        for version in (subprocess.CompletedProcess(["claude", "--version"], 0, "2.1.260 (Claude Code)\n", ""),
                        subprocess.CompletedProcess(["claude", "--version"], 1, "", "private credential"),
                        subprocess.CompletedProcess(["claude", "--version"], 0, "", "")):
            with self.subTest(version=version.returncode, stdout=version.stdout):
                with patch("agent_optimizer.harnesses.claude_code.subprocess.run", return_value=version), \
                     patch("agent_optimizer.harnesses.command.execute") as execute:
                    result = self.harness.run(self.request)
                execute.assert_not_called()
                self.assertEqual(result.status, "infrastructure_error")
                self.assertIsNone(result.returncode)
                self.assertNotIn("private credential", result.detail)
        self.assertFalse((self.logs / "cli-version.txt").exists())

    def test_missing_cli_and_version_timeout_are_infrastructure_errors(self):
        for failure in (FileNotFoundError("private credential"),
                        subprocess.TimeoutExpired(["claude", "--version"], 5, stderr=b"private credential")):
            with self.subTest(failure=type(failure).__name__):
                with patch("agent_optimizer.harnesses.claude_code.subprocess.run", side_effect=failure), \
                     patch("agent_optimizer.harnesses.command.execute") as execute:
                    result = self.harness.run(self.request)
                execute.assert_not_called()
                self.assertEqual(result.status, "infrastructure_error")
                self.assertNotIn("private credential", result.detail)

    def test_fake_cli_passes_through_real_process_execute(self):
        binary = self.root / "bin"
        binary.mkdir()
        fake = binary / "claude"
        fake.write_text("#!/usr/bin/env python3\n"
                        "import json, pathlib, sys\n"
                        "if sys.argv[1:] == ['--version']:\n"
                        "    print('2.1.261 (Claude Code)')\n"
                        "else:\n"
                        "    assert sys.argv[1:4] == ['-p', 'prompt ; $(ignored)', '--output-format']\n"
                        "    pathlib.Path('task/answer.txt').write_text('fixture result')\n"
                        f"    print(json.dumps({SUCCESS!r}))\n", encoding="utf-8")
        fake.chmod(0o755)
        self.request.task_dir.mkdir()
        self.request.profile["required_cli_version"] = "2.1.261"
        with patch.dict(os.environ, {"PATH": str(binary) + os.pathsep + os.environ.get("PATH", "")}):
            result = self.harness.run(self.request)
        self.assertEqual(result.status, "completed", result.detail)
        self.assertEqual(result.metrics["harness_reported_io_tokens"], 15)
        self.assertEqual(result.metrics["harness_reported_cost_usd"], 0.01)
        self.assertEqual((self.request.task_dir / "answer.txt").read_text(), "fixture result")
        self.assertEqual((self.logs / "cli-version.txt").read_text(), "2.1.261\n")


if __name__ == "__main__":
    unittest.main()
