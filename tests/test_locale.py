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

    def test_command_placeholders_in_help_are_literal_text(self):
        from agent_optimizer.locale import human

        with patch.dict(os.environ, {"AGENT_OPT_LANG": "ko"}):
            self.assertIn("{task_dir}", human("Agent execution argv (e.g. python agent.py {task_dir})"))

    def test_english_user_help_and_subcommand_explanation(self):
        env = dict(os.environ, AGENT_OPT_LANG="en")
        for args, expected in ((["--help"], "Optimization experiments for multiple Agents"),
                               (["init", "--help"], "Create an experiment")):
            with self.subTest(args=args):
                result = subprocess.run([str(ROOT / ".venv/bin/agent-opt"), *args], cwd=ROOT,
                                        env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)
                self.assertNotIn("여러 Agent의 최적화 실험", result.stdout)

    def test_invalid_python_language_fails_without_traceback(self):
        result = subprocess.run([str(ROOT / ".venv/bin/agent-opt"), "--help"], cwd=ROOT,
                                env=dict(os.environ, AGENT_OPT_LANG="ja"), capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("AGENT_OPT_LANG", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_english_developer_python_help(self):
        result = subprocess.run([str(ROOT / ".venv/bin/python"), "scripts/dev.py", "--help"],
                                cwd=ROOT, env=dict(os.environ, AGENT_OPT_LANG="en"),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Development commands:", result.stdout)
        self.assertIn("Check the development environment", result.stdout)
        self.assertNotIn("개발 명령:", result.stdout)

    def test_korean_tui_tty_error_and_english_variant(self):
        for language, expected in (("ko", "TUI에는 입력과 출력 모두 TTY가 필요합니다"),
                                   ("en", "TUI requires a TTY for both input and output")):
            with self.subTest(language=language):
                result = subprocess.run([str(ROOT / ".venv/bin/agent-opt"), "tui"], cwd=ROOT,
                                        env=dict(os.environ, AGENT_OPT_LANG=language),
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertIn(expected, result.stderr)


if __name__ == "__main__":
    unittest.main()
