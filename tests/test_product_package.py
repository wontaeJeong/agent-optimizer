"""examples/소스 마커 없는 package-only 레이아웃; wheel build와 구분한다."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PackageProductTests(unittest.TestCase):
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
