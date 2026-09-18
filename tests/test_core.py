from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from agent_optimizer.config import load_agent, load_experiment, load_tasks, validate_objective
from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.objectives import aggregate, select
from agent_optimizer.runner import Budget, GroupRunner, preflight, run_experiment
from support import demo_registry as Registry
from agent_optimizer.workspace import CandidateStore, digest, safe_path
from agent_optimizer.results import EventStore

from support import test_project, resolved_agent

_TEST_WORKSPACE, ROOT = test_project()


class ObjectiveTests(unittest.TestCase):
    def setUp(self):
        self.objective = {"mode": "pareto", "metrics": [
            {"name": "quality", "direction": "maximize"},
            {"name": "seconds", "direction": "minimize"},
        ]}

    def test_pareto_tradeoffs_missing_and_dominated(self):
        rows = [{"candidate_id": str(i), "metrics": {"quality": q, "seconds": s}}
                for i, (q, s) in enumerate([(1, 10), (0.8, 5), (0.5, 15), (1, None)])]
        self.assertEqual({r["candidate_id"] for r in select(rows, self.objective)}, {"0", "1"})

    def test_constraints_and_lexicographic(self):
        obj = {**self.objective, "mode": "lexicographic", "constraints": [{"metric": "seconds", "max": 6}]}
        rows = [{"metrics": {"quality": 1, "seconds": 10}}, {"metrics": {"quality": 0.8, "seconds": 5}}]
        self.assertEqual(select(rows, obj), [rows[1]])

    def test_weighted_scales(self):
        obj = {"mode": "weighted", "metrics": [
            {"name": "q", "direction": "maximize", "scale": 1},
            {"name": "s", "direction": "minimize", "scale": 100},
        ]}
        rows = [{"metrics": {"q": 1, "s": 10}}, {"metrics": {"q": 0.8, "s": 5}}]
        self.assertEqual(select(rows, obj), [rows[0]])

    def test_missing_metric_not_zero(self):
        result = aggregate([{"metrics": {"tokens": 10}}, {"metrics": {"tokens": None}}],
                           [{"name": "tokens", "aggregate": "mean"}])
        self.assertIsNone(result["tokens"])

    def test_percentile_and_sum(self):
        rows = [{"metrics": {"v": i}} for i in range(1, 21)]
        result = aggregate(rows, [{"name": "p95", "source": "v", "aggregate": "p95"},
                                  {"name": "total", "source": "v", "aggregate": "sum"}])
        self.assertEqual(result, {"p95": 19, "total": 210})

    def test_invalid_objective_rejected(self):
        with self.assertRaises(ConfigurationError):
            validate_objective({"metrics": [{"name": "x", "direction": "down"}]})


class WorkspaceTests(unittest.TestCase):
    def test_snapshot_lineage_edit_boundary_and_source_unchanged(self):
        agent = load_agent(ROOT / "examples/minimal/solo.toml")
        original = digest(agent.source.path)
        with tempfile.TemporaryDirectory() as directory:
            agent = resolved_agent(ROOT / "examples/minimal/solo.toml", Path(directory) / "source")
            store = CandidateStore(Path(directory) / "candidates", agent)
            base = store.create()
            child = store.create(base, {"prompts/system.md": "changed"}, "test")
            self.assertEqual(child.parents, (base.id,))
            self.assertNotEqual(child.content_hash, base.content_hash)
            self.assertEqual(digest(agent.source.path), original)
            with self.assertRaises(ConfigurationError):
                store.create(base, {"../escape": "bad"})
            with self.assertRaises(ConfigurationError):
                store.create(base, {"agent.toml": "bad"})

    def test_symlink_and_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "link").symlink_to("/etc/passwd")
            with self.assertRaises(ConfigurationError):
                digest(root)
            for relative in ["../secret", "/etc/passwd", "a/../../x", "a\\b"]:
                with self.assertRaises(ConfigurationError):
                    safe_path(root, relative)

    def test_cross_agent_transfer_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left = CandidateStore(root / "a", resolved_agent(ROOT / "examples/minimal/solo.toml", root / "left-source"))
            right = CandidateStore(root / "b", resolved_agent(ROOT / "examples/minimal/team.toml", root / "right-source"))
            with self.assertRaises(ConfigurationError):
                right.create(left.create(), {"prompts/system.md": "wrong"})


class ExperimentTests(unittest.TestCase):
    def test_multi_agent_demo_and_private_data_boundary(self):
        spec = load_experiment(ROOT / "examples/minimal/experiment.toml")
        before = [digest(a.source.path) for a in spec["_agents"]]
        with tempfile.TemporaryDirectory() as directory:
            run, summary = run_experiment(spec, Registry(), Path(directory))
            self.assertEqual(summary["status"], "completed")
            self.assertTrue(summary["synthetic"])
            self.assertEqual({g["agent_id"] for g in summary["groups"]}, {"rtl-solo", "rtl-team"})
            solo = next(g for g in summary["groups"] if g["agent_id"] == "rtl-solo")
            self.assertEqual(solo["baseline"]["metrics"]["solve_rate"], 0)
            self.assertEqual(solo["selected"][0]["metrics"]["solve_rate"], 1)
            for request in run.rglob("request.json"):
                value = json.loads(request.read_text())
                self.assertNotIn("evaluation", value)
                self.assertNotIn("expected", value)
            for group in summary["groups"]:
                frozen = run / group["agent_id"] / group["harness_id"] / "frozen_selection.json"
                self.assertTrue(frozen.is_file())
                self.assertTrue(group["final_test"])
            self.assertEqual([digest(a.source.path) for a in spec["_agents"]], before)

    def test_branch_gate_skip_does_not_remove_other_branch(self):
        spec = load_experiment(ROOT / "examples/minimal/branching.toml")
        with tempfile.TemporaryDirectory() as directory:
            _, summary = run_experiment(spec, Registry(), Path(directory))
            solo = next(g for g in summary["groups"] if g["agent_id"] == "rtl-solo")
            self.assertEqual(solo["stages"][1]["status"], "skipped")
            self.assertEqual(solo["selected"][0]["metrics"]["solve_rate"], 1)

    def test_matrix_two_harness_profiles_remains_separate(self):
        spec = load_experiment(ROOT / "examples/minimal/experiment.toml")
        other = copy.deepcopy(spec["_profiles"][0])
        other["id"] = "fixture-second"
        spec["_profiles"].append(other)
        with tempfile.TemporaryDirectory() as directory:
            _, summary = run_experiment(spec, Registry(), Path(directory))
            self.assertEqual(len(summary["groups"]), 4)
            self.assertEqual(len({(g["agent_id"], g["harness_id"]) for g in summary["groups"]}), 4)

    def test_trial_budget_stops_and_keeps_evidence(self):
        spec = load_experiment(ROOT / "examples/minimal/experiment.toml")
        spec["budget"]["max_trials"] = 1
        with tempfile.TemporaryDirectory() as directory:
            run, summary = run_experiment(spec, Registry(), Path(directory))
            self.assertEqual(summary["status"], "budget_exhausted")
            self.assertEqual(summary["trials_used"], 1)
            self.assertTrue(list(run.rglob("result.json")))

    def test_planned_optimizer_never_falls_back(self):
        spec = load_experiment(ROOT / "examples/minimal/research-planned.toml")
        with self.assertRaises(UnavailableError):
            preflight(spec, Registry())

    def test_family_split_leakage_rejected(self):
        data = json.loads((ROOT / "examples/minimal/tasks.json").read_text())
        for task in data["tasks"]:
            task["family"] = "same-design"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text(json.dumps(data))
            with self.assertRaises(ConfigurationError):
                load_tasks(path)

    def test_mutated_candidate_rejected_before_execution(self):
        spec = load_experiment(ROOT / "examples/minimal/experiment.toml")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = resolved_agent(ROOT / "examples/minimal/solo.toml", root / "source")
            group = GroupRunner(spec, agent, spec["_profiles"][0], root,
                                Registry(), Budget(spec["budget"]), EventStore(root / "events.jsonl"))
            candidate = group.candidates.create()
            (candidate.path / "prompts/system.md").write_text("modified behind the store")
            with self.assertRaises(ConfigurationError):
                group.evaluate(candidate, "validation")

    def test_private_simulation_files_never_enter_agent_workspace(self):
        from agent_optimizer.contracts import Evaluation

        class CheckingEvaluator:
            def evaluate(self, task, output_dir, timeout_seconds):
                self_test.assertTrue(task.evaluation.get("private_files"))
                workspace = output_dir.parent / "agent_workspace"
                self_test.assertFalse((workspace / "private").exists())
                self_test.assertFalse((workspace / "task/private").exists())
                self_test.assertNotIn("$fatal", (workspace / "request.json").read_text())
                return Evaluation("passed", {"passed": 1.0})

        self_test = self
        spec = load_experiment(ROOT / "examples/minimal/experiment.toml")
        tasks, metadata = load_tasks(ROOT / "examples/rtl-debugger/tasks.json")
        # Keep real private testbench data, replace only the simulator for this boundary test.
        spec["_tasks"], spec["_benchmark_metadata"], spec["evaluator"] = tasks, metadata, "iverilog"
        registry = Registry()
        registry.factories["evaluators"]["iverilog"] = lambda config: CheckingEvaluator()
        with tempfile.TemporaryDirectory() as directory:
            _, summary = run_experiment(spec, registry, Path(directory))
            self.assertEqual(summary["status"], "completed")

    def test_rerank_rejects_changed_metric_semantics(self):
        import contextlib
        import io
        from agent_optimizer.cli import main
        spec = load_experiment(ROOT / "examples/minimal/experiment.toml")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run, _ = run_experiment(spec, Registry(), root)
            goal = root / "goal.toml"
            goal.write_text('[objective]\n[[objective.metrics]]\nname="solve_rate"\n'
                            'source="agent_tokens"\ndirection="minimize"\n')
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["rerank", str(run), str(goal)]), 2)

    def test_cycle_and_unknown_option_rejected(self):
        text = (ROOT / "examples/minimal/experiment.toml").read_text()
        text = text.replace('project_root = "../.."', f'project_root = "{ROOT}"')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiment.toml"
            path.write_text(text.replace('inputs = ["baseline"]', 'inputs = ["repair"]', 1))
            with self.assertRaises(ConfigurationError):
                load_experiment(path)
            path.write_text('concurrency = 8\n' + text)
            with self.assertRaises(ConfigurationError):
                load_experiment(path)


if __name__ == "__main__":
    unittest.main()
