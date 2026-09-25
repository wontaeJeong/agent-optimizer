import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, RunRequest
from support import ROOT, module

demo = module("ace_demo_selection", ROOT / "examples/ace-rtl/environment/demo.py")
adapter = module("ace_demo_adapter", ROOT / "examples/ace-rtl/adapter.py")


class AceDemoTests(unittest.TestCase):
    def manifest(self):
        return {"schema_version": 1, "tasks": [
            {"id": "cvdp_copilot_8x3_priority_encoder_0001", "family": "priority", "split": "validation", "files": {"rtl/a.v": ""}},
            {"id": "cvdp_copilot_16qam_mapper_0001", "family": "qam", "split": "validation", "files": {"rtl/b.v": ""}},
        ]}

    def test_selection_is_disjoint_and_does_not_mutate_imported_manifest(self):
        manifest = self.manifest()
        before = copy.deepcopy(manifest)
        result = demo.select_tasks(manifest)
        self.assertEqual([t["split"] for t in result["tasks"]], ["train", "validation"])
        self.assertEqual(len({t["family"] for t in result["tasks"]}), 2)
        self.assertEqual(manifest, before)
        self.assertTrue(all(v == "" for t in result["tasks"] for v in t["files"].values()))

    def test_missing_task_or_same_family_is_not_silently_replaced(self):
        manifest = self.manifest()
        manifest["tasks"][1]["family"] = "priority"
        with self.assertRaises(ConfigurationError):
            demo.select_tasks(manifest)
        manifest["tasks"].pop()
        with self.assertRaises(ConfigurationError):
            demo.select_tasks(manifest)

    def test_guidance_change_reaches_harness_prompt_directly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "skills/ace-rtl/references/role-guidance.md"
            path.parent.mkdir(parents=True)
            path.write_text("candidate-specific-guidance")
            request = RunRequest(root, root, root / "task", "public-prompt", 0, 30, {}, root / "logs")
            result = adapter.with_ace_guidance(request)
            self.assertIn("candidate-specific-guidance", result.prompt)
            self.assertIn("public-prompt", result.prompt)
            self.assertEqual(request.prompt, "public-prompt")

    def test_lifecycle_prepares_fixed_demo_from_relocated_example(self):
        with tempfile.TemporaryDirectory(prefix="ace-profile-") as directory:
            root = Path(directory)
            example = root / "examples/ace-rtl"
            (example / "environment").mkdir(parents=True)
            shutil.copyfile(ROOT / "examples/ace-rtl/environment/demo.py",
                            example / "environment/demo.py")
            (example / "environment/setup.py").write_text(
                'from pathlib import Path\n'
                'def prepare_environment(*, offline=False, platform=None):\n'
                '    assert offline and platform == "linux/arm64"\n'
                '    return Path("public.jsonl"), {"platform": platform}\n')
            (example / "prepare.py").write_text(
                'def prepare_dataset(dataset, output, lock):\n'
                '    assert output.name == "all-tasks.json" and lock["platform"] == "linux/arm64"\n'
                '    return {"schema_version": 1, "tasks": [\n'
                '      {"id": "cvdp_copilot_8x3_priority_encoder_0001", "family": "priority", '
                '"split": "validation", "files": {"rtl/a.v": ""}},\n'
                '      {"id": "cvdp_copilot_16qam_mapper_0001", "family": "qam", '
                '"split": "validation", "files": {"rtl/b.v": ""}}]}\n')
            shutil.copyfile(ROOT / "examples/ace-rtl/environment/lifecycle.py",
                            example / "environment/lifecycle.py")
            lifecycle = module("isolated_ace_lifecycle_prepare", example / "environment/lifecycle.py")
            target = lifecycle.prepare(root, offline=True, platform="linux/arm64")
            self.assertEqual(target, root.resolve() / "datasets/ace-demo/tasks.json")
            self.assertEqual([row["split"] for row in json.loads(target.read_text())["tasks"]],
                             ["train", "validation"])
