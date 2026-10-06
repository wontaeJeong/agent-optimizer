from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import unittest
from contextlib import contextmanager, redirect_stdout
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent_optimizer.config import load_agent, read_toml
from agent_optimizer.contracts import RunRequest, Task
from agent_optimizer.registry import Registry
from agent_optimizer.results import EventStore
from agent_optimizer.runner import Budget, GroupRunner
from agent_optimizer.sources import materialize_agent
from agent_optimizer.workspace import CandidateStore, copy_tree
from support import ROOT, module


EXAMPLE = ROOT / "examples/model-rtl-agent"
RTL = "module example(output logic ready); assign ready = 1'b1; endmodule\n"


@contextmanager
def model_server(status=200, content=RTL, message=None):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            requests.append({"path": self.path, "auth": self.headers.get("Authorization"),
                             "body": json.loads(self.rfile.read(int(self.headers["Content-Length"])))})
            payload = json.dumps({"choices": [{"message": message if message is not None else
                                                {"role": "assistant", "content": content},
                                                "finish_reason": "stop"}]}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


class ModelRTLAgentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.assertTrue((EXAMPLE / "agent/src/agent.py").is_file())
        self.spec = load_agent(EXAMPLE / "agent.toml")
        self.profile = read_toml(EXAMPLE / "harness.toml")
        self.assertEqual(self.spec.supported_harnesses, (self.profile["adapter"],))
        self.assertEqual(self.spec.editable, ("prompts/system.md", "src/agent.py"))
        self.assertEqual(self.profile["runtime"], {"kind": "local"})
        self.assertTrue(self.profile["allow_local"])
        self.assertEqual(self.profile["command"],
                         ["{python}", "{agent_dir}/src/agent.py", "{task_dir}"])
        self.source = self.root / "original"
        shutil.copytree(EXAMPLE / "agent", self.source)
        (self.source / ".env").write_text("fixture credential material must stay out of snapshots")
        (self.source / "credentials.json").write_text("fixture credential material")
        self.source_sha = hashlib.sha256((self.source / "src/agent.py").read_bytes()).hexdigest()
        self.spec = replace(self.spec, source=replace(self.spec.source, path=self.source))
        self.spec, _ = materialize_agent(self.spec, self.root / "source")
        self.store = CandidateStore(self.root / "candidates", self.spec)
        self.baseline = self.store.create()
        self.workspace = self.root / "trial" / "agent_workspace"
        self.workspace.mkdir(parents=True)
        copy_tree(self.baseline.path, self.workspace / "agent")
        self.assertFalse((self.workspace / "agent/.env").exists())
        self.assertFalse((self.workspace / "agent/credentials.json").exists())
        self.task = self.workspace / "task"
        (self.task / "rtl").mkdir(parents=True)
        (self.task / "rtl/example.sv").write_text("", encoding="utf-8")
        self.private = self.root / "private" / "evaluator.json"
        self.private.parent.mkdir()
        self.private.write_text('{"secret": "fixture-only"}', encoding="utf-8")
        self.original = EXAMPLE / "agent/src/agent.py"
        self.original_sha = hashlib.sha256(self.original.read_bytes()).hexdigest()
        self.private_sha = hashlib.sha256(self.private.read_bytes()).hexdigest()
        registry = Registry()
        registry.load_plugins(ROOT, {"harnesses": {
            "model_rtl_command": "examples/model-rtl-agent/adapter.py:ModelRTLCommand"}})
        self.harness = registry.resolve("harnesses", "model_rtl_command")()

    def request(self, declaration="rtl/example.sv", introduction="Implement the public module."):
        system = (self.workspace / "agent/prompts/system.md").read_text(encoding="utf-8")
        prompt = (system + "\n\n" + introduction + "\nWrite target files: " + declaration +
                  "\nTask files are in ./task. Modify only task outputs.")
        return RunRequest(self.workspace, self.workspace / "agent", self.task, prompt, 1, 15,
                          self.profile, self.root / "logs")

    def assert_untouched(self):
        self.assertEqual(hashlib.sha256(self.original.read_bytes()).hexdigest(), self.original_sha)
        self.assertEqual(hashlib.sha256((self.source / "src/agent.py").read_bytes()).hexdigest(), self.source_sha)
        self.assertEqual(hashlib.sha256(self.private.read_bytes()).hexdigest(), self.private_sha)
        self.assertEqual([p.relative_to(self.task).as_posix() for p in self.task.rglob("*") if p.is_file()],
                         ["rtl/example.sv"])

    def test_public_prompt_snapshot_code_and_system_prompt_reach_model_and_only_target_changes(self):
        with model_server() as (url, requests), patch.dict(os.environ, {
            "DEMO_AGENT_MODEL_BASE_URL": url, "DEMO_AGENT_MODEL_ID": "fixture-rtl",
            "DEMO_AGENT_MODEL_API_KEY": "fixture-only-token",
            "AGENT_OPT_MODEL_BASE_URL": "https://wrong.example/v1",
            "AGENT_OPT_MODEL_API_KEY": "wrong-token",
        }):
            result = self.harness.run(self.request(introduction=(
                "Documented example: Write target files: rtl/other.sv\nImplement the public module.")))
        self.assertEqual(result.status, "completed", Path(result.stderr_path).read_text())
        self.assertEqual((self.task / "rtl/example.sv").read_text(), RTL)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["path"], "/v1/chat/completions")
        self.assertEqual(requests[0]["auth"], "Bearer fixture-only-token")
        self.assertEqual(requests[0]["body"]["model"], "fixture-rtl")
        self.assertEqual(requests[0]["body"]["messages"], [
            {"role": "system", "content": (self.workspace / "agent/prompts/system.md").read_text()},
            {"role": "user", "content": self.request().prompt.replace(
                "Implement the public module.",
                "Documented example: Write target files: rtl/other.sv\nImplement the public module.")},
        ])
        output = json.loads(Path(result.stdout_path).read_text())
        self.assertEqual(output["agent_sha256"], hashlib.sha256(
            (self.workspace / "agent/src/agent.py").read_bytes()).hexdigest())
        self.assertEqual(output["target"], "rtl/example.sv")
        self.assertEqual(output["model"], "fixture-rtl")
        self.assertNotIn("fixture-only-token", Path(result.stdout_path).read_text())
        self.assertNotIn("fixture-only-token", Path(result.stderr_path).read_text())
        self.assert_untouched()

    def test_edited_candidate_code_and_prompt_are_executed_from_snapshot(self):
        changed_prompt = "Candidate system prompt: emit the entire public RTL module.\n"
        changed_code = (self.baseline.path / "src/agent.py").read_text() + "\n# Candidate-specific revision\n"
        child = self.store.create(self.baseline, {"src/agent.py": changed_code,
                                                  "prompts/system.md": changed_prompt}, "fixture")
        copy_tree(child.path, self.workspace / "agent")
        with model_server() as (url, requests), patch.dict(os.environ, {
            "DEMO_AGENT_MODEL_BASE_URL": url, "DEMO_AGENT_MODEL_ID": "fixture-rtl",
            "DEMO_AGENT_MODEL_API_KEY": "fixture-only-token",
        }):
            result = self.harness.run(self.request())
        self.assertEqual(result.status, "completed")
        self.assertEqual(requests[0]["body"]["messages"][0]["content"], changed_prompt)
        output = json.loads(Path(result.stdout_path).read_text())
        self.assertEqual(output["agent_sha256"], hashlib.sha256(changed_code.encode()).hexdigest())
        self.assertNotEqual(output["agent_sha256"], self.original_sha)
        self.assertEqual((self.task / "rtl/example.sv").read_text(), RTL)
        self.assert_untouched()

    def test_agent_worker_deadline_is_120_and_timeout_leaves_target_empty(self):
        request = self.request()
        (self.workspace / "request.json").write_text(json.dumps({"prompt": request.prompt}), encoding="utf-8")
        agent = module("fixture_model_rtl_deadline", self.workspace / "agent/src/agent.py")
        deadlines = []

        def delayed_worker(argv, **kwargs):
            self.assertEqual(argv[-2:], ["agent_optimizer.models", "--request"])
            deadlines.append((kwargs["timeout"], json.loads(kwargs["input"])["timeout"]))
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

        output = StringIO()
        with patch.dict(os.environ, {"DEMO_AGENT_MODEL_BASE_URL": "http://localhost:1234/v1",
                                  "DEMO_AGENT_MODEL_ID": "fixture-rtl",
                                  "DEMO_AGENT_MODEL_API_KEY": "fixture-only-token"}, clear=True), \
                patch("sys.argv", ["agent.py", str(self.task)]), \
                patch.object(agent.Path, "cwd", return_value=self.workspace), \
                patch("agent_optimizer.models.subprocess.run", side_effect=delayed_worker), \
                redirect_stdout(output):
            with self.assertRaises(SystemExit) as failure:
                agent.main()
        self.assertEqual(failure.exception.code, 2)
        self.assertEqual(deadlines, [(120, 120)])
        self.assertEqual(json.loads(output.getvalue()), {"status": "model_unavailable"})
        self.assertEqual((self.task / "rtl/example.sv").read_text(encoding="utf-8"), "")
        self.assert_untouched()

    def test_missing_model_configuration_maps_to_null_official_score_in_runner(self):
        registry = Registry()
        registry.load_plugins(ROOT, {"harnesses": {
            "model_rtl_command": "examples/model-rtl-agent/adapter.py:ModelRTLCommand"},
            "evaluators": {"sample_eval": "examples/minimal/evaluator.py:TextFixtureEvaluator"}})
        experiment = {"_root": ROOT, "_benchmark_metadata": {}, "_tasks": [], "name": "fixture",
                      "evaluator": "sample_eval", "plugins": {}, "seed": 0}
        group = GroupRunner(experiment, self.spec, self.profile, self.root / "group", registry,
                            Budget({"trial_timeout_seconds": 15}), EventStore(self.root / "events.jsonl"))
        candidate = group.candidates.create()
        task = Task("public", "train", "Implement the public module.\nWrite target files: rtl/example.sv",
                    {"rtl/example.sv": ""}, {})
        with patch.dict(os.environ, {"DEMO_AGENT_MODEL_BASE_URL": "", "DEMO_AGENT_MODEL_ID": "",
                                     "DEMO_AGENT_MODEL_API_KEY": ""}):
            record = group.trial(candidate, task, 0)
        self.assertEqual(record["status"], "infrastructure_error")
        self.assertIsNone(record["metrics"]["passed"])
        self.assertFalse(record["valid"])
        self.assertEqual(record["execution"]["returncode"], 2)
        self.assertIsNone(record["execution"]["metrics"]["agent_tokens"])
        self.assertIsNone(record["execution"]["metrics"]["agent_cost_usd"])
        self.assertEqual(json.loads(Path(record["execution"]["stdout_path"]).read_text()),
                         {"status": "model_unavailable"})
        self.assert_untouched()

    def test_http_auth_failure_is_infrastructure_error_without_credential_in_logs(self):
        with model_server(status=401) as (url, requests), patch.dict(os.environ, {
            "DEMO_AGENT_MODEL_BASE_URL": url, "DEMO_AGENT_MODEL_ID": "fixture-rtl",
            "DEMO_AGENT_MODEL_API_KEY": "fixture-only-token",
        }):
            result = self.harness.run(self.request())
        self.assertEqual(result.status, "infrastructure_error")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(len(requests), 1)
        self.assertEqual((self.task / "rtl/example.sv").read_text(), "")
        self.assertNotIn("fixture-only-token", Path(result.stdout_path).read_text())
        self.assertNotIn("fixture-only-token", Path(result.stderr_path).read_text())
        self.assert_untouched()

    def test_unsafe_or_unavailable_targets_are_rejected_before_model_call(self):
        for declaration in ("", "../private/evaluator.sv", "rtl/not-declared.sv",
                            "rtl/example.sv, rtl/other.sv",
                            "src/agent.py", "rtl/example.txt"):
            with self.subTest(declaration=declaration), model_server() as (url, requests), patch.dict(os.environ, {
                "DEMO_AGENT_MODEL_BASE_URL": url, "DEMO_AGENT_MODEL_ID": "fixture-rtl",
                "DEMO_AGENT_MODEL_API_KEY": "fixture-only-token",
            }):
                result = self.harness.run(self.request(declaration))
                self.assertNotEqual(result.status, "completed")
                self.assertEqual(requests, [])
                self.assertEqual((self.task / "rtl/example.sv").read_text(), "")
                self.assert_untouched()
        outside = self.root / "outside.sv"
        outside.write_text("outside")
        (self.task / "rtl/example.sv").unlink()
        (self.task / "rtl/example.sv").symlink_to(outside)
        with model_server() as (url, requests), patch.dict(os.environ, {
            "DEMO_AGENT_MODEL_BASE_URL": url, "DEMO_AGENT_MODEL_ID": "fixture-rtl",
            "DEMO_AGENT_MODEL_API_KEY": "fixture-only-token",
        }):
            result = self.harness.run(self.request())
            self.assertEqual(result.status, "process_error")
            self.assertEqual(requests, [])
            self.assertEqual(outside.read_text(), "outside")

    def test_bad_completion_never_writes_target_or_reports_completion(self):
        for content in ("", None, ["not-text"]):
            with self.subTest(content=content), model_server(content=content) as (url, requests), \
                    patch.dict(os.environ, {"DEMO_AGENT_MODEL_BASE_URL": url,
                                            "DEMO_AGENT_MODEL_ID": "fixture-rtl",
                                            "DEMO_AGENT_MODEL_API_KEY": "fixture-only-token"}):
                result = self.harness.run(self.request())
                self.assertEqual(result.status, "infrastructure_error")
                self.assertEqual(len(requests), 1)
                self.assertEqual((self.task / "rtl/example.sv").read_text(), "")

    def test_tool_only_completion_without_text_is_infrastructure_error(self):
        with model_server(message={"role": "assistant", "tool_calls": [{
                "id": "call_1", "type": "function", "function": {"name": "unused", "arguments": "{}"}}]}) as (url, _), \
                patch.dict(os.environ, {"DEMO_AGENT_MODEL_BASE_URL": url,
                                        "DEMO_AGENT_MODEL_ID": "fixture-rtl",
                                        "DEMO_AGENT_MODEL_API_KEY": "fixture-only-token"}):
            result = self.harness.run(self.request())
        self.assertEqual(result.status, "infrastructure_error")
        self.assertEqual((self.task / "rtl/example.sv").read_text(), "")

    def test_only_exact_marker_on_exit_two_changes_process_error(self):
        for code, message, expected in ((1, '{"status":"model_unavailable"}', "process_error"),
                                        (2, '{"status":"model_unavailable","detail":"x"}', "process_error"),
                                        (2, '{"status":"failed"}', "process_error"),
                                        (2, "not-json", "process_error"),
                                        (2, "", "process_error"),
                                        (2, '{"status":"model_unavailable"}', "infrastructure_error")):
            with self.subTest(code=code, message=message):
                profile = {**self.profile, "command": ["{python}", "-c",
                    f"import sys; print({message!r}); sys.exit({code})"]}
                request = self.request()
                request = RunRequest(request.workspace, request.agent_dir, request.task_dir, request.prompt,
                                     request.seed, request.timeout_seconds, profile, request.logs)
                result = self.harness.run(request)
                self.assertEqual(result.status, expected)
                self.assertEqual(result.returncode, code)
                self.assertIsNone(result.metrics["agent_tokens"])


if __name__ == "__main__":
    unittest.main()
