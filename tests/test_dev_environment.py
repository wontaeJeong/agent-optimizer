import copy
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
import venv
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.contracts import ConfigurationError, UnavailableError, ExecutionResult, Task, Evaluation
from support import ROOT, module

setup = module("ace_setup", ROOT / "examples/ace-rtl/environment/setup.py")
prepare = module("ace_prepare_dev", ROOT / "examples/ace-rtl/prepare.py")
cvdp = module("ace_eval_dev", ROOT / "examples/ace-rtl/evaluator.py")


def official_row():
    # Same metadata shape as the pinned HF QAM16 row; no reference solution.
    return {
        "id": "cvdp_copilot_demo_0001", "categories": ["cid003", "easy"],
        "input": {"prompt": "Implement dut", "context": {}},
        "output": {"response": "", "context": {}},
        "harness": {"files": {
            "docker-compose.yml": "services:\n  direct:\n    image: __OSS_SIM_IMAGE__\n    env_file: ./src/.env\n    command: pytest /src/test_runner.py\n",
            "src/.env": "SIM = icarus\nVERILOG_SOURCES = /code/rtl/dut.sv\n",
            "src/test_runner.py": "PRIVATE_CHECKER",
        }},
    }


class DatasetAcquisitionTests(unittest.TestCase):
    def fetch(self, destination, *, offline=False, payload=b"verified data"):
        self.assertTrue(hasattr(setup, "fetch_asset"), "verified atomic downloader missing")
        return setup.fetch_asset(
            "https://example.invalid/pinned/data", destination,
            hashlib.sha256(payload).hexdigest(), offline=offline,
        )

    def test_verified_cache_reuse_never_needs_network(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "data"
            with patch("urllib.request.urlopen", return_value=io.BytesIO(b"verified data")):
                first = self.fetch(path)
            with patch("urllib.request.urlopen", side_effect=AssertionError("unexpected network")):
                cached = self.fetch(path, offline=True)
                online = self.fetch(path)
            self.assertEqual(first["sha256"], cached["sha256"])
            self.assertEqual(first["sha256"], online["sha256"])
            self.assertEqual(path.read_bytes(), b"verified data")
            self.assertNotIn("OPENROUTER_API_KEY", json.dumps(first))

    def test_hash_failure_preserves_existing_cache_and_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "data"
            path.write_bytes(b"preexisting")
            with patch("urllib.request.urlopen", return_value=io.BytesIO(b"corrupt")):
                with self.assertRaises(ConfigurationError):
                    self.fetch(path)
            self.assertEqual(path.read_bytes(), b"preexisting")
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["data"])

    def test_offline_missing_or_corrupt_asset_fails(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "data"
            with patch("urllib.request.urlopen", side_effect=AssertionError("unexpected network")):
                with self.assertRaises((ConfigurationError, UnavailableError)):
                    self.fetch(path, offline=True)
                path.write_bytes(b"corrupt")
                with self.assertRaises((ConfigurationError, UnavailableError)):
                    self.fetch(path, offline=True)

    def test_interrupted_download_never_publishes_partial_content(self):
        class BrokenStream(io.BytesIO):
            def read(self, *args):
                if self.tell():
                    raise OSError("connection lost")
                return super().read(2)

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "data"
            with patch("urllib.request.urlopen", return_value=BrokenStream(b"data")):
                with self.assertRaises(UnavailableError):
                    self.fetch(path)
            self.assertEqual(list(Path(d).iterdir()), [])


class OfficialImportTests(unittest.TestCase):
    def test_direct_image_and_private_metadata_targets_without_golden(self):
        row = official_row()
        original = copy.deepcopy(row)
        tasks, excluded = prepare.convert([row])
        self.assertEqual(excluded, [])
        self.assertEqual(tasks[0]["evaluation"]["targets"], ["rtl/dut.sv"])
        self.assertEqual(tasks[0]["files"], {"rtl/dut.sv": ""})
        self.assertNotIn("PRIVATE_CHECKER", json.dumps(tasks[0]["files"]))
        self.assertEqual(row, original)

    def test_targets_are_not_guessed_and_unsupported_rows_have_reasons(self):
        for change in ("missing", "wildcard", "traversal", "commercial", "category", "image"):
            with self.subTest(change=change):
                row = official_row()
                files = row["harness"]["files"]
                if change == "missing":
                    files["src/.env"] = "SIM=icarus"
                elif change == "wildcard":
                    files["src/.env"] = "VERILOG_SOURCES=/code/rtl/*.sv"
                elif change == "traversal":
                    files["src/.env"] = "VERILOG_SOURCES=/code/rtl/../secret.sv"
                elif change == "commercial":
                    files["src/.env"] += "\nSIM=xrun"
                elif change == "category":
                    row["categories"] = ["cid007"]
                else:
                    files["docker-compose.yml"] = files["docker-compose.yml"].replace("__OSS_SIM_IMAGE__", "unknown/image")
                tasks, excluded = prepare.convert([row])
                self.assertEqual(tasks, [])
                self.assertTrue(excluded[0]["reason"])

    def test_trivial_dockerfile_does_not_whitelist_an_unreviewed_compose_image(self):
        row = official_row()
        row["harness"]["files"]["Dockerfile"] = "FROM __OSS_SIM_IMAGE__\n"
        row["harness"]["files"]["docker-compose.yml"] = "services:\n  direct:\n    image: unknown/image\n"
        tasks, excluded = prepare.convert([row])
        self.assertEqual(tasks, [])
        self.assertTrue(excluded[0]["reason"])

    def test_missing_compose_is_excluded_instead_of_upstream_llm_scoring(self):
        row = official_row()
        del row["harness"]["files"]["docker-compose.yml"]
        row["harness"]["files"]["Dockerfile"] = "FROM __OSS_SIM_IMAGE__\n"
        self.assertEqual(prepare.convert([row])[0], [])

    def test_empty_supported_set_fails_preparation(self):
        self.assertTrue(hasattr(prepare, "prepare_dataset"), "checked preparation missing")
        with tempfile.TemporaryDirectory() as d:
            dataset = Path(d) / "no_commercial.jsonl"
            dataset.write_text("")
            output = Path(d) / "tasks.json"
            with self.assertRaises(ConfigurationError):
                prepare.prepare_dataset(dataset, output)
            self.assertFalse(output.exists())
            self.assertTrue(output.with_suffix(".excluded.json").is_file())


class EnvironmentChecks(unittest.TestCase):
    def test_setup_missing_executable_is_named_unavailable(self):
        with tempfile.TemporaryDirectory() as d, patch.object(setup.subprocess, "run", side_effect=FileNotFoundError("missing uv")):
            with self.assertRaises(UnavailableError):
                setup.run(["uv", "--version"], log=Path(d) / "setup.log")

    def test_platform_rejects_injection_and_unsupported_os(self):
        self.assertTrue(hasattr(setup, "validate_platform"), "platform validation missing")
        for value in ("linux/amd64", "linux/arm64"):
            self.assertEqual(setup.validate_platform(value), value)
        for value in ("darwin/arm64", "linux/amd64;id", "", "windows/amd64"):
            with self.assertRaises(ConfigurationError):
                setup.validate_platform(value)

    def test_live_auth_and_free_model_validation_precedes_any_execution(self):
        self.assertTrue(hasattr(setup, "validate_live"), "live preflight missing")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(UnavailableError, "blocked_auth"):
                setup.validate_live()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only", "AGENT_OPT_MODEL": "openrouter/vendor/paid"}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "free"):
                setup.validate_live()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only", "AGENT_OPT_MODEL": "openrouter/vendor/model:free"}, clear=True):
            self.assertEqual(setup.validate_live(), "openrouter/vendor/model:free")

    def test_doctor_cannot_report_ready_from_image_presence_only(self):
        self.assertTrue(hasattr(setup, "doctor"), "execution capability doctor missing")
        with tempfile.TemporaryDirectory() as d:
            def execute(argv, **kwargs):
                if argv[:2] == ["docker", "run"]:
                    return subprocess.CompletedProcess(argv, 1, "", "exec format error")
                return subprocess.CompletedProcess(argv, 0, "available", "")
            with patch.object(setup.subprocess, "run", side_effect=execute):
                report = setup.doctor(Path(d), "linux/amd64", "eval-image", "agent-image")
            self.assertFalse(report["ready"])
            self.assertEqual(report["checks"]["eval_tools"]["returncode"], 1)

    def test_offline_missing_source_never_clones(self):
        self.assertTrue(hasattr(setup, "prepare_sources"), "offline source verification missing")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(UnavailableError):
                setup.prepare_sources(Path(d), offline=True)


class EvaluatorRuntimeTests(unittest.TestCase):
    def test_driver_keeps_virtualenv_identity_when_python_is_a_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            environment = Path(d).resolve() / "driver-env"
            venv.EnvBuilder(with_pip=False, symlinks=True).create(environment)
            with patch.dict(os.environ, {"CVDP_PYTHON": str(environment / "bin/python")}):
                evaluator = cvdp.CVDPEvaluator()
            prefix = subprocess.check_output([str(evaluator.python), "-c", "import sys; print(sys.prefix)"], text=True).strip()
            self.assertEqual(prefix, str(environment), "resolving the Python symlink bypasses isolated dependencies")

    def test_docker_launch_failure_is_not_a_candidate_zero(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "output"
            (output / "rtl").mkdir(parents=True)
            (output / "rtl/dut.sv").write_text("module dut; endmodule")
            task = Task(**prepare.convert([official_row()])[0][0])
            def execute(argv, cwd, logs, timeout, env=None):
                prefix = Path(argv[-1])
                prefix.mkdir(parents=True)
                (prefix / "raw_result.json").write_text(json.dumps({task.id: {"tests": [{"result": 125, "error_msg": None}]}}))
                return ExecutionResult("completed", 0, 0.1, "out", "err")
            with patch.object(cvdp, "run_process", side_effect=execute), patch.object(cvdp, "cleanup_network"):
                result = cvdp.CVDPEvaluator().evaluate(task, output, 10)
            self.assertEqual(result.status, "infrastructure_error")
            self.assertIsNone(result.metrics["passed"])

    def test_nested_driver_gets_selected_platform_image_and_no_host_model_key(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "output"
            (output / "rtl").mkdir(parents=True)
            (output / "rtl/dut.sv").write_text("module dut; endmodule")
            task = Task(**prepare.convert([official_row()])[0][0])
            observed = {}
            def execute(argv, cwd, logs, timeout, env=None):
                observed.update(argv=argv, env=env)
                prefix = Path(argv[argv.index("-p") + 1])
                prefix.mkdir(parents=True)
                (prefix / "raw_result.json").write_text(json.dumps({task.id: {"tests": [{"result": 0}]}}))
                return ExecutionResult("completed", 0, 0.1, "out", "err")
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only-secret", "OSS_SIM_IMAGE": "sha256:abc", "DOCKER_DEFAULT_PLATFORM": "linux/amd64"}):
                with patch.object(cvdp, "run_process", side_effect=execute), patch.object(cvdp.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
                    result = cvdp.CVDPEvaluator().evaluate(task, output, 10)
            self.assertEqual(result.status, "passed")
            self.assertIsNotNone(observed["env"], "driver inherited host credentials")
            self.assertEqual(observed["env"]["OSS_SIM_IMAGE"], "sha256:abc")
            self.assertEqual(observed["env"]["DOCKER_DEFAULT_PLATFORM"], "linux/amd64")
            self.assertNotIn("OPENROUTER_API_KEY", observed["env"])
            self.assertIn("--network-name", observed["argv"])
            self.assertNotIn("test-only-secret", json.dumps(observed))

    def test_timeout_cleanup_only_removes_containers_on_owned_network(self):
        self.assertTrue(hasattr(cvdp, "cleanup_network"), "scoped cleanup missing")
        commands = []
        def docker(argv, **kwargs):
            commands.append(argv)
            if argv[1] == "ps":
                self.assertIn("network=agent-opt-cvdp-test", argv)
                return subprocess.CompletedProcess(argv, 0, "owned-id\n", "")
            return subprocess.CompletedProcess(argv, 0, "", "")
        with tempfile.TemporaryDirectory() as d, patch.object(cvdp.subprocess, "run", side_effect=docker):
            cvdp.cleanup_network("agent-opt-cvdp-test", Path(d))
        self.assertIn(["docker", "rm", "-f", "owned-id"], commands)
        self.assertFalse(any("prune" in cmd for cmd in commands))


class SmokeEvidenceTests(unittest.TestCase):
    def test_pass_status_without_nonempty_official_raw_tests_is_not_smoke_success(self):
        path = ROOT / "examples/ace-rtl/environment/checks.py"
        self.assertTrue(path.is_file(), "smoke evidence validation missing")
        checks = module("ace_checks_test", path)
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d) / "raw_result.json"
            for contents in ({}, {"demo": {"tests": []}}):
                raw.write_text(json.dumps(contents))
                result = Evaluation("passed", {"passed": 1.0}, "", {"raw_result": str(raw)})
                with self.assertRaises(UnavailableError):
                    checks.require_verdict(result, "passed", official=True)
            raw.write_text(json.dumps({"demo": {"tests": [{"result": 0}]}}))
            checks.require_verdict(result, "passed", official=True)
            with self.assertRaises(UnavailableError):
                checks.require_verdict(result, "failed", official=True)
