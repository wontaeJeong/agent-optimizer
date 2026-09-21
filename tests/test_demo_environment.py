import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.network import demo_environment
from support import ROOT, module

setup = module("demo_setup", ROOT / "examples/ace-rtl/environment/setup.py")
checks = module("demo_model_checks", ROOT / "examples/ace-rtl/environment/model_checks.py")
doctor = module("demo_merged_doctor", ROOT / "scripts/dev_doctor.py")


class DemoEnvironmentTests(unittest.TestCase):
    def test_live_accepts_configured_model_and_refuses_missing_endpoint(self):
        with patch.dict(os.environ, {"MODEL_ENDPOINT": "https://example.invalid/v1/chat/completion",
                                    "MODEL_API_KEY": "fixture-key"}, clear=True):
            self.assertEqual(setup.validate_live(), "compatible/glm5.3-flash")
            self.assertEqual(os.environ["MODEL_ID"], "glm5.3-flash")
            self.assertEqual(os.environ["OPENCODE_CONFIG"], "/opt/agent-optimizer/compatible.json")
        with patch.dict(os.environ, {"MODEL_API_KEY": "fixture-key"}, clear=True), self.assertRaises(ConfigurationError):
            setup.validate_live()

    def test_system_ca_selection_preserves_explicit_bundle_without_environment_mutation(self):
        with patch("sys.platform", "linux"), patch.object(Path, "is_file", return_value=True):
            environment = {}
            self.assertEqual(demo_environment(environment)["AGENT_OPT_CA_BUNDLE"], "/etc/ssl/certs/ca-certificates.crt")
            self.assertEqual(environment, {})
            self.assertEqual(demo_environment({"AGENT_OPT_CA_BUNDLE": "/custom.pem"})["AGENT_OPT_CA_BUNDLE"], "/custom.pem")
            self.assertEqual(demo_environment({"AGENT_OPT_CA_BUNDLE": ""})["AGENT_OPT_CA_BUNDLE"], "")

    def test_corrupt_checkout_probe_is_safe_and_does_not_echo_subprocess_errors(self):
        runner = doctor.Runner(ROOT, "evaluation", {})
        with patch.object(doctor.subprocess, "run", side_effect=subprocess.CalledProcessError(
                128, ["git"], stderr="fixture-secret")):
            runner.probe("source", ["git", "status"], "Inspect source", "Preserve changes and rerun setup")
        self.assertEqual(runner.checks[0]["status"], "error")
        self.assertNotIn("fixture-secret", json.dumps(runner.checks))

    def test_explicit_probe_failure_sets_nonzero_readiness_without_leaking_or_mutating_env(self):
        report = {"ready": True, "areas": {"core": True, "evaluation": True, "live": True}, "checks": []}
        environment = {"MODEL_ENDPOINT": "https://example.invalid/chat/completion", "MODEL_API_KEY": "fixture-secret",
                       "AGENT_OPT_CA_BUNDLE": ""}
        with patch.dict(os.environ, environment, clear=True), patch.object(checks, "probe_model", side_effect=UnavailableError("fixture-secret")):
            checks.check_models(ROOT, report)
            self.assertEqual(dict(os.environ), environment)
        self.assertFalse(report["ready"])
        self.assertEqual(report["model_status"], "blocked")
        self.assertNotIn("fixture-secret", json.dumps(report))

    def test_explicit_probe_cannot_pass_without_container_tool_result(self):
        original = {"ready": True, "areas": {"core": True, "evaluation": True, "live": True}, "checks": []}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "external").mkdir()
            (root / "external/environment-lock.json").write_text('{"platform":"linux/amd64"}')
            for failed in (False, True):
                report = copy.deepcopy(original)
                with patch.dict(os.environ, {"MODEL_ENDPOINT": "https://example.invalid/chat/completion", "MODEL_API_KEY": "key", "AGENT_OPT_CA_BUNDLE": ""}, clear=True), patch.object(
                        checks, "probe_model", return_value={"status": "passed"}), patch.object(
                        checks, "probe_harness", side_effect=UnavailableError("failed") if failed else None):
                    checks.check_models(root, report)
                self.assertEqual(report["ready"], not failed)
