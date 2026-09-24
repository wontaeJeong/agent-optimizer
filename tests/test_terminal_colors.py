"""Color highlights terminal messages without changing redirected or machine output."""
import contextlib
import io
import json
import os
import pty
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_optimizer.cli import main
from agent_optimizer.terminal_report import PreparationStatus, ProgressDisplay
from support import ROOT, module, test_project


class TTYOutput(io.StringIO):
    def isatty(self):
        return True


class TerminalColorsTests(unittest.TestCase):
    def test_failed_trial_and_rejected_optimizer_iteration_are_not_successes(self):
        with patch.dict(os.environ, {"NO_COLOR": ""}):
            for event, expected in (({"event": "trial_completed", "status": "passed"}, "\x1b[32m"),
                                    ({"event": "trial_completed", "status": "failed"}, "\x1b[31m"),
                                    ({"event": "trial_completed", "status": "error"}, "\x1b[31m"),
                                    ({"event": "optimizer_iteration_completed", "accepted": False}, "\x1b[33m"),
                                    ({"event": "optimizer_iteration_completed",
                                      "status": "invalid_interface"}, "\x1b[31m")):
                with self.subTest(event=event):
                    output = TTYOutput()
                    ProgressDisplay(stream=output)({"timestamp": "2026-09-24T10:00:00Z", **event})
                    self.assertIn(expected, output.getvalue())

    def test_cli_argument_errors_are_red_on_tty(self):
        error = TTYOutput()
        with patch.dict(os.environ, {"NO_COLOR": ""}), contextlib.redirect_stderr(error):
            with self.assertRaises(SystemExit):
                main(["run"])
        self.assertIn("\x1b[31m", error.getvalue())

    def test_developer_argument_errors_are_red_on_tty(self):
        dev = module("color_dev_args", ROOT / "scripts/dev.py")
        error = TTYOutput()
        with patch.dict(os.environ, {"NO_COLOR": ""}), contextlib.redirect_stderr(error):
            with self.assertRaises(SystemExit):
                dev.main(["setup", "--not-a-flag"])
        self.assertIn("\x1b[31m", error.getvalue())

    def test_developer_setup_highlights_progress_without_coloring_summary_json(self):
        dev = module("color_dev", ROOT / "scripts/dev.py")
        output = TTYOutput()
        doctor = SimpleNamespace(collect_report=lambda *a, **k: {"ready": True},
                                 render_report=lambda *a: None)
        with patch.dict(os.environ, {"NO_COLOR": "", "AGENT_OPT_BOOTSTRAPPED": str(ROOT)}), \
                patch.object(dev.os, "chdir"), patch.object(dev, "load", return_value=doctor), \
                patch.object(dev, "run_core", return_value=0), contextlib.redirect_stdout(output):
            self.assertEqual(dev.main(["setup", "--core"]), 0)
        self.assertIn("\x1b[33m", output.getvalue())
        self.assertIn("\x1b[32m", output.getvalue())
        self.assertEqual(json.loads(output.getvalue().splitlines()[-1])["status"], "ready")

    def test_developer_command_failure_is_red_on_tty(self):
        dev = module("color_dev_failure", ROOT / "scripts/dev.py")
        output = TTYOutput()
        results = [SimpleNamespace(returncode=0), SimpleNamespace(returncode=7)]
        with patch.dict(os.environ, {"NO_COLOR": ""}), \
                patch.object(dev.subprocess, "run", side_effect=results), \
                contextlib.redirect_stdout(output):
            self.assertEqual(dev.run_core("lint"), 7)
        self.assertIn("\x1b[31m", output.getvalue())
        self.assertIn("lint failed (exit 7)", re.sub(r"\x1b\[[0-9;]*m", "", output.getvalue()))

    def test_interactive_menu_highlights_title_and_invalid_choice(self):
        menu = module("color_menu", ROOT / "scripts/menu.py")
        output = TTYOutput()
        with patch.dict(os.environ, {"NO_COLOR": ""}), patch.object(sys.stdin, "isatty", return_value=True), \
                patch("builtins.input", side_effect=["9", "0"]), contextlib.redirect_stdout(output):
            self.assertEqual(menu.main([]), 0)
        self.assertIn("\x1b[36m", output.getvalue())
        self.assertIn("\x1b[33m", output.getvalue())

    def test_interactive_wizard_highlights_heading_and_prompt(self):
        from agent_optimizer.setup_wizard import wizard_arguments

        temporary, root = test_project()
        self.addCleanup(temporary.cleanup)
        output = TTYOutput()
        with patch.dict(os.environ, {"NO_COLOR": ""}), contextlib.redirect_stderr(output), \
                patch("builtins.input", side_effect=EOFError):
            with self.assertRaises(EOFError):
                wizard_arguments(root)
        self.assertIn("\x1b[36m", output.getvalue())
        self.assertIn("\x1b[33m", output.getvalue())

    def run_make_tty(self, *args, no_color="", stderr_tty=True, executable="make",
                     cwd=ROOT, extra_env=None):
        master, slave = pty.openpty()
        process = None
        try:
            process = subprocess.Popen([executable, *args], cwd=cwd, stdin=subprocess.DEVNULL,
                                       stdout=slave, stderr=slave if stderr_tty else subprocess.PIPE,
                                       shell=False,
                                       env={**os.environ, "NO_COLOR": no_color, **(extra_env or {})})
            chunks = []
            deadline = time.monotonic() + 40
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError("make did not finish")
                if not select.select([master], [], [], 0.1)[0]:
                    if process.poll() is not None:
                        break
                    continue
                chunk = os.read(master, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            return process.wait(timeout=5), b"".join(chunks).decode()
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            if process is not None and process.stderr is not None:
                process.stderr.close()
            os.close(slave)
            os.close(master)

    def test_make_help_and_validation_error_highlight_on_tty(self):
        code, help_text = self.run_make_tty("help")
        self.assertEqual(code, 0, help_text)
        self.assertIn("\x1b[36m", help_text)
        code, error = self.run_make_tty("doctor", "ARGS=--core --dataset sample_text")
        self.assertNotEqual(code, 0)
        self.assertIn("\x1b[31m", error)

    def test_shell_setup_highlights_prerequisites_and_install_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "bin").mkdir()
            shutil.copyfile(ROOT / "scripts/bootstrap.sh", root / "scripts/bootstrap.sh")
            fake_uv = root / "bin/uv"
            fake_uv.write_text("#!/bin/sh\nexit 2\n")
            fake_uv.chmod(0o755)
            code, output = self.run_make_tty(
                "scripts/bootstrap.sh", "setup", "--core", "--offline", executable="sh", cwd=root,
                extra_env={"PATH": f"{root / 'bin'}:{os.environ['PATH']}", "AGENT_OPT_CA_BUNDLE": ""})
            plain_code, plain = self.run_make_tty(
                "scripts/bootstrap.sh", "setup", "--core", "--offline", executable="sh", cwd=root,
                no_color="1", extra_env={"PATH": f"{root / 'bin'}:{os.environ['PATH']}",
                                         "AGENT_OPT_CA_BUNDLE": ""})
        self.assertEqual(code, 2, output)
        self.assertEqual(plain_code, 2, plain)
        self.assertIn("\x1b[33m[setup] core prerequisites", output)
        self.assertIn("\x1b[32m[setup] prerequisites: complete", output)
        self.assertIn("\x1b[33m[setup] project Python", output)
        self.assertNotIn("\x1b[", plain)

    def test_make_respects_no_color_and_json_output(self):
        code, help_text = self.run_make_tty("help", no_color="1")
        self.assertEqual(code, 0)
        self.assertNotIn("\x1b[", help_text)
        code, text = self.run_make_tty("doctor", "ARGS=--core --json", stderr_tty=False)
        self.assertIn(code, (0, 2), text)
        self.assertEqual(json.loads(text)["scope"], "core")
        self.assertNotIn("\x1b[", text)

    def test_cli_doctor_highlights_readiness_and_errors_on_tty(self):
        temporary, root = test_project()
        self.addCleanup(temporary.cleanup)
        output = TTYOutput()
        with patch.dict(os.environ, {"NO_COLOR": ""}), contextlib.redirect_stdout(output):
            self.assertEqual(main(["doctor", "--dataset", "sample_text",
                                   "--project-root", str(root)]), 0)
        self.assertIn("\x1b[32m", output.getvalue())
        self.assertIn("readiness: ready", re.sub(r"\x1b\[[0-9;]*m", "", output.getvalue()))
        error = TTYOutput()
        with patch.dict(os.environ, {"NO_COLOR": ""}), contextlib.redirect_stderr(error):
            self.assertEqual(main(["rerank"]), 2)
        self.assertIn("\x1b[31m", error.getvalue())
        self.assertIn("error: rerank", re.sub(r"\x1b\[[0-9;]*m", "", error.getvalue()))

    def test_cli_json_stays_parseable_even_on_tty(self):
        temporary, root = test_project()
        self.addCleanup(temporary.cleanup)
        output = TTYOutput()
        with patch.dict(os.environ, {"NO_COLOR": ""}), contextlib.redirect_stdout(output):
            self.assertEqual(main(["doctor", "--dataset", "sample_text", "--json",
                                   "--project-root", str(root)]), 0)
        self.assertTrue(json.loads(output.getvalue())["ready"])
        self.assertNotIn("\x1b[", output.getvalue())

    def test_no_color_disables_cli_and_progress_on_tty(self):
        output = TTYOutput()
        with patch.dict(os.environ, {"NO_COLOR": "1"}), contextlib.redirect_stderr(output):
            self.assertEqual(main(["rerank"]), 2)
            ProgressDisplay(stream=output)({"event": "error", "timestamp": "2026-09-24T10:00:00Z"})
        self.assertNotIn("\x1b[31m", output.getvalue())

    def test_progress_distinguishes_running_completed_and_error_events(self):
        output = TTYOutput()
        display = ProgressDisplay(stream=output)
        with patch.dict(os.environ, {"NO_COLOR": ""}):
            for name in ("trial_started", "trial_completed", "error"):
                display({"event": name, "timestamp": "2026-09-24T10:00:00Z"})
        text = output.getvalue()
        self.assertIn("\x1b[33m", text)
        self.assertIn("\x1b[32m", text)
        self.assertIn("\x1b[31m", text)

    def test_preparation_highlights_failure_but_redirected_output_is_plain(self):
        output = TTYOutput()
        with patch.dict(os.environ, {"NO_COLOR": ""}):
            with self.assertRaisesRegex(RuntimeError, "broken"):
                with PreparationStatus("sample_text", stream=output):
                    raise RuntimeError("broken")
        self.assertIn("\x1b[31m", output.getvalue())
        plain = io.StringIO()
        with PreparationStatus("sample_text", stream=plain):
            pass
        self.assertNotIn("\x1b[", plain.getvalue())

    def test_developer_doctor_uses_same_severity_colors_and_plain_redirects(self):
        doctor = module("color_dev_doctor", ROOT / "scripts/dev_doctor.py")
        report = {"scope": "core", "ready": False, "areas": {"core": False},
                  "checks": [{"status": "error", "id": "core.git", "message": "missing",
                              "remedy": "Install Git"}]}
        terminal = TTYOutput()
        with patch.dict(os.environ, {"NO_COLOR": ""}), contextlib.redirect_stdout(terminal):
            doctor.render_report(report)
        self.assertIn("\x1b[31m", terminal.getvalue())
        self.assertIn("\x1b[33m", terminal.getvalue())
        plain = io.StringIO()
        with contextlib.redirect_stdout(plain):
            doctor.render_report(report)
        self.assertNotIn("\x1b[", plain.getvalue())


if __name__ == "__main__":
    unittest.main()
