"""API-free checks for the explicitly selected research CVDP example."""
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.cli import main as agent_opt
from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError
from support import ROOT, module, test_project


EXAMPLE = ROOT / "examples/model-rtl-agent/prepare.py"


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

    def test_public_single_rtl_targets_keep_split_family_and_locked_provenance(self):
        original = self.benchmark.read_bytes()
        result = self.prepare()
        self.assertEqual(result, self.config_root / "experiment.toml")
        subset = json.loads(self.subset.read_text(encoding="utf-8"))
        generated = json.loads((self.config_root / "tasks.json").read_text(encoding="utf-8"))
        for document in (subset, generated):
            self.assertEqual([(row["id"], row["split"], row["family"])
                              for row in document["tasks"]],
                             [("a-train", "train", "second"),
                              ("z-train", "train", "first"),
                              ("c-validation", "validation", "third")])
            self.assertEqual(document["id"], "cvdp-reviewed-no-commercial")
            self.assertEqual(document["data_sha256"], "public-sha256")
            self.assertEqual(document["source_revision"], "fixed-revision")
            self.assertNotIn("private-evaluation-fixture", json.dumps(document))
            self.assertNotIn("row", document["tasks"][0]["files"])
            self.assertEqual(document["tasks"][0]["evaluation"]["row"]["id"], "a-train")
        self.assertEqual(generated["dataset_provenance"], self.provider["provenance"])
        self.assertEqual(generated["dataset_provider"], "cvdp")
        self.assertEqual(self.benchmark.read_bytes(), original)
        self.assertEqual(self.private.read_text(encoding="utf-8"), "private-evaluation-fixture")

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
