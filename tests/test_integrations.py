import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agent_optimizer.contracts import AgentSpec, SourceSpec, ExecutionResult, UnavailableError, ConfigurationError
from agent_optimizer.sources import materialize_agent
from support import ROOT, module

prepare = module("ace_prepare", ROOT / "examples/ace-rtl/prepare.py")
cvdp = module("ace_evaluator", ROOT / "examples/ace-rtl/evaluator.py")

def row():
    return {"id": "demo", "categories": ["cid003", "easy"],
            "input": {"prompt": "Implement public spec", "context": {}},
            "output": {"response": "SECRET", "context": {"rtl/dut.sv": "SECRET"}},
            "harness": {"files": {"Dockerfile": "FROM __OSS_SIM_IMAGE__\n", "src/test.py": "PRIVATE_TEST",
                                  "docker-compose.yml": "services:\n  direct:\n    build: .\n"}}}

class SourceTests(unittest.TestCase):
    def test_git_url_rewrite_preserves_pinned_source_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "mirror"
            repo.mkdir()

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()

            git("init", "-q")
            (repo / "prompt.md").write_text("pinned content")
            git("add", "prompt.md")
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "pinned")
            revision = git("rev-parse", "HEAD")
            (repo / "prompt.md").write_text("later content")
            git("add", "prompt.md")
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "later")
            public_url = "https://github.com/example/pinned-agent.git"
            agent = AgentSpec("test", root, None, "test", ("command",), ("*.md",), "prompt.md",
                              source=SourceSpec("git", url=public_url, revision=revision,
                                                timeout_seconds=10))
            rewrite = {"GIT_CONFIG_COUNT": "1",
                       "GIT_CONFIG_KEY_0": f"url.file://{repo}.insteadOf",
                       "GIT_CONFIG_VALUE_0": public_url}
            with patch.dict(os.environ, rewrite):
                resolved, lock = materialize_agent(agent, root / "snapshot")
                wrong = AgentSpec("test", root, None, "test", ("command",), ("*.md",), "prompt.md",
                                  source=SourceSpec("git", url=public_url, revision="0" * 40,
                                                    timeout_seconds=10))
                with self.assertRaises(UnavailableError):
                    materialize_agent(wrong, root / "wrong-revision")
            self.assertEqual((resolved.bundle / "prompt.md").read_text(), "pinned content")
            self.assertEqual(lock["url"], public_url)
            self.assertEqual(lock["requested_commit"], revision)
            self.assertEqual(lock["resolved_commit"], revision)
            self.assertEqual(json.loads((root / "snapshot/source-lock.json").read_text())
                             ["resolved_commit"], revision)
            self.assertFalse((root / "wrong-revision").exists())

    def test_git_source_pinned_and_original_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); repo = root / "repo"; repo.mkdir()
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()
            git("init", "-q")
            (repo / "prompt.md").write_text("original")
            git("add", ".")
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "initial")
            sha = git("rev-parse", "HEAD")
            (repo / "prompt.md").write_text("uncommitted")
            agent = AgentSpec("test", root, None, "test", ("command",), ("*.md",), "prompt.md",
                              source=SourceSpec("git", url=str(repo), revision=sha))
            resolved, lock = materialize_agent(agent, root / "snapshot")
            self.assertEqual((resolved.bundle / "prompt.md").read_text(), "original")
            self.assertEqual((repo / "prompt.md").read_text(), "uncommitted")
            self.assertEqual(lock["resolved_commit"], sha)

    def test_local_secrets_and_ide_files_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / "source"; source.mkdir()
            (source / "prompt.md").write_text("public")
            (source / ".env").write_text("secret")
            (source / ".codex").mkdir()
            (source / ".codex/auth.json").write_text("secret")
            agent = AgentSpec("test", root, None, "test", ("command",), ("*.md",), "prompt.md",
                              source=SourceSpec("local", path=source))
            resolved, _ = materialize_agent(agent, root / "snapshot")
            self.assertFalse((resolved.bundle / ".env").exists())
            self.assertFalse((resolved.bundle / ".codex").exists())


class OptionalIntegrationTests(unittest.TestCase):
    def test_selected_integration_excludes_generated_bytecode(self):
        from agent_optimizer.integrations import selected_files

        with tempfile.TemporaryDirectory(prefix="pinned-bytecode-") as directory:
            root = Path(directory)
            repo, _ = self.pinned_fixture(root)
            generated = repo / "examples/ace-rtl/__pycache__/adapter.cpython-312.pyc"
            generated.parent.mkdir()
            generated.write_bytes(b"transient bytecode")
            selected = {path.relative_to(repo).as_posix() for path in selected_files(repo, "ace-rtl")}
            self.assertIn("examples/ace-rtl/adapter.py", selected)
            self.assertNotIn("examples/ace-rtl/__pycache__/adapter.cpython-312.pyc", selected)

    def pinned_fixture(self, root):
        repo = root / "first-party"
        for relative in ("examples/ace-rtl/adapter.py", "examples/ace-rtl/environment/lifecycle.py",
                         "examples/rtl-debugger/Dockerfile", "examples/benchmarks/cvdp.py",
                         "experiments/simple-feedback/optimizer.py", "src/agent_optimizer/models.py"):
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(relative)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "pinned"], check=True)
        revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                           text=True).strip()
        return repo, revision

    def test_acquire_optional_integration_is_pinned_and_reusable_offline(self):
        from agent_optimizer.integrations import acquire_integration

        with tempfile.TemporaryDirectory(prefix="pinned-integration-") as directory:
            root = Path(directory)
            repo, revision = self.pinned_fixture(root)
            workspace = root / "workspace"
            workspace.mkdir()
            cache = root / "cache"
            result = acquire_integration(workspace, "ace-rtl", source_url=str(repo),
                                         revision=revision, cache_dir=cache)
            self.assertEqual(result["revision"], revision)
            self.assertEqual((workspace / "examples/ace-rtl/adapter.py").read_text(),
                             "examples/ace-rtl/adapter.py")
            self.assertFalse((workspace / ".agent-opt/integration-ready.json").exists())
            reused = acquire_integration(workspace, "ace-rtl", source_url=str(repo),
                                         revision=revision, cache_dir=cache, offline=True)
            self.assertEqual(reused["revision"], revision)

    def test_acquire_optional_integration_rejects_conflicts_and_missing_offline_cache(self):
        from agent_optimizer.integrations import acquire_integration

        with tempfile.TemporaryDirectory(prefix="pinned-integration-") as directory:
            root = Path(directory)
            repo, revision = self.pinned_fixture(root)
            workspace = root / "workspace"
            workspace.mkdir()
            with self.assertRaises(UnavailableError):
                acquire_integration(workspace, "ace-rtl", source_url=str(repo), revision=revision,
                                    cache_dir=root / "cache", offline=True)
            conflict = workspace / "examples/ace-rtl/adapter.py"
            conflict.parent.mkdir(parents=True)
            conflict.write_text("user-owned")
            with self.assertRaises(ConfigurationError):
                acquire_integration(workspace, "ace-rtl", source_url=str(repo), revision=revision,
                                    cache_dir=root / "cache")
            self.assertEqual(conflict.read_text(), "user-owned")
            self.assertFalse((workspace / ".agent-opt/integration-ready.json").exists())

    def test_acquire_optional_integration_rejects_metadata_symlink(self):
        from agent_optimizer.integrations import acquire_integration

        with tempfile.TemporaryDirectory(prefix="pinned-symlink-") as directory:
            root = Path(directory)
            repo, revision = self.pinned_fixture(root)
            workspace = root / "workspace"
            workspace.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (workspace / ".agent-opt").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ConfigurationError):
                acquire_integration(workspace, "ace-rtl", source_url=str(repo), revision=revision,
                                    cache_dir=root / "cache")
            self.assertEqual(list(outside.iterdir()), [])

    def test_acquire_optional_integration_requires_each_reviewed_directory(self):
        from agent_optimizer.integrations import acquire_integration

        with tempfile.TemporaryDirectory(prefix="pinned-missing-") as directory:
            root = Path(directory)
            repo, _ = self.pinned_fixture(root)
            shutil.rmtree(repo / "examples/benchmarks")
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture",
                            "-c", "user.email=test@example.invalid", "commit", "-qm", "missing"], check=True)
            revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                               text=True).strip()
            workspace = root / "workspace"
            workspace.mkdir()
            with self.assertRaises(ConfigurationError):
                acquire_integration(workspace, "ace-rtl", source_url=str(repo), revision=revision,
                                    cache_dir=root / "cache")
            self.assertFalse((workspace / "examples/ace-rtl/adapter.py").exists())

    def test_acquire_optional_integration_uses_selected_cache_directory(self):
        from agent_optimizer.integrations import acquire_integration

        with tempfile.TemporaryDirectory(prefix="selected-cache-") as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            revision = "a" * 40

            def selected_cache(target, url, commit, *, offline=False):
                self.assertEqual(target, root / "cache/agent-optimizer/integrations" / revision)
                raise UnavailableError("cache path observed")

            with patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}), \
                    patch("agent_optimizer.integrations.acquire_pinned_git", side_effect=selected_cache):
                with self.assertRaisesRegex(UnavailableError, "cache path observed"):
                    acquire_integration(workspace, "ace-rtl", source_url=str(root / "repo"),
                                        revision=revision)

    def test_ready_ace_workspace_registers_only_pinned_integration_components(self):
        from agent_optimizer.catalog import INTEGRATIONS
        from agent_optimizer.registry import Registry

        with tempfile.TemporaryDirectory(prefix="ace-components-") as directory:
            root = Path(directory)
            files = {}
            for relative in ("examples/ace-rtl/evaluator.py",
                             "examples/ace-rtl/environment/network_driver.py",
                             "examples/ace-rtl/prepare.py",
                             "examples/ace-rtl/environment/setup.py",
                             "examples/benchmarks/cvdp.py"):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
                files[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
            marker = root / ".agent-opt/integration-ready.json"
            marker.parent.mkdir()
            revision = INTEGRATIONS["ace-rtl"]["revision"]
            marker.write_text(json.dumps({"ready": True, "id": "ace-rtl", "revision": revision,
                                          "contract": 1, "url": INTEGRATIONS["ace-rtl"]["url"],
                                          "files": files}))
            registry = Registry()
            registry.load_project(root)
            self.assertEqual(registry.resolve("evaluators", "cvdp").__name__, "CVDPEvaluator")
            self.assertNotIn("sample_eval", registry.factories["evaluators"])

class CVDPTests(unittest.TestCase):
    def test_public_inputs_never_contain_solution_or_harness(self):
        tasks, excluded = prepare.convert([row()])
        self.assertFalse(excluded)
        public = json.dumps({k: tasks[0][k] for k in ["prompt", "files"]})
        self.assertNotIn("SECRET", public)
        self.assertNotIn("PRIVATE_TEST", public)
        self.assertNotIn("SECRET", json.dumps(tasks))
        self.assertIn("PRIVATE_TEST", json.dumps(tasks[0]["evaluation"]))

    def test_commercial_and_unreviewed_images_excluded(self):
        commercial = row(); commercial["harness"]["files"]["command"] = "xrun -64bit"
        unreviewed = row(); unreviewed["harness"]["files"]["Dockerfile"] = "FROM other/image"
        tasks, excluded = prepare.convert([commercial, unreviewed])
        self.assertEqual(tasks, [])
        self.assertEqual(len(excluded), 2)

    def test_empty_official_results_are_not_pass(self):
        from agent_optimizer.contracts import Task
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); out = root / "evaluation"; (out / "rtl").mkdir(parents=True)
            (out / "rtl/dut.sv").write_text("module dut; endmodule")
            task = Task(**prepare.convert([row()])[0][0])
            def execute(argv, cwd, logs, timeout, env=None):
                prefix = Path(argv[-1]); prefix.mkdir(parents=True)
                (prefix / "raw_result.json").write_text(json.dumps({"demo": {"tests": []}}))
                return ExecutionResult("completed", 0, 0.1, "out", "err")
            with patch.object(cvdp, "run_process", side_effect=execute), patch.object(cvdp, "cleanup_network"):
                result = cvdp.CVDPEvaluator().evaluate(task, out, 10)
            self.assertEqual(result.status, "infrastructure_error")
            self.assertIsNone(result.metrics["passed"])

    def test_official_tests_score_candidate_not_agent_claim(self):
        from agent_optimizer.contracts import Task
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); out = root / "evaluation"; (out / "rtl").mkdir(parents=True)
            (out / "rtl/dut.sv").write_text("CANDIDATE_RTL")
            (out / "success.json").write_text('{"passed":true}')
            task = Task(**prepare.convert([row()])[0][0])
            def execute(argv, cwd, logs, timeout, env=None):
                submission = json.loads(Path(argv[argv.index("-f")+1]).read_text())
                self.assertEqual(submission["output"]["context"]["rtl/dut.sv"], "CANDIDATE_RTL")
                prefix = Path(argv[-1]); prefix.mkdir(parents=True)
                (prefix / "raw_result.json").write_text(json.dumps({"demo": {"tests": [{"result": 0}, {"result": 1}]}}))
                return ExecutionResult("completed", 0, 0.1, "out", "err")
            with patch.object(cvdp, "run_process", side_effect=execute), patch.object(cvdp, "cleanup_network"):
                result = cvdp.CVDPEvaluator().evaluate(task, out, 10)
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.metrics["passed"], 0)

if __name__ == "__main__":
    unittest.main()
