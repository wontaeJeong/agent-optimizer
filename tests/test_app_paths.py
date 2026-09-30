import concurrent.futures
import os
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.registry import Registry
from agent_optimizer.runner import run_experiment


ROOT = Path(__file__).resolve().parents[1]
TEMP = Path(tempfile.gettempdir()) / 'agent-optimizer-final-mvp-a'


class AppPathsTests(unittest.TestCase):
    def setUp(self):
        TEMP.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=TEMP)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / '앱 home'
        self.env = patch.dict(os.environ, {'AGENT_OPT_HOME': str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_resolvers_are_cwd_independent_and_read_only(self):
        from agent_optimizer.app_paths import app_path, resolve_app_home, resolve_run_base, resolve_session_base
        with patch('pathlib.Path.home', return_value=self.root), patch.dict(os.environ, {'HOME': str(self.root)}):
            self.assertEqual(resolve_app_home({}), self.root / '.agent-optimizer')
            self.assertEqual(resolve_app_home({'AGENT_OPT_HOME': ''}), self.root / '.agent-optimizer')
            self.assertEqual(resolve_app_home({'AGENT_OPT_HOME': '~/새 home'}), self.root / '새 home')
        for cwd in (self.root, ROOT):
            self.assertEqual(resolve_app_home(cwd=cwd), self.home)
        for name in ('experiments', 'runs', 'sessions', 'assets', 'cache', 'logs'):
            self.assertEqual(app_path(name), self.home / name)
        self.assertEqual(resolve_run_base({'_root': ROOT}), self.home / 'runs')
        self.assertEqual(resolve_session_base(), self.home / 'sessions')
        self.assertFalse(self.home.exists())

    def test_relative_override_is_configuration_error(self):
        from agent_optimizer.app_paths import resolve_app_home
        for value in ('relative', '../escape', '.'):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                resolve_app_home({'AGENT_OPT_HOME': value}, cwd=self.root)

    def test_output_precedence_preserves_project_boundary(self):
        from agent_optimizer.app_paths import resolve_run_base
        spec = {'_root': self.root, 'output_dir': '옛 runs'}
        self.assertEqual(resolve_run_base(spec), self.root / '옛 runs')
        self.assertEqual(resolve_run_base(spec, self.root / 'explicit'), self.root / 'explicit')
        with self.assertRaises(ConfigurationError):
            resolve_run_base({'_root': self.root, 'output_dir': '../escape'})
        self.assertFalse(self.home.exists())

    def external_spec(self):
        folder = self.root / '설정'
        shutil.copytree(ROOT / 'examples/minimal', folder)
        for manifest in (folder / 'solo.toml', folder / 'team.toml'):
            # The original manifests use sibling local sources; retain provenance.
            text = manifest.read_text()
            import re
            text = re.sub(r'path = "([^"]+)"',
                          lambda m: 'path = "' + str((ROOT / 'examples/minimal' / m[1]).resolve()) + '"', text)
            manifest.write_text(text)
        original = (folder / 'experiment.toml').read_text()
        original = original.replace('project_root = "../.."', f'project_root = "{ROOT}"\nconfig_root = "."')
        original = original.replace('agents = ["examples/minimal/solo.toml", "examples/minimal/team.toml"]',
                                    'agents = ["solo.toml", "team.toml"]')
        original = original.replace('harnesses = ["examples/minimal/harness.toml"]', 'harnesses = ["harness.toml"]')
        original = original.replace('benchmark = "examples/minimal/tasks.json"', 'benchmark = "tasks.json"')
        (folder / 'experiment.toml').write_text(original)
        return folder / 'experiment.toml'

    def test_external_config_keeps_project_and_source_provenance(self):
        path = self.external_spec()
        spec = load_experiment(path)
        self.assertEqual(spec['_root'], ROOT)
        self.assertEqual(spec['_config_root'], path.parent)
        self.assertTrue(all(agent.source.path.is_absolute() for agent in spec['_agents']))
        root, summary = run_experiment(spec, Registry(), self.root / 'output')
        self.assertEqual(summary['status'], 'completed')
        self.assertTrue((root / 'lifecycle.json').is_file())

    def test_external_config_cannot_escape_declared_boundary(self):
        path = self.external_spec()
        path.write_text(path.read_text().replace('benchmark = "tasks.json"', 'benchmark = "../tasks.json"'))
        with self.assertRaises(ConfigurationError):
            load_experiment(path)

    def test_default_runs_are_unique_under_concurrency(self):
        project = self.root / 'project'
        shutil.copytree(ROOT / 'examples/minimal', project / 'examples/minimal')
        def run(_):
            spec = load_experiment(project / 'examples/minimal/experiment.toml')
            spec.pop('output_dir', None)
            return run_experiment(spec, Registry())[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            roots = list(pool.map(run, range(2)))
        self.assertNotEqual(roots[0], roots[1])
        self.assertTrue(all(root.parent == self.home / 'runs' for root in roots))

    def test_permission_failure_does_not_fallback(self):
        spec = load_experiment(ROOT / 'examples/minimal/experiment.toml')
        spec.pop('output_dir', None)
        with patch('pathlib.Path.mkdir', side_effect=PermissionError('fixture')):
            with self.assertRaises(PermissionError):
                run_experiment(spec, Registry())
        self.assertFalse(self.home.exists())

    def test_integration_cache_is_home_owned_explicit_and_offline(self):
        from agent_optimizer.integrations import acquire_integration
        from agent_optimizer.contracts import UnavailableError
        repo = self.root / 'repo'
        for relative in ('examples/ace-rtl/adapter.py', 'examples/rtl-debugger/Dockerfile',
                         'examples/benchmarks/cvdp.py', 'experiments/simple-feedback/optimizer.py',
                         'src/agent_optimizer/models.py'):
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('fixture')
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.invalid', 'commit', '-qm', '검증 fixture'], check=True)
        revision = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        workspace = self.root / 'workspace'
        workspace.mkdir()
        with self.assertRaises(UnavailableError):
            acquire_integration(workspace, 'ace-rtl', source_url=str(repo), revision=revision, offline=True)
        self.assertFalse(self.home.exists())
        acquire_integration(workspace, 'ace-rtl', source_url=str(repo), revision=revision)
        self.assertTrue((self.home / 'cache/integrations' / revision / '.git').is_dir())
        acquire_integration(workspace, 'ace-rtl', source_url=str(repo), revision=revision, offline=True)
        with self.assertRaises(UnavailableError):
            acquire_integration(workspace, 'ace-rtl', source_url=str(repo), revision=revision,
                                cache_dir=self.root / 'explicit-empty', offline=True)
        edited = workspace / 'examples/ace-rtl/adapter.py'
        edited.write_text('사용자 수정')
        with self.assertRaises(ConfigurationError):
            acquire_integration(workspace, 'ace-rtl', source_url=str(repo), revision=revision, offline=True)
        self.assertEqual(edited.read_text(), '사용자 수정')

    def test_custom_dataset_default_cache_preserves_modified_artifacts(self):
        from agent_optimizer.datasets import CustomDataset
        source = self.root / 'custom.json'
        source.write_text((ROOT / 'examples/minimal/tasks.json').read_text())
        provider = CustomDataset(source, evaluator='text_fixture')
        result = provider.prepare()
        output = Path(result['benchmark'])
        self.assertTrue(output.is_relative_to(self.home / 'cache'))
        self.assertEqual(json.loads(output.read_text())['source_sha256'], result['provenance']['sha256'])
        output.write_text('사용자 수정')
        with self.assertRaises(ConfigurationError):
            provider.prepare()
        self.assertEqual(output.read_text(), '사용자 수정')

    def test_pinned_checkout_concurrent_publication(self):
        from agent_optimizer.datasets import acquire_pinned_git
        repo = self.root / 'repo'
        repo.mkdir()
        (repo / 'data').write_text('fixture')
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.invalid', 'commit', '-qm', '검증 fixture'], check=True)
        revision = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        target = self.home / 'cache/source' / revision
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            paths = list(pool.map(lambda _: acquire_pinned_git(target, str(repo), revision), range(2)))
        self.assertEqual(paths, [target, target])
        self.assertEqual((target / 'data').read_text(), 'fixture')

    def test_read_only_cli_does_not_create_fresh_home(self):
        commands = (['--help'], ['catalog', 'list', '--kind', 'harness', '--json'],
                    ['plan', str(ROOT / 'examples/minimal/experiment.toml')],
                    ['doctor', '--plan', str(ROOT / 'examples/minimal/experiment.toml'), '--json'])
        import sys
        for args in commands:
            result = subprocess.run([sys.executable, '-m', 'agent_optimizer', *args],
                                    cwd=self.root, env={**os.environ, 'PYTHONPATH': str(ROOT / 'src')},
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(self.home.exists())

    def test_generated_config_boundary_does_not_rebase_seed_or_plugin(self):
        path = self.external_spec()
        seed = self.root / 'seed-project'
        shutil.copytree(ROOT / 'examples/minimal', seed / 'examples/minimal')
        (seed / 'seed.py').write_text('pass\n')
        import sys
        for manifest in (path.parent / 'solo.toml', path.parent / 'team.toml'):
            manifest.write_text(manifest.read_text().replace('build = []',
                                f'build = ["{sys.executable}", "agent/harness_source/seed.py"]'))
        text = path.read_text().replace(str(ROOT), str(seed), 1)
        text += '\n[candidate_seed_files]\n"harness_source/seed.py" = "seed.py"\n'
        path.write_text(text)
        root, summary = run_experiment(load_experiment(path), Registry(), self.root / 'seed-output')
        self.assertEqual(summary['status'], 'completed')
        manifest = json.loads((root / 'manifest.json').read_text())
        self.assertIn('harness_source/seed.py', manifest['candidate_seed_sha256'])
        self.assertIn('examples/minimal/evaluator.py:TextFixtureEvaluator', manifest['plugin_sha256'])

    def test_pinned_checkout_publish_race_reuses_verified_winner(self):
        from agent_optimizer.datasets import acquire_pinned_git
        repo = self.root / 'repo'
        repo.mkdir()
        (repo / 'data').write_text('fixture')
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.invalid', 'commit', '-qm', '검증 fixture'], check=True)
        revision = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        target = self.home / 'cache/source' / revision

        def competing_publish(staged, destination):
            shutil.copytree(staged, destination)
            raise FileExistsError('동시 생성 fixture')

        with patch.object(Path, 'rename', competing_publish):
            self.assertEqual(acquire_pinned_git(target, str(repo), revision), target)
        self.assertEqual((target / 'data').read_text(), 'fixture')
