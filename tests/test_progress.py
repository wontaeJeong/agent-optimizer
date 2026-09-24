"""A blocking trial must leave enough durable state to locate its slow phase."""
import json
import unittest

from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError, Evaluation
from agent_optimizer.registry import Registry
from agent_optimizer.runner import run_experiment
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
