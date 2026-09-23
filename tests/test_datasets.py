"""Dataset preparation must preserve held-out and private evaluator boundaries."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.config import validate_runtime
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.datasets import CustomDataset, acquire_pinned_git
from agent_optimizer.contracts import UnavailableError
from agent_optimizer.contracts import Task
from examples.benchmarks.verilog_eval import REVISION, Provider, import_verilog_eval, prepare_runtime, split_families
from examples.benchmarks.verilog_evaluator import VerilogEvaluator
from examples.benchmarks.cvdp import import_cvdp
from test_dev_environment import official_row


class DatasetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for mode in ("dataset_spec-to-rtl", "dataset_code-complete-iccad2023"):
            directory = self.root / mode
            directory.mkdir()
            for number in range(1, 5):
                stem = f"Prob{number:03d}_task"
                (directory / f"{stem}_prompt.txt").write_text(f"Implement {stem}\n")
                (directory / f"{stem}_test.sv").write_text("private_testbench_sentinel")
                (directory / f"{stem}_ref.sv").write_text("private_reference_sentinel")
                if mode.endswith("iccad2023"):
                    (directory / f"{stem}_ifc.txt").write_text("module TopModule();\n")

    def test_importer_keeps_related_tasks_in_same_split_without_private_bytes(self):
        specification = import_verilog_eval(self.root, "spec-to-rtl")
        completion = import_verilog_eval(self.root, "code-complete-iccad2023")
        self.assertEqual(len(specification["tasks"]), 4)
        self.assertEqual({t["family"]: t["split"] for t in specification["tasks"]},
                         {t["family"]: t["split"] for t in completion["tasks"]})
        self.assertEqual(set(t["split"] for t in specification["tasks"]),
                         {"train", "validation", "test"})
        for task in [*specification["tasks"], *completion["tasks"]]:
            public = json.dumps({"prompt": task["prompt"], "files": task["files"]})
            self.assertNotIn("private_testbench_sentinel", public)
            self.assertNotIn("private_reference_sentinel", public)
            self.assertNotIn("_test.sv", public)
            self.assertNotIn("_ref.sv", public)

    def test_too_few_families_cannot_be_split_into_three_sets(self):
        with self.assertRaisesRegex(ConfigurationError, "families"):
            split_families(["one", "two"])

    def test_pinned_git_download_is_atomic_reused_offline_and_rejects_dirty_tree(self):
        origin = self.root / "origin"
        origin.mkdir()
        subprocess.run(["git", "init", "-q", str(origin)], check=True)
        (origin / "README.md").write_text("pinned version\n")
        subprocess.run(["git", "-C", str(origin), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(origin), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
        revision = subprocess.check_output(["git", "-C", str(origin), "rev-parse", "HEAD"], text=True).strip()
        target = self.root / "cache" / "checkout"
        with self.assertRaises(UnavailableError):
            acquire_pinned_git(target, str(origin), revision, offline=True)
        self.assertFalse(target.exists())
        self.assertEqual(acquire_pinned_git(target, str(origin), revision), target)
        self.assertEqual(acquire_pinned_git(target, str(origin), revision, offline=True), target)
        (target / "README.md").write_text("modified")
        with self.assertRaises(ConfigurationError):
            acquire_pinned_git(target, str(origin), revision, offline=True)

    def test_provider_prepares_public_manifest_from_a_pinned_local_source(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
        revision = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()
        provider = Provider(url=str(self.root), revision=revision)
        cache = self.root / "prepared"
        with self.assertRaises(UnavailableError):
            provider.prepare(cache, offline=True)
        with patch("examples.benchmarks.verilog_eval.prepare_runtime",
                   return_value={"runtime": {"kind": "docker", "image": "verified-v12"},
                                 "image_id": "sha256:verified"}):
            prepared = provider.prepare(cache)
        document = json.loads(Path(prepared["benchmark"]).read_text())
        self.assertEqual(document["source_revision"], revision)
        self.assertEqual(prepared["evaluator"], "examples/benchmarks/verilog_evaluator.py:VerilogEvaluator")
        self.assertEqual(len(document["tasks"]), 4)
        self.assertEqual(prepared["evaluation_runtime"]["image"], "verified-v12")
        with patch("examples.benchmarks.verilog_eval.prepare_runtime",
                   return_value={"runtime": {"kind": "docker", "image": "verified-v12"},
                                 "image_id": "sha256:verified"}):
            self.assertEqual(provider.prepare(cache, offline=True)["benchmark"], prepared["benchmark"])
        validate_runtime(prepared["evaluation_runtime"])
        self.assertEqual(prepared["provenance"]["image_id"], "sha256:verified")

    def test_missing_v12_image_blocks_offline_prepare(self):
        with patch("examples.benchmarks.verilog_eval.subprocess.run") as run:
            run.return_value.returncode = 1
            with self.assertRaisesRegex(UnavailableError, "offline"):
                prepare_runtime(offline=True)

    def test_verilog_evaluator_rejects_unverified_simulator_version(self):
        tool = self.root / "iverilog"
        tool.write_text("#!/usr/bin/env python3\nprint('Icarus Verilog version 13.0')\n")
        tool.chmod(0o755)
        task = Task(id="Prob001_task", split="validation", family="Prob001_task",
                    prompt="Implement", files={"solution.sv": ""},
                    evaluation={"source_dir": str(self.root), "problem_id": "Prob001_task",
                                "mode": "spec-to-rtl"})
        previous = os.environ.get("VERILOG_EVAL_IVERILOG")
        os.environ["VERILOG_EVAL_IVERILOG"] = str(tool)
        self.addCleanup(lambda: os.environ.pop("VERILOG_EVAL_IVERILOG", None)
                        if previous is None else os.environ.__setitem__("VERILOG_EVAL_IVERILOG", previous))
        with self.assertRaisesRegex(UnavailableError, "v12"):
            VerilogEvaluator({"kind": "local"}).validate_benchmark([task], {"source_revision": REVISION})

    def test_verilog_evaluator_refuses_a_mismatched_source_revision(self):
        task = Task(id="Prob001_task", split="validation", family="Prob001_task",
                    prompt="Implement", files={"solution.sv": ""},
                    evaluation={"source_dir": str(self.root), "problem_id": "Prob001_task",
                                "mode": "spec-to-rtl"})
        with self.assertRaisesRegex(ConfigurationError, "revision"):
            VerilogEvaluator({"kind": "docker", "image": "local-test"}).validate_benchmark(
                [task], {"source_revision": "unreviewed"})

    def test_cvdp_importer_uses_reviewed_rows_and_family_disjoint_splits(self):
        rows = []
        for index in range(4):
            row = official_row()
            row["id"] = f"cvdp_copilot_demo_{index:04d}"
            rows.append(row)
        data = self.root / "no_commercial.jsonl"
        data.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        manifest = import_cvdp(data)
        self.assertEqual({task["split"] for task in manifest["tasks"]},
                         {"train", "validation", "test"})
        self.assertEqual(len(manifest["tasks"]), 4)
        self.assertNotIn("PRIVATE_CHECKER", json.dumps([task["files"] for task in manifest["tasks"]]))

    def test_custom_dataset_requires_scorer_and_records_a_stable_family_split(self):
        source = self.root / "custom.json"
        source.write_text(json.dumps({"schema_version": 1, "tasks": [
            {"id": f"task-{i}", "family": f"family-{i}", "prompt": "Answer",
             "files": {"input.txt": str(i)}, "evaluation": {"expected": str(i)}}
            for i in range(4)]}))
        with self.assertRaisesRegex(ConfigurationError, "evaluator"):
            CustomDataset(source, evaluator="").prepare(self.root / "output")
        prepared = CustomDataset(source, evaluator="team_eval").prepare(self.root / "output")
        result = json.loads(Path(prepared["benchmark"]).read_text())
        self.assertEqual({task["split"] for task in result["tasks"]},
                         {"train", "validation", "test"})
        self.assertEqual(prepared["evaluator"], "team_eval")


if __name__ == "__main__":
    unittest.main()
