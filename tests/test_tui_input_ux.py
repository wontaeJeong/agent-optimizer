"""선택형 입력의 실제 키 조작·취소·설정 생성 회귀."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Input, OptionList, Select, SelectionList

from support import test_project, choose_row
from agent_optimizer.config import load_experiment
from agent_optimizer.tui import OptimizerApp


class InputUXTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary, self.root = test_project()
        self.addCleanup(self.temporary.cleanup)

    async def test_existing_starts_on_list_and_browser_loads_selected_file(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await choose_row(app, pilot, 'existing')
            self.assertIsInstance(app.focused, OptionList)
            await choose_row(app, pilot, 'path.browse')
            screen = app.screen
            screen.query_one('#path-value', Input).value = str(self.root / 'examples/minimal')
            screen.query_one('#path-value', Input).focus()
            await pilot.press('enter')
            options = screen.query_one('#path-options', OptionList)
            options.highlighted = next(i for i, p in enumerate(screen.paths) if p.name == 'experiment.toml')
            options.focus()
            await pilot.press('enter')
            await pilot.pause()
            self.assertEqual(app.page, 'Review')
            self.assertEqual(app.experiment, (self.root / 'examples/minimal/experiment.toml').resolve())

    async def test_cid_selection_is_explicit_and_cancel_keeps_original(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            app.selections = {'Agent': 'ace-rtl', 'Harness': 'ace-native', 'Optimizer': 'baseline', 'Dataset': 'cvdp'}
            app._show('Native')
            await choose_row(app, pilot, 'cids')
            choices = app.screen.query_one(SelectionList)
            self.assertEqual(choices.selected, [])
            await pilot.press('space')
            await pilot.click('#choice-apply')
            await pilot.pause()
            self.assertEqual(app.native_values['cids'], ['cid002'])
            await choose_row(app, pilot, 'cids')
            await pilot.press('down', 'space', 'escape')
            self.assertEqual(app.native_values['cids'], ['cid002'])

    async def test_batch_split_only_applies_to_explicit_supported_rows(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            app.native_rows_catalog = [
                {'id': 'A', 'cid': 'cid002', 'targets': ['rtl'], 'tools': [], 'supported': True, 'reason': ''},
                {'id': 'B', 'cid': 'cid002', 'targets': ['rtl'], 'tools': [], 'supported': True, 'reason': ''},
                {'id': 'PNR', 'cid': 'cid007', 'targets': [], 'tools': [], 'supported': False, 'reason': 'PNR 제외'},
            ]
            app.native_values = {'rows': {'B': 'test'}}
            app._show('NativeRows')
            await choose_row(app, pilot, 'rows.batch')
            self.assertEqual(app.screen.query_one(SelectionList).option_count, 2)
            await pilot.press('space')
            await pilot.click('#choice-apply')
            await pilot.pause()
            await pilot.click('#split-train')
            await pilot.pause()
            self.assertEqual(app.native_values['rows'], {'A': 'train', 'B': 'test'})

    async def test_profile_applies_endpoint_and_model_together_without_secrets(self):
        app = OptimizerApp(self.root)
        app.model_presets = {'local': {'AGENT_OPT_MODEL_BASE_URL': 'http://localhost:8000/v1',
                                      'AGENT_OPT_MODEL_ID': 'local-model', 'AGENT_OPT_MODEL_API_KEY': 'discard'}}
        async with app.run_test() as pilot:
            app.selections = {'Agent': 'ace-rtl', 'Harness': 'ace-opencode', 'Optimizer': 'gepa'}
            app.model_values['AGENT_OPT_MODEL_API_KEY'] = 'session-key'
            app._open_model_setup('Review')
            await choose_row(app, pilot, 'model.profile')
            choices = app.screen.query_one(OptionList)
            choices.highlighted = next(i for i, row in enumerate(app.screen.items) if row[0] == 'local')
            await pilot.press('enter')
            await pilot.pause()
            self.assertEqual(app.model_values['AGENT_OPT_MODEL_ID'], 'local-model')
            self.assertEqual(app.model_values['AGENT_OPT_MODEL_BASE_URL'], 'http://localhost:8000/v1')
            self.assertEqual(app.model_values['AGENT_OPT_MODEL'], 'compatible/local-model')
            self.assertEqual(app.model_values['AGENT_OPT_MODEL_API_KEY'], 'session-key')
            self.assertNotIn('session-key', app.export_screenshot())

    async def test_search_keeps_row_identity_and_escape_restores_list(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await choose_row(app, pilot, 'new')
            await pilot.press('ctrl+f')
            app.query_one('#search', Input).value = 'rtl-solo'
            await pilot.pause()
            self.assertEqual([row.id for row in app.rows], ['rtl-solo'])
            await pilot.press('enter')
            await pilot.pause()
            self.assertEqual(app.selections['Agent'], 'rtl-solo')
            self.assertEqual(app.page, 'Harness')

    async def test_advanced_creates_real_config_only_after_prepare(self):
        app = OptimizerApp(self.root)
        with patch.dict(os.environ, {'AGENT_OPT_LANG': 'ko'}):
            async with app.run_test() as pilot:
                await choose_row(app, pilot, 'advanced')
                self.assertTrue(any(row.id == 'agent' for row in app.rows))
                app.advanced_values.update(name='my-agent', agent=str(self.root / 'examples/minimal/agents/solo'),
                    editable=['configs/strategy.json'], harness='fixture', optimizer=['baseline'], dataset='sample_text')
                await choose_row(app, pilot, 'advanced.continue')
                self.assertEqual(app.page, 'Model')
                await choose_row(app, pilot, 'review')
                self.assertEqual(app.page, 'Review')
                self.assertFalse(Path(os.environ['AGENT_OPT_HOME']).joinpath('experiments').exists())
                await choose_row(app, pilot, 'prepare')
                for _ in range(100):
                    await pilot.pause(0.05)
                    if not app.busy:
                        break
                self.assertTrue(app.preparation_complete, app.preparation_error)
                spec = load_experiment(app.experiment)
                self.assertEqual(spec['_agents'][0].editable, ('configs/strategy.json',))
                self.assertEqual(spec['_profiles'][0]['adapter'], 'fixture')
                self.assertEqual(spec['stages'][0]['optimizer'], 'baseline')

    async def test_evaluator_form_saves_fields_without_json_typing(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            app._show('Native')
            await choose_row(app, pilot, 'evaluator')
            app.screen.query_one('#field-repo', Input).value = str(self.root)
            app.screen.query_one('#field-sim_image', Input).value = 'reviewed:tag'
            await pilot.click('#form-apply')
            await pilot.pause()
            self.assertEqual(app.native_values['evaluator'], {'repo': str(self.root), 'sim_image': 'reviewed:tag'})

    async def test_evaluator_cancel_preserves_draft_without_committing(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            app._show('Native')
            await choose_row(app, pilot, 'evaluator')
            app.screen.query_one('#field-sim_image', Input).value = 'reviewed:draft'
            await pilot.pause()
            await pilot.press('escape')
            self.assertNotIn('evaluator', app.native_values)
            await choose_row(app, pilot, 'evaluator')
            self.assertEqual(app.screen.query_one('#field-sim_image', Input).value, 'reviewed:draft')

    async def test_custom_profile_rejects_secret_url_before_render_and_validates_pair(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            app.selections = {'Agent': 'ace-rtl', 'Harness': 'ace-native', 'Optimizer': 'gepa'}
            app._open_model_setup('Review')
            await choose_row(app, pilot, 'model.profile')
            options = app.screen.query_one(OptionList)
            options.highlighted = next(i for i, item in enumerate(app.screen.items) if item[0] == 'custom')
            await pilot.press('enter')
            await pilot.pause()
            entry = app.screen.query_one('#field-AGENT_OPT_MODEL_BASE_URL', Input)
            entry.value = 'https://user:PROFILE-SECRET@host.example/v1'
            await pilot.pause()
            self.assertEqual(entry.value, '')
            self.assertNotIn('PROFILE-SECRET', app.export_screenshot())
            entry.value = 'http://localhost:8000/v1'
            app.screen.query_one('#field-AGENT_OPT_MODEL_ID', Input).value = 'local-model'
            await pilot.click('#form-apply')
            await pilot.pause()
            self.assertEqual(app.model_values['AGENT_OPT_MODEL_ID'], 'local-model')

    async def test_advanced_editable_chooser_excludes_symlinks_and_preserves_hidden_selection(self):
        app = OptimizerApp(self.root)
        agent = self.root / 'examples/minimal/agents/solo'
        (agent / '.env').write_text('SECRET=value')
        (agent / 'escape.txt').symlink_to(self.root / 'pyproject.toml')
        async with app.run_test() as pilot:
            await choose_row(app, pilot, 'advanced')
            app.advanced_values['agent'] = str(agent)
            await choose_row(app, pilot, 'editable')
            screen = app.screen
            self.assertNotIn('.env', [item[0] for item in screen.items])
            self.assertNotIn('escape.txt', [item[0] for item in screen.items])
            screen.query_one(SelectionList).select('configs/strategy.json')
            screen.query_one('#choice-search', Input).value = 'system.md'
            await pilot.pause()
            screen.query_one(SelectionList).select('prompts/system.md')
            await pilot.click('#choice-apply')
            await pilot.pause()
            self.assertEqual(app.advanced_values['editable'], ['configs/strategy.json', 'prompts/system.md'])

    async def test_browser_shows_virtualenv_and_keyboard_navigation_needs_no_path_typing(self):
        app = OptimizerApp(self.root)
        (self.root / '.venv/bin').mkdir(parents=True)
        (self.root / '.venv/bin/python').write_text('fixture')
        async with app.run_test(size=(50, 20)) as pilot:
            app._show('Native')
            await choose_row(app, pilot, 'python')
            screen = app.screen
            self.assertIn('.venv', [p.name for p in screen.paths])
            options = screen.query_one(OptionList)
            options.highlighted = next(i for i, p in enumerate(screen.paths) if p.name == '.venv')
            await pilot.press('enter')
            options.highlighted = next(i for i, p in enumerate(screen.paths) if p.name == 'bin')
            await pilot.press('enter')
            options.highlighted = next(i for i, p in enumerate(screen.paths) if p.name == 'python')
            await pilot.press('enter')
            await pilot.pause()
            self.assertEqual(app.native_values['python'], str(self.root / '.venv/bin/python'))

    async def test_search_escape_restores_choices_without_implicit_selection(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await choose_row(app, pilot, 'new')
            original = [row.id for row in app.rows]
            await pilot.press('ctrl+f')
            app.query_one('#search', Input).value = 'no-match'
            await pilot.pause()
            self.assertEqual(app.rows, [])
            await pilot.press('escape')
            self.assertEqual([row.id for row in app.rows], original)
            self.assertEqual(app.selections, {})

    async def test_modal_ctrl_enter_applies_cids_and_evaluator_fields(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            app._show('Native')
            await choose_row(app, pilot, 'cids')
            await pilot.press('space', 'ctrl+enter')
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 1)
            self.assertEqual(app.native_values['cids'], ['cid002'])
            await choose_row(app, pilot, 'evaluator')
            app.screen.query_one('#field-sim_image', Input).value = 'reviewed:tag'
            await pilot.press('ctrl+enter')
            await pilot.pause()
            self.assertEqual(app.native_values['evaluator'], {'sim_image': 'reviewed:tag'})

    async def test_git_url_blocks_credentials_but_allows_ssh_username(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await choose_row(app, pilot, 'advanced')
            await choose_row(app, pilot, 'git')
            entry = app.screen.query_one('#field-url', Input)
            entry.value = 'https://user:GIT-UX-SECRET@host.example/repo.git'
            await pilot.pause()
            self.assertEqual(entry.value, '')
            self.assertNotIn('GIT-UX-SECRET', repr(app.form_drafts))
            self.assertNotIn('GIT-UX-SECRET', app.export_screenshot())
            await pilot.press('escape')
            await choose_row(app, pilot, 'git')
            entry = app.screen.query_one('#field-url', Input)
            entry.value = 'ssh://git@host.example/repo.git'
            self.assertEqual(entry.value, 'ssh://git@host.example/repo.git')
            entry.value = 'git@host.example:repo.git'
            self.assertEqual(entry.value, 'git@host.example:repo.git')

    async def test_existing_to_advanced_review_returns_to_model_and_offers_edit(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            app._load_existing(self.root / 'examples/minimal/experiment.toml')
            app._show('Home')
            await choose_row(app, pilot, 'advanced')
            app.advanced_values.update(agent=str(self.root / 'examples/minimal/agents/solo'),
                editable=['configs/strategy.json'], harness='fixture', optimizer=['baseline'], dataset='sample_text')
            await choose_row(app, pilot, 'advanced.continue')
            await choose_row(app, pilot, 'review')
            self.assertIn('edit:Advanced', [row.id for row in app.rows])
            await pilot.press('escape')
            self.assertEqual(app.page, 'Model')
            await pilot.press('escape')
            self.assertEqual(app.page, 'Advanced')

    async def test_direction_select_draft_and_git_revision_are_visible_before_prepare(self):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await choose_row(app, pilot, 'advanced')
            await choose_row(app, pilot, 'direction')
            app.screen.query_one(Select).value = 'minimize'
            await pilot.pause()
            await pilot.press('escape')
            await choose_row(app, pilot, 'direction')
            self.assertEqual(app.screen.query_one(Select).value, 'minimize')
            await pilot.press('escape')
            app.advanced_values['revision'] = 'a' * 40
            self.assertIn('a' * 40, app._review())

    async def test_narrow_browser_apply_and_cancel_are_visible_and_clickable(self):
        app = OptimizerApp(self.root)
        async with app.run_test(size=(50, 20)) as pilot:
            app._show('Workspace')
            app.query_one('#options', OptionList).focus()
            await choose_row(app, pilot, 'workspace.browse')
            self.assertTrue(await pilot.click('#path-apply'))
            await pilot.pause()
            self.assertEqual(app.page, 'Model')
