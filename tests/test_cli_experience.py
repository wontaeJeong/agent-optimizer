"""User-facing commands share the existing validated experiment contract."""
import contextlib
import io
import json
import multiprocessing
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.cli import main
from agent_optimizer.config import load_experiment
from agent_optimizer.registry import PROJECT_COMPONENTS, PROJECT_DEPENDENCIES, Registry
from agent_optimizer.readiness import collect_plan
from agent_optimizer.runner import run_experiment
from agent_optimizer.session import SessionInterrupted, _project_event, run_session
from agent_optimizer.setup_wizard import _bounded_tasks, wizard_arguments, write_experiment
from agent_optimizer.terminal_report import SessionProgress
from support import ROOT, test_project


class CLIExperienceTests(unittest.TestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)
        self.agent = self.root / "examples/minimal/agents/solo"
        self.data = self.root / "examples/minimal/tasks.json"

    def test_top_level_help_points_to_setup_and_explains_run_and_report(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["--help"]), 0)
        text = re.sub(r"\x1b\[[0-9;]*m", "", output.getvalue())
        self.assertIn("Usage:", text)
        self.assertIn("Options", text)
        self.assertNotIn("--install-completion", text)
        self.assertIn("make setup-core", text)
        self.assertIn("기존 실험", text)
        self.assertIn("준비된 실험 실행", text)
        self.assertIn("실행 요약 확인 또는 HTML 재생성", text)
        self.assertFalse((self.root / "runs").exists())

    def test_command_help_explains_dataset_choice_and_read_only_doctor(self):
        for argv, expected in (
                (["init", "--help"], ("--agent", "데이터셋", "--optimizer", "--yes")),
                (["datasets", "prepare", "--help"], ("등록된 데이터셋 ID 또는 로컬 tasks.json",
                                                          "--evaluator", "--offline")),
                (["doctor", "--help"], ("읽기 전용", "--model", "--plan 필요"))):
            output = io.StringIO()
            with self.subTest(argv=argv), contextlib.redirect_stdout(output):
                self.assertEqual(main(argv), 0)
            text = re.sub(r"\x1b\[[0-9;]*m", "", output.getvalue())
            self.assertIn("Usage:", text)
            self.assertIn("Options", text)
            for phrase in expected:
                self.assertIn(phrase, text)
        self.assertFalse((self.root / "runs").exists())

    def test_doctor_human_status_changes_language_but_json_does_not(self):
        rendered, machine = {}, {}
        for language in ("ko", "en"):
            with patch.dict(os.environ, {"AGENT_OPT_LANG": language}):
                with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["doctor", "--dataset", "sample_text", "--project-root", str(self.root)]), 0)
                rendered[language] = output.getvalue()
                with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["doctor", "--dataset", "sample_text", "--project-root", str(self.root), "--json"]), 0)
                machine[language] = json.loads(output.getvalue())
        self.assertIn("준비 상태:", rendered["ko"])
        self.assertIn("readiness:", rendered["en"])
        self.assertEqual(machine["ko"], machine["en"])

    def test_plan_budget_diagnostic_localizes_number_without_changing_json(self):
        plan = self.root / "examples/minimal/experiment.toml"
        plan.write_text(plan.read_text().replace("max_trials = 40", "max_trials = 1"))
        with patch.dict(os.environ, {"AGENT_OPT_LANG": "ko"}):
            human_output = io.StringIO()
            with contextlib.redirect_stdout(human_output), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["doctor", "--plan", str(plan)]), 2)
            machine_output = io.StringIO()
            with contextlib.redirect_stdout(machine_output), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["doctor", "--plan", str(plan), "--json"]), 2)
        self.assertIn("평가 예산은 최소", human_output.getvalue())
        budget = next(row for row in json.loads(machine_output.getvalue())["checks"]
                      if row["id"] == "budget.trials")
        self.assertIn("Trial budget must reserve at least", budget["message"])

    def test_datasets_list_rejects_ignored_positional_filters(self):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            self.assertEqual(main(["datasets", "list", "missing-dataset"]), 2)
        self.assertIn("unexpected extra argument", error.getvalue())
        self.assertEqual(output.getvalue(), "")

    def test_doctor_keeps_legacy_binary_inventory_without_options(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["doctor"]), 0)
        self.assertEqual(set(json.loads(output.getvalue())), {"python3", "git", "docker", "opencode"})

    def test_plan_doctor_api_free_minimal_needs_no_model_credentials(self):
        output, progress = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"AGENT_OPT_MODEL_API_KEY": "", "AGENT_OPT_MODEL_BASE_URL": ""}), \
                patch("agent_optimizer.models.probe_model", side_effect=AssertionError("model call")), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(progress):
            code = main(["doctor", "--plan", str(self.root / "examples/minimal/experiment.toml"), "--json"])
        report = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(progress.getvalue(), "")
        self.assertTrue(report["ready"], report)
        self.assertNotIn("model.configuration", {row["id"] for row in report["checks"]})

    def test_research_plan_uses_only_prefixed_model_settings(self):
        plan = self.root / "examples/minimal/experiment.toml"
        plan.write_text(plan.read_text().replace('optimizer = "file_variants"', 'optimizer = "gepa"'))
        configured = {"AGENT_OPT_MODEL_BASE_URL": "https://example.invalid/v1",
                      "AGENT_OPT_MODEL_API_KEY": "fixture-secret"}
        with patch.dict(os.environ, configured, clear=True):
            result = collect_plan(plan, Registry())
        self.assertEqual(next(row["status"] for row in result["checks"]
                              if row["id"] == "model.configuration"), "ok")
        self.assertNotIn("fixture-secret", json.dumps(result))
        with patch.dict(os.environ, {"MODEL_ENDPOINT": configured["AGENT_OPT_MODEL_BASE_URL"],
                                     "MODEL_API_KEY": "legacy-secret"}, clear=True):
            result = collect_plan(plan, Registry())
        self.assertEqual(next(row["status"] for row in result["checks"]
                              if row["id"] == "model.configuration"), "error")
        self.assertNotIn("legacy-secret", json.dumps(result))

    def test_plan_doctor_collects_model_evaluator_budget_and_agent_failures(self):
        plan = self.root / "examples/minimal/experiment.toml"
        plan.write_text(plan.read_text().replace('evaluator = "text_fixture"', 'evaluator = "missing-evaluator"')
                        .replace('max_trials = 40', 'max_trials = 1')
                        + '\n[[stages]]\nid = "research"\noptimizer = "gepa"\nmax_trials = 3\n')
        (self.root / "examples/minimal/agents/solo/prompts/system.md").unlink()
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with patch.dict(os.environ, {"AGENT_OPT_MODEL_API_KEY": "", "AGENT_OPT_MODEL_BASE_URL": ""}), \
                patch("agent_optimizer.runner.preflight", side_effect=AssertionError("preflight")), \
                patch("agent_optimizer.models.probe_model", side_effect=AssertionError("model call")):
            report = collect_plan(plan, Registry())
        checks = {row["id"]: row for row in report["checks"]}
        self.assertFalse(report["ready"])
        for name in ("model.configuration", "evaluator.registration", "budget.trials", "agent.prompt"):
            self.assertEqual(checks[name]["status"], "error", name)
            self.assertTrue(checks[name]["remedy"])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_explicit_model_probe_only_runs_when_requested(self):
        plan = self.root / "examples/minimal/experiment.toml"
        with patch("agent_optimizer.models.probe_model", return_value={"status": "passed"}) as probe, \
                 patch.dict(os.environ, {"AGENT_OPT_MODEL_API_KEY": "", "AGENT_OPT_MODEL_BASE_URL": ""}):
            report = collect_plan(plan, Registry(), model=True)
        self.assertTrue(report["ready"], report)
        self.assertEqual({row["id"] for row in report["checks"] if row["area"] == "model"},
                         {"model.probe"})
        probe.assert_called_once()

    def test_model_doctor_and_html_report_keep_json_stdout_separate_from_progress(self):
        plan = self.root / "examples/minimal/experiment.toml"
        output, progress = io.StringIO(), io.StringIO()
        with patch("agent_optimizer.models.probe_model", return_value={"status": "passed"}), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(progress):
            self.assertEqual(main(["doctor", "--plan", str(plan), "--model", "--json"]), 0)
        self.assertEqual(json.loads(output.getvalue())["scope"], "plan")
        self.assertIn("[doctor] check=plan-model starting", progress.getvalue())

        run, _ = run_experiment(load_experiment(plan), Registry(), self.root / "runs")
        output, progress = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(progress):
            self.assertEqual(main(["report", str(run), "--html"]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "completed")
        self.assertIn("[report] check=html starting", progress.getvalue())

    def test_doctor_json_emits_one_remedial_object_for_unprepared_dataset_and_bad_plan(self):
        missing = io.StringIO()
        with contextlib.redirect_stdout(missing):
            self.assertNotEqual(main(["doctor", "--dataset", "cvdp", "--json",
                                      "--project-root", str(self.root)]), 0)
        dataset = json.loads(missing.getvalue())
        self.assertFalse(dataset["ready"])
        self.assertTrue(any(row["status"] != "ok" and row["remedy"] for row in dataset["checks"]))

        broken = self.root / "examples/minimal/experiment.toml"
        broken.write_text(broken.read_text().replace('evaluator = "text_fixture"', 'evaluator = "absent"')
                          .replace('optimizer = "file_variants"', 'optimizer = "gepa"'))
        output = io.StringIO()
        with patch.dict(os.environ, {"AGENT_OPT_MODEL_API_KEY": "SECRET_VALUE", "AGENT_OPT_MODEL_BASE_URL": ""}), \
                contextlib.redirect_stdout(output):
            self.assertNotEqual(main(["doctor", "--plan", str(broken), "--json"]), 0)
        report = json.loads(output.getvalue())
        self.assertFalse(report["ready"])
        self.assertIn("model.configuration", {row["id"] for row in report["checks"]})
        self.assertNotIn("SECRET_VALUE", output.getvalue())

    def test_shipped_sample_dataset_doctor_checks_fixture_files_without_writes(self):
        for missing, failing in ((None, None), ("examples/minimal/tasks.json", "dataset.sample_text.tasks"),
                                 ("examples/minimal/evaluator.py", "dataset.sample_text.evaluator")):
            with self.subTest(missing=missing):
                temporary, root = test_project()
                self.addCleanup(temporary.cleanup)
                if missing:
                    (root / missing).unlink()
                before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
                output = io.StringIO()
                with patch("agent_optimizer.runner.preflight", side_effect=AssertionError("preflight")), \
                        patch("agent_optimizer.models.probe_model", side_effect=AssertionError("model")), \
                        contextlib.redirect_stdout(output):
                    code = main(["doctor", "--dataset", "sample_text", "--project-root", str(root), "--json"])
                report = json.loads(output.getvalue())
                self.assertEqual(report["scope"], "dataset")
                self.assertEqual(report["ready"], missing is None, report)
                self.assertEqual(code, 0 if missing is None else 2)
                checks = {row["id"]: row for row in report["checks"]}
                self.assertTrue({"dataset.sample_text.tasks", "dataset.sample_text.evaluator"} <= set(checks))
                if missing == "examples/minimal/evaluator.py":
                    self.assertEqual(checks["dataset.registration"]["status"], "error")
                else:
                    self.assertNotIn("dataset.registration", checks)
                if failing:
                    self.assertEqual(checks[failing]["status"], "error")
                    self.assertIn(missing, checks[failing]["remedy"])
                self.assertEqual(before, {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()})
                self.assertFalse(list(root.rglob("*.pyc")))

    def test_invalid_plan_schema_still_reports_independent_evaluator(self):
        plan = self.root / "examples/minimal/experiment.toml"
        plan.write_text(plan.read_text().replace('agents = ["examples/minimal/solo.toml", "examples/minimal/team.toml"]',
                                               'agents = ["missing.toml"]')
                        .replace('evaluator = "text_fixture"', 'evaluator = "missing-evaluator"'))
        report = collect_plan(plan, Registry())
        self.assertFalse(report["ready"])
        self.assertEqual({row["id"] for row in report["checks"] if row["status"] == "error"} &
                         {"plan.schema", "evaluator.registration"},
                         {"plan.schema", "evaluator.registration"})

    def test_plan_doctor_checks_declared_command_and_research_options_without_running_evaluator(self):
        plan = self.root / "examples/minimal/experiment.toml"
        harness = self.root / "examples/minimal/harness.toml"
        harness.write_text('id = "command"\nadapter = "command"\nallow_local = true\n[runtime]\nkind = "local"\n')
        manifest = self.root / "examples/minimal/solo.toml"
        manifest.write_text(manifest.read_text().replace('"fixture", "opencode", "command"', '"command"'))
        manifest = self.root / "examples/minimal/team.toml"
        manifest.write_text(manifest.read_text().replace('"fixture", "opencode", "command"', '"command"'))
        evaluator = self.root / "examples/minimal/evaluator.py"
        evaluator.write_text('class TextFixtureEvaluator:\n'
                             '    def __init__(self, *args): raise AssertionError("evaluator constructed")\n'
                             '    def validate_benchmark(self, *args): raise AssertionError("trial validation")\n')
        plan.write_text(plan.read_text().replace('optimizer = "file_variants"', 'optimizer = "gepa"')
                        .replace('include_seeds = true', 'file = "missing.txt"\niterations = -1'))
        with patch.dict(os.environ, {"AGENT_OPT_MODEL_BASE_URL": "", "AGENT_OPT_MODEL_API_KEY": ""}), \
                patch("agent_optimizer.runner.preflight", side_effect=AssertionError("preflight")):
            report = collect_plan(plan, Registry())
        checks = {row["id"]: row for row in report["checks"]}
        self.assertEqual(checks["agent.argv"]["status"], "error")
        self.assertEqual(checks["optimizer.options"]["status"], "error")
        self.assertEqual(checks["evaluator.registration"]["status"], "ok")

    def test_opencode_profile_needs_its_declared_model_env_and_binary_not_optimizer_api_key(self):
        plan = self.root / "examples/minimal/experiment.toml"
        harness = self.root / "examples/minimal/harness.toml"
        harness.write_text('id = "opencode"\nadapter = "opencode"\nmodel_env = "TEAM_MODEL"\n'
                           '[runtime]\nkind = "docker"\nimage = "pinned-agent"\n')
        with patch.dict(os.environ, {"AGENT_OPT_MODEL_API_KEY": "", "AGENT_OPT_MODEL_BASE_URL": "", "TEAM_MODEL": ""}), \
                patch("agent_optimizer.readiness.shutil.which", return_value=None):
            checks = {row["id"]: row for row in collect_plan(plan, Registry())["checks"]}
        self.assertEqual(checks["model.configuration"]["status"], "error")
        self.assertIn("TEAM_MODEL", checks["model.configuration"]["remedy"])
        self.assertEqual(checks["runtime.binary"]["status"], "error")
        with patch.dict(os.environ, {"AGENT_OPT_MODEL_API_KEY": "", "AGENT_OPT_MODEL_BASE_URL": "", "TEAM_MODEL": "team/model"}), \
                patch("agent_optimizer.readiness.shutil.which", return_value="/usr/bin/docker"):
            checks = {row["id"]: row for row in collect_plan(plan, Registry())["checks"]}
        self.assertEqual(checks["model.configuration"]["status"], "ok")
        self.assertEqual(checks["runtime.binary"]["status"], "ok")

    def test_invalid_project_root_is_structured_json_failure(self):
        plan = self.root / "examples/minimal/experiment.toml"
        plan.write_text(plan.read_text().replace('project_root = "../.."', 'project_root = ["invalid"]'))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["doctor", "--plan", str(plan), "--json"])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(output.getvalue())["ready"])

    def test_multiple_harness_profiles_have_unique_stable_check_ids(self):
        plan = self.root / "examples/minimal/experiment.toml"
        plan.write_text(plan.read_text().replace('harnesses = ["examples/minimal/harness.toml"]',
                                               'harnesses = ["examples/minimal/harness.toml", '
                                               '"examples/minimal/second.toml"]'))
        (self.root / "examples/minimal/second.toml").write_text('id = "second"\nadapter = "fixture"\n')
        report = collect_plan(plan, Registry())
        identifiers = [row["id"] for row in report["checks"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertTrue(report["ready"], report)

    def test_malformed_evaluator_id_is_structured_failure(self):
        plan = self.root / "examples/minimal/experiment.toml"
        plan.write_text(plan.read_text().replace('evaluator = "text_fixture"', 'evaluator = ["bad"]'))
        report = collect_plan(plan, Registry())
        self.assertFalse(report["ready"])
        self.assertEqual({row["id"]: row["status"] for row in report["checks"]}["evaluator.registration"],
                         "error")

    def test_doctor_never_imports_evaluator_optimizer_or_harness_plugins(self):
        for relative in ("examples/minimal/evaluator.py", "experiments/sample-team/optimizer.py",
                         "experiments/sample-team/harness.py"):
            path = self.root / relative
            path.write_text(path.read_text() + "\nfrom pathlib import Path\n"
                            "Path(__file__).with_name('import-side-effect').write_text('unexpected')\n")
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        dataset = io.StringIO()
        plan = io.StringIO()
        with contextlib.redirect_stdout(dataset):
            dataset_code = main(["doctor", "--dataset", "sample_text", "--project-root", str(self.root), "--json"])
        with contextlib.redirect_stdout(plan):
            plan_code = main(["doctor", "--plan", str(self.root / "examples/minimal/experiment.toml"), "--json"])
        self.assertEqual(dataset_code, 0, dataset.getvalue())
        self.assertEqual(plan_code, 0, plan.getvalue())
        self.assertTrue(json.loads(dataset.getvalue())["ready"])
        self.assertTrue(json.loads(plan.getvalue())["ready"])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_user_doctor_disables_bytecode_before_package_and_plugin_imports(self):
        package_root = Path(__file__).resolve().parents[1]
        shutil.copytree(package_root / "src/agent_optimizer", self.root / "src/agent_optimizer",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        env = {key: value for key, value in os.environ.items()
               if key not in {"PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX"}}
        env["PYTHONPATH"] = str(self.root / "src")
        argv = ["doctor", "--dataset", "sample_text", "--project-root", str(self.root), "--json"]
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for command in ([sys.executable, str(package_root / "scripts/agent-opt"), *argv],):
            with self.subTest(command=command[:3]):
                result = subprocess.run(command, cwd=self.root, env=env, capture_output=True,
                                        text=True, timeout=30, shell=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(json.loads(result.stdout)["ready"])
                self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_direct_main_doctor_guards_later_plugin_imports(self):
        # cli is already imported by this test process, just as in an embedding application.
        import agent_optimizer.cli as cli
        previous = sys.dont_write_bytecode
        sys.dont_write_bytecode = False
        try:
            original_registry = cli.Registry

            def guarded_registry():
                self.assertTrue(sys.dont_write_bytecode, "doctor must guard before registry construction")
                return original_registry()

            before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
            with patch.object(cli, "Registry", side_effect=guarded_registry), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["doctor", "--dataset", "sample_text",
                                           "--project-root", str(self.root), "--json"]), 0)
            self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
            # main restores the value at call entry (False), not the test process's earlier value.
            self.assertIs(sys.dont_write_bytecode, False)
        finally:
            sys.dont_write_bytecode = previous

    def test_direct_doctor_restores_each_entry_bytecode_setting_even_on_exception(self):
        import agent_optimizer.cli as cli
        previous = sys.dont_write_bytecode
        try:
            for enabled in (False, True):
                with self.subTest(enabled=enabled):
                    sys.dont_write_bytecode = enabled
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(cli.main(["doctor", "--plan",
                                                   str(self.root / "examples/minimal/experiment.toml"), "--json"]), 0)
                    self.assertIs(sys.dont_write_bytecode, enabled)

                    def fail_during_doctor(*_args, **_kwargs):
                        self.assertTrue(sys.dont_write_bytecode)
                        raise RuntimeError("interrupted doctor")

                    with patch.object(cli.typer.main, "get_command", side_effect=fail_during_doctor):
                        with self.assertRaisesRegex(RuntimeError, "interrupted doctor"):
                            cli.main(["doctor"])
                    self.assertIs(sys.dont_write_bytecode, enabled)
        finally:
            sys.dont_write_bytecode = previous

    def test_direct_doctor_preserves_env_enabled_bytecode_guard(self):
        package_root = Path(__file__).resolve().parents[1]
        script = "\n".join((
            "import sys",
            "from agent_optimizer.cli import main",
            "assert sys.dont_write_bytecode is True, 'environment flag missing on entry'",
            "assert main(['doctor', '--plan', sys.argv[1], '--json']) == 0",
            "assert sys.dont_write_bytecode is True, 'doctor changed the entry flag'",
        ))
        result = subprocess.run(
            [sys.executable, "-c", script, str(self.root / "examples/minimal/experiment.toml")],
            cwd=self.root, capture_output=True, text=True, timeout=30, shell=False,
            env={**os.environ, "PYTHONPATH": str(package_root / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ready"])

    def test_symlink_editable_path_reports_structured_error(self):
        manifest = self.root / "examples/minimal/solo.toml"
        manifest.write_text(manifest.read_text().replace('"configs/**",', '"configs/**", "escape/**",'))
        (self.agent / "escape").symlink_to(self.root / "examples/minimal/agents/team", target_is_directory=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["doctor", "--plan", str(self.root / "examples/minimal/experiment.toml"), "--json"])
        self.assertEqual(code, 2)
        checks = {row["id"]: row for row in json.loads(output.getvalue())["checks"]}
        self.assertEqual(checks["plan.schema"]["status"], "ok")
        self.assertEqual(checks["agent.editable"]["status"], "error")

    def test_excluded_symlink_under_editable_glob_does_not_block_snapshot(self):
        manifest = self.root / "examples/minimal/solo.toml"
        manifest.write_text(manifest.read_text() + '\nexclude = ["src/link.py"]\n')
        (self.agent / "src/link.py").symlink_to(self.root / "examples/minimal/tasks.json")
        report = collect_plan(self.root / "examples/minimal/experiment.toml", Registry())
        checks = {row["id"]: row for row in report["checks"]}
        self.assertEqual(checks["agent.editable"]["status"], "ok")
        self.assertTrue(report["ready"], report)

    def test_prompt_must_survive_declared_source_snapshot_filters(self):
        manifest = self.root / "examples/minimal/solo.toml"
        for key, value in (("include", '["configs/**", "src/**"]'),
                           ("exclude", '["prompts/**"]')):
            with self.subTest(key=key):
                original = manifest.read_text()
                manifest.write_text(original.replace('include = ["prompts/**", "configs/**", "src/**", '
                                                     '"overlays/**", "harness_source/**"]',
                                                     'include = ' + value) if key == "include" else
                                    original + '\nexclude = ' + value + '\n')
                report = collect_plan(self.root / "examples/minimal/experiment.toml", Registry())
                checks = {row["id"]: row for row in report["checks"]}
                self.assertEqual(checks["agent.prompt"]["status"], "error")
                self.assertFalse(report["ready"])
                manifest.write_text(original)

    def test_pinned_git_plan_checks_declarations_without_fetching_or_claiming_contents(self):
        plan = self.root / "examples/minimal/experiment.toml"
        for name in ("solo", "team"):
            manifest = self.root / f"examples/minimal/{name}.toml"
            text = manifest.read_text()
            text = text.replace('kind = "local"', 'kind = "git"').replace(
                f'path = "agents/{name}"',
                'url = "https://example.invalid/team/agent.git"\nrevision = "' + 'a' * 40 + '"')
            manifest.write_text(text)
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with patch("agent_optimizer.sources.subprocess.run", side_effect=AssertionError("no Git fetch")):
            report = collect_plan(plan, Registry())
        checks = {row["id"]: row for row in report["checks"]}
        self.assertTrue(report["ready"], report)
        for identifier in ("agent.source", "agent.prompt", "agent.editable"):
            self.assertEqual(checks[identifier]["status"], "ok", checks)
            self.assertIn("unverified", checks[identifier]["message"].lower())
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_pinned_git_exact_source_include_matches_editable_glob_without_fetch(self):
        plan = self.root / "examples/minimal/experiment.toml"
        manifest = self.root / "examples/minimal/solo.toml"
        text = manifest.read_text().replace('kind = "local"', 'kind = "git"').replace(
            'path = "agents/solo"',
            'url = "https://example.invalid/team/agent.git"\nrevision = "' + 'a' * 40 + '"')
        text = text.replace('editable = ["prompts/**", "configs/**", "src/**", "overlays/**", "harness_source/**"]',
                            'editable = ["configs/**"]').replace(
            'include = ["prompts/**", "configs/**", "src/**", "overlays/**", "harness_source/**"]',
            'include = ["prompts/system.md", "configs/strategy.json"]')
        for excluded in (False, True):
            with self.subTest(excluded=excluded):
                manifest.write_text(text + ('\nexclude = ["configs/strategy.json"]\n' if excluded else ''))
                before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
                output = io.StringIO()
                with patch("agent_optimizer.sources.subprocess.run", side_effect=AssertionError("no Git fetch")), \
                        contextlib.redirect_stdout(output):
                    code = main(["doctor", "--plan", str(plan), "--json"])
                report = json.loads(output.getvalue())
                checks = {row["id"]: row for row in report["checks"]}
                self.assertEqual(code, 2 if excluded else 0, report)
                self.assertEqual(checks["agent.prompt"]["status"], "ok")
                self.assertEqual(checks["agent.editable"]["status"], "error" if excluded else "ok")
                self.assertIn("unverified", checks["agent.editable"]["message"].lower())
                self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_pinned_git_plan_rejects_excluded_prompt_and_unsafe_editable(self):
        plan = self.root / "examples/minimal/experiment.toml"
        manifest = self.root / "examples/minimal/solo.toml"
        text = manifest.read_text().replace('kind = "local"', 'kind = "git"').replace(
            'path = "agents/solo"',
            'url = "https://example.invalid/team/agent.git"\nrevision = "' + 'a' * 40 + '"')
        manifest.write_text(text + '\nexclude = ["prompts/**"]\n')
        checks = {row["id"]: row for row in collect_plan(plan, Registry())["checks"]}
        self.assertEqual(checks["agent.prompt"]["status"], "error")
        manifest.write_text(text.replace('"configs/**"', '"../escape/**"'))
        checks = {row["id"]: row for row in collect_plan(plan, Registry())["checks"]}
        self.assertEqual(checks["agent.editable"]["status"], "error")

    def test_pinned_git_plan_rejects_malformed_locator_and_unpinned_revision(self):
        plan = self.root / "examples/minimal/experiment.toml"
        manifest = self.root / "examples/minimal/solo.toml"
        original = manifest.read_text().replace('kind = "local"', 'kind = "git"').replace(
            'path = "agents/solo"',
            'url = "https://example.invalid/team/agent.git"\nrevision = "' + 'a' * 40 + '"')
        for broken in (original.replace('https://example.invalid/team/agent.git', 'https://'),
                       original.replace('a' * 40, 'main')):
            manifest.write_text(broken)
            checks = {row["id"]: row for row in collect_plan(plan, Registry())["checks"]}
            self.assertEqual(checks["plan.schema"]["status"], "error")

    def test_evaluator_docker_runtime_requires_binary_even_with_local_harness(self):
        plan = self.root / "examples/minimal/experiment.toml"
        plan.write_text(plan.read_text() + '\n[evaluation_runtime]\nkind = "docker"\nimage = "eval-only"\n')
        with patch("agent_optimizer.readiness.shutil.which", return_value=None):
            report = collect_plan(plan, Registry())
        self.assertEqual({row["id"]: row["status"] for row in report["checks"]}["runtime.binary"], "error")
        self.assertFalse(report["ready"])

    def test_trial_budget_reserves_repeated_baseline_and_final_test(self):
        plan = self.root / "examples/minimal/experiment.toml"
        plan.write_text(plan.read_text().replace('max_trials = 40', 'max_trials = 18')
                        .replace('repetitions = 1', 'repetitions = 3')
                        .replace('optimizer = "file_variants"', 'optimizer = "file_variants"\nmax_trials = 5'))
        report = collect_plan(plan, Registry())
        check = {row["id"]: row for row in report["checks"]}["budget.trials"]
        self.assertEqual(check["status"], "error")
        self.assertIn("28", check["remedy"])

    def test_dataset_inventory_lists_builtin_names_without_recommending_one(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main(["datasets", "list", "--project-root", str(self.root)])
        self.assertEqual(result, 0)
        names = {row["name"] for row in json.loads(output.getvalue())}
        self.assertEqual(names, {"cvdp", "verilog-spec", "verilog-completion", "sample_text"})

    def test_wheel_catalog_without_repository(self):
        with tempfile.TemporaryDirectory(prefix="standalone-agent-opt-") as directory:
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["datasets", "list", "--project-root", directory]), 0)
            rows = json.loads(output.getvalue())
            self.assertEqual({row["name"] for row in rows},
                             {"cvdp", "verilog-spec", "verilog-completion"})
            self.assertTrue(all(row["requires_preparation"] for row in rows))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_optional_integration_catalog_is_pinned_and_read_only(self):
        from agent_optimizer.catalog import INTEGRATIONS

        self.assertEqual(INTEGRATIONS["ace-rtl"]["revision"],
                         "ae0874fb94d94284a07a17d84ef60058ed9a97b6")
        self.assertEqual(INTEGRATIONS["ace-rtl"]["contract"], 1)
        with tempfile.TemporaryDirectory(prefix="catalog-only-") as directory:
            output = io.StringIO()
            with patch("subprocess.run", side_effect=AssertionError("조회 중 외부 도구 실행")), \
                    contextlib.redirect_stdout(output):
                self.assertEqual(main(["datasets", "list", "--project-root", directory]), 0)
            self.assertFalse((Path(directory) / "examples").exists())
            self.assertIn("cvdp", {row["name"] for row in json.loads(output.getvalue())})

    def test_ace_pending_pointer_before_preparation_is_read_only(self):
        workspace = self.root / "new-user-workspace"
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            self.assertEqual(main(["init", "--profile", "ace-rtl",
                                   "--workspace", str(workspace)]), 0, error.getvalue())
        pointer = Path(json.loads(output.getvalue())["experiment"])
        self.assertEqual(pointer, workspace.resolve() / "experiment.toml")
        self.assertEqual({p.name for p in workspace.iterdir()}, {"experiment.toml"})
        diagnostic = io.StringIO()
        with contextlib.redirect_stdout(diagnostic), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["doctor", "--plan", str(pointer), "--json"]), 2)
        self.assertEqual({row["id"]: row["status"] for row in json.loads(diagnostic.getvalue())["checks"]}
                         ["integration.prepare"], "blocked")
        error = io.StringIO()
        with contextlib.redirect_stderr(error), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["run", str(pointer)]), 2)
        self.assertIn("prepare", error.getvalue())
        self.assertFalse((workspace / "integrations").exists())

    def test_ace_profile_rejects_mixed_agent_settings_without_writes(self):
        workspace = self.root / "invalid-profile"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["init", "--profile", "ace-rtl", "--workspace", str(workspace),
                                   "--agent", str(self.agent)]), 2)
        self.assertFalse(workspace.exists())

    def test_ace_pointer_rejects_symlink_before_preparation(self):
        from agent_optimizer.contracts import ConfigurationError
        from agent_optimizer.integrations import read_pointer

        workspace = self.root / "source-pointer"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["init", "--profile", "ace-rtl",
                                   "--workspace", str(workspace)]), 0)
        alias = self.root / "pointer-alias.toml"
        alias.symlink_to(workspace / "experiment.toml")
        with self.assertRaises(ConfigurationError):
            read_pointer(alias)

    def test_bare_cli_prepares_only_explicit_cvdp_dataset(self):
        from agent_optimizer.catalog import INTEGRATIONS

        workspace = self.root / "bare-cvdp"
        workspace.mkdir()

        def selected_files(root, integration_id, *, offline=False):
            self.assertEqual((root, integration_id), (workspace.resolve(), "cvdp"))
            sources = {
                "examples/benchmarks/cvdp.py": (
                    'import json\nfrom pathlib import Path\n'
                    'class Provider:\n'
                    '    def describe(self): return {"name": "cvdp", "task_form": "rtl-generation", '
                    '"evaluator": "cvdp"}\n'
                    '    def prepare(self, cache, *, offline=False):\n'
                    '        output = cache / "tasks.json"\n'
                    '        output.parent.mkdir(parents=True, exist_ok=True)\n'
                    '        output.write_text(json.dumps({"schema_version": 1, "tasks": [\n'
                    '          {"id": "one", "split": "validation", "prompt": "task", '
                    '"files": {"dut.sv": "module dut; endmodule"}, "evaluation": {}}]}))\n'
                    '        return {"benchmark": str(output), "evaluator": "cvdp"}\n'
                    '    def doctor(self, cache):\n'
                    '        return [{"id": "dataset.fixture", "area": "dataset", "status": "ok", '
                    '"message": "prepared", "remedy": ""}]\n'),
                "examples/ace-rtl/evaluator.py": "class CVDPEvaluator: pass\n",
                "examples/ace-rtl/prepare.py": "# public importer fixture\n",
                "examples/ace-rtl/environment/setup.py": "# fixed environment fixture\n",
                "examples/ace-rtl/environment/network_driver.py": "# trusted helper fixture\n",
            }
            for relative, body in sources.items():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body)
            return {"url": INTEGRATIONS["cvdp"]["url"],
                    "revision": INTEGRATIONS["cvdp"]["revision"], "paths": list(sources)}

        output = io.StringIO()
        with patch("agent_optimizer.integrations.acquire_integration", side_effect=selected_files), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["datasets", "prepare", "cvdp", "--project-root", str(workspace)]), 0)
        self.assertEqual(json.loads(output.getvalue())["dataset_provider"], "cvdp")
        marker = json.loads((workspace / ".agent-opt/integration-ready.json").read_text())
        self.assertEqual(marker["id"], "cvdp")
        registry = Registry()
        registry.load_project(workspace)
        self.assertEqual(registry.resolve("evaluators", "cvdp").__name__, "CVDPEvaluator")

    def test_ace_prepare_marks_workspace_ready_only_after_lifecycle_checks(self):
        from agent_optimizer.catalog import INTEGRATIONS
        from agent_optimizer.contracts import ConfigurationError
        from agent_optimizer.integrations import resolve_pointer

        workspace = self.root / "prepared-user-workspace"
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["init", "--profile", "ace-rtl", "--workspace", str(workspace)]), 0)
        pointer = Path(json.loads(output.getvalue())["experiment"])

        def prepared_files(root, integration_id, *, offline=False):
            self.assertEqual((root, integration_id, offline), (workspace.resolve(), "ace-rtl", True))
            lifecycle = root / "examples/ace-rtl/environment/lifecycle.py"
            lifecycle.parent.mkdir(parents=True)
            lifecycle.write_text(
                'from pathlib import Path\n'
                'def prepare(root, *, offline=False, platform=None):\n'
                '    target = root / "datasets/ace-demo/tasks.json"\n'
                '    target.parent.mkdir(parents=True, exist_ok=True)\n'
                '    target.write_text("{}")\n'
                '    return target\n'
                'def inspect(root, *, platform=None):\n'
                '    return {"ready": True, "checks": [], "lock": {"platform": "linux/arm64"}}\n')
            return {"url": INTEGRATIONS["ace-rtl"]["url"],
                    "revision": INTEGRATIONS["ace-rtl"]["revision"],
                    "paths": ["examples/ace-rtl/environment/lifecycle.py"]}

        with patch("agent_optimizer.integrations.acquire_integration", side_effect=prepared_files), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["prepare", str(pointer), "--offline"]), 0)
        marker = json.loads((workspace / ".agent-opt/integration-ready.json").read_text())
        self.assertTrue(marker["ready"])
        self.assertEqual(marker["revision"], INTEGRATIONS["ace-rtl"]["revision"])
        (workspace / "examples/ace-rtl/environment/lifecycle.py").write_text("tampered")
        with self.assertRaises(ConfigurationError):
            resolve_pointer(pointer)

    def test_unrelated_project_with_same_package_name_is_not_treated_as_source_checkout(self):
        with tempfile.TemporaryDirectory(prefix="user-project-") as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text('[project]\nname = "agent-optimizer"\n')
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["datasets", "list", "--project-root", directory]), 0)
            self.assertEqual({row["name"] for row in json.loads(output.getvalue())},
                             {"cvdp", "verilog-spec", "verilog-completion"})

    def test_bare_workspace_custom_agent_and_evaluator(self):
        temporary = tempfile.TemporaryDirectory(prefix="agent-opt-bare-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        agent = root / "agents/solo"
        shutil.copytree(self.agent, agent)
        shutil.copyfile(self.data, root / "tasks.json")
        shutil.copyfile(self.root / "examples/minimal/evaluator.py", root / "evaluator.py")
        before = (agent / "configs/strategy.json").read_bytes()
        args = ["init", "--project-root", str(root), "--name", "bare-user",
                "--agent", "agents/solo", "--dataset", "tasks.json",
                "--evaluator", "evaluator.py:TextFixtureEvaluator",
                "--editable", "configs/strategy.json", "--optimizer", "baseline",
                "--command", "{python} {agent_dir}/src/fixture_agent.py {task_dir}", "--yes"]
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            self.assertEqual(main(args), 0, error.getvalue())
        experiment = Path(json.loads(output.getvalue())["experiment"])
        diagnostic, run = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(diagnostic), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["doctor", "--plan", str(experiment), "--json"]), 0,
                             diagnostic.getvalue())
        self.assertTrue(json.loads(diagnostic.getvalue())["ready"])
        with contextlib.redirect_stdout(run), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["run", str(experiment)]), 0)
        result = json.loads(run.getvalue())
        self.assertEqual(result["status"], "completed")
        self.assertTrue((Path(result["run_dir"]) / "report.html").is_file())
        self.assertEqual((agent / "configs/strategy.json").read_bytes(), before)

    def test_dataset_inventory_works_from_outside_project_import_path(self):
        package_root = Path(__file__).resolve().parents[1]
        command = [sys.executable, "-c", "import sys; from agent_optimizer.cli import main; "
                   "sys.exit(main(['datasets', 'list', '--project-root', sys.argv[1]]))",
                   str(package_root)]
        with tempfile.TemporaryDirectory() as elsewhere:
            process = subprocess.run(command, cwd=elsewhere, capture_output=True, text=True,
                                     env={**os.environ, "PYTHONPATH": str(package_root / "src")},
                                     timeout=30, shell=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual({row["name"] for row in json.loads(process.stdout)},
                         {"cvdp", "verilog-spec", "verilog-completion", "sample_text"})

    def test_shipped_synthetic_team_components_run_from_generated_plan(self):
        args = ["init", "--project-root", str(self.root), "--agent", str(self.agent),
                "--name", "shipped-team", "--dataset", "sample_text", "--harness", "sample_command",
                "--optimizer", "sample_baseline", "--editable", "configs/strategy.json",
                 "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]', "--yes"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
        plan = Path(json.loads(output.getvalue())["experiment"])
        spec = load_experiment(plan)
        self.assertEqual(spec["_profiles"][0]["adapter"], "sample_command")
        self.assertEqual(spec["_benchmark_metadata"]["dataset_provider"], "sample_text")
        self.assertEqual(spec["evaluator"], "sample_eval")
        self.assertFalse(spec.get("plugins"))
        run, summary = run_experiment(spec, Registry(), self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["groups"][0]["stages"][0]["checkpoint"],
                         {"kind": "synthetic_example"})
        trials = [json.loads(path.read_text()) for path in run.glob("**/trials/**/result.json")]
        self.assertTrue(trials)
        self.assertTrue(all(row["metrics"]["sample_adapter"] == 1.0 for row in trials))
        fingerprints = json.loads((run / "manifest.json").read_text())["plugin_sha256"]
        for reference in ("experiments/sample-team/provider.py:Provider",
                          "experiments/sample-team/harness.py:Harness",
                          "experiments/sample-team/optimizer.py:Optimizer",
                          "examples/minimal/evaluator.py:TextFixtureEvaluator"):
            self.assertIn(reference, fingerprints)

    def test_registered_provider_cannot_return_an_evaluator_file_reference(self):
        provider = self.root / "experiments/sample-team/provider.py"
        code = provider.read_text()
        provider.write_text(code.replace('"evaluator": "sample_eval"',
                                         '"evaluator": "examples/minimal/evaluator.py:TextFixtureEvaluator"'))
        args = ["init", "--project-root", str(self.root), "--agent", str(self.agent),
                "--dataset", "sample_text", "--name", "invalid-provider",
                "--editable", "configs/strategy.json", "--optimizer", "baseline", "--command-json",
                 '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]', "--yes"]
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(args), 2)
        self.assertIn("registered evaluator ID", errors.getvalue())
        self.assertFalse((self.root / "runs").exists())

    def test_noninteractive_init_requires_explicit_dataset_without_creating_files(self):
        error = io.StringIO()
        with patch("sys.stdin.isatty", return_value=False), contextlib.redirect_stderr(error):
            result = main(["init", "--project-root", str(self.root), "--agent", str(self.agent)])
        self.assertEqual(result, 2)
        self.assertIn("dataset", error.getvalue().lower())
        self.assertFalse((self.root / "runs").exists())

    def test_init_no_optimizer_fails_before_dataset_preparation(self):
        args = ["init", "--project-root", str(self.root), "--agent", str(self.agent),
                "--name", "no-optimizer", "--dataset", "sample_text",
                "--editable", "configs/strategy.json", "--command-json",
                '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]', "--yes"]
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
            code = main(args)
        self.assertEqual(code, 2)
        self.assertIn("--optimizer", errors.getvalue())
        self.assertFalse((self.root / "external/datasets/sample_text").exists())
        self.assertFalse((self.root / "runs/configs/no-optimizer").exists())

    def test_init_rejects_removed_argv_without_preparing_dataset(self):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
            code = main(["init", "--project-root", str(self.root), "--agent", str(self.agent),
                         "--name", "old-argv", "--dataset", str(self.data),
                         "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                         "--editable", "configs/strategy.json", "--optimizer", "baseline",
                         "--argv", "{python}", "{task_dir}", "--yes"])
        self.assertEqual(code, 2)
        self.assertFalse((self.root / "runs").exists())

    def test_init_generates_loadable_config_for_custom_scored_dataset(self):
        output = io.StringIO()
        args = ["init", "--project-root", str(self.root), "--agent", str(self.agent),
                "--name", "custom-demo", "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--editable", "configs/strategy.json", "--optimizer", "baseline",
                 "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]', "--yes"]
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

    def test_tui_optional_ace_decline_creates_no_workspace_or_cache(self):
        workspace, cache = self.root / "declined-ace", self.root / "unused-cache"
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with patch("sys.stdin.isatty", return_value=True), \
                patch("builtins.input", side_effect=["3", str(workspace), "n"]), \
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(cache)}), \
                contextlib.redirect_stderr(terminal), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
        self.assertIn("ACE-RTL", terminal.getvalue())
        self.assertIn(str(workspace), terminal.getvalue())
        self.assertFalse(workspace.exists())
        self.assertFalse(cache.exists())

    def test_tui_optional_ace_prepares_then_requires_separate_run_confirmation(self):
        from agent_optimizer.catalog import INTEGRATIONS
        from agent_optimizer.integrations import selected_files

        workspace = self.root / "selected-ace"
        target = workspace / "experiment.toml"
        source = self.data.read_text(encoding="utf-8")

        def pinned_files(root, integration_id, *, offline=False):
            self.assertEqual((root, integration_id, offline), (workspace.resolve(), "ace-rtl", False))
            originals = selected_files(ROOT, "ace-rtl")
            paths = [path.relative_to(ROOT).as_posix() for path in originals]
            for path, relative in zip(originals, paths):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
            (root / "examples/ace-rtl/environment/lifecycle.py").write_text(
                'from agent_optimizer.contracts import UnavailableError\n'
                'def prepare(root, *, offline=False, platform=None):\n'
                '    output = root / "datasets/ace-demo/tasks.json"\n'
                '    output.parent.mkdir(parents=True, exist_ok=True)\n'
                f'    output.write_text({source!r}, encoding="utf-8")\n'
                '    print("[setup] 검증된 데이터셋 준비 완료")\n'
                '    return output\n'
                'def inspect(root, *, platform=None):\n'
                '    return {"ready": True, "checks": [], "lock": {"platform": "linux/amd64"}}\n'
                'def run(root, *, iterations=None, platform=None):\n'
                '    (root / "executed.marker").write_text("executed")\n'
                '    return 0\n', encoding="utf-8")
            return {"url": INTEGRATIONS["ace-rtl"]["url"],
                    "revision": INTEGRATIONS["ace-rtl"]["revision"], "paths": paths}

        class Terminal(io.StringIO):
            def isatty(self):
                return True

        for answers, expected in ((["3", str(workspace), "y", "n"], 2),
                                  (["1", str(target), "y"], 0)):
            terminal = Terminal()
            with patch("sys.stdin.isatty", return_value=True), \
                    patch("builtins.input", side_effect=answers), \
                    patch.dict(os.environ, {"AGENT_OPT_MODEL_API_KEY": "fixture",
                                             "AGENT_OPT_MODEL_BASE_URL": "https://example.invalid/v1",
                                            "AGENT_OPT_MODEL": "fixture"}), \
                    patch("agent_optimizer.integrations.acquire_integration", side_effect=pinned_files), \
                    patch("agent_optimizer.readiness.shutil.which", return_value="/fixture/docker"), \
                    contextlib.redirect_stderr(terminal), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["tui", "--project-root", str(self.root)]), expected,
                                 terminal.getvalue())
            self.assertTrue(target.is_file())
            self.assertTrue((workspace / ".agent-opt/integration-ready.json").is_file())
            self.assertEqual((workspace / "executed.marker").exists(), expected == 0)
            self.assertIn("계획 진단: 준비됨", terminal.getvalue())

    def test_tui_wizard_prepares_explicit_user_choice_and_runs(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal, output = Terminal(), io.StringIO()
        answers = ["2", "wizard-demo", str(self.agent), "configs/strategy.json", str(self.data),
                   "examples/minimal/evaluator.py:TextFixtureEvaluator", "", "", "1", "1",
                   "{python} {agent_dir}/src/fixture_agent.py {task_dir}", "y"]
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=answers), \
                contextlib.redirect_stderr(terminal), contextlib.redirect_stdout(output):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "completed")
        self.assertTrue((self.root / "runs/configs/wizard-demo/experiment.toml").is_file())
        self.assertIn("fixture-validation", terminal.getvalue())
        self.assertIn("데이터셋:", terminal.getvalue().split("선택한 데이터셋 준비 중", 1)[0][-500:])

    def test_interactive_init_creates_a_config_without_running_agent(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal, output = Terminal(), io.StringIO()
        answers = ["guided-demo", str(self.agent), "configs/strategy.json", str(self.data),
                   "examples/minimal/evaluator.py:TextFixtureEvaluator", "", "", "1", "1",
                   "{python} {agent_dir}/src/fixture_agent.py {task_dir}", "y"]
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=answers), \
                contextlib.redirect_stderr(terminal), contextlib.redirect_stdout(output):
            self.assertEqual(main(["init", "--project-root", str(self.root)]), 0)
        self.assertTrue(Path(json.loads(output.getvalue())["experiment"]).is_file())
        self.assertIn("doctor --plan", terminal.getvalue())
        self.assertIn("agent-opt run", terminal.getvalue())
        self.assertFalse(any(path.name == "summary.json" for path in (self.root / "runs").rglob("summary.json")))

    def test_english_interactive_init_explains_next_commands(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal, output = Terminal(), io.StringIO()
        answers = ["english-guide", str(self.agent), "configs/strategy.json", str(self.data),
                   "examples/minimal/evaluator.py:TextFixtureEvaluator", "", "", "1", "1",
                   "{python} {agent_dir}/src/fixture_agent.py {task_dir}", "y"]
        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}), \
                patch("sys.stdin.isatty", return_value=True), \
                patch("builtins.input", side_effect=answers), \
                contextlib.redirect_stderr(terminal), contextlib.redirect_stdout(output):
            self.assertEqual(main(["init", "--project-root", str(self.root)]), 0)
        self.assertTrue(Path(json.loads(output.getvalue())["experiment"]).is_file())
        self.assertIn("Configuration created:", terminal.getvalue())
        self.assertIn("Next: agent-opt doctor --plan", terminal.getvalue())

    def test_interactive_init_multiple_datasets_prints_session_run_instructions(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal, output = Terminal(), io.StringIO()
        answers = ["multi-guided", str(self.agent), "configs/strategy.json",
                   f"{self.data},{self.data}", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                   "", "", "1", "1", "{python} {agent_dir}/src/fixture_agent.py {task_dir}", "y"]
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=answers), \
                contextlib.redirect_stderr(terminal), contextlib.redirect_stdout(output):
            self.assertEqual(main(["init", "--project-root", str(self.root)]), 0)
        result = json.loads(output.getvalue())
        self.assertTrue(Path(result["session"]).is_file())
        self.assertIn(f"agent-opt run-session {result['session']}", terminal.getvalue())
        self.assertNotIn(f"doctor --plan {result['session']}", terminal.getvalue())

    def test_tui_multi_dataset_run_shows_independent_rows_and_one_json(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal, output = Terminal(), io.StringIO()
        answers = ["2", "multi-wizard", str(self.agent), "configs/strategy.json",
                   f"{self.data},{self.data}", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                   "", "", "1", "1", "{python} {agent_dir}/src/fixture_agent.py {task_dir}", "y"]
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=answers), \
                contextlib.redirect_stderr(terminal), contextlib.redirect_stdout(output):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "completed")
        self.assertIn("[1/2]", terminal.getvalue())
        self.assertIn("[2/2]", terminal.getvalue())

    def test_tui_existing_ace_profile_does_not_ask_for_command_or_prepare_dataset(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with patch("sys.stdin.isatty", return_value=True), \
                patch("builtins.input", side_effect=["1", "examples/ace-rtl/experiment.toml"]), \
                patch("agent_optimizer.cli.run_experiment", side_effect=AssertionError("should not run")), \
                contextlib.redirect_stderr(terminal), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
        self.assertNotIn("Agent execution argv", terminal.getvalue())
        self.assertFalse((self.root / "runs").exists())
        self.assertFalse(any(self.root.rglob("__pycache__")))

    def test_ace_example_plan_reuses_registered_cvdp_evaluator(self):
        benchmark = self.root / "datasets/ace-demo/tasks.json"
        benchmark.parent.mkdir(parents=True)
        shutil.copyfile(self.data, benchmark)
        shutil.copytree(ROOT / "experiments/simple-feedback", self.root / "experiments/simple-feedback")
        model_module = self.root / "src/agent_optimizer/models.py"
        model_module.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "src/agent_optimizer/models.py", model_module)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["doctor", "--plan", str(self.root / "examples/ace-rtl/experiment.toml"),
                                   "--json"]), 0)
        report = json.loads(output.getvalue())
        self.assertTrue(report["ready"], report["checks"])

    def test_tui_existing_ready_experiment_requires_confirmation_before_run(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        experiment = "examples/minimal/experiment.toml"
        with patch("sys.stdin.isatty", return_value=True), \
                patch("builtins.input", side_effect=["1", experiment, "n"]), \
                contextlib.redirect_stderr(Terminal()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
        self.assertFalse((self.root / "runs").exists())
        output = io.StringIO()
        with patch("sys.stdin.isatty", return_value=True), \
                patch("builtins.input", side_effect=["1", experiment, "y"]), \
                contextlib.redirect_stderr(Terminal()), contextlib.redirect_stdout(output):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "completed")

    def test_tui_existing_experiment_keeps_stdout_as_single_json_result(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        output = io.StringIO()
        with patch("sys.stdin", Terminal("1\nexamples/minimal/experiment.toml\ny\n")), \
                contextlib.redirect_stderr(Terminal()), contextlib.redirect_stdout(output):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "completed")

    def test_ace_existing_profile_uses_direct_lifecycle_for_tui_and_run(self):
        benchmark = self.root / "datasets/ace-demo/tasks.json"
        benchmark.parent.mkdir(parents=True)
        shutil.copyfile(self.data, benchmark)  # Loading only; never passed to the ACE evaluator.
        (self.root / "examples/ace-rtl/environment/lifecycle.py").write_text(
            'import os\n'
            'def run(root, *, iterations=None, platform=None):\n'
            '    if os.getcwd() != str(root):\n'
            '        return 2\n'
            '    with (root / "launch.marker").open("a") as stream:\n'
            '        stream.write(str(root) + ":direct\\n")\n'
            '    return int(os.environ.get("LIVE_STATUS", "0"))\n')
        experiment = self.root / "examples/ace-rtl/experiment.toml"

        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with patch("sys.stdin", Terminal("1\nexamples/ace-rtl/experiment.toml\ny\n")), \
                patch("agent_optimizer.cli.collect_plan", return_value={"scope": "plan", "ready": True,
                                                                         "checks": []}), \
                patch("agent_optimizer.cli.run_experiment", side_effect=AssertionError("generic run")), \
                contextlib.redirect_stderr(terminal), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 0, terminal.getvalue())
        with patch.dict(os.environ, {"LIVE_STATUS": "3"}), \
                patch("agent_optimizer.cli.run_experiment", side_effect=AssertionError("generic run")), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["run", str(experiment)]), 3)
        self.assertEqual((self.root / "launch.marker").read_text().splitlines(),
                         [f"{self.root.resolve()}:direct", f"{self.root.resolve()}:direct"])
        self.assertFalse((self.root / "scripts/bootstrap.sh").exists())

    def test_ace_launcher_rejects_a_copied_experiment_instead_of_running_the_fixed_demo(self):
        benchmark = self.root / "datasets/ace-demo/tasks.json"
        benchmark.parent.mkdir(parents=True)
        shutil.copyfile(self.data, benchmark)
        source = self.root / "examples/ace-rtl/experiment.toml"
        copied = source.with_name("changed-experiment.toml")
        shutil.copyfile(source, copied)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["run", str(copied)]), 2)
        self.assertFalse((self.root / "runs").exists())

    def test_ace_run_rejects_output_override_before_launch(self):
        benchmark = self.root / "datasets/ace-demo/tasks.json"
        benchmark.parent.mkdir(parents=True)
        shutil.copyfile(self.data, benchmark)
        (self.root / "examples/ace-rtl/environment/lifecycle.py").write_text(
            'def run(root, *, iterations=None, platform=None):\n'
            '    (root / "launch.marker").write_text("launched")\n'
            '    return 0\n')
        error = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(error):
            self.assertEqual(main(["run", str(self.root / "examples/ace-rtl/experiment.toml"),
                                   "--output", str(self.root / "custom-runs")]), 2)
        self.assertIn("--output", error.getvalue())
        self.assertFalse((self.root / "launch.marker").exists())

    def test_wizard_selects_a_registered_harness_for_the_generated_run(self):
        terminal = io.StringIO()
        answers = iter(["chosen-harness", str(self.agent),
                        "configs/strategy.json", str(self.data),
                        "examples/minimal/evaluator.py:TextFixtureEvaluator", "", "", "1", "y"])

        def answer():
            if "하네스 번호" in terminal.getvalue().splitlines()[-1]:
                return str(sorted(Registry().factories["harnesses"]).index("fixture") + 1)
            return next(answers)

        with patch("builtins.input", side_effect=answer), contextlib.redirect_stderr(terminal):
            arguments = wizard_arguments(self.root)
        self.assertEqual(arguments[arguments.index("--harness") + 1], "fixture")
        self.assertNotIn("--command-json", arguments)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(arguments), 0)
        spec = load_experiment(self.root / "runs/configs/chosen-harness/experiment.toml")
        self.assertEqual(spec["_profiles"][0]["adapter"], "fixture")
        run, summary = run_experiment(spec, Registry(), self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        self.assertTrue((run / "manifest.json").is_file())

    def test_wizard_prompts_follow_language_without_changing_options(self):
        for language, expected in (("ko", "실험 이름:"), ("en", "Experiment name:")):
            with self.subTest(language=language):
                output = io.StringIO()
                with patch.dict(os.environ, {"AGENT_OPT_LANG": language}), \
                        patch("builtins.input", side_effect=EOFError), contextlib.redirect_stderr(output):
                    with self.assertRaises(EOFError):
                        wizard_arguments(self.root)
                self.assertIn(expected, output.getvalue())

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

    def test_wizard_accepts_glob_with_one_real_runtime_harness_file(self):
        # The minimal fixture has one Python runtime scaffold under src/**.
        answers = ["harness-demo", str(self.agent), "src/**", str(self.data),
                   "examples/minimal/evaluator.py:TextFixtureEvaluator", "", "", "5", "1",
                   "{python} {agent_dir}/src/fixture_agent.py {task_dir}", "", "y"]
        with patch("builtins.input", side_effect=answers), contextlib.redirect_stderr(io.StringIO()):
            args = wizard_arguments(self.root)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
        stage = load_experiment(self.root / "runs/configs/harness-demo/experiment.toml")["stages"][0]
        self.assertEqual(stage["optimizer"], "meta_harness")
        self.assertEqual(stage["config"]["file"], "src/fixture_agent.py")

    def test_init_preserves_pinned_git_agent_url_in_manifest(self):
        url = "https://example.invalid/team/agent.git"
        args = ["init", "--project-root", str(self.root), "--agent", url,
                "--revision", "a" * 40, "--name", "remote-demo",
                "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--editable", "configs/strategy.json", "--optimizer", "baseline",
                 "--command-json", '["{python}","{agent_dir}/agent.py","{task_dir}"]', "--yes"]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(args), 0)
        spec = load_experiment(self.root / "runs/configs/remote-demo/experiment.toml")
        self.assertEqual(spec["_agents"][0].source.url, url)
        self.assertEqual(spec["_agents"][0].source.revision, "a" * 40)

    def test_init_resolves_single_editable_glob_to_a_concrete_gepa_target(self):
        args = ["init", "--project-root", str(self.root), "--agent", str(self.agent),
                "--name", "glob-demo", "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--editable", "configs/**", "--optimizer", "gepa",
                 "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]', "--yes"]
        error = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(error):
            self.assertEqual(main(args), 0, error.getvalue())
        spec = load_experiment(self.root / "runs/configs/glob-demo/experiment.toml")
        self.assertEqual(spec["stages"][0]["config"]["file"], "configs/strategy.json")

    def test_init_accepts_agent_argv_with_dash_prefixed_options_as_json(self):
        arguments = ["{python}", "{agent_dir}/src/fixture_agent.py", "--target", "{task_dir}"]
        args = ["init", "--project-root", str(self.root), "--name", "flag-demo",
                "--agent", str(self.agent), "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--optimizer", "baseline", "--editable", "configs/strategy.json",
                "--command-json", json.dumps(arguments), "--yes"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
        profile = load_experiment(self.root / "runs/configs/flag-demo/experiment.toml")["_profiles"][0]
        self.assertEqual(profile["command"], arguments)

    def test_init_command_text_preserves_quoted_and_dash_prefixed_argv(self):
        args = ["init", "--project-root", str(self.root), "--name", "text-command",
                "--agent", str(self.agent), "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--optimizer", "baseline", "--editable", "configs/strategy.json",
                "--command", '{python} "{agent_dir}/src/fixture agent.py" --target {task_dir}', "--yes"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
        profile = load_experiment(self.root / "runs/configs/text-command/experiment.toml")["_profiles"][0]
        self.assertEqual(profile["command"], ["{python}", "{agent_dir}/src/fixture agent.py",
                                              "--target", "{task_dir}"])

    def test_init_opencode_does_not_require_or_write_command(self):
        args = ["init", "--project-root", str(self.root), "--name", "opencode-demo",
                "--agent", str(self.agent), "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--optimizer", "baseline", "--editable", "configs/strategy.json",
                "--harness", "opencode", "--yes"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
        profile = load_experiment(self.root / "runs/configs/opencode-demo/experiment.toml")["_profiles"][0]
        self.assertEqual(profile["adapter"], "opencode")
        self.assertNotIn("command", profile)

    def test_init_rejects_invalid_command_options_before_dataset_preparation(self):
        prefix = ["init", "--project-root", str(self.root), "--agent", str(self.agent),
                  "--dataset", str(self.data), "--editable", "configs/strategy.json", "--yes"]
        for name, options in (("conflict", ["--command", "python agent.py", "--command-json", '["python"]']),
                              ("unclosed", ["--command", "'python agent.py"]),
                              ("empty", ["--command", " "]),
                              ("opencode-input", ["--harness", "opencode", "--command", "python agent.py"])):
            with self.subTest(name=name):
                error = io.StringIO()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(error):
                    self.assertEqual(main([*prefix, "--name", name, *options]), 2)
                self.assertTrue(error.getvalue())
                self.assertFalse((self.root / "runs/configs" / name).exists())

    def test_stage_budget_is_sized_for_selected_tasks_not_entire_downloaded_dataset(self):
        source = self.root / "large.json"
        document = json.loads(self.data.read_text())
        document["tasks"] = [dict(task, id=f"{task['id']}-{index}",
                                  family=f"{task['family']}-{index}")
                             for task in document["tasks"] for index in range(10)]
        source.write_text(json.dumps(document))
        args = ["init", "--project-root", str(self.root), "--name", "sampled",
                "--agent", str(self.agent), "--dataset", str(source),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--optimizer", "gepa", "--max-tasks", "3", "--editable",
                 "configs/strategy.json", "--command-json",
                 '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]', "--yes"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
        spec = load_experiment(self.root / "runs/configs/sampled/experiment.toml")
        self.assertEqual(len(spec["_tasks"]), 3)
        self.assertLess(spec["stages"][0]["max_trials"], 20)

    def test_small_sample_balances_train_validation_and_test(self):
        document = json.loads(self.data.read_text())
        document["tasks"] = [dict(task, id=f"{task['id']}-{index}",
                                  family=f"{task['family']}-{index}")
                             for task in document["tasks"] for index in range(10)]
        sampled = _bounded_tasks(document, 9)
        self.assertEqual({split: sum(task["split"] == split for task in sampled["tasks"])
                          for split in ("train", "validation", "test")},
                         {"train": 3, "validation": 3, "test": 3})

    def test_user_can_bound_trial_and_walltime_before_running(self):
        args = ["init", "--project-root", str(self.root), "--name", "bounded",
                "--agent", str(self.agent), "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--optimizer", "baseline", "--editable", "configs/strategy.json",
                "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]',
                "--max-trials", "12", "--max-wall-time-seconds", "90",
                "--trial-timeout-seconds", "20", "--yes"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
        spec = load_experiment(self.root / "runs/configs/bounded/experiment.toml")
        self.assertEqual(spec["budget"], {"max_trials": 12,
                                          "max_wall_time_seconds": 90,
                                          "trial_timeout_seconds": 20})

    def test_custom_evaluator_metric_is_used_by_objective_and_gepa(self):
        args = ["init", "--project-root", str(self.root), "--name", "custom-metric",
                "--agent", str(self.agent), "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--metric", "latency", "--direction", "minimize",
                "--optimizer", "gepa", "--editable", "configs/strategy.json",
                "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]',
                "--yes"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
        spec = load_experiment(self.root / "runs/configs/custom-metric/experiment.toml")
        self.assertEqual(spec["objective"]["metrics"][0],
                         {"name": "latency", "source": "latency", "direction": "minimize",
                          "aggregate": "mean"})
        self.assertEqual(spec["stages"][0]["config"]["metric"], "latency")
        self.assertEqual(spec["stages"][0]["config"]["direction"], "minimize")

    def test_insufficient_trial_limit_does_not_publish_partial_experiment(self):
        args = ["init", "--project-root", str(self.root), "--name", "too-small",
                "--agent", str(self.agent), "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--optimizer", "baseline", "--editable", "configs/strategy.json",
                "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]',
                "--max-trials", "1", "--yes"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 2)
        self.assertFalse((self.root / "runs/configs/too-small").exists())

    def test_invalid_team_optimizer_config_fails_before_preparing_data(self):
        args = ["init", "--project-root", str(self.root), "--name", "bad-options",
                "--agent", str(self.agent), "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--optimizer", "baseline", "--optimizer-config", "[]",
                "--editable", "configs/strategy.json",
                "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]',
                "--yes"]
        error = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(error):
            self.assertEqual(main(args), 2)
        self.assertIn("optimizer-config", error.getvalue())
        self.assertFalse((self.root / "external").exists())

    def test_structured_optimizer_options_complete_user_flow(self):
        options = {"file_variants": {"include_seeds": True, "variants": [
            {"name": "enable-repair", "files": {"configs/strategy.json": '{"repair": true}'}}
        ]}}
        args = ["init", "--project-root", str(self.root), "--name", "structured-options",
                "--agent", str(self.agent), "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--optimizer", "file_variants", "--editable", "configs/strategy.json",
                "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]',
                "--optimizer-config", json.dumps(options), "--yes"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
        plan = self.root / "runs/configs/structured-options/experiment.toml"
        spec = load_experiment(plan)
        self.assertEqual(spec["stages"][0]["config"]["variants"], options["file_variants"]["variants"])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["doctor", "--plan", str(plan), "--json"]), 0)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["run", str(plan)]), 0)
        run = Path(json.loads(output.getvalue())["run_dir"])
        summary = json.loads((run / "summary.json").read_text())
        self.assertEqual(summary["status"], "completed")
        self.assertTrue(summary["synthetic"])
        self.assertEqual(summary["groups"][0]["baseline"]["metrics"]["solve_rate"], 0)
        self.assertEqual(summary["groups"][0]["selected"][0]["metrics"]["solve_rate"], 1)
        self.assertTrue((run / "report.html").is_file())

    def test_failed_generation_can_retry_without_removing_existing_directory(self):
        args = ["init", "--project-root", str(self.root), "--name", "invalid-once",
                "--agent", str(self.agent), "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--optimizer", "baseline", "--editable", "configs/strategy.json",
                "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]',
                "--yes"]
        bad = [*args, "--optimizer-config", '{"baseline":{"unsupported":null}}']
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(bad), 2)
        self.assertFalse((self.root / "runs/configs/invalid-once").exists())
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)

        existing = self.root / "runs/configs/existing"
        existing.mkdir()
        (existing / "sentinel").write_bytes(b"unchanged")
        args[args.index("invalid-once")] = "existing"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 2)
        self.assertEqual((existing / "sentinel").read_bytes(), b"unchanged")

    def test_multi_dataset_generation_failure_can_retry_without_leaving_first_plan(self):
        config_root = self.root / "runs/configs/multi-retry"
        config_root.mkdir(parents=True)
        (config_root / "sentinel").write_bytes(b"keep")
        second = self.root / "second.json"
        second.write_text("invalid JSON")
        args = ["init", "--project-root", str(self.root), "--name", "multi-retry",
                "--agent", str(self.agent), "--dataset", str(self.data), "--dataset", str(second),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--optimizer", "baseline", "--editable", "configs/strategy.json",
                "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]',
                "--yes"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 2)
        self.assertEqual((config_root / "sentinel").read_bytes(), b"keep")
        self.assertFalse((config_root / "1-tasks").exists())
        self.assertFalse((config_root / "session.json").exists())

        document = json.loads(self.data.read_text())
        document["id"] = "second-dataset"
        second.write_text(json.dumps(document))
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
        prepared = json.loads(output.getvalue())
        self.assertEqual(len(prepared["experiments"]), 2)
        self.assertTrue((config_root / "1-tasks/experiment.toml").is_file())
        self.assertTrue((config_root / "2-second/experiment.toml").is_file())

    def test_generated_optimizer_strings_round_trip_del_character(self):
        value = "repair\x7fversion"
        options = {"file_variants": {"variants": [
            {"name": value, "files": {"configs/strategy.json": '{"repair": true}'}}
        ]}}
        args = ["init", "--project-root", str(self.root), "--name", "special-options",
                "--agent", str(self.agent), "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--optimizer", "file_variants", "--editable", "configs/strategy.json",
                "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]',
                "--optimizer-config", json.dumps(options), "--yes"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
        spec = load_experiment(self.root / "runs/configs/special-options/experiment.toml")
        self.assertEqual(spec["stages"][0]["config"]["variants"][0]["name"], value)

    def test_multi_dataset_output_failure_does_not_leave_dangling_session(self):
        class BrokenOutput:
            def write(self, value):
                raise OSError("output unavailable")

        args = ["init", "--project-root", str(self.root), "--name", "broken-output",
                "--agent", str(self.agent), "--dataset", str(self.data),
                "--dataset", "sample_text", "--evaluator",
                "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--optimizer", "baseline", "--editable", "configs/strategy.json",
                "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]',
                "--yes"]
        with contextlib.redirect_stdout(BrokenOutput()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 2)
        config_root = self.root / "runs/configs/broken-output"
        self.assertFalse((config_root / "session.json").exists())
        self.assertFalse((config_root / "1-tasks").exists())
        self.assertFalse((config_root / "2-sample_text").exists())

        (config_root / "session.json").write_bytes(b"existing session")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 2)
        self.assertEqual((config_root / "session.json").read_bytes(), b"existing session")
        self.assertFalse((config_root / "1-tasks").exists())

    def test_gepa_trial_allowance_tracks_requested_iterations_and_merge(self):
        args = ["init", "--project-root", str(self.root), "--name", "long-search",
                "--agent", str(self.agent), "--dataset", str(self.data),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--optimizer", "gepa",
                "--optimizer-config", '{"gepa":{"iterations":6,"batch_size":1,"merge":true}}',
                "--editable", "configs/strategy.json",
                "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]',
                "--yes"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
        spec = load_experiment(self.root / "runs/configs/long-search/experiment.toml")
        self.assertEqual(spec["stages"][0]["config"]["iterations"], 6)
        self.assertGreaterEqual(spec["stages"][0]["max_trials"], 15)

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
            "'future_eval', "
            "'provenance': {'version': 'fixture'}}\n")
        (team / "harness.py").write_text(
            "from agent_optimizer.harnesses.command import FixtureHarness as Harness\n")
        (team / "optimizer.py").write_text(
            "from agent_optimizer.optimizers.baseline import BaselineOptimizer as Optimizer\n")
        (team / "helper.py").write_text("VERSION = 1\n")
        additions = {"datasets": {"future_set": "experiments/future-team/dataset.py:Provider"},
                     "harnesses": {"future_harness": "experiments/future-team/harness.py:Harness"},
                     "optimizers": {"future_opt": "experiments/future-team/optimizer.py:Optimizer"},
                     "evaluators": {"future_eval": "examples/minimal/evaluator.py:TextFixtureEvaluator"}}
        with patch.dict(PROJECT_COMPONENTS, {kind: {**PROJECT_COMPONENTS[kind], **entries}
                                            for kind, entries in additions.items()}), \
                patch.dict(PROJECT_DEPENDENCIES,
                           {"datasets/future_set": ["experiments/future-team/helper.py"]}), \
                patch("pathlib.Path.cwd", return_value=self.root):
            inventory = io.StringIO()
            with contextlib.redirect_stdout(inventory):
                self.assertEqual(main(["datasets", "list", "--project-root", str(self.root)]), 0)
            self.assertIn("future_set", {item["name"] for item in json.loads(inventory.getvalue())})
            plugins = io.StringIO()
            with contextlib.redirect_stdout(plugins):
                self.assertEqual(main(["plugins", "--project-root", str(self.root)]), 0)
            self.assertIn("future_opt", json.loads(plugins.getvalue())["optimizers"]["implemented"])
            choices = sorted([*PROJECT_COMPONENTS["datasets"]])
            algorithms = sorted([*Registry().factories["optimizers"], "future_opt"])
            answers = ["future-wizard", str(self.agent),
                       "configs/strategy.json", str(choices.index("future_set") + 1),
                       str(algorithms.index("future_opt") + 1),
                       str(sorted([*Registry().factories["harnesses"], "future_harness"])
                           .index("future_harness") + 1), "y"]
            with patch("builtins.input", side_effect=answers), contextlib.redirect_stderr(io.StringIO()):
                wizard = wizard_arguments(self.root)
            self.assertIn("future_set", wizard)
            self.assertIn("future_opt", wizard)
            self.assertEqual(wizard[wizard.index("--harness") + 1], "future_harness")
            self.assertNotIn("--command-json", wizard)
            self.assertNotIn("--extensions", wizard)
            args = ["init", "--project-root", str(self.root), "--agent", str(self.agent),
                    "--name", "future-demo", "--dataset", "future_set", "--harness", "future_harness",
                    "--optimizer", "future_opt", "--editable", "configs/strategy.json", "--yes"]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 0)
            experiment = self.root / "runs/configs/future-demo/experiment.toml"
            spec = load_experiment(experiment)
            self.assertNotIn("extensions", spec)
            self.assertNotIn("future_set", spec.get("plugins", {}).get("datasets", {}))
            self.assertEqual(spec["_benchmark_metadata"]["dataset_provider"], "future_set")
            for action in ("validate", "plan", "run"):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main([action, str(experiment)]), 0)
            root, summary = run_experiment(spec, Registry(), self.root / "runs")
            self.assertEqual(summary["status"], "completed")
            hashes = json.loads((root / "manifest.json").read_text())["plugin_sha256"]
            for reference in ("experiments/future-team/dataset.py:Provider",
                              "experiments/future-team/helper.py", "experiments/future-team/harness.py:Harness",
                              "experiments/future-team/optimizer.py:Optimizer",
                              "examples/minimal/evaluator.py:TextFixtureEvaluator"):
                self.assertIn(reference, hashes)
            self.assertNotIn("extensions_sha256", json.loads((root / "manifest.json").read_text()))
            session_args = [*args, "--dataset", "future_set", "--name", "future-session"]
            session_output = io.StringIO()
            with contextlib.redirect_stdout(session_output):
                self.assertEqual(main(session_args), 0)
            session_path = json.loads(session_output.getvalue())["session"]
            session_output = io.StringIO()
            with contextlib.redirect_stdout(session_output), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["run-session", session_path]), 0)
            self.assertEqual(json.loads(session_output.getvalue())["status"], "completed")

    def test_generated_benchmark_preserves_evaluator_specific_runtime_options(self):
        config_root = self.root / "runs/configs/image-demo"
        data = {"benchmark": str(self.data), "evaluator": "text_fixture",
                "evaluator_config": {"sim_image": "locked-image:v1"},
                "provenance": {"image_id": "sha256:known", "source_revision": "fixed"}}
        file = write_experiment(config_root, agent=self.agent,
                                harness={"command": ["{python}", "{agent_dir}/src/fixture_agent.py",
                                                     "{task_dir}"]},
                                dataset=data, stages=[],
                                plugins={"evaluators": {"text_fixture":
                                        "examples/minimal/evaluator.py:TextFixtureEvaluator"}},
                                dependencies={}, name="image-demo", editable=["configs/strategy.json"])
        spec = load_experiment(file)
        self.assertEqual(spec["evaluator_config"]["sim_image"], "locked-image:v1")
        self.assertEqual(spec["_benchmark_metadata"]["dataset_provenance"]["image_id"], "sha256:known")

    def test_multiple_selected_datasets_get_separate_runs_and_linked_reports(self):
        datasets = []
        for label in ("first", "second"):
            file = self.root / f"{label}.json"
            document = json.loads(self.data.read_text())
            document["id"] = f"custom-{label}"
            file.write_text(json.dumps(document))
            datasets.append(file)
        args = ["init", "--project-root", str(self.root), "--agent", str(self.agent),
                "--name", "comparison", "--dataset", str(datasets[0]),
                "--dataset", str(datasets[1]), "--evaluator",
                "examples/minimal/evaluator.py:TextFixtureEvaluator", "--editable",
                 "configs/strategy.json", "--optimizer", "baseline", "--command-json",
                 '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]', "--yes"]
        init_output = io.StringIO()
        with contextlib.redirect_stdout(init_output):
            self.assertEqual(main(args), 0)
        session = Path(json.loads(init_output.getvalue())["session"])
        self.assertEqual(len(json.loads(session.read_text())["experiments"]), 2)
        run_output, progress = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(run_output), contextlib.redirect_stderr(progress):
            self.assertEqual(main(["run-session", str(session)]), 0)
        report = json.loads(run_output.getvalue())
        self.assertEqual(report["status"], "completed")
        self.assertEqual(len(report["reports"]), 2)
        index = Path(report["index_html"]).read_text()
        self.assertIn("first", index)
        self.assertIn("second", index)
        self.assertIn("서로 다른 채점기의 점수를 직접 비교하거나 순위를 매기지 않습니다.", index)
        self.assertTrue(all(Path(path).is_file() for path in report["reports"]))

    def test_run_session_cli_limits_workers_and_preserves_json_and_reports(self):
        experiment = self.root / "examples/minimal/experiment.toml"
        session = self.root / "session.json"
        session.write_text(json.dumps({"schema_version": 1, "experiments": [
            {"dataset": "same", "experiment": str(experiment)},
            {"dataset": "same", "experiment": str(experiment)}]}))
        output_dir = self.root / "custom-sessions"
        output, progress = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(progress):
            self.assertEqual(main(["run-session", str(session), "--jobs", "2",
                                   "--output", str(output_dir)]), 0)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(len(summary["reports"]), 2)
        self.assertIn("[1/2] same", progress.getvalue())
        self.assertIn("[2/2] same", progress.getvalue())
        self.assertTrue(all(Path(report).is_file() for report in summary["reports"]))
        stored = json.loads((Path(summary["session_dir"]) / "summary.json").read_text())
        self.assertGreater(stored["session_wall_time_seconds"], 0)

    def test_run_session_rejects_zero_jobs_without_creating_output(self):
        session = self.root / "session.json"
        session.write_text(json.dumps({"schema_version": 1, "experiments": [
            {"dataset": str(index), "experiment": "unused.toml"} for index in range(2)]}))
        output = self.root / "should-not-exist"
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["run-session", str(session), "--jobs", "0",
                                   "--output", str(output)]), 2)
        self.assertFalse(output.exists())

    def test_dataset_preparation_progress_never_corrupts_json_stdout(self):
        team = self.root / "experiments" / "loader"
        team.mkdir(parents=True)
        (team / "dataset.py").write_text(
            "from pathlib import Path\nclass Provider:\n"
            "    def describe(self):\n        return {'name': 'team_data'}\n"
            "    def prepare(self, cache, *, offline=False):\n"
            "        print('preparing dataset...')\n"
            "        return {'benchmark': str(Path(__file__).resolve().parents[2] / "
            "'examples/minimal/tasks.json'), 'evaluator': "
                 "'team_eval', 'provenance': {}}\n")
        output, progress = io.StringIO(), io.StringIO()
        with patch.dict(PROJECT_COMPONENTS, {**PROJECT_COMPONENTS,
                        "datasets": {**PROJECT_COMPONENTS["datasets"],
                                     "team_data": "experiments/loader/dataset.py:Provider"},
                        "evaluators": {**PROJECT_COMPONENTS["evaluators"],
                                       "team_eval": "examples/minimal/evaluator.py:TextFixtureEvaluator"}}), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(progress):
            self.assertEqual(main(["datasets", "prepare", "team_data", "--project-root",
                                   str(self.root)]), 0)
        self.assertEqual(json.loads(output.getvalue())["evaluator"], "team_eval")
        self.assertIn("preparing dataset", progress.getvalue())
        self.assertIn("dataset=team_data", progress.getvalue())
        self.assertIn("complete", progress.getvalue())

    def test_removed_extensions_option_fails_before_asset_preparation(self):
        args = ["init", "--project-root", str(self.root), "--agent", str(self.agent),
                "--dataset", "cvdp", "--extensions", "unused.toml", "--yes"]
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 2)
        self.assertFalse((self.root / "external").exists())

    def test_session_preserves_other_dataset_report_when_one_config_fails(self):
        first, second = self.root / "broken-a.json", self.root / "good-b.json"
        first.write_text(self.data.read_text())
        second.write_text(self.data.read_text())
        args = ["init", "--project-root", str(self.root), "--name", "partial-demo",
                "--agent", str(self.agent), "--dataset", str(first), "--dataset", str(second),
                "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                "--optimizer", "baseline", "--editable", "configs/strategy.json",
                 "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]', "--yes"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
        session = Path(json.loads(output.getvalue())["session"])
        entries = json.loads(session.read_text())["experiments"]
        broken = Path(entries[0]["experiment"])
        broken.write_text(broken.read_text().replace('schema_version = 1', 'schema_version = 999', 1))
        result, progress = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(result), contextlib.redirect_stderr(progress):
            self.assertEqual(main(["run-session", str(session)]), 3)
        summary = json.loads(result.getvalue())
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(len(summary["reports"]), 1)
        self.assertTrue(Path(summary["reports"][0]).is_file())
        self.assertIn("broken-a", Path(summary["index_html"]).read_text())

    def test_session_workers_overlap_but_jobs_one_runs_sequentially(self):
        timing_dir = self.root / "timings"
        timing_dir.mkdir()
        evaluator = self.root / "examples/minimal/slow_evaluator.py"
        evaluator.write_text(
            "import json\nimport os\nimport time\nfrom pathlib import Path\n"
            "from agent_optimizer.contracts import Evaluation\n"
            f"DIRECTORY = Path({str(timing_dir)!r})\n"
            "class SlowEvaluator:\n"
            "    def __init__(self, settings):\n        pass\n"
            "    def evaluate(self, task, output_dir, timeout_seconds):\n"
            "        marker = DIRECTORY / f'{os.getpid()}.json'\n"
            "        if not marker.exists():\n"
            "            started = time.monotonic()\n"
            "            time.sleep(0.25)\n"
            "            marker.write_text(json.dumps({'start': started, 'end': time.monotonic()}))\n"
            "        return Evaluation('passed', {'passed': 1.0})\n", encoding="utf-8")
        experiment = self.root / "examples/minimal/slow-experiment.toml"
        experiment.write_text((self.root / "examples/minimal/experiment.toml").read_text()
                              .replace('evaluator = "text_fixture"', 'evaluator = "slow_fixture"')
                              .replace('text_fixture = "examples/minimal/evaluator.py:TextFixtureEvaluator"',
                                       'slow_fixture = "examples/minimal/slow_evaluator.py:SlowEvaluator"'),
                              encoding="utf-8")
        items = [{"dataset": "same", "experiment": str(experiment)} for _ in range(2)]

        for jobs, overlap in ((2, True), (1, False)):
            with self.subTest(jobs=jobs):
                with SessionProgress(["same", "same"], stream=io.StringIO()) as progress:
                    entries = run_session(items, self.root / f"session-{jobs}", jobs=jobs, progress=progress)
                self.assertEqual([entry["status"] for entry in entries], ["completed", "completed"], entries)
                self.assertEqual(len({entry["report"] for entry in entries}), 2)
                self.assertTrue(all((self.root / f"session-{jobs}" / entry["report"]).is_file()
                                    for entry in entries))
                spans = sorted([json.loads(path.read_text()) for path in timing_dir.glob("*.json")],
                               key=lambda row: row["start"])
                self.assertEqual(len(spans), 2)
                self.assertEqual(spans[1]["start"] < spans[0]["end"], overlap)
                for marker in timing_dir.glob("*.json"):
                    marker.unlink()

    def test_session_event_projection_drops_private_feedback_and_artifacts(self):
        public = _project_event({"event": "trial_completed", "task_id": "known", "phase": "evaluation",
                                 "feedback": "private-answer", "artifacts": {"secret": "private-answer"},
                                 "metrics": {"task_wall_time_seconds": 2.0, "answer": "private-answer"}})
        self.assertEqual(public, {"event": "trial_completed", "task_id": "known", "phase": "evaluation",
                                  "metrics": {"task_wall_time_seconds": 2.0}})

    def test_session_worker_failure_keeps_other_report_and_input_order(self):
        valid = self.root / "examples/minimal/experiment.toml"
        broken = self.root / "examples/minimal/broken.toml"
        broken.write_text(valid.read_text().replace("schema_version = 1", "schema_version = 999", 1))
        items = [{"dataset": "broken", "experiment": str(broken)},
                 {"dataset": "working", "experiment": str(valid)}]
        session_root = self.root / "session-failure"
        with SessionProgress(["broken", "working"], stream=io.StringIO()) as progress:
            entries = run_session(items, session_root, jobs=2, progress=progress)
        self.assertEqual([(row["dataset"], row["status"]) for row in entries],
                         [("broken", "error"), ("working", "completed")])
        self.assertIsNone(entries[0]["report"])
        self.assertTrue((session_root / entries[1]["report"]).is_file())

    def test_session_interrupt_stops_running_workers_and_marks_pending(self):
        experiment = self.root / "examples/minimal/experiment.toml"
        items = [{"dataset": str(i), "experiment": str(experiment)} for i in range(3)]
        session_root = self.root / "session-interrupted"
        existing = {process.pid for process in multiprocessing.active_children()}
        progress = SessionProgress([item["dataset"] for item in items], stream=io.StringIO())
        with progress, patch.object(progress, "event", side_effect=KeyboardInterrupt):
            with self.assertRaises(SessionInterrupted) as raised:
                run_session(items, session_root, jobs=2, progress=progress)
        self.assertEqual([entry["status"] for entry in raised.exception.entries],
                         ["interrupted", "interrupted", "interrupted"])
        self.assertFalse((session_root / "runs/03").exists())
        self.assertEqual({process.pid for process in multiprocessing.active_children()}, existing)

    def test_session_interrupt_stops_running_agent_child_process(self):
        marker = self.root / "agent-child.pid"
        agent_file = self.root / "examples/minimal/agents/solo/src/fixture_agent.py"
        agent_file.write_text("import os\nimport time\nfrom pathlib import Path\n"
                              f"Path({str(marker)!r}).write_text(str(os.getpid()))\n"
                              "time.sleep(30)\n", encoding="utf-8")
        experiment = self.root / "examples/minimal/experiment.toml"
        items = [{"dataset": str(index), "experiment": str(experiment)} for index in range(2)]
        progress = SessionProgress(["first", "second"], stream=io.StringIO())

        def interrupt_after_agent_launch(index, event):
            if event["event"] != "agent_started":
                return
            deadline = time.monotonic() + 3
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists(), "agent child never started")
            raise KeyboardInterrupt

        try:
            with progress, patch.object(progress, "event", side_effect=interrupt_after_agent_launch):
                with self.assertRaises(SessionInterrupted):
                    run_session(items, self.root / "session-agent-interrupt", jobs=1, progress=progress)
            child_pid = int(marker.read_text())
            for _ in range(30):
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.05)
            else:
                self.fail("interrupted session left a running Agent process")
        finally:
            if marker.exists():
                try:
                    os.killpg(int(marker.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    unittest.main()
