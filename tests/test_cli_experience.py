"""User-facing commands share the existing validated experiment contract."""
import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.cli import main
from agent_optimizer.config import load_experiment
from agent_optimizer.registry import Registry
from agent_optimizer.runner import run_experiment
from support import test_project


class CLIExperienceTests(unittest.TestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)
        self.agent = self.root / "examples/minimal/agents/solo"
        self.data = self.root / "examples/minimal/tasks.json"

    def test_dataset_inventory_lists_builtin_names_without_recommending_one(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main(["datasets", "list", "--project-root", str(self.root)])
        self.assertEqual(result, 0)
        names = {row["name"] for row in json.loads(output.getvalue())}
        self.assertEqual(names, {"cvdp", "verilog-spec", "verilog-completion"})

    def test_noninteractive_init_requires_explicit_dataset_without_creating_files(self):
        error = io.StringIO()
        with patch("sys.stdin.isatty", return_value=False), contextlib.redirect_stderr(error):
            result = main(["init", "--project-root", str(self.root), "--agent", str(self.agent)])
        self.assertEqual(result, 2)
        self.assertIn("dataset", error.getvalue().lower())
        self.assertFalse((self.root / "runs").exists())

    def test_init_generates_loadable_config_for_custom_scored_dataset(self):
        output = io.StringIO()
        args = ["init", "--project-root", str(self.root), "--agent", str(self.agent),
                "--name", "custom-demo", "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--editable", "configs/strategy.json", "--optimizer", "baseline",
                "--argv", "{python}", "{agent_dir}/src/fixture_agent.py", "{task_dir}", "--yes"]
        before = (self.agent / "configs/strategy.json").read_bytes()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(args), 0)
        experiment = Path(json.loads(output.getvalue())["experiment"])
        spec = load_experiment(experiment)
        self.assertEqual(spec["_benchmark_metadata"]["synthetic"], True)
        run, summary = run_experiment(spec, Registry(), self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        self.assertTrue((run / "summary.json").is_file())
        self.assertEqual((self.agent / "configs/strategy.json").read_bytes(), before)

    def test_run_keeps_stdout_json_and_shows_task_progress_on_stderr(self):
        output, progress = io.StringIO(), io.StringIO()
        experiment = self.root / "examples/minimal/experiment.toml"
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(progress):
            code = main(["run", str(experiment), "--output", str(self.root / "runs")])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "completed")
        self.assertIn("fixture-validation", progress.getvalue())
        self.assertIn("evaluation", progress.getvalue())

    def test_tui_rejects_non_terminal_without_creating_files(self):
        errors = io.StringIO()
        with patch("sys.stdin.isatty", return_value=False), contextlib.redirect_stderr(errors):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
        self.assertIn("TTY", errors.getvalue())
        self.assertFalse((self.root / "runs").exists())

    def test_tui_wizard_prepares_explicit_user_choice_and_runs(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal, output = Terminal(), io.StringIO()
        answers = ["wizard-demo", str(self.agent),
                   "{python} {agent_dir}/src/fixture_agent.py {task_dir}",
                   "configs/strategy.json", str(self.data),
                   "examples/minimal/evaluator.py:TextFixtureEvaluator", "1", "y"]
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=answers), \
                contextlib.redirect_stderr(terminal), contextlib.redirect_stdout(output):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "completed")
        self.assertTrue((self.root / "runs/configs/wizard-demo/experiment.toml").is_file())
        self.assertIn("fixture-validation", terminal.getvalue())

    def test_tui_eof_leaves_sources_and_configuration_untouched(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        before = (self.agent / "configs/strategy.json").read_bytes()
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=EOFError), \
                contextlib.redirect_stderr(Terminal()):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
        self.assertFalse((self.root / "runs").exists())
        self.assertEqual((self.agent / "configs/strategy.json").read_bytes(), before)

    def test_init_preserves_pinned_git_agent_url_in_manifest(self):
        url = "https://example.invalid/team/agent.git"
        args = ["init", "--project-root", str(self.root), "--agent", url,
                "--revision", "a" * 40, "--name", "remote-demo",
                "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--editable", "configs/strategy.json", "--optimizer", "baseline",
                "--argv", "{python}", "{agent_dir}/agent.py", "{task_dir}", "--yes"]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(args), 0)
        spec = load_experiment(self.root / "runs/configs/remote-demo/experiment.toml")
        self.assertEqual(spec["_agents"][0].source.url, url)
        self.assertEqual(spec["_agents"][0].source.revision, "a" * 40)

    def test_team_dataset_harness_and_optimizer_extend_wizard_without_core_edits(self):
        team = self.root / "experiments" / "future-team"
        team.mkdir(parents=True)
        (team / "dataset.py").write_text(
            "from pathlib import Path\n"
            "class Provider:\n"
            "    def describe(self):\n"
            "        return {'name': 'future-set', 'task_form': 'text', 'evaluator': 'future-eval'}\n"
            "    def prepare(self, cache, *, offline=False):\n"
            "        return {'benchmark': str(Path(__file__).resolve().parents[2] / "
            "'examples/minimal/tasks.json'), 'evaluator': "
            "'examples/minimal/evaluator.py:TextFixtureEvaluator', "
            "'provenance': {'version': 'fixture'}}\n")
        (team / "harness.py").write_text(
            "from agent_optimizer.harnesses.command import FixtureHarness as Harness\n")
        (team / "optimizer.py").write_text(
            "from agent_optimizer.optimizers.baseline import BaselineOptimizer as Optimizer\n")
        manifest = team / "extensions.toml"
        manifest.write_text(
            'schema_version = 1\n[plugins.datasets]\n'
            'future_set = "experiments/future-team/dataset.py:Provider"\n'
            '[plugins.harnesses]\nfuture_harness = "experiments/future-team/harness.py:Harness"\n'
            '[plugins.optimizers]\nfuture_opt = "experiments/future-team/optimizer.py:Optimizer"\n'
            '[plugins.evaluators]\nfuture_eval = "examples/minimal/evaluator.py:TextFixtureEvaluator"\n')
        inventory = io.StringIO()
        with contextlib.redirect_stdout(inventory):
            self.assertEqual(main(["datasets", "list", "--project-root", str(self.root),
                                   "--extensions", str(manifest)]), 0)
        self.assertIn("future_set", {item["name"] for item in json.loads(inventory.getvalue())})
        args = ["init", "--project-root", str(self.root), "--agent", str(self.agent),
                "--name", "future-demo", "--dataset", "future_set", "--harness", "future_harness",
                "--optimizer", "future_opt", "--extensions", str(manifest),
                "--editable", "configs/strategy.json", "--argv", "{python}", "{task_dir}", "--yes"]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(args), 0)
        spec = load_experiment(self.root / "runs/configs/future-demo/experiment.toml")
        root, summary = run_experiment(spec, Registry(), self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        hashes = json.loads((root / "manifest.json").read_text())["plugin_sha256"]
        self.assertIn("experiments/future-team/dataset.py:Provider", hashes)


if __name__ == "__main__":
    unittest.main()
