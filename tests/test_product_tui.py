import asyncio
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from agent_optimizer.history import record_lifecycle
from agent_optimizer.tui import OptimizerApp


class ProductTUITests(unittest.IsolatedAsyncioTestCase):
    async def test_result_explicit_output_parent_is_visible_in_shared_history(self):
        from agent_optimizer.preset_tui import write_sample_selection
        from agent_optimizer.config import load_experiment
        from agent_optimizer.registry import Registry
        from agent_optimizer.runner import run_experiment
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'AGENT_OPT_HOME': str(Path(directory) / 'home')}):
            base = Path(directory).resolve()
            config = write_sample_selection(root, 'rtl-solo', 'baseline')
            run, _ = run_experiment(load_experiment(config), Registry(), output=base / 'explicit-output')
            app = OptimizerApp(base / 'another-cwd')
            app.experiment = config
            app.run_result = {'run_dir': run}
            async with app.run_test() as pilot:
                app._show('History')
                await pilot.pause()
                self.assertEqual(len(app.history), 1)
                self.assertEqual(app.history[0]['run_dir'], str(run))

    async def test_reportless_history_visible_and_server_worker_cleanup(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'AGENT_OPT_HOME': directory}), patch('agent_optimizer.report_view.open_browser', side_effect=lambda url: (time.sleep(.2) or False)):
            home = Path(directory).resolve()
            failed = home / 'runs/20261001T000000Z-aaaaaaaa'
            failed.mkdir(parents=True)
            record_lifecycle(failed, status='interrupted')
            complete = home / 'runs/20261001T000001Z-bbbbbbbb'
            complete.mkdir()
            record_lifecycle(complete, status='completed')
            (complete / 'report.html').write_text('<html>로컬 보고서</html>')
            app = OptimizerApp(home / 'project')
            async with app.run_test() as pilot:
                app._show('History')
                self.assertEqual(len(app.rows), 2)
                self.assertIn('interrupted', app.rows[1].description)
                app.action_open_report(complete / 'report.html')
                app._show('Home')
                self.assertEqual(app.page, 'Home')
                for _ in range(40):
                    await pilot.pause(.025)
                    if app.home_status:
                        break
                self.assertIn('http://127.0.0.1:', app.home_status)
                url = app._report_handle.url
                text = await asyncio.to_thread(lambda: urlopen(url).read().decode())
                self.assertIn('로컬 보고서', text)
                previous = app._report_handle
                (complete / 'report.html').write_text('<html>재생성 보고서</html>')
                app.action_open_report(complete / 'report.html')
                for _ in range(40):
                    await pilot.pause(.025)
                    if app._report_handle is not None and app._report_handle is not previous:
                        break
                self.assertIsNot(app._report_handle, previous)
                url = app._report_handle.url
                text = await asyncio.to_thread(lambda: urlopen(url).read().decode())
                self.assertIn('재생성 보고서', text)
            with self.assertRaises(OSError):
                await asyncio.to_thread(lambda: urlopen(url, timeout=.2))

    async def test_session_history_selects_actual_child_report(self):
        from textual.widgets import OptionList
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'AGENT_OPT_HOME': directory}), patch('agent_optimizer.report_view.open_browser', return_value=False):
            home = Path(directory).resolve()
            session = home / 'sessions/20261001T000000Z-aaaaaaaa'
            children = []
            for index in (1, 2):
                run = session / f'runs/{index:02d}/20261001T00000{index}Z-bbbbbbb{index}'
                run.mkdir(parents=True)
                record_lifecycle(run, status='completed')
                (run / 'report.html').write_text(f'<html>child-{index}</html>')
                children.append({'dataset': str(index), 'status': 'completed', 'run_dir': run.relative_to(session).as_posix(),
                                 'report': (run / 'report.html').relative_to(session).as_posix(), 'trials_used': 1})
            record_lifecycle(session, status='completed', kind='session', children=children)
            (session / 'index.html').write_text('<html>session</html>')
            app = OptimizerApp(home / 'project')
            async with app.run_test() as pilot:
                app._show('History')
                options = app.query_one(OptionList)
                options.highlighted = options.get_option_index(session.name)
                options.focus()
                await pilot.press('enter')
                await pilot.pause()
                self.assertEqual(app.page, 'SessionHistory')
                self.assertEqual(len(app.rows), 2)
                await pilot.press('enter')
                for _ in range(40):
                    await pilot.pause(.025)
                    if app._report_handle:
                        break
                url = app._report_handle.url
                text = await asyncio.to_thread(lambda: urlopen(url).read().decode())
                self.assertIn('child-', text)
                self.assertNotIn('session', text)
