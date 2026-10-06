"""안정 ID와 읽기 전용 선택·뒤로가기 계약을 검증한다."""
import os
import json
import unittest
import tempfile
import shutil
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

from textual.widgets import Input, OptionList, Static

from support import test_project, choose_row
from agent_optimizer.preset_tui import preset_options
from agent_optimizer.tui import OptimizerApp


class ChoiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)

    async def test_reordered_translated_component_and_action_use_ids(self):
        original = preset_options(self.root, "Agent")
        self.assertTrue(all(hasattr(row, "id") for row in original))
        fixture = next(row for row in original if row.id == "rtl-solo")
        action = next(row for row in original if row.id == "advanced")
        rows = [replace(fixture, label="동일 표시"), replace(action, label="동일 표시")]
        with patch("agent_optimizer.tui.preset_options", return_value=rows):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter", "enter")
                self.assertEqual(app.selections, {"Agent": "rtl-solo"})
                await pilot.press("escape", "down", "enter")
                self.assertEqual(app.page, "Advanced")
                self.assertFalse((self.root / "runs").exists())

    async def test_missing_or_partial_fixture_manifests_keep_agent_menu_unique(self):
        for manifests in ((), ("solo.toml",), ("team.toml",), ("solo.toml", "team.toml")):
            with self.subTest(manifests=manifests), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                if manifests:
                    (root / "examples/minimal").mkdir(parents=True)
                    for name in manifests:
                        shutil.copyfile(self.root / "examples/minimal" / name, root / "examples/minimal" / name)
                    # Two manifests can refer to the same component ID.
                    if len(manifests) == 2:
                        shutil.copyfile(root / "examples/minimal/solo.toml", root / "examples/minimal/team.toml")
                app = OptimizerApp(root)
                async with app.run_test() as pilot:
                    await pilot.press("enter")
                    self.assertEqual(app.page, "Agent")
                    ids = [row.id for row in app.rows]
                    self.assertEqual(len(ids), len(set(ids)))
                    self.assertEqual("rtl-solo" in ids, "solo.toml" in manifests)
                    self.assertEqual("rtl-team" in ids, manifests == ("team.toml",))

    async def test_installed_workspace_preserves_baseline_and_meta_selection(self):
        for optimizer in ("baseline", "meta_harness"):
            with self.subTest(optimizer=optimizer), patch("agent_optimizer.tui.is_source_checkout", return_value=False), \
                    patch.dict(os.environ, {"AGENT_OPT_MODEL": "openrouter/fixture-model", "OPENROUTER_API_KEY": "fixture-key"}):
                app = OptimizerApp(self.root)
                async with app.run_test() as pilot:
                    for identifier in ('new', 'ace-rtl', 'ace-opencode'):
                        await choose_row(app, pilot, identifier)
                    app.query_one(OptionList).highlighted = next(i for i, row in enumerate(app.rows) if row.id == optimizer)
                    await pilot.press("enter", "enter")
                    self.assertEqual(app.page, "Workspace")
                    chosen = dict(app.selections)
                    await choose_row(app, pilot, 'workspace.custom')
                    app.query_one(Input).value = "선택한 작업공간"
                    await pilot.press("enter")
                    self.assertEqual(app.selections, chosen)
                    self.assertEqual(app.workspace, self.root / "선택한 작업공간")
                    if optimizer == "baseline":
                        self.assertEqual(app.model_fields, ["AGENT_OPT_MODEL", "OPENROUTER_API_KEY"])
                    else:
                        self.assertIn("AGENT_OPT_MODEL_BASE_URL", app.model_fields)
                    await pilot.press("escape", "escape")
                    self.assertEqual(app.page, "Dataset")
                    self.assertEqual(app.selections, chosen)

    async def test_four_steps_disabled_back_and_parent_change_are_read_only(self):
        app = OptimizerApp(self.root)
        async with app.run_test(size=(60, 24)) as pilot:
            await pilot.press("enter")
            self.assertTrue(all(hasattr(row, "id") for row in app.rows))
            disabled = next(i for i, row in enumerate(app.rows) if not row.enabled)
            app.query_one(OptionList).highlighted = disabled
            await pilot.pause()
            detail = str(app.query_one("#details", Static).render())
            self.assertIn("선택할 수 없는 이유", detail)
            await pilot.press("enter")
            self.assertEqual(app.page, "Agent")
            app.query_one(OptionList).highlighted = next(
                i for i, row in enumerate(app.rows) if row.id == "rtl-solo")
            await pilot.press("enter", "enter", "enter", "enter", "enter")
            self.assertEqual(app.page, "Review")
            self.assertEqual(app.selections, {"Agent": "rtl-solo", "Harness": "fixture",
                                             "Optimizer": "baseline", "Dataset": "sample_text"})
            app.experiment = self.root / "examples/minimal/experiment.toml"
            await pilot.press("escape", "escape", "escape", "escape", "escape")
            self.assertEqual(app.page, "Agent")
            self.assertEqual(app.rows[app.query_one(OptionList).highlighted].id, "rtl-solo")
            app.query_one(OptionList).highlighted = next(
                i for i, row in enumerate(app.rows) if row.id == "ace-rtl")
            await pilot.press("enter")
            self.assertEqual(app.selections, {"Agent": "ace-rtl"})
            self.assertIsNone(app.experiment)
            self.assertTrue(app.query_one(OptionList).has_focus)
            self.assertFalse((self.root / "runs").exists())

    async def test_report_action_is_explicit_and_never_starts_server(self):
        run = self.root / "runs/20261001T000000Z-abcdef12"
        run.mkdir(parents=True)
        (run / "summary.json").write_text(json.dumps({"schema_version": 1, "run_id": run.name,
                                                     "status": "completed", "groups": [], "trials_used": 0}))
        (run / "report.html").write_text("비밀 없는 fixture 보고서")
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            app._finish({"status": "completed", "report_html": run / "report.html"})
            self.assertTrue(any(getattr(row, "id", None) == "report.open" for row in app.rows))
            app.query_one(OptionList).highlighted = next(
                i for i, row in enumerate(app.rows) if row.id == "report.open")
            await pilot.press("enter")
            self.assertIn("report.html", str(app.query_one("#details", Static).render()))
            app._show("Home")
            self.assertTrue(hasattr(app, "set_home_status"))
            app.set_home_status("보고서 열람 연결 준비됨")
            self.assertIn("연결 준비됨", str(app.query_one("#home-status", Static).render()))

    async def test_planned_is_metadata_only_and_enter_is_blocked(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("enter", "enter", "enter")
            self.assertTrue(any(getattr(row, "kind", "") == "planned" for row in app.rows))
            app.query_one(OptionList).highlighted = next(
                i for i, row in enumerate(app.rows) if row.kind == "planned")
            await pilot.press("enter")
            self.assertEqual(app.page, "Optimizer")
            self.assertNotIn("Optimizer", app.selections)
            self.assertIn("미구현", str(app.query_one("#details", Static).render()))

    async def test_selected_profile_metadata_controls_actual_edit_surface(self):
        app = OptimizerApp(self.root)
        app.component_metadata = {"ace-opencode": {"edit_surfaces": {"meta_harness": "selected/profile.py"}}}
        async with app.run_test() as pilot:
            for identifier in ('new', 'ace-rtl', 'ace-opencode'):
                await choose_row(app, pilot, identifier)
            app.query_one(OptionList).highlighted = next(i for i, row in enumerate(app.rows) if row.id == 'meta_harness')
            await pilot.pause()
            detail = str(app.query_one("#details", Static).render())
            self.assertIn("selected/profile.py", detail)
            await pilot.press("enter", "enter")
            self.assertIn("selected/profile.py", app._review())

    async def test_narrow_details_are_keyboard_scrollable_in_both_languages(self):
        for language in ("ko", "en"):
            with self.subTest(language=language), patch.dict(os.environ, {"AGENT_OPT_LANG": language}):
                app = OptimizerApp(self.root)
                async with app.run_test(size=(50, 20)) as pilot:
                    await pilot.press("enter", "enter", "enter", "down", "tab", "pagedown")
                    panel = app.query_one("#details-panel")
                    self.assertTrue(panel.can_focus)
                    self.assertGreater(panel.scroll_y, 0)

    async def test_capture_fixture(self):
        capture = os.environ.get("B_TUI_CAPTURE")
        if not capture:
            self.skipTest("명시적 캡처 실행에서만 SVG를 저장합니다")
        app = OptimizerApp(self.root)
        isolation = {key: value for key, value in os.environ.items() if key in {
            "HOME", "TMPDIR", "AGENT_OPT_HOME", "XDG_CACHE_HOME"}}
        with patch.dict(os.environ, {**isolation, "AGENT_OPT_LANG": "ko", "AGENT_OPT_MODEL": "compatible/fixture-model",
                                    "AGENT_OPT_MODEL_ID": "fixture-model",
                                    "AGENT_OPT_MODEL_BASE_URL": "https://fixture.example/v1",
                                    "AGENT_OPT_MODEL_API_KEY": ""}, clear=True):
            async with app.run_test(size=(80, 28)) as pilot:
                await pilot.press("enter", "enter", "enter", "enter", "enter")
                app.save_screenshot(filename=capture)
