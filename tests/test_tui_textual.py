"""입력 reactive 경계와 실제 키 입력의 비밀 URL 거부 회귀."""
import os
import unittest
from unittest.mock import patch

from textual.widgets import Input, OptionList

from support import test_project, legacy_model_page
from agent_optimizer.tui import OptimizerApp


class TextualInputRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_credential_typing_is_cleared_until_reset_but_plain_urls_work(self):
        temporary, root = test_project()
        self.addCleanup(temporary.cleanup)
        isolation = {key: value for key, value in os.environ.items() if key in {
            "HOME", "TMPDIR", "AGENT_OPT_HOME", "XDG_CACHE_HOME"}}
        with patch.dict(os.environ, {**isolation, "AGENT_OPT_MODEL": "compatible/fixture-model",
                                    "AGENT_OPT_MODEL_ID": "fixture-model",
                                    "AGENT_OPT_MODEL_API_KEY": "fixture-key"}, clear=True):
            app = OptimizerApp(root)
            async with app.run_test() as pilot:
                await legacy_model_page(app, pilot)
                app.query_one(OptionList).highlighted = app.model_fields.index("AGENT_OPT_MODEL_BASE_URL")
                await pilot.press("enter", "end", "enter")
                entry = app.query_one(Input)
                entry.value = "https://user:"
                await pilot.pause()
                await pilot.press("end", "s")
                self.assertEqual(entry.value, "")
                for character in "ecret-token@host.example/v1":
                    await pilot.press(character)
                    self.assertEqual(entry.value, "")
                self.assertNotIn("secret-token", repr(app.input_drafts))
                self.assertNotIn("secret-token", app.export_screenshot())
                await pilot.press("escape", "end", "enter")
                for url in ("https://long.example/v1/" + "긴경로/" * 20, "http://[::1]:8080/v1"):
                    entry.value = url
                    await pilot.pause()
                    self.assertFalse(entry.password)
                    self.assertEqual(entry.value, url)
                await pilot.press("enter")
                self.assertEqual(app.model_values["AGENT_OPT_MODEL_BASE_URL"], "http://[::1]:8080/v1")
