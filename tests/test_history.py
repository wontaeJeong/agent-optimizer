import json
import io
import multiprocessing
import os
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
        self.assertEqual(list_history(app_home=self.home)[0]['status'], 'error')

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
        self.assertEqual(list_history(app_home=self.home)[0]['status'], 'error')
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
