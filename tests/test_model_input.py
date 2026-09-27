import getpass
import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.model_input import ensure_model_api, session_environment


class ModelInputTests(unittest.TestCase):
    def test_hidden_input_failure_does_not_echo_or_publish_partial_settings(self):
        values = {}
        output, errors = io.StringIO(), io.StringIO()
        with patch("builtins.input", side_effect=["https://example.invalid/v1", ""]), \
                patch("getpass.getpass", side_effect=getpass.GetPassWarning("terminal echo")), \
                redirect_stdout(output), redirect_stderr(errors):
            with self.assertRaises(ConfigurationError):
                ensure_model_api(values)
        self.assertEqual(values, {})
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("terminal echo", errors.getvalue())

    def test_existing_model_values_need_no_prompt_and_session_restores_after_failure(self):
        configured = {"AGENT_OPT_MODEL_BASE_URL": "https://example.invalid/v1",
                      "AGENT_OPT_MODEL_API_KEY": "fixture-secret"}
        with patch("builtins.input", side_effect=AssertionError("중복 URL 질문")), \
                patch("getpass.getpass", side_effect=AssertionError("중복 키 질문")):
            staged = ensure_model_api(configured)
        before = dict(os.environ)
        with self.assertRaisesRegex(RuntimeError, "run failed"):
            with session_environment(staged):
                self.assertEqual(os.environ["AGENT_OPT_MODEL_API_KEY"], "fixture-secret")
                raise RuntimeError("run failed")
        self.assertEqual(dict(os.environ), before)
