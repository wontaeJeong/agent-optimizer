from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.cli import main
from agent_optimizer.config import load_experiment, validate_objective
from agent_optimizer.contracts import (
    BudgetExceeded, ConfigurationError, Evaluation, ExecutionResult, OptimizationResult,
)
from agent_optimizer.objectives import select
from agent_optimizer.process import run_process
from agent_optimizer.registry import Registry
from agent_optimizer.runner import Budget, run_experiment
from agent_optimizer.sources import materialize_agent
from support import test_project


_PROJECT, ROOT = test_project()


class Harness:
    def run(self, request):
        return ExecutionResult("completed", 0, 0.01, "", "", {"agent_tokens": 7})


class Evaluator:
    def evaluate(self, task, output_dir, timeout_seconds):
        return Evaluation("passed", {"passed": 1.0})


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.spec = load_experiment(ROOT / "examples/minimal/experiment.toml")
        self.spec["_agents"] = self.spec["_agents"][:1]
        self.spec.update(stages=[], final_stages=["baseline"], final_test=False)
        self.spec["budget"] = {"max_trials": 20, "max_wall_time_seconds": 10,
                               "trial_timeout_seconds": 5}
        self.registry = Registry()
        self.registry.factories["harnesses"]["fixture"] = Harness
        self.spec["evaluator"] = "controlled"
        self.registry.factories["evaluators"]["controlled"] = lambda config: Evaluator()
        self.now = 0.0

    def run_experiment(self):
        return run_experiment(self.spec, self.registry, self.output)

    def persisted(self):
        run = next(self.output.glob("*/summary.json")).parent
        summary = json.loads((run / "summary.json").read_text())
        events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
        return run, summary, events

    def optimizer(self, optimize):
        self.registry.factories["optimizers"]["controlled"] = lambda: type(
            "Optimizer", (), {"optimize": staticmethod(optimize)})()
        self.spec["stages"] = [{"id": "search", "optimizer": "controlled"}]
        self.spec["final_stages"] = ["search"]

    def test_failed_reservation_does_not_count_a_trial(self):
        with patch("agent_optimizer.runner.time.monotonic", side_effect=lambda: self.now):
            budget = Budget({"max_wall_time_seconds": 1})
            self.now = 2
            with self.assertRaises(BudgetExceeded):
                budget.reserve()
        self.assertEqual(budget.used, 0)

    def test_global_timeout_is_invalid_and_not_selected(self):
        owner = self

        class SleepingHarness:
            def run(self, request):
                owner.assertAlmostEqual(request.timeout_seconds, 0.2)
                result = run_process([sys.executable, "-c", "import time; time.sleep(2)"],
                                     request.workspace, request.logs, request.timeout_seconds)
                owner.now += request.timeout_seconds
                return result

        self.registry.factories["harnesses"]["fixture"] = SleepingHarness
        self.spec["budget"]["max_wall_time_seconds"] = 0.2
        # Freeze only the runner's clock during setup, not subprocess timeout clocks.
        # Source/setup budget accounting is covered separately below.
        with patch("agent_optimizer.runner.time", wraps=time) as clock:
            clock.monotonic.side_effect = lambda: self.now
            _, summary = self.run_experiment()
        self.assertEqual(summary["status"], "budget_exhausted")
        group = summary["groups"][0]
        self.assertIsNone(group["baseline"])
        self.assertEqual(group["selected"], [])
        self.assertEqual(group["trial_count"], 1)
        run, _, events = self.persisted()
        record = next(e for e in events if e["event"] == "trial_completed")
        self.assertEqual(record["status"], "interrupted")
        self.assertFalse(record["valid"])
        self.assertIsNone(record["metrics"]["passed"])
        self.assertEqual(record["execution"]["status"], "timeout")
        self.assertEqual(json.loads(next(run.rglob("result.json")).read_text())["trial_id"],
                         record["trial_id"])

    def test_configured_trial_timeout_remains_a_scored_failure(self):
        class SleepingHarness:
            def run(self, request):
                return run_process([sys.executable, "-c", "import time; time.sleep(2)"],
                                   request.workspace, request.logs, request.timeout_seconds)

        self.registry.factories["harnesses"]["fixture"] = SleepingHarness
        self.spec["budget"]["trial_timeout_seconds"] = 0.05
        _, summary = self.run_experiment()
        self.assertEqual(summary["status"], "completed")
        self.assertTrue(summary["groups"][0]["baseline"]["valid"])
        self.assertEqual(summary["groups"][0]["baseline"]["metrics"]["solve_rate"], 0)

    def test_last_evaluation_cannot_finish_after_global_deadline(self):
        owner = self

        class SlowEvaluator:
            def evaluate(self, task, output_dir, timeout_seconds):
                owner.now = 11
                return Evaluation("passed", {"passed": 1.0})

        self.registry.factories["evaluators"]["controlled"] = lambda config: SlowEvaluator()
        with patch("agent_optimizer.runner.time.monotonic", side_effect=lambda: self.now):
            _, summary = self.run_experiment()
        self.assertEqual(summary["status"], "budget_exhausted")
        self.assertEqual(summary["groups"][0]["selected"], [])
        record = self.persisted()[2][0]
        self.assertEqual(record["metrics"]["agent_tokens"], 7)
        self.assertIsNone(record["metrics"]["passed"])

    def test_source_time_is_in_global_budget(self):
        def slow_source(agent, target):
            result = materialize_agent(agent, target)
            self.now = 11
            return result

        with patch("agent_optimizer.runner.time.monotonic", side_effect=lambda: self.now), \
                patch("agent_optimizer.runner.materialize_agent", side_effect=slow_source):
            _, summary = self.run_experiment()
        self.assertEqual(summary["status"], "budget_exhausted")
        self.assertEqual(summary["trials_used"], 0)
        self.assertTrue((self.persisted()[0] / "report.md").is_file())

    def test_source_interrupt_and_error_have_complete_summary_envelope(self):
        for exception, status in [(KeyboardInterrupt(), "interrupted"),
                                  (ConfigurationError("source missing"), "source_error")]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                self.output = Path(directory)
                with patch("agent_optimizer.runner.materialize_agent", side_effect=exception):
                    if status == "source_error":
                        with self.assertRaises(ConfigurationError):
                            self.run_experiment()
                    else:
                        try:
                            _, summary = self.run_experiment()
                        except KeyboardInterrupt:
                            self.fail("Source interruption escaped without a durable summary")
                        self.assertEqual(summary["status"], status)
                run, summary, _ = self.persisted()
                self.assertEqual(summary["status"], status)
                self.assertEqual(summary["trials_used"], 0)
                self.assertEqual(summary["groups"], [])
                self.assertTrue((run / "manifest.json").is_file())
                self.assertTrue((run / "report.md").is_file())

    def test_usage_is_durable_at_call_time_before_stage_exit(self):
        for exception, status in [(BudgetExceeded("search limit"), "budget_exhausted"),
                                  (RuntimeError("optimizer bug"), "error"),
                                  (KeyboardInterrupt(), "interrupted")]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                self.output = Path(directory)

                def optimize(context, seeds, config):
                    context.record_usage(13, 5, None)
                    path = next(self.output.glob("*/events.jsonl"))
                    events = [json.loads(line) for line in path.read_text().splitlines()]
                    usage = [e for e in events if e["event"] == "optimizer_usage"]
                    self.assertEqual(len(usage), 1)
                    self.assertEqual((usage[0]["agent_id"], usage[0]["harness_id"],
                                      usage[0]["stage_id"]), ("rtl-solo", "fixture", "search"))
                    raise exception

                self.optimizer(optimize)
                if status == "error":
                    with self.assertRaisesRegex(RuntimeError, "optimizer bug"):
                        self.run_experiment()
                else:
                    self.run_experiment()
                run, summary, _ = self.persisted()
                self.assertEqual(summary["status"], status)
                group = summary["groups"][0]
                self.assertEqual(group["trial_count"], 1)
                self.assertIsNotNone(group["baseline"])
                self.assertEqual(group["selected"], [])
                self.assertEqual(group["optimizer_usage"][0]["input_tokens"], 13)
                self.assertEqual(group["stages"][0]["status"], status)
                self.assertEqual(json.loads(next(run.rglob("search.json")).read_text())["status"], status)

    def test_trial_limit_preserves_current_stage_completed_evaluations(self):
        def optimize(context, seeds, config):
            return OptimizationResult([context.propose(seeds[0], {"prompts/system.md": text}, "search")
                                       for text in ("first", "second")])

        self.optimizer(optimize)
        self.spec["budget"]["max_trials"] = 2
        _, summary = self.run_experiment()
        self.assertEqual(summary["status"], "budget_exhausted")
        self.assertEqual(summary["trials_used"], 2)
        group = summary["groups"][0]
        self.assertEqual(group["trial_count"], 2)
        self.assertEqual(len(group["stages"][0]["evaluated"]), 1)
        self.assertEqual(group["selected"], [])

    def test_optimizer_return_after_deadline_preserves_usage_and_checkpoint(self):
        def optimize(context, seeds, config):
            context.record_usage(9, 4, 0.01)
            self.now = 11
            return OptimizationResult(seeds, {"iteration": 1})

        self.optimizer(optimize)
        with patch("agent_optimizer.runner.time.monotonic", side_effect=lambda: self.now):
            _, summary = self.run_experiment()
        self.assertEqual(summary["status"], "budget_exhausted")
        group = summary["groups"][0]
        self.assertEqual(group["optimizer_usage"][0]["cost_usd"], 0.01)
        self.assertEqual(group["stages"][0]["checkpoint"], {"iteration": 1})
        self.assertEqual(group["selected"], [])

    def test_final_test_deadline_keeps_validation_selection(self):
        owner = self

        class SlowTestEvaluator(Evaluator):
            def evaluate(self, task, output_dir, timeout_seconds):
                if task.split == "test":
                    owner.now = 11
                return super().evaluate(task, output_dir, timeout_seconds)

        self.registry.factories["evaluators"]["controlled"] = lambda config: SlowTestEvaluator()
        self.spec["final_test"] = True
        with patch("agent_optimizer.runner.time.monotonic", side_effect=lambda: self.now):
            _, summary = self.run_experiment()
        self.assertEqual(summary["status"], "budget_exhausted")
        group = summary["groups"][0]
        self.assertEqual(group["selected"][0]["candidate_id"], "c0001")
        self.assertEqual(group["final_test"], [])
        self.assertEqual(group["trial_count"], 2)

    def test_group_initialization_error_keeps_group_identity(self):
        calls = 0

        def evaluator(config):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("initialization failed")
            return Evaluator()

        self.registry.factories["evaluators"]["controlled"] = evaluator
        with self.assertRaisesRegex(RuntimeError, "initialization failed"):
            self.run_experiment()
        _, summary, _ = self.persisted()
        self.assertEqual(summary["status"], "error")
        self.assertEqual(len(summary["groups"]), 1)
        group = summary["groups"][0]
        self.assertEqual((group["agent_id"], group["harness_id"], group["status"]),
                         ("rtl-solo", "fixture", "error"))
        self.assertIsNone(group["baseline"])
        self.assertEqual(group["trial_count"], 0)

    def test_manifest_input_error_still_writes_error_summary(self):
        self.spec["benchmark"] = "missing-benchmark.json"
        with self.assertRaises(FileNotFoundError):
            self.run_experiment()
        _, summary, _ = self.persisted()
        self.assertEqual(summary["status"], "error")
        self.assertEqual(summary["error_type"], "FileNotFoundError")
        self.assertEqual(summary["trials_used"], 0)

    def test_final_test_interrupt_preserves_frozen_selection_and_completed_test(self):
        def optimize(context, seeds, config):
            return OptimizationResult([context.propose(seeds[0], {"prompts/system.md": "new"}, "search")])

        class InterruptEvaluator:
            tests = 0

            def evaluate(self, task, output_dir, timeout_seconds):
                if task.split == "test":
                    self.tests += 1
                    if self.tests == 2:
                        raise KeyboardInterrupt()
                return Evaluation("passed", {"passed": 1.0})

        self.optimizer(optimize)
        self.spec["final_test"] = True
        self.registry.factories["evaluators"]["controlled"] = lambda config: InterruptEvaluator()
        run, summary = self.run_experiment()
        self.assertEqual(summary["status"], "interrupted")
        self.assertEqual(len(summary["groups"]), 1)
        group = summary["groups"][0]
        self.assertEqual(group["trial_count"], 4)
        self.assertEqual(len(group["final_test"]), 1)
        self.assertEqual(group["selected"][0]["candidate_id"], "c0002")
        self.assertEqual(json.loads(next(run.rglob("frozen_selection.json")).read_text()), group["selected"])
        records = [e for e in self.persisted()[2] if e["event"] == "trial_completed"]
        self.assertEqual([r["status"] for r in records], ["passed", "passed", "passed", "interrupted"])

    def test_baseline_interrupt_keeps_previous_group(self):
        self.spec["_agents"].append(replace(self.spec["_agents"][0], id="second-agent"))

        class InterruptHarness(Harness):
            def run(self, request):
                if "second-agent" in request.workspace.parts:
                    raise KeyboardInterrupt()
                return super().run(request)

        self.registry.factories["harnesses"]["fixture"] = InterruptHarness
        _, summary = self.run_experiment()
        self.assertEqual(summary["status"], "interrupted")
        self.assertEqual(len(summary["groups"]), 2)
        first, second = summary["groups"]
        self.assertEqual(first["status"], "completed")
        self.assertEqual(second["status"], "interrupted")
        self.assertIsNone(second["baseline"])
        self.assertEqual(second["trial_count"], 1)

    def test_output_root_link_error_is_recorded_with_trial_identity_and_reraised(self):
        class LinkHarness(Harness):
            def run(self, request):
                request.task_dir.rename(request.workspace / "original-task")
                request.task_dir.symlink_to(request.agent_dir, target_is_directory=True)
                return super().run(request)

        self.registry.factories["harnesses"]["fixture"] = LinkHarness
        with self.assertRaises(ConfigurationError):
            self.run_experiment()
        run, summary, events = self.persisted()
        self.assertEqual(summary["status"], "error")
        self.assertEqual(len(summary["groups"]), 1)
        self.assertEqual(summary["groups"][0]["trial_count"], 1)
        record = next(e for e in events if e["event"] == "trial_completed")
        self.assertEqual(record["status"], "error")
        self.assertFalse(record["valid"])
        self.assertEqual(record["error_type"], "ConfigurationError")
        self.assertEqual((record["agent_id"], record["candidate_id"], record["split"]),
                         ("rtl-solo", "c0001", "validation"))
        self.assertEqual(next(run.rglob("result.json")).parent.name, record["trial_id"])

    def test_report_and_rerank_accept_nullable_baseline(self):
        class InterruptHarness:
            def run(self, request):
                raise KeyboardInterrupt()

        self.registry.factories["harnesses"]["fixture"] = InterruptHarness
        run, summary = self.run_experiment()
        self.assertEqual(len(summary["groups"]), 1)
        goal = self.output / "objective.toml"
        goal.write_text('[objective]\n[[objective.metrics]]\nname="solve_rate"\n'
                        'source="passed"\ndirection="maximize"\n')
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(main(["rerank", str(run), str(goal)]), 0)
        self.assertEqual(json.loads(stdout.getvalue())[0]["selected"], [])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["report", str(run), "--csv", str(self.output / "trials.csv")]), 0)
        self.assertIn("interrupted", (self.output / "trials.csv").read_text())


class SelectionTests(unittest.TestCase):
    def test_pareto_rejects_explicit_keep_in_config_and_direct_selector(self):
        objective = {"mode": "pareto", "keep": 1,
                     "metrics": [{"name": "quality", "direction": "maximize"}]}
        for call in (lambda: validate_objective(objective), lambda: select([], objective)):
            with self.subTest(call=call), self.assertRaises(ConfigurationError):
                call()

    def test_invalid_and_partial_rows_cannot_be_selected(self):
        rows = [{"candidate_id": "invalid", "valid": False, "metrics": {"quality": 10}},
                {"candidate_id": "partial", "partial": True, "metrics": {"quality": 20}},
                {"candidate_id": "complete", "valid": True, "metrics": {"quality": 1}}]
        for mode in ("pareto", "weighted", "lexicographic"):
            with self.subTest(mode=mode):
                self.assertEqual(select(rows, {"mode": mode, "metrics": [
                    {"name": "quality", "direction": "maximize"}]}), [rows[2]])
