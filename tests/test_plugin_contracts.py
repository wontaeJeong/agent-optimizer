from __future__ import annotations

import contextlib
import hashlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.cli import main
from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError, OptimizationResult, UnavailableError
from agent_optimizer.registry import Registry
from agent_optimizer.runner import preflight, run_experiment
from agent_optimizer.workspace import digest
from support import ROOT, test_project


class PluginContractTests(unittest.TestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name) / "runs"
        self.spec = load_experiment(self.root / "examples/minimal/experiment.toml")
        self.spec["_agents"] = self.spec["_agents"][:1]
        self.spec.update(stages=[], final_stages=["baseline"], final_test=False)
        self.reference = "examples/minimal/evaluator.py:TextFixtureEvaluator"
        self.helper = "examples/minimal/helper.py"
        (self.root / self.helper).write_text("VALUE = 1\n")

    def manifest(self):
        run, summary = run_experiment(self.spec, Registry(), self.output)
        self.assertEqual(summary["status"], "completed")
        return json.loads((run / "manifest.json").read_text())

    def test_experiment_accepts_dependency_mapping(self):
        path = self.root / "examples/minimal/experiment.toml"
        path.write_text(path.read_text() + '\n[plugin_dependencies]\n'
                        '"evaluators/text_fixture" = ["examples/minimal/helper.py"]\n')
        spec = load_experiment(path)
        self.assertEqual(spec["plugin_dependencies"], {"evaluators/text_fixture": [self.helper]})
        preflight(spec, Registry())

    def test_dependency_only_edit_changes_manifest_fingerprint(self):
        self.spec["plugin_dependencies"] = {"evaluators/text_fixture": [self.helper]}
        before = self.manifest()
        (self.root / self.helper).write_text("VALUE = 2\n")
        after = self.manifest()
        self.assertNotEqual(before["plugin_sha256"], after["plugin_sha256"])
        self.assertEqual(before["plugin_sha256"][self.reference], after["plugin_sha256"][self.reference])
        self.assertEqual(after["plugin_sha256"][self.helper], hashlib.sha256(b"VALUE = 2\n").hexdigest())

    def test_unchanged_file_registration_needs_no_dependency_declaration(self):
        registry = Registry()
        preflight(self.spec, registry)
        preflight(self.spec, registry)
        manifest = self.manifest()
        expected = hashlib.sha256((self.root / "examples/minimal/evaluator.py").read_bytes()).hexdigest()
        self.assertEqual(manifest["plugin_sha256"], {self.reference: expected})

    def test_optimizer_and_harness_dependencies_are_fingerprinted(self):
        for kind, name, source in [
            ("optimizers", "team", "from agent_optimizer.optimizers.baseline import BaselineOptimizer as Plugin\n"),
            ("harnesses", "team", "from agent_optimizer.harnesses.command import FixtureHarness as Plugin\n"),
        ]:
            file = f"examples/minimal/{kind}.py"
            (self.root / file).write_text(source)
            self.spec["plugins"][kind] = {name: f"{file}:Plugin"}
            helper = f"examples/minimal/{kind}_helper.py"
            (self.root / helper).write_text("SETTING = 3\n")
            self.spec.setdefault("plugin_dependencies", {})[f"{kind}/{name}"] = [helper]
        fingerprints = self.manifest()["plugin_sha256"]
        for kind in ("optimizers", "harnesses"):
            with self.subTest(kind=kind):
                self.assertIn(f"examples/minimal/{kind}.py:Plugin", fingerprints)
                self.assertEqual(fingerprints.get(f"examples/minimal/{kind}_helper.py"),
                                 hashlib.sha256(b"SETTING = 3\n").hexdigest())

    def test_missing_escaping_and_nonfile_dependencies_fail_preflight(self):
        (self.root / "linked.py").symlink_to(self.root / self.helper)
        for path in ("missing.py", "../outside.py", str(self.root / self.helper),
                     "examples/minimal", "linked.py", "examples\\minimal\\helper.py", ""):
            with self.subTest(path=path):
                self.spec["plugin_dependencies"] = {"evaluators/text_fixture": [path]}
                with self.assertRaises(ConfigurationError):
                    preflight(self.spec, Registry())

    def test_dead_plugin_dependency_references_fail_preflight(self):
        for key in ("evaluators/typo", "unknown/text_fixture", "text_fixture", "optimizers/baseline"):
            with self.subTest(key=key):
                self.spec["plugin_dependencies"] = {key: [self.helper]}
                with self.assertRaises(ConfigurationError):
                    preflight(self.spec, Registry())

    def test_malformed_dependency_declarations_fail_preflight(self):
        for declaration in ([], None, {"evaluators/text_fixture": self.helper},
                            {"evaluators/text_fixture": [1]}, {"evaluators/text_fixture": {}}):
            with self.subTest(declaration=declaration):
                self.spec["plugin_dependencies"] = declaration
                with self.assertRaises(ConfigurationError):
                    preflight(self.spec, Registry())

    def test_malformed_plugin_inventory_has_configuration_diagnostic_before_loading(self):
        for plugins, diagnostic in (
            ([], "plugins must be a mapping"),
            ({"unknown": {}}, "Unknown plugin kind"),
            ({"unknown": 1}, "Unknown plugin kind"),
            ({"evaluators": 1}, "plugins.evaluators must be a mapping"),
            ({"evaluators": {"demo": 1}}, "file.py:Symbol"),
            ({"evaluators": {"demo": "missing_symbol"}}, "file.py:Symbol"),
        ):
            with self.subTest(plugins=plugins):
                self.spec["plugins"] = plugins
                with self.assertRaisesRegex(ConfigurationError, diagnostic):
                    preflight(self.spec, Registry())

    def test_invalid_dependency_is_rejected_before_plugin_code_executes(self):
        plugin = self.root / "examples/minimal/optimizer.py"
        plugin.write_text('raise AssertionError("plugin executed before dependency validation")\n')
        self.spec["plugins"]["optimizers"] = {"team": "examples/minimal/optimizer.py:Optimizer"}
        self.spec["plugin_dependencies"] = {"optimizers/team": ["missing.py"]}
        with self.assertRaises(ConfigurationError):
            preflight(self.spec, Registry())

    def test_dependency_cannot_shadow_registered_plugin_fingerprint(self):
        (self.root / self.reference).write_text("different file with a colon in its name\n")
        self.spec["plugin_dependencies"] = {"evaluators/text_fixture": [self.reference]}
        with self.assertRaises(ConfigurationError):
            preflight(self.spec, Registry())

    def test_file_plugin_can_replace_reserved_optimizer_slot(self):
        (self.root / "examples/minimal/optimizer.py").write_text(
            "from agent_optimizer.contracts import OptimizationResult\n"
            "class Optimizer:\n"
            "    def optimize(self, context, seeds, config):\n"
            "        return OptimizationResult(seeds, {'team_plugin': True})\n")
        self.spec["plugins"]["optimizers"] = {"meta_harness": "examples/minimal/optimizer.py:Optimizer"}
        self.spec.update(stages=[{"id": "team", "optimizer": "meta_harness"}], final_stages=["team"])
        _, summary = run_experiment(self.spec, Registry(), self.output)
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["groups"][0]["stages"][0]["checkpoint"], {"team_plugin": True})

    def test_installed_entrypoint_only_names_are_not_loaded(self):
        class Entry:
            name = "installed_team"

            def load(self):
                return object

        with patch("importlib.metadata.entry_points", return_value=[Entry()]), \
                patch("agent_optimizer.registry.entry_points", return_value=[Entry()], create=True):
            with self.assertRaises(UnavailableError):
                Registry().resolve("optimizers", "installed_team")

    def test_inventory_lists_only_implemented_integrations(self):
        inventory = Registry().describe()
        self.assertEqual(inventory["optimizers"]["implemented"], ["baseline", "file_variants"])
        self.assertFalse(inventory["optimizers"].get("planned"))

    def test_independent_file_optimizers_multi_agent_history_and_selection(self):
        # Team A repairs; separately implemented team B deliberately regresses.
        # A last-stage-only pool would incorrectly choose B for both Agents.
        (self.root / "team_a.py").write_text('''
from agent_optimizer.contracts import OptimizationResult
class Optimizer:
    def optimize(self, context, seeds, config):
        parent, = seeds
        initial = context.history()
        context.evaluate(parent)
        candidate = context.propose(parent, {"configs/strategy.json": '{"repair": true}'}, "team_a")
        context.evaluate(candidate)
        context.record_usage(10, 2, None)
        return OptimizationResult([candidate], {"seed": parent.id, "producer": parent.producer,
            "initial": initial, "history": context.history(), "candidate": candidate.id})
''')
        (self.root / "team_b.py").write_text('''
from agent_optimizer.contracts import OptimizationResult
class Search:
    def optimize(self, context, seeds, config):
        baseline = seeds[0]
        before = context.history()
        score = context.evaluate(baseline)
        after_baseline = context.history()
        child = context.propose(baseline, {"configs/strategy.json": '{"repair": false}',
            "prompts/system.md": "Independent team B"}, "team_b")
        context.record_usage(None, 3, None)
        context.evaluate(child)
        return OptimizationResult([child], {"seed": baseline.id, "producer": baseline.producer,
            "initial": before, "baseline_history": after_baseline, "history": context.history(),
            "baseline_score": score, "candidate": child.id})
''')
        self.spec["_agents"] = load_experiment(self.root / "examples/minimal/experiment.toml")["_agents"]
        self.spec["plugins"]["optimizers"] = {"team_a": "team_a.py:Optimizer", "team_b": "team_b.py:Search"}
        self.spec.update(stages=[{"id": "a", "optimizer": "team_a"}, {"id": "b", "optimizer": "team_b"}],
                         final_test=True)
        self.spec.pop("final_stages")
        originals = [digest(agent.source.path) for agent in self.spec["_agents"]]
        from agent_optimizer.runner import GroupRunner
        original_trial = GroupRunner.trial

        def checked_trial(group, candidate, task, repeat):
            if task.split == "test":
                a, b = [stage["checkpoint"] for stage in group.summary["stages"]]
                self.assertNotIn(a["candidate"], {row["candidate_id"] for row in b["history"]})
                frozen = json.loads((group.root / "frozen_selection.json").read_text())
                self.assertEqual(frozen, group.summary["selected"])
                self.assertEqual(frozen[0]["candidate_id"], group.summary["stages"][0]["checkpoint"]["candidate"])
            return original_trial(group, candidate, task, repeat)

        with patch.object(GroupRunner, "trial", checked_trial):
            run, summary = run_experiment(self.spec, Registry(), self.output)
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(len(summary["groups"]), 2)
        self.assertEqual(summary["trials_used"], 16)  # each: validation 3 + train 3 + test 2
        for group in summary["groups"]:
            self.assertEqual({stage["optimizer"] for stage in group["stages"]}, {"team_a", "team_b"})
            a, b = [stage["checkpoint"] for stage in group["stages"]]
            self.assertEqual((a["producer"], b["producer"]), ("baseline", "baseline"))
            self.assertEqual(a["seed"], b["seed"])
            self.assertEqual(a["initial"], [])
            self.assertEqual({row["candidate_id"] for row in b["initial"]}, {b["seed"]})
            self.assertEqual(b["initial"], b["baseline_history"])  # cached baseline, no duplicate trial
            for stage in (a, b):
                self.assertEqual({row["candidate_id"] for row in stage["history"]}, {stage["seed"], stage["candidate"]})
                self.assertTrue(all(row["split"] == "train" and row["agent_id"] == group["agent_id"]
                                    for row in stage["history"]))
            self.assertEqual(group["selected"][0]["candidate_id"], a["candidate"])
            self.assertEqual({usage["optimizer"] for usage in group["optimizer_usage"]}, {"team_a", "team_b"})
            self.assertEqual({usage["stage_id"] for usage in group["optimizer_usage"]}, {"a", "b"})
            for name in ("a", "b"):
                self.assertTrue((run / group["agent_id"] / group["harness_id"] / "stages" / f"{name}.json").is_file())
        self.assertEqual([digest(agent.source.path) for agent in self.spec["_agents"]], originals)
        # Explicit final subset still selects B, even though A has better validation.
        self.spec.update(final_stages=["b"], final_test=False)
        _, subset = run_experiment(self.spec, Registry(), self.output)
        for group in subset["groups"]:
            self.assertEqual(group["selected"][0]["candidate_id"], group["stages"][1]["checkpoint"]["candidate"])

    def test_team_optimizer_uses_train_feedback_and_durable_usage_only(self):
        class TeamOptimizer:
            def optimize(self, context, seeds, config):
                self.context = context
                self.initial_history = context.history()
                self.before = context.evaluate(seeds[0])
                self.feedback = context.history()
                candidate = context.propose(seeds[0], {"configs/strategy.json": '{"repair": true}'}, "team")
                self.after = context.evaluate(candidate)
                context.record_usage(12, 4, None)
                return OptimizationResult([candidate], {"iteration": 1, "parent": seeds[0].id})

        optimizer = TeamOptimizer()
        registry = Registry()
        registry.factories["optimizers"]["team"] = lambda: optimizer
        self.spec.update(stages=[{"id": "team-search", "optimizer": "team"}],
                         final_stages=["team-search"], final_test=True)
        source = self.spec["_agents"][0].source.path
        original = digest(source)
        run, summary = run_experiment(self.spec, registry, self.output)
        group = summary["groups"][0]
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(optimizer.initial_history, [])  # baseline validation already ran
        self.assertEqual(optimizer.before["split"], "train")
        self.assertEqual(optimizer.before["metrics"]["solve_rate"], 0)
        self.assertEqual(optimizer.after["split"], "train")
        self.assertEqual(optimizer.after["metrics"]["solve_rate"], 1)
        self.assertTrue(optimizer.feedback[0]["feedback"])
        history = optimizer.context.history()  # validation and final test have now run too
        self.assertEqual(len(history), 2)
        self.assertTrue(all(row["split"] == "train" for row in history))
        self.assertEqual({row["task_id"] for row in history}, {"fixture-train"})
        for split in ("validation", "test"):
            with self.subTest(split=split), self.assertRaises(TypeError):
                optimizer.context.evaluate(None, split=split)
        self.assertEqual(digest(source), original)
        self.assertEqual(group["selected"][0]["metrics"]["solve_rate"], 1)
        self.assertEqual({row["split"] for row in group["final_test"]}, {"test"})
        self.assertEqual(group["stages"][0]["checkpoint"]["iteration"], 1)
        events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
        usage = [event for event in events if event["event"] == "optimizer_usage"]
        self.assertEqual(usage, [{"event": "optimizer_usage", "agent_id": "rtl-solo",
                                 "harness_id": "fixture", "stage_id": "team-search", "optimizer": "team",
                                 "input_tokens": 12, "output_tokens": 4, "cost_usd": None}])
        self.assertEqual(group["optimizer_usage"], [{k: v for k, v in usage[0].items() if k != "event"}])

    def test_template_plan_and_explicit_unavailable_run(self):
        path = ROOT / "experiments/optimizer-template/experiment.toml"
        self.assertTrue(path.is_file(), "team optimizer template must provide a plannable experiment")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(main(["plan", str(path)]), 0)
        self.assertTrue(json.loads(stdout.getvalue())["valid"])
        spec = load_experiment(path)
        registry = Registry()
        preflight(spec, registry)
        template_optimizer = registry.resolve("optimizers", spec["stages"][0]["optimizer"])()
        with self.assertRaises(UnavailableError):
            template_optimizer.optimize(None, [], {})
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(main(["run", str(path), "--output", str(self.output)]), 2)
        self.assertIn("team", stderr.getvalue().lower())
        summary = json.loads(next(self.output.glob("*/summary.json")).read_text())
        self.assertEqual(summary["status"], "error")
        self.assertEqual(summary["error_type"], "UnavailableError")
        self.assertEqual(summary["groups"][0]["selected"], [])
        self.assertEqual(summary["groups"][0]["final_test"], [])


if __name__ == "__main__":
    unittest.main()
