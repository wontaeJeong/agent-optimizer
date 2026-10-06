"""PTY에서는 입력 없는 관측 단계가 같은 프레임의 다음 상태를 버리면 안 된다."""
from pathlib import Path
import sys
import tempfile
import unittest

from test_installed_cli import interact_tui


class InstalledPTYProtocolTests(unittest.TestCase):
    def test_observation_steps_preserve_later_markers_in_the_same_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            cli = root / 'fixture-cli'
            cli.write_text(f'#!{sys.executable}\n'
                           'import sys\n'
                           'print("initial observed next-ready", flush=True)\n'
                           'assert sys.stdin.readline().strip()=="q"\n')
            cli.chmod(0o755)
            transcript = interact_tui(cli, root, {'PATH': '/usr/bin:/bin'}, [
                ('initial', b''), ('observed', b''), ('next-ready', b'q\n')])
            self.assertIn('initial observed next-ready', transcript)
