import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import signal
import select
import re
from urllib.request import urlopen
import unittest
from unittest.mock import patch

from agent_optimizer.cli import main
from agent_optimizer.config import load_experiment
from agent_optimizer.history import list_history, verified_report
from agent_optimizer.preset_tui import write_sample_selection
from agent_optimizer.registry import Registry
from agent_optimizer.runner import run_experiment
from agent_optimizer.report_view import open_browser as launch_browser

ROOT = Path(__file__).resolve().parents[1]


class ProductWiringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / 'home'
        env = patch.dict(os.environ, {'AGENT_OPT_HOME': str(self.home)})
        env.start()
        self.addCleanup(env.stop)

    def test_generated_fixture_home_provenance_run_history(self):
        config = write_sample_selection(ROOT, 'rtl-solo', 'baseline', name='f-fixture')
        self.assertTrue(config.is_relative_to(self.home / 'experiments'))
        spec = load_experiment(config)
        self.assertEqual(spec['_root'], ROOT)
        self.assertEqual(spec['_config_root'], config.parent)
        self.assertNotIn('output_dir', spec)
        run, summary = run_experiment(spec, Registry())
        self.assertEqual(summary['status'], 'completed')
        self.assertTrue(run.is_relative_to(self.home / 'runs'))
        rows = list_history(app_home=self.home)
        self.assertEqual(rows[0]['run_id'], run.name)
        self.assertEqual(verified_report(rows[0]), run / 'report.html')

    def test_report_conflicts_rejected_before_regeneration_or_server(self):
        run = self.base / 'run'
        run.mkdir()
        (run / 'summary.json').write_text('{"status":"completed"}')
        for options in (['--json', '--serve', '--html'], ['--no-open'], ['--port', '1234'], ['--csv', str(self.base / 'export.csv'), '--serve']):
            with self.subTest(options=options), patch('agent_optimizer.report_server.start_report_server') as server, contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['report', str(run), *options]), 2)
                self.assertEqual(stdout.getvalue(), '')
                server.assert_not_called()
                self.assertFalse((run / 'report.html').exists())
                self.assertFalse((self.base / 'export.csv').exists())

    def test_report_json_one_value(self):
        run = self.base / 'run'
        run.mkdir()
        (run / 'summary.json').write_text('{"status":"completed"}')
        with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['report', str(run), '--json']), 0)
        self.assertEqual(json.loads(stdout.getvalue()), {'status': 'completed'})

    def test_native_profile_loader_accepts_contract_and_rejects_secret_fields(self):
        import shutil
        config = write_sample_selection(ROOT, 'rtl-solo', 'baseline', name='loader')
        shutil.copyfile(ROOT / 'examples/ace-rtl/harness-native.toml', config.parent / 'harness.toml')
        manifest = (config.parent / 'agent.toml').read_text().replace('["fixture"]', '["ace_native"]')
        (config.parent / 'agent.toml').write_text(manifest)
        spec = load_experiment(config)
        self.assertEqual(spec['_profiles'][0]['compatibility']['roles'], ['generator', 'reflector', 'coordinator'])
        with (config.parent / 'harness.toml').open('a') as stream:
            stream.write('\napi_key = "KEY-SENTINEL"\n')
        with self.assertRaisesRegex(Exception, 'compatibility'):
            load_experiment(config)

    def test_native_adapter_registered_and_legacy_preserved(self):
        registry = Registry()
        registry.load_project(ROOT)
        self.assertEqual(registry.resolve('harnesses', 'ace_native').__name__, 'ACENative')
        from agent_optimizer.catalog import list_choices
        rows = {row['id']: row for row in list_choices('harness', ROOT)}
        self.assertEqual(rows['ace-native']['execution_mode'], 'native')
        self.assertIn('ace-opencode', rows)
        self.assertIn('ace-claude-code', rows)

    def test_native_selection_requires_explicit_rows_before_writing(self):
        from agent_optimizer.native_selection import write_native_selection
        for cids, rows in [([], {}), (['cid003'], {'r': 'validation'}), (['cid002'], {})]:
            with self.subTest(cids=cids, rows=rows), self.assertRaises(Exception):
                write_native_selection(ROOT, 'gepa', cids=cids, rows=rows, dataset=self.base / 'missing', source=self.base / 'missing')
        self.assertFalse(self.home.exists())

    def test_cli_generated_fixture_run_serve_get_and_sigint_cleanup(self):
        with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
            code = main(['init', '--project-root', str(ROOT), '--agent-preset', 'rtl-solo',
                         '--harness-profile', 'fixture', '--optimizer', 'baseline',
                         '--dataset', 'sample_text', '--name', 'cli-e2e', '--yes'])
        self.assertEqual(code, 0)
        config = Path(json.loads(stdout.getvalue())['experiment'])
        with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['run', str(config)]), 0)
        run = Path(json.loads(stdout.getvalue())['run_dir'])
        env = {**os.environ, 'PYTHONPATH': str(ROOT / 'src'), 'PYTHONDONTWRITEBYTECODE': '1'}
        proc = subprocess.Popen([sys.executable, '-m', 'agent_optimizer', 'report', str(run), '--serve', '--no-open'],
                                cwd=self.base, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertTrue(select.select([proc.stderr], [], [], 10)[0])
            line = proc.stderr.readline()
            notice = proc.stderr.readline() + proc.stderr.readline()
            url = re.search(r'http://127\.0\.0\.1:\d+/report.html', line).group()
            with urlopen(url, timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertIn('Agent Optimizer', response.read().decode())
            proc.send_signal(signal.SIGINT)
            out, err = proc.communicate(timeout=10)
            self.assertEqual(proc.returncode, 130)
            self.assertEqual(out, '')
            self.assertIn('localhost', notice + err)
            with self.assertRaises(OSError):
                urlopen(url, timeout=.2)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()

    def test_new_generated_config_ids_are_unique_and_original_agent_unchanged(self):
        original = (ROOT / 'examples/minimal/agents/solo/configs/strategy.json').read_bytes()
        first = write_sample_selection(ROOT, 'rtl-solo', 'baseline', name='same-name')
        second = write_sample_selection(ROOT, 'rtl-solo', 'baseline', name='same-name')
        self.assertNotEqual(first, second)
        self.assertEqual((ROOT / 'examples/minimal/agents/solo/configs/strategy.json').read_bytes(), original)

    def test_generated_config_seed_root_snapshot_and_editable_guard(self):
        from agent_optimizer.setup_wizard import _literal
        config = write_sample_selection(ROOT, 'rtl-solo', 'baseline', name='seed-root')
        original = (ROOT / 'examples/minimal/agents/solo/configs/strategy.json').read_bytes()
        manifest = config.parent / 'agent.toml'
        build = [sys.executable, '-c', 'from pathlib import Path; import sys; assert Path(sys.argv[1]).is_file()', 'agent/configs/strategy.json']
        manifest.write_text(manifest.read_text().replace('\n[source]', f'\nbuild = {_literal(build)}\n[source]'))
        (config.parent / 'seed.json').write_text('{"repair": true}')
        # Root declarations must precede the existing TOML sections.
        config.write_text('candidate_seed_root = "config"\n' + config.read_text() + '\n[candidate_seed_files]\n"configs/strategy.json" = "seed.json"\n')
        spec = load_experiment(config)
        self.assertEqual(spec['_seed_root'], config.parent)
        run, summary = run_experiment(spec, Registry())
        self.assertEqual(summary['groups'][0]['baseline']['metrics']['solve_rate'], 1.0)
        self.assertEqual((ROOT / 'examples/minimal/agents/solo/configs/strategy.json').read_bytes(), original)
        before = set(run.parent.iterdir())
        spec['candidate_seed_files'] = {'private/checker.py': 'seed.json'}
        with self.assertRaisesRegex(Exception, 'editable'):
            run_experiment(spec, Registry())
        self.assertEqual(set(run.parent.iterdir()), before)
        spec['candidate_seed_files'] = {'configs/strategy.json': 'tasks.json'}
        with self.assertRaisesRegex(Exception, 'benchmark'):
            run_experiment(spec, Registry())
        self.assertEqual(set(run.parent.iterdir()), before)

    def test_generated_local_git_locator_keeps_original_project_origin(self):
        from agent_optimizer.setup_wizard import prepare_selection, write_experiment
        dataset, plugins, dependencies = prepare_selection(ROOT, 'sample_text')
        config = write_experiment(self.home / 'experiments/git-origin', agent='relative-repo',
            harness={'adapter': 'fixture', 'revision': 'a' * 40}, dataset=dataset,
            stages=[], plugins=plugins, dependencies=dependencies, name='git-origin',
            editable=['prompts/system.md'], project_root=ROOT, max_tasks=3)
        self.assertEqual(load_experiment(config)['_agents'][0].source.url, str(ROOT / 'relative-repo'))

    def test_selected_source_helpers_stage_in_home_without_overwriting_conflicts(self):
        from agent_optimizer.integrations import stage_local_integration
        source = ROOT / 'examples/ace-rtl/prepare.py'
        original = source.read_bytes()
        assets = stage_local_integration(ROOT, 'cvdp')
        self.assertTrue(assets.is_relative_to(self.home / 'assets'))
        staged = assets / 'examples/ace-rtl/prepare.py'
        self.assertEqual(staged.read_bytes(), original)
        staged.write_text('사용자 변경 보존')
        with self.assertRaisesRegex(Exception, '충돌'):
            stage_local_integration(ROOT, 'cvdp')
        self.assertEqual(staged.read_text(), '사용자 변경 보존')
        self.assertEqual(source.read_bytes(), original)

    def test_default_browser_success_or_failure_keeps_url_and_closes_server(self):
        from agent_optimizer.cli import serve_report
        from agent_optimizer.history import record_lifecycle
        run = self.home / 'runs/20261001T000000Z-12345678'
        run.mkdir(parents=True)
        record_lifecycle(run, status='completed')
        (run / 'report.html').write_text('<html>보고서</html>')
        for successful in (True, False):
            urls = []
            def browser(argv, **kwargs):
                from types import SimpleNamespace
                url = argv[-1]
                urls.append(url)
                with urlopen(url, timeout=2) as response:
                    self.assertEqual(response.status, 200)
                if not successful:
                    raise OSError('PRIVATE-SENTINEL')
                self.assertFalse(kwargs['shell'])
                self.assertTrue(kwargs['start_new_session'])
                self.assertNotIn('AGENT_OPT_MODEL_API_KEY', kwargs['env'])
                return SimpleNamespace(wait=lambda timeout: 0, poll=lambda: 0)
            with self.subTest(successful=successful), patch('agent_optimizer.report_view.open_browser', launch_browser), patch('agent_optimizer.report_view.subprocess.Popen', side_effect=browser), patch('time.sleep', side_effect=KeyboardInterrupt), contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(serve_report(run), 130)
                self.assertEqual(stdout.getvalue(), '')
                self.assertIn(urls[0], stderr.getvalue())
                self.assertNotIn('PRIVATE-SENTINEL', stderr.getvalue())
            with self.assertRaises(OSError):
                urlopen(urls[0], timeout=.2)

    def test_unsafe_home_config_boundary_rejected_before_asset_preparation(self):
        self.home.mkdir()
        external = self.base / 'external'
        external.mkdir()
        (self.home / 'experiments').symlink_to(external, target_is_directory=True)
        with patch('agent_optimizer.preset_tui.prepare_ace_selection') as prepare, contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
            code = main(['init', '--project-root', str(ROOT), '--agent-preset', 'ace-rtl', '--harness-profile', 'ace-opencode',
                         '--dataset', 'cvdp', '--optimizer', 'gepa', '--name', 'unsafe', '--yes'])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), '')
        prepare.assert_not_called()
        self.assertEqual(list(external.iterdir()), [])

    def test_copied_legacy_benchmark_cannot_change_scoring_material(self):
        from support import test_project
        from agent_optimizer.preset_tui import write_ace_selection, verify_ace_selection
        temporary, project = test_project()
        self.addCleanup(temporary.cleanup)
        benchmark = project / 'datasets/ace-demo/tasks.json'
        benchmark.parent.mkdir(parents=True)
        document = json.loads((ROOT / 'examples/minimal/tasks.json').read_text())
        document['tasks'] = document['tasks'][:2]
        benchmark.write_text(json.dumps(document))
        config = write_ace_selection(project, 'gepa')
        verify_ace_selection(load_experiment(config))
        document['tasks'][0]['evaluation']['expected'] = '변경된 채점 기준'
        (config.parent / 'tasks.json').write_text(json.dumps(document))
        with self.assertRaisesRegex(Exception, '선택형 설정'):
            verify_ace_selection(load_experiment(config))

    def test_browser_timeout_reaps_only_owned_helper_process(self):
        actual_popen = subprocess.Popen
        processes = []
        class ShortWait:
            def __init__(self, argv, **kwargs):
                self.process = actual_popen([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
                processes.append(self.process)
                self.pid = self.process.pid
            def wait(self, timeout):
                return self.process.wait(timeout=.05 if timeout == 5 else timeout)
            def poll(self):
                return self.process.poll()
        with patch('agent_optimizer.report_view.subprocess.Popen', ShortWait):
            self.assertFalse(launch_browser('http://127.0.0.1:12345/report.html'))
        self.assertIsNotNone(processes[0].returncode)
        self.assertNotEqual(processes[0].returncode, 0)
