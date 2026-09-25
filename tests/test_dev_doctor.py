import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from support import ROOT, module
from test_network import certificate


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / "scripts/dev_doctor.py").is_file(), "aggregate doctor missing")
        self.doctor = module("doctor_test", ROOT / "scripts/dev_doctor.py")
        self.adapter = self.doctor.example_adapter()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"AGENT_OPT_CA_BUNDLE": ""}, clear=True).start()

    def checks(self, report):
        checks = {item["id"]: item for item in report["checks"]}
        self.assertEqual(len(checks), len(report["checks"]))
        for item in checks.values():
            self.assertEqual(set(item), {"id", "area", "status", "message", "remedy"})
            if item["status"] != "ok":
                self.assertTrue(item["remedy"])
        return checks

    def test_invalid_ca_preserves_aggregate_and_environment_across_calls(self):
        dev = module("doctor_network_entry", ROOT / "scripts/dev.py")
        for value in ("missing-SECRET.pem", "invalid-SECRET.pem", "private-SECRET.pem"):
            bundle = self.root / value
            if value.startswith("invalid"):
                bundle.write_text("SECRET invalid PEM")
            if value.startswith("private"):
                bundle.write_text("-----BEGIN PRIVATE KEY-----\nSECRET\n")
            with self.subTest(value=value), patch.dict(os.environ, {
                    "AGENT_OPT_CA_BUNDLE": str(bundle), "HTTPS_PROXY": "http://SECRET@proxy",
                    "http_proxy": "", "HTTP_PROXY": "SECRET", "SSL_CERT_FILE": "original"}, clear=True), \
                    patch.object(dev, "ROOT", self.root), patch.object(dev, "load", return_value=self.doctor), \
                    patch.object(self.doctor.shutil, "which", return_value=None):
                before = dict(os.environ)
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(dev.main(["doctor", "--json"]), 2)
                report = json.loads(output.getvalue())
                self.assertEqual(set(report), {"ready", "areas", "checks"})
                checks = self.checks(report)
                self.assertEqual(checks["network.configuration"]["status"], "error")
                self.assertIn("AGENT_OPT_CA_BUNDLE", checks["network.configuration"]["remedy"])
                self.assertIn("unset", checks["network.configuration"]["remedy"])
                for name in ("core.git", "core.uv", "core.python", "source.ACE-RTL", "data.LICENSE", "live.key"):
                    self.assertEqual(checks[name]["status"], "error")
                self.assertNotIn("SECRET", output.getvalue())
                self.assertEqual(dict(os.environ), before)
                del os.environ["AGENT_OPT_CA_BUNDLE"]
                self.assertEqual(self.checks(self.doctor.collect_report(self.root))["network.configuration"]["status"], "ok")

    def test_network_settings_are_child_scoped_and_invalid_ca_does_not_block_local_checks(self):
        bundle = certificate(self.root)
        self.prepared()
        for valid in (True, False):
            self.lock["ca_bundle_sha256"] = hashlib.sha256(bundle.read_bytes()).hexdigest() if valid else None
            self.write_lock()
            with self.subTest(valid=valid), patch.dict(os.environ, {
                    "AGENT_OPT_CA_BUNDLE": str(bundle if valid else self.root / "missing-SECRET.pem"),
                    "HTTPS_PROXY": "http://SECRET@proxy", "HTTP_PROXY": "ignored", "http_proxy": "",
                    "SSL_CERT_FILE": "original", "KEEP": "original"}, clear=True):
                before = dict(os.environ)
                seen = []
                def execute(argv, **kwargs):
                    seen.append(kwargs["env"])
                    return self.execute(argv, **kwargs)
                with patch.object(self.doctor.subprocess, "run", side_effect=execute):
                    report = self.doctor.collect_report(self.root)
                checks = self.checks(report)
                self.assertEqual(report["ready"], valid)
                self.assertTrue(report["areas"]["evaluation"])
                for name in ("core.git", "source.ACE-RTL", "driver.packages", "tools.evaluation", "tools.opencode"):
                    self.assertEqual(checks[name]["status"], "ok")
                self.assertTrue(seen)
                for env in seen:
                    self.assertEqual(env["https_proxy"], "http://SECRET@proxy")
                    self.assertEqual(env["HTTP_PROXY"], "")
                    self.assertEqual(env["KEEP"], "original")
                    if valid:
                        self.assertEqual(env["SSL_CERT_FILE"], str(bundle))
                    else:
                        self.assertNotIn("SSL_CERT_FILE", env)
                        self.assertNotIn("AGENT_OPT_CA_BUNDLE", env)
                self.assertEqual(dict(os.environ), before)
                self.assertNotIn("SECRET", json.dumps(report))

    def public_checkout(self):
        # Fresh source copy: actual invocation, no cached implementation imports.
        shutil.copytree(ROOT / "src", self.root / "src", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "scripts", self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "examples/ace-rtl/environment", self.root / "examples/ace-rtl/environment",
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(ROOT / "Makefile", self.root / "Makefile")
        tools = self.root / "bin"
        tools.mkdir()
        for name in ("dirname", "sh", "sleep", "ps", "awk"):
            (tools / name).symlink_to(shutil.which(name, path=os.defpath))
        (tools / "python3").symlink_to(sys.executable)
        return {"PATH": str(tools), "HOME": str(self.root), "HTTPS_PROXY": "http://SECRET@proxy"}

    def test_direct_doctor_does_not_write_project_bytecode(self):
        environment = self.public_checkout()
        result = subprocess.run([sys.executable, "scripts/dev.py", "doctor", "--json"],
                                cwd=self.root, env=environment, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(list(self.root.rglob("*.pyc")), [])

    def test_public_make_and_direct_doctor_invalid_ca_and_no_project_bytecode(self):
        environment = self.public_checkout()
        for ca in (str(self.root / "missing-SECRET.pem"), ""):
            for command in ([sys.executable, "scripts/dev.py", "doctor", "--json"],
                            [shutil.which("make", path=os.defpath), "doctor", "ARGS=--json"]):
                with self.subTest(ca=bool(ca), command=command[0]):
                    result = subprocess.run(command, cwd=self.root, env={**environment, "AGENT_OPT_CA_BUNDLE": ca},
                                            text=True, capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    report = json.loads(result.stdout)
                    self.assertEqual(set(report), {"ready", "areas", "checks"})
                    checks = self.checks(report)
                    self.assertIn("network.configuration", checks)
                    self.assertEqual(checks["network.configuration"]["status"], "error" if ca else "ok")
                    self.assertEqual(checks["core.git"]["status"], "error")
                    self.assertNotIn("SECRET", result.stdout + result.stderr)
                    self.assertEqual(list(self.root.rglob("*.pyc")), [])

    def prepared(self):
        setup = self.adapter.setup
        payload = b"fixture\n"
        digest = hashlib.sha256(payload).hexdigest()
        patch.object(setup, "ASSETS", {name: digest for name in setup.ASSETS}).start()
        patch.object(setup, "REQUIREMENTS_SHA256", digest).start()
        paths = [".venv/bin/python", ".venv/bin/agent-opt", "external/cvdp-venv/bin/python",
                 "external/cvdp_benchmark/requirements.txt", setup.DRIVER_LOCK]
        paths += [f"external/cvdp-data/{setup.DATA_REVISION}/{name}" for name in setup.ASSETS]
        for relative in paths:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        for name in setup.REPOS:
            (self.root / "external" / name / ".git").mkdir(parents=True, exist_ok=True)
        self.lock = {
            "platform": "linux/amd64", "repos": {k: list(v) for k, v in setup.REPOS.items()},
            "dataset": {"revision": setup.DATA_REVISION, "files": {
                name: {"sha256": digest, "bytes": len(payload), "url": "https://example.invalid"}
                for name in setup.ASSETS}},
            "driver_requirements": {"path": setup.DRIVER_LOCK, "sha256": digest,
                                    "upstream_sha256": digest, "python": "3.12"},
            "driver_packages": "PyYAML==6.0.2\n", "opencode_version": "1.18.31",
            "images": {
                "evaluation": {"tag": "agent-optimizer-cvdp:8e894cf-amd64", "id": "sha256:" + "a" * 64},
                "agent": {"tag": "agent-optimizer-opencode:1.18.31-amd64", "id": "sha256:" + "b" * 64}},
        }
        self.write_lock()
        patch.object(self.doctor.shutil, "which", side_effect=lambda name, **kw: "/bin/" + name).start()
        patch.object(self.doctor.subprocess, "run", side_effect=self.execute).start()

    def write_lock(self):
        (self.root / "external/environment-lock.json").write_text(json.dumps(self.lock))

    def execute(self, argv, **kwargs):
        self.assertIs(kwargs["shell"], False)
        self.assertGreater(kwargs["timeout"], 0)
        self.assertTrue(kwargs["capture_output"])
        self.assertNotIn("PYTHONPATH", kwargs["env"])
        self.assertFalse(set(argv) & {"clone", "checkout", "sync", "pull"})
        self.assertNotEqual(argv[:2], ["docker", "build"])
        stdout = ""
        if argv[:2] in (["git", "--version"], ["uv", "--version"], ["docker", "--version"]):
            stdout = "version"
        elif argv[:2] == ["docker", "version"]:
            stdout = "linux/amd64"
        elif argv[:3] == ["docker", "compose", "version"]:
            stdout = "Compose version"
        elif argv[:3] == ["git", "rev-parse", "HEAD"]:
            stdout = self.adapter.setup.REPOS[Path(kwargs["cwd"]).name][1]
        elif argv[:2] == ["git", "status"]:
            stdout = ""
        elif argv[:3] == ["docker", "image", "inspect"]:
            image = next(i for i in self.lock["images"].values() if i["tag"] == argv[-1])
            stdout = json.dumps([{"Id": image["id"], "Os": "linux", "Architecture": "amd64"}])
        elif argv[:2] == ["docker", "run"]:
            self.assertEqual(argv[argv.index("--pull") + 1], "never")
            self.assertEqual(argv[argv.index("--network") + 1], "none")
            self.assertTrue(any(i["id"] in argv for i in self.lock["images"].values()))
            stdout = "1.18.31" if "opencode" in argv else "tools available"
        elif argv[:3] == ["docker", "rm", "--force"]:
            self.assertEqual(len(argv), 4)
            self.assertTrue(argv[3].startswith("agent-opt-doctor-"))
        elif argv[:4] == ["uv", "--offline", "pip", "freeze"]:
            stdout = "PyYAML==6.0.2\n"
        elif argv[0] == str(self.root / ".venv/bin/agent-opt"):
            self.assertEqual(argv[1:], ["--help"])
        elif argv[0] in (str(self.root / ".venv/bin/python"),
                         str(self.root / "external/cvdp-venv/bin/python")):
            self.assertIn("-I", argv)
            self.assertIn("-B", argv)
            if "version_info" in argv[-1]:
                stdout = "3.12"
        else:
            self.fail(f"Unexpected diagnostic command: {argv}")
        return subprocess.CompletedProcess(argv, 0, stdout, "SECRET_PROCESS_OUTPUT")

    def test_fresh_checkout_aggregates_independent_errors_without_writes(self):
        with patch.object(self.doctor.shutil, "which", return_value=None):
            report = self.doctor.collect_report(self.root)
        checks = self.checks(report)
        for name in ("core.git", "core.uv", "core.python", "docker.cli", "environment.lock",
                     "source.ACE-RTL", "source.cvdp_benchmark", "live.key", "live.model"):
            self.assertEqual(checks[name]["status"], "error", name)
        self.assertEqual(checks["docker.daemon"]["status"], "blocked")
        self.assertFalse(report["ready"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_core_report_never_loads_example_or_probes_docker_and_is_read_only(self):
        with patch.object(self.doctor, "example_adapter", side_effect=AssertionError("example loader")), \
                patch.object(self.doctor.shutil, "which", return_value=None), \
                patch.object(self.doctor.subprocess, "run", side_effect=AssertionError("unexpected probe")):
            report = self.doctor.collect_report(self.root, core_only=True)
        self.assertEqual(report["scope"], "core")
        self.assertEqual(report["areas"], {"core": False})
        self.assertFalse(report["ready"])
        self.assertFalse(any(c["id"].startswith(("docker.", "image.", "live.")) for c in report["checks"]))
        checks = self.checks(report)
        self.assertIn("network.configuration", checks)
        for name in ("core.uv", "core.python", "core.venv", "core.package", "core.cli", "core.ruff", "core.build"):
            self.assertIn("setup --core", checks[name]["remedy"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_core_ready_depends_only_on_core_and_network_with_scoped_human_output(self):
        for name in ("python", "agent-opt"):
            path = self.root / ".venv/bin" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        before = dict(os.environ)
        with patch.object(self.doctor, "example_adapter", side_effect=AssertionError("example loader")), \
                patch.object(self.doctor.shutil, "which", side_effect=lambda name, **k: "/bin/" + name), \
                patch.object(self.doctor.subprocess, "run", side_effect=self.execute):
            report = self.doctor.collect_report(self.root, core_only=True)
            self.assertEqual(report["areas"], {"core": True})
            self.assertTrue(report["ready"])
            with patch.dict(os.environ, {"AGENT_OPT_CA_BUNDLE": "missing-SECRET.pem"}):
                invalid = self.doctor.collect_report(self.root, core_only=True)
            self.assertFalse(invalid["ready"])
            self.assertEqual(self.checks(invalid)["core.python"]["status"], "ok")
            self.assertNotIn("SECRET", json.dumps(invalid))
        self.assertEqual(dict(os.environ), before)
        output = io.StringIO()
        with redirect_stdout(output):
            self.doctor.render_report(report)
        self.assertIn("코어 개발 환경: 준비됨", output.getvalue())
        self.assertIn("검사하지 않았습니다", output.getvalue())
        self.assertNotIn("Live checks validate", output.getvalue())

    def test_developer_doctor_human_language_does_not_change_json(self):
        report = {"scope": "core", "ready": True, "areas": {"core": True}, "checks": [
            {"id": "core.host", "status": "error",
             "message": "Host OS and diagnostic Python compatibility (Mac/Linux, Python >=3.11).",
             "remedy": "Use Mac or Ubuntu with Python >=3.11; run sh scripts/bootstrap.sh setup."}]}
        outputs = {}
        for language in ("ko", "en"):
            with patch.dict(os.environ, {"AGENT_OPT_LANG": language}):
                text = io.StringIO()
                with redirect_stdout(text):
                    self.doctor.render_report(report)
                outputs[language] = text.getvalue()
                machine = io.StringIO()
                with redirect_stdout(machine):
                    self.doctor.render_report(report, json_output=True)
                self.assertEqual(json.loads(machine.getvalue()), report)
        self.assertIn("코어 개발 환경: 준비됨", outputs["ko"])
        self.assertIn("호스트 OS와 진단 Python", outputs["ko"])
        self.assertIn("Mac 또는 Ubuntu", outputs["ko"])
        self.assertIn("Core development environment: ready", outputs["en"])

    def test_public_core_doctor_json_without_example_files(self):
        environment = self.public_checkout()
        shutil.rmtree(self.root / "examples")
        for command in ([sys.executable, "scripts/dev.py", "doctor", "--core", "--json"],
                        [shutil.which("make", path=os.defpath), "doctor", "ARGS=--core --json"]):
            with self.subTest(command=command):
                result = subprocess.run(command, cwd=self.root, env=environment,
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 2, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(set(report), {"scope", "ready", "areas", "checks"})
                self.assertEqual(report["scope"], "core")
                self.assertEqual(set(report["areas"]), {"core"})
                self.assertNotIn("SECRET", result.stdout + result.stderr)
        self.assertEqual(list(self.root.rglob("*.pyc")), [])
        self.assertFalse((self.root / "external").exists())

    def test_selected_doctor_json_is_single_read_only_document_with_dataset_area(self):
        environment = self.public_checkout()
        shutil.copytree(ROOT / "examples/benchmarks", self.root / "examples/benchmarks")
        shutil.copytree(ROOT / "experiments/sample-team", self.root / "experiments/sample-team")
        shutil.copyfile(ROOT / "examples/ace-rtl/prepare.py", self.root / "examples/ace-rtl/prepare.py")
        shutil.copyfile(ROOT / "examples/ace-rtl/evaluator.py", self.root / "examples/ace-rtl/evaluator.py")
        (self.root / "examples/minimal").mkdir()
        shutil.copyfile(ROOT / "examples/minimal/evaluator.py", self.root / "examples/minimal/evaluator.py")
        before = {str(p) for p in self.root.rglob("*")}
        command = ["sh", "scripts/bootstrap.sh", "doctor", "--dataset", "verilog-spec", "--json"]
        result = subprocess.run(command, cwd=self.root, env=environment,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["scope"], "dataset")
        self.assertEqual(set(report["areas"]), {"core", "dataset"})
        self.assertIn("dataset.verilog.provenance", self.checks(report))
        self.assertNotIn("SECRET", result.stdout + result.stderr)
        self.assertEqual({str(p) for p in self.root.rglob("*")}, before)
        self.assertFalse(any(p.endswith("/setup-logs") for p in before))

    def test_selected_doctor_skips_ace_and_uses_shared_checks(self):
        from agent_optimizer import readiness
        with patch.object(self.doctor, "example_adapter", side_effect=AssertionError("ACE loaded")), \
                patch.object(readiness, "collect_dataset", return_value={"scope": "dataset", "ready": True,
                    "checks": [{"id": "dataset.fixture", "area": "dataset", "status": "ok",
                                "message": "Fixture", "remedy": ""}]}):
            report = self.doctor.collect_report(self.root, dataset="sample_text")
        self.assertEqual(report["scope"], "dataset")
        self.assertEqual(self.checks(report)["dataset.fixture"]["status"], "ok")
        self.assertNotIn("evaluation", report["areas"])

    def test_malformed_cvdp_selected_platform_yields_actionable_check_not_traceback(self):
        setup = self.adapter.setup
        cache = self.root / "external/datasets/cvdp"
        cache.mkdir(parents=True)
        (cache / "evaluation-lock.json").write_text(json.dumps({
            "dataset": {"revision": setup.DATA_REVISION, "files": {}},
            "driver_requirements": {}, "driver_packages": "", "images": {"evaluation": {}},
            "repos": {"cvdp_benchmark": list(setup.REPOS["cvdp_benchmark"])},
            "simulator_verified": True, "platform": {"private": "SECRET"},
        }))
        rows = setup.evaluation_checks(cache)
        self.assertEqual(rows[0]["id"], "dataset.cvdp.lock")
        self.assertEqual(rows[0]["status"], "error")
        self.assertIn("prepare cvdp", rows[0]["remedy"])
        self.assertNotIn("SECRET", json.dumps(rows))

    def test_ready_does_not_require_live_but_live_requires_ready(self):
        self.prepared()
        report = self.doctor.collect_report(self.root)
        self.assertEqual(report["areas"], {"core": True, "evaluation": True, "live": False})
        self.assertTrue(report["ready"])
        with patch.dict(os.environ, {"AGENT_OPT_MODEL_API_KEY": "secret", "AGENT_OPT_MODEL_ENDPOINT": "https://example.invalid/chat/completion"}):
            self.assertTrue(self.doctor.collect_report(self.root)["areas"]["live"])
            (self.root / ".venv/bin/python").unlink()
            self.assertFalse(self.doctor.collect_report(self.root)["areas"]["live"])

    def test_corrupt_lock_types_do_not_abort_other_checks_or_expose_values(self):
        self.prepared()
        mutations = [None, [], {"platform": []}, {"images": []}, {"driver_packages": {}},
                     {"dataset": {"files": []}}, {"repos": []},
                     {"images": {"evaluation": {"tag": [], "id": 1}}}]
        for change in mutations:
            with self.subTest(change=change):
                value = {**self.lock, **change} if isinstance(change, dict) else change
                path = self.root / "external/environment-lock.json"
                path.write_text(json.dumps(value))
                report = self.doctor.collect_report(self.root)
                checks = self.checks(report)
                self.assertEqual(checks["environment.lock"]["status"], "error")
                self.assertEqual(checks["source.ACE-RTL"]["status"], "ok")
                self.assertIn("live.model", checks)
        path.write_text('{SECRET_CORRUPT_LOCK')
        report = self.doctor.collect_report(self.root)
        self.assertEqual(self.checks(report)["environment.lock"]["status"], "error")
        self.assertNotIn("SECRET", json.dumps(report))

    def test_timeouts_are_aggregated_and_dependents_blocked(self):
        self.prepared()
        def execute(argv, **kwargs):
            if argv[:2] == ["docker", "version"]:
                raise subprocess.TimeoutExpired(argv, 15, output="SECRET_TIMEOUT")
            return self.execute(argv, **kwargs)
        with patch.object(self.doctor.subprocess, "run", side_effect=execute):
            report = self.doctor.collect_report(self.root)
        checks = self.checks(report)
        self.assertEqual(checks["docker.daemon"]["status"], "error")
        self.assertEqual(checks["image.agent"]["status"], "blocked")
        self.assertEqual(checks["source.ACE-RTL"]["status"], "ok")
        self.assertNotIn("SECRET", json.dumps(report))

    def test_source_revision_and_dirty_state_fail_independently(self):
        self.prepared()
        for command, stdout in (("rev-parse", "0" * 40), ("status", " M file")):
            def execute(argv, **kwargs):
                if argv[:2] == ["git", command]:
                    return subprocess.CompletedProcess(argv, 0, stdout, "")
                return self.execute(argv, **kwargs)
            with self.subTest(command=command), patch.object(self.doctor.subprocess, "run", side_effect=execute):
                checks = self.checks(self.doctor.collect_report(self.root))
                self.assertEqual(checks["source.ACE-RTL"]["status"], "error")

    def test_assets_and_driver_lock_drift_are_errors(self):
        self.prepared()
        paths = [(f"external/cvdp-data/{self.adapter.setup.DATA_REVISION}/LICENSE", "data.LICENSE"),
                 (self.adapter.setup.DRIVER_LOCK, "driver.lock"),
                 ("external/cvdp_benchmark/requirements.txt", "driver.lock")]
        for relative, name in paths:
            path = self.root / relative
            original = path.read_bytes()
            path.write_text("drift")
            checks = self.checks(self.doctor.collect_report(self.root))
            self.assertEqual(checks[name]["status"], "error")
            path.write_bytes(original)

    def test_driver_packages_drift_and_wrong_python_are_errors(self):
        self.prepared()
        for target in ("packages", "python"):
            def execute(argv, **kwargs):
                if target == "packages" and "freeze" in argv:
                    return subprocess.CompletedProcess(argv, 0, "PyYAML==0.0.0", "")
                if target == "python" and "cvdp-venv" in argv[0] and "version_info" in argv[-1]:
                    return subprocess.CompletedProcess(argv, 0, "3.11", "")
                return self.execute(argv, **kwargs)
            with self.subTest(target=target), patch.object(self.doctor.subprocess, "run", side_effect=execute):
                checks = self.checks(self.doctor.collect_report(self.root))
                self.assertEqual(checks[f"driver.{target}"]["status"], "error")

    def test_both_image_identities_platforms_and_missing_images_are_rejected(self):
        self.prepared()
        for name in ("evaluation", "agent"):
            for info in ([], [{"Id": "sha256:" + "c" * 64, "Os": "linux", "Architecture": "amd64"}],
                         [{"Id": self.lock["images"][name]["id"], "Os": "linux", "Architecture": "arm64"}]):
                def execute(argv, **kwargs):
                    if argv[:3] == ["docker", "image", "inspect"] and argv[-1] == self.lock["images"][name]["tag"]:
                        return subprocess.CompletedProcess(argv, 0, json.dumps(info), "")
                    return self.execute(argv, **kwargs)
                with self.subTest(name=name, info=info), patch.object(self.doctor.subprocess, "run", side_effect=execute):
                    report = self.doctor.collect_report(self.root)
                    checks = self.checks(report)
                    self.assertEqual(checks[f"image.{name}"]["status"], "error")
                    self.assertFalse(report["ready"])
                    tool = "evaluation" if name == "evaluation" else "opencode"
                    self.assertEqual(checks[f"tools.{tool}"]["status"], "blocked")
                    dev = module("dev_image_doctor", ROOT / "scripts/dev.py")
                    with patch.object(dev, "ROOT", self.root), patch.object(dev, "load", return_value=self.doctor), \
                            redirect_stdout(io.StringIO()):
                        self.assertEqual(dev.main(["doctor", "--json"]), 2)

    def test_valid_images_cannot_mask_failed_actual_tools(self):
        self.prepared()
        def execute(argv, **kwargs):
            if argv[:2] == ["docker", "run"]:
                return subprocess.CompletedProcess(argv, 1, "SECRET", "SECRET")
            return self.execute(argv, **kwargs)
        with patch.object(self.doctor.subprocess, "run", side_effect=execute):
            report = self.doctor.collect_report(self.root)
        checks = self.checks(report)
        self.assertEqual(checks["image.evaluation"]["status"], "ok")
        self.assertEqual(checks["tools.evaluation"]["status"], "error")
        self.assertEqual(checks["tools.opencode"]["status"], "error")
        self.assertFalse(report["ready"])

    def test_json_cli_is_single_secret_free_document_and_read_only(self):
        self.prepared()
        dev = module("dev_doctor_cli_test", ROOT / "scripts/dev.py")
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        output = io.StringIO()
        with patch.object(dev, "ROOT", self.root), redirect_stdout(output), \
                patch.dict(os.environ, {"OPENROUTER_API_KEY": "SECRET_KEY", "AGENT_OPT_MODEL": "SECRET_MODEL"}), \
                patch.object(self.adapter.setup, "prepare_sources", side_effect=AssertionError("mutation")), \
                patch.object(self.adapter.setup, "prepare_data", side_effect=AssertionError("mutation")):
            code = dev.main(["doctor", "--json", "--platform", "SECRET_PLATFORM"])
        report = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(report["ready"])
        self.assertNotIn("SECRET", output.getvalue())
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_human_render_and_success_cli(self):
        self.prepared()
        report = self.doctor.collect_report(self.root)
        output = io.StringIO()
        with redirect_stdout(output):
            self.doctor.render_report(report)
        self.assertIn("core", output.getvalue())
        self.assertIn("live", output.getvalue())
        self.assertIn("AGENT_OPT_MODEL_API_KEY", output.getvalue())
        dev = module("dev_doctor_success_test", ROOT / "scripts/dev.py")
        # Keep the real collector/renderer, using the prepared adapter fixture.
        with patch.object(dev, "ROOT", self.root), patch.object(dev, "load", return_value=self.doctor), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(dev.main(["doctor", "--json"]), 0)

    def test_uninstalled_project_cannot_be_masked_by_inherited_pythonpath(self):
        venv.EnvBuilder(with_pip=False, symlinks=True).create(self.root / ".venv")
        with patch.object(self.doctor.shutil, "which", return_value=None), \
                patch.dict(os.environ, {"PYTHONPATH": str(ROOT / "src")}):
            report = self.doctor.collect_report(self.root)
        checks = self.checks(report)
        self.assertEqual(checks["core.package"]["status"], "error")
        self.assertFalse(report["areas"]["core"])

    def test_missing_git_and_uv_block_only_dependent_existing_checks(self):
        self.prepared()
        with patch.object(self.doctor.shutil, "which", side_effect=lambda name, **kw: None if name in {"git", "uv"} else "/bin/" + name):
            checks = self.checks(self.doctor.collect_report(self.root))
        self.assertEqual(checks["source.ACE-RTL"]["status"], "blocked")
        self.assertEqual(checks["driver.packages"]["status"], "blocked")
        self.assertEqual(checks["data.LICENSE"]["status"], "ok")

    def test_plain_interpreter_symlink_is_not_a_project_virtualenv(self):
        import sys
        python = self.root / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        python.symlink_to(Path(sys.executable).resolve())
        with patch.object(self.doctor.shutil, "which", return_value=None):
            checks = self.checks(self.doctor.collect_report(self.root))
        self.assertIn("core.venv", checks)
        self.assertEqual(checks["core.venv"]["status"], "error")

    def test_malformed_platform_and_lock_values_never_escape_json(self):
        self.prepared()
        for change in ({"platform": "SECRET_PLATFORM"}, {"opencode_version": "SECRET_VERSION"},
                       {"images": {"agent": {"id": "SECRET_ID", "tag": "SECRET_TAG"}}}):
            with self.subTest(change=change):
                value = {**self.lock, **change}
                (self.root / "external/environment-lock.json").write_text(json.dumps(value))
                report = self.doctor.collect_report(self.root, "SECRET_ARGUMENT")
                self.assertFalse(report["ready"])
                self.assertNotIn("SECRET", json.dumps(report))

    def test_missing_lock_cli_still_collects_core_data_and_live(self):
        dev = module("dev_doctor_fresh_cli", ROOT / "scripts/dev.py")
        output = io.StringIO()
        with patch.object(dev, "ROOT", self.root), patch.object(self.doctor.shutil, "which", return_value=None), \
                redirect_stdout(output), patch("sys.argv", ["dev.py", "doctor", "--json"]):
            self.assertEqual(dev.main(), 2)
        checks = self.checks(json.loads(output.getvalue()))
        self.assertEqual(checks["environment.lock"]["status"], "error")
        self.assertEqual(checks["core.python"]["status"], "error")
        self.assertEqual(checks["data.LICENSE"]["status"], "error")
        self.assertEqual(checks["live.model"]["status"], "error")
        self.assertEqual(list(self.root.iterdir()), [])

    def container_lifecycle(self, outcome):
        self.prepared()
        running = {"unrelated-sentinel"}
        started, removed = [], []

        def execute(argv, **kwargs):
            self.assertNotIn("prune", argv)
            self.assertNotIn("ps", argv, "cleanup must not discover unrelated containers")
            if argv[:2] == ["docker", "run"]:
                name = argv[argv.index("--name") + 1] if "--name" in argv else "unnamed"
                self.assertNotIn(name, running)
                started.append(name)
                running.add(name)
                if outcome == "timeout":
                    raise subprocess.TimeoutExpired(argv, 120, output="SECRET_TIMEOUT")
                if outcome == "interrupt":
                    raise KeyboardInterrupt()
                result = self.execute(argv, **kwargs)
                # --rm may have removed a normally exited container already.
                running.remove(name)
                return result
            if argv[:2] == ["docker", "rm"]:
                self.assertEqual(argv, ["docker", "rm", "--force", started[-1]])
                self.assertIs(kwargs["shell"], False)
                self.assertTrue(kwargs["capture_output"])
                self.assertGreater(kwargs["timeout"], 0)
                self.assertLessEqual(kwargs["timeout"], 15)
                removed.append(argv[-1])
                existed = argv[-1] in running
                running.discard(argv[-1])
                return subprocess.CompletedProcess(argv, 0 if existed else 1, "", "SECRET_CLEANUP")
            return self.execute(argv, **kwargs)

        with patch.object(self.doctor.subprocess, "run", side_effect=execute):
            if outcome == "interrupt":
                with self.assertRaises(KeyboardInterrupt):
                    self.doctor.collect_report(self.root)
            else:
                report = self.doctor.collect_report(self.root)
                self.assertEqual(report["ready"], outcome == "normal")
                self.assertNotIn("SECRET", json.dumps(report))
        self.assertEqual(running, {"unrelated-sentinel"})
        self.assertEqual(removed, started)
        self.assertEqual(len(started), 1 if outcome == "interrupt" else 2)
        self.assertEqual(len(started), len(set(started)))
        for name in started:
            self.assertRegex(name, r"^agent-opt-doctor-[0-9a-f]{32}$")

    def test_tool_timeout_removes_only_owned_containers(self):
        self.container_lifecycle("timeout")

    def test_tool_interrupt_removes_owned_container_before_propagating(self):
        self.container_lifecycle("interrupt")

    def test_normal_tools_cleanup_is_scoped_and_tolerates_auto_removal(self):
        self.container_lifecycle("normal")
