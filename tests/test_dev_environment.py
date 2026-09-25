import copy
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
import venv
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError, UnavailableError, ExecutionResult, Task, Evaluation, RunRequest
from agent_optimizer.harnesses.opencode import OpenCodeHarness
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
    def test_existing_wrong_driver_python_is_preserved_before_online_or_offline_install(self):
        for offline in (False, True):
            with self.subTest(offline=offline), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                driver = root / "external/cvdp-venv"
                driver.mkdir(parents=True)
                sentinel = driver / "user-owned"
                sentinel.write_text("preserve this environment")
                def run(argv, *args, **kwargs):
                    self.assertNotIn("install", argv, "incompatible driver reached dependency installation")
                with patch.object(setup, "ROOT", root), patch.object(setup, "run", side_effect=run), \
                        patch.object(setup, "prepare_sources"), \
                        patch.object(setup, "prepare_data", return_value=(root / "data", {})), \
                        patch.object(setup.subprocess, "check_output", return_value="3.11\n"):
                    with self.assertRaisesRegex(UnavailableError, "Python 3.12.*3.11"):
                        setup.prepare_environment(offline=offline, platform="linux/arm64")
                self.assertEqual(sentinel.read_text(), "preserve this environment")

    def test_doctor_rejects_wrong_python_even_when_dependencies_and_images_execute(self):
        for version, ready in (("3.11", False), ("3.12", True), ("3.14", False)):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as d:
                with patch.object(setup.subprocess, "check_output", return_value=version + "\n"), \
                        patch.object(setup.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, version, "")):
                    report = setup.doctor(Path(d), "linux/arm64", "eval-image", "agent-image")
                self.assertEqual(report["ready"], ready)
                if not ready:
                    self.assertIn("Python 3.12", report["checks"]["driver"]["error"])
                    self.assertIn("preserved", report["checks"]["driver"]["error"])

    def test_omitted_platform_uses_daemon_native_platform_not_environment_default(self):
        for native in ("linux/arm64", "linux/amd64"):
            with self.subTest(native=native), patch.dict(os.environ, {"DOCKER_DEFAULT_PLATFORM": "linux/unsupported"}):
                with patch.object(setup.subprocess, "check_output", return_value=native + "\n"):
                    self.assertEqual(setup.validate_platform(None), native)

    def test_explicit_platform_is_honored_without_native_detection(self):
        with patch.object(setup.subprocess, "check_output", side_effect=AssertionError("unexpected detection")):
            self.assertEqual(setup.validate_platform("linux/amd64"), "linux/amd64")
            self.assertEqual(setup.validate_platform("linux/arm64"), "linux/arm64")

    def test_unsupported_native_architecture_errors_without_substitution(self):
        with patch.object(setup.subprocess, "check_output", return_value="linux/riscv64\n"):
            with self.assertRaisesRegex(ConfigurationError, "linux/riscv64"):
                setup.validate_platform(None)

    def test_unavailable_daemon_cannot_select_a_guessed_platform(self):
        with patch.object(setup.subprocess, "check_output", side_effect=subprocess.CalledProcessError(1, ["docker", "version"])):
            with self.assertRaises(UnavailableError):
                setup.validate_platform(None)

    def test_failed_explicit_build_never_retries_another_architecture(self):
        builds = []
        def run(argv, *args, **kwargs):
            if argv[:2] == ["docker", "build"]:
                builds.append(argv[argv.index("--platform") + 1])
                raise UnavailableError("build failed")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.object(setup, "ROOT", root), patch.object(setup, "run", side_effect=run), \
                    patch.object(setup, "validate_driver_python"), \
                    patch.object(setup, "driver_requirements", return_value={}), \
                    patch.object(setup, "prepare_sources"), \
                    patch.object(setup, "prepare_data", return_value=(root / "dataset", {})):
                with self.assertRaisesRegex(UnavailableError, "build failed"):
                    setup.prepare_environment(platform="linux/amd64")
        self.assertEqual(builds, ["linux/amd64"])

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

    def test_live_model_configuration_precedes_any_execution(self):
        self.assertTrue(hasattr(setup, "validate_live"), "live preflight missing")
        with patch.dict(os.environ, {"AGENT_OPT_MODEL_ENDPOINT": "https://example.invalid/v1/chat/completion"}, clear=True):
            with self.assertRaisesRegex(UnavailableError, "blocked_auth"):
                setup.validate_live()
        with patch.dict(os.environ, {"AGENT_OPT_MODEL_API_KEY": "test-only"}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "AGENT_OPT_MODEL_ENDPOINT"):
                setup.validate_live()
        with patch.dict(os.environ, {"AGENT_OPT_MODEL_API_KEY": "test-only", "AGENT_OPT_MODEL_ID": "model-a",
                                    "AGENT_OPT_MODEL_BASE_URL": "https://example.invalid/v1"}, clear=True):
            self.assertEqual(setup.validate_live(), "compatible/model-a")

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


class DriverLockTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.external = self.root / "external"
        self.requirements = self.external / "cvdp_benchmark/requirements.txt"
        self.requirements.parent.mkdir(parents=True)
        self.requirements.write_text("pyyaml==6.0.2\n")
        self.lockfile = self.root / "examples/ace-rtl/environment/requirements-cvdp-py312.txt"
        self.lockfile.parent.mkdir(parents=True)
        self.lockfile.write_text("pyyaml==6.0.2\n")
        self.expected = {
            "path": "examples/ace-rtl/environment/requirements-cvdp-py312.txt",
            "sha256": hashlib.sha256(b"pyyaml==6.0.2\n").hexdigest(),
            "upstream_sha256": hashlib.sha256(b"pyyaml==6.0.2\n").hexdigest(),
            "python": "3.12",
        }
        self.addCleanup(patch.stopall)
        patch.object(setup, "ROOT", self.root).start()
        patch.object(setup, "REQUIREMENTS_SHA256", self.expected["upstream_sha256"], create=True).start()

    def test_changed_upstream_requirements_cannot_use_stale_compiled_lock(self):
        self.assertTrue(hasattr(setup, "driver_requirements"), "driver lock validation missing")
        self.assertEqual(setup.driver_requirements(self.external), self.expected)
        self.requirements.write_text("pyyaml==0.0.0\n")
        with self.assertRaisesRegex(ConfigurationError, "requirements.*hash"):
            setup.driver_requirements(self.external)
        self.assertEqual(self.requirements.read_text(), "pyyaml==0.0.0\n")

    def test_offline_check_rejects_changed_lock_or_installed_packages(self):
        self.assertTrue(hasattr(setup, "validate_driver_lock"), "offline driver check missing")
        lock = {"driver_requirements": self.expected, "driver_packages": "PyYAML==6.0.2\n"}
        with patch.object(setup.subprocess, "check_output", return_value="PyYAML==6.0.2\n"):
            setup.validate_driver_lock(self.external, lock)
            self.lockfile.write_text("pyyaml==0.0.0\n")
            with self.assertRaisesRegex(ConfigurationError, "lock.*differs"):
                setup.validate_driver_lock(self.external, lock)
        self.lockfile.write_text("pyyaml==6.0.2\n")
        with patch.object(setup.subprocess, "check_output", return_value="PyYAML==0.0.0\n"):
            with self.assertRaisesRegex(ConfigurationError, "packages.*differ"):
                setup.validate_driver_lock(self.external, lock)

    def test_online_and_offline_setup_sync_only_compiled_lock_and_record_hash(self):
        images = {
            "evaluation": {"tag": "agent-optimizer-cvdp:8e894cf-arm64", "id": "sha256:eval"},
            "agent": {"tag": f"agent-optimizer-opencode:{setup.OPENCODE_VERSION}-arm64", "id": "sha256:agent"},
        }
        (self.external / "cvdp-venv").mkdir()
        def output(argv, **kwargs):
            if argv[:3] == ["docker", "image", "inspect"]:
                identity = next(image["id"] for image in images.values() if image["tag"] == argv[-1])
                return json.dumps([{"Os": "linux", "Architecture": "arm64", "Id": identity}])
            return "PyYAML==6.0.2\n"
        for offline in (False, True):
            with self.subTest(offline=offline):
                commands = []
                with patch.object(setup, "validate_driver_python"), \
                        patch.object(setup, "prepare_sources"), \
                        patch.object(setup, "prepare_data", return_value=(self.external / "data", {})), \
                        patch.object(setup, "doctor", return_value={"ready": True}), \
                        patch.object(setup, "run", side_effect=lambda argv, *a, **kw: commands.append(argv)), \
                        patch.object(setup.subprocess, "check_output", side_effect=output):
                    _, lock = setup.prepare_environment(offline=offline, platform="linux/arm64")
                installs = [cmd for cmd in commands if "pip" in cmd]
                self.assertEqual(installs, [["uv", *(["--offline"] if offline else []), "pip", "sync",
                                            "--python", str(self.external / "cvdp-venv/bin/python"),
                                            str(self.lockfile)]])
                self.assertEqual(lock.get("driver_requirements"), self.expected)
                recorded = json.loads((self.external / "environment-lock.json").read_text())
                self.assertEqual(recorded["driver_requirements"], self.expected)
                self.assertFalse(any("sync" in cmd and "pip" not in cmd for cmd in commands),
                                 "example setup must not replace bootstrap's project Python (CI supports 3.11)")
                if offline:
                    self.assertFalse(any(cmd[:2] == ["docker", "build"] for cmd in commands))

    def test_selected_cvdp_setup_preserves_full_ace_lock_and_never_prepares_agent_image(self):
        from examples.benchmarks import cvdp as provider_module
        dataset = "\n".join(json.dumps({**official_row(), "id": f"cvdp_copilot_{i:04d}"})
                            for i in range(3)).encode() + b"\n"
        assets = {setup.DATA_FILE: hashlib.sha256(dataset).hexdigest(),
                  "LICENSE": hashlib.sha256(b"license").hexdigest(),
                  "NOTICE": hashlib.sha256(b"notice").hexdigest()}
        full_lock = self.external / "environment-lock.json"
        full_lock.write_bytes(b"full ACE lock sentinel\n")
        before_full_lock = full_lock.read_bytes()
        (self.external / "cvdp_benchmark/.git").mkdir()
        commands = []
        original_load = provider_module._load

        def load(path, name):
            return setup if path.name == "setup.py" else original_load(path, name)

        def external_command(argv, *args, **kwargs):
            commands.append(argv)
            if argv[:2] == ["git", "clone"]:
                (Path(argv[-1]) / ".git").mkdir(parents=True)
            if "venv" in argv:
                python = self.external / "cvdp-venv/bin/python"
                python.parent.mkdir(parents=True, exist_ok=True)
                python.write_text("fixture")

        def inspected(argv, **kwargs):
            if argv[:2] == ["docker", "version"]:
                return "linux/arm64\n"
            if argv[:3] == ["git", "rev-parse", "HEAD"]:
                return setup.REPOS["cvdp_benchmark"][1] + "\n"
            if argv[:2] == ["git", "status"]:
                return ""
            if argv[:3] == ["docker", "image", "inspect"]:
                return json.dumps([{"Id": "sha256:" + "a" * 64, "Os": "linux", "Architecture": "arm64"}])
            if argv[0] == "uv":
                return "PyYAML==6.0.2\n"
            return "3.12\n"

        def tool(argv, **kwargs):
            name = argv[-2]
            version = {"yosys": "Yosys 0.40", "iverilog": "Icarus Verilog version 13.0",
                       "vvp": "Icarus Verilog runtime version 13.0",
                       "verilator": "Verilator 5.038"}[name]
            return subprocess.CompletedProcess(argv, 0, version, "")

        def downloaded(url, **kwargs):
            return io.BytesIO(dataset if url.endswith(setup.DATA_FILE) else
                              b"license" if url.endswith("LICENSE") else b"notice")

        with patch.object(setup, "ROOT", self.root), patch.object(setup, "ASSETS", assets), \
                patch.object(setup, "REQUIREMENTS_SHA256", self.expected["upstream_sha256"]), \
                patch.object(setup, "run", side_effect=external_command), \
                patch.object(setup.subprocess, "check_output", side_effect=inspected), \
                patch.object(setup.subprocess, "run", side_effect=tool), \
                patch("urllib.request.urlopen", side_effect=downloaded), \
                patch.object(provider_module, "_load", side_effect=load), \
                patch.object(setup, "prepare_environment", side_effect=AssertionError("ACE setup invoked")):
            result = provider_module.Provider().prepare(self.external / "datasets/cvdp")
            self.assertIn("evaluation", result["provenance"])
            self.assertNotIn("agent_image", result["provenance"])
            self.assertEqual(before_full_lock, full_lock.read_bytes())
            self.assertTrue((self.external / "datasets/cvdp/evaluation-lock.json").is_file())
            self.assertFalse((self.external / "ACE-RTL").exists())
            self.assertEqual(result["evaluator"], "cvdp")
            self.assertEqual(result["evaluator_config"]["sim_image_id"], "sha256:" + "a" * 64)
            self.assertFalse(any(cmd[:2] == ["docker", "build"] and "docker/Dockerfile.sim" not in cmd
                                 for cmd in commands))
            self.assertFalse(any("opencode" in str(cmd).lower() for cmd in commands))
            commands.clear()
            reused = provider_module.Provider().prepare(self.external / "datasets/cvdp", offline=True)
            self.assertEqual(reused["evaluator_config"]["sim_image_id"], result["evaluator_config"]["sim_image_id"])
            self.assertFalse(any(cmd[:2] == ["docker", "build"] or cmd[:2] == ["git", "clone"]
                                 for cmd in commands))
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.external.rglob("*") if p.is_file()}
            rows = provider_module.Provider().doctor(self.external / "datasets/cvdp")
            self.assertTrue(all(row["status"] == "ok" for row in rows), rows)
            self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns)
                                       for p in self.external.rglob("*") if p.is_file()})
            evaluation_lock = self.external / "datasets/cvdp/evaluation-lock.json"
            original_lock = evaluation_lock.read_bytes()
            tasks = self.external / "datasets/cvdp/cvdp/tasks.json"
            original_tasks = tasks.read_bytes()
            self.assertIn("tasks_sha256", json.loads(original_lock))
            self.assertEqual(len(json.loads(original_lock)["tasks_sha256"]), 64)
            tasks.unlink()
            rows = provider_module.Provider().doctor(self.external / "datasets/cvdp")
            self.assertEqual(next(row["status"] for row in rows if row["id"] == "dataset.cvdp.tasks"), "error")
            tasks.write_bytes(original_tasks.replace(b"cvdp-reviewed", b"cvdp-tampered"))
            rows = provider_module.Provider().doctor(self.external / "datasets/cvdp")
            self.assertEqual(next(row["status"] for row in rows if row["id"] == "dataset.cvdp.tasks"), "error")
            tasks.write_bytes(original_tasks)
            legacy = json.loads(original_lock)
            legacy.pop("tasks_sha256")
            evaluation_lock.write_text(json.dumps(legacy))
            rows = provider_module.Provider().doctor(self.external / "datasets/cvdp")
            self.assertEqual(next(row["status"] for row in rows if row["id"] == "dataset.cvdp.tasks"), "error")
            with self.assertRaisesRegex(UnavailableError, "online"):
                provider_module.Provider().prepare(self.external / "datasets/cvdp", offline=True)
            evaluation_lock.write_bytes(original_lock)
            changed = json.loads(original_lock)
            changed["images"]["evaluation"]["id"] = "sha256:" + "b" * 64
            evaluation_lock.write_text(json.dumps(changed))
            rows = provider_module.Provider().doctor(self.external / "datasets/cvdp")
            self.assertTrue(any(row["id"] == "dataset.cvdp.image" and row["status"] == "error"
                                and row["remedy"] for row in rows), rows)
            evaluation_lock.write_bytes(original_lock)
            (self.external / "cvdp-data" / setup.DATA_REVISION / "LICENSE").write_text("tampered")
            rows = provider_module.Provider().doctor(self.external / "datasets/cvdp")
            self.assertTrue(any(row["status"] == "error" and "LICENSE" in row["id"]
                                and row["remedy"] for row in rows), rows)
            self.assertEqual(before_full_lock, full_lock.read_bytes())
            (self.external / "cvdp-data" / setup.DATA_REVISION / "LICENSE").write_bytes(b"license")
            malformed = json.loads(evaluation_lock.read_text())
            malformed["dataset"]["files"]["LICENSE"] = []
            evaluation_lock.write_text(json.dumps(malformed))
            rows = provider_module.Provider().doctor(self.external / "datasets/cvdp")
            self.assertTrue(any(row["status"] == "error" and row["remedy"] for row in rows), rows)
            with self.assertRaises(ConfigurationError):
                provider_module.Provider().prepare(self.external / "datasets/cvdp", offline=True)
            self.assertEqual(evaluation_lock.read_text(), json.dumps(malformed))

    def test_legacy_full_ace_still_prepares_two_sources_and_images(self):
        images = {"agent-optimizer-cvdp:8e894cf-arm64": "sha256:eval",
                  f"agent-optimizer-opencode:{setup.OPENCODE_VERSION}-arm64": "sha256:agent"}
        commands = []
        checked_sources = []

        def inspected(argv, **kwargs):
            if argv[:3] == ["git", "rev-parse", "HEAD"]:
                checked_sources.append(Path(kwargs["cwd"]).name)
                return setup.REPOS[Path(kwargs["cwd"]).name][1] + "\n"
            if argv[:2] == ["git", "status"]:
                return ""
            return json.dumps([{"Os": "linux", "Architecture": "arm64", "Id": images[argv[-1]]}])

        def execute(argv, *args, **kwargs):
            commands.append(argv)
            if argv[:2] == ["git", "clone"]:
                Path(argv[-1]).mkdir(parents=True)

        with patch.object(setup, "ROOT", self.root), patch.object(setup, "run", side_effect=execute), \
                patch.object(setup, "prepare_data",
                return_value=(self.external / "dataset", {})), patch.object(setup, "driver_requirements",
                return_value={}), patch.object(setup, "validate_driver_python"), \
                patch.object(setup, "driver_packages", return_value="PyYAML==6.0.2\n"), \
                patch.object(setup, "doctor", return_value={"ready": True}), \
                patch.object(setup.subprocess, "check_output", side_effect=inspected):
            _, lock = setup.prepare_environment(platform="linux/arm64")
        self.assertEqual(set(lock["images"]), {"evaluation", "agent"})
        self.assertEqual(set(checked_sources), {"ACE-RTL", "cvdp_benchmark"})
        self.assertIn("ACE-RTL", {Path(cmd[-1]).name for cmd in commands if cmd[:2] == ["git", "clone"]})
        self.assertEqual(set(lock["repos"]), {"ACE-RTL", "cvdp_benchmark"})
        self.assertEqual(len([cmd for cmd in commands if cmd[:2] == ["docker", "build"]]), 2)
        self.assertTrue((self.external / "environment-lock.json").is_file())

    def test_selected_online_rebuild_preserves_full_ace_tag_and_locked_image_identity(self):
        images = {}
        builds = []
        stage = ["full"]
        original = "sha256:" + "a" * 64
        rebuilt = "sha256:" + "b" * 64

        def execute(argv, *args, **kwargs):
            if argv[:2] == ["docker", "build"]:
                tag = argv[argv.index("-t") + 1]
                builds.append((stage[0], tag))
                images[tag] = (rebuilt if stage[0] == "selected" else
                               "sha256:" + "c" * 64 if "opencode" in tag else original)

        def inspected(argv, **kwargs):
            self.assertEqual(argv[:3], ["docker", "image", "inspect"])
            return json.dumps([{"Id": images[argv[-1]], "Os": "linux", "Architecture": "arm64"}])

        def tool(argv, **kwargs):
            versions = {"yosys": "Yosys 0.40", "iverilog": "Icarus Verilog version 13.0",
                        "vvp": "Icarus Verilog runtime version 13.0", "verilator": "Verilator 5.038"}
            return subprocess.CompletedProcess(argv, 0, versions[argv[-2]], "")

        with patch.object(setup, "ROOT", self.root), patch.object(setup, "run", side_effect=execute), \
                patch.object(setup, "prepare_sources"), patch.object(setup, "prepare_data",
                return_value=(self.external / "dataset", {"revision": "fixture", "files": {}})), \
                patch.object(setup, "validate_driver_python"), \
                patch.object(setup, "driver_packages", return_value="PyYAML==6.0.2\n"), \
                patch.object(setup, "doctor", return_value={"ready": True}), \
                patch.object(setup.subprocess, "check_output", side_effect=inspected), \
                patch.object(setup.subprocess, "run", side_effect=tool):
            _, full = setup.prepare_environment(platform="linux/arm64")
            full_lock = self.external / "environment-lock.json"
            original_lock = full_lock.read_bytes()
            stage[0] = "selected"
            _, selected = setup.prepare_evaluation_environment(
                platform="linux/arm64", cache=self.external / "datasets/cvdp")
            self.assertNotEqual(selected["images"]["evaluation"]["tag"], full["images"]["evaluation"]["tag"])
            self.assertEqual(images[full["images"]["evaluation"]["tag"]], original)
            self.assertEqual(setup.verified_sim_image(setup.read_environment_lock(full_lock)),
                             full["images"]["evaluation"]["tag"])
            self.assertEqual(full_lock.read_bytes(), original_lock)
        self.assertEqual(len([tag for stage_name, tag in builds if stage_name == "selected"]), 1)

    def test_malformed_selected_lock_fails_with_repair_without_running_setup_or_overwriting_cache(self):
        cache = self.external / "datasets/cvdp"
        cache.mkdir(parents=True)
        lock_path = cache / "evaluation-lock.json"
        valid = {"platform": "linux/arm64", "ca_bundle_sha256": None,
                 "driver_requirements": self.expected, "driver_packages": "PyYAML==6.0.2\n",
                 "dataset": {"revision": setup.DATA_REVISION, "files": {}},
                 "images": {"evaluation": {"tag": setup.evaluation_image("linux/arm64", selected=True),
                                           "id": "sha256:" + "a" * 64}}}
        for key, malformed in (("driver_packages", {}), ("images", [])):
            for offline in (False, True):
                with self.subTest(key=key, offline=offline):
                    lock = {**valid, key: malformed}
                    original = json.dumps(lock).encode()
                    lock_path.write_bytes(original)
                    commands = []
                    with patch.object(setup, "ROOT", self.root), \
                            patch.object(setup, "ca_fingerprint", return_value=None), \
                            patch.object(setup, "prepare_sources"), \
                            patch.object(setup, "prepare_data", return_value=(self.external / "data", valid["dataset"])), \
                            patch.object(setup, "validate_driver_python"), \
                            patch.object(setup, "driver_packages", return_value="PyYAML==6.0.2\n"), \
                            patch.object(setup, "inspect_image", return_value=valid["images"]["evaluation"]), \
                            patch.object(setup, "verify_evaluation_tools"), \
                            patch.object(setup, "run", side_effect=lambda argv, *a, **kw: commands.append(argv)):
                        with self.assertRaisesRegex(ConfigurationError, "evaluation lock.*preserved.*prepare cvdp"):
                            setup.prepare_evaluation_environment(offline=offline, platform="linux/arm64", cache=cache)
                    self.assertEqual(lock_path.read_bytes(), original)
                    self.assertEqual(commands, [])

    def test_selected_evaluation_image_rejects_wrong_simulator_tool_version(self):
        def version(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, "Icarus Verilog version 12.0", "")

        with patch.object(setup.subprocess, "run", side_effect=version):
            with self.assertRaisesRegex(UnavailableError, "version"):
                setup.verify_evaluation_tools("sha256:" + "a" * 64, "linux/arm64")

    def test_invalid_evaluation_image_inspection_is_a_configuration_error(self):
        with patch.object(setup.subprocess, "check_output", return_value='[{}]'):
            with self.assertRaises(ConfigurationError):
                setup.inspect_image("agent-optimizer-cvdp:test", "linux/arm64")


class PreparedImageTests(unittest.TestCase):
    def run_dev(self, command, *, actual_id=None, missing=False, tag="agent-optimizer-cvdp:8e894cf-amd64",
                architecture="amd64"):
        dev = module("dev_image_test", ROOT / "scripts/dev.py")
        identity = "sha256:" + "a" * 64
        lock = {"platform": "linux/amd64", "images": {
            "evaluation": {"tag": tag, "id": identity},
            "agent": {"tag": "agent-optimizer-opencode:test", "id": "sha256:" + "b" * 64},
        }}
        observed = []
        def dispatch(prepared):
            observed.append((os.environ["OSS_SIM_IMAGE"], os.environ["DOCKER_DEFAULT_PLATFORM"], prepared))
            return 0
        def inspect(argv, **kwargs):
            self.assertEqual(argv, ["docker", "image", "inspect", tag])
            if missing:
                raise subprocess.CalledProcessError(1, argv)
            return json.dumps([{"Id": actual_id or identity, "Os": "linux", "Architecture": architecture}])
        def doctor(external, platform, eval_image, agent_image):
            self.assertEqual((eval_image, agent_image), (identity, lock["images"]["agent"]["id"]))
            return {"ready": True, "checks": {}}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "external").mkdir()
            (root / "external/environment-lock.json").write_text(json.dumps(lock))
            stdout = io.StringIO()
            with patch.object(dev, "ROOT", root), patch.object(dev.os, "chdir"), \
                    patch.object(setup, "ROOT", root), \
                    patch.object(dev, "demo_environment", side_effect=lambda: dict(os.environ)), \
                    patch.object(dev, "load", side_effect=[setup, SimpleNamespace(smoke=dispatch, live=dispatch)]), \
                    patch.object(setup, "prepare_sources"), patch.object(setup, "prepare_data"), \
                    patch.object(setup, "validate_driver_lock"), patch.object(setup, "doctor", side_effect=doctor), \
                    patch.object(setup.subprocess, "check_output", side_effect=inspect), \
                    patch("sys.argv", ["dev.py", command, "--platform", "linux/amd64"]), \
                    patch.dict(os.environ, {"AGENT_OPT_MODEL_API_KEY": "test-only", "AGENT_OPT_MODEL_ENDPOINT": "https://example.invalid/v1/chat/completion", "AGENT_OPT_CA_BUNDLE": ""}), \
                    redirect_stdout(stdout):
                code = dev.main()
        return code, observed, stdout.getvalue()

    def test_smoke_and_live_use_dockerfile_safe_tag_verified_against_locked_id(self):
        for command in ("smoke", "live"):
            with self.subTest(command=command):
                code, observed, _ = self.run_dev(command)
                self.assertEqual(code, 0)
                self.assertEqual(observed[0][:2], ("agent-optimizer-cvdp:8e894cf-amd64", "linux/amd64"))

    def test_changed_or_missing_image_blocks_before_smoke_or_live_success(self):
        # Aggregate doctor covers both image identities in test_dev_doctor instead.
        for command in ("smoke", "live"):
            for changes in ({"actual_id": "sha256:" + "c" * 64}, {"missing": True}, {"architecture": "arm64"}):
                with self.subTest(command=command, changes=changes):
                    code, observed, stdout = self.run_dev(command, **changes)
                    self.assertEqual(code, 2)
                    self.assertEqual(observed, [])
                    self.assertIn("image", stdout.lower())

    def test_bare_id_or_invalid_tag_in_lock_cannot_enter_dockerfile(self):
        for tag in ("sha256:" + "a" * 64, "agent-optimizer-cvdp:test\nRUN false", "nvidia/cvdp-sim:latest"):
            with self.subTest(tag=tag):
                code, observed, _ = self.run_dev("smoke", tag=tag)
                self.assertEqual(code, 2)
                self.assertEqual(observed, [])


class EvaluatorRuntimeTests(unittest.TestCase):
    def test_driver_keeps_virtualenv_identity_when_python_is_a_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            environment = Path(d).resolve() / "driver-env"
            venv.EnvBuilder(with_pip=False, symlinks=True).create(environment)
            with patch.dict(os.environ, {"AGENT_OPT_CVDP_PYTHON": str(environment / "bin/python")}):
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
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only-secret", "OSS_SIM_IMAGE": "agent-optimizer-cvdp:8e894cf-amd64", "DOCKER_DEFAULT_PLATFORM": "linux/amd64"}):
                with patch.object(cvdp, "run_process", side_effect=execute), patch.object(cvdp.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
                    result = cvdp.CVDPEvaluator().evaluate(task, output, 10)
            self.assertEqual(result.status, "passed")
            self.assertIsNotNone(observed["env"], "driver inherited host credentials")
            self.assertEqual(observed["env"]["OSS_SIM_IMAGE"], "agent-optimizer-cvdp:8e894cf-amd64")
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


class PrivateResultLogTests(unittest.TestCase):
    def evaluate_log(self, contents, *, path_kind="absolute", status=1):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            output = root / "output"
            (output / "rtl").mkdir(parents=True)
            (output / "rtl/dut.sv").write_text("module dut; endmodule")
            task = Task(**prepare.convert([official_row()])[0][0])
            def execute(argv, cwd, logs, timeout, env=None):
                prefix = Path(argv[-1])
                report = prefix / "demo/reports/1.txt"
                report.parent.mkdir(parents=True)
                report.write_text(contents)
                outside = root / "outside.txt"
                outside.write_text(contents)
                if path_kind == "absolute":
                    log = str(report)
                elif path_kind == "relative":
                    log = "demo/reports/1.txt"
                elif path_kind == "outside":
                    log = str(outside)
                elif path_kind == "traversal":
                    log = "../../outside.txt"
                elif path_kind == "absolute-traversal":
                    log = str(prefix / "../../outside.txt")
                elif path_kind == "symlink":
                    report.unlink()
                    report.symlink_to(outside)
                    log = str(report)
                elif path_kind == "directory-symlink":
                    (prefix / "linked").symlink_to(root, target_is_directory=True)
                    log = str(prefix / "linked/outside.txt")
                elif path_kind == "prefix-symlink":
                    moved = prefix.with_name("moved")
                    prefix.rename(moved)
                    prefix.symlink_to(moved, target_is_directory=True)
                    log = str(report)
                elif path_kind == "directory":
                    log = str(report.parent)
                elif path_kind == "missing":
                    log = str(report.with_name("missing.txt"))
                else:
                    log = None
                (prefix / "raw_result.json").write_text(json.dumps({task.id: {"tests": [
                    {"result": status, "log": log, "error_msg": None, "execution": 0.866, "pid": 36711}
                ], "errors": int(status != 0)}}))
                return ExecutionResult("completed", 0, 0.1, "out", "err")
            read_text = Path.read_text
            def guarded_read(path, *args, **kwargs):
                self.assertNotEqual(path.resolve(), root / "outside.txt", "unsafe private log was read")
                return read_text(path, *args, **kwargs)
            with patch.object(cvdp, "run_process", side_effect=execute), patch.object(cvdp, "cleanup_network"), \
                    patch.object(Path, "read_text", guarded_read):
                result = cvdp.CVDPEvaluator().evaluate(task, output, 10)
            self.assertNotIn("PRIVATE_SENTINEL", result.feedback)
            return result

    def test_result_one_null_error_uses_private_docker_build_or_launch_evidence(self):
        for diagnostic in (
            "#3 [internal] load metadata for docker.io/library/sha256:abc\n"
            "#3 ERROR: pull access denied, repository does not exist or may require authorization: "
            "server message: insufficient_scope: authorization failed",
            "failed to solve: image: failed to resolve source metadata for docker.io/library/image:tag",
            "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?",
            "Error response from daemon: failed to create task for container: OCI runtime create failed",
        ):
            for path_kind in ("absolute", "relative"):
                with self.subTest(diagnostic=diagnostic, path_kind=path_kind):
                    result = self.evaluate_log("PRIVATE_SENTINEL\n" + diagnostic, path_kind=path_kind)
                    self.assertEqual(result.status, "infrastructure_error")
                    self.assertIsNone(result.metrics["passed"])

    def test_hdl_compile_and_functional_failures_remain_candidate_zero(self):
        for diagnostic in (
            "rtl/dut.sv:12: syntax error\nmake: *** [sim.vvp] Error 2",
            "AssertionError: sequence mismatch\nTESTS=3 PASS=0 FAIL=3",
            "rtl/missing.sv: No such file or directory\niverilog failed",
            "rtl/dut.sv: Permission denied\nmake: *** [compile] Error 1",
        ):
            with self.subTest(diagnostic=diagnostic):
                result = self.evaluate_log("PRIVATE_SENTINEL\n" + diagnostic)
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.metrics["passed"], 0.0)

    def test_unsafe_or_unreadable_private_log_is_invalid_without_reading_outside(self):
        for path_kind in ("outside", "traversal", "absolute-traversal", "symlink", "directory-symlink",
                          "prefix-symlink", "directory", "missing"):
            with self.subTest(path_kind=path_kind):
                result = self.evaluate_log("PRIVATE_SENTINEL", path_kind=path_kind)
                self.assertEqual(result.status, "infrastructure_error")
                self.assertIsNone(result.metrics["passed"])

    def test_absent_optional_log_keeps_existing_binary_verdict(self):
        for status, expected in ((0, "passed"), (1, "failed")):
            with self.subTest(status=status):
                result = self.evaluate_log("", path_kind="none", status=status)
                self.assertEqual(result.status, expected)


class SmokeEvidenceTests(unittest.TestCase):
    def test_smoke_reports_running_and_failed_tool_gate_before_final_json(self):
        checks = module("ace_smoke_progress", ROOT / "examples/ace-rtl/environment/checks.py")

        class NoEvaluatorNeeded:
            def load_plugins(self, *_args):
                pass

        output, progress = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(checks, "ROOT", Path(directory)), \
                patch.object(checks, "Registry", return_value=NoEvaluatorNeeded()), \
                patch.object(checks, "execute", return_value=ExecutionResult("timeout", None, 0.1, "out", "err")), \
                redirect_stdout(output), redirect_stderr(progress):
            with self.assertRaises(UnavailableError):
                checks.smoke({"images": {"evaluation": {"id": "fixture-image"}}})
        self.assertIn("[smoke] check=T4-real-tools starting", progress.getvalue())
        self.assertIn("[smoke] check=T4-real-tools failed", progress.getvalue())
        self.assertEqual(json.loads(output.getvalue())["status"], "failed")

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


class ShippedRTLProfileTests(unittest.TestCase):
    def test_docker_invocation_forwards_default_provider_and_explicit_compatible_settings(self):
        profile = load_experiment(ROOT / "examples/rtl-debugger/experiment.toml")["_profiles"][0]
        for model, required in (
            ("openrouter/vendor/model:free", {"AGENT_OPT_MODEL", "OPENROUTER_API_KEY"}),
            ("compatible/example-model", {"AGENT_OPT_MODEL", "OPENCODE_CONFIG", "AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_ID", "AGENT_OPT_MODEL_API_KEY"}),
        ):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                stdout, stderr = root / "stdout", root / "stderr"
                stdout.write_text("")
                stderr.write_text("")
                commands = []
                def docker(argv, *args, **kwargs):
                    commands.append(argv)
                    return ExecutionResult("completed", 0, 0, str(stdout), str(stderr))
                request = RunRequest(root, root / "agent", root / "task", "public task", 10, 0, profile, root / "logs")
                with patch.dict(os.environ, {"AGENT_OPT_MODEL": model, "OPENROUTER_API_KEY": "test-only-secret", "AGENT_OPT_MODEL_API_KEY": "test-only-secret"}), \
                        patch("agent_optimizer.process.run_process", side_effect=docker), \
                        patch("agent_optimizer.process.subprocess.run"):
                    os.environ.pop("OPENCODE_CONFIG", None)
                    if model.startswith("compatible/"):
                        os.environ.update(OPENCODE_CONFIG="/work/agent/provider-compatible.json",
                                           AGENT_OPT_MODEL_ID="example-model", AGENT_OPT_MODEL_BASE_URL="http://example.invalid/v1")
                    result = OpenCodeHarness().run(request)
                self.assertEqual(result.status, "completed")
                argv = commands[0]
                forwarded = {argv[i + 1] for i, value in enumerate(argv[:-1]) if value == "--env"}
                self.assertTrue(required <= forwarded, f"missing container environment: {required - forwarded}")
                if model.startswith("openrouter/"):
                    self.assertNotIn("OPENCODE_CONFIG", forwarded)
                self.assertNotIn("test-only-secret", " ".join(argv))
                self.assertEqual(argv[argv.index("--model") + 1], model)
