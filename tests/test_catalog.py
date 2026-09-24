"""Python registrations are the shared component inventory and run provenance."""
import hashlib
import json
import unittest
from unittest.mock import patch

from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.registry import PROJECT_COMPONENTS, PROJECT_DEPENDENCIES, Registry
from agent_optimizer.runner import preflight, run_experiment
from agent_optimizer.setup_wizard import component_inventory
from support import ROOT, test_project


class ProjectRegistryTests(unittest.TestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)

    def test_bundled_inventory_comes_from_python_registrations(self):
        registry = Registry()
        registry.load_project(ROOT)
        self.assertEqual(set(registry.describe()["datasets"]["implemented"]),
                         {"cvdp", "verilog-spec", "verilog-completion", "sample_text"})
        self.assertIn("verilog_eval", registry.describe()["evaluators"]["implemented"])
        self.assertEqual(registry.resolve("datasets", "verilog-completion")().describe()["task_form"],
                         "code-complete-iccad2023")
        inventory, components, dependencies = component_inventory(ROOT)
        self.assertEqual(inventory.describe()["datasets"], registry.describe()["datasets"])
        self.assertEqual(components["datasets"]["cvdp"],
                         "examples/benchmarks/cvdp.py:Provider")
        self.assertIn("datasets/cvdp", dependencies)

    def test_shipped_synthetic_team_is_registered_and_prepares_without_file_plugins(self):
        registry = Registry()
        registry.load_project(ROOT)
        self.assertIn("sample_text", registry.describe()["datasets"]["implemented"])
        self.assertIn("sample_eval", registry.describe()["evaluators"]["implemented"])
        self.assertIn("sample_command", registry.describe()["harnesses"]["implemented"])
        self.assertIn("sample_baseline", registry.describe()["optimizers"]["implemented"])
        provider = registry.resolve("datasets", "sample_text")()
        self.assertEqual(provider.describe()["evaluator"], "sample_eval")
        self.assertEqual(provider.prepare(self.root / "external/datasets/sample_text", offline=True)["evaluator"],
                         "sample_eval")

    def test_missing_file_and_duplicate_id_fail_before_importing_team_code(self):
        marker = self.root / "was-imported"
        team = self.root / "experiments/team"
        team.mkdir(parents=True)
        (team / "provider.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
        with patch.dict(PROJECT_COMPONENTS["datasets"],
                        {"team": "experiments/team/provider.py:Provider",
                         "missing": "experiments/team/missing.py:Provider"}):
            with self.assertRaises(ConfigurationError):
                Registry().load_project(self.root)
        self.assertFalse(marker.exists())
        with patch.dict(PROJECT_COMPONENTS["optimizers"],
                        {"baseline": "experiments/team/provider.py:Provider"}):
            with self.assertRaisesRegex(ConfigurationError, "Duplicate"):
                Registry().load_project(self.root)
        self.assertFalse(marker.exists())

    def test_explicit_plugin_cannot_shadow_a_project_registration(self):
        spec = load_experiment(self.root / "examples/minimal/experiment.toml")
        spec["plugins"]["evaluators"]["cvdp"] = "examples/minimal/evaluator.py:TextFixtureEvaluator"
        with self.assertRaisesRegex(ConfigurationError, "Duplicate plugin registration: evaluators/cvdp"):
            preflight(spec, Registry())

    def test_unknown_benchmark_provider_is_not_silently_ignored(self):
        spec = load_experiment(self.root / "examples/minimal/experiment.toml")
        spec["_benchmark_metadata"]["dataset_provider"] = "deleted-team"
        with self.assertRaisesRegex(ConfigurationError, "Unregistered dataset provider"):
            preflight(spec, Registry())

    def test_selected_bundled_evaluator_and_provider_include_declared_helpers(self):
        spec = load_experiment(self.root / "examples/minimal/experiment.toml")
        spec["_benchmark_metadata"]["dataset_provider"] = "verilog-spec"
        spec["evaluator"] = "verilog_eval"
        registry = Registry()
        registry.load_project(self.root)
        files = registry.selected_files(self.root, spec)
        self.assertIn("examples/benchmarks/verilog_eval.py:Provider", files)
        self.assertIn("examples/benchmarks/verilog_evaluator.py:VerilogEvaluator", files)
        self.assertIn("examples/benchmarks/Dockerfile.iverilog12", files)
        self.assertIn("examples/benchmarks/verilog_eval.py", files)
        self.assertNotIn("examples/benchmarks/cvdp.py:Provider", files)

    def test_selected_central_files_and_helpers_are_fingerprinted_without_registration_in_plan(self):
        team = self.root / "experiments/team"
        team.mkdir(parents=True)
        provider = team / "provider.py"
        provider.write_text("class Provider:\n    pass\n")
        helper = team / "helper.py"
        helper.write_text("VALUE = 1\n")
        harness = team / "harness.py"
        harness.write_text("from agent_optimizer.harnesses.command import FixtureHarness as Harness\n")
        optimizer = team / "optimizer.py"
        optimizer.write_text("from agent_optimizer.optimizers.baseline import BaselineOptimizer as Optimizer\n")
        evaluator = team / "evaluator.py"
        evaluator.write_text("from agent_optimizer.optimizers.baseline import BaselineOptimizer as Evaluator\n")
        additions = {"datasets": {"team": "experiments/team/provider.py:Provider"},
                     "harnesses": {"team": "experiments/team/harness.py:Harness"},
                     "optimizers": {"team": "experiments/team/optimizer.py:Optimizer"},
                     "evaluators": {"team": "experiments/team/evaluator.py:Evaluator"}}
        with patch.dict(PROJECT_COMPONENTS, {kind: {**PROJECT_COMPONENTS[kind], **entries}
                                            for kind, entries in additions.items()}), \
                patch.dict(PROJECT_DEPENDENCIES, {"datasets/team": ["experiments/team/helper.py"]}):
            spec = load_experiment(self.root / "examples/minimal/experiment.toml")
            spec["_agents"] = spec["_agents"][:1]
            spec.update(stages=[{"id": "team", "optimizer": "team"}], final_stages=["team"],
                        final_test=False, evaluator="text_fixture")
            spec["_profiles"][0]["adapter"] = "team"
            spec["_benchmark_metadata"]["dataset_provider"] = "team"
            registry = Registry()
            preflight(spec, registry)
            selected = registry.selected_files(self.root, spec)
            for reference in ("experiments/team/provider.py:Provider", "experiments/team/helper.py",
                              "experiments/team/harness.py:Harness", "experiments/team/optimizer.py:Optimizer",
                              "examples/minimal/evaluator.py:TextFixtureEvaluator"):
                self.assertIn(reference, selected)
            self.assertNotIn("experiments/team/evaluator.py:Evaluator", selected)
            before, _ = run_experiment(spec, Registry(), self.root / "runs")
            first = json.loads((before / "manifest.json").read_text())
            helper.write_text("VALUE = 2\n")
            after, _ = run_experiment(spec, Registry(), self.root / "runs")
            second = json.loads((after / "manifest.json").read_text())
            self.assertEqual(first["plugin_sha256"]["experiments/team/helper.py"],
                             hashlib.sha256(b"VALUE = 1\n").hexdigest())
            self.assertEqual(second["plugin_sha256"]["experiments/team/helper.py"],
                             hashlib.sha256(b"VALUE = 2\n").hexdigest())
            self.assertNotIn("extensions_sha256", second)
            self.assertNotIn("extensions", second["experiment"])


if __name__ == "__main__":
    unittest.main()
