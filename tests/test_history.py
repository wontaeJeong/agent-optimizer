import json
import io
import multiprocessing
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.contracts import ConfigurationError


TEMP = Path(tempfile.gettempdir()) / 'agent-optimizer-final-mvp-a'


class HistoryTests(unittest.TestCase):
    def setUp(self):
        TEMP.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=TEMP)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / 'home'

    def run_fixture(self, name='20261001T000000Z-12345678', status='completed', base=None):
        root = (base or self.home / 'runs') / name
        root.mkdir(parents=True)
        (root / 'summary.json').write_text(json.dumps({
            'schema_version': 1, 'run_id': name, 'status': status, 'groups': [], 'trials_used': 0}))
        (root / 'manifest.json').write_text(json.dumps({'experiment': {'name': '실험'}}))
        return root

    def test_empty_home_lookup_has_no_side_effects(self):
        from agent_optimizer.history import list_history
        self.assertEqual(list_history(app_home=self.home), [])
        self.assertFalse(self.home.exists())

    def test_reportless_runs_status_and_dedup_across_cwd(self):
        from agent_optimizer.history import list_history
        run = self.run_fixture()
        before = sorted(run.iterdir())
        rows = list_history(app_home=self.home, run_bases=[run.parent])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'completed')
        self.assertEqual(rows[0]['experiment_name'], '실험')
        self.assertEqual(rows[0]['run_dir'], str(run))
        self.assertIsNone(rows[0]['report_path'])
        self.assertTrue(rows[0]['diagnostic'])
        with patch('pathlib.Path.cwd', return_value=self.root / '다른 cwd'):
            self.assertEqual(rows, list_history(app_home=self.home))
        self.assertEqual(before, sorted(run.iterdir()))

    def test_missing_corrupt_and_unfinished_records_are_not_success(self):
        from agent_optimizer.history import list_history
        root = self.run_fixture(status='running')
        broken = self.run_fixture('20261001T000001Z-12345679', status='error')
        (broken / 'summary.json').write_text('{broken')
        (broken / 'manifest.json').unlink()
        unknown = self.home / 'runs/20261001T000002Z-12345670'
        unknown.mkdir()
        rows = {row['run_id']: row for row in list_history(app_home=self.home)}
        self.assertEqual(rows[root.name]['status'], 'stale')
        self.assertEqual(rows[broken.name]['status'], 'unknown')
        self.assertTrue(rows[broken.name]['diagnostic'])
        self.assertEqual(rows[unknown.name]['status'], 'unknown')

    def test_safe_report_revalidation_blocks_replacement_and_uri(self):
        from agent_optimizer.history import list_history, verified_report
        root = self.run_fixture()
        report = root / 'report.html'
        report.write_text('<html>fixture</html>')
        row = list_history(app_home=self.home)[0]
        self.assertEqual(verified_report(row), report)
        forged = {**row, 'report_path': 'file:///etc/passwd'}
        with self.assertRaises(ConfigurationError):
            verified_report(forged)
        report.unlink()
        report.symlink_to(self.root / 'external.html')
        with self.assertRaises(ConfigurationError):
            verified_report(row)

    def test_symlink_special_metadata_and_external_run_are_not_followed(self):
        from agent_optimizer.history import list_history, verified_report
        root = self.run_fixture()
        (root / 'summary.json').unlink()
        os.mkfifo(root / 'summary.json')
        (root / 'report.html').symlink_to(self.root / 'outside')
        outside = self.run_fixture('20261001T000001Z-12345679', base=self.root / 'outside-runs')
        (root.parent / outside.name).symlink_to(outside, target_is_directory=True)
        rows = list_history(app_home=self.home)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'unknown')
        self.assertIsNone(rows[0]['report_path'])
        self.assertTrue(rows.diagnostics)
        with self.assertRaises(ConfigurationError):
            verified_report(rows[0])

    def test_lifecycle_and_session_children_without_html(self):
        from agent_optimizer.history import list_history, record_lifecycle
        session = self.home / 'sessions/20261001T000000Z-87654321'
        child = self.run_fixture(status='interrupted', base=session / 'runs/01')
        record_lifecycle(session, status='interrupted', kind='session', children=[{
            'dataset': 'fixture', 'run_dir': child.relative_to(session).as_posix()}])
        rows = list_history(app_home=self.home)
        parent = next(row for row in rows if row['run_id'] == session.name)
        child_row = next(row for row in rows if row['run_id'] == child.name)
        self.assertEqual(parent['status'], 'interrupted')
        self.assertEqual(parent['child_runs'], [str(child)])
        self.assertEqual(child_row['session_id'], session.name)
        self.assertIsNone(parent['report_path'])

    def test_legacy_scored_failure_infrastructure_and_events(self):
        from agent_optimizer.history import list_history
        legacy = self.run_fixture(status='no_eligible_candidate', base=self.root / 'project/runs/dev-live')
        infra = self.run_fixture('20261001T000001Z-12345679', status='source_error')
        event = self.run_fixture('20261001T000002Z-12345670')
        (event / 'summary.json').unlink()
        (event / 'events.jsonl').write_text('{"event":"interrupted"}\n')
        rows = {row['run_id']: row for row in list_history(app_home=self.home, project_root=self.root / 'project')}
        self.assertEqual(rows[legacy.name]['status'], 'no_eligible_candidate')
        self.assertEqual(rows[infra.name]['status'], 'source_error')
        self.assertEqual(rows[event.name]['status'], 'interrupted')

    def test_runner_failure_and_interrupt_survive_report_writer_failure(self):
        from agent_optimizer.config import load_experiment
        from agent_optimizer.history import list_history
        from agent_optimizer.registry import Registry
        from agent_optimizer.runner import run_experiment
        root = Path(__file__).resolve().parents[1]
        for index, error in enumerate((KeyboardInterrupt(), RuntimeError('fixture'))):
            base = self.root / str(index)
            spec = load_experiment(root / 'examples/minimal/experiment.toml')
            with patch('agent_optimizer.runner.materialize_agent', side_effect=error), patch(
                    'agent_optimizer.results.write_report_artifacts', side_effect=RuntimeError('report fixture')):
                with self.assertRaises(RuntimeError):
                    run_experiment(spec, Registry(), base)
            rows = list_history(app_home=self.home, run_bases=[base])
            self.assertEqual(rows[0]['status'], 'interrupted' if index == 0 else 'source_error')
            self.assertIsNone(rows[0]['report_path'])
            self.assertTrue((Path(rows[0]['run_dir']) / 'lifecycle.json').is_file())

    def test_session_workers_record_child_run_references(self):
        from agent_optimizer.session import run_session
        from agent_optimizer.terminal_report import SessionProgress
        from agent_optimizer.history import list_history
        root = Path(__file__).resolve().parents[1]
        experiment = str(root / 'examples/minimal/experiment.toml')
        session = self.home / 'sessions/20261001T000000Z-87654321'
        session.mkdir(parents=True)
        with patch.dict(os.environ, {'AGENT_OPT_HOME': str(self.home)}), SessionProgress(
                ['first', 'second'], stream=io.StringIO()) as progress:
            entries = run_session([{'dataset': 'first', 'experiment': experiment},
                                   {'dataset': 'second', 'experiment': experiment}],
                                  session, jobs=2, progress=progress)
        self.assertEqual([entry['status'] for entry in entries], ['completed', 'completed'])
        for entry in entries:
            self.assertTrue((session / entry['run_dir'] / 'lifecycle.json').is_file())
        rows = list_history(app_home=self.home)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row['session_id'] == session.name for row in rows))
        self.assertEqual(json.loads((session / 'lifecycle.json').read_text())['status'], 'completed')

    def test_session_infrastructure_error_has_reportless_lifecycle(self):
        from agent_optimizer.session import run_session
        from agent_optimizer.terminal_report import SessionProgress
        from agent_optimizer.history import list_history
        session = self.home / 'sessions/20261001T000000Z-87654321'
        with SessionProgress(['missing'], stream=io.StringIO()) as progress:
            entries = run_session([{'dataset': 'missing', 'experiment': str(self.root / 'missing.toml')}],
                                  session, jobs=1, progress=progress)
        self.assertEqual(entries[0]['status'], 'error')
        row = list_history(app_home=self.home)[0]
        self.assertEqual(row['status'], 'error')
        self.assertIsNone(row['report_path'])

    def test_duplicate_run_id_and_symlink_parent_are_not_scanned_twice(self):
        from agent_optimizer.history import list_history
        run = self.run_fixture()
        self.run_fixture(base=self.root / 'copied-runs')
        parent = self.root / 'linked-parent'
        parent.symlink_to(self.home, target_is_directory=True)
        rows = list_history(app_home=self.home, run_bases=[self.root / 'copied-runs', parent / 'runs'])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['run_dir'], str(run))

    def test_session_report_and_external_metadata_links_are_revalidated(self):
        from agent_optimizer.history import list_history, record_lifecycle, verified_report
        session = self.home / 'sessions/20261001T000000Z-87654321'
        record_lifecycle(session, status='completed', kind='session', children=[
            {'run_dir': '/etc', 'report': 'file:///etc/passwd'}])
        (session / 'index.html').write_text('<html>fixture</html>')
        row = list_history(app_home=self.home)[0]
        self.assertEqual(row['child_runs'], [])
        self.assertEqual(verified_report(row), session / 'index.html')
        old = session.with_name('moved')
        session.rename(old)
        session.symlink_to(old, target_is_directory=True)
        with self.assertRaises(ConfigurationError):
            verified_report(row)

    def test_session_interrupt_records_pending_and_child_links(self):
        from agent_optimizer.session import SessionInterrupted, run_session
        from agent_optimizer.terminal_report import SessionProgress
        from agent_optimizer.history import list_history
        root = Path(__file__).resolve().parents[1]
        session = self.home / 'sessions/20261001T000000Z-87654321'
        items = [{'dataset': str(index), 'experiment': str(root / 'examples/minimal/experiment.toml')}
                 for index in range(2)]
        progress = SessionProgress(['first', 'second'], stream=io.StringIO())
        with progress, patch.object(progress, 'event', side_effect=KeyboardInterrupt):
            with self.assertRaises(SessionInterrupted):
                run_session(items, session, jobs=1, progress=progress)
        lifecycle = json.loads((session / 'lifecycle.json').read_text())
        self.assertEqual(lifecycle['status'], 'interrupted')
        self.assertEqual([child['status'] for child in lifecycle['children']], ['interrupted', 'interrupted'])
        row = next(row for row in list_history(app_home=self.home) if row['kind'] == 'session')
        self.assertEqual(row['status'], 'interrupted')
        self.assertEqual(len(row['child_runs']), 1)

    def test_skipped_base_diagnostics_do_not_require_a_fake_run(self):
        from agent_optimizer.history import list_history
        self.home.mkdir()
        (self.home / 'runs').symlink_to(self.root / 'external')
        rows = list_history(app_home=self.home)
        self.assertEqual(rows, [])
        self.assertTrue(rows.diagnostics)

    def test_session_setup_failure_records_infrastructure_error(self):
        from agent_optimizer.session import run_session
        from agent_optimizer.terminal_report import SessionProgress
        from agent_optimizer.history import list_history
        session = self.home / 'sessions/20261001T000000Z-87654321'
        with SessionProgress(['fixture'], stream=io.StringIO()) as progress, patch(
                'agent_optimizer.session.multiprocessing.get_context', side_effect=OSError('fixture')):
            with self.assertRaises(OSError):
                run_session([], session, jobs=1, progress=progress)
        self.assertEqual(next(row for row in list_history(app_home=self.home)
                              if row['run_id'] == session.name)['status'], 'error')

    def test_session_callback_failure_cleans_workers_and_records_error(self):
        from agent_optimizer.session import run_session
        from agent_optimizer.terminal_report import SessionProgress
        from agent_optimizer.history import list_history
        root = Path(__file__).resolve().parents[1]
        session = self.home / 'sessions/20261001T000000Z-87654321'
        existing = {child.pid for child in multiprocessing.active_children()}
        progress = SessionProgress(['fixture'], stream=io.StringIO())
        with progress, patch.object(progress, 'event', side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError):
                run_session([{'dataset': 'fixture', 'experiment': str(root / 'examples/minimal/experiment.toml')}],
                            session, jobs=1, progress=progress)
        self.assertEqual(next(row for row in list_history(app_home=self.home)
                              if row['run_id'] == session.name)['status'], 'error')
        self.assertEqual({child.pid for child in multiprocessing.active_children()}, existing)

    def test_structurally_invalid_summary_cannot_claim_success(self):
        from agent_optimizer.history import list_history
        run = self.run_fixture()
        (run / 'summary.json').write_text(json.dumps({'schema_version': 1, 'run_id': run.name,
                                                     'status': 'completed', 'groups': '손상', 'trials_used': -1}))
        rows = list_history(app_home=self.home)
        self.assertEqual(rows[0]['status'], 'unknown')
        self.assertIsNone(rows[0]['trials_used'])
        self.assertTrue(rows.diagnostics)

    def session_fixture(self, base, *, lifecycle=None):
        from agent_optimizer.history import record_lifecycle
        session = base / '20261001T000000Z-87654321'
        child = self.run_fixture('20261001T000001Z-12345678', base=session / 'runs/01')
        (session / 'index.html').write_text('<html>fixture</html>')
        entries = [{'dataset': 'fixture', 'status': 'completed', 'trials_used': 0,
                    'report': (child / 'report.html').relative_to(session).as_posix()}]
        (session / 'summary.json').write_text(json.dumps({'status': 'completed', 'experiments': entries}))
        if lifecycle is not None:
            record_lifecycle(session, status=lifecycle, kind='session')
        return session, child

    def test_explicit_custom_parent_recognizes_lifecycle_session_and_children(self):
        from agent_optimizer.history import list_history, verified_report
        session, child = self.session_fixture(self.root / '사용자 session 부모', lifecycle='completed')
        (session / 'summary.json').unlink()
        rows = list_history(app_home=self.home, run_bases=(session.parent,))
        row = next(row for row in rows if row['run_id'] == session.name)
        self.assertEqual(row['kind'], 'session')
        self.assertEqual(row['status'], 'completed')
        self.assertEqual(row['child_runs'], [str(child)])
        self.assertEqual(verified_report(row), session / 'index.html')
        self.assertEqual(next(row for row in rows if row['kind'] == 'run')['session_id'], session.name)
        self.assertFalse(self.home.exists())

    def test_legacy_summary_only_session_is_found_in_project_and_custom_parent(self):
        from agent_optimizer.history import list_history, verified_report
        for layout in ('legacy', 'custom'):
            with self.subTest(layout=layout):
                project = self.root / layout
                session, child = self.session_fixture(project / 'sessions')
                before = (session / 'summary.json').read_bytes()
                options = {'project_root': project} if layout == 'legacy' else {'run_bases': (session.parent,)}
                rows = list_history(app_home=self.home, **options)
                row = next(row for row in rows if row['run_id'] == session.name)
                self.assertEqual(row['status'], 'completed')
                self.assertEqual(row['kind'], 'session')
                self.assertEqual(row['child_runs'], [str(child)])
                self.assertEqual(verified_report(row), session / 'index.html')
                self.assertEqual(before, (session / 'summary.json').read_bytes())
                self.assertFalse((session / 'lifecycle.json').exists())

    def test_explicit_mixed_parent_distinguishes_runs_and_sessions(self):
        from agent_optimizer.history import list_history
        for layout in ('custom', 'runs', 'sessions'):
            with self.subTest(layout=layout):
                home = self.root / layout / 'home'
                base = home / layout if layout != 'custom' else self.root / layout / 'mixed'
                session, child = self.session_fixture(base)
                run = self.run_fixture('20261001T000002Z-12345679', base=base)
                (run / 'report.html').write_text('<html>fixture</html>')
                rows = {row['run_id']: row for row in list_history(app_home=home, run_bases=(base,))}
                self.assertEqual(set(rows), {session.name, child.name, run.name})
                self.assertEqual(rows[session.name]['report_path'], str(session / 'index.html'))
                self.assertEqual(rows[run.name]['kind'], 'run')
                self.assertEqual(rows[run.name]['report_path'], str(run / 'report.html'))

    def test_running_summary_or_lifecycle_uses_actual_terminal_event(self):
        from agent_optimizer.history import list_history, record_lifecycle
        for mode in ('summary', 'lifecycle', 'both'):
            for status in ('interrupted', 'source_error', 'error', 'budget_exhausted'):
                with self.subTest(mode=mode, status=status):
                    base = self.root / (mode + status)
                    run = self.run_fixture(status='running', base=base)
                    if mode == 'lifecycle':
                        (run / 'summary.json').unlink()
                    if mode in {'lifecycle', 'both'}:
                        record_lifecycle(run, status='running')
                    (run / 'events.jsonl').write_text(json.dumps({'event': status}) + '\n')
                    row = list_history(app_home=self.home, run_bases=(base,))[0]
                    self.assertEqual(row['status'], status)
                    self.assertNotIn('종료 기록이 없습니다', row['diagnostic'] or '')

    def test_terminal_summary_wins_and_nonterminal_events_do_not_claim_completion(self):
        from agent_optimizer.history import list_history
        run = self.run_fixture()
        (run / 'events.jsonl').write_text('{"event":"interrupted"}\n')
        self.assertEqual(list_history(app_home=self.home)[0]['status'], 'completed')
        summary = json.loads((run / 'summary.json').read_text())
        summary['status'] = 'running'
        (run / 'summary.json').write_text(json.dumps(summary))
        (run / 'events.jsonl').write_text('{"event":"stage_completed"}\n')
        self.assertEqual(list_history(app_home=self.home)[0]['status'], 'stale')

    def test_terminal_event_after_damaged_event_line_is_still_used(self):
        from agent_optimizer.history import list_history
        run = self.run_fixture(status='running')
        (run / 'events.jsonl').write_text('{broken\n{"event":"interrupted"}\n')
        rows = list_history(app_home=self.home)
        self.assertEqual(rows[0]['status'], 'interrupted')
        self.assertTrue(rows.diagnostics)

    def test_invalid_session_summary_falls_back_to_terminal_lifecycle(self):
        from agent_optimizer.history import list_history
        invalid = ({'status': 'completed'}, {'status': 'completed', 'experiments': '손상'},
                   {'status': 'completed', 'experiments': []},
                   {'status': 'completed', 'experiments': [{}]},
                   {'status': 'completed', 'experiments': [{'dataset': 'fixture', 'status': 'completed',
                                                          'report': [], 'trials_used': 0}]},
                   {'status': 'completed', 'experiments': [{'dataset': 'fixture', 'status': 'error',
                                                          'report': None}]},
                   {'status': 'completed', 'experiments': ['손상']},
                   {'status': 'completed', 'experiments': [{'dataset': 1, 'status': 'completed', 'report': None}]},
                   {'status': 'completed', 'experiments': [{'dataset': 'fixture', 'status': [], 'report': None}]},
                   {'status': 'completed', 'experiments': [{'dataset': 'fixture', 'status': 'completed',
                                                          'report': 'file:///etc/passwd', 'trials_used': 0}]},
                   {'status': 'completed', 'experiments': [{'dataset': 'fixture', 'status': 'completed',
                                                          'report': '../outside.html'}]},
                   {'status': 'completed', 'experiments': [{'dataset': 'fixture', 'status': 'completed',
                                                          'report': None, 'run_dir': '/etc'}]},
                   {'status': 'completed', 'experiments': [{'dataset': 'fixture', 'status': 'completed',
                                                          'report': None, 'trials_used': -1}]},
                   {'status': 'completed', 'experiments': [{'dataset': 'fixture', 'status': 'completed',
                                                          'report': None, 'trials_used': False}]})
        for layout in ('home', 'custom'):
            for terminal in ('error', 'interrupted'):
                for index, document in enumerate(invalid):
                    with self.subTest(layout=layout, terminal=terminal, index=index):
                        home = self.root / f'{layout}-{terminal}-{index}'
                        base = home / 'sessions' if layout == 'home' else home / 'custom'
                        session, _ = self.session_fixture(base, lifecycle=terminal)
                        (session / 'summary.json').write_text(json.dumps(document))
                        options = {} if layout == 'home' else {'run_bases': (base,)}
                        rows = list_history(app_home=home, **options)
                        row = next(row for row in rows if row['run_id'] == session.name)
                        self.assertEqual(row['status'], terminal)
                        self.assertIn('summary.json', row['diagnostic'])

    def test_damaged_summary_only_session_cannot_claim_success_or_follow_links(self):
        from agent_optimizer.history import list_history
        session, child = self.session_fixture(self.root / 'custom')
        (session / 'summary.json').write_text(json.dumps({'status': 'completed', 'experiments': [
            {'dataset': 'fixture', 'status': 'completed', 'report': 'file:///etc/passwd',
             'run_dir': '/etc', 'trials_used': -1}]}))
        rows = list_history(app_home=self.home, run_bases=(session.parent,))
        row = next(row for row in rows if row['run_id'] == session.name)
        self.assertEqual(row['kind'], 'session')
        self.assertEqual(row['status'], 'unknown')
        self.assertEqual(row['child_runs'], [str(child)])
        self.assertIn('summary.json', row['diagnostic'])

    def test_real_process_cwds_read_identical_home_history(self):
        from agent_optimizer.history import record_lifecycle
        run = self.run_fixture()
        record_lifecycle(run, status='completed')
        source = Path(__file__).resolve().parents[1] / 'src'
        script = ('import json; from agent_optimizer.app_paths import resolve_app_home; '
                  'from agent_optimizer.history import list_history; '
                  'print(json.dumps(list_history(app_home=resolve_app_home()), ensure_ascii=False))')
        outputs = []
        for name in ('첫 cwd', '둘째 cwd'):
            cwd = self.root / name
            cwd.mkdir()
            result = subprocess.run([sys.executable, '-c', script], cwd=cwd,
                                    env={**os.environ, 'PYTHONPATH': str(source),
                                         'AGENT_OPT_HOME': str(self.home)},
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append(json.loads(result.stdout))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0][0]['run_dir'], str(run))

    def test_valid_run_summary_is_not_reclassified_by_stray_session_html(self):
        from agent_optimizer.history import list_history
        run = self.run_fixture(base=self.root / 'explicit')
        (run / 'report.html').write_text('<html>run fixture</html>')
        (run / 'index.html').write_text('<html>오래된 파일</html>')
        row = list_history(app_home=self.home, run_bases=(run.parent,))[0]
        self.assertEqual(row['kind'], 'run')
        self.assertEqual(row['status'], 'completed')
        self.assertEqual(row['report_path'], str(run / 'report.html'))

    def test_legacy_partial_session_accepts_reportless_infrastructure_child(self):
        from agent_optimizer.history import list_history
        session, child = self.session_fixture(self.root / 'legacy')
        summary = json.loads((session / 'summary.json').read_text())
        summary['status'] = 'partial'
        summary['experiments'].append({'dataset': '미준비', 'status': 'error', 'report': None,
                                       'run_dir': None, 'error': 'fixture'})
        (session / 'summary.json').write_text(json.dumps(summary))
        row = next(row for row in list_history(app_home=self.home, run_bases=(session.parent,))
                   if row['run_id'] == session.name)
        self.assertEqual(row['status'], 'partial')
        self.assertEqual(row['child_runs'], [str(child)])
        self.assertIsNone(row['diagnostic'])

    def test_reportless_corrupt_legacy_session_uses_only_real_child_layout(self):
        from agent_optimizer.history import list_history
        session, child = self.session_fixture(self.root / 'legacy')
        (session / 'index.html').unlink()
        (session / 'summary.json').write_text('{broken')
        row = next(row for row in list_history(app_home=self.home, run_bases=(session.parent,))
                   if row['run_id'] == session.name)
        self.assertEqual(row['kind'], 'session')
        self.assertEqual(row['status'], 'unknown')
        self.assertEqual(row['child_runs'], [str(child)])
        self.assertIsNone(row['report_path'])
        self.assertIn('summary.json', row['diagnostic'])
