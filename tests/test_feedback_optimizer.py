import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import BudgetExceeded, ConfigurationError, UnavailableError
from agent_optimizer.registry import Registry
from agent_optimizer.runner import run_experiment
from agent_optimizer.workspace import digest
from support import ROOT, module, test_project
from test_models import completion, model_server


class FeedbackOptimizerTests(unittest.TestCase):
    def test_deadline_expiry_on_model_failure_keeps_budget_status(self):
        optimizer = module("feedback_deadline", ROOT / "experiments/simple-feedback/optimizer.py")
        with tempfile.TemporaryDirectory() as directory:
            candidate = SimpleNamespace(id="c1", path=Path(directory))
            class Context:
                calls = 0
                def evaluate(self, _candidate):
                    return {"valid": True, "split": "train"}
                def history(self):
                    return []
                def remaining_seconds(self):
                    self.calls += 1
                    if self.calls > 1:
                        raise BudgetExceeded("deadline")
                    return 0.01
            with patch.dict(os.environ, {"AGENT_OPT_MODEL_BASE_URL": "https://example.invalid/v1", "AGENT_OPT_MODEL_API_KEY": "key"}, clear=True), patch.object(
                    optimizer, "complete", side_effect=UnavailableError("timed out")), self.assertRaises(BudgetExceeded):
                optimizer.Optimizer().optimize(Context(), [candidate], {"file": "guidance.md", "iterations": 1})

    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)
        plugin = self.root / "optimizer.py"
        shutil.copyfile(ROOT / "experiments/simple-feedback/optimizer.py", plugin)
        self.spec = load_experiment(self.root / "examples/minimal/experiment.toml")
        self.spec["_agents"] = self.spec["_agents"][:1]
        self.spec["plugins"]["optimizers"] = {"feedback": "optimizer.py:Optimizer"}
        self.config = {"file": "configs/strategy.json", "iterations": 3}
        self.spec.update(stages=[{"id": "feedback", "optimizer": "feedback", "config": self.config}],
                         final_stages=["feedback"])
        self.output = Path(temporary.name) / "runs"

    def run_with(self, replies):
        with model_server([(200, r) for r in replies]) as (url, requests), patch.dict(os.environ, {
            "AGENT_OPT_MODEL_BASE_URL": url + "/v1", "AGENT_OPT_MODEL_API_KEY": "fixture-key",
        }, clear=True):
            run, summary = run_experiment(self.spec, Registry(), self.output)
        return run, summary, requests

    def test_three_iterations_preserve_sources_split_boundary_usage_and_diffs(self):
        source = self.spec["_agents"][0].source.path
        before = digest(source)
        replies = [completion(json.dumps({"content": json.dumps({"repair": True, "iteration": i})}),
                              None if i == 0 else {"prompt_tokens": 10, "completion_tokens": 4}) for i in range(3)]
        run, summary, requests = self.run_with(replies)
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(digest(source), before)
        group = summary["groups"][0]
        self.assertEqual(len(group["stages"][0]["evaluated"]), 4)
        self.assertEqual(group["selected"][0]["metrics"]["solve_rate"], 1)
        self.assertEqual([u["input_tokens"] for u in group["optimizer_usage"]], [None, 10, 10])
        self.assertTrue(all(u["cost_usd"] is None for u in group["optimizer_usage"]))
        self.assertEqual(len(requests), 3)
        payloads = json.dumps([r["body"] for r in requests])
        self.assertIn("fixture-train", payloads)
        self.assertNotIn("fixture-validation", payloads)
        self.assertNotIn("fixture-test", payloads)
        self.assertNotIn("evaluation_workspace", payloads)
        self.assertNotIn("artifacts", payloads)
        last_prompt = json.loads(requests[-1]["body"]["messages"][1]["content"])
        self.assertEqual(json.loads(last_prompt["content"])["iteration"], 1)
        events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
        trials = [e for e in events if e["event"] == "trial_completed"]
        self.assertEqual(sum(e["split"] == "train" for e in trials), 4)
        self.assertEqual(sum(e["split"] == "validation" for e in trials), 4)
        self.assertTrue(all(e["split"] == "test" for e in trials[-2:]))
        self.assertEqual(len(list(run.glob("**/changes.diff"))), 4)

    def test_bad_content_keeps_usage_and_failure_instead_of_baseline_fallback(self):
        with self.assertRaises(UnavailableError):
            self.run_with([completion('{"files":{"../escape":"bad"}}', {"prompt_tokens": 5, "completion_tokens": 3})])
        summary = json.loads(next(self.output.glob("*/summary.json")).read_text())
        self.assertEqual(summary["status"], "error")
        self.assertEqual(summary["groups"][0]["optimizer_usage"][0]["input_tokens"], 5)
        self.assertEqual(summary["groups"][0]["selected"], [])

    def test_noneditable_file_is_rejected(self):
        self.config["file"] = "README.md"
        with self.assertRaises(ConfigurationError):
            self.run_with([completion('{"content":"overwrite"}')])

    def test_invalid_iterations_fail_without_model_call(self):
        for count in [0, -1, True, 1.5, "3"]:
            self.config["iterations"] = count
            with self.subTest(count=count), self.assertRaises(ConfigurationError):
                self.run_with([completion('{"content":"unused"}')])
