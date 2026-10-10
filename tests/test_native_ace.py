import json
import copy
import os
import sys
import subprocess
import tempfile
import types
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.contracts import AgentSpec, ConfigurationError, Evaluation, RunRequest
from agent_optimizer.models import ModelSettings
from agent_optimizer.workspace import CandidateStore, copy_tree
from test_native_cvdp import BASE, DATA, ROOT, load

UPSTREAM = BASE / 'external/ACE-RTL'


class NativeACETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not UPSTREAM.is_dir() or not DATA.is_file():
            raise unittest.SkipTest('고정 prepared upstream/데이터 없음')
        cls.bridge = load('native_bridge')
        cls.prepare = load('native_prepare')
        cls.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        cls.source = Path(cls.tmp.name) / 'source'
        cls.prepare.prepare_source(UPSTREAM, cls.source)
        cls.rows = load('native_cvdp').load_pinned_rows(DATA)
        cls.row = next(r for r in cls.rows if r['id'] == 'cvdp_copilot_64b66b_decoder_0001')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # The core-only shared environment lacks PyYAML. The trusted public
        # processor never parses YAML; mock only the unused import dependency.
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, {'yaml': types.ModuleType('yaml')}).start()

    def request(self, source=None, iterations=2):
        workspace = self.root / 'workspace'
        agent = workspace / 'agent'
        copy_tree(source or self.source, agent)
        task = workspace / 'task'
        task.mkdir()
        logs = self.root / 'logs'
        logs.mkdir()
        return RunRequest(workspace, agent, task, '공개 prompt', 0, 15,
                          {'id': 'ace_native', 'native': {'max_iterations': iterations, 'llm_timeout': 2, 'evaluator_timeout': 2}}, logs)

    def test_real_upstream_loop_reflects_then_passes_without_private_context(self):
        request = self.request()
        calls = []
        def completion(messages, **kwargs):
            calls.append(messages)
            self.assertEqual(kwargs['settings'].endpoint, 'http://127.0.0.1/v1/chat/completions')
            self.assertNotIn('PRIVATE_SENTINEL', json.dumps(messages))
            content = 'module decoder_64b66b; endmodule' if messages[0]['content'].startswith('generator') else 'FOCUSED_ERROR: mismatch\nREASONING: public failure\nGUIDANCE: fix public behavior\nCONTINUE: improve'
            if 'selected_rules' in messages[-1]['content']:
                content = '{"selected_rules": []}'
            return {'choices': [{'message': {'content': content}}], 'usage': {'prompt_tokens': 3, 'completion_tokens': 4}}
        evaluations = []
        def evaluate(task, output_dir, timeout):
            evaluations.append(output_dir)
            artifact = output_dir.parent / 'raw.json'
            artifact.write_text(json.dumps({'PRIVATE_SENTINEL': 'golden'}))
            return Evaluation('failed' if len(evaluations) == 1 else 'passed', {'passed': float(len(evaluations) != 1)}, 'PRIVATE_SENTINEL', {'raw_result': str(artifact)})
        settings = ModelSettings('http://127.0.0.1/v1/chat/completions', 'fixture-model', 'fixture-token')
        row = copy.deepcopy(self.row)
        row['harness']['files']['src/private-golden.py'] = 'PRIVATE_SENTINEL'
        row['output']['context']['rtl/decoder_64b66b.sv'] = 'PRIVATE_SENTINEL'
        result = self.bridge.run_native(request, row, evaluator=evaluate, settings=settings, completion=completion)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(len(result['attempts']), 2)
        self.assertEqual(len(evaluations), 2)
        self.assertTrue(any(r['role'] == 'reflector' for r in result['requests']))
        self.assertTrue((request.task_dir / 'rtl/decoder_64b66b.sv').is_file())
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))
        self.assertTrue(result['evaluations'][0]['evidence_paths'][0].endswith('raw.json'))
        self.assertIn(result['evaluations'][0]['evidence_paths'][0], result['evidence_paths'])
        self.assertEqual(result['usage_status'], 'partial')
        self.assertEqual(len({r['request_id'] for r in result['requests']}), len(result['requests']))

    def test_candidate_store_changes_consumed_prompt_and_imported_code(self):
        agent = AgentSpec('ace-rtl-native', self.source, self.source, '', ('ace_native',), ('native/guidance.md', 'native/orchestration.py'))
        store = CandidateStore(self.root / 'candidates', agent)
        a = store.create()
        b = store.create(a, {'native/guidance.md': 'GUIDANCE_B', 'native/orchestration.py': 'def guidance(role, text):\n    return "CODE_B\\n" + text\n'}, 'meta_harness')
        observed = []
        for i, candidate in enumerate([a, b]):
            self.root = Path(self.temp.name) / str(i)
            request = self.request(candidate.path, 1)
            def completion(messages, **kwargs):
                observed.append(json.dumps(messages))
                return {'choices': [{'message': {'content': 'module x; endmodule'}}]}
            result = self.bridge.run_native(request, self.row, evaluator=lambda *a: Evaluation('passed', {'passed': 1}), settings=ModelSettings('http://localhost/v1/chat/completions', 'fixture', 'token'), completion=completion)
            self.assertEqual(result['usage_status'], 'unreported')
            self.assertTrue(all(r['input_tokens'] is None for r in result['requests']))
            self.assertEqual(result['candidate_hash'], candidate.content_hash)
        self.assertNotIn('GUIDANCE_B', observed[0])
        self.assertIn('GUIDANCE_B', observed[1])
        self.assertIn('CODE_B', observed[1])
        store.verify(a)
        store.verify(b)
        with self.assertRaises(ConfigurationError):
            store.create(a, {'skills/ace-rtl/scripts/ace_cvdp_native/cli.py': 'bad'})

    def test_all_three_roles_use_same_transport_and_fail_closed(self):
        request = self.request()
        settings = ModelSettings('http://localhost/v1/chat/completions', 'fixture', 'secret')
        roles = []
        def completion(messages, **kwargs):
            roles.append(messages[0]['content'].split('\n')[0])
            self.assertEqual(kwargs['settings'], settings)
            return {'choices': [{'message': {'content': 'CONTINUE: public'}}]}
        transport = self.bridge.RoleTransport(request, settings, completion)
        for role in ['generator', 'reflector', 'coordinator']:
            transport.call(role, '공개 입력')
        self.assertEqual(roles, ['generator', 'reflector', 'coordinator'])
        def fail(*args, **kwargs):
            raise RuntimeError('HTTP 429 PRIVATE secret')
        transport.completion = fail
        with self.assertRaises(self.bridge.NativeCallError):
            transport.call('coordinator', '공개 입력')
        self.assertEqual(transport.requests[-1]['status'], 'api_error')
        self.assertNotIn('secret', json.dumps(transport.requests))

    def test_upstream_coordinator_reaches_product_model_on_iteration_twelve(self):
        request = self.request(iterations=13)
        calls = []
        generator_inputs = []
        def completion(messages, **kwargs):
            role = messages[0]['content'].split('\n')[0]
            calls.append(role)
            content = 'module x; endmodule' if role == 'generator' else 'CONTINUE: keep improving'
            if role == 'generator':
                generator_inputs.append(messages[-1]['content'])
            if role == 'coordinator':
                content = 'RESTART: public specification에서 재설계'
            if 'selected_rules' in messages[-1]['content']:
                content = '{"selected_rules": []}'
            return {'choices': [{'message': {'content': content}}]}
        count = [0]
        def evaluate(*args):
            count[0] += 1
            return Evaluation('passed' if count[0] == 13 else 'failed', {'passed': float(count[0] == 13)})
        result = self.bridge.run_native(request, self.row, evaluator=evaluate,
                                       settings=ModelSettings('http://localhost/v1/chat/completions', 'fixture', 'token'), completion=completion)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(set(calls), {'generator', 'reflector', 'coordinator'})
        self.assertEqual(len(result['attempts']), 13)
        self.assertIn('Fresh start requested', generator_inputs[-1])
        self.assertIn('Previous candidate:\n{}', generator_inputs[-1])

    def test_multifile_loop_submits_every_target(self):
        row = next(r for r in self.rows if 'cid002' in r['categories'] and len(r['output']['context']) == 3)
        request = self.request(iterations=1)
        def completion(*args, **kwargs):
            content = '\n'.join(f'// TARGET_FILE: {p}\nmodule m{i}; endmodule' for i, p in enumerate(row['output']['context']))
            return {'choices': [{'message': {'content': content}}]}
        def evaluate(task, output_dir, timeout):
            self.assertEqual(len(list(output_dir.rglob('*.sv'))), 3)
            return Evaluation('passed', {'passed': 1})
        result = self.bridge.run_native(request, row, evaluator=evaluate,
                                       settings=ModelSettings('http://localhost/v1/chat/completions', 'fixture', 'token'), completion=completion)
        self.assertEqual(len(result['generated_files']), 3)

    def test_generator_protocol_survives_candidate_guidance_changes(self):
        request = self.request(iterations=1)
        (request.agent_dir / 'native/guidance.md').write_text('일반적인 문제 해결 지침만 제공합니다')
        captured = []
        def completion(messages, **kwargs):
            captured.append(messages[0]['content'])
            return {'choices': [{'message': {'content': 'module x; endmodule'}}]}
        self.bridge.run_native(request, self.row, evaluator=lambda *args: Evaluation('passed', {'passed': 1}),
                               settings=ModelSettings('http://localhost/v1/chat/completions', 'fixture', 'token'),
                               completion=completion)
        self.assertIn('Markdown', captured[0])
        self.assertIn('// TARGET_FILE:', captured[0])

    def test_markdown_output_is_agent_incomplete_without_evaluator_call(self):
        request = self.request(iterations=1)
        def completion(*args, **kwargs):
            return {'choices': [{'message': {'content': '```verilog\nmodule x; endmodule\n```'}}]}
        def evaluator(*args):
            self.fail('출력 계약 위반을 공식 평가기에 전달하면 안 됩니다')
        with self.assertRaises((self.bridge.NativeCallError, ConfigurationError)) as raised:
            self.bridge.run_native(request, self.row, evaluator=evaluator,
                                   settings=ModelSettings('http://localhost/v1/chat/completions', 'fixture', 'token'),
                                   completion=completion)
        self.assertEqual(getattr(raised.exception, 'status', None), 'agent_incomplete')
        self.assertFalse((request.task_dir / 'rtl/decoder_64b66b.sv').exists())

    def test_nested_targets_accept_reordered_complete_sections(self):
        row = copy.deepcopy(self.row)
        row['output']['context'] = {'rtl/a.sv': '', 'rtl/sub/b.sv': ''}
        request = self.request(iterations=1)
        def completion(*args, **kwargs):
            return {'choices': [{'message': {'content': '// TARGET_FILE: rtl/sub/b.sv\nmodule b; endmodule\n// TARGET_FILE: rtl/a.sv\nmodule a; endmodule'}}]}
        result = self.bridge.run_native(request, row, evaluator=lambda *args: Evaluation('passed', {'passed': 1}),
                                       settings=ModelSettings('http://localhost/v1/chat/completions', 'fixture', 'token'), completion=completion)
        self.assertEqual(result['status'], 'passed')
        self.assertTrue((request.task_dir / 'rtl/sub/b.sv').is_file())
        self.assertTrue((request.task_dir / 'rtl/a.sv').is_file())

    def test_actual_cid007_lint_only_row_uses_native_loop_and_public_context(self):
        row = next(r for r in self.rows if r['id'] == 'cvdp_copilot_IIR_filter_0019')
        request = self.request(iterations=1)
        inputs = []
        def completion(messages, **kwargs):
            inputs.append(messages[-1]['content'])
            return {'choices': [{'message': {'content': 'module iir_filter; endmodule'}}]}
        result = self.bridge.run_native(request, row, evaluator=lambda *args: Evaluation('passed', {'passed': 1}),
                                       settings=ModelSettings('http://localhost/v1/chat/completions', 'fixture', 'token'), completion=completion)
        self.assertEqual(result['status'], 'passed')
        self.assertIn('LINT code review', inputs[0])
        self.assertNotIn('src/lint.py', inputs[0])
        self.assertEqual(result['generated_files'][0]['path'], 'rtl/iir_filter.sv')

    def test_invalid_provider_json_and_auth_timeout_fail_closed(self):
        request = self.request()
        settings = ModelSettings('http://localhost/v1/chat/completions', 'fixture', 'token')
        for role in ['generator', 'reflector', 'coordinator']:
            def invalid(*args, **kwargs):
                return {'choices': []}
            transport = self.bridge.RoleTransport(request, settings, invalid)
            with self.assertRaises(self.bridge.NativeCallError):
                transport.call(role, 'public')
            self.assertEqual(transport.requests[-1]['status'], 'api_error')
        def timeout(*args, **kwargs):
            raise TimeoutError('PRIVATE_SECRET')
        transport = self.bridge.RoleTransport(request, settings, timeout)
        with self.assertRaises(self.bridge.NativeCallError) as raised:
            transport.call('generator', 'public')
        self.assertEqual(raised.exception.status, 'api_error')
        self.assertEqual(transport.requests[-1]['status'], 'timeout')
        self.assertNotIn('PRIVATE_SECRET', json.dumps(transport.requests))

    def test_model_timeout_at_outer_deadline_remains_execution_timeout(self):
        request = self.request()
        settings = ModelSettings('http://localhost/v1/chat/completions', 'fixture', 'token')
        def timeout(*args, **kwargs):
            transport.deadline = time.monotonic() - 1
            raise TimeoutError('PRIVATE_SECRET')
        transport = self.bridge.RoleTransport(request, settings, timeout)
        with self.assertRaises(self.bridge.NativeCallError) as raised:
            transport.call('generator', 'public')
        self.assertEqual(raised.exception.status, 'timeout')

    def test_adapter_routes_native_worker_without_coding_binary(self):
        adapter = load('native_adapter')
        request = self.request()
        public = load('native_cvdp').public_row(self.row)
        (request.task_dir / 'native-task.json').write_text(json.dumps(public))
        recorded = []
        timeouts = []
        def run_worker(argv, cwd, logs, timeout, **kwargs):
            from agent_optimizer.contracts import ExecutionResult
            recorded.append(argv)
            timeouts.append(timeout)
            metadata = json.loads((logs / 'native-execution.json').read_text())
            metadata['status'] = 'passed'
            (logs / 'native-execution.json').write_text(json.dumps(metadata))
            return ExecutionResult('completed', 0, 0.01, '', '')
        original = adapter.sibling
        prep = original('native_prepare')
        prep.readiness = lambda *args, **kwargs: {'ready': True}
        with patch.object(adapter, 'sibling', side_effect=lambda name: prep if name == 'native_prepare' else original(name)), patch.object(adapter, 'run_worker', side_effect=run_worker):
            result = adapter.ACENative({'dataset': str(DATA), 'python': sys.executable}).run(request)
        self.assertEqual(result.status, 'completed')
        self.assertEqual(recorded[0][0], sys.executable)
        self.assertTrue(recorded[0][1].endswith('native_worker.py'))
        self.assertFalse(any(Path(arg).name in {'opencode', 'claude'} for arg in recorded[0]))
        self.assertLess(timeouts[0], request.timeout_seconds)

    def test_isolated_worker_home_preserves_host_docker_configuration(self):
        from agent_optimizer.contracts import ExecutionResult
        adapter = load('native_adapter')
        request = self.request()
        (request.task_dir / 'native-task.json').write_text(json.dumps(load('native_cvdp').public_row(self.row)))
        host = self.root / 'host-home'
        (host / '.docker').mkdir(parents=True)
        observed = {}
        def run_worker(argv, cwd, logs, timeout, **kwargs):
            observed.update(kwargs['env'])
            return ExecutionResult('completed', 0, .01, '', '')
        original = adapter.sibling
        prep = original('native_prepare')
        prep.readiness = lambda *args, **kwargs: {'ready': True, 'checks': []}
        with patch.dict(os.environ, {'HOME': str(host)}, clear=True), \
                patch.object(adapter, 'sibling', side_effect=lambda name: prep if name == 'native_prepare' else original(name)), \
                patch.object(adapter, 'run_worker', side_effect=run_worker):
            adapter.ACENative({'dataset': str(DATA)}).run(request)
        self.assertNotEqual(observed['HOME'], str(host))
        self.assertEqual(observed.get('DOCKER_CONFIG'), str(host / '.docker'))

    def test_native_agent_manifest_loads_existing_core_source_contract(self):
        from agent_optimizer.config import load_agent
        agent = load_agent(ROOT / 'examples/ace-rtl/source-native.toml')
        self.assertEqual(agent.id, 'ace-rtl-native')
        self.assertEqual(agent.source.kind, 'local')
        self.assertEqual(agent.prompt_file, 'native/guidance.md')

    def test_worker_adapter_preserves_usage_after_output_evaluator_and_api_errors(self):
        from agent_optimizer.contracts import ExecutionResult
        for mode in ['output', 'evaluator', 'api']:
            with self.subTest(mode=mode):
                self.root = Path(self.temp.name) / mode
                request = self.request()
                (request.task_dir / 'native-task.json').write_text(json.dumps(load('native_cvdp').public_row(self.row)))
                adapter = load('native_adapter')
                with patch.object(sys, 'path', [str(ROOT / 'examples/ace-rtl'), *sys.path]):
                    worker = load('native_worker')
                count = [0]
                def completion(*args, **kwargs):
                    count[0] += 1
                    if mode == 'api' and count[0] > 1:
                        raise RuntimeError('PRIVATE_SECRET auth')
                    content = '```verilog\nmodule x; endmodule\n```' if mode == 'output' else 'module x; endmodule'
                    return {'choices': [{'message': {'content': content}}], 'usage': {'completion_tokens': 9}}
                def evaluate(*args):
                    if mode == 'evaluator':
                        raise RuntimeError('PRIVATE_SECRET evaluator')
                    return Evaluation('failed', {'passed': 0})
                def native(request, row):
                    return self.bridge.run_native(request, row, evaluator=evaluate,
                                                  settings=ModelSettings('http://localhost/v1/chat/completions', 'fixture', 'token'), completion=completion)
                def run_worker(argv, cwd, logs, timeout, **kwargs):
                    with patch.object(sys, 'argv', argv[1:]), patch.object(worker, 'run_native', side_effect=native), patch.object(worker, 'NativeCallError', self.bridge.NativeCallError):
                        code = worker.main()
                    return ExecutionResult('process_error', code, .01, '', '')
                original = adapter.sibling
                prep = original('native_prepare')
                prep.readiness = lambda *args, **kwargs: {'ready': True, 'checks': []}
                with patch.object(adapter, 'sibling', side_effect=lambda name: prep if name == 'native_prepare' else original(name)), patch.object(adapter, 'run_worker', side_effect=run_worker):
                    result = adapter.ACENative({'dataset': str(DATA)}).run(request)
                sidecar = json.loads((request.logs / 'native-execution.json').read_text())
                self.assertEqual(result.status, 'agent_incomplete' if mode == 'output' else 'infrastructure_error')
                self.assertTrue(sidecar['requests'])
                self.assertEqual(sidecar['requests'][0]['status'], 'completed')
                self.assertIsNone(sidecar['requests'][0]['input_tokens'])
                self.assertEqual(sidecar['requests'][0]['output_tokens'], 9)
                self.assertEqual(sidecar['usage_status'], 'partial')
                self.assertNotIn('PRIVATE_SECRET', json.dumps(sidecar))

    def test_adapter_cleanup_has_one_total_deadline_and_skips_completed_networks(self):
        from dataclasses import replace
        from agent_optimizer.contracts import ExecutionResult
        request = replace(self.request(), timeout_seconds=.4)
        (request.task_dir / 'native-task.json').write_text(json.dumps(load('native_cvdp').public_row(self.row)))
        adapter = load('native_adapter')
        cleanup = load('native_cleanup')
        markers = []
        def run_worker(argv, cwd, logs, timeout, **kwargs):
            for i in range(6):
                marker = logs / 'native' / str(i) / 'native-owned-network.json'
                marker.parent.mkdir(parents=True)
                marker.write_text(json.dumps({'network': 'agent-opt-cvdp-' + f'{i:032x}', 'status': 'completed' if i < 3 else 'pending'}))
                markers.append(marker)
            return ExecutionResult('timeout', -9, .01, '', '')
        calls = []
        def stalled(argv, **kwargs):
            calls.append(argv)
            time.sleep(kwargs['timeout'])
            raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
        original = adapter.sibling
        prep = original('native_prepare')
        prep.readiness = lambda *args, **kwargs: {'ready': True, 'checks': []}
        def sibling(name):
            return prep if name == 'native_prepare' else cleanup if name == 'native_cleanup' else original(name)
        started = time.monotonic()
        with patch.object(adapter, 'sibling', side_effect=sibling), patch.object(adapter, 'run_worker', side_effect=run_worker), patch.object(cleanup.subprocess, 'run', side_effect=stalled):
            result = adapter.ACENative({'dataset': str(DATA)}).run(request)
        self.assertEqual(result.status, 'timeout')
        self.assertLess(time.monotonic() - started, .7)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('agent-opt-cvdp-' + f'{0:032x}', json.dumps(calls))
        sidecar = json.loads((request.logs / 'native-execution.json').read_text())
        self.assertEqual(sidecar['cleanup']['status'], 'incomplete')
        self.assertEqual(json.loads(markers[-1].read_text())['status'], 'deferred')

    def test_readiness_failure_sidecar_keeps_checks_and_unknown_provenance_null(self):
        adapter = load('native_adapter')
        request = self.request()
        lock = request.agent_dir / 'native/source-lock.json'
        data = json.loads(lock.read_text())
        data['revision'] = '0' * 40
        lock.write_text(json.dumps(data))
        result = adapter.ACENative({'python': '/missing/python'}).run(request)
        self.assertEqual(result.status, 'infrastructure_error')
        sidecar = json.loads((request.logs / 'native-execution.json').read_text())
        self.assertIsNone(sidecar['source_revision'])
        self.assertIsNone(sidecar['source_hash'])
        self.assertIsNone(sidecar['task_id'])
        self.assertEqual({c['id'] for c in sidecar['readiness_checks']}, {'native_source', 'native_python'})
        self.assertEqual(sidecar['usage_status'], 'unreported')

    def test_unsupported_preparation_has_sidecar_without_invented_requests(self):
        row = next(r for r in self.rows if r['id'] == 'cvdp_copilot_64b66b_encoder_0022')
        adapter = load('native_adapter')
        request = self.request()
        (request.task_dir / 'native-task.json').write_text(json.dumps(load('native_cvdp').public_row(row)))
        original = adapter.sibling
        prep = original('native_prepare')
        prep.readiness = lambda *args, **kwargs: {'ready': True, 'checks': []}
        with patch.object(adapter, 'sibling', side_effect=lambda name: prep if name == 'native_prepare' else original(name)):
            result = adapter.ACENative({'dataset': str(DATA)}).run(request)
        sidecar = json.loads((request.logs / 'native-execution.json').read_text())
        self.assertEqual(result.status, 'unsupported')
        self.assertEqual(sidecar['status'], 'unsupported')
        self.assertIn('PNR', sidecar['diagnostic'])
        self.assertEqual(sidecar['requests'], [])
        self.assertEqual(sidecar['cleanup']['status'], 'not_started')

    def test_missing_result_and_infra_stop_inner_loop(self):
        request = self.request()
        def completion(*args, **kwargs):
            return {'choices': [{'message': {'content': 'module x; endmodule'}}]}
        result = self.bridge.run_native(request, self.row, evaluator=lambda *args: Evaluation('infrastructure_error', {'passed': None}),
                                       settings=ModelSettings('http://localhost/v1/chat/completions', 'fixture', 'token'), completion=completion)
        self.assertEqual(result['status'], 'infra_error')
        self.assertEqual(len(result['attempts']), 1)

    def test_api_failure_preserves_completed_iteration_and_missing_usage(self):
        request = self.request()
        count = [0]
        def completion(messages, **kwargs):
            if messages[0]['content'].startswith('generator'):
                count[0] += 1
                if count[0] == 2:
                    raise RuntimeError('auth PRIVATE_SECRET')
                content = 'module x; endmodule'
            else:
                content = 'CONTINUE: repair'
            if 'selected_rules' in messages[-1]['content']:
                content = '{"selected_rules": []}'
            return {'choices': [{'message': {'content': content}}]}
        with self.assertRaises(self.bridge.NativeCallError):
            self.bridge.run_native(request, self.row, evaluator=lambda *args: Evaluation('failed', {'passed': 0}),
                                   settings=ModelSettings('http://localhost/v1/chat/completions', 'fixture', 'token'), completion=completion)
        progress = json.loads((request.logs / 'native-progress.json').read_text())
        self.assertEqual(len(progress['attempts']), 1)
        self.assertEqual(progress['attempts'][0]['status'], 'failed')
        requests = json.loads((request.logs / 'native-requests.json').read_text())
        self.assertEqual(requests[-1]['status'], 'api_error')
        self.assertNotIn('PRIVATE_SECRET', json.dumps(requests))

    def test_actual_worker_payload_and_sidecar_fixture(self):
        adapter = load('native_adapter')
        request = self.request(iterations=1)
        payload = {'workspace': str(request.workspace), 'agent_dir': str(request.agent_dir), 'task_dir': str(request.task_dir),
                   'prompt': request.prompt, 'seed': request.seed, 'timeout_seconds': request.timeout_seconds,
                   'profile': {**request.profile, 'native': {**request.profile['native'], 'dataset': str(DATA)}},
                   'logs': str(request.logs), 'task_id': self.row['id']}
        payload_path = request.logs / 'native-request.json'
        payload_path.write_text(json.dumps(payload))
        entry = self.root / 'fixture_worker.py'
        examples = ROOT / 'examples/ace-rtl'
        entry.write_text('import sys,types\n'
                         'sys.modules["yaml"]=types.ModuleType("yaml")\n'
                         f'sys.path.insert(0,{str(examples)!r})\n'
                         'import native_worker,native_bridge\n'
                         'from agent_optimizer.models import ModelSettings\n'
                         'from agent_optimizer.contracts import Evaluation\n'
                         'def completion(*args,**kwargs):\n'
                         '    return {"choices":[{"message":{"content":"module x; endmodule"}}]}\n'
                         'native_worker.run_native=lambda request,row: native_bridge.run_native(request,row,evaluator=lambda *a:Evaluation("passed",{"passed":1}),settings=ModelSettings("http://localhost/v1/chat/completions","fixture","token"),completion=completion)\n'
                         'raise SystemExit(native_worker.main())\n')
        env = {**os.environ, 'PYTHONPATH': str(ROOT / 'src')}
        result = adapter.run_worker([sys.executable, str(entry), str(payload_path)], request.workspace, request.logs, 10, env=env)
        self.assertEqual(result.status, 'completed', Path(result.stderr_path).read_text())
        sidecar = json.loads((request.logs / 'native-execution.json').read_text())
        self.assertEqual(sidecar['execution_mode'], 'native')
        self.assertEqual(sidecar['status'], 'passed')
        self.assertEqual(sidecar['usage_status'], 'unreported')
        self.assertTrue((request.task_dir / 'rtl/decoder_64b66b.sv').is_file())

    def test_existing_model_environment_reaches_native_roles(self):
        request = self.request(iterations=1)
        observed = []
        def completion(messages, **kwargs):
            observed.append(kwargs['settings'].model)
            self.assertEqual(kwargs['settings'].api_key, 'fixture-key')
            return {'choices': [{'message': {'content': 'module x; endmodule'}}]}
        with patch.dict(os.environ, {'AGENT_OPT_MODEL_BASE_URL': 'http://localhost/v1', 'AGENT_OPT_MODEL_ID': 'native-env-model', 'AGENT_OPT_MODEL_API_KEY': 'fixture-key'}, clear=False):
            result = self.bridge.run_native(request, self.row, evaluator=lambda *args: Evaluation('passed', {'passed': 1}), completion=completion)
        self.assertEqual(observed, ['native-env-model'])
        self.assertNotIn('fixture-key', json.dumps(result))

    def test_readiness_wrong_pin_asset_dependency_and_interpreter(self):
        with patch.object(self.prepare, 'probe_python', return_value={'ready': True, 'reason': ''}):
            ready = self.prepare.readiness(self.source, sys.executable)
            self.assertTrue(ready['ready'])
        self.assertFalse(self.prepare.readiness(self.source, '/missing/python')['ready'])
        (self.source / 'native/source-lock.json').read_text()
        copy_tree(self.source, self.root / 'bad')
        marker = self.root / 'bad/native/source-lock.json'
        data = json.loads(marker.read_text())
        data['revision'] = '0' * 40
        marker.write_text(json.dumps(data))
        self.assertFalse(self.prepare.readiness(self.root / 'bad', sys.executable)['ready'])
        (self.root / 'bad/skills/ace-rtl/scripts/ace_cvdp_native/cli.py').unlink()
        self.assertFalse(self.prepare.readiness(self.root / 'bad', sys.executable)['ready'])
        with patch.object(self.prepare, 'probe_python', return_value={'ready': False, 'reason': '필수 yaml 없음'}):
            self.assertFalse(self.prepare.readiness(self.source, sys.executable)['ready'])

    def test_worker_timeout_and_cancel_kills_descendant(self):
        adapter = load('native_adapter')
        script = self.root / 'child.py'
        script.write_text('import subprocess,sys,time\np=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"])\nprint(p.pid,flush=True)\ntime.sleep(60)\n')
        for cancel in [False, True]:
            logs = self.root / ('cancel' if cancel else 'timeout')
            started = time.monotonic()
            result = adapter.run_worker([sys.executable, str(script)], self.root, logs, 0.5, cancel=(lambda: time.monotonic() - started > 0.25) if cancel else None)
            self.assertEqual(result.status, 'interrupted' if cancel else 'timeout')
            self.assertEqual(json.loads((logs / 'cleanup.json').read_text())['process_group_terminated'], True)
            pid = int(Path(result.stdout_path).read_text().strip())
            state = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
            self.assertTrue(not state.stdout.strip() or state.stdout.strip().startswith('Z'))


if __name__ == '__main__':
    unittest.main()
