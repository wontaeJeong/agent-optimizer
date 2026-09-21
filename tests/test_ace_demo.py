import copy
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
