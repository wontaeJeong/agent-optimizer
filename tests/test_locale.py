"""언어 선택은 개발 진입점과 사용자 출력에 동일하게 적용합니다."""

import contextlib
import io
import json
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

    def test_developer_option_error_is_korean_by_default_and_english_when_selected(self):
        for language, expected in (("ko", "지원하지 않는 옵션"), ("en", "Unsupported option")):
            with self.subTest(language=language):
                result = subprocess.run(["sh", "scripts/bootstrap.sh", "setup", "--invalid"],
                                        cwd=ROOT, env=dict(os.environ, AGENT_OPT_LANG=language),
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertIn(expected, result.stderr)
                self.assertNotIn(".env", result.stderr)

    def test_english_menu_help_before_python_installation(self):
        result = subprocess.run(["sh", "scripts/bootstrap.sh", "menu", "--help"], cwd=ROOT,
                                env=dict(os.environ, AGENT_OPT_LANG="en"), capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("interactive numbered menu", result.stdout)
        self.assertNotIn("대화형 번호 메뉴", result.stdout)

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

    def test_english_command_harness_option_help(self):
        result = subprocess.run([str(ROOT / ".venv/bin/agent-opt"), "init", "--help"], cwd=ROOT,
                                env=dict(os.environ, AGENT_OPT_LANG="en"), capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        command_help = result.stdout.split("--command", 1)[1].split("--command-json", 1)[0]
        self.assertIn("Command harness", command_help)
        self.assertIn("Agent argv: split", command_help)
        self.assertNotIn("명령 하네스의 Agent argv", result.stdout)

    def test_english_init_missing_agent_error(self):
        result = subprocess.run([str(ROOT / ".venv/bin/agent-opt"), "init", "--dataset", "sample_text", "--yes"],
                                cwd=ROOT, env=dict(os.environ, AGENT_OPT_LANG="en"),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Specify --agent and --editable", result.stderr)

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

    def test_english_developer_setup_option_help(self):
        result = subprocess.run([str(ROOT / ".venv/bin/python"), "scripts/dev.py", "setup", "--help"],
                                cwd=ROOT, env=dict(os.environ, AGENT_OPT_LANG="en"),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Prepare or diagnose core tools only", result.stdout)
        self.assertNotIn("코어 도구만 준비", result.stdout)

    def test_korean_tui_tty_error_and_english_variant(self):
        for language, expected in (("ko", "TUI에는 입력과 출력 모두 TTY가 필요합니다"),
                                   ("en", "TUI requires a TTY for both input and output")):
            with self.subTest(language=language):
                result = subprocess.run([str(ROOT / ".venv/bin/agent-opt"), "tui"], cwd=ROOT,
                                        env=dict(os.environ, AGENT_OPT_LANG=language),
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertIn(expected, result.stderr)

    def test_english_tui_existing_experiment_prompts(self):
        from agent_optimizer.cli import main

        class Terminal(io.StringIO):
            def isatty(self):
                return True

        for answers, expected in (([EOFError()], "Start an experiment:"),
                                  (["1", EOFError()], "Existing experiment.toml path:")):
            with self.subTest(answers=answers), patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}), \
                    patch("sys.stdin.isatty", return_value=True), \
                    patch("builtins.input", side_effect=answers):
                output = Terminal()
                with contextlib.redirect_stderr(output):
                    self.assertEqual(main(["tui"]), 2)
                self.assertIn(expected, output.getvalue())

    def test_project_owned_init_error_is_translated_without_changing_option_name(self):
        for language, expected in (("ko", "데이터셋을 --dataset으로 직접 선택하세요"),
                                   ("en", "Select a dataset explicitly with --dataset")):
            with self.subTest(language=language):
                result = subprocess.run([str(ROOT / ".venv/bin/agent-opt"), "init", "--yes"],
                                        cwd=ROOT, env=dict(os.environ, AGENT_OPT_LANG=language),
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertIn(expected, result.stderr)

    def test_plan_doctor_human_remedy_translates_but_json_remains_english(self):
        plan = ROOT / "nonexistent-language-check.toml"
        for language, expected in (("ko", "실험 파일이 없거나 잘못되었습니다"),
                                   ("en", "Experiment file is missing or invalid")):
            with self.subTest(language=language):
                environment = dict(os.environ, AGENT_OPT_LANG=language)
                result = subprocess.run([str(ROOT / ".venv/bin/agent-opt"), "doctor", "--plan", str(plan)],
                                        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertIn(expected, result.stdout)
                machine = subprocess.run([str(ROOT / ".venv/bin/agent-opt"), "doctor", "--plan", str(plan), "--json"],
                                         cwd=ROOT, env=environment, capture_output=True, text=True, timeout=10)
                self.assertEqual(machine.returncode, 2)
                self.assertEqual(json.loads(machine.stdout)["checks"][0]["message"],
                                 "Experiment file is missing or invalid")

    def test_model_diagnostic_translates_guidance_without_changing_identifiers(self):
        from agent_optimizer.locale import render_diagnostic

        row = {"id": "model.configuration", "status": "error",
               "message": "Required model configuration is present",
               "remedy": "Set AGENT_OPT_MODEL_ENDPOINT (or AGENT_OPT_MODEL_BASE_URL) and AGENT_OPT_MODEL_API_KEY for research optimizers; set AGENT_OPT_MODEL for OpenCode harnesses"}
        message, remedy = render_diagnostic(row, lang="ko")
        self.assertIn("필요한 모델 설정", message)
        self.assertIn("연구 Optimizer", remedy)
        self.assertIn("AGENT_OPT_MODEL_API_KEY", remedy)
        self.assertIn("AGENT_OPT_MODEL", remedy)
        self.assertEqual(row["message"], "Required model configuration is present")
        self.assertEqual(render_diagnostic(row, lang="en"), (row["message"], row["remedy"]))


if __name__ == "__main__":
    unittest.main()
