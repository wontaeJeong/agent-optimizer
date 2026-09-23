"""Research names must execute distinct, bounded train/validation searches."""
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import Candidate, UnavailableError
from agent_optimizer.registry import Registry
from agent_optimizer.runner import run_experiment
from agent_optimizer.optimizers.ecdysis import _train_score, group_failures
from agent_optimizer.optimizers.meta_harness import _score as meta_score
from support import test_project


class ResearchSearchTests(unittest.TestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)
        self.spec = load_experiment(self.root / "examples/minimal/experiment.toml")
        self.spec["_agents"] = self.spec["_agents"][:1]
        self.spec["final_test"] = True
        self.spec["budget"]["max_trials"] = 20

    def test_gepa_changes_snapshot_and_freezes_selection_before_test(self):
        self.spec["stages"] = [{"id": "gepa", "optimizer": "gepa", "max_trials": 7,
                                "config": {"file": "configs/strategy.json", "iterations": 1}}]
        self.spec["final_stages"] = ["gepa"]
        sent = []

        def reply(messages, **kwargs):
            sent.append(messages)
            return {"choices": [{"message": {"content": '{"content":"{\\"repair\\": true}"}'}}]}

        environment = {"MODEL_BASE_URL": "http://localhost:12345/v1", "MODEL_API_KEY": "fixture-key",
                       "MODEL_ID": "offline-fixture"}
        with patch.dict(os.environ, environment), patch("agent_optimizer.optimizers.research.complete",
                                                         side_effect=reply):
            root, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        stage = summary["groups"][0]["stages"][0]
        self.assertEqual(stage["status"], "completed")
        self.assertEqual(summary["groups"][0]["selected"][0]["metrics"]["solve_rate"], 1.0)
        self.assertIn("frontier", stage["checkpoint"])
        self.assertEqual((self.root / "examples/minimal/agents/solo/configs/strategy.json").read_text(),
                         '{"repair": false}\n')
        events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
        self.assertIn("optimizer_iteration_started", [row["event"] for row in events])
        self.assertNotIn("fixture-test", json.dumps(sent))
        self.assertEqual(len(list(root.rglob("frozen_selection.json"))), 1)
        self.assertEqual(summary["groups"][0]["optimizer_usage"][0]["input_tokens"], None)

    def test_research_model_failure_is_recorded_not_replaced_by_baseline(self):
        self.spec["stages"] = [{"id": "gepa", "optimizer": "gepa", "max_trials": 5,
                                "config": {"file": "configs/strategy.json", "iterations": 1}}]
        self.spec["final_stages"] = ["gepa"]
        environment = {"MODEL_BASE_URL": "http://localhost:12345/v1", "MODEL_API_KEY": "fixture-key"}
        with patch.dict(os.environ, environment), patch("agent_optimizer.optimizers.research.complete",
                                                         side_effect=UnavailableError("model unavailable")):
            with self.assertRaisesRegex(UnavailableError, "model unavailable"):
                run_experiment(self.spec, Registry(), self.root / "runs")
        summary_file = next((self.root / "runs").rglob("summary.json"))
        summary = json.loads(summary_file.read_text())
        self.assertEqual(summary["status"], "error")
        self.assertEqual(summary["groups"][0]["selected"], [])

    def test_missing_research_model_config_fails_before_any_trial(self):
        self.spec["stages"] = [{"id": "gepa", "optimizer": "gepa", "max_trials": 5,
                                "config": {"file": "configs/strategy.json", "iterations": 1}}]
        self.spec["final_stages"] = ["gepa"]
        output = self.root / "runs"
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex((UnavailableError, ValueError), "MODEL_ENDPOINT|MODEL_BASE_URL"):
                run_experiment(self.spec, Registry(), output)
        self.assertFalse(output.exists())

    def test_gepa_candidate_uses_bounded_train_minibatch(self):
        original = next(t for t in self.spec["_tasks"] if t.split == "train")
        self.spec["_tasks"] += [replace(original, id=f"extra-train-{index}", family=f"extra-{index}")
                                for index in range(2)]
        self.spec["stages"] = [{"id": "gepa", "optimizer": "gepa", "max_trials": 7,
                                "config": {"file": "configs/strategy.json", "iterations": 1,
                                           "batch_size": 1}}]
        self.spec["final_stages"] = ["gepa"]
        response = {"choices": [{"message": {"content": '{"content":"{\\"repair\\": true}"}'}}]}
        environment = {"MODEL_BASE_URL": "http://localhost:12345/v1", "MODEL_API_KEY": "fixture-key"}
        with patch.dict(os.environ, environment), patch("agent_optimizer.optimizers.research.complete",
                                                         return_value=response):
            root, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        records = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()
                   if '"event": "trial_completed"' in line]
        candidate_ids = {r["candidate_id"] for r in records if r["split"] == "train" and
                         r["candidate_id"] != "c0001"}
        self.assertEqual(len(candidate_ids), 1)
        self.assertEqual(len([r for r in records if r["split"] == "train"
                              and r["candidate_id"] in candidate_ids]), 1)

    def test_gepa_keeps_incomparable_frontier_then_merges_complementary_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            base.joinpath("prompt.md").write_text("seed")
            seed = Candidate("seed", "fixture", base, "seed-hash")

            class Context:
                candidates = []

                def evaluate(self, candidate):
                    return {"valid": True, "split": "train"}

                def train_task_ids(self):
                    return ["train-1"]

                def evaluate_batch(self, candidate, task_ids):
                    return {"valid": True, "split": "train"}

                def evaluate_validation(self, candidate):
                    score = {"seed": (0, 0), "left": (1, 0), "right": (0, 1), "both": (1, 1)}[
                        (candidate.path / "prompt.md").read_text()]
                    return {"valid": True, "tasks": [
                        {"task_id": f"val-{i}", "valid": True, "metrics": {"passed": score[i]}}
                        for i in range(2)]}

                def history(self):
                    return [{"candidate_id": "seed", "task_id": "train-1",
                             "metrics": {"passed": 0}, "feedback": "needs repair"}]

                def propose(self, parent, files, producer):
                    name = f"c{len(self.candidates) + 1}"
                    folder = base / name
                    folder.mkdir()
                    (folder / "prompt.md").write_text(files["prompt.md"])
                    candidate = Candidate(name, "fixture", folder, name, parents=(parent.id,),
                                          producer=producer)
                    self.candidates.append(candidate)
                    return candidate

                def remaining_seconds(self):
                    return 10

                def record_usage(self, *args):
                    pass

                def emit(self, event, **fields):
                    pass

            responses = iter("left right both".split())

            def reply(messages, **kwargs):
                return {"choices": [{"message": {"content": json.dumps({"content": next(responses)})}}]}

            environment = {"MODEL_BASE_URL": "http://localhost:12345/v1", "MODEL_API_KEY": "fixture-key"}
            with patch.dict(os.environ, environment), patch("agent_optimizer.optimizers.research.complete",
                                                             side_effect=reply):
                from agent_optimizer.optimizers.gepa import GEPAOptimizer
                result = GEPAOptimizer().optimize(Context(), [seed],
                                                  {"file": "prompt.md", "iterations": 2, "merge": True})
            self.assertEqual([item.id for item in result.candidates], ["c3"])
            self.assertEqual(result.checkpoint["merges"][0]["parents"], ["c1", "c2"])

    def test_meta_harness_rejects_invalid_code_then_selects_runnable_scaffold(self):
        source = self.root / "examples/minimal/agents/solo/src/fixture_agent.py"
        repaired = source.read_text().replace("if strategy.get('repair'):", "if True:")
        self.spec["stages"] = [{"id": "meta", "optimizer": "meta_harness", "max_trials": 8,
                                "config": {"file": "src/fixture_agent.py", "iterations": 2}}]
        self.spec["final_stages"] = ["meta"]
        responses = iter(["not python !!!", repaired])

        def reply(messages, **kwargs):
            return {"choices": [{"message": {"content": json.dumps({"content": next(responses)})}}]}

        environment = {"MODEL_BASE_URL": "http://localhost:12345/v1", "MODEL_API_KEY": "fixture-key"}
        with patch.dict(os.environ, environment), patch("agent_optimizer.optimizers.research.complete",
                                                         side_effect=reply):
            _, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        stage = summary["groups"][0]["stages"][0]
        self.assertEqual([entry["status"] for entry in stage["checkpoint"]["iterations"]],
                         ["invalid_interface", "accepted"])
        self.assertEqual(summary["groups"][0]["selected"][0]["metrics"]["solve_rate"], 1.0)
        self.assertIn("if strategy.get('repair'):", source.read_text())

    def test_ecdysis_prioritizes_cross_task_failures_and_strictly_accepts_improvement(self):
        original = next(t for t in self.spec["_tasks"] if t.split == "train")
        self.spec["_tasks"].append(replace(original, id="other-train", family="other-family"))
        source = self.root / "examples/minimal/agents/solo/src/fixture_agent.py"
        repaired = source.read_text().replace("if strategy.get('repair'):", "if True:")
        self.spec["stages"] = [{"id": "ecdysis", "optimizer": "ecdysis", "max_trials": 10,
                                "config": {"file": "src/fixture_agent.py", "rounds": 2,
                                           "refinement_passes": 2}}]
        self.spec["final_stages"] = ["ecdysis"]
        responses = iter([{"spec": "repair shared failures"}, {"spec": "preserve task generality"},
                          {"content": repaired}, {"spec": "no further change"},
                          {"spec": "keep existing"}, {"content": repaired}])

        def reply(messages, **kwargs):
            return {"choices": [{"message": {"content": json.dumps(next(responses))}}]}

        environment = {"MODEL_BASE_URL": "http://localhost:12345/v1", "MODEL_API_KEY": "fixture-key"}
        with patch.dict(os.environ, environment), patch("agent_optimizer.optimizers.research.complete",
                                                         side_effect=reply):
            _, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        rounds = summary["groups"][0]["stages"][0]["checkpoint"]["rounds"]
        self.assertEqual(rounds[0]["groups"][0]["distinct_tasks"], 2)
        self.assertEqual([round_["accepted"] for round_ in rounds], [True, False])
        self.assertEqual(summary["groups"][0]["selected"][0]["metrics"]["solve_rate"], 1.0)

    def test_ecdysis_groups_repeated_failures_by_distinct_tasks(self):
        records = [
            {"task_id": "task-one", "candidate_id": "c1", "status": "failed",
             "metrics": {"passed": 0.0}, "feedback": "mismatch"},
            {"task_id": "task-one", "candidate_id": "c1", "status": "failed",
             "metrics": {"passed": 0.0}, "feedback": "mismatch"},
            {"task_id": "task-two", "candidate_id": "c1", "status": "failed",
             "metrics": {"passed": 0.0}, "feedback": "different instance"},
        ]
        groups = group_failures(records, threshold=1.0, metric="passed")
        self.assertEqual(groups[0]["distinct_tasks"], 2)
        self.assertEqual(groups[0]["failure_count"], 3)

    def test_scaffold_optimizers_respect_minimize_objectives(self):
        validation = {"valid": True, "tasks": [
            {"metrics": {"latency": 2.0}}, {"metrics": {"latency": 4.0}}]}
        self.assertEqual(meta_score(validation, "latency", "minimize"), -3.0)
        self.assertEqual(_train_score({"valid": True, "metrics": {"latency": 2.0}},
                                      "latency", "minimize"), -2.0)
        failures = group_failures([
            {"task_id": "slow", "status": "passed", "metrics": {"latency": 5.0}},
            {"task_id": "fast", "status": "passed", "metrics": {"latency": 1.0}}],
            threshold=2.0, metric="latency", direction="minimize")
        self.assertEqual(failures[0]["task_ids"], ["slow"])


if __name__ == "__main__":
    unittest.main()
