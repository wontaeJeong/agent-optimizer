import contextlib
import io
import os
import unittest
from unittest.mock import patch

from agent_optimizer.cli import main


class EntryTests(unittest.TestCase):
    def test_ci_with_tty_does_not_force_application(self):
        class TerminalBuffer(io.StringIO):
            def isatty(self):
                return True
        stdout, stderr = TerminalBuffer(), TerminalBuffer()
        with patch('sys.stdin.isatty', return_value=True), patch('sys.stdout', stdout), patch('sys.stderr', stderr), patch.dict(os.environ, {'CI': 'true', 'TERM': 'xterm'}), patch('agent_optimizer.tui.OptimizerApp.run') as run:
            self.assertEqual(main([]), 2)
            run.assert_not_called()
    def test_no_arguments_interactive_enters_existing_tui(self):
        with patch('sys.stdin.isatty', return_value=True), patch('sys.stdout.isatty', return_value=True), patch('sys.stderr.isatty', return_value=True), patch.dict(os.environ, {'TERM': 'xterm'}), patch('agent_optimizer.tui.OptimizerApp.run', return_value=0) as run:
            self.assertEqual(main([]), 0)
            run.assert_called_once()

    def test_help_and_noninteractive_never_enter_tui(self):
        for args, tty, term in [([], False, 'xterm'), ([], True, 'dumb'), (['--help'], True, 'xterm')]:
            with self.subTest(args=args, tty=tty, term=term), patch('sys.stdin.isatty', return_value=tty), patch('sys.stdout.isatty', return_value=tty), patch('sys.stderr.isatty', return_value=tty), patch.dict(os.environ, {'TERM': term}), patch('agent_optimizer.tui.OptimizerApp.run') as run, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertIn(main(args), (0, 2))
                run.assert_not_called()
