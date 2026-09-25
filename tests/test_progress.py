"""A blocking trial must leave enough durable state to locate its slow phase."""
import json
import io
import contextlib
import unittest

from agent_optimizer.config import load_experiment
from agent_optimizer.cli import main
from agent_optimizer.contracts import ConfigurationError, Evaluation
from agent_optimizer.registry import Registry
from agent_optimizer.runner import run_experiment
from agent_optimizer.terminal_report import PreparationStatus, ProgressDisplay
from support import test_project


class ProgressTests(unittest.TestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)
        self.spec = load_experiment(self.root / "examples/minimal/experiment.toml")
        self.spec["_agents"] = self.spec["_agents"][:1]
        self.spec.update(stages=[], final_stages=["baseline"], final_test=False)

    def test_trial_phase_start_is_durable_before_completion(self):
        root, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
        names = [event["event"] for event in events]
        for first, later in (("trial_started", "agent_started"),
                             ("agent_started", "evaluation_started"),
                             ("evaluation_started", "trial_completed")):
            self.assertLess(names.index(first), names.index(later))
        self.assertTrue(all(event["schema_version"] == 1 and event["timestamp"] for event in events))
        started = next(e for e in events if e["event"] == "trial_started")
        self.assertEqual((started["agent_id"], started["task_id"], started["split"]),
                         ("rtl-solo", "fixture-validation", "validation"))

    def test_terminal_progress_shows_known_iterations_budget_and_slowest_tasks(self):
        output = io.StringIO()
        display = ProgressDisplay(stream=output)
        display({"event": "optimizer_iteration_started", "timestamp": "2026-09-24T10:00:00Z",
                 "stage_id": "search", "iteration": 2, "total": 3})
        for task, duration in (("fast", 1.0), ("slow", 5.0)):
            display({"event": "trial_completed", "timestamp": "2026-09-24T10:00:00Z", "task_id": task,
                     "dataset": "demo", "metrics": {"task_wall_time_seconds": duration}})
        text = output.getvalue()
        self.assertIn("iteration=2/3", text)
        self.assertIn("completed=2", text)
        self.assertIn("slow: 5.00s", text)
        last_line = text.splitlines()[-1]
        self.assertLess(last_line.index("slow: 5.00s"), last_line.index("fast: 1.00s"))
        self.assertNotIn("ETA", text)

    def test_interactive_progress_uses_rich_styling_and_keeps_json_stdout_clean(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        output, terminal = io.StringIO(), Terminal()
        with contextlib.redirect_stdout(output), ProgressDisplay(stream=terminal) as progress:
            progress.configure_budget(4)
            progress({"event": "trial_completed", "timestamp": "2026-09-24T10:00:00Z",
                      "dataset": "fixture", "task_id": "slow",
                      "metrics": {"task_wall_time_seconds": 5.0}})
            print('{"status":"completed"}')
        self.assertEqual(json.loads(output.getvalue()), {"status": "completed"})
        self.assertIn("slow", terminal.getvalue())
        self.assertIn("remaining=3", terminal.getvalue())
        self.assertRegex(terminal.getvalue(), r"\x1b\[[0-9;]+m")

    def test_interactive_preparation_keeps_failure_visible(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with self.assertRaisesRegex(ValueError, "fixture failure"):
            with PreparationStatus("chosen", stream=terminal):
                raise ValueError("fixture failure")
        self.assertIn("dataset=chosen", terminal.getvalue())
        self.assertIn("failed", terminal.getvalue())
        self.assertRegex(terminal.getvalue(), r"\x1b\[[0-9;]+m")

    def test_named_operation_keeps_stdout_clean_and_marks_failure(self):
        output, status = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(ValueError, "fixture failure"):
                with PreparationStatus("host-api", stream=status, action="doctor", subject="check"):
                    raise ValueError("fixture failure")
        self.assertEqual(output.getvalue(), "")
        self.assertIn("[doctor] check=host-api starting", status.getvalue())
        self.assertIn("[doctor] check=host-api failed", status.getvalue())

    def test_configured_max_trial_budget_is_not_a_planned_total(self):
        output = io.StringIO()
        display = ProgressDisplay(stream=output)
        display.configure_budget(4)
        display({"event": "trial_completed", "timestamp": "2026-09-24T10:00:00Z", "task_id": "a",
                 "metrics": {"task_wall_time_seconds": 1.0}})
        text = output.getvalue()
        self.assertIn("MAX TRIAL BUDGET", text)
        self.assertIn("completed=1", text)
        self.assertIn("remaining=3", text)
        self.assertNotIn("planned", text)

    def test_run_command_passes_experiment_maximum_into_live_progress(self):
        progress = io.StringIO()
        with contextlib.redirect_stderr(progress), contextlib.redirect_stdout(io.StringIO()):
            result = main(["run", str(self.root / "examples/minimal/experiment.toml"),
                           "--output", str(self.root / "runs")])
        self.assertEqual(result, 0)
        self.assertIn("MAX TRIAL BUDGET completed=7 remaining=33 / 40", progress.getvalue())

    def test_optimizer_validation_view_omits_feedback_and_private_data(self):
        path = self.root / "examples/minimal/observer.py"
        path.write_text(
            "from agent_optimizer.contracts import OptimizationResult\n"
            "class Observer:\n"
            "    def optimize(self, context, seeds, config):\n"
            "        return OptimizationResult(seeds, {'view': context.evaluate_validation(seeds[0])})\n")
        self.spec["plugins"]["optimizers"] = {"observer": "examples/minimal/observer.py:Observer"}
        self.spec["stages"] = [{"id": "check", "optimizer": "observer"}]
        self.spec["final_stages"] = ["check"]
        root, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        view = summary["groups"][0]["stages"][0]["checkpoint"]["view"]
        self.assertEqual(view["split"], "validation")
        self.assertTrue(all(set(task) == {"task_id", "metrics", "valid"} for task in view["tasks"]))
        self.assertNotIn("evaluation", json.dumps(view))
        self.assertNotIn("artifacts", json.dumps(view))

    def test_one_stage_trial_allowance_does_not_starve_next_stage(self):
        greedy = self.root / "examples/minimal/greedy.py"
        greedy.write_text(
            "from agent_optimizer.contracts import OptimizationResult\n"
            "class Greedy:\n"
            "    def optimize(self, context, seeds, config):\n"
            "        for i in range(3):\n"
            "            child = context.propose(seeds[0], {'configs/strategy.json': "
            "'{\"repair\": true, \"iteration\": ' + str(i) + '}'}, 'greedy')\n"
            "            context.evaluate(child)\n"
            "        return OptimizationResult([child])\n"
            "class Modest:\n"
            "    def optimize(self, context, seeds, config):\n"
            "        return OptimizationResult(seeds)\n", encoding="utf-8")
        self.spec["plugins"]["optimizers"] = {
            "greedy": "examples/minimal/greedy.py:Greedy",
            "modest": "examples/minimal/greedy.py:Modest",
        }
        self.spec["stages"] = [{"id": "first", "optimizer": "greedy", "max_trials": 1},
                               {"id": "second", "optimizer": "modest", "max_trials": 1}]
        self.spec["final_stages"] = ["second"]
        root, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        stages = summary["groups"][0]["stages"]
        self.assertEqual([(stage["id"], stage["status"]) for stage in stages],
                         [("first", "budget_exhausted"), ("second", "completed")])
        self.assertTrue(summary["groups"][0]["selected"])

    def test_insufficient_global_budget_rejected_before_any_trials(self):
        self.spec["stages"] = [{"id": "first", "optimizer": "baseline", "max_trials": 2},
                               {"id": "second", "optimizer": "baseline", "max_trials": 2}]
        self.spec["budget"]["max_trials"] = 4
        output = self.root / "runs"
        with self.assertRaisesRegex(ConfigurationError, "reserve"):
            run_experiment(self.spec, Registry(), output)
        self.assertFalse(output.exists())

    def test_repeated_baseline_and_final_test_reserve_trials_before_run_directory(self):
        self.spec.update(stages=[{"id": "limited", "optimizer": "baseline", "max_trials": 1}],
                         repetitions=3, final_test=True, final_stages=["limited"])
        self.spec["budget"]["max_trials"] = 5  # Old calculation: 1 + 1 + 2 = 4; actual minimum: 3 + 1 + 6 = 10.
        output = self.root / "runs"
        with self.assertRaisesRegex(ConfigurationError, "at least 10 trials"):
            run_experiment(self.spec, Registry(), output)
        self.assertFalse(output.exists())

    def test_optimizer_can_sample_only_named_train_tasks(self):
        path = self.root / "examples/minimal/batch.py"
        path.write_text(
            "from agent_optimizer.contracts import ConfigurationError, OptimizationResult\n"
            "class Batch:\n"
            "    def optimize(self, context, seeds, config):\n"
            "        ids = context.train_task_ids()\n"
            "        try:\n"
            "            context.evaluate_batch(seeds[0], ['fixture-validation'])\n"
            "        except ConfigurationError:\n"
            "            denied = True\n"
            "        else:\n"
            "            denied = False\n"
            "        row = context.evaluate_batch(seeds[0], ids)\n"
            "        return OptimizationResult(seeds, {'denied': denied, 'ids': ids, 'row': row})\n")
        self.spec["plugins"]["optimizers"] = {"batch": "examples/minimal/batch.py:Batch"}
        self.spec["stages"] = [{"id": "batch", "optimizer": "batch"}]
        self.spec["final_stages"] = ["batch"]
        _, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        checkpoint = summary["groups"][0]["stages"][0]["checkpoint"]
        self.assertTrue(checkpoint["denied"])
        self.assertEqual(checkpoint["ids"], ["fixture-train"])
        self.assertEqual(checkpoint["row"]["split"], "train")

    def test_evaluator_receives_provider_options_without_changing_runtime_contract(self):
        options = []

        class Evaluator:
            def __init__(self, config):
                options.append(config)

            def evaluate(self, task, output_dir, timeout_seconds):
                return Evaluation("passed", {"passed": 1.0})

        self.spec["plugins"]["evaluators"] = {}
        self.spec["evaluator_config"] = {"sim_image": "pinned-evaluation-image"}
        registry = Registry()
        registry.factories["evaluators"]["text_fixture"] = Evaluator
        _, summary = run_experiment(self.spec, registry, self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        self.assertTrue(options)
        self.assertTrue(all(option["sim_image"] == "pinned-evaluation-image" for option in options))


if __name__ == "__main__":
    unittest.main()
