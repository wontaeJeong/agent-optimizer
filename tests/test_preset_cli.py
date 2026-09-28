"""CLI 선택이 TUI의 등록 프리셋·실행 계약을 그대로 사용하는지 검사한다."""
import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.cli import _launch_existing, main
from agent_optimizer.config import load_experiment
from agent_optimizer.integrations import prepare_experiment
from agent_optimizer.preset_tui import verify_ace_selection, write_ace_selection
from agent_optimizer.readiness import collect_plan
from agent_optimizer.registry import Registry
from support import ROOT, test_project


class PresetCLITests(unittest.TestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)
        tasks = json.loads((ROOT / "examples/minimal/tasks.json").read_text())
        tasks["tasks"] = tasks["tasks"][:2]
        path = self.root / "datasets/ace-demo/tasks.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(tasks))

    def call(self, *argv):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            status = main([*argv, "--project-root", str(self.root)])
        return status, output.getvalue(), error.getvalue()

    def init_ace(self, optimizer, name, *options):
        with patch("agent_optimizer.preset_tui.prepare_ace_selection"):
            result = self.call("init", "--name", name, "--agent-preset", "ace-rtl",
                               "--harness-profile", "ace-opencode", "--optimizer", optimizer,
                               "--dataset", "cvdp", "--yes", *options)
        self.assertEqual(result[0], 0, result[2])
        return Path(json.loads(result[1])["experiment"]), result

    def test_catalog_read_only_and_installed_choices_are_not_reserved(self):
        before = {file.relative_to(self.root) for file in self.root.rglob("*")}
        for kind, identifier in (("agent", "ace-rtl"), ("harness", "ace-opencode"),
                                 ("optimizer", "gepa"), ("optimizer", "meta_harness"),
                                 ("dataset", "cvdp")):
            status, value, error = self.call("catalog", "list", "--kind", kind, "--json")
            self.assertEqual(status, 0, error)
            self.assertIn(identifier, {row["id"] for row in json.loads(value)})
            self.assertNotIn("codex", {row["id"] for row in json.loads(value)})
            status, value, error = self.call("catalog", "show", kind, identifier, "--json")
            self.assertEqual(status, 0, error)
            self.assertTrue(json.loads(value)["reason"])
        self.assertEqual({file.relative_to(self.root) for file in self.root.rglob("*")}, before)
        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}):
            status, value, error = self.call("catalog", "show", "optimizer", "gepa")
        self.assertEqual(status, 0, error)
        self.assertIn("training feedback", value)

    def test_catalog_includes_declared_profile_without_changing_adapter_list(self):
        profile = self.root / "examples/ace-rtl/harness-team.toml"
        profile.write_text('id = "ace-team"\nadapter = "command"\nallow_local = true\n'
                           '[runtime]\nkind = "local"\n')
        status, value, error = self.call("catalog", "show", "harness", "ace-team", "--json")
        self.assertEqual(status, 0, error)
        details = json.loads(value)
        self.assertEqual(details["adapter"], "command")
        self.assertIsInstance(details["requirements"], list)
        self.assertEqual(details["runtime"]["kind"], "local")

    def test_catalog_reads_new_agent_manifest_from_examples(self):
        status, value, error = self.call("catalog", "list", "--kind", "agent", "--json")
        self.assertEqual(status, 0, error)
        agents = {row["id"]: row for row in json.loads(value)}
        self.assertIn("model-rtl-agent", agents)
        self.assertIn("model_rtl_command", agents["model-rtl-agent"]["supported_harnesses"])
        status, value, error = self.call("catalog", "show", "harness", "model-rtl-command", "--json")
        self.assertEqual(status, 0, error)
        self.assertEqual(json.loads(value)["adapter"], "model_rtl_command")

    def test_cli_gepa_and_meta_share_tui_stage_profile_and_active_seed(self):
        for optimizer in ("gepa", "meta_harness"):
            with self.subTest(optimizer=optimizer):
                path, (_, stdout, error) = self.init_ace(optimizer, "cli-" + optimizer)
                spec = load_experiment(path)
                tui = load_experiment(write_ace_selection(self.root, optimizer))
                verify_ace_selection(spec)
                self.assertEqual(path.parent.name, "cli-" + optimizer)
                self.assertEqual(json.loads(stdout)["stages"], [optimizer])
                self.assertEqual(spec["stages"], tui["stages"])
                self.assertEqual(spec["budget"], tui["budget"])
                self.assertEqual(spec["_profiles"], tui["_profiles"])
                self.assertEqual(spec["evaluator"], "cvdp")
                self.assertIn("agent-opt prepare", error)
                if optimizer == "meta_harness":
                    scaffold = spec["stages"][0]["config"]["file"]
                    self.assertIn(scaffold, spec["_agents"][0].editable)
                    self.assertIn("runpy.run_path", " ".join(spec["_agents"][0].build))
                    self.assertTrue((self.root / spec["candidate_seed_files"][scaffold]).is_file())
                else:
                    self.assertEqual(spec["stages"][0]["config"]["file"],
                                     "skills/ace-rtl/references/role-guidance.md")

    def test_explicit_gepa_iteration_budget_uses_shared_validator(self):
        path, _ = self.init_ace("gepa", "short-search", "--optimizer-config",
                                '{"gepa":{"iterations":2,"batch_size":1}}')
        spec = load_experiment(path)
        verify_ace_selection(spec)
        self.assertEqual(spec["stages"][0]["config"]["iterations"], 2)
        self.assertEqual(spec["stages"][0]["max_trials"], 6)
        self.assertEqual(spec["budget"]["max_trials"], 7)
        self.assertEqual({row["id"]: row["status"] for row in collect_plan(path, Registry())["checks"]}
                         ["integration.assets"], "error")

    def test_invalid_inputs_fail_before_network_or_configuration_write(self):
        for flags in (("--agent", "./agent"), ("--harness", "command"),
                      ("--harness-profile", "codex"), ("--optimizer-config", '{"gepa":{"merge":true}}'),
                      ("--optimizer-config", '{"gepa":{"iterations":0}}'),
                      ("--metric", "unsupported"), ("--evaluator", "custom"),
                      ("--max-trials", "1"), ("--max-tasks", "1")):
            with self.subTest(flags=flags), patch(
                    "agent_optimizer.preset_tui.prepare_ace_selection",
                    side_effect=AssertionError("network before validation")):
                status, value, error = self.call(
                    "init", "--name", "invalid-ace", "--agent-preset", "ace-rtl",
                    "--harness-profile", "ace-opencode", "--optimizer", "gepa",
                    "--dataset", "cvdp", "--yes", *flags)
            self.assertEqual(status, 2, error)
            self.assertEqual(value, "")
            self.assertFalse((self.root / "runs/configs/invalid-ace").exists())

    def test_symlinked_config_root_is_rejected_before_ace_preparation(self):
        (self.root / "runs").symlink_to(self.root / "examples", target_is_directory=True)
        with patch("agent_optimizer.preset_tui.prepare_ace_selection",
                   side_effect=AssertionError("prepared before validating config root")):
            status, output, error = self.call(
                "init", "--name", "unsafe", "--agent-preset", "ace-rtl",
                "--harness-profile", "ace-opencode", "--optimizer", "gepa",
                "--dataset", "cvdp", "--yes")
        self.assertEqual(status, 2, error)
        self.assertEqual(output, "")

    def test_legacy_pointer_and_new_preset_flags_are_exclusive(self):
        workspace = self.root / "pending-legacy"
        status, output, error = self.call(
            "init", "--profile", "ace-rtl", "--workspace", str(workspace),
            "--agent-preset", "ace-rtl", "--harness-profile", "ace-opencode")
        self.assertEqual(status, 2, error)
        self.assertEqual(output, "")
        self.assertFalse(workspace.exists())

    def test_prepare_selected_config_checks_the_pin_before_work(self):
        path, _ = self.init_ace("gepa", "selected-prepare")
        with patch("agent_optimizer.preset_tui.prepare_ace_selection") as prepare:
            result = prepare_experiment(path, offline=True)
        self.assertEqual(result["experiment"], path.resolve())
        prepare.assert_called_once_with(self.root.resolve(), offline=True)
        plan = path.read_text()
        path.write_text(plan.replace('optimizer = "gepa"', 'optimizer = "meta_harness"'))
        with patch("agent_optimizer.preset_tui.prepare_ace_selection",
                   side_effect=AssertionError("prepared invalid config")):
            with self.assertRaisesRegex(Exception, "선택형 설정"):
                prepare_experiment(path)

    def test_fixture_preset_runs_without_a_model_or_docker(self):
        status, value, error = self.call("init", "--name", "cli-fixture",
                                         "--agent-preset", "rtl-solo", "--harness-profile", "fixture",
                                         "--optimizer", "baseline", "--dataset", "sample_text", "--yes")
        self.assertEqual(status, 0, error)
        path = Path(json.loads(value)["experiment"])
        self.assertEqual(load_experiment(path)["_profiles"][0]["adapter"], "fixture")
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["run", str(path)]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "completed")
        self.assertTrue((Path(result["run_dir"]) / "report.html").is_file())

    def test_existing_custom_init_does_not_replace_explicit_zero_timeout_with_default(self):
        status, output, error = self.call(
            "init", "--name", "zero-timeout", "--agent", "examples/minimal/agents/solo",
            "--command", "{python} {agent_dir}/src/fixture_agent.py {task_dir}",
            "--editable", "configs/strategy.json", "--dataset", "examples/minimal/tasks.json",
            "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
            "--optimizer", "baseline", "--trial-timeout-seconds", "0", "--yes")
        self.assertEqual(status, 2, error)
        self.assertEqual(output, "")
        self.assertFalse((self.root / "runs/configs/zero-timeout").exists())

    def test_tampered_selected_profile_is_refused_before_runner(self):
        path, _ = self.init_ace("gepa", "tampered-profile")
        # The generated selection refers to the source profile, not a local copy.
        original = self.root / "examples/ace-rtl/harness.toml"
        before = original.read_text()
        try:
            original.write_text(before.replace('kind = "docker"', 'kind = "local"')
                                .replace('model_env = "AGENT_OPT_MODEL"',
                                         'model_env = "AGENT_OPT_MODEL"\nallow_local = true'))
            spec = load_experiment(path)
            with self.assertRaisesRegex(Exception, "선택형 설정"):
                _launch_existing(spec, Registry())
        finally:
            original.write_text(before)
