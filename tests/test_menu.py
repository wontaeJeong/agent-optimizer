"""Bounded menu flows and real public entrypoints, without external services."""
import contextlib
import io
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.models import ModelSettings
from support import ROOT, module


class TerminalOutput(io.StringIO):
    def isatty(self):
        return True


class MenuFlows(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / "scripts/menu.py").is_file(), "numbered menu is absent")
        self.menu = module("menu_flows", ROOT / "scripts/menu.py")
        temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.env = {"MODEL_ENDPOINT": "https://example.invalid/chat/completion",
                    "MODEL_API_KEY": "inherited-secret"}

    def flow(self, inputs, *, env=None, token="", codes=()):
        calls = []
        codes = iter(codes)

        def execute(argv, *, cwd, env, shell):
            self.assertFalse(shell)
            self.assertEqual(cwd, self.root)
            calls.append((argv, env.copy()))
            return subprocess.CompletedProcess(argv, next(codes, 0))

        output = TerminalOutput()
        before = dict(os.environ)
        with patch.object(self.menu, "ROOT", self.root), patch.object(
            self.menu.sys.stdin, "isatty", return_value=True
        ), patch(
            "builtins.input", side_effect=inputs
        ), patch.object(self.menu.getpass, "getpass", return_value=token), patch.object(
            self.menu.subprocess, "run", side_effect=execute
        ), contextlib.redirect_stdout(output):
            code = self.menu.main([], env=self.env if env is None else env)
        self.assertEqual(dict(os.environ), before)
        return code, output.getvalue(), calls

    def test_invalid_choice_exit_and_eof_do_no_work(self):
        for inputs in (["$(touch bad)", "9", "0"], [EOFError()]):
            code, _, calls = self.flow(inputs)
            self.assertEqual(code, 0)
            self.assertEqual(calls, [])
            self.assertEqual(list(self.root.iterdir()), [])

    def test_interrupt_exits_130(self):
        code, _, calls = self.flow([KeyboardInterrupt()])
        self.assertEqual(code, 130)
        self.assertEqual(calls, [])

    def test_setup_doctor_delegate_and_failure_returns_without_retry(self):
        code, output, calls = self.flow(["1", "2", "0"], codes=[7, 0])
        self.assertEqual(code, 0)
        self.assertIn("exit 7", output)
        self.assertEqual([c[0] for c in calls], [
            ["sh", str(self.root / "scripts/bootstrap.sh"), "setup", "--core"],
            ["sh", str(self.root / "scripts/bootstrap.sh"), "doctor", "--core"],
        ])
        self.assertEqual(calls[0][1], self.env)

    def test_option_seven_explicitly_prepares_full_ace_environment(self):
        code, output, calls = self.flow(["7", "0"])
        self.assertEqual(code, 0)
        self.assertEqual([c[0] for c in calls], [["sh", str(self.root / "scripts/bootstrap.sh"), "setup"]])
        self.assertIn("7. ACE", output)

    def test_option_eight_delegates_to_venv_tui_and_reports_child_failure(self):
        cli = self.root / ".venv/bin/agent-opt"
        cli.parent.mkdir(parents=True)
        cli.touch()
        code, output, calls = self.flow(["8", "0"], codes=[7])
        self.assertEqual(code, 7)
        self.assertEqual([call[0] for call in calls], [[str(cli), "tui"]])
        self.assertIn("exit 7", output)
        self.assertIn("8.", output)

    def test_option_eight_later_success_resets_prior_child_failure(self):
        cli = self.root / ".venv/bin/agent-opt"
        cli.parent.mkdir(parents=True)
        cli.touch()
        code, output, calls = self.flow(["8", "8", "0"], codes=[7, 0])
        self.assertEqual(code, 0)
        self.assertEqual([call[0] for call in calls], [[str(cli), "tui"], [str(cli), "tui"]])
        self.assertEqual(output.count("exit 7"), 1)

    def test_option_eight_missing_venv_does_not_attempt_install(self):
        code, output, calls = self.flow(["8", "0"])
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        self.assertIn("setup --core", output)

    def test_demo_requires_existing_venv(self):
        _, output, calls = self.flow(["3", "0"])
        self.assertIn("sh scripts/bootstrap.sh setup --core", output)
        self.assertEqual(calls, [])

    def venv(self):
        python = self.root / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)
        return python

    def test_demo_then_focused_local_feedback_regression(self):
        python = self.venv()
        _, output, calls = self.flow(["3", "0"])
        self.assertEqual(calls[0][0], ["sh", str(self.root / "scripts/bootstrap.sh"), "demo"])
        self.assertEqual(calls[1][0], [str(python), "-m", "unittest", "discover", "-s", "tests",
                                       "-p", "test_feedback_optimizer.py", "-v"])
        self.assertIn("회귀 테스트", output)
        self.assertEqual(len(calls), 2)

    def test_demo_failure_stops_second_stage_and_test_failure_is_reported(self):
        self.venv()
        for codes, count in [([4], 1), ([0, 5], 2)]:
            with self.subTest(codes=codes):
                _, output, calls = self.flow(["3", "0"], codes=codes)
                self.assertEqual(len(calls), count)
                self.assertIn(f"exit {codes[-1]}", output)

    def test_model_base_switch_override_and_session_only_token(self):
        before = self.env.copy()
        _, output, calls = self.flow(["4", "2", "https://example.invalid/v1", "other-model", "2", "0"],
                                     token="new-hidden-secret")
        self.assertEqual(self.env, before)
        self.assertNotIn("new-hidden-secret", output)
        self.assertNotIn("inherited-secret", output)
        self.assertEqual(calls[0][0][-2:], ["doctor", "--model"])
        child = calls[0][1]
        self.assertNotIn("MODEL_ENDPOINT", child)
        self.assertEqual(child["MODEL_BASE_URL"], "https://example.invalid/v1")
        self.assertEqual(ModelSettings.from_env(child).endpoint, "https://example.invalid/v1/chat/completions")
        self.assertEqual(child["MODEL_ID"], "other-model")
        self.assertEqual(child["MODEL_API_KEY"], "new-hidden-secret")
        self.assertEqual(calls[1][1], child)

    def test_model_exact_switch_default_model_and_empty_token_keeps_inherited(self):
        env = {"MODEL_BASE_URL": "https://example.invalid/v1", "MODEL_API_KEY": "kept"}
        _, _, calls = self.flow(["4", "1", "https://example.invalid/chat/completion", "", "0"], env=env)
        child = calls[0][1]
        self.assertNotIn("MODEL_BASE_URL", child)
        self.assertEqual(ModelSettings.from_env(child).endpoint, "https://example.invalid/chat/completion")
        self.assertEqual(child["MODEL_ID"], "glm5.3-flash")
        self.assertEqual(child["MODEL_API_KEY"], "kept")

    def test_model_inherited_defaults(self):
        env = {**self.env, "MODEL_ID": "inherited-model"}
        _, _, calls = self.flow(["4", "", "", "", "0"], env=env)
        self.assertEqual(calls[0][1], env)

    def test_empty_inherited_model_id_uses_default_on_enter(self):
        env = {**self.env, "MODEL_ID": ""}
        code, _, calls = self.flow(["4", "", "", "", "0"], env=env)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][-2:], ["doctor", "--model"])
        self.assertEqual(calls[0][1]["MODEL_ID"], "glm5.3-flash")
        self.assertEqual(env["MODEL_ID"], "")

    def test_invalid_model_input_does_not_commit_partial_settings(self):
        for values in (["9"], ["1", "http://remote.invalid", ""],
                       ["1", "https://valid.invalid", "bad model"]):
            with self.subTest(values=values):
                _, output, calls = self.flow(["4", *values, "2", "0"], token="replacement")
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0][1], self.env)
                self.assertNotIn("replacement", output)

    def test_eof_during_model_edit_exits_without_execution_or_environment_change(self):
        for values in ([], ["2"], ["2", "https://new.invalid"]):
            code, _, calls = self.flow(["4", *values, EOFError()])
            self.assertEqual(code, 0)
            self.assertEqual(calls, [])

    def test_live_default_and_bounded_iterations(self):
        for value, expected in [("", "3"), ("1", "1"), ("20", "20")]:
            with self.subTest(value=value):
                _, _, calls = self.flow(["5", value, "0"])
                self.assertEqual(calls[0][0][-3:], ["live", "--iterations", expected])
                self.assertEqual(calls[0][1], self.env)

    def test_invalid_iterations_never_execute(self):
        for value in ["0", "21", "-1", "1.5", "x", "3; touch bad"]:
            with self.subTest(value=value):
                _, _, calls = self.flow(["5", value, "0"])
                self.assertEqual(calls, [])

    def test_missing_live_model_guides_to_option_four(self):
        _, output, calls = self.flow(["5", "0"], env={})
        self.assertIn("4", output)
        self.assertEqual(calls, [])

    def test_missing_empty_reports_need_no_setup(self):
        for exists in [False, True]:
            if exists:
                (self.root / "runs").mkdir()
            _, output, calls = self.flow(["6", "0"])
            self.assertIn("보고서가 없습니다", output)
            self.assertEqual(calls, [])

    def test_reports_show_current_content_and_reject_outside_links_and_paths(self):
        runs = self.root / "runs"
        first = runs / "20260922T000000Z-minimal/report.md"
        second = runs / "dev-live/20260922T000000Z-ace/report.md"
        for report in [first, second]:
            report.parent.mkdir(parents=True)
            report.write_text("CURRENT " + report.parent.name)
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "report.md").write_text("PRIVATE")
        (runs / "linked-directory").symlink_to(outside, target_is_directory=True)
        (first.parent / "other.txt").write_text("OTHER")
        linked = runs / "linked-file/report.md"
        linked.parent.mkdir()
        linked.symlink_to(outside / "report.md")
        _, output, calls = self.flow(["6", "1", "6", "2", "6", str(outside / "report.md"), "0"])
        self.assertIn("CURRENT 20260922T000000Z-minimal", output)
        self.assertIn("CURRENT 20260922T000000Z-ace", output)
        self.assertNotIn("PRIVATE", output)
        self.assertNotIn("OTHER", output)
        self.assertNotIn("linked-", output)
        self.assertEqual(calls, [])

    def test_symlink_runs_root_is_not_followed(self):
        outside = self.root / "outside/run"
        outside.mkdir(parents=True)
        (outside / "report.md").write_text("PRIVATE")
        (self.root / "runs").symlink_to(outside.parent, target_is_directory=True)
        _, output, _ = self.flow(["6", "0"])
        self.assertNotIn("PRIVATE", output)
        self.assertIn("보고서가 없습니다", output)

    def test_hidden_input_failure_aborts_without_echo_fallback(self):
        output = TerminalOutput()
        with patch.object(self.menu.sys.stdin, "isatty", return_value=True), patch(
            "builtins.input", side_effect=["4", "1", "", "", "2", "0"]
        ), patch.object(self.menu.getpass, "getpass", self.menu.getpass.fallback_getpass), patch.object(
            self.menu.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
        ) as run, contextlib.redirect_stdout(output):
            self.assertEqual(self.menu.main([], env=self.env), 0)
        self.assertEqual(len(run.call_args_list), 1)
        self.assertEqual(run.call_args.kwargs["env"], self.env)
        self.assertIn("취소", output.getvalue())

    def test_report_replaced_after_listing_cannot_escape_runs(self):
        report = self.root / "runs/run/report.md"
        report.parent.mkdir(parents=True)
        report.write_text("original")
        outside = self.root / "private"
        outside.write_text("PRIVATE")

        def replace_then_select(_prompt):
            report.unlink()
            report.symlink_to(outside)
            return "1"

        with patch.object(self.menu, "ROOT", self.root), patch("builtins.input", replace_then_select), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError):
                self.menu.reports()


class MenuEntrypoints(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(ROOT / "scripts", self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "src", self.root / "src", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(ROOT / "Makefile", self.root / "Makefile")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.jsonl"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("MODEL_")}
        self.env.update(PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        PYTHONDONTWRITEBYTECODE="1", MENU_LOG=str(self.log))
        # Intercept only selected external actions, never the public menu entrypoint.
        self.executable("sh", f'''#!{sys.executable}
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
if len(args) > 1 and args[1] in ("setup", "doctor", "demo", "live"):
    with open(os.environ["MENU_LOG"], "a") as stream:
        stream.write(json.dumps({{"argv": args, "cwd": os.getcwd(), "env": {{k: v for k, v in os.environ.items() if k.startswith("MODEL_")}}}}) + "\\n")
    sys.exit(int(os.environ.get("MENU_EXIT", "0")))
os.execv("/bin/sh", ["sh", *args])
''')
        for tool in ["uv", "docker", "git", "curl", "wget"]:
            self.executable(tool, "#!/bin/sh\nprintf 'unexpected tool probe' >&2\nexit 99\n")

    def executable(self, name, content):
        file = self.bin / name
        file.write_text(content)
        file.chmod(0o755)

    def entries(self):
        return [[sys.executable, str(self.root / "scripts/dev.py"), "menu"],
                ["/bin/sh", str(self.root / "scripts/bootstrap.sh"), "menu"],
                [shutil.which("make"), "-f", str(self.root / "Makefile"), "menu"]]

    def interact(self, argv, steps, env=None):
        master, slave = pty.openpty()
        process = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave,
                                   cwd=self.root, env=env or self.env, start_new_session=True)
        os.close(slave)
        captured = b""
        cursor = 0

        def read_until(marker):
            nonlocal captured, cursor
            deadline = time.monotonic() + 10
            while marker not in captured[cursor:]:
                if time.monotonic() > deadline:
                    self.fail(f"PTY waiting for {marker!r}: {captured!r}")
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        self.fail(f"PTY exited before {marker!r}: {captured!r}")
                    captured += chunk
            cursor = captured.index(marker, cursor) + len(marker)

        try:
            for prompt, text in steps:
                read_until(prompt.encode())
                os.write(master, text.encode())
            deadline = time.monotonic() + 10
            while process.poll() is None or select.select([master], [], [], 0)[0]:
                if time.monotonic() > deadline:
                    self.fail("menu did not exit")
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    captured += chunk
            return process.wait(timeout=3), captured.decode()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)

    def test_all_entrypoints_help_without_tools_or_writes(self):
        for entry in self.entries():
            argv = entry + (["ARGS=--help"] if "make" in Path(entry[0]).name else ["--help"])
            result = subprocess.run(argv, cwd=self.root, env=self.env, text=True, capture_output=True)
            with self.subTest(entry=entry):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("menu", result.stdout)
        self.assertFalse(self.log.exists())
        for name in ["runs", ".venv", "external", ".cache"]:
            self.assertFalse((self.root / name).exists())
        self.assertEqual(list(self.root.rglob("__pycache__")), [])

    def test_all_entrypoints_reject_non_tty(self):
        for entry in self.entries():
            result = subprocess.run(entry, input="0\n", cwd=self.root, env=self.env,
                                    text=True, capture_output=True)
            with self.subTest(entry=entry):
                self.assertEqual(result.returncode, 2)
                self.assertIn("TTY", result.stdout + result.stderr)
        self.assertFalse(self.log.exists())

    def test_piped_output_is_rejected_even_with_terminal_input(self):
        master, slave = pty.openpty()
        try:
            os.write(master, b"0\n")
            result = subprocess.run(self.entries()[0], stdin=slave, capture_output=True,
                                    cwd=self.root, env=self.env, text=True, timeout=5)
        finally:
            os.close(master)
            os.close(slave)
        self.assertEqual(result.returncode, 2)
        self.assertIn("TTY", result.stdout + result.stderr)

    def test_menu_startup_exit_is_read_only(self):
        code, output = self.interact(self.entries()[0], [("선택: ", "0\n")])
        self.assertEqual(code, 0)
        self.assertNotIn("unexpected tool", output)
        self.assertFalse(self.log.exists())
        for name in ["runs", ".venv", "external", ".cache"]:
            self.assertFalse((self.root / name).exists())

    def test_bootstrap_missing_python_guides_setup_without_installing(self):
        for name in ["python3", "python"]:
            self.executable(name, "#!/bin/sh\nexit 1\n")
        result = subprocess.run(self.entries()[1], input="0\n", capture_output=True,
                                cwd=self.root, env=self.env, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("sh scripts/bootstrap.sh setup", result.stderr)
        self.assertNotIn("unexpected tool", result.stderr)
        self.assertFalse(self.log.exists())

    def test_shell_help_does_not_even_probe_python(self):
        for name in ["python3", "python"]:
            self.executable(name, "#!/bin/sh\nprintf 'unexpected interpreter probe' >&2\nexit 99\n")
        result = subprocess.run(self.entries()[1] + ["--help"], capture_output=True,
                                cwd=self.root, env=self.env, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")

    def test_all_entrypoints_route_selection_to_bootstrap_and_propagate_failure(self):
        for entry in self.entries():
            with self.subTest(entry=entry):
                code, output = self.interact(entry, [("선택: ", "2\n"), ("선택: ", "0\n")],
                                             {**self.env, "MENU_EXIT": "8"})
                self.assertEqual(code, 0)
                self.assertIn("exit 8", output)
        self.assertTrue(self.log.exists(), "selected action was never launched")
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(len(calls), 3)
        for call in calls:
            self.assertEqual(call["argv"], [str(self.root / "scripts/bootstrap.sh"), "doctor", "--core"])
            self.assertEqual(call["cwd"], str(self.root))

    def test_real_hidden_token_reaches_only_child_environment(self):
        before = dict(os.environ)
        secret = "pty-only-secret-914"
        code, output = self.interact(self.entries()[0], [
            ("선택: ", "4\n"), ("URL 방식", "1\n"), ("MODEL_ENDPOINT", "https://example.invalid/chat/completion\n"),
            ("MODEL_ID", "\n"), ("Bearer token", secret + "\n"), ("선택: ", "5\n"),
            ("반복 횟수", "3\n"), ("선택: ", "0\n"),
        ])
        self.assertEqual(code, 0)
        self.assertNotIn(secret, output)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual([call["argv"][1:] for call in calls], [["doctor", "--model"], ["live", "--iterations", "3"]])
        for call in calls:
            self.assertEqual(call["env"]["MODEL_API_KEY"], secret)
            self.assertNotIn(secret, " ".join(call["argv"]))
            self.assertEqual(call["env"]["MODEL_ID"], "glm5.3-flash")
        self.assertEqual(dict(os.environ), before)


if __name__ == "__main__":
    unittest.main()
