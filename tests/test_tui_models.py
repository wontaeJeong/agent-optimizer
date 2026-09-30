"""실제 Pilot로 API 입력·출처·비밀·충돌 차단을 검증한다."""
import os
import unittest
from unittest.mock import patch
from pathlib import Path

from textual.widgets import Input, OptionList, Static

from support import test_project
from agent_optimizer.tui import OptimizerApp
from agent_optimizer.contracts import ConfigurationError


ENV = {"AGENT_OPT_LANG": "ko", "AGENT_OPT_MODEL": "compatible/fixture-model",
       "AGENT_OPT_MODEL_ID": "fixture-model", "AGENT_OPT_MODEL_BASE_URL": "https://fixture.example/v1",
       "AGENT_OPT_MODEL_API_KEY": "SENTINEL-secret-b-20261001"}


class ModelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)
        self.capture = os.environ.get("B_TUI_SECRET_CAPTURE")
        isolation = {key: value for key, value in os.environ.items() if key in {
            "HOME", "TMPDIR", "AGENT_OPT_HOME", "XDG_CACHE_HOME"}}
        self.environment = patch.dict(os.environ, {**isolation, **ENV}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    async def edit(self, app, pilot, field):
        app.query_one(OptionList).highlighted = app.model_fields.index(field)
        await pilot.press("enter", "end", "enter")

    async def test_endpoint_stays_plaintext_custom_draft_back_and_q_is_input(self):
        app = OptimizerApp(self.root)
        async with app.run_test(size=(50, 24)) as pilot:
            await pilot.press("enter", "enter", "enter", "enter", "enter")
            await self.edit(app, pilot, "AGENT_OPT_MODEL_BASE_URL")
            entry = app.query_one(Input)
            self.assertFalse(entry.password)
            entry.value = "https://custom.example/v1/긴경로"
            await pilot.pause()
            await pilot.press("end", "q")
            draft = entry.value
            self.assertTrue(app.is_running)
            await pilot.press("escape", "end", "enter")
            self.assertEqual(entry.value, draft)
            await pilot.press("enter")
            self.assertEqual(app.model_values["AGENT_OPT_MODEL_BASE_URL"], draft)
            self.assertEqual(os.environ["AGENT_OPT_MODEL_BASE_URL"], "https://fixture.example/v1")
            self.assertIn(draft, app._review())
            self.assertNotIn(ENV["AGENT_OPT_MODEL_API_KEY"], app._review())

    async def test_bad_urls_block_before_state_or_preparation_and_hide_credentials(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("enter", "enter", "enter", "enter", "enter")
            await self.edit(app, pilot, "AGENT_OPT_MODEL_BASE_URL")
            entry = app.query_one(Input)
            for url in ("https://user:URL-SENTINEL@fixture.example/v1", "https://fixture.example/v1?k=URL-SENTINEL",
                        "https://fixture.example/v1#URL-SENTINEL", "https://fixture.example:bad/v1",
                        "https://fixture.example:70000/v1", "http://remote.example/v1",
                        "https://fixture.example/v1/chat/completions", "ftp://fixture.example/v1",
                        "https://@fixture.example/v1", "https://fixture.example/v1?",
                        "https://fixture.example/v1#", "https://fixture.example/v1/../private"):
                with self.subTest(url=url):
                    entry.value = url
                    await pilot.press("enter")
                    self.assertEqual(app.model_mode, "input")
                    self.assertNotIn("AGENT_OPT_MODEL_BASE_URL", app.model_values)
                    self.assertNotIn("URL-SENTINEL", str(app.query_one("#details", Static).render()))
                    self.assertFalse(app.busy)
            self.assertFalse((self.root / "runs").exists())

    async def test_credential_url_is_removed_before_render_escape_and_reentry(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("enter", "enter", "enter", "enter", "enter")
            await self.edit(app, pilot, "AGENT_OPT_MODEL_BASE_URL")
            entry = app.query_one(Input)
            for url in ("https://user:URL-SENTINEL@fixture.example/v1", "https://fixture.example/v1?token=URL-SENTINEL",
                        "https://fixture.example/v1#URL-SENTINEL", "https://user:URL-SENTINEL"):
                with self.subTest(url=url):
                    entry.value = url
                    # Synchronous rendering must never see the rejected value, even before Changed is dispatched.
                    self.assertNotIn("URL-SENTINEL", str(entry.render()))
                    self.assertNotIn("URL-SENTINEL", entry.value)
                    await pilot.press("escape", "end", "enter")
                    self.assertNotIn("URL-SENTINEL", repr(app.input_drafts))
                    self.assertNotIn("URL-SENTINEL", entry.value)
                    self.assertNotIn("URL-SENTINEL", app.export_screenshot())
                    self.assertFalse(entry.password)
            # A legacy draft inserted by a caller is safe in repr and must not rehydrate.
            app.input_drafts["AGENT_OPT_MODEL_BASE_URL"] = "https://user:URL-SENTINEL@fixture.example/v1"
            self.assertNotIn("URL-SENTINEL", repr(app.input_drafts))
            await pilot.press("escape", "end", "enter")
            self.assertNotIn("URL-SENTINEL", entry.value)
            entry.value = "https://safe.example/v1"
            await pilot.press("enter")
            self.assertEqual(app._model_value("AGENT_OPT_MODEL_BASE_URL"), ("https://safe.example/v1", "session"))

    async def test_bare_selector_display_schema_and_execution_share_effective_values(self):
        os.environ["AGENT_OPT_MODEL"] = "team-model"
        os.environ["AGENT_OPT_MODEL_ID"] = ""
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("enter", "enter", "enter", "enter", "enter", "end", "enter")
            self.assertEqual(app.page, "Review")
            fields = app.model_configuration()["fields"]
            self.assertEqual(fields["AGENT_OPT_MODEL_ID"], {"value": "team-model", "configured": True, "source": "derived"})
            self.assertEqual(fields["AGENT_OPT_MODEL"]["value"], "compatible/team-model")
            self.assertEqual(app._execution_environment()["AGENT_OPT_MODEL_ID"], "team-model")
            self.assertEqual(app._execution_environment()["AGENT_OPT_MODEL"], "compatible/team-model")
            self.assertIn("team-model", app._review())
            self.assertEqual(os.environ["AGENT_OPT_MODEL"], "team-model")

    async def test_custom_and_multiple_profile_selectors_block_conflicts_before_prepare(self):
        experiment = self.root / "examples/minimal/experiment.toml"
        profile = self.root / "examples/minimal/harness.toml"
        profile.write_text('id = "opencode"\nadapter = "opencode"\nmodel_env = "TEAM_AGENT_MODEL"\n'
                           '[runtime]\nkind = "docker"\nimage = "fixture-image"\n'
                           'env_passthrough = ["TEAM_AGENT_MODEL", "AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_API_KEY"]\n')
        os.environ["TEAM_AGENT_MODEL"] = "compatible/agent-model"
        os.environ["AGENT_OPT_MODEL_ID"] = "optimizer-model"
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            app._load_existing(experiment)
            await pilot.press("enter", "end", "enter")
            self.assertEqual(app.page, "Model")
            self.assertIn("TEAM_AGENT_MODEL", str(app.query_one("#details", Static).render()))
            app._show("Review")
            await pilot.press("down", "enter")
            self.assertFalse(app.busy)
            self.assertEqual(app.page, "Model")
            self.assertFalse((self.root / "runs").exists())
            await self.edit(app, pilot, "AGENT_OPT_MODEL_ID")
            app.query_one(Input).value = "agent-model"
            await pilot.press("enter", "end", "enter")
            self.assertEqual(app.page, "Review")
            # A second profile cannot silently override the shared compatible API ID.
            second = profile.with_name("second.toml")
            second.write_text(profile.read_text().replace('id = "opencode"', 'id = "second"')
                              .replace("TEAM_AGENT_MODEL", "SECOND_AGENT_MODEL"))
            experiment.write_text(experiment.read_text().replace('harnesses = ["examples/minimal/harness.toml"]',
                                  'harnesses = ["examples/minimal/harness.toml", "examples/minimal/second.toml"]'))
            os.environ["SECOND_AGENT_MODEL"] = "compatible/different-model"
            app._open_model_setup("Review")
            await pilot.press("end", "enter")
            self.assertEqual(app.page, "Model")
            self.assertIn("SECOND_AGENT_MODEL", str(app.query_one("#details", Static).render()))
            with self.assertRaises(ConfigurationError):
                app._execution_environment()
            self.assertEqual(os.environ["AGENT_OPT_MODEL_ID"], "optimizer-model")

    async def test_custom_bare_selector_derives_id_and_records_real_source(self):
        profile = self.root / "examples/minimal/harness.toml"
        profile.write_text('id = "opencode"\nadapter = "opencode"\nmodel_env = "TEAM_AGENT_MODEL"\n'
                           '[runtime]\nkind = "docker"\nimage = "fixture-image"\n')
        os.environ["TEAM_AGENT_MODEL"] = "team-model"
        os.environ["AGENT_OPT_MODEL_ID"] = ""
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            app._load_existing(self.root / "examples/minimal/experiment.toml")
            await pilot.press("enter", "end", "enter")
            self.assertEqual(app.page, "Review")
            self.assertEqual(app._model_value("AGENT_OPT_MODEL_ID"), ("team-model", "derived"))
            self.assertEqual(app.model_configuration()["fields"]["TEAM_AGENT_MODEL"]["value"], "compatible/team-model")
            self.assertEqual(app._execution_environment()["TEAM_AGENT_MODEL"], "compatible/team-model")

    async def test_environment_credentials_never_render_and_short_key_keeps_labels(self):
        os.environ["AGENT_OPT_MODEL_BASE_URL"] = "https://user:URL-SENTINEL@fixture.example/v1"
        os.environ["AGENT_OPT_MODEL_API_KEY"] = "a"
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("enter", "enter", "enter", "enter", "enter")
            text = "\n".join(row[0] for row in app.rows) + app._review()
            self.assertNotIn("URL-SENTINEL", text)
            self.assertIn("자격증명 포함 URL", text)
            self.assertIn("compatible/fixture-model", text)
            self.assertIn("Agent", text)
            await self.edit(app, pilot, "AGENT_OPT_MODEL_BASE_URL")
            self.assertNotIn("URL-SENTINEL", app.query_one(Input).value)

    async def test_mismatch_blocks_review_then_explicit_edit_resolves_it(self):
        os.environ["AGENT_OPT_MODEL_ID"] = "other-model"
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("enter", "enter", "enter", "enter", "enter", "end", "enter")
            self.assertEqual(app.page, "Model")
            self.assertIn("일치", str(app.query_one("#details", Static).render()))
            self.assertEqual(os.environ["AGENT_OPT_MODEL_ID"], "other-model")
            await self.edit(app, pilot, "AGENT_OPT_MODEL_ID")
            app.query_one(Input).value = "fixture-model"
            await pilot.press("enter", "end", "enter")
            self.assertEqual(app.page, "Review")
            self.assertIn("세션", app._review())

    async def test_environment_choice_restores_value_and_source_after_custom(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("enter", "enter", "enter", "enter", "enter")
            await self.edit(app, pilot, "AGENT_OPT_MODEL_BASE_URL")
            app.query_one(Input).value = "https://custom.example/v1"
            await pilot.press("enter")
            app.query_one(OptionList).highlighted = app.model_fields.index("AGENT_OPT_MODEL_BASE_URL")
            await pilot.press("enter", "home", "enter")
            self.assertEqual(app._model_value("AGENT_OPT_MODEL_BASE_URL"), ("https://fixture.example/v1", "environment"))
            self.assertNotIn("AGENT_OPT_MODEL_BASE_URL", app.model_values)

    async def test_empty_model_id_derives_from_compatible_without_environment_mutation(self):
        os.environ["AGENT_OPT_MODEL_ID"] = ""
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("enter", "enter", "enter", "enter", "enter", "end", "enter")
            self.assertEqual(app.page, "Review")
            self.assertEqual(app._execution_environment()["AGENT_OPT_MODEL_ID"], "fixture-model")
            self.assertEqual(os.environ["AGENT_OPT_MODEL_ID"], "")

    async def test_named_presets_and_key_masking_preserve_sources(self):
        app = OptimizerApp(self.root)
        self.assertTrue(hasattr(app, "model_presets"))
        app.model_presets = {"팀 설정": {"AGENT_OPT_MODEL_BASE_URL": "https://team.example/v1",
                                      "AGENT_OPT_MODEL_ID": "fixture-model",
                                      "AGENT_OPT_MODEL_API_KEY": "NEVER-PRESET-KEY"}}
        self.assertNotIn("NEVER-PRESET-KEY", repr(app.model_presets))
        async with app.run_test() as pilot:
            await pilot.press("enter", "enter", "enter", "enter", "enter")
            app.query_one(OptionList).highlighted = app.model_fields.index("AGENT_OPT_MODEL_BASE_URL")
            await pilot.press("enter")
            self.assertTrue(any("팀 설정" in row[0] for row in app.rows))
            app.query_one(OptionList).highlighted = next(
                i for i, row in enumerate(app.rows) if "팀 설정" in row[0])
            await pilot.press("enter")
            self.assertEqual(app.model_values["AGENT_OPT_MODEL_BASE_URL"], "https://team.example/v1")
            self.assertIn("파일", app._review())
            await self.edit(app, pilot, "AGENT_OPT_MODEL_API_KEY")
            entry = app.query_one(Input)
            self.assertTrue(entry.password)
            entry.value = "SESSION-SENTINEL"
            self.assertNotIn("SESSION-SENTINEL", str(entry.render()))
            await pilot.press("enter")
            self.assertNotIn("SESSION-SENTINEL", app._review())
            self.assertNotIn("NEVER-PRESET-KEY", app._review())
            self.assertNotIn("SESSION-SENTINEL", repr(app.model_values))
            self.assertNotIn("SESSION-SENTINEL", repr(app.model_configuration()))

    async def test_native_metadata_does_not_require_coding_selector_or_optimizer_for_baseline(self):
        app = OptimizerApp(self.root)
        self.assertTrue(hasattr(app, "component_metadata"))
        app.component_metadata = {"native-fixture": {"execution_mode": "native", "requires_model_api": True,
                                                   "model_roles": ["generator", "reflector", "coordinator"]}}
        app.selections = {"Agent": "ace-rtl", "Harness": "native-fixture", "Optimizer": "baseline", "Dataset": "cvdp"}
        self.assertEqual(app._required_model_fields(), ["AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_ID", "AGENT_OPT_MODEL_API_KEY"])
        summary = "\n".join(app._model_summary())
        self.assertIn("generator", summary)
        self.assertIn("Optimizer API: 불필요", summary)
        os.environ["AGENT_OPT_MODEL_ID"] = ""
        os.environ["AGENT_OPT_MODEL"] = "compatible/coding-only"
        self.assertNotEqual(app._model_value("AGENT_OPT_MODEL_ID")[0], "coding-only")

    async def test_fixture_needs_no_optimizer_api_even_with_conflicting_environment(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            app.query_one(OptionList).highlighted = next(
                i for i, row in enumerate(app.rows) if row[0] == "rtl-solo")
            await pilot.press("enter", "enter", "enter", "enter", "enter")
            self.assertEqual(app.page, "Review")
            self.assertEqual(app._required_model_fields(), [])
            app.model_values["AGENT_OPT_MODEL_API_KEY"] = "unnecessary-session-key"
            self.assertNotEqual(app._execution_environment().get("AGENT_OPT_MODEL_API_KEY"),
                                "unnecessary-session-key")

    async def test_secret_absent_from_svg_and_safe_endpoint_visible(self):
        app = OptimizerApp(self.root)
        async with app.run_test(size=(80, 28)) as pilot:
            await pilot.press("enter", "enter", "enter", "enter", "enter")
            svg = app.export_screenshot()
            self.assertNotIn(ENV["AGENT_OPT_MODEL_API_KEY"], svg)
            self.assertIn("fixture.example", svg)
            await self.edit(app, pilot, "AGENT_OPT_MODEL_API_KEY")
            app.query_one(Input).value = "SESSION-SENTINEL"
            await pilot.pause()
            svg = app.export_screenshot()
            self.assertNotIn("SESSION-SENTINEL", svg)
            if self.capture:
                app.save_screenshot(filename=str(Path(self.capture)))
