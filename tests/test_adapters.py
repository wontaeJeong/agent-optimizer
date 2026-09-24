from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.contracts import ExecutionResult, RunRequest
from agent_optimizer.harnesses.opencode import OpenCodeHarness
from agent_optimizer.process import execute, run_process
from agent_optimizer.config import load_experiment
from support import ROOT


class ProcessTests(unittest.TestCase):
    def test_passthrough_omits_absent_but_keeps_empty_and_present_values_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            runtime = {"kind": "docker", "image": "example:tag",
                       "env_passthrough": ["OPTIONAL_ABSENT", "PRESENT", "EMPTY"]}
            fixture = ExecutionResult("completed", 0, 0, "stdout", "stderr")
            with patch.dict(os.environ, {"PRESENT": "fixture-private-value", "EMPTY": ""}, clear=True), \
                    patch("agent_optimizer.process.run_process", return_value=fixture) as run, \
                    patch("agent_optimizer.process.subprocess.run"):
                execute(["agent"], root, root / "logs", 1, runtime)
            argv = run.call_args.args[0]
            forwarded = [argv[i + 1] for i, arg in enumerate(argv[:-1]) if arg == "--env"]
            self.assertNotIn("OPTIONAL_ABSENT", forwarded)
            self.assertIn("PRESENT", forwarded)
            self.assertIn("EMPTY", forwarded)
            self.assertNotIn("fixture-private-value", " ".join(argv))
            self.assertNotIn("EMPTY=", forwarded)

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


@unittest.skipUnless(os.environ.get("AGENT_OPT_TEST_DOCKER_IMAGE"),
                     "Set AGENT_OPT_TEST_DOCKER_IMAGE to an existing OpenCode image")
class DockerEnvironmentTests(unittest.TestCase):
    def test_image_default_survives_absence_and_explicit_compatible_override_wins(self):
        # Retain real config results without mounting host config/credentials or using a model.
        root = ROOT / "runs" / ("docker-env-regression-" + uuid.uuid4().hex[:12])
        root.mkdir(parents=True)
        runtime = load_experiment(ROOT / "examples/rtl-debugger/experiment.toml")["_profiles"][0]["runtime"].copy()
        runtime.update(image=os.environ["AGENT_OPT_TEST_DOCKER_IMAGE"], network="none")
        overlay = (ROOT / "examples/rtl-debugger/agent/overlays/opencode/opencode.json").read_text()
        for provider in ("openrouter", "compatible"):
            with self.subTest(provider=provider):
                work = root / provider
                (work / "agent").mkdir(parents=True)
                (work / "opencode.json").write_text(overlay)
                (work / "agent/provider-compatible.json").write_text(
                    (ROOT / "examples/ace-rtl/environment/openai-compatible.json").read_text())
                model = "openrouter/vendor/model:free" if provider == "openrouter" else "compatible/example-model"
                with patch.dict(os.environ, {"AGENT_OPT_MODEL": model}):
                    for key in ("OPENCODE_CONFIG", "OPENROUTER_API_KEY", "AGENT_OPT_MODEL_API_KEY", "AGENT_OPT_MODEL_ID", "AGENT_OPT_MODEL_BASE_URL"):
                        os.environ.pop(key, None)
                    if provider == "compatible":
                        os.environ.update(OPENCODE_CONFIG="/work/agent/provider-compatible.json",
                                          AGENT_OPT_MODEL_ID="example-model", AGENT_OPT_MODEL_BASE_URL="http://example.invalid/v1")
                    else:
                        self.assertNotIn("OPENCODE_CONFIG", os.environ)
                    result = execute(["opencode", "debug", "config"], work, work / "logs", 60, runtime)
                self.assertEqual(result.returncode, 0, Path(result.stderr_path).read_text())
                config = json.loads(Path(result.stdout_path).read_text())
                self.assertEqual(config.get("model"), model)
                self.assertEqual(config.get("small_model"), model)
                self.assertEqual(config.get("enabled_providers"), [provider])
                self.assertEqual(config["provider"][provider]["options"]["apiKey"], "")
                self.assertEqual(config["agent"]["rtl"]["mode"], "primary")
        # Deliberately empty host values must override image values, not be treated as absent.
        with patch.dict(os.environ, {"OPENCODE_CONFIG": ""}):
            result = execute(["python3", "-c", "import os; print(repr(os.environ.get('OPENCODE_CONFIG')))"],
                             root, root / "empty-value-logs", 30, runtime)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(Path(result.stdout_path).read_text().strip(), "''")
        print(f"Docker environment evidence: {root}")


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


if __name__ == "__main__":
    unittest.main()
