"""언어 선택은 개발 진입점과 사용자 출력에 동일하게 적용합니다."""

import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class TerminalLanguageTests(unittest.TestCase):
    def invoke(self, language):
        env = dict(os.environ, AGENT_OPT_LANG=language)
        return subprocess.run(["sh", "scripts/bootstrap.sh", "help"], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=10)

    def test_english_developer_help_before_python_installation(self):
        result = self.invoke("en")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Development commands:", result.stdout)
        self.assertNotIn("개발 명령:", result.stdout)

    def test_invalid_language_stops_before_any_command(self):
        result = self.invoke("ja")
        self.assertEqual(result.returncode, 2)
        self.assertIn("AGENT_OPT_LANG", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_python_language_selection_and_invalid_value(self):
        from agent_optimizer.locale import current_language, t

        for selected, expected in (("", "ko"), ("ko", "ko"), ("en", "en")):
            with self.subTest(selected=selected), patch.dict(os.environ, {"AGENT_OPT_LANG": selected}):
                self.assertEqual(current_language(), expected)
                self.assertEqual(t("remedy"), "Remedy" if expected == "en" else "해결")
        with patch.dict(os.environ, {"AGENT_OPT_LANG": "ja"}):
            with self.assertRaisesRegex(ValueError, "AGENT_OPT_LANG"):
                current_language()


if __name__ == "__main__":
    unittest.main()
