from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.contracts import ExecutionResult, RunRequest
from support import IcarusVerilog
from agent_optimizer.harnesses.opencode import OpenCodeHarness
from agent_optimizer.process import execute, run_process


class ProcessTests(unittest.TestCase):
    def test_process_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_process([sys.executable, "-c", "import time; time.sleep(10)"], root, root / "logs", 0.05)
            self.assertEqual(result.status, "timeout")
            self.assertLess(result.wall_time_seconds, 2)

    def test_argv_is_not_interpreted_by_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arg = "$(touch injected); echo hello"
            result = run_process([sys.executable, "-c", "import sys; print(sys.argv[1])", arg], root, root / "logs", 5)
            self.assertEqual(Path(result.stdout_path).read_text().strip(), arg)
            self.assertFalse((root / "injected").exists())

    def test_missing_executable_is_infrastructure_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_process(["/nonexistent/agent-opt-test"], root, root / "logs", 1)
            self.assertEqual(result.status, "infrastructure_error")

    def test_docker_mount_and_cleanup_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = ExecutionResult("process_error", 125, 0, "stdout", "stderr")
            with patch("agent_optimizer.process.run_process", return_value=result) as run, \
                 patch("agent_optimizer.process.subprocess.run") as cleanup:
                output = execute(["agent"], root, root / "logs", 1, {"kind": "docker", "image": "example:tag"})
            argv = run.call_args.args[0]
            self.assertEqual(argv.count("--mount"), 1)
            self.assertNotIn("docker.sock", " ".join(argv))
            self.assertIn("--cap-drop=ALL", argv)
            self.assertEqual(output.status, "infrastructure_error")
            cleanup.assert_called_once()


class OpenCodeContractTests(unittest.TestCase):
    def test_argv_usage_and_error_event(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, err = root / "out.jsonl", root / "err.log"
            output.write_text('\n'.join(json.dumps(x) for x in [
                {"type": "step_finish", "part": {"tokens": {"input": 12, "output": 3}, "cost": 0.01}},
                {"type": "error", "error": {"message": "test provider failure"}},
            ]))
            err.write_text("")
            profile = {"adapter": "opencode", "agent": "rtl", "model_env": "TEST_AGENT_MODEL"}
            request = RunRequest(root, root / "agent", root / "task", "prompt ; $(ignored)", 5, 3, profile, root / "logs")
            harness = OpenCodeHarness()
            with patch.dict(os.environ, {"TEST_AGENT_MODEL": "provider/model"}):
                argv = harness.argv(request)
                self.assertEqual(argv[-1], request.prompt)
                self.assertIn("json", argv)
                fixture = ExecutionResult("completed", 0, 0.1, str(output), str(err))
                with patch("agent_optimizer.harnesses.command.execute", return_value=fixture):
                    result = harness.run(request)
            self.assertEqual(result.status, "infrastructure_error")
            self.assertEqual(result.metrics["harness_reported_io_tokens"], 15)
            self.assertIsNone(result.metrics["agent_tokens"])


class IcarusContractTests(unittest.TestCase):
    def test_fake_tool_success_requires_test_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dut.sv").write_text("module dut; endmodule")
            stdout, stderr = root / "out", root / "err"
            stdout.write_text("TEST_PASS\n")
            stderr.write_text("")
            fixture = ExecutionResult("completed", 0, 0.01, str(stdout), str(stderr))
            with patch("example_iverilog.execute", return_value=fixture):
                result = IcarusVerilog().run(root, {"sources": ["dut.sv"]}, 10)
                self.assertEqual(result.status, "passed")
                stdout.write_text("normal exit, no verification marker")
                result = IcarusVerilog().run(root, {"sources": ["dut.sv"]}, 10)
                self.assertEqual(result.status, "failed")

    @unittest.skipUnless(shutil.which("iverilog") and shutil.which("vvp"), "Icarus binaries not installed")
    def test_real_iverilog_smoke(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tb.sv").write_text('module tb; initial begin $display("TEST_PASS"); $finish; end endmodule')
            result = IcarusVerilog().run(root, {"sources": ["tb.sv"], "top": "tb"}, 10)
            self.assertEqual(result.status, "passed")


if __name__ == "__main__":
    unittest.main()

