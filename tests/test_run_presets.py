"""실행 프리셋 적용의 상태 격리와 실제 합성 E2E를 검증한다."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen
import asyncio

from textual.widgets import OptionList

from agent_optimizer.tui import OptimizerApp


ROOT = Path(__file__).resolve().parents[1]


async def choose(app, pilot, row_id):
    options = app.query_one(OptionList)
    options.highlighted = options.get_option_index(row_id)
    options.focus()
    await pilot.press('enter')
    await pilot.pause()


class RunPresetTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_apply_replaces_tasks_but_reuses_assets_and_invalidates_old_run(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'AGENT_OPT_HOME': directory}):
            app = OptimizerApp(ROOT)
            app.native_values = {'dataset': '/local/data.jsonl', 'source': '/local/source',
                                 'python': '/local/python', 'evaluator': {'repo': '/local/cvdp'},
                                 'cids': ['cid007'], 'rows': {'old': 'test'}}
            app.model_values['AGENT_OPT_MODEL_ID'] = 'session-model'
            async with app.run_test() as pilot:
                self.assertIn('presets', [row.id for row in app.rows])
                await choose(app, pilot, 'presets')
                # 조회만으로 이전 선택/실행을 변경하지 않는다.
                app.experiment = Path(directory) / 'old.toml'
                app.preparation_complete = True
                app.doctor_report = {'ready': True}
                options = app.query_one(OptionList)
                options.highlighted = options.get_option_index('native-cid002-gepa')
                await pilot.pause()
                self.assertEqual(app.native_values['rows'], {'old': 'test'})
                await pilot.press('enter')
                await pilot.pause()
                self.assertEqual(app.page, 'Native')
                self.assertEqual(app.selections, {'Agent': 'ace-rtl', 'Harness': 'ace-native',
                                                  'Optimizer': 'gepa', 'Dataset': 'cvdp'})
                self.assertEqual(app.native_values['cids'], ['cid002'])
                self.assertEqual(app.native_values['rows'], {
                    'cvdp_copilot_Attenuator_0001': 'train',
                    'cvdp_copilot_64b66b_decoder_0001': 'validation'})
                self.assertEqual(app.native_values['source'], '/local/source')
                self.assertEqual(app.model_values['AGENT_OPT_MODEL_ID'], 'session-model')
                self.assertIsNone(app.experiment)
                self.assertFalse(app.preparation_complete)
                self.assertIsNone(app.doctor_report)
                self.assertEqual(app.native_values['dataset'], '/local/data.jsonl')
                self.assertEqual(app.native_values['evaluator'], {'repo': '/local/cvdp'})
                await pilot.press('escape')
                self.assertEqual(app.page, 'Presets')
                await choose(app, pilot, 'native-cid016-baseline')
                self.assertEqual(app.native_values['rows'], {'cvdp_copilot_32_bit_Brent_Kung_PP_adder_0001': 'validation'})
                self.assertIn('최대 trial budget  1', app._review())

    async def test_fixture_preset_end_to_end_result_history_and_report(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'AGENT_OPT_HOME': directory}):
            app = OptimizerApp(ROOT)
            async with app.run_test() as pilot:
                await choose(app, pilot, 'presets')
                await choose(app, pilot, 'fixture-solo-file-variants')
                self.assertEqual(app.page, 'Review')
                self.assertIsNone(app.experiment)
                await choose(app, pilot, 'prepare')
                for _ in range(100):
                    await pilot.pause(.05)
                    if not app.busy:
                        break
                self.assertTrue(app.preparation_complete, app.preparation_error)
                await choose(app, pilot, 'doctor')
                for _ in range(100):
                    await pilot.pause(.05)
                    if not app.busy:
                        break
                self.assertTrue(app.doctor_report['ready'], app.doctor_report)
                await choose(app, pilot, 'run')
                for _ in range(200):
                    await pilot.pause(.05)
                    if app.page == 'Result':
                        break
                self.assertEqual(app.run_result['status'], 'completed', app.run_result)
                run = Path(app.run_result['run_dir'])
                self.assertTrue((run / 'report.html').is_file())
                app._show('History')
                self.assertTrue(any(row['run_dir'] == str(run) for row in app.history))
                with patch('agent_optimizer.report_view.open_browser', return_value=False):
                    await choose(app, pilot, run.name)
                    for _ in range(100):
                        await pilot.pause(.02)
                        if app._report_handle:
                            break
                    self.assertIsNotNone(app._report_handle)
                    html = await asyncio.to_thread(lambda: urlopen(app._report_handle.url, timeout=2).read().decode())
                    self.assertIn('<html', html)

    async def test_native_missing_assets_blocks_continue_without_creating_config(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'AGENT_OPT_HOME': directory}):
            app = OptimizerApp(ROOT)
            async with app.run_test(size=(50, 24)) as pilot:
                await choose(app, pilot, 'presets')
                await choose(app, pilot, 'native-cid004-meta_harness')
                options = app.query_one(OptionList)
                self.assertEqual(options.get_option_at_index(options.highlighted).id, 'dataset')
                await choose(app, pilot, 'native.continue')
                self.assertEqual(app.page, 'Native')
                self.assertFalse(app.busy)
                self.assertIsNone(app.experiment)
                self.assertFalse((Path(directory) / 'experiments').exists())

    async def test_legacy_preset_routes_to_its_model_without_native_task_selection(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'AGENT_OPT_HOME': directory}):
            app = OptimizerApp(ROOT)
            async with app.run_test() as pilot:
                await choose(app, pilot, 'presets')
                await choose(app, pilot, 'legacy-opencode-meta_harness')
                self.assertEqual(app.page, 'Model')
                self.assertEqual(app.selections['Harness'], 'ace-opencode')
                self.assertIn('AGENT_OPT_MODEL', app.model_fields)
                self.assertNotIn('rows', app.native_values)
                self.assertIsNone(app.experiment)
                await pilot.press('escape')
                self.assertEqual(app.page, 'Presets')

    async def test_missing_fixture_source_is_disabled_in_preset_menu(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'AGENT_OPT_HOME': directory}):
            app = OptimizerApp(Path(directory) / 'no-examples')
            async with app.run_test() as pilot:
                await choose(app, pilot, 'presets')
                fixture = next(row for row in app.rows if row.id == 'fixture-solo-baseline')
                self.assertFalse(fixture.enabled)
                await choose(app, pilot, fixture.id)
                self.assertEqual(app.page, 'Presets')
                self.assertIsNone(app.experiment)
