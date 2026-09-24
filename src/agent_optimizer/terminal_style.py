"""Small ANSI highlights for human-facing terminal output."""
import argparse
import os
import sys


COLORS = {"error": 31, "warning": 33, "success": 32, "heading": 36}


def style(text, tone, *, stream=None):
    stream = sys.stdout if stream is None else stream
    if os.environ.get("NO_COLOR") or not getattr(stream, "isatty", lambda: False)():
        return text
    return f"\x1b[{COLORS[tone]}m{text}\x1b[0m"


class ColorArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: {style('error:', 'error', stream=sys.stderr)} {message}\n")
