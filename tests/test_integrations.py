import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agent_optimizer.contracts import AgentSpec, SourceSpec, ExecutionResult, UnavailableError
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
