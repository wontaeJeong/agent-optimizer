"""G 리뷰의 pair/inner·outer/redaction 누락을 실제 자료 경계로 검증한다."""
import copy
import json
import os
import shlex
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.config import load_experiment
from agent_optimizer.diagnostics import CommandOutcome
from agent_optimizer.native_selection import write_native_selection
from agent_optimizer.readiness import Runner, check, collect_plan
from agent_optimizer.registry import Registry
import test_native_product as native_fixture
ROOT = native_fixture.ROOT


class NativeDiagnosisReviewTests(unittest.TestCase):
    def setUp(self):
        fixture = native_fixture.NativeProductTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.base = fixture.base
        self.good = self.evaluator('inner')
        self.plan = write_native_selection(ROOT, 'baseline', cids=['cid002'], rows=fixture.rows,
                                           dataset=fixture.data, source=fixture.source,
                                           evaluator=self.good)
        self.spec = load_experiment(self.plan)
        self.argv = []
        self.engine = []

    def evaluator(self, name):
        repo = self.base / name
        repo.mkdir()
        (repo / 'run_benchmark.py').write_text('# 로컬 평가 자산 fixture\n')
        (repo / 'pin').write_text('8e894cf74414ab1eaea1e2b4e80a02f123df07b6')
        python = self.base / (name + '-python')
        python.write_text('# import 진단 외부 경계 fixture\n')
        return {'repo': str(repo), 'python': str(python), 'sim_image': name + '-tag',
                'sim_image_id': 'sha256:' + 'a' * 64}

    def snapshot(self):
        return {str(p): (p.is_dir(), p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                for p in [self.base, *self.base.rglob('*')]}

    def report(self, spec):
        def probe(runner, argv, **options):
            self.argv.append(list(argv))
            if argv[0] == 'git':
                return CommandOutcome('git rev-parse', 0, (Path(argv[2]) / 'pin').read_text())
            if argv[:3] == ['docker', 'image', 'inspect']:
                identity = 'sha256:' + ('b' if argv[3] == 'outer-tag' else 'a') * 64
                return CommandOutcome('docker image inspect', 0, json.dumps([{'Id': identity}]))
            if argv[1:4] == ['-I', '-B', '-c']:
                return CommandOutcome('driver Python', 0, 'ok')
            raise AssertionError('준비/네트워크/모델 실행 금지: ' + repr(argv))
        original = self.fixture.prep.readiness
        def engine(source, python):
            self.engine.append((Path(source), str(python)))
            return original(source, python)
        before = self.snapshot()
        with patch('agent_optimizer.readiness.load_experiment', return_value=spec), \
             patch.object(Runner, 'run', probe), \
             patch.object(self.fixture.prep, 'readiness', side_effect=engine), \
             patch.object(self.fixture.prep, 'probe_python', return_value={'ready': True}), \
             patch('shutil.which', return_value='/fixture/tool'), \
             patch('agent_optimizer.models.probe_model', side_effect=AssertionError('model probe')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('network')), \
             patch('pathlib.Path.mkdir', side_effect=AssertionError('mkdir')):
            result = collect_plan(self.plan, Registry())
        self.assertEqual(before, self.snapshot())
        self.assertEqual(len(result['checks']), len({row['id'] for row in result['checks']}))
        self.assertTrue(all(set(row) == {'id', 'area', 'status', 'message', 'remedy'} for row in result['checks']))
        return {row['id']: row for row in result['checks']}

    def test_legacy_first_profile_cannot_hide_native_dataset_failure(self):
        spec = copy.deepcopy(self.spec)
        native = spec['_profiles'][0]
        native['native']['dataset'] = str(self.base / 'missing.jsonl')
        agent = spec['_agents'][0]
        legacy = replace(agent, id='legacy-agent', supported_harnesses=('command',),
                         source=replace(agent.source, path=self.base / 'legacy-only'))
        spec['_agents'] = [legacy, agent]
        spec['_profiles'] = [{'id': 'legacy', 'adapter': 'command', 'command': ['fixture']}, native]
        spec['pairs'] = [{'agent': legacy.id, 'harness': 'legacy'}, {'agent': agent.id, 'harness': native['id']}]
        rows = self.report(spec)
        self.assertEqual(rows['native.selection']['status'], 'error')
        self.assertEqual(self.engine, [(agent.source.path, native['native']['python'])])

    def test_two_native_pairs_use_their_own_sources_interpreters_and_inner_assets(self):
        spec = copy.deepcopy(self.spec)
        first = spec['_profiles'][0]
        first['id'] = 'native-a'
        second = copy.deepcopy(first)
        second.update(id='native-b')
        second['native']['python'] = str(self.base / 'engine-b')
        second['native']['evaluator'] = self.evaluator('second')
        second_source = self.base / 'source-b'
        shutil.copytree(self.fixture.source, second_source)
        (second_source / 'skills/ace-rtl/scripts/ace_cvdp_native/cli.py').write_text('# 손상된 pin asset\n')
        agent_a = replace(spec['_agents'][0], id='agent-a')
        agent_b = replace(agent_a, id='agent-b', source=replace(agent_a.source, path=second_source))
        spec['_agents'], spec['_profiles'] = [agent_a, agent_b], [first, second]
        spec['pairs'] = [{'agent': 'agent-a', 'harness': 'native-a'}, {'agent': 'agent-b', 'harness': 'native-b'}]
        rows = self.report(spec)
        self.assertEqual(rows['native_source:agent-a/native-a']['status'], 'ok')
        self.assertEqual(rows['native_source:agent-b/native-b']['status'], 'error')
        self.assertEqual(self.engine, [(agent_a.source.path, first['native']['python']),
                                      (agent_b.source.path, second['native']['python'])])
        self.assertTrue(any(cmd[:4] == ['docker', 'image', 'inspect', 'second-tag'] for cmd in self.argv))
        second['native']['dataset'] = str(self.base / 'missing-dataset')
        rows = self.report(spec)
        self.assertEqual(rows['native.selection:agent-b/native-b']['status'], 'error')
        self.assertEqual(rows['native.selection:agent-a/native-a']['status'], 'ok')

    def test_outer_missing_assets_are_not_replaced_by_good_inner_settings(self):
        spec = copy.deepcopy(self.spec)
        spec['evaluator_config'] = {'repo': str(self.base / 'outer-missing'),
                                    'python': str(self.base / 'outer-missing-python')}
        rows = self.report(spec)
        self.assertEqual(rows['native.evaluator.assets']['status'], 'ok')
        self.assertEqual(rows['native.outer.evaluator.assets']['status'], 'error')
        self.assertEqual(rows['native.outer.evaluator.python']['status'], 'error')
        self.assertEqual(rows['native.outer.evaluator.dependencies']['status'], 'blocked')

    def test_native_source_subdir_uses_the_same_root_as_runtime_snapshot(self):
        spec = copy.deepcopy(self.spec)
        container = self.base / 'nested-source'
        source = container / 'active'
        shutil.copytree(self.fixture.source, source)
        agent = spec['_agents'][0]
        spec['_agents'] = [replace(agent, source=replace(agent.source, path=container, subdir='active'))]
        rows = self.report(spec)
        self.assertEqual(rows['native_source']['status'], 'ok')
        self.assertEqual(self.engine, [(source, spec['_profiles'][0]['native']['python'])])

    def test_default_matrix_checks_each_pair_and_is_independent_of_profile_order(self):
        spec = copy.deepcopy(self.spec)
        first = spec['_profiles'][0]
        first['id'] = 'native-a'
        second = copy.deepcopy(first)
        second['id'] = 'native-b'
        second['native']['python'] = str(self.base / 'engine-b')
        agent_a = replace(spec['_agents'][0], id='agent-a')
        source_b = self.base / 'source-b'
        shutil.copytree(self.fixture.source, source_b)
        agent_b = replace(agent_a, id='agent-b', source=replace(agent_a.source, path=source_b))
        spec['_agents'], spec['_profiles'] = [agent_a, agent_b], [first, second]
        expected = {(agent.source.path, profile['native']['python'])
                    for agent in spec['_agents'] for profile in spec['_profiles']}
        rows = self.report(spec)
        self.assertEqual(set(self.engine), expected)
        self.assertEqual(sum(key.startswith('native.selection:') for key in rows), 4)
        statuses = {key: row['status'] for key, row in rows.items() if key.startswith('native')}
        self.engine.clear()
        spec['_profiles'].reverse()
        reversed_rows = self.report(spec)
        self.assertEqual(set(self.engine), expected)
        self.assertEqual(statuses, {key: row['status'] for key, row in reversed_rows.items() if key.startswith('native')})

    def test_inner_empty_config_uses_runtime_environment_not_outer_settings(self):
        spec = copy.deepcopy(self.spec)
        spec['_profiles'][0]['native']['evaluator'] = {}
        with patch.dict(os.environ, {'CVDP_REPO': str(self.base / 'missing-inner-env'),
                                    'AGENT_OPT_CVDP_PYTHON': str(self.base / 'missing-inner-python')}):
            rows = self.report(spec)
        self.assertEqual(rows['native.evaluator.assets']['status'], 'error')
        self.assertEqual(rows['native.evaluator.python']['status'], 'error')
        self.assertEqual(rows['native.outer.evaluator.assets']['status'], 'ok')

    def test_invalid_inner_settings_do_not_hide_other_native_profile(self):
        spec = copy.deepcopy(self.spec)
        first = spec['_profiles'][0]
        first['id'] = 'native-a'
        second = copy.deepcopy(first)
        second['id'] = 'native-b'
        first['native']['evaluator'] = ['잘못된 객체']
        spec['_profiles'].append(second)
        rows = self.report(spec)
        agent = spec['_agents'][0].id
        self.assertEqual(rows['native.selection:' + agent + '/native-a']['status'], 'error')
        self.assertEqual(rows['native.evaluator.settings:' + agent + '/native-a']['status'], 'error')
        self.assertEqual(rows['native.evaluator.assets:' + agent + '/native-b']['status'], 'ok')
        self.assertEqual(rows['native.outer.evaluator.assets']['status'], 'ok')

    def test_outer_git_pin_and_image_identity_are_checked_independently(self):
        spec = copy.deepcopy(self.spec)
        outer = self.evaluator('outer')
        (Path(outer['repo']) / 'pin').write_text('0' * 40)
        spec['evaluator_config'] = outer
        rows = self.report(spec)
        self.assertEqual(rows['native.evaluator.pin']['status'], 'ok')
        self.assertEqual(rows['native.simulator.identity']['status'], 'ok')
        self.assertEqual(rows['native.outer.evaluator.pin']['status'], 'error')
        self.assertEqual(rows['native.outer.simulator.identity']['status'], 'error')
        self.assertTrue(any(cmd[0] == outer['python'] for cmd in self.argv))

    def test_equal_inner_outer_settings_reuse_only_read_only_probes(self):
        rows = self.report(self.spec)
        self.assertEqual(rows['native.outer.evaluator.assets']['status'], 'ok')
        self.assertEqual(rows['native.outer.simulator.identity']['status'], 'ok')
        self.assertEqual(sum(cmd[0] == 'git' for cmd in self.argv), 1)
        self.assertEqual(sum(cmd[:3] == ['docker', 'image', 'inspect'] for cmd in self.argv), 1)
        self.assertEqual(sum(cmd[0] == self.good['python'] for cmd in self.argv), 1)

    def test_shared_image_probe_does_not_share_inner_outer_identity_verdict(self):
        spec = copy.deepcopy(self.spec)
        spec['evaluator_config']['sim_image_id'] = 'sha256:' + 'b' * 64
        rows = self.report(spec)
        self.assertEqual(rows['native.simulator.identity']['status'], 'ok')
        self.assertEqual(rows['native.outer.simulator.identity']['status'], 'error')
        self.assertEqual(sum(cmd[:3] == ['docker', 'image', 'inspect'] for cmd in self.argv), 1)


class RetryRedactionReviewTests(unittest.TestCase):
    def test_actual_doctor_schema_retry_keeps_model_flag_and_path_without_probe(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {'AGENT_OPT_MODEL_ID': 'model', 'AGENT_OPT_MODEL_API_KEY': 'a'}, clear=True), \
             patch('agent_optimizer.models.probe_model', side_effect=AssertionError('model probe')):
            path = Path(directory) / 'model 공백/experiment.toml'
            report = collect_plan(path, Registry(), model=True)
        self.assertEqual(report['ready'], False)
        retry = report['checks'][0]['remedy'].split('Retry: ', 1)[1]
        self.assertEqual(shlex.split(retry), ['agent-opt', 'doctor', '--plan', str(path), '--model'])

    def test_public_model_and_short_key_do_not_destroy_flags_or_labels(self):
        command = shlex.join(['agent-opt', 'doctor', '--plan', '/tmp/한글 공백/model-plan.toml', '--model'])
        for key in ('fixture-key', 'a', 'Fix'):
            with self.subTest(key=key), patch.dict(os.environ, {'AGENT_OPT_MODEL_ID': 'model', 'AGENT_OPT_MODEL_API_KEY': key}, clear=True):
                row = check('model.configuration', 'model', False, '모델 준비 필요', '모델 설정을 수정하세요',
                            cause='준비되지 않은 모델', retry=command)
            self.assertEqual(row['remedy'].split('Retry: ', 1)[1], command)
            self.assertIn('Cause:', row['message'])

    def test_secret_in_user_path_does_not_become_a_fake_redacted_retry(self):
        secret = 'G-PRIVATE-PATH-SENTINEL'
        for fragment in (secret, 'a'):
            with self.subTest(fragment=fragment), patch.dict(os.environ, {'AGENT_OPT_MODEL_ID': 'model', 'AGENT_OPT_MODEL_API_KEY': fragment}, clear=True):
                row = check('model.configuration', 'model', False, '준비 필요', '설정을 확인하세요',
                            cause='키 문제', retry=shlex.join(['agent-opt', 'doctor', '--plan', '/tmp/' + fragment + '/plan.toml', '--model']))
            retry = row['remedy'].split('Retry: ', 1)[1]
            self.assertNotIn('agent-opt', retry)
            self.assertNotIn('[redacted]', retry)
            self.assertIn('명령을 표시할 수 없습니다', retry)
            if len(fragment) > 1:
                self.assertNotIn(fragment, str(row))

    def test_server_error_preserves_public_options_and_scrubs_real_credentials(self):
        from agent_optimizer.report_view import start_view
        from agent_optimizer.report_server import ReportServerError
        path = '/tmp/한글 공백/model-run'
        command = shlex.join(['agent-opt', 'report', path, '--html', '--serve', '--no-open', '--port', '4321'])
        with patch.dict(os.environ, {'AGENT_OPT_MODEL_ID': 'model', 'AGENT_OPT_MODEL_API_KEY': 'a'}, clear=True), \
             patch('agent_optimizer.report_view.verified_report', return_value=Path('/tmp/report.html')), \
             patch('agent_optimizer.report_view.start_report_server', side_effect=ReportServerError('port_in_use', '키 값=a; 포트 사용 중', error_number=48)):
            with self.assertRaises(ReportServerError) as raised:
                start_view({'run_dir': path}, port=4321, retry=command)
        text = str(raised.exception)
        self.assertIn('Cause:', text)
        self.assertIn('Fix:', text)
        self.assertIn('Retry: ' + command, text)
        self.assertNotIn('값=a', text)
        self.assertEqual(raised.exception.code, 'port_in_use')
