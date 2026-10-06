"""최종 사용자 여정에서 발견한 prepare 분기 회귀."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_optimizer.cli import main
from agent_optimizer.preset_tui import write_sample_selection


class FinalAcceptanceTests(unittest.TestCase):
    def test_native_prepare_resolves_source_subdir_like_runtime_and_doctor(self):
        import shutil
        from test_native_product import NativeProductTests, ROOT
        from agent_optimizer.native_selection import write_native_selection
        fixture = NativeProductTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        config = write_native_selection(ROOT, 'baseline', cids=['cid002'], rows=fixture.rows,
                                        dataset=fixture.data, source=fixture.source, evaluator=fixture.evaluator)
        container = fixture.base / 'container'
        nested = container / 'active'
        shutil.copytree(fixture.source, nested)
        manifest = config.parent / 'agent.toml'
        manifest.write_text(manifest.read_text().replace(str(fixture.source), str(container))
                            .replace('[source]', '[source]\nsubdir = "active"'))
        from agent_optimizer.config import load_experiment
        self.assertEqual(load_experiment(config)['_agents'][0].source.subdir, 'active')
        with patch.object(fixture.prep, 'probe_python', return_value={'ready': True}), \
             contextlib.redirect_stdout(io.StringIO()) as stdout, \
             contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(main(['prepare', str(config), '--offline']), 0, stderr.getvalue())
        self.assertTrue(json.loads(stdout.getvalue())['ready'])
        # An actual active-file hash mismatch must still fail, never use the sibling source.
        (nested / 'skills/ace-rtl/scripts/ace_cvdp_native/cli.py').write_text('# 변조\n')
        with patch.object(fixture.prep, 'probe_python', return_value={'ready': True}), \
             contextlib.redirect_stdout(io.StringIO()) as stdout, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['prepare', str(config), '--offline']), 2)
        self.assertEqual(stdout.getvalue(), '')
        self.assertFalse((fixture.base / 'home/runs').exists())

    def test_fixture_prepare_checks_existing_experiment_without_ace_or_run(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory, patch.dict(
                os.environ, {'AGENT_OPT_HOME': str(Path(directory) / 'home')}):
            config = write_sample_selection(root, 'rtl-solo', 'baseline')
            home = Path(directory)
            def snapshot():
                return {str(p): (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                        for p in (home, *home.rglob('*'))}
            before = snapshot()
            with patch('agent_optimizer.integrations.acquire_integration', side_effect=AssertionError('획득 금지')), \
                 patch('agent_optimizer.models.complete', side_effect=AssertionError('모델 호출 금지')), \
                 contextlib.redirect_stdout(io.StringIO()) as stdout, \
                 contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(main(['prepare', str(config), '--offline']), 0, stderr.getvalue())
            prepared = json.loads(stdout.getvalue())
            self.assertTrue(prepared['ready'])
            self.assertEqual(prepared['scope'], 'preflight')
            self.assertEqual(prepared['live'], 'not_run')
            self.assertEqual(before, snapshot())
            self.assertFalse((home / 'home/runs').exists())
            # A valid schema must not hide an unsupported implementation.
            manifest = config.parent / 'harness.toml'
            manifest.write_text(manifest.read_text().replace('adapter = "fixture"', 'adapter = "not-implemented"'))
            with contextlib.redirect_stdout(io.StringIO()) as stdout, \
                 contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['prepare', str(config), '--offline']), 2)
            self.assertEqual(stdout.getvalue(), '')
            self.assertFalse((home / 'home/runs').exists())
