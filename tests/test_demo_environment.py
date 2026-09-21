import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.contracts import ConfigurationError
from support import ROOT, module

diagnostics = module("demo_diagnostics", ROOT / "examples/ace-rtl/environment/diagnostics.py")
setup = module("demo_setup", ROOT / "examples/ace-rtl/environment/setup.py")


class DemoEnvironmentTests(unittest.TestCase):
    def test_corrupt_checkout_remains_a_structured_independent_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "external").mkdir()
            (root / "external/environment-lock.json").write_text(json.dumps({"platform": "linux/amd64", "images": {
                "evaluation": {"id": "eval"}, "agent": {"id": "agent"}}}))
            with patch.object(setup, "ROOT", root), patch.dict(os.environ, {}, clear=True), patch.object(
                    diagnostics, "prerequisites", return_value={"ready": True, "checks": {}}), patch.object(
                    setup, "prepare_sources", side_effect=subprocess.CalledProcessError(128, ["git"])), patch.object(
                    setup, "prepare_data", side_effect=ConfigurationError("bad data")):
                report = diagnostics.inspect_environment(setup, "linux/amd64")
            self.assertFalse(report["ready"])
            self.assertEqual(report["checks"]["sources"]["status"], "blocked")
            self.assertEqual(report["checks"]["data"]["status"], "blocked")

    def test_prerequisites_accumulate_failures_and_never_echo_process_output(self):
        def run(argv, **_kwargs):
            return subprocess.CompletedProcess(argv, 0 if argv[0] == "git" else 1, "fixture-secret", "fixture-secret")
        with patch.object(diagnostics.subprocess, "run", side_effect=run), patch.dict(os.environ, {}, clear=True):
            result = diagnostics.prerequisites()
        self.assertFalse(result["ready"])
        self.assertEqual(result["checks"]["git"]["status"], "passed")
        self.assertEqual(result["checks"]["compose"]["status"], "blocked")
        self.assertIn("docker compose", result["checks"]["compose"]["repair"])
        self.assertNotIn("fixture-secret", json.dumps(result))
        self.assertNotIn("opencode", result["checks"])

    def test_ca_build_requires_buildx_but_offline_reuse_does_not(self):
        with patch.dict(os.environ, {"AGENT_OPT_CA_BUNDLE": "/fixture.pem"}, clear=True), patch.object(
                diagnostics.subprocess, "run", side_effect=lambda argv, **kw: subprocess.CompletedProcess(
                    argv, 1 if "buildx" in argv else 0, "", "")):
            self.assertFalse(diagnostics.prerequisites()["ready"])
            self.assertTrue(diagnostics.prerequisites(offline=True)["ready"])

    def test_doctor_before_setup_reports_preparation_and_prerequisites(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(setup, "ROOT", Path(directory)), patch.object(
                diagnostics.subprocess, "run", side_effect=FileNotFoundError()):
            result = diagnostics.inspect_environment(setup, "linux/amd64")
        self.assertFalse(result["ready"])
        self.assertEqual(result["checks"]["prepared"]["status"], "blocked")
        self.assertEqual(result["checks"]["uv"]["status"], "blocked")
        self.assertEqual(result["model_status"], "not_checked")

    def test_live_accepts_configured_model_and_refuses_missing_endpoint(self):
        with patch.dict(os.environ, {"MODEL_ENDPOINT": "https://example.invalid/v1/chat/completion",
                                    "MODEL_API_KEY": "fixture-key"}, clear=True):
            self.assertEqual(setup.validate_live(), "compatible/glm5.3-flash")
            self.assertEqual(os.environ["MODEL_ID"], "glm5.3-flash")
            self.assertEqual(os.environ["OPENCODE_CONFIG"], "/opt/agent-optimizer/compatible.json")
        with patch.dict(os.environ, {"MODEL_API_KEY": "fixture-key"}, clear=True), self.assertRaises(ConfigurationError):
            setup.validate_live()

    def test_system_ca_selection_preserves_explicit_bundle(self):
        with patch.object(diagnostics.sys, "platform", "linux"), patch.object(Path, "is_file", return_value=True), patch.dict(
                os.environ, {}, clear=True):
            diagnostics.configure_network()
            self.assertEqual(os.environ["AGENT_OPT_CA_BUNDLE"], "/etc/ssl/certs/ca-certificates.crt")
            os.environ["AGENT_OPT_CA_BUNDLE"] = "/custom.pem"
            diagnostics.configure_network()
            self.assertEqual(os.environ["AGENT_OPT_CA_BUNDLE"], "/custom.pem")
