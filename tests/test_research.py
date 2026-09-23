"""Research names must execute distinct, bounded train/validation searches."""
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import Candidate
from agent_optimizer.registry import Registry
from agent_optimizer.runner import run_experiment
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


if __name__ == "__main__":
    unittest.main()
