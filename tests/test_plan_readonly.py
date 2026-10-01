"""사용자 기본 interpreter에서 plan의 실제 file-plugin cache 쓰기와 범위 복구."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from support import ROOT, test_project


class PlanReadonlyTests(unittest.TestCase):
    def setUp(self):
        temporary, self.project = test_project()
        self.addCleanup(temporary.cleanup)
        self.base = self.project.parent
        # Plain user invocation may cache core imports; keep those in the owned
        # temp copy, not in the checkout or the shared environment's source tree.
        self.core = self.base / 'core'
        shutil.copytree(ROOT / 'src/agent_optimizer', self.core / 'agent_optimizer',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        self.home = self.base / 'app'
        self.config = self.project / 'examples/minimal/experiment.toml'
        self.environment = {'PATH': '/usr/bin:/bin', 'HOME': str(self.base / 'user'),
                            'AGENT_OPT_HOME': str(self.home), 'TMPDIR': os.environ['TMPDIR'],
                            'PYTHONPATH': str(self.core), 'AGENT_OPT_LANG': 'ko'}

    def snapshot(self):
        return {str(p): (p.lstat().st_mode, p.lstat().st_ino, p.lstat().st_mtime_ns,
                        p.read_bytes() if p.is_file() else None)
                for p in (self.project, *self.project.rglob('*'))}

    def invoke(self, *arguments):
        self.assertNotIn('PYTHONDONTWRITEBYTECODE', self.environment)
        argv = [sys.executable, *arguments]
        self.assertNotIn('-B', argv)
        return subprocess.run(argv, cwd=self.project, env=self.environment,
                              capture_output=True, text=True, timeout=30)

    def test_actual_module_plan_keeps_writable_project_and_home_unchanged_without_B(self):
        self.assertEqual(list(self.project.rglob('__pycache__')), [])
        before = self.snapshot()
        result = self.invoke('-m', 'agent_optimizer', 'plan', str(self.config))
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertTrue(plan['valid'])
        self.assertTrue(plan['integrations_ready'])
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.home.exists())

    def test_main_restores_bytecode_setting_after_actual_plugin_success_and_error(self):
        # CLI import occurs before main; a direct library caller must recover its
        # own global setting even when a trusted file plugin raises during import.
        script = '''
import contextlib,io,json,sys
from pathlib import Path
from agent_optimizer.cli import main,plan_command
config=Path(sys.argv[1]); plugin=Path(sys.argv[2]); previous=sys.argv[3]=='true'
invoke=(lambda:main(['plan',str(config)])) if sys.argv[4]=='main' else (lambda:plan_command(config))
sys.dont_write_bytecode=previous
with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
    code=invoke()
assert code==0 and json.loads(out.getvalue())['integrations_ready']
assert sys.dont_write_bytecode is previous
assert not list(config.parents[2].rglob('__pycache__'))
plugin.write_text('raise ValueError("검증용 plugin import 실패")\\n')
with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
    code=invoke()
assert code==2 and out.getvalue()=='' and '검증용 plugin import 실패' in err.getvalue()
assert sys.dont_write_bytecode is previous
assert not list(config.parents[2].rglob('__pycache__'))
print(json.dumps({'previous':previous,'success':0,'error':2,'restored':True}))
'''
        for previous in ('false', 'true'):
            for mode in ('main', 'callback'):
                with self.subTest(previous=previous, mode=mode):
                    case = self.base / ('project-' + previous + '-' + mode)
                    shutil.copytree(self.project, case)
                    config = case / 'examples/minimal/experiment.toml'
                    plugin = case / 'examples/minimal/evaluator.py'
                    result = self.invoke('-c', script, str(config), str(plugin), previous, mode)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue(json.loads(result.stdout)['restored'])
                    self.assertEqual(list(case.rglob('__pycache__')), [])
                    self.assertFalse(self.home.exists())

    def test_bytecode_write_resumes_outside_plan_guard_for_a_library_caller(self):
        unguarded = self.project / 'unguarded.py'
        unguarded.write_text('VALUE = "실제 Python cache 대조"\n')
        script = '''
import contextlib,importlib.util,io,json,sys
from pathlib import Path
from agent_optimizer.cli import main
assert sys.dont_write_bytecode is False
with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
    assert main(['plan',sys.argv[1]])==0
assert json.loads(out.getvalue())['integrations_ready']
assert sys.dont_write_bytecode is False
file=Path(sys.argv[2]); spec=importlib.util.spec_from_file_location('unguarded',file)
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
cache=Path(importlib.util.cache_from_source(str(file)))
assert module.VALUE=='실제 Python cache 대조' and cache.is_file()
print(cache)
'''
        result = self.invoke('-c', script, str(self.config), str(unguarded))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(Path(result.stdout.strip()).is_file())
        self.assertFalse((self.project / 'examples/minimal/__pycache__').exists())
