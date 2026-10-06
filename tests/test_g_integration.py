"""G 실행 경계·읽기 전용 진단 통합 회귀(실모델/실 EDA 없음)."""
import os
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer import model_input, readiness
from agent_optimizer.registry import Registry
from support import test_project


class EnvironmentBoundaryTests(unittest.TestCase):
    def test_core_command_accepts_explicit_existing_venv_without_installation(self):
        import sys
        from support import module, ROOT
        dev = module('g_dev', ROOT / 'scripts/dev.py')
        with patch.dict(os.environ, {'AGENT_OPT_CORE_PYTHON': sys.executable}), \
             patch.object(dev.subprocess, 'run', return_value=type('Result', (), {'returncode': 0})()) as run:
            self.assertEqual(dev.run_core('lint'), 0)
        self.assertEqual(run.call_args_list[0].args[0][0], sys.executable)
        self.assertEqual(run.call_args_list[1].args[0], [sys.executable, '-m', 'ruff', 'check', '.'])
        self.assertTrue(all('sync' not in call.args[0] for call in run.call_args_list))

    def test_overlapping_contexts_serialize_and_restore_without_cross_session_key(self):
        entered, release, attempted, second_entered = (threading.Event() for _ in range(4))
        observed = []
        def first():
            with model_input.session_environment({'G_KEY': 'first'}):
                entered.set()
                release.wait(3)
                observed.append(os.environ.get('G_KEY'))
        def second():
            attempted.set()
            with model_input.session_environment({'G_KEY': 'second'}):
                second_entered.set()
                observed.append(os.environ.get('G_KEY'))
        with patch.dict(os.environ, {'G_KEY': 'original'}):
            a = threading.Thread(target=first)
            b = threading.Thread(target=second)
            a.start()
            self.assertTrue(entered.wait(2))
            b.start()
            self.assertTrue(attempted.wait(2))
            try:
                self.assertFalse(second_entered.wait(.1))
                self.assertEqual(model_input.environment_snapshot()['G_KEY'], 'original')
            finally:
                release.set()
                a.join(3)
                b.join(3)
            self.assertFalse(a.is_alive() or b.is_alive())
            self.assertEqual(observed, ['first', 'second'])
            self.assertEqual(os.environ['G_KEY'], 'original')

    def test_nested_context_exception_restores_outer_then_original(self):
        with patch.dict(os.environ, {'G_KEY': 'original'}):
            with model_input.session_environment({'G_KEY': 'outer'}):
                with self.assertRaises(ValueError):
                    with model_input.session_environment({'G_KEY': 'inner'}):
                        self.assertEqual(os.environ['G_KEY'], 'inner')
                        raise ValueError('fixture')
                self.assertEqual(os.environ['G_KEY'], 'outer')
            self.assertEqual(os.environ['G_KEY'], 'original')


class HomeDiagnosisTests(unittest.TestCase):
    def test_report_port_failure_keeps_code_and_executable_quoted_retry(self):
        from agent_optimizer.report_view import start_view
        from agent_optimizer.report_server import ReportServerError
        row = {'run_dir': '/tmp/보고서 공백/run'}
        with patch('agent_optimizer.report_view.verified_report', return_value=Path('/tmp/report.html')), \
             patch('agent_optimizer.report_view.start_report_server', side_effect=ReportServerError('port_in_use', '포트 사용 중', error_number=48)):
            with self.assertRaises(ReportServerError) as raised:
                start_view(row, port=4321, retry="agent-opt report '/tmp/보고서 공백/run' --html --serve --no-open --port 4321")
        self.assertEqual(raised.exception.code, 'port_in_use')
        self.assertEqual(raised.exception.errno, 48)
        for text in ('Cause:', 'Fix:', "'/tmp/보고서 공백/run'", '--html --serve --no-open --port 4321', '127.0.0.1:4321'):
            self.assertIn(text, str(raised.exception))

    def test_static_doctor_rejects_relative_or_file_home_without_writes(self):
        temporary, root = test_project()
        self.addCleanup(temporary.cleanup)
        home = root / 'file-home'
        home.write_text('보존')
        plan = root / 'examples/minimal/experiment.toml'
        plan.write_text(plan.read_text().replace('output_dir = "runs"', ''))
        for value in ('relative-home', str(home)):
            with self.subTest(home=value), patch.dict(os.environ, {'AGENT_OPT_HOME': value}):
                report = readiness.collect_plan(plan, Registry())
                self.assertFalse(report['ready'])
                row = next(row for row in report['checks'] if row['id'] == 'app.paths')
                self.assertEqual(row['status'], 'error')
                self.assertIn('Retry:', row['remedy'])
                self.assertIn('Cause:', row['message'])
        self.assertEqual(home.read_text(), '보존')
        self.assertFalse((root / 'runs').exists())

    def test_config_seed_is_diagnosed_from_config_boundary(self):
        from agent_optimizer.preset_tui import write_ace_selection
        import json
        temporary, root = test_project()
        self.addCleanup(temporary.cleanup)
        tasks = root / 'datasets/ace-demo/tasks.json'
        tasks.parent.mkdir(parents=True)
        document = json.loads((root / 'examples/minimal/tasks.json').read_text())
        document['tasks'] = document['tasks'][:2]
        tasks.write_text(json.dumps(document))
        spec = readiness.load_experiment(write_ace_selection(root, 'meta_harness'))
        self.assertEqual(readiness._seed_check(spec)['status'], 'ok')
        target = next(iter(spec['candidate_seed_files']))
        source = spec['candidate_seed_files'][target]
        spec['candidate_seed_files'][target] = spec['benchmark']
        self.assertEqual(readiness._seed_check(spec)['status'], 'error')
        spec['candidate_seed_files'][target] = source
        Path(spec['_seed_root'] / next(iter(spec['candidate_seed_files'].values()))).unlink()
        self.assertEqual(readiness._seed_check(spec)['status'], 'error')


class UILifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_delayed_highlight_after_details_unmount_does_not_fail_shutdown(self):
        from agent_optimizer.tui import OptimizerApp
        temporary, root = test_project()
        self.addCleanup(temporary.cleanup)
        app = OptimizerApp(root)
        async with app.run_test() as pilot:
            await pilot.press('enter')
            await app.query_one('#details-panel').remove()
            app._detail(0)
            self.assertFalse(app.query('#details-panel').nodes)
