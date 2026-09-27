"""API-free checks for the explicitly selected research CVDP example."""
import json
import hashlib
import os
import shutil
import threading
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent_optimizer.cli import main as agent_opt
from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError, RunRequest, UnavailableError
from agent_optimizer.registry import Registry
from agent_optimizer.runner import run_experiment
from support import ROOT, module, test_project


EXAMPLE = ROOT / "examples/model-rtl-agent/prepare.py"
RTL = "module example(output logic ready); assign ready = 1'b1; endmodule\n"


@contextmanager
def loopback_model(*, invalid_agent=False, invalid_optimizer=False, agent_status=200):
    requests = []
    original_code = (ROOT / "examples/model-rtl-agent/agent/src/agent.py").read_text()
    repaired_code = original_code.replace(
        "output.write_text(text, encoding=\"utf-8\")",
        f"output.write_text(text.replace('module broken', {RTL!r}), encoding=\"utf-8\")",
    )
    assert repaired_code != original_code

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({"path": self.path, "auth": self.headers.get("Authorization"), **body})
            system = body["messages"][0]["content"]
            user = body["messages"][1]["content"]
            if body["model"] == "fixture-agent":
                content = (None if invalid_agent else RTL if "REPAIRED_PROMPT" in system
                           or "rtl/first.v" in user else "module broken")
            elif invalid_optimizer:
                content = json.dumps({"content": ""})
            elif "Ecdysis analyst:" in system:
                content = json.dumps({"spec": "Repair the shared train RTL failure."})
            elif "Ecdysis moderator:" in system:
                content = json.dumps({"spec": "Keep the public target interface."})
            elif "GEPA reflection:" in system:
                content = json.dumps({"content": system_prompt + "\nREPAIRED_PROMPT\n"})
            elif "Meta-Harness:" in system or "Ecdysis editor:" in system:
                content = json.dumps({"content": repaired_code})
            else:
                content = json.dumps({"content": ""})
            payload = json.dumps({"id": "fixture-chat", "object": "chat.completion",
                                  "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                                               "finish_reason": "stop"}]}).encode()
            self.send_response(agent_status if body["model"] == "fixture-agent" else 200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    system_prompt = (ROOT / "examples/model-rtl-agent/agent/prompts/system.md").read_text()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def task(identifier, split, family, targets):
    return {"id": identifier, "split": split, "family": family,
            "prompt": "Implement the public circuit.",
            "files": {target: "" for target in targets},
            "evaluation": {"targets": targets, "row": {"id": identifier,
                                                    "output": {"response": "", "context": {}}}}}


class ResearchCVDPExampleTests(unittest.TestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)
        self.root = self.root.resolve()
        self.example = module("research_cvdp_example", EXAMPLE)
        self.benchmark = self.root / "external/datasets/cvdp/cvdp/tasks.json"
        self.benchmark.parent.mkdir(parents=True)
        self.tasks = [
            task("z-train", "train", "first", ["rtl/first.v"]),
            task("b-train", "train", "second", ["rtl/duplicate.sv"]),
            task("a-train", "train", "second", ["rtl/second.sv"]),
            task("a-validation", "validation", "first", ["rtl/leaked.v"]),
            task("c-validation", "validation", "third", ["rtl/third.sv"]),
            task("d-validation", "validation", "fourth", ["rtl/fourth.v"]),
            task("e-test", "test", "third", ["rtl/heldout.v"]),
            task("f-multiple", "train", "fifth", ["rtl/one.v", "rtl/two.sv"]),
            task("g-non-rtl", "train", "sixth", ["src/wrong.v"]),
            task("h-traversal", "validation", "seventh", ["rtl/../wrong.v"]),
        ]
        self.document = {"schema_version": 1, "synthetic": False,
                         "id": "cvdp-reviewed-no-commercial", "source_revision": "fixed-revision",
                         "data_sha256": "public-sha256", "excluded": [{"id": "excluded"}],
                         "tasks": self.tasks}
        self.benchmark.write_text(json.dumps(self.document), encoding="utf-8")
        self.private = self.root / "external/private-evaluator.txt"
        self.private.write_text("private-evaluation-fixture", encoding="utf-8")
        self.provider = {"benchmark": str(self.benchmark), "evaluator": "cvdp",
                         "evaluator_config": {"repo": str(self.root / "external/cvdp_benchmark"),
                                              "python": str(self.root / "external/cvdp-venv/bin/python"),
                                              "sim_image": "locked:fixed", "sim_image_id": "sha256:image"},
                         "provenance": {"source_revision": "fixed-revision",
                                        "sha256": "public-sha256", "image_id": "sha256:image",
                                        "dataset": {"revision": "fixed-hf"},
                                        "evaluation": {"tasks_sha256": "locked-tasks"}},
                         "dataset_provider": "cvdp"}
        self.config_root = self.root / "runs/configs/model-rtl-research"
        self.subset = self.root / "external/datasets/cvdp-research/subset.json"

    def prepare(self):
        with patch.object(self.example, "prepare_selection", return_value=(self.provider, {}, {})) as selected:
            result = self.example.prepare(self.root, dataset="cvdp", offline=True)
        selected.assert_called_once_with(self.root, "cvdp", offline=True)
        return result

    def offline_spec(self):
        spec = load_experiment(self.prepare())
        evaluator = self.root / "experiments/public_rtl_fixture.py"
        evaluator.write_text('''from pathlib import Path
from agent_optimizer.contracts import Evaluation

class PublicRTLEvaluator:
    def __init__(self, config):
        pass

    def evaluate(self, task, output_dir: Path, timeout_seconds):
        target, = task.evaluation["targets"]
        files = [p.relative_to(output_dir).as_posix() for p in output_dir.rglob("*") if p.is_file()]
        if files != [target]:
            return Evaluation("failed", {"passed": 0.0}, "Unexpected public outputs")
        good = (output_dir / target).read_text(encoding="utf-8") == "module example(output logic ready); assign ready = 1'b1; endmodule\\n"
        return Evaluation("passed" if good else "failed", {"passed": float(good)},
                          "Public RTL fixture exact match" if good else "Public RTL fixture mismatch")
''', encoding="utf-8")
        spec["evaluator"] = "public_rtl_fixture"
        spec["plugins"].setdefault("evaluators", {})["public_rtl_fixture"] = (
            "experiments/public_rtl_fixture.py:PublicRTLEvaluator")
        return spec

    @staticmethod
    def fixture_environment(url):
        return {"AGENT_OPT_MODEL_BASE_URL": url, "AGENT_OPT_MODEL_ID": "fixture-optimizer",
                "AGENT_OPT_MODEL_API_KEY": "optimizer-fixture-token",
                "DEMO_AGENT_MODEL_BASE_URL": url, "DEMO_AGENT_MODEL_ID": "fixture-agent",
                "DEMO_AGENT_MODEL_API_KEY": "agent-fixture-token"}

    def test_loopback_stages_run_snapshot_code_with_train_only_evidence(self):
        spec = self.offline_spec()
        original = {path: path.read_bytes() for path in (
            self.root / "examples/model-rtl-agent/agent/src/agent.py",
            self.root / "examples/model-rtl-agent/agent/prompts/system.md",
            self.root / "experiments/public_rtl_fixture.py", self.benchmark, self.private)}
        with loopback_model() as (url, requests), patch.dict(os.environ, self.fixture_environment(url), clear=True):
            run, summary = run_experiment(spec, Registry(), self.root / "offline-runs")
        group = summary["groups"][0]
        self.assertEqual(summary["status"], "completed")
        self.assertEqual([stage["id"] for stage in group["stages"]], ["gepa", "meta", "ecdysis"])
        self.assertEqual([stage["status"] for stage in group["stages"]], ["completed"] * 3)
        self.assertEqual(spec["budget"]["max_trials"], 16)
        self.assertEqual(summary["trials_used"], 12)
        self.assertEqual(summary["trials_used"], group["trial_count"])
        self.assertFalse(spec["final_test"])
        self.assertEqual(group["final_test"], [])
        self.assertEqual(group["baseline"]["metrics"]["solve_rate"], 0.0)
        self.assertEqual(group["selected"][0]["metrics"]["solve_rate"], 1.0)
        self.assertEqual([stage["selected"][0]["metrics"]["solve_rate"]
                          for stage in group["stages"]], [1.0, 1.0, 1.0])

        events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
        trials = [event for event in events if event["event"] == "trial_completed"]
        self.assertEqual({row["split"] for row in trials}, {"train", "validation"})
        baseline_train = [row for row in trials if row["split"] == "train" and row["candidate_id"] == "c0001"]
        self.assertEqual({row["task_id"]: row["metrics"]["passed"] for row in baseline_train},
                         {"a-train": 0.0, "z-train": 1.0})
        self.assertTrue(all(row["valid"] for row in baseline_train))
        self.assertEqual([row["event"] for row in events if row["event"] == "stage_started"],
                         ["stage_started"] * 3)
        self.assertEqual([stage["checkpoint"]["iterations"][0]["accepted"]
                          for stage in group["stages"][:2]], [True, True])
        ecdysis = group["stages"][2]["checkpoint"]["rounds"][0]
        self.assertEqual(ecdysis["status"], "accepted")
        self.assertEqual(ecdysis["groups"][0]["task_ids"], ["a-train"])
        self.assertEqual(ecdysis["retained_score"], 1.0)

        group_dir = run / group["agent_id"] / group["harness_id"]
        candidates = group_dir / "candidates"
        optimizer_calls = [row for row in requests if row["model"] == "fixture-optimizer"]
        agent_calls = [row for row in requests if row["model"] == "fixture-agent"]
        self.assertEqual(len(agent_calls), len(trials))
        # The runner executes these trials sequentially; the user message identifies each request.
        trial_requests = {}
        for trial, call in zip(trials, agent_calls, strict=True):
            trial_dir = group_dir / "trials" / trial["trial_id"]
            request_prompt = json.loads((trial_dir / "agent_workspace/request.json").read_text())["prompt"]
            self.assertEqual(call["messages"][1], {"role": "user", "content": request_prompt})
            trial_requests[trial["trial_id"]] = call
        edits = {"gepa": "prompts/system.md", "meta": "src/agent.py", "ecdysis": "src/agent.py"}
        baseline_code = (candidates / "c0001/bundle/src/agent.py").read_bytes()
        for stage in group["stages"]:
            checkpoint = stage["checkpoint"]
            candidate_id = (checkpoint["iterations"][0]["candidate_id"] if stage["id"] != "ecdysis"
                            else checkpoint["rounds"][0]["candidate_id"])
            candidate = candidates / candidate_id
            metadata = json.loads((candidate / "candidate.json").read_text())
            self.assertEqual(metadata["parents"], ["c0001"])
            self.assertEqual(metadata["changed_files"], [edits[stage["id"]]])
            diff = (candidate / "changes.diff").read_text()
            self.assertIn("--- a/" + edits[stage["id"]], diff)
            self.assertIn("+++ b/" + edits[stage["id"]], diff)
            self.assertNotIn("--- a/" + ("src/agent.py" if stage["id"] == "gepa"
                                       else "prompts/system.md"), diff)
            snapshot = (candidate / "bundle/src/agent.py").read_bytes()
            if stage["id"] == "gepa":
                self.assertEqual(snapshot, baseline_code)
                self.assertIn("REPAIRED_PROMPT", (candidate / "bundle/prompts/system.md").read_text())
            else:
                self.assertNotEqual(snapshot, baseline_code)
            candidate_trials = [row for row in trials if row["candidate_id"] == candidate_id]
            self.assertEqual({row["split"] for row in candidate_trials}, {"train", "validation"})
            for trial in candidate_trials:
                trial_dir = group_dir / "trials" / trial["trial_id"]
                actual_prompt = (trial_dir / "agent_workspace/agent/prompts/system.md").read_text()
                self.assertEqual(actual_prompt, (candidate / "bundle/prompts/system.md").read_text())
                self.assertEqual(trial_requests[trial["trial_id"]]["messages"][0],
                                 {"role": "system", "content": actual_prompt})
                self.assertEqual((trial_dir / "agent_workspace/agent/src/agent.py").read_bytes(), snapshot)
                agent_file_sha256 = json.loads(Path(trial["execution"]["stdout_path"]).read_text())[
                    "agent_file_sha256"]
                self.assertEqual(agent_file_sha256, hashlib.sha256(snapshot).hexdigest())
                self.assertEqual(trial["metrics"]["passed"], 1.0)
                self.assertFalse((trial_dir / "agent_workspace/private").exists())
                self.assertFalse((trial_dir / "agent_workspace/agent/.env").exists())
        self.assertEqual(json.loads((group_dir / "frozen_selection.json").read_text()), group["selected"])
        self.assertTrue(all(path.read_bytes() == content for path, content in original.items()))

        self.assertEqual(len(optimizer_calls), 5)  # GEPA, Meta, Ecdysis reviews x2 + edit
        self.assertTrue(all(row["path"] == "/v1/chat/completions" for row in requests))
        self.assertEqual({row["auth"] for row in optimizer_calls}, {"Bearer optimizer-fixture-token"})
        self.assertEqual({row["auth"] for row in agent_calls}, {"Bearer agent-fixture-token"})
        self.assertNotIn("private-evaluation-fixture", json.dumps(requests))
        self.assertNotIn("c-validation", json.dumps(optimizer_calls))
        self.assertNotIn("e-test", json.dumps(optimizer_calls))
        self.assertNotIn("c0002", json.dumps(optimizer_calls[1:]))
        self.assertNotIn("c0003", json.dumps(optimizer_calls[2:]))
        for call in optimizer_calls[:2]:
            evidence = json.loads(call["messages"][1]["content"])["train"]
            self.assertEqual(len(evidence), 2)
            self.assertEqual({row["task_id"] for row in evidence}, {"a-train", "z-train"})
            self.assertEqual({row.get("candidate_id") for row in evidence}, {None})
        for role, call in zip(("analyst", "moderator"), optimizer_calls[2:4], strict=True):
            self.assertIn(f"Ecdysis {role}:", call["messages"][0]["content"])
            review = json.loads(call["messages"][1]["content"])
            self.assertEqual(review["evidence"], [{
                "pattern": "failed:passed", "task_ids": ["a-train"],
                "examples": [{"task_id": "a-train", "feedback": "Public RTL fixture mismatch"}],
                "failure_count": 1, "distinct_tasks": 1}])
            self.assertEqual(review["previous_spec"],
                             "" if role == "analyst" else "Repair the shared train RTL failure.")
        editor = optimizer_calls[4]
        self.assertIn("Ecdysis editor:", editor["messages"][0]["content"])
        edit_request = json.loads(editor["messages"][1]["content"])
        self.assertEqual(edit_request["file"], "src/agent.py")
        self.assertEqual(edit_request["content"], baseline_code.decode())
        self.assertEqual(edit_request["train"], {
            "groups": review["evidence"], "specification": "Keep the public target interface."})
        for call in optimizer_calls[2:]:
            payload = call["messages"][1]["content"]
            self.assertNotIn("z-train", payload)  # A successful baseline train is not failure evidence.
            self.assertNotIn("c0002", payload)
            self.assertNotIn("c0003", payload)
            self.assertNotIn("c-validation", payload)
            self.assertNotIn("e-test", payload)
            self.assertNotIn("private-evaluation-fixture", payload)
        self.assertEqual([row["event"] for row in events if row["event"] == "optimizer_review_started"],
                         ["optimizer_review_started"] * 2)
        for artifact in run.rglob("*"):
            if artifact.is_file():
                content = artifact.read_bytes()
                for secret in ("agent-fixture-token", "optimizer-fixture-token"):
                    self.assertNotIn(secret.encode(), content, artifact.relative_to(run))

    def test_missing_agent_env_after_static_plan_is_invalid_runner_trial(self):
        spec = self.offline_spec()
        spec["stages"] = []
        spec["final_stages"] = ["baseline"]
        with loopback_model() as (url, requests), patch.dict(os.environ, {
                "AGENT_OPT_MODEL_BASE_URL": url, "AGENT_OPT_MODEL_ID": "fixture-optimizer",
                "AGENT_OPT_MODEL_API_KEY": "optimizer-fixture-token"}, clear=True):
            run, summary = run_experiment(spec, Registry(), self.root / "offline-runs")
        records = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()
                   if '"event": "trial_completed"' in line]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "infrastructure_error",
                         Path(records[0]["execution"]["stderr_path"]).read_text())
        self.assertFalse(records[0]["valid"])
        self.assertIsNone(records[0]["metrics"]["passed"])
        self.assertEqual(records[0]["execution"]["returncode"], 2)
        self.assertEqual(summary["groups"][0]["selected"], [])
        self.assertEqual(requests, [])

    def test_loopback_http_401_stays_invalid_through_runner_without_raw_or_model_success(self):
        spec = self.offline_spec()
        spec["stages"] = []
        spec["final_stages"] = ["baseline"]
        with loopback_model(agent_status=401) as (url, requests), \
                patch.dict(os.environ, self.fixture_environment(url), clear=True):
            run, summary = run_experiment(spec, Registry(), self.root / "offline-runs")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["path"], "/v1/chat/completions")
        self.assertEqual(requests[0]["model"], "fixture-agent")
        self.assertEqual(summary["status"], "no_eligible_candidate")
        self.assertEqual(summary["trials_used"], 1)
        self.assertEqual(summary["groups"][0]["selected"], [])
        self.assertFalse(summary["groups"][0]["baseline"]["valid"])
        events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
        records = [event for event in events if event["event"] == "trial_completed"]
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["status"], "infrastructure_error")
        self.assertFalse(record["valid"])
        self.assertIsNone(record["metrics"]["passed"])
        self.assertEqual(record["execution"]["returncode"], 2)
        self.assertEqual(json.loads(Path(record["execution"]["stdout_path"]).read_text()),
                         {"status": "model_unavailable"})
        self.assertNotIn("evaluation_started", [event["event"] for event in events])
        self.assertEqual(list(run.rglob("raw_result.json")), [])
        self.assertFalse((Path(record["execution"]["stdout_path"]).parent.parent /
                          "evaluation_workspace").exists())
        for artifact in run.rglob("*"):
            if artifact.is_file():
                content = artifact.read_bytes()
                self.assertNotIn(b"agent-fixture-token", content, artifact.relative_to(run))
                self.assertNotIn(b"optimizer-fixture-token", content, artifact.relative_to(run))

    def test_invalid_loopback_agent_or_optimizer_reply_never_becomes_a_score(self):
        for invalid_agent, invalid_optimizer in ((True, False), (False, True)):
            with self.subTest(agent=invalid_agent, optimizer=invalid_optimizer):
                if self.config_root.exists():
                    shutil.rmtree(self.config_root)
                spec = self.offline_spec()
                if invalid_agent:
                    spec["stages"] = []
                    spec["final_stages"] = ["baseline"]
                with loopback_model(invalid_agent=invalid_agent, invalid_optimizer=invalid_optimizer) as (url, _), \
                        patch.dict(os.environ, self.fixture_environment(url), clear=True):
                    if invalid_optimizer:
                        previous = set((self.root / "offline-runs").glob("*/summary.json"))
                        with self.assertRaisesRegex(UnavailableError, "nonempty content"):
                            run_experiment(spec, Registry(), self.root / "offline-runs")
                    else:
                        run, summary = run_experiment(spec, Registry(), self.root / "offline-runs")
                        self.assertEqual(summary["groups"][0]["selected"], [])
                if invalid_optimizer:
                    created = set((self.root / "offline-runs").glob("*/summary.json")) - previous
                    self.assertEqual(len(created), 1)
                    run = created.pop().parent
                    summary = json.loads((run / "summary.json").read_text())
                    self.assertEqual(summary["status"], "error")
                    self.assertEqual(summary["groups"][0]["selected"], [])
                records = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()
                           if '"event": "trial_completed"' in line]
                if invalid_agent:
                    self.assertEqual(len(records), 1)
                    self.assertEqual(records[0]["status"], "infrastructure_error")
                    self.assertFalse(records[0]["valid"])
                    self.assertIsNone(records[0]["metrics"]["passed"])
                else:
                    self.assertEqual({row["task_id"] for row in records},
                                     {"a-train", "z-train", "c-validation"})
                    self.assertEqual(summary["groups"][0]["stages"][0]["status"], "error")

    def test_public_single_rtl_targets_keep_split_family_and_locked_provenance(self):
        original = self.benchmark.read_bytes()
        result = self.prepare()
        self.assertEqual(result, self.config_root / "experiment.toml")
        generated = json.loads((self.config_root / "tasks.json").read_text(encoding="utf-8"))
        self.assertEqual([(row["id"], row["split"], row["family"])
                          for row in generated["tasks"]],
                         [("a-train", "train", "second"),
                          ("z-train", "train", "first"),
                          ("c-validation", "validation", "third")])
        self.assertEqual(generated["id"], "cvdp-reviewed-no-commercial")
        self.assertEqual(generated["data_sha256"], "public-sha256")
        self.assertEqual(generated["source_revision"], "fixed-revision")
        self.assertNotIn("private-evaluation-fixture", json.dumps(generated))
        self.assertNotIn("row", generated["tasks"][0]["files"])
        self.assertEqual(generated["tasks"][0]["evaluation"]["row"]["id"], "a-train")
        self.assertTrue(all(row["prompt"].endswith("\nWrite target files: " +
                                                        row["evaluation"]["targets"][0])
                            for row in generated["tasks"]))
        self.assertEqual(generated["dataset_provenance"], self.provider["provenance"])
        self.assertEqual(generated["dataset_provider"], "cvdp")
        self.assertFalse(self.subset.exists())
        self.assertEqual(self.benchmark.read_bytes(), original)
        self.assertEqual(self.private.read_text(encoding="utf-8"), "private-evaluation-fixture")

    def test_importer_style_target_declaration_is_preserved_once(self):
        # ace-rtl/prepare.py:convert supplies this trailing declaration in public task prompts.
        for row in self.tasks:
            target = row["evaluation"]["targets"][0]
            row["prompt"] += "\nWrite target files: " + target
        self.benchmark.write_text(json.dumps(self.document), encoding="utf-8")
        generated = json.loads((self.prepare().parent / "tasks.json").read_text(encoding="utf-8"))
        by_id = {row["id"]: row for row in self.tasks}
        for row in generated["tasks"]:
            self.assertEqual(row["prompt"], by_id[row["id"]]["prompt"])
            self.assertEqual(row["prompt"].count("\nWrite target files: "), 1)

    def test_subset_is_transient_and_removed_on_success(self):
        original_writer = self.example.write_experiment
        seen = []

        def inspect_writer(*args, **kwargs):
            temporary_subset = Path(kwargs["dataset"]["benchmark"])
            self.assertTrue(temporary_subset.is_file())
            self.assertFalse(temporary_subset.is_symlink())
            self.assertTrue(temporary_subset.parent.is_dir())
            self.assertFalse(temporary_subset.parent.is_symlink())
            seen.append(temporary_subset)
            return original_writer(*args, **kwargs)

        with patch.object(self.example, "prepare_selection", return_value=(self.provider, {}, {})), \
                patch.object(self.example, "write_experiment", side_effect=inspect_writer):
            self.example.prepare(self.root, dataset="cvdp")
        self.assertEqual(len(seen), 1)
        self.assertFalse(seen[0].exists())
        self.assertFalse(seen[0].parent.exists())
        self.assertFalse(self.subset.exists())
        self.assertEqual([row["id"] for row in json.loads(
            (self.config_root / "tasks.json").read_text(encoding="utf-8"))["tasks"]],
            ["a-train", "z-train", "c-validation"])

    def test_failed_config_writer_removes_transient_subset_and_leaves_no_output(self):
        seen = []

        def fail_writer(*args, **kwargs):
            temporary_subset = Path(kwargs["dataset"]["benchmark"])
            self.assertTrue(temporary_subset.is_file())
            seen.append(temporary_subset)
            raise ConfigurationError("설정 생성 실패 fixture")

        with patch.object(self.example, "prepare_selection", return_value=(self.provider, {}, {})), \
                patch.object(self.example, "write_experiment", side_effect=fail_writer):
            with self.assertRaisesRegex(ConfigurationError, "설정 생성 실패"):
                self.example.prepare(self.root, dataset="cvdp")
        self.assertEqual(len(seen), 1)
        self.assertFalse(seen[0].exists())
        self.assertFalse(seen[0].parent.exists())
        self.assertFalse(self.subset.exists())
        self.assertFalse(self.config_root.exists())

    def test_existing_subset_and_symlink_parent_are_never_written(self):
        with self.subTest(existing="file"):
            self.subset.parent.mkdir(parents=True)
            self.subset.write_text("preserve earlier content", encoding="utf-8")
            self.prepare()
            self.assertEqual(self.subset.read_text(encoding="utf-8"), "preserve earlier content")
        shutil.rmtree(self.config_root)
        self.subset.unlink()
        self.subset.parent.rmdir()
        with self.subTest(existing="symlink"), TemporaryDirectory() as destination:
            outside = Path(destination)
            self.subset.parent.symlink_to(outside, target_is_directory=True)
            self.prepare()
            self.assertFalse((outside / "subset.json").exists())
            self.assertEqual(len(json.loads((self.config_root / "tasks.json").read_text())["tasks"]), 3)

    def test_config_parent_symlink_is_rejected_before_provider_call(self):
        with TemporaryDirectory() as destination:
            (self.root / "runs").mkdir()
            (self.root / "runs/configs").symlink_to(destination, target_is_directory=True)
            with patch.object(self.example, "prepare_selection", side_effect=AssertionError("provider called")):
                with self.assertRaises(ConfigurationError):
                    self.example.prepare(self.root, dataset="cvdp")
            self.assertEqual(list(Path(destination).iterdir()), [])

    def test_malformed_provider_rows_fail_as_configuration_errors_before_outputs(self):
        valid = task("a-train", "train", "first", ["rtl/first.v"])
        invalid = (
            {"tasks": None}, {"tasks": {}}, {"tasks": [None]},
            {"tasks": [*self.tasks, {**valid, "prompt": None}]},
            {"tasks": [*self.tasks, {key: value for key, value in valid.items() if key != "prompt"}]},
            {"tasks": [{**valid, "evaluation": None}]},
            {"tasks": [{**valid, "files": ["rtl/first.v"]}]},
            {"tasks": [{**valid, "evaluation": {"targets": None}}]},
            {"tasks": [{**valid, "evaluation": {"targets": "rtl/first.v"}}]},
            {"tasks": [{**valid, "evaluation": {"targets": [1]}}]},
            {"tasks": [*self.tasks, {**valid, "evaluation": None}]},
        )
        for broken in invalid:
            with self.subTest(document=broken):
                self.benchmark.write_text(json.dumps({**self.document, **broken}), encoding="utf-8")
                with patch.object(self.example, "prepare_selection", return_value=(self.provider, {}, {})), \
                        patch("agent_optimizer.models.complete", side_effect=AssertionError("model called")) as model:
                    with self.assertRaisesRegex(ConfigurationError, "CVDP public"):
                        self.example.prepare(self.root, dataset="cvdp")
                model.assert_not_called()
                self.assertFalse(self.config_root.exists())
                self.assertFalse(self.subset.exists())

    def test_generated_plan_declares_real_command_editables_and_independent_stages(self):
        spec = load_experiment(self.prepare())
        self.assertEqual(spec["_root"], self.root)
        self.assertEqual(spec["evaluator"], "cvdp")
        self.assertEqual(spec["evaluator_config"], self.provider["evaluator_config"])
        self.assertEqual(spec["_agents"][0].source.path,
                         self.root / "examples/model-rtl-agent/agent")
        self.assertEqual(spec["_agents"][0].editable, ("prompts/system.md", "src/agent.py"))
        self.assertEqual(spec["_profiles"][0]["adapter"], "model_rtl_command")
        self.assertEqual(spec["_profiles"][0]["command"],
                         ["{python}", "{agent_dir}/src/agent.py", "{task_dir}"])
        self.assertEqual(spec["plugins"]["harnesses"]["model_rtl_command"],
                         "examples/model-rtl-agent/adapter.py:ModelRTLCommand")
        self.assertEqual([(stage["id"], stage["optimizer"], stage["max_trials"], stage["inputs"])
                          for stage in spec["stages"]],
                         [("gepa", "gepa", 5, ["baseline"]),
                          ("meta", "meta_harness", 4, ["baseline"]),
                          ("ecdysis", "ecdysis", 4, ["baseline"])])
        self.assertEqual([stage["config"] for stage in spec["stages"]], [
            {"file": "prompts/system.md", "iterations": 1, "batch_size": 2,
             "request_timeout_seconds": 60},
            {"file": "src/agent.py", "iterations": 1, "required_symbol": "main",
             "request_timeout_seconds": 60},
            {"file": "src/agent.py", "rounds": 1, "refinement_passes": 2,
             "request_timeout_seconds": 60}])
        self.assertEqual(spec["final_stages"], ["gepa", "meta", "ecdysis"])
        self.assertFalse(spec["final_test"])
        self.assertEqual(spec["budget"], {"max_trials": 16, "max_wall_time_seconds": 3600,
                                          "trial_timeout_seconds": 180})
        self.assertEqual(spec["objective"], {"mode": "lexicographic", "keep": 1,
                                             "metrics": [{"name": "solve_rate", "source": "passed",
                                                          "direction": "maximize", "aggregate": "mean"}]})
        def available_provider(root, _dataset_id, registry):
            registry.load_project(root)
            return []

        with patch.dict(os.environ, {"AGENT_OPT_MODEL_BASE_URL": "http://127.0.0.1:1/v1",
                                     "AGENT_OPT_MODEL_ID": "fixture-only",
                                     "AGENT_OPT_MODEL_API_KEY": "fixture-only"}, clear=True), \
                patch("agent_optimizer.readiness._dataset", side_effect=available_provider):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(agent_opt(["doctor", "--plan", str(self.config_root / "experiment.toml"),
                                            "--json"]), 0)
        plan = json.loads(output.getvalue())
        self.assertTrue(plan["ready"], [(row["id"], row["status"]) for row in plan["checks"]])
        self.assertEqual(plan["scope"], "plan")
        self.assertEqual(next(row["status"] for row in plan["checks"]
                              if row["id"] == "model.configuration"), "ok")
        # Static plan checks optimizer settings, not this Agent's DEMO credentials.
        workspace = self.root / "trial"
        workspace.mkdir()
        shutil.copytree(self.root / "examples/model-rtl-agent/agent", workspace / "agent")
        task_dir = workspace / "task"
        (task_dir / "rtl").mkdir(parents=True)
        (task_dir / "rtl/fixture.sv").write_text("", encoding="utf-8")
        registry = Registry()
        registry.load_plugins(self.root, spec["plugins"])
        harness = registry.resolve("harnesses", "model_rtl_command")()
        request = RunRequest(workspace, workspace / "agent", task_dir,
                             "Implement this circuit.\nWrite target files: rtl/fixture.sv\n"
                             "Task files are in ./task. Modify only task outputs.",
                             1, 15, spec["_profiles"][0], self.root / "logs")
        with patch.dict(os.environ, {"DEMO_AGENT_MODEL_BASE_URL": "",
                                     "DEMO_AGENT_MODEL_ID": "",
                                     "DEMO_AGENT_MODEL_API_KEY": ""}):
            execution = harness.run(request)
        self.assertEqual(execution.status, "infrastructure_error")
        self.assertEqual(execution.returncode, 2)
        self.assertEqual((task_dir / "rtl/fixture.sv").read_text(encoding="utf-8"), "")

    def test_insufficient_distinct_families_fail_without_writing_a_config(self):
        for excluded, reason in (("z-train", "train"), ("c-validation", "validation")):
            with self.subTest(excluded=excluded):
                document = {**self.document, "tasks": [row for row in self.tasks
                                                       if row["id"] not in {excluded, "d-validation"}]}
                self.benchmark.write_text(json.dumps(document), encoding="utf-8")
                with patch.object(self.example, "prepare_selection", return_value=(self.provider, {}, {})):
                    with self.assertRaisesRegex(ConfigurationError, reason):
                        self.example.prepare(self.root, dataset="cvdp")
                self.assertFalse(self.config_root.exists())
                self.assertFalse(self.subset.exists())

    def test_existing_configuration_rejects_before_provider_or_subset_write(self):
        self.config_root.mkdir(parents=True)
        marker = self.config_root / "experiment.toml"
        marker.write_text("do not replace", encoding="utf-8")
        self.subset.parent.mkdir(parents=True)
        self.subset.write_text("old subset", encoding="utf-8")
        with patch.object(self.example, "prepare_selection", side_effect=AssertionError("provider called")):
            with self.assertRaisesRegex(ConfigurationError, "already exists"):
                self.example.prepare(self.root, dataset="cvdp")
        self.assertEqual(marker.read_text(encoding="utf-8"), "do not replace")
        self.assertEqual(self.subset.read_text(encoding="utf-8"), "old subset")

    def test_dataset_selection_must_be_explicit_cvdp(self):
        with patch.object(self.example, "prepare_selection", side_effect=AssertionError("provider called")):
            for selection in (None, "verilog-spec"):
                with self.subTest(selection=selection), self.assertRaises((ConfigurationError, TypeError)):
                    if selection is None:
                        self.example.prepare(self.root)
                    else:
                        self.example.prepare(self.root, dataset=selection)

    def test_command_requires_explicit_cvdp_and_respects_offline(self):
        for args in ([], ["--dataset", "verilog-spec"]):
            with self.subTest(args=args), self.assertRaises(SystemExit), redirect_stderr(StringIO()):
                self.example.main(args)
        output = StringIO()
        with patch.object(self.example, "prepare_selection", return_value=(self.provider, {}, {})) as selected:
            with redirect_stdout(output):
                self.example.main(["--dataset", "cvdp", "--offline", "--project-root", str(self.root)])
        selected.assert_called_once_with(self.root, "cvdp", offline=True)
        self.assertIn(str(self.config_root / "experiment.toml"), output.getvalue())


if __name__ == "__main__":
    unittest.main()
