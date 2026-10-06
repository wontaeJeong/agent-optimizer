"""examples/소스 마커 없는 package-only 레이아웃; wheel build와 구분한다."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import textwrap

ROOT = Path(__file__).resolve().parents[1]


class PackageProductTests(unittest.TestCase):
    def _native_workspace_flow(self, *, decoy_policy):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            package = base / 'installed'
            shutil.copytree(ROOT / 'src/agent_optimizer', package / 'agent_optimizer', ignore=shutil.ignore_patterns('__pycache__'))
            workspace, cwd = base / 'explicit-workspace', base / 'foreign-cwd'
            workspace.mkdir()
            cwd.mkdir()
            loader = textwrap.dedent('''
                import importlib.util
                from pathlib import Path
                def sibling(name):
                    file = Path(__file__).with_name(name + '.py')
                    spec = importlib.util.spec_from_file_location('_workspace_' + name, file)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    return module
            ''')
            helpers = workspace / 'examples/ace-rtl'
            helpers.mkdir(parents=True)
            (helpers / 'native_prepare.py').write_text(loader)
            policy = textwrap.dedent('''
                from pathlib import Path
                from agent_optimizer.app_paths import app_path
                from agent_optimizer.setup_wizard import write_experiment
                def validate_selection(cids, rows, optimizer):
                    assert cids == ['workspace-category'] and rows == {'workspace-row': 'validation'}
                def inspect_selection(root, cids, rows, dataset, prepare=None):
                    return [{'id': 'workspace-row', 'targets': ['output.txt']}]
                def available_rows(root, dataset, cids, prepare=None):
                    return [{'id': 'workspace-row', 'cid': 'workspace-category', 'targets': ['output.txt'], 'tools': [], 'supported': True, 'reason': ''}]
                def native_trial_budget(optimizer, rows, options=None):
                    return 7
                def write_native_selection(root, optimizer, *, prepare=None, source, dataset, rows, **options):
                    return write_experiment(app_path('experiments') / 'workspace-generated', agent=Path(source),
                        harness={'adapter': 'command', 'command': ['python', 'agent.py']},
                        dataset={'benchmark': str(dataset), 'evaluator': 'scorer'}, stages=[],
                        plugins={'evaluators': {'scorer': 'evaluator.py:Scorer'}}, dependencies={}, name='workspace-generated',
                        editable=['prompts/system.md'], project_root=Path(root), max_tasks=1, max_trials=7)
            ''')
            (helpers / 'native_selection.py').write_text(policy)
            if decoy_policy:
                decoy = cwd / 'examples/ace-rtl'
                decoy.mkdir(parents=True)
                (decoy / 'native_prepare.py').write_text(loader)
                (decoy / 'native_selection.py').write_text(textwrap.dedent('''
                    from agent_optimizer.contracts import ConfigurationError
                    def validate_selection(cids, rows, optimizer):
                        raise ConfigurationError('CWD의 다른 정책은 이 선택을 거부합니다')
                    def native_trial_budget(optimizer, rows, options=None):
                        return 99
                '''))
            agent = base / 'source'
            (agent / 'prompts').mkdir(parents=True)
            (agent / 'prompts/system.md').write_text('공개 fixture guidance')
            (workspace / 'evaluator.py').write_text('class Scorer: pass\n')
            dataset = base / 'dataset.json'
            dataset.write_text(json.dumps({'schema_version': 1, 'synthetic': True, 'tasks': [
                {'id': 'workspace-row', 'split': 'validation', 'prompt': '공개 fixture', 'files': {'input.txt': '공개'}, 'evaluation': {'expected': 'ok'}}]}))
            program = textwrap.dedent('''
                import asyncio, os
                from pathlib import Path
                from textual.widgets import OptionList
                from agent_optimizer.tui import OptimizerApp
                from agent_optimizer.config import load_experiment
                async def flow():
                    workspace = Path(os.environ['FIXTURE_WORKSPACE'])
                    app = OptimizerApp(Path.cwd())
                    app.workspace = workspace
                    app.selections = {'Agent':'ace-rtl', 'Harness':'ace-native', 'Optimizer':'baseline', 'Dataset':'cvdp'}
                    app.native_values = {'cids':['workspace-category'], 'rows':{'workspace-row':'validation'},
                        'source':os.environ['FIXTURE_SOURCE'], 'dataset':os.environ['FIXTURE_DATASET']}
                    async with app.run_test() as pilot:
                        app._show('Native')
                        options = app.query_one(OptionList)
                        options.highlighted = options.get_option_index('rows.pick')
                        options.focus()
                        await pilot.press('enter')
                        await pilot.pause()
                        assert app.page == 'NativeRows', app.page
                        app._show('Native')
                        options.highlighted = options.get_option_index('native.continue')
                        options.focus()
                        await pilot.press('enter')
                        await pilot.pause()
                        assert app.page == 'Model', app.page
                        app._show('Review')
                        review = app._review()
                        assert '  최대 trial budget  7' in review, review
                        assert '  최대 trial budget  99' not in review, review
                        app._prepare()
                        for _ in range(100):
                            await pilot.pause(.02)
                            if not app.busy: break
                        assert app.preparation_complete, app.preparation_error
                        spec = load_experiment(app.experiment)
                        assert spec['_root'] == workspace, spec['_root']
                        assert spec['budget']['max_trials'] == 7, spec['budget']
                        assert {task.id:task.split for task in spec['_tasks']} == {'workspace-row':'validation'}
                        assert '  최대 trial budget  7' in app._review(), app._review()
                asyncio.run(flow())
            ''')
            env = {**os.environ, 'PYTHONPATH': str(package), 'PYTHONDONTWRITEBYTECODE': '1',
                   'AGENT_OPT_HOME': str(base / 'home'), 'HOME': str(base / 'user-home'),
                   'FIXTURE_WORKSPACE': str(workspace), 'FIXTURE_SOURCE': str(agent), 'FIXTURE_DATASET': str(dataset),
                   'AGENT_OPT_MODEL_BASE_URL': 'http://127.0.0.1:12345/v1', 'AGENT_OPT_MODEL_ID': 'fixture', 'AGENT_OPT_MODEL_API_KEY': 'KEY-SENTINEL'}
            process = subprocess.run([sys.executable, '-c', program], cwd=cwd, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(process.returncode, 0, process.stderr)

    def test_native_explicit_workspace_overrides_actual_cwd_policy(self):
        self._native_workspace_flow(decoy_policy=True)

    def test_package_only_native_valid_workspace_without_cwd_assets(self):
        self._native_workspace_flow(decoy_policy=False)

    def test_package_only_custom_project_from_two_cwds(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            package = base / 'installed'
            shutil.copytree(ROOT / 'src/agent_optimizer', package / 'agent_optimizer', ignore=shutil.ignore_patterns('__pycache__'))
            project = base / 'project'
            agent = project / 'agent'
            (agent / 'prompts').mkdir(parents=True)
            (agent / 'prompts/system.md').write_text('공개 guidance')
            (agent / 'agent.py').write_text('import sys\nfrom pathlib import Path\n(Path(sys.argv[1]) / "output.txt").write_text("ok")\n')
            (project / 'evaluator.py').write_text('from pathlib import Path\nfrom agent_optimizer.contracts import Evaluation\nclass Scorer:\n def __init__(self, config=None): pass\n def evaluate(self, task, output_dir, timeout_seconds):\n  passed = (Path(output_dir) / "output.txt").read_text() == task.evaluation["expected"]\n  return Evaluation("passed" if passed else "failed", {"passed": float(passed)})\n')
            tasks = project / 'tasks.json'
            tasks.write_text(json.dumps({'schema_version': 1, 'synthetic': True, 'tasks': [
                {'id': 'validation', 'split': 'validation', 'prompt': '공개 과제', 'files': {'input.txt': '공개'}, 'evaluation': {'expected': 'ok'}}]}))
            cwd1, cwd2 = base / 'cwd1', base / 'cwd2'
            cwd1.mkdir()
            cwd2.mkdir()
            env = {**os.environ, 'PYTHONPATH': str(package), 'AGENT_OPT_HOME': str(base / 'home'), 'HOME': str(base / 'user-home'),
                   'PYTHONDONTWRITEBYTECODE': '1'}
            def cli(cwd, *args):
                proc = subprocess.run([sys.executable, '-m', 'agent_optimizer', *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=20)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                return json.loads(proc.stdout)
            cli(cwd1, 'catalog', 'list', '--kind', 'harness', '--json')
            self.assertFalse((base / 'home').exists())
            generated = cli(cwd1, 'init', '--project-root', str(project), '--agent', 'agent', '--editable', 'prompts/system.md',
                '--command', f'{sys.executable} {{agent_dir}}/agent.py {{task_dir}}', '--optimizer', 'baseline',
                '--dataset', 'tasks.json', '--evaluator', 'evaluator.py:Scorer', '--name', 'package-e2e', '--yes')
            config = Path(generated['experiment'])
            self.assertTrue(config.is_relative_to(base / 'home/experiments'))
            plan = cli(cwd2, 'plan', str(config))
            self.assertEqual(plan['tasks_by_split'], {'train': 0, 'validation': 1, 'test': 0})
            self.assertEqual(plan['sources']['package-e2e']['path'], str(agent))
            diagnosis = cli(cwd2, 'doctor', '--plan', str(config), '--json')
            self.assertTrue(diagnosis['ready'])
            result = cli(cwd2, 'run', str(config))
            self.assertEqual(result['status'], 'completed')
            run = Path(result['run_dir'])
            self.assertTrue(run.is_relative_to(base / 'home/runs'))
            report = cli(cwd1, 'report', str(run), '--json')
            self.assertTrue(report['synthetic'])
            self.assertTrue((run / 'report.html').is_file())
            self.assertFalse((cwd1 / 'runs').exists())
            self.assertFalse((cwd2 / 'runs').exists())
