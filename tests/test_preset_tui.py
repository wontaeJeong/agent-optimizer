"""선택형 ACE 설정이 기본 예제를 바꾸지 않고 실제 stage를 지정하는지 검사한다."""
import json
import io
import copy
import os
import unittest
from contextlib import redirect_stderr
from dataclasses import replace
from unittest.mock import patch
from types import SimpleNamespace

from agent_optimizer.cli import _launch_existing, main
from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.registry import Registry
from agent_optimizer.registry import PROJECT_COMPONENTS
from agent_optimizer.readiness import collect_plan
from support import ROOT, test_project


class PresetConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)
        target = self.root / "datasets/ace-demo/tasks.json"
        target.parent.mkdir(parents=True)
        source = json.loads((ROOT / "examples/minimal/tasks.json").read_text())
        source["tasks"] = source["tasks"][:2]
        target.write_text(json.dumps(source))

    def test_gepa_and_meta_create_independent_run_owned_experiments(self):
        from agent_optimizer.preset_tui import write_ace_selection

        original = (self.root / "examples/ace-rtl/experiment.toml").read_bytes()
        gepa = load_experiment(write_ace_selection(self.root, "gepa"))
        meta = load_experiment(write_ace_selection(self.root, "meta_harness"))
        self.assertEqual((self.root / "examples/ace-rtl/experiment.toml").read_bytes(), original)
        self.assertEqual(gepa["_profiles"][0]["id"], "ace-opencode")
        self.assertEqual(gepa["_profiles"][0]["adapter"], "ace_opencode")
        self.assertEqual(gepa["stages"][0]["optimizer"], "gepa")
        self.assertEqual(gepa["stages"][0]["config"], {
            "file": "skills/ace-rtl/references/role-guidance.md", "metric": "passed",
            "direction": "maximize", "iterations": 3, "batch_size": 4, "merge": False})
        self.assertEqual(meta["stages"][0]["optimizer"], "meta_harness")
        scaffold = "skills/ace-rtl/scripts/agent_opt_scaffold.py"
        self.assertEqual(meta["stages"][0]["config"]["file"], scaffold)
        self.assertEqual(meta["stages"][0]["config"]["required_symbol"], "prepare_task")
        self.assertIn(scaffold, meta["_agents"][0].editable)
        self.assertIn("runpy.run_path", " ".join(meta["_agents"][0].build))
        self.assertEqual(meta["budget"]["max_trials"], 9)
        self.assertEqual(gepa["budget"]["max_trials"], 9)
        self.assertEqual(meta["final_test"], False)
        self.assertEqual(meta["evaluator"], "cvdp")
        self.assertEqual(meta["evaluator_config"]["repo"],
                         str(self.root.resolve() / "external/cvdp_benchmark"))
        self.assertEqual(meta["evaluator_config"]["python"],
                         str(self.root.resolve() / "external/cvdp-venv/bin/python"))
        self.assertEqual((self.root / meta["candidate_seed_files"][scaffold]).is_file(), True)
        self.assertNotEqual(meta["_source"], gepa["_source"])

    def test_missing_ace_tasks_do_not_trigger_preparation(self):
        from agent_optimizer.preset_tui import write_ace_selection
        (self.root / "datasets/ace-demo/tasks.json").unlink()
        with self.assertRaisesRegex(Exception, "준비|tasks"):
            write_ace_selection(self.root, "gepa")
        self.assertFalse((self.root / "runs").exists())

    def test_generated_ace_config_runs_through_selected_runner(self):
        from agent_optimizer.preset_tui import write_ace_selection
        spec = load_experiment(write_ace_selection(self.root, "gepa"))
        self.assertIsNone(_launch_existing(spec, Registry()))

    def test_malformed_selected_preset_is_a_configuration_error(self):
        from agent_optimizer.preset_tui import write_ace_selection
        spec = load_experiment(write_ace_selection(self.root, "gepa"))
        spec["preset_selection"] = "not-a-mapping"
        with self.assertRaisesRegex(ConfigurationError, "선택형 설정"):
            _launch_existing(spec, Registry())

    def test_selected_preset_cannot_claim_different_source_or_evaluator(self):
        from agent_optimizer.preset_tui import write_ace_selection
        spec = load_experiment(write_ace_selection(self.root, "gepa"))

        def changed_source(value):
            value["_agents"][0] = replace(value["_agents"][0], source=replace(
                value["_agents"][0].source, revision="0" * 40))

        for change in (lambda value: value.update(evaluator="sample_eval"),
                       lambda value: value.update(benchmark="examples/minimal/tasks.json"),
                       lambda value: value["_profiles"][0].update(adapter="command"),
                       lambda value: value["budget"].update(max_trials=8), changed_source):
            tampered = copy.deepcopy(spec)
            change(tampered)
            with self.subTest(change=change), self.assertRaisesRegex(ConfigurationError, "선택형 설정"):
                _launch_existing(tampered, Registry())

    def test_selected_meta_rejects_tampered_seed_and_objective(self):
        from agent_optimizer.preset_tui import ACE_SCAFFOLD, write_ace_selection
        spec = load_experiment(write_ace_selection(self.root, "meta_harness"))
        changed = copy.deepcopy(spec)
        changed["objective"]["metrics"][0]["source"] = "task_wall_time_seconds"
        with self.assertRaisesRegex(ConfigurationError, "선택형 설정"):
            _launch_existing(changed, Registry())
        (self.root / spec["candidate_seed_files"][ACE_SCAFFOLD]).write_text("def prepare_task(task_dir): pass\n")
        with self.assertRaisesRegex(ConfigurationError, "선택형 설정"):
            _launch_existing(spec, Registry())

    def test_installed_preset_verifies_pin_before_importing_lifecycle(self):
        from agent_optimizer.preset_tui import run_ace_selection, write_ace_selection
        target = write_ace_selection(self.root, "gepa")
        (self.root / ".agent-opt-source").unlink()
        lifecycle = self.root / "examples/ace-rtl/environment/lifecycle.py"
        sentinel = self.root / "ran-unverified.txt"
        lifecycle.write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\n"
                             + lifecycle.read_text())
        with self.assertRaisesRegex((ConfigurationError, UnavailableError), "준비"):
            run_ace_selection(target)
        self.assertFalse(sentinel.exists())

    def test_selected_opencode_provider_uses_matching_image_configuration(self):
        from agent_optimizer.preset_tui import run_ace_selection, write_ace_selection
        target = write_ace_selection(self.root, "gepa")
        inspection = {"ready": True, "checks": [], "platform": "linux/arm64",
                      "sim_image": "locked-sim-image",
                      "lock": {"images": {"agent": {"id": "locked-agent-image"}}}}
        for selector, extra, config in (("compatible/fixture", {},
                                         "/opt/agent-optimizer/compatible.json"),
                                        ("openrouter/free-model", {"OPENROUTER_API_KEY": "fixture-token"},
                                         "/opt/agent-optimizer/opencode.json")):
            with self.subTest(selector=selector):
                seen = []

                def run(spec, registry, *, on_event):
                    seen.append((os.environ.get("OPENCODE_CONFIG"),
                                 spec["_profiles"][0]["runtime"]["image"]))
                    return self.root / "runs/example", {"status": "completed", "trials_used": 0}

                env = {"AGENT_OPT_MODEL": selector, "AGENT_OPT_MODEL_BASE_URL": "http://localhost:1234/v1",
                       "AGENT_OPT_MODEL_API_KEY": "fixture-key", "AGENT_OPT_MODEL_ID": "fixture", **extra}
                with patch.dict(os.environ, env, clear=True), \
                     patch("agent_optimizer.preset_tui._lifecycle",
                           return_value=SimpleNamespace(inspect=lambda root: inspection)), \
                     patch("agent_optimizer.readiness.collect_plan",
                           return_value={"ready": True, "checks": []}), \
                     patch("agent_optimizer.runner.run_experiment", side_effect=run), \
                     patch("sys.stdout", io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(run_ace_selection(target), 0)
                self.assertEqual(seen, [(config, "locked-agent-image")])

    def test_selected_opencode_rejects_missing_key_or_mismatched_compatible_model(self):
        from agent_optimizer.preset_tui import run_ace_selection, write_ace_selection
        target = write_ace_selection(self.root, "gepa")
        for model, model_id, extra in (("openrouter/free", "fixture", {}),
                                       ("compatible/different", "fixture",
                                        {"OPENROUTER_API_KEY": "fixture-key"})):
            with self.subTest(model=model), patch.dict(os.environ, {
                    "AGENT_OPT_MODEL": model, "AGENT_OPT_MODEL_ID": model_id,
                    "AGENT_OPT_MODEL_BASE_URL": "http://localhost:1234/v1",
                    "AGENT_OPT_MODEL_API_KEY": "fixture-key", **extra}, clear=True), \
                 patch("agent_optimizer.preset_tui._lifecycle",
                       side_effect=AssertionError("invalid model must not inspect assets")):
                with self.assertRaisesRegex((ConfigurationError, UnavailableError),
                                            "OPENROUTER_API_KEY|일치"):
                    run_ace_selection(target)

    def test_noninteractive_run_uses_same_selected_lifecycle(self):
        from agent_optimizer.preset_tui import write_ace_selection
        target = write_ace_selection(self.root, "meta_harness")
        with patch("agent_optimizer.preset_tui.run_ace_selection", return_value=3) as run:
            self.assertEqual(main(["run", str(target)]), 3)
        run.assert_called_once_with(target)

    def test_existing_tui_rerun_uses_selected_lifecycle(self):
        from agent_optimizer.preset_tui import write_ace_selection
        target = write_ace_selection(self.root, "meta_harness")

        class Terminal(io.StringIO):
            def isatty(self):
                return True

        with patch("sys.stdin.isatty", return_value=True), \
             patch("agent_optimizer.preset_tui.select_four", return_value=("existing", "", "", "")), \
             patch("builtins.input", side_effect=[str(target), "y"]), \
             patch("agent_optimizer.cli._tui_model_environment", return_value={}), \
             patch("agent_optimizer.cli.collect_plan", return_value={"ready": True, "checks": []}), \
             patch("agent_optimizer.preset_tui.run_ace_selection", return_value=3) as run, \
             redirect_stderr(Terminal()):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 3)
        run.assert_called_once_with(target.resolve())

    def test_plan_diagnoses_missing_active_scaffold_before_any_trial(self):
        from agent_optimizer.preset_tui import write_ace_selection, ACE_SCAFFOLD
        target = write_ace_selection(self.root, "meta_harness")
        spec = load_experiment(target)
        (self.root / spec["candidate_seed_files"][ACE_SCAFFOLD]).unlink()
        report = collect_plan(target, Registry())
        self.assertIn("candidate.seed", {row["id"] for row in report["checks"]
                                        if row["status"] != "ok"})

    def test_synthetic_agent_preset_runs_with_its_explicit_fixture_dataset(self):
        from agent_optimizer.preset_tui import write_sample_selection
        target = write_sample_selection(self.root, "rtl-solo", "file_variants")
        spec = load_experiment(target)
        self.assertEqual(spec["_agents"][0].id, "rtl-solo")
        self.assertEqual(spec["_profiles"][0]["adapter"], "fixture")
        self.assertEqual(spec["evaluator"], "sample_eval")
        self.assertEqual(spec["stages"][0]["optimizer"], "file_variants")
        self.assertEqual(spec["budget"]["max_trials"], 4)
        output = io.StringIO()
        with patch("sys.stdout", output), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["run", str(target)]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "completed")


class PresetNavigationTests(unittest.TestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)

    def test_non_tty_points_to_noninteractive_init_and_run(self):
        terminal = io.StringIO()
        with patch("sys.stdin.isatty", return_value=False), redirect_stderr(terminal):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
        self.assertIn("agent-opt init", terminal.getvalue())
        self.assertIn("agent-opt run", terminal.getvalue())

    def test_tui_opens_preset_without_numbered_start_menu(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        screen = Terminal()
        with patch("sys.stdin.isatty", return_value=True), \
             patch("agent_optimizer.preset_tui.select_four",
                   return_value=("ace-rtl", "ace-opencode", "baseline", "cvdp")), \
             patch("builtins.input", side_effect=["n"]), redirect_stderr(screen):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
        self.assertIn("준비하고 실행할까요?", screen.getvalue())
        self.assertNotIn("선택 [5/1/2/3/4]", screen.getvalue())

    def test_escaping_preset_opens_previous_menu_and_history(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        screen = Terminal()
        with patch("sys.stdin.isatty", return_value=True), \
             patch("agent_optimizer.preset_tui.select_four", return_value=None) as preset, \
             patch("builtins.input", side_effect=["4"]), \
             patch("agent_optimizer.cli._tui_run_history", return_value=0), \
             redirect_stderr(screen):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 0)
        preset.assert_called_once()
        self.assertIn("선택 [5/1/2/3/4]", screen.getvalue())

    def test_four_explicit_choices_are_read_only_and_go_back_preserves_agent(self):
        from agent_optimizer.preset_tui import select_four

        visits = []
        answers = iter([0, 0, None, 0, 1, 0])

        def choose(title, options):
            visits.append((title, [row[0] for row in options]))
            return next(answers)

        result = select_four(self.root, choose=choose)
        self.assertEqual(result, ("ace-rtl", "ace-opencode", "meta_harness", "cvdp"))
        self.assertEqual([v[0] for v in visits],
                         ["Agent", "Harness", "Optimizer", "Harness", "Optimizer", "Dataset"])
        self.assertFalse((self.root / "runs").exists())

    def test_synthetic_agent_has_explicit_fixture_and_dataset_in_same_flow(self):
        from agent_optimizer.preset_tui import select_four

        def choose(title, options):
            chosen = {"Agent": "rtl-solo", "Harness": "Fixture", "Optimizer": "Baseline",
                      "Dataset": "sample_text"}[title]
            return [row[0] for row in options].index(chosen)

        self.assertEqual(select_four(self.root, choose=choose),
                         ("rtl-solo", "fixture", "baseline", "sample_text"))
        self.assertFalse((self.root / "runs").exists())

    def test_each_component_offers_an_advanced_or_existing_file_route(self):
        from agent_optimizer.preset_tui import select_four

        for target in ("Harness", "Optimizer", "Dataset"):
            with self.subTest(target=target):
                def choose(title, options):
                    if title == target:
                        return next(index for index, row in enumerate(options)
                                    if row[0] == f"내 {title} 연결하기"
                                    or title == "Dataset" and "tasks.json" in row[0])
                    return 0

                self.assertEqual(select_four(self.root, choose=choose)[0], "custom")
        self.assertFalse((self.root / "runs").exists())

    def test_registered_team_optimizer_is_visible_without_importing_its_file(self):
        from agent_optimizer.preset_tui import select_four

        seen = []

        def choose(title, options):
            if title == "Optimizer":
                seen.extend(row[0] for row in options)
            return 0

        with patch.dict(PROJECT_COMPONENTS["optimizers"],
                        {"team_example": "experiments/sample-team/optimizer.py:Optimizer"}):
            self.assertEqual(select_four(self.root, choose=choose)[0], "ace-rtl")
        self.assertIn("team_example", seen)

    def test_backtracking_keeps_focus_and_agent_change_invalidates_following_choices(self):
        from agent_optimizer.preset_tui import choose_preset, select_four
        self.assertEqual(choose_preset("Agent", [("ACE", "a", True), ("fixture", "b", True)],
                                       initial=1, read_key=lambda: "enter"), 1)
        keys = iter(["rtl-solo", 0, 0, None, None, None, "ACE-RTL", 0, 0, 0])

        def choose(title, options):
            selection = next(keys)
            if title == "Agent":
                return next(index for index, row in enumerate(options) if row[0] == selection)
            return selection

        self.assertEqual(select_four(self.root, choose=choose),
                         ("ace-rtl", "ace-opencode", "gepa", "cvdp"))

    def test_confirmation_back_reopens_dataset_with_previous_choices(self):
        from agent_optimizer.preset_tui import select_four
        visited = []
        result = select_four(self.root,
                             choose=lambda title, options: visited.append(title) or 0,
                             initial=("ace-rtl", "ace-opencode", "gepa", "cvdp"), start_page=3)
        self.assertEqual(result, ("ace-rtl", "ace-opencode", "gepa", "cvdp"))
        self.assertEqual(visited, ["Dataset"])

    def test_final_back_returns_to_selection_without_preparing(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        selections = [("ace-rtl", "ace-opencode", "gepa", "cvdp"),
                      ("ace-rtl", "ace-opencode", "meta_harness", "cvdp")]
        with patch("sys.stdin.isatty", return_value=True), \
             patch("agent_optimizer.preset_tui.select_four", side_effect=selections) as chooser, \
             patch("builtins.input", side_effect=["b", "n"]), \
             redirect_stderr(Terminal()):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
        self.assertEqual(chooser.call_count, 2)
        self.assertEqual(chooser.call_args.kwargs["start_page"], 3)
        self.assertFalse((self.root / "runs").exists())

    def test_focus_updates_explanation_before_selection_without_preparing(self):
        from agent_optimizer.preset_tui import choose_preset

        observed = io.StringIO()
        keys = iter(["down", "up", "enter"])
        options = [("GEPA", "역할 안내 수정", True),
                   ("Meta-Harness", "활성 Python 실행", True)]
        with redirect_stderr(observed), patch("agent_optimizer.preset_tui.shutil.get_terminal_size",
                                               return_value=__import__("os").terminal_size((96, 24))):
            self.assertEqual(choose_preset("Optimizer", options, read_key=lambda: next(keys)), 0)
        frames = observed.getvalue()
        self.assertLess(frames.index("역할 안내 수정"), frames.index("활성 Python 실행"))
        self.assertGreater(frames.count("역할 안내 수정"), 1)

    def test_wide_terminal_shows_focused_description_beside_option(self):
        from agent_optimizer.preset_tui import choose_preset
        display = io.StringIO()
        with redirect_stderr(display), patch("agent_optimizer.preset_tui.shutil.get_terminal_size",
                                             return_value=os.terminal_size((110, 24))):
            self.assertEqual(choose_preset("Optimizer", [("GEPA", "role-guidance.md 수정", True)],
                                           read_key=lambda: "enter"), 0)
        self.assertTrue(any(line.lstrip().startswith("> GEPA") and "role-guidance.md" in line
                            for line in display.getvalue().splitlines()))

    def test_incompatible_focus_explains_reason_and_escape_cancels(self):
        from agent_optimizer.preset_tui import choose_preset

        observed = io.StringIO()
        keys = iter(["down", "enter", "escape"])
        with redirect_stderr(observed):
            self.assertIsNone(choose_preset("Harness", [("OpenCode", "선택 가능", True),
                                                      ("Codex", "미구현 adapter", False)],
                                            read_key=lambda: next(keys)))
        self.assertIn("미구현 adapter", observed.getvalue())

    def test_narrow_screen_keeps_description_and_keyboard_hints(self):
        from agent_optimizer.preset_tui import choose_preset

        observed = io.StringIO()
        with redirect_stderr(observed), patch("agent_optimizer.preset_tui.shutil.get_terminal_size",
                                               return_value=__import__("os").terminal_size((42, 24))):
            self.assertEqual(choose_preset("Dataset", [("CVDP", "공식 평가", True)],
                                           read_key=lambda: "enter"), 0)
        self.assertIn("공식 평가", observed.getvalue())
        self.assertIn("Esc", observed.getvalue())

    def test_agent_screen_explains_escape_opens_previous_menu(self):
        from agent_optimizer.preset_tui import choose_preset
        screen = io.StringIO()
        with redirect_stderr(screen):
            self.assertIsNone(choose_preset("Agent", [("ACE-RTL", "선택", True)],
                                            read_key=lambda: "escape"))
        self.assertIn("Esc 메뉴", screen.getvalue())

    def test_english_navigation_translates_status_and_keys(self):
        from agent_optimizer.preset_tui import choose_preset
        observed = io.StringIO()
        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}), redirect_stderr(observed):
            self.assertEqual(choose_preset("Dataset", [("CVDP", "Official evaluation", True)],
                                           read_key=lambda: "enter"), 0)
        self.assertIn("Available", observed.getvalue())
        self.assertIn("Navigate", observed.getvalue())

    def test_navigation_distinguishes_missing_assets_from_unimplemented(self):
        from agent_optimizer.preset_tui import choose_preset
        output = io.StringIO()
        keys = iter(["down", "escape"])
        with redirect_stderr(output):
            self.assertIsNone(choose_preset("Harness", [("OpenCode", "설정 검사 예정", True, "자산 준비 필요"),
                                                       ("Codex", "등록 ID 없음", False, "미구현")],
                                            read_key=lambda: next(keys)))
        self.assertIn("자산 준비 필요", output.getvalue())
        self.assertIn("미구현", output.getvalue())

    def test_confirmation_cancel_does_not_prepare_or_write(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with patch("sys.stdin.isatty", return_value=True), \
             patch("agent_optimizer.preset_tui.select_four",
                   return_value=("ace-rtl", "ace-opencode", "gepa", "cvdp")), \
             patch("builtins.input", side_effect=["n"]), \
             redirect_stderr(terminal):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
        self.assertFalse((self.root / "runs").exists())
        self.assertIn("role-guidance.md", terminal.getvalue())
        self.assertIn("9 trial", terminal.getvalue())

    def test_english_confirmation_shows_distinct_model_roles_without_key_values(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en", "AGENT_OPT_MODEL_API_KEY": "never-show-me"}), \
             patch("sys.stdin.isatty", return_value=True), \
             patch("agent_optimizer.preset_tui.select_four",
                   return_value=("ace-rtl", "ace-opencode", "meta_harness", "cvdp")), \
             patch("builtins.input", side_effect=["n"]), redirect_stderr(terminal):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
        self.assertIn("Agent model", terminal.getvalue())
        self.assertIn("Optimizer model", terminal.getvalue())
        self.assertNotIn("never-show-me", terminal.getvalue())

    def test_confirmation_marks_optimizer_url_and_model_id_configuration_separately(self):
        from agent_optimizer.cli import _run_ace_selection
        screen = io.StringIO()
        with patch.dict(os.environ, {"AGENT_OPT_MODEL_BASE_URL": "",
                                          "AGENT_OPT_MODEL_ID": "fixture-id",
                                          "AGENT_OPT_MODEL_API_KEY": "fixture-secret"}), \
             patch("builtins.input", return_value="n"), redirect_stderr(screen):
            self.assertEqual(_run_ace_selection(self.root, "gepa"), 2)
        self.assertIn("AGENT_OPT_MODEL_BASE_URL: 입력 필요", screen.getvalue())
        self.assertIn("AGENT_OPT_MODEL_ID: 설정됨", screen.getvalue())
        self.assertNotIn("fixture-secret", screen.getvalue())

    def test_confirmation_shows_agent_provider_key_requirement_without_value(self):
        from agent_optimizer.cli import _run_ace_selection
        screen = io.StringIO()
        with patch.dict(os.environ, {"AGENT_OPT_MODEL": "openrouter/free",
                                          "OPENROUTER_API_KEY": ""}), \
             patch("builtins.input", return_value="n"), redirect_stderr(screen):
            self.assertEqual(_run_ace_selection(self.root, "gepa"), 2)
        self.assertIn("OPENROUTER_API_KEY: 입력 필요", screen.getvalue())

    def test_ace_profile_requests_independent_agent_model_selector(self):
        from agent_optimizer.cli import _tui_model_environment
        from agent_optimizer.preset_tui import write_ace_selection
        target = self.root / "datasets/ace-demo/tasks.json"
        target.parent.mkdir(parents=True)
        document = json.loads((ROOT / "examples/minimal/tasks.json").read_text())
        document["tasks"] = document["tasks"][:2]
        target.write_text(json.dumps(document))
        spec = load_experiment(write_ace_selection(self.root, "gepa"))
        with patch("agent_optimizer.model_input.ensure_model_selector",
                   side_effect=lambda env, key: {**env, key: "provider/model"}) as selector, \
             patch("agent_optimizer.model_input.ensure_model_api", side_effect=lambda env: env):
            result = _tui_model_environment(spec, {})
        selector.assert_called_once()
        self.assertEqual(result["AGENT_OPT_MODEL"], "provider/model")

    def test_missing_ace_model_selector_prompts_instead_of_crashing(self):
        from agent_optimizer.model_input import ensure_model_selector
        with patch("builtins.input", return_value="compatible/model"), redirect_stderr(io.StringIO()):
            self.assertEqual(ensure_model_selector({}, "AGENT_OPT_MODEL")["AGENT_OPT_MODEL"],
                             "compatible/model")

    def test_bare_ace_model_id_uses_compatible_api_after_confirming_model_change(self):
        from agent_optimizer.cli import _tui_model_environment
        spec = {"_profiles": [{"adapter": "ace_opencode", "model_env": "AGENT_OPT_MODEL"}],
                "preset_selection": {"agent": "ace-rtl"},
                "stages": [{"optimizer": "gepa"}]}
        env = {"AGENT_OPT_MODEL_BASE_URL": "https://example.invalid/v1",
               "AGENT_OPT_MODEL_API_KEY": "fixture-secret", "AGENT_OPT_MODEL_ID": "glm5.3-flash"}
        with patch("builtins.input", side_effect=["deepseek-flash", "y"]), \
             redirect_stderr(io.StringIO()):
            staged = _tui_model_environment(spec, env)
        self.assertEqual(staged["AGENT_OPT_MODEL"], "compatible/deepseek-flash")
        self.assertEqual(staged["AGENT_OPT_MODEL_ID"], "deepseek-flash")
        self.assertEqual(env["AGENT_OPT_MODEL_ID"], "glm5.3-flash")

    def test_declined_ace_model_change_does_not_prepare_assets(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        screen = Terminal()
        env = {"AGENT_OPT_MODEL": "", "AGENT_OPT_MODEL_BASE_URL": "https://example.invalid/v1",
               "AGENT_OPT_MODEL_API_KEY": "fixture-secret", "AGENT_OPT_MODEL_ID": "glm5.3-flash"}
        with patch.dict(os.environ, env), patch("sys.stdin.isatty", return_value=True), \
             patch("agent_optimizer.preset_tui.select_four",
                   return_value=("ace-rtl", "ace-opencode", "gepa", "cvdp")), \
             patch("agent_optimizer.preset_tui.prepare_ace_selection",
                   side_effect=AssertionError("model must be checked before preparation")), \
             patch("builtins.input", side_effect=["y", "deepseek-flash", "n"]), \
             redirect_stderr(screen):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
        self.assertIn("AGENT_OPT_MODEL_ID", screen.getvalue())

    def test_ace_baseline_does_not_request_optimizer_api(self):
        from agent_optimizer.cli import _tui_model_environment
        from agent_optimizer.preset_tui import write_ace_selection
        target = self.root / "datasets/ace-demo/tasks.json"
        target.parent.mkdir(parents=True)
        tasks = json.loads((ROOT / "examples/minimal/tasks.json").read_text())
        tasks["tasks"] = tasks["tasks"][:2]
        target.write_text(json.dumps(tasks))
        spec = load_experiment(write_ace_selection(self.root, "baseline"))
        with patch("agent_optimizer.model_input.ensure_model_api",
                   side_effect=AssertionError("baseline has no optimizer API")), \
             patch("agent_optimizer.model_input.ensure_model_selector",
                   side_effect=lambda env, key: {**env, key: "provider/model"}):
            self.assertEqual(_tui_model_environment(spec, {})["AGENT_OPT_MODEL"], "provider/model")

    def test_ace_baseline_compatible_agent_requests_provider_api(self):
        from agent_optimizer.cli import _tui_model_environment
        from agent_optimizer.preset_tui import write_ace_selection
        target = self.root / "datasets/ace-demo/tasks.json"
        target.parent.mkdir(parents=True)
        tasks = json.loads((ROOT / "examples/minimal/tasks.json").read_text())
        tasks["tasks"] = tasks["tasks"][:2]
        target.write_text(json.dumps(tasks))
        spec = load_experiment(write_ace_selection(self.root, "baseline"))
        with patch("agent_optimizer.model_input.ensure_model_api",
                   side_effect=lambda env: {**env, "AGENT_OPT_MODEL_API_KEY": "session-only"}) as api, \
             patch("agent_optimizer.model_input.ensure_model_selector",
                   side_effect=lambda env, key: {**env, key: "compatible/fixture"}):
            self.assertEqual(_tui_model_environment(spec, {})["AGENT_OPT_MODEL_API_KEY"], "session-only")
        api.assert_called_once()

    def test_ace_baseline_confirmation_labels_optimizer_model_unneeded(self):
        from agent_optimizer.cli import _run_ace_selection
        output = io.StringIO()
        with patch("builtins.input", return_value="n"), redirect_stderr(output):
            self.assertEqual(_run_ace_selection(self.root, "baseline"), 2)
        self.assertIn("Optimizer 모델: 필요 없음", output.getvalue())

    def test_english_synthetic_confirmation_labels_fixture(self):
        from agent_optimizer.cli import _run_sample_selection
        output = io.StringIO()
        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}), \
             patch("builtins.input", return_value="n"), redirect_stderr(output):
            self.assertEqual(_run_sample_selection(self.root, "rtl-solo", "baseline"), 2)
        self.assertIn("synthetic fixture", output.getvalue())
        self.assertIn("Prepare and run?", output.getvalue())

    def test_confirmed_meta_selection_routes_generated_stage_to_runner(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        document = json.loads((ROOT / "examples/minimal/tasks.json").read_text())
        document["tasks"] = document["tasks"][:2]
        destinations = []

        def prepare(root):
            target = root / "datasets/ace-demo/tasks.json"
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps(document))

        def execute(path):
            destinations.append(load_experiment(path)["stages"][0]["optimizer"])
            return 0

        with patch("sys.stdin.isatty", return_value=True), \
             patch("agent_optimizer.preset_tui.select_four",
                   return_value=("ace-rtl", "ace-opencode", "meta_harness", "cvdp")), \
             patch("agent_optimizer.preset_tui.prepare_ace_selection", side_effect=prepare), \
             patch("agent_optimizer.preset_tui.run_ace_selection", side_effect=execute), \
             patch("agent_optimizer.cli._tui_model_environment", return_value={}), \
             patch("builtins.input", side_effect=["y"]), \
             redirect_stderr(Terminal()):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 0)
        self.assertEqual(destinations, ["meta_harness"])

    def test_confirmed_synthetic_preset_runs_without_model_or_docker(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        output = io.StringIO()
        with patch("sys.stdin.isatty", return_value=True), \
             patch("agent_optimizer.preset_tui.select_four",
                   return_value=("rtl-solo", "fixture", "baseline", "sample_text")), \
             patch("agent_optimizer.preset_tui.prepare_ace_selection",
                   side_effect=AssertionError("합성 프리셋은 ACE 자산을 준비하면 안 됩니다")), \
             patch("builtins.input", side_effect=["y"]), \
             patch("sys.stdout", output), redirect_stderr(Terminal()):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "completed")


if __name__ == "__main__":
    unittest.main()
