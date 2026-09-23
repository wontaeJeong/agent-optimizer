"""Team extensions must be discoverable without changing core registry code."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from agent_optimizer.catalog import load_extensions
from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.registry import Registry
from agent_optimizer.runner import run_experiment
from support import test_project


class ExtensionCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.team = self.root / "experiments" / "sample"
        self.team.mkdir(parents=True)
        (self.team / "dataset.py").write_text(
            "class Provider:\n"
            "    def describe(self):\n"
            "        return {'name': 'sample', 'task_form': 'text', 'evaluator': 'sample_eval'}\n"
            "    def prepare(self, cache, *, offline=False):\n"
            "        return {'benchmark': str(cache / 'tasks.json'), 'evaluator': 'sample_eval', "
            "'provenance': {'version': 'fixture'}}\n",
            encoding="utf-8",
        )

    def test_team_dataset_is_discoverable_and_invokable(self):
        manifest = self.team / "extensions.toml"
        manifest.write_text(
            'schema_version = 1\n[plugins.datasets]\nsample = "experiments/sample/dataset.py:Provider"\n',
            encoding="utf-8",
        )
        inventory = load_extensions(manifest, self.root)
        registry = Registry()
        registry.load_plugins(self.root, inventory["plugins"])
        self.assertEqual(registry.resolve("datasets", "sample")().describe(),
                         {"name": "sample", "task_form": "text", "evaluator": "sample_eval"})
        self.assertIn("sample", registry.describe()["datasets"]["implemented"])

    def test_missing_plugin_file_fails_before_loading_another_plugin(self):
        marker = self.root / "was-imported"
        (self.team / "dataset.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
        manifest = self.team / "extensions.toml"
        manifest.write_text(
            'schema_version = 1\n[plugins.datasets]\n'
            'sample = "experiments/sample/dataset.py:Provider"\n'
            'missing = "experiments/sample/not-there.py:Provider"\n', encoding="utf-8")
        with self.assertRaises(ConfigurationError):
            load_extensions(manifest, self.root)
        self.assertFalse(marker.exists())

    def test_bad_manifest_version_is_rejected(self):
        manifest = self.team / "extensions.toml"
        manifest.write_text('schema_version = 0\n[plugins.datasets]\n', encoding="utf-8")
        with self.assertRaisesRegex(ConfigurationError, "schema_version"):
            load_extensions(manifest, self.root)

    def test_builtin_name_collision_rejected_before_team_code_runs(self):
        marker = self.root / "was-imported"
        (self.team / "dataset.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
        manifest = self.team / "extensions.toml"
        manifest.write_text(
            'schema_version = 1\n[plugins.datasets]\n'
            'sample = "experiments/sample/dataset.py:Provider"\n'
            '[plugins.optimizers]\nbaseline = "experiments/sample/dataset.py:Provider"\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ConfigurationError, "Duplicate"):
            Registry().load_plugins(self.root, load_extensions(manifest, self.root)["plugins"])
        self.assertFalse(marker.exists())

    def test_experiment_records_team_extension_manifest_and_provider_hash(self):
        temporary, root = test_project()
        self.addCleanup(temporary.cleanup)
        team = root / "experiments" / "sample"
        team.mkdir(parents=True)
        provider = team / "provider.py"
        provider.write_text("class Provider:\n    def describe(self):\n        return {'name': 'sample'}\n")
        extension = team / "extensions.toml"
        extension.write_text('schema_version = 1\n[plugins.datasets]\n'
                             'sample = "experiments/sample/provider.py:Provider"\n')
        experiment = root / "examples/minimal/experiment.toml"
        experiment.write_text(experiment.read_text().replace('schema_version = 1\n',
                                                              'schema_version = 1\nextensions = "experiments/sample/extensions.toml"\n', 1))
        spec = load_experiment(experiment)
        spec["_agents"] = spec["_agents"][:1]
        spec.update(stages=[], final_stages=["baseline"], final_test=False)
        run, summary = run_experiment(spec, Registry(), root / "runs")
        self.assertEqual(summary["status"], "completed")
        manifest = json.loads((run / "manifest.json").read_text())
        self.assertEqual(manifest["extensions_sha256"], hashlib.sha256(extension.read_bytes()).hexdigest())
        self.assertEqual(manifest["plugin_sha256"]["experiments/sample/provider.py:Provider"],
                         hashlib.sha256(provider.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
