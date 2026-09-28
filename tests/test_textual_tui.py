"""Textual 화면에서 실제 키 입력으로 프리셋과 실행 확인을 검증한다."""
import asyncio
import io
import json
import os
import unittest
from pathlib import Path
from contextlib import redirect_stderr
from unittest.mock import patch

from support import test_project


class TextualFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)

    async def test_cli_rejects_piped_output_even_with_tty_input_and_error(self):
        from agent_optimizer.cli import main

        errors = io.StringIO()
        with redirect_stderr(errors), patch("sys.stdin.isatty", return_value=True), \
             patch("sys.stdout.isatty", return_value=False), \
             patch("sys.stderr.isatty", return_value=True):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
        self.assertIn("TTY", errors.getvalue())

    async def test_highlight_disabled_and_back_preserve_selection(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import OptionList, Static

        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            self.assertEqual(app.page, "Agent")
            await pilot.press("down")
            self.assertIn("호환", str(app.query_one("#details", Static).render()))
            await pilot.press("up", "enter")
            self.assertEqual(app.page, "Harness")
            await pilot.press("down")
            self.assertIn("호환", str(app.query_one("#details", Static).render()))
            await pilot.press("enter")
            self.assertEqual(app.page, "Harness")
            await pilot.press("up", "enter", "down", "enter", "enter")
            self.assertEqual(app.page, "Review")
            await pilot.press("escape")
            self.assertEqual(app.page, "Dataset")
            await pilot.press("escape", "escape", "escape")
            self.assertEqual(app.page, "Agent")
            self.assertEqual(app.query_one(OptionList).highlighted, 0)
            await pilot.press("q")

    async def test_switching_agent_revalidates_dependent_choices(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import OptionList, Static

        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("enter", "enter", "down", "enter", "enter")
            self.assertEqual(app.page, "Review")
            await pilot.press("escape", "escape", "escape", "escape")
            index = next(i for i, row in enumerate(app.rows) if row[0] == "rtl-solo")
            await pilot.press(*(["down"] * index), "enter")
            self.assertEqual(app.page, "Harness")
            self.assertEqual(app.selections["Agent"], "rtl-solo")
            self.assertEqual(app.rows[0][0], "Fixture")
            self.assertIn("Fixture", str(app.query_one("#details", Static).render()))
            self.assertNotIn("Optimizer", app.selections)
            await pilot.press("enter", "enter", "enter")
            self.assertEqual(app.page, "Review")
            self.assertIn("sample_text", str(app.query_one("#review", Static).render()))

    async def test_existing_config_and_history_are_read_only_until_run(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input, Static

        name = "20260927T120000Z-abcdef12"
        run = self.root / "runs" / name
        run.mkdir(parents=True)
        (run / "summary.json").write_text(json.dumps({"schema_version": 1, "run_id": name,
                                                         "status": "completed", "groups": [],
                                                         "trials_used": 2}))
        (run / "report.html").write_text("report")
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("escape")
            self.assertEqual(app.page, "Home")
            await pilot.press("down", "down", "enter")
            self.assertEqual(app.page, "History")
            self.assertIn(name, str(app.query_one("#details", Static).render()))
            await pilot.press("escape", "up", "enter")
            self.assertEqual(app.page, "Existing")
            app.query_one(Input).value = "examples/minimal/experiment.toml"
            await pilot.press("enter")
            self.assertEqual(app.page, "Review")
            self.assertFalse((self.root / "runs" / "configs").exists())

    async def test_english_home_and_quit(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("escape")
                self.assertIn("New Optimization", str(app.query_one("#details", Static).render()))
                await pilot.press("q")

    async def test_fixture_runs_in_worker_and_displays_report(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            index = next(i for i, row in enumerate(app.rows) if row[0] == "rtl-solo")
            await pilot.press(*(["down"] * index), "enter", "enter", "enter", "enter")
            self.assertEqual(app.page, "Review")
            await pilot.press("enter")
            self.assertEqual(app.page, "Running")
            for _ in range(150):
                if not app.busy:
                    break
                await asyncio.sleep(0.1)
            self.assertFalse(app.busy)
            text = str(app.query_one("#details", Static).render())
            self.assertIn("report.html", text)
            self.assertIn("완료", text)
            self.assertTrue(list((self.root / "runs").glob("*/report.html")))

    async def test_review_cancel_and_model_input_never_prepares_assets(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input, Static

        with patch.dict(os.environ, {"AGENT_OPT_MODEL": "", "AGENT_OPT_MODEL_BASE_URL": "",
                                     "AGENT_OPT_MODEL_API_KEY": "", "AGENT_OPT_MODEL_ID": ""}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter", "enter", "enter", "enter")
                self.assertEqual(app.page, "Review")
                self.assertIn("role-guidance.md", str(app.query_one("#review", Static).render()))
                await pilot.press("enter")
                self.assertEqual(app.page, "Model")
                self.assertIn("AGENT_OPT_MODEL", app.query_one(Input).placeholder)
                await pilot.press("escape")
                self.assertEqual(app.page, "Review")
                await pilot.press("down", "enter")
                self.assertEqual(app.page, "Dataset")
                self.assertFalse((self.root / "runs").exists())

    async def test_history_rejects_replaced_report(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        name = "20260927T120000Z-abcdef12"
        run = self.root / "runs" / name
        run.mkdir(parents=True)
        (run / "summary.json").write_text(json.dumps({"schema_version": 1, "run_id": name,
                                                         "status": "completed", "groups": [],
                                                         "trials_used": 3}))
        report = run / "report.html"
        report.write_text("report")
        outside = self.root / "private.html"
        outside.write_text("private")
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("escape", "down", "down", "enter")
            self.assertIn("3", str(app.query_one("#details", Static).render()))
            report.unlink()
            report.symlink_to(outside)
            await pilot.press("enter")
            self.assertIn("안전하게", str(app.query_one("#details", Static).render()))
            self.assertNotIn("private", str(app.query_one("#details", Static).render()))

    async def test_existing_experiment_requires_review_then_runs_directly(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input, Static

        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("escape", "down", "enter")
            app.query_one(Input).value = "examples/minimal/experiment.toml"
            await pilot.press("enter")
            self.assertEqual(app.page, "Review")
            self.assertFalse((self.root / "runs").exists())
            await pilot.press("enter")
            for _ in range(150):
                if not app.busy:
                    break
                await asyncio.sleep(0.1)
            self.assertFalse(app.busy)
            self.assertIn("report.html", str(app.query_one("#details", Static).render()))
            self.assertTrue(list((self.root / "runs").glob("*/report.html")))

    async def test_unready_existing_experiment_shows_diagnostic_without_running(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input, Static

        plan = self.root / "examples/minimal/experiment.toml"
        plan.write_text(plan.read_text().replace("max_trials = 40", "max_trials = 1"))
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("escape", "down", "enter")
            app.query_one(Input).value = "examples/minimal/experiment.toml"
            await pilot.press("enter", "enter")
            for _ in range(80):
                if not app.busy:
                    break
                await asyncio.sleep(0.1)
            text = str(app.query_one("#details", Static).render())
            self.assertIn("설정/준비 오류", text)
            self.assertIn("budget", text)
            self.assertFalse(list((self.root / "runs").glob("*/report.html")))

    async def test_recent_history_filters_symlinks_invalid_and_limits_to_ten(self):
        from agent_optimizer.tui import OptimizerApp

        runs = self.root / "runs"
        for number in range(12):
            name = f"20260927T{number:02}0000Z-{number:08x}"
            directory = runs / ("dev-live" if number % 2 else "") / name
            directory.mkdir(parents=True)
            (directory / "summary.json").write_text(json.dumps({
                "schema_version": 1, "run_id": name, "status": "completed",
                "groups": [], "trials_used": number}))
            (directory / "report.html").write_text("report")
        (runs / "20260927T010000Z-00000001" ).symlink_to(runs / "dev-live" / "20260927T110000Z-0000000b")
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("escape", "down", "down", "enter")
            self.assertEqual(len(app.history), 10)
            self.assertEqual(app.history[0][0], "20260927T110000Z-0000000b")
            self.assertNotIn("20260927T010000Z-00000001", [item[0] for item in app.history])

    async def test_narrow_terminal_stacks_details_below_options(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        app = OptimizerApp(self.root)
        async with app.run_test(size=(50, 24)) as pilot:
            self.assertTrue(app.has_class("narrow"))
            await pilot.press("down")
            self.assertIn("호환", str(app.query_one("#details", Static).render()))
            options = app.query_one("#options")
            details = app.query_one("#details-panel")
            self.assertGreater(details.region.y, options.region.y)

    async def test_existing_opencode_asks_only_its_declared_model(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input

        harness = self.root / "examples/minimal/harness.toml"
        harness.write_text('id = "opencode"\nadapter = "opencode"\nmodel_env = "TEAM_MODEL"\n'
                           '[runtime]\nkind = "docker"\nimage = "pinned-agent"\n'
                           'env_passthrough = ["TEAM_MODEL", "AGENT_OPT_MODEL_BASE_URL", '
                           '"AGENT_OPT_MODEL_API_KEY"]\n')
        with patch.dict(os.environ, {"TEAM_MODEL": "", "AGENT_OPT_MODEL_BASE_URL": "",
                                     "AGENT_OPT_MODEL_API_KEY": ""}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("escape", "down", "enter")
                app.query_one(Input).value = "examples/minimal/experiment.toml"
                await pilot.press("enter", "enter")
                self.assertEqual(app.page, "Model")
                self.assertEqual(app.model_fields, ["TEAM_MODEL"])
                await pilot.press("escape")
                self.assertFalse((self.root / "runs").exists())

    async def test_bare_ace_model_requires_compatible_api_before_preparation(self):
        from agent_optimizer.tui import OptimizerApp

        with patch.dict(os.environ, {"AGENT_OPT_MODEL": "fixture-id",
                                     "AGENT_OPT_MODEL_BASE_URL": "", "AGENT_OPT_MODEL_ID": "",
                                     "AGENT_OPT_MODEL_API_KEY": ""}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter", "enter", "down", "down", "enter", "enter")
                self.assertEqual(app.page, "Review")
                await pilot.press("enter")
                self.assertEqual(app.page, "Model")
                self.assertIn("AGENT_OPT_MODEL_BASE_URL", app.model_fields)
                self.assertFalse((self.root / "runs").exists())

    async def test_narrow_review_can_scroll_to_report_with_keyboard(self):
        from agent_optimizer.tui import OptimizerApp

        app = OptimizerApp(self.root)
        async with app.run_test(size=(50, 20)) as pilot:
            await pilot.press("enter", "enter", "enter", "enter")
            panel = app.query_one("#review-panel")
            self.assertTrue(panel.can_focus)
            await pilot.press("tab", "pagedown")
            self.assertGreater(panel.scroll_y, 0)

    async def test_custom_route_leads_to_cli_setup_without_claiming_compatibility(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            index = next(i for i, row in enumerate(app.rows) if "Harness" in row[0] and row[2])
            await pilot.press(*(["down"] * index), "enter")
            self.assertEqual(app.page, "Advanced")
            self.assertIn("agent-opt init", str(app.query_one("#details", Static).render()))
            self.assertFalse((self.root / "runs").exists())

    async def test_english_selection_and_review_are_localized(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                self.assertIn("Assets to prepare", str(app.query_one("#details", Static).render()))
                await pilot.press("enter", "enter", "enter", "enter")
                text = str(app.query_one("#review", Static).render())
                self.assertIn("Agent model", text)
                self.assertIn("Report: runs/<run-id>/report.html", text)
