import importlib.util
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT if (ROOT / 'external/ACE-RTL').exists() else ROOT.parent.parent
DATA = BASE / 'external/cvdp-data/5b807d945f6a99aa645f7e43a64a2115e281b4bf/cvdp_v1.1.0_nonagentic_code_generation_no_commercial.jsonl'


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'examples/ace-rtl/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeCVDPTests(unittest.TestCase):
    def setUp(self):
        self.bridge = load('native_cvdp')

    def test_actual_pinned_rows_public_boundary_and_multifile(self):
        if not DATA.exists():
            self.skipTest('고정 prepared 데이터 없음')
        rows = self.bridge.load_pinned_rows(DATA)
        for cid, count in [('cid002', 94), ('cid004', 55), ('cid007', 40), ('cid016', 35)]:
            selected = [r for r in rows if cid in r['categories']]
            self.assertEqual(len(selected), count)
            verdict = self.bridge.inspect_row(selected[0])
            self.assertEqual(verdict['supported'], cid != 'cid007')
            if cid == 'cid007':
                self.assertIn('PNR', verdict['reason'])
                continue
            public = self.bridge.public_row(selected[0])
            self.assertNotIn('harness', public)
            self.assertEqual(public['output']['context'], {p: '' for p in selected[0]['output']['context']})
        multi = next(r for r in rows if 'cid002' in r['categories'] and len(r['output']['context']) == 3)
        self.assertTrue(self.bridge.inspect_row(multi)['supported'])
        self.assertEqual(len(self.bridge.public_row(multi)['output']['context']), 3)

    def test_real_lint_only_cid007_and_trivial_oss_alias_builds(self):
        if not DATA.exists():
            self.skipTest('고정 prepared 데이터 없음')
        rows = self.bridge.load_pinned_rows(DATA)
        lint = next(r for r in rows if r['id'] == 'cvdp_copilot_IIR_filter_0019')
        verdict = self.bridge.inspect_row(lint)
        self.assertTrue(verdict['supported'])
        self.assertIn('Verilator', verdict['tools'])
        for row in [r for r in rows if set(r['categories']) & {'cid002', 'cid004', 'cid016'}]:
            self.assertTrue(self.bridge.inspect_row(row)['supported'], row['id'])
        self.assertEqual(self.bridge.classify_result({'tests': [{'result': 0}, {'result': 1}]})[0], 'failed')

    def test_strict_complete_declared_output_bundle(self):
        targets = ['rtl/a.sv', 'rtl/b.sv']
        text = '// TARGET_FILE: rtl/a.sv\nmodule a; endmodule\n// TARGET_FILE: rtl/b.sv\nmodule b; endmodule'
        self.assertEqual(set(self.bridge.parse_outputs(text, targets)), set(targets))
        for bad in [text.split('// TARGET_FILE: rtl/b.sv')[0], text + '\n// TARGET_FILE: src/checker.py\nx', '', text + '\n// TARGET_FILE: ../escape\nx', text + '\n// TARGET_FILE: rtl/a.sv\nx']:
            with self.subTest(bad=bad), self.assertRaises(ConfigurationError):
                self.bridge.parse_outputs(bad, targets)
        with self.assertRaises(ConfigurationError):
            self.bridge.parse_outputs('module x; endmodule', ['../x.sv'])

    def test_output_symlink_rejected(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
            root = Path(tmp)
            (root / 'rtl').mkdir()
            (root / 'outside').write_text('module a; endmodule')
            (root / 'rtl/a.sv').symlink_to(root / 'outside')
            with self.assertRaises(ConfigurationError):
                self.bridge.read_outputs(root, ['rtl/a.sv'])

    def test_native_preparation_requires_selection_and_rejects_wrong_data_hash(self):
        if not DATA.exists():
            self.skipTest('고정 prepared 데이터 없음')
        prepare = load('native_prepare')
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
            output = Path(tmp) / 'tasks.json'
            with self.assertRaises(ConfigurationError):
                prepare.prepare_dataset(DATA, output, cids=[])
            lint = prepare.prepare_dataset(DATA, output, cids=['cid007'])
            self.assertEqual(len(lint['tasks']), 13)
            self.assertEqual(len(json.loads(output.with_suffix('.excluded.json').read_text())), 27)
            result = prepare.prepare_dataset(DATA, output, cids=['cid002', 'cid004', 'cid016'])
            self.assertFalse(result['synthetic'])
            self.assertTrue(result['tasks'])
            for task in result['tasks']:
                self.assertEqual(task['split'], 'validation')
                self.assertNotIn('harness', json.loads(task['files']['native-task.json']))
            bad = Path(tmp) / 'bad.jsonl'
            bad.write_text('{}')
            with self.assertRaises(ConfigurationError):
                self.bridge.load_pinned_rows(bad)

    def test_official_results_not_agent_pass_and_safe_feedback(self):
        for record, want in [({'tests': [{'result': 0}]}, 'passed'), ({'passed': True, 'tests': [{'result': 1}]}, 'failed'), ({'tests': [{'result': 127, 'error_msg': 'PRIVATE_SECRET command not found'}]}, 'infrastructure_error'), ({'tests': []}, 'infrastructure_error'), ({'passed': True}, 'infrastructure_error'), ({'tests': [{'result': True}]}, 'infrastructure_error')]:
            status, feedback = self.bridge.classify_result(record)
            self.assertEqual(status, want)
            self.assertNotIn('PRIVATE_SECRET', feedback)

    def test_trusted_official_evaluator_raw_schema_and_network_ownership(self):
        if not DATA.exists():
            self.skipTest('고정 prepared 데이터 없음')
        from agent_optimizer.contracts import ExecutionResult, Task
        native = load('native_evaluator')
        row = next(r for r in self.bridge.load_pinned_rows(DATA) if r['id'] == 'cvdp_copilot_64b66b_decoder_0001')
        for record, want in [({'tests': [{'result': 0}]}, 'passed'), ({'passed': True, 'tests': [{'result': 1}]}, 'failed'), ({'tests': [{'result': 127, 'error_msg': 'command not found'}]}, 'infrastructure_error'), ({'tests': []}, 'infrastructure_error')]:
            with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
                output = Path(tmp) / 'output'
                (output / 'rtl').mkdir(parents=True)
                (output / 'rtl/decoder_64b66b.sv').write_text('module x; endmodule')
                task = Task(row['id'], 'test', row['input']['prompt'], {}, {'row': row, 'targets': ['rtl/decoder_64b66b.sv']})
                def run_process(argv, cwd, logs, timeout, env):
                    prefix = Path(argv[argv.index('-p') + 1])
                    prefix.mkdir()
                    (prefix / 'raw_result.json').write_text(json.dumps({row['id']: record}))
                    self.assertNotIn('AGENT_OPT_MODEL_API_KEY', env)
                    return ExecutionResult('completed', 0, .01, '', '')
                with patch.object(native.official, 'run_process', side_effect=run_process), patch.object(native.cleanup, 'cleanup_network', return_value={'status': 'completed', 'reason': None}):
                    result = native.NativeCVDPEvaluator({'repo': '/fixture/repo', 'python': '/fixture/python'}).evaluate(task, output, 2)
                self.assertEqual(result.status, want)
                self.assertTrue((Path(tmp) / 'native-owned-network.json').is_file())
                self.assertEqual(json.loads((Path(tmp) / 'native-owned-network.json').read_text())['status'], 'completed')

    def test_bounded_cleanup_removes_only_owned_ids_without_raw_stderr(self):
        import time
        import types
        cleanup = load('native_cleanup')
        network = 'agent-opt-cvdp-' + 'a' * 32
        calls = []
        def run(argv, **kwargs):
            calls.append(argv)
            self.assertLessEqual(kwargs['timeout'], 1)
            return types.SimpleNamespace(returncode=0, stdout='b' * 12 if argv[1] == 'ps' else '', stderr='PRIVATE_SECRET')
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
            with patch.object(cleanup.subprocess, 'run', side_effect=run):
                result = cleanup.cleanup_network(network, Path(tmp), deadline=time.monotonic() + 1)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(calls, [['docker', 'ps', '-aq', '--filter', 'network=' + network],
                                     ['docker', 'rm', '-f', 'b' * 12], ['docker', 'network', 'rm', network]])
            self.assertNotIn('PRIVATE_SECRET', (Path(tmp) / 'cleanup.json').read_text())
            with patch.object(cleanup.subprocess, 'run', side_effect=AssertionError('예산 종료 후 호출 금지')):
                deferred = cleanup.cleanup_network(network, Path(tmp), deadline=time.monotonic() - 1)
            self.assertEqual(deferred['status'], 'deferred')


if __name__ == '__main__':
    unittest.main()
