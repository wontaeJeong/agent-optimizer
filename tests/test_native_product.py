"""로컬 계약 fixture; 실제 upstream/model/EDA 성공 증거가 아니다."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_optimizer.cli import main
from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import Evaluation, ExecutionResult
from agent_optimizer.native_selection import preparation, write_native_selection
from agent_optimizer.registry import Registry
from agent_optimizer.runner import run_experiment

ROOT = Path(__file__).resolve().parents[1]


class NativeProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        env = patch.dict(os.environ, {'AGENT_OPT_HOME': str(self.base / 'home')})
        env.start()
        self.addCleanup(env.stop)
        self.source = self.base / 'source'
        asset = self.source / 'skills/ace-rtl/scripts/ace_cvdp_native/cli.py'
        asset.parent.mkdir(parents=True)
        asset.write_text('# 계약 fixture; upstream loop를 실행하지 않습니다\n')
        native = self.source / 'native'
        native.mkdir()
        for file in ('guidance.md', 'orchestration.py'):
            shutil.copyfile(ROOT / 'examples/ace-rtl/native' / file, native / file)
        (native / 'source-lock.json').write_text(json.dumps({'schema_version': 1,
            'revision': 'fead921f18bb57345b5a41ef93ba625be208e99c', 'source_hash': 'a' * 64,
            'files': {asset.relative_to(self.source).as_posix(): hashlib.sha256(asset.read_bytes()).hexdigest()}}))
        rows = [{'id': name, 'categories': ['cid002'], 'input': {'prompt': '공개 구현 명세', 'context': {}},
            'output': {'response': '', 'context': {'rtl/result.sv': 'PRIVATE-SENTINEL'}},
            'harness': {'files': {'docker-compose.yml': 'services:\n  sim:\n    image: __OSS_SIM_IMAGE__\n',
                                   'private.py': 'PRIVATE-SENTINEL'}}} for name in ('row-train', 'row-validation', 'row-test')]
        self.data = self.base / 'fixture.jsonl'
        self.data.write_text('\n'.join(json.dumps(row) for row in rows))
        prep = preparation(ROOT)
        cvdp = prep.sibling('native_cvdp')
        cvdp.DATA_SHA256 = hashlib.sha256(self.data.read_bytes()).hexdigest()
        self.cvdp = cvdp
        sibling = prep.sibling
        prep.sibling = lambda name: cvdp if name == 'native_cvdp' else sibling(name)
        self.prep = prep
        prepared = patch('agent_optimizer.native_selection.preparation', return_value=prep)
        prepared.start()
        self.addCleanup(prepared.stop)
        repo = self.base / 'evaluator'
        repo.mkdir()
        (repo / 'run_benchmark.py').write_text('# 평가 fixture\n')
        self.evaluator = {'repo': str(repo), 'python': sys.executable}
        self.rows = {'row-train': 'train', 'row-validation': 'validation', 'row-test': 'test'}

    def test_explicit_four_cids_and_unsupported_row_fail_before_publish(self):
        rows = [json.loads(line) for line in self.data.read_text().splitlines()]
        blocked = json.loads(json.dumps(rows[0]))
        blocked.update(id='blocked-pnr', categories=['cid007'])
        blocked['harness']['files']['Dockerfile.synth'] = 'FROM __OSS_PNR_IMAGE__'
        rows.append(blocked)
        self.data.write_text('\n'.join(json.dumps(row) for row in rows))
        self.cvdp.DATA_SHA256 = hashlib.sha256(self.data.read_bytes()).hexdigest()
        with self.assertRaisesRegex(Exception, 'PNR'):
            write_native_selection(ROOT, 'baseline', cids=['cid007'], rows={'blocked-pnr': 'validation'}, dataset=self.data, source=self.source)
        self.assertFalse((self.base / 'home').exists())
        for cid in ('cid004', 'cid007', 'cid016'):
            row = json.loads(json.dumps(rows[0]))
            row.update(id='row-' + cid, categories=[cid])
            if cid == 'cid007':
                row['harness']['files']['src/lint.py'] = '# binary lint fixture'
            rows.append(row)
        self.data.write_text('\n'.join(json.dumps(row) for row in rows))
        self.cvdp.DATA_SHA256 = hashlib.sha256(self.data.read_bytes()).hexdigest()
        chosen = {'row-train': 'train', 'row-cid004': 'validation', 'row-cid007': 'validation', 'row-cid016': 'validation'}
        config = write_native_selection(ROOT, 'gepa', cids=['cid002', 'cid004', 'cid007', 'cid016'], rows=chosen,
                                        dataset=self.data, source=self.source, evaluator=self.evaluator)
        spec = load_experiment(config)
        self.assertEqual({task.id for task in spec['_tasks']}, set(chosen))
        self.assertEqual(spec['_benchmark_metadata']['native']['reviewed_cids'], ['cid002', 'cid004', 'cid007', 'cid016'])

    def test_core_selection_consumes_example_eligibility_without_redefining_it(self):
        from agent_optimizer.native_selection import selection_policy, validate_selection
        policy, prepare = selection_policy(ROOT)
        policy.CIDS.add('future-domain-cid')
        with patch('agent_optimizer.native_selection.selection_policy', return_value=(policy, prepare)):
            validate_selection(['future-domain-cid'], {'row': 'validation'}, 'baseline')
        self.assertFalse((self.base / 'home').exists())

    def test_offline_native_prepare_fails_without_install_or_replacing_selection(self):
        config = write_native_selection(ROOT, 'baseline', cids=['cid002'], rows=self.rows,
                                        dataset=self.data, source=self.source, evaluator=self.evaluator)
        original = config.read_bytes()
        source = (self.source / 'native/orchestration.py').read_bytes()
        with patch.object(self.prep, 'probe_python', return_value={'ready': False, 'reason': '의존성 fixture 미준비'}), contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['prepare', str(config), '--offline']), 2)
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual((self.source / 'native/orchestration.py').read_bytes(), source)
        self.assertFalse((self.base / 'home/runs').exists())

    def test_installed_native_assets_are_consumed_from_declared_distribution_origin(self):
        from types import SimpleNamespace
        from agent_optimizer.registry import NATIVE_DEPENDENCIES
        prefix = self.base / 'prefix'
        origin = prefix / 'share/agent-optimizer'
        for name in {*NATIVE_DEPENDENCIES, 'examples/ace-rtl/native_adapter.py'}:
            target = origin / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        metadata_file = Path('share/agent-optimizer/examples/ace-rtl/native_prepare.py')
        installed = SimpleNamespace(files=[metadata_file], locate_file=lambda file: prefix / file)
        with patch('agent_optimizer.native_selection.is_source_checkout', return_value=False), patch('importlib.metadata.distribution', return_value=installed):
            config = write_native_selection(self.base / 'foreign-cwd', 'baseline', cids=['cid002'], rows=self.rows,
                                            dataset=self.data, source=self.source, evaluator=self.evaluator)
        spec = load_experiment(config)
        self.assertEqual(spec['_root'], origin)
        self.assertEqual(spec['_agents'][0].source.path, self.source)
        registry = Registry()
        registry.load_plugins(origin, spec['plugins'])
        self.assertEqual(registry.resolve('harnesses', 'ace_native').__name__, 'ACENative')

    def test_modified_private_native_evaluation_rejected_before_run_creation(self):
        config = write_native_selection(ROOT, 'baseline', cids=['cid002'], rows=self.rows,
                                        dataset=self.data, source=self.source, evaluator=self.evaluator)
        benchmark = config.parent / 'tasks.json'
        document = json.loads(benchmark.read_text())
        document['tasks'][0]['evaluation']['row']['harness']['files']['private.py'] = '변경된 채점 기준'
        benchmark.write_text(json.dumps(document))
        with self.assertRaisesRegex(Exception, '고정'):
            run_experiment(load_experiment(config), Registry())
        self.assertFalse((self.base / 'home/runs').exists())

    def test_native_cli_writer_gepa_meta_active_surfaces_and_public_tasks(self):
        for optimizer, file, symbol in [('gepa', 'native/guidance.md', None), ('meta_harness', 'native/orchestration.py', 'guidance')]:
            with self.subTest(optimizer=optimizer), contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
                code = main(['init', '--project-root', str(self.base / 'foreign-cwd'), '--agent-preset', 'ace-rtl',
                    '--harness-profile', 'ace_native', '--dataset', 'cvdp', '--optimizer', optimizer,
                    '--cid', 'cid002', '--rows', json.dumps(self.rows), '--native-dataset', str(self.data),
                    '--native-source', str(self.source), '--native-evaluator', json.dumps(self.evaluator), '--yes'])
                self.assertEqual(code, 0)
                config = Path(json.loads(stdout.getvalue())['experiment'])
                spec = load_experiment(config)
                self.assertEqual(spec['_root'], ROOT)
                self.assertEqual(spec['_profiles'][0]['adapter'], 'ace_native')
                self.assertEqual(spec['stages'][0]['config']['file'], file)
                self.assertEqual(spec['stages'][0]['config'].get('required_symbol'), symbol)
                self.assertEqual([task.split for task in spec['_tasks']], ['train', 'validation', 'test'])
                self.assertTrue(spec['final_test'])
                self.assertEqual(spec['_agents'][0].source.path, self.source)
                for task in spec['_tasks']:
                    self.assertNotIn('PRIVATE-SENTINEL', json.dumps({'prompt': task.prompt, 'files': task.files}))
                self.assertNotIn('AGENT_OPT_MODEL_API_KEY', config.read_text())

    def test_native_baseline_runner_optional_result_event_and_report(self):
        config = write_native_selection(ROOT, 'baseline', cids=['cid002'], rows=self.rows,
                                        dataset=self.data, source=self.source, evaluator=self.evaluator)
        spec = load_experiment(config)
        registry = Registry()
        registry.load_project(ROOT)
        def harness_run(adapter, request):
            from agent_optimizer.workspace import digest
            public = json.loads((request.task_dir / 'native-task.json').read_text())
            (request.task_dir / 'rtl/result.sv').write_text('module result; endmodule')
            request.logs.mkdir(parents=True)
            (request.logs / 'native').mkdir()
            (request.logs / 'native/safe.json').write_text('{}')
            payload = {'schema_version': 1, 'execution_mode': 'native', 'profile': 'ace-native',
                'task_id': public['id'], 'candidate_hash': digest(request.agent_dir), 'source_revision': 'fead921f18bb57345b5a41ef93ba625be208e99c',
                'source_hash': 'a' * 64, 'status': 'completed', 'native_wall_time_seconds': .01,
                'attempts': [{'attempt': 1, 'iteration': 1, 'status': 'passed'}], 'requests': [],
                'generated_files': ['rtl/result.sv'], 'evidence_paths': ['native/safe.json'],
                'usage_status': 'unreported', 'prompt': 'PRIVATE-SENTINEL'}
            (request.logs / 'native-execution.json').write_text(json.dumps(payload))
            return ExecutionResult('completed', 0, .01, '', '', metrics={'agent_tokens': None})
        with patch.object(registry.resolve('harnesses', 'ace_native'), 'run', harness_run), patch.object(registry.resolve('evaluators', 'cvdp_native'), 'evaluate', return_value=Evaluation('passed', {'passed': 1.0})):
            run, summary = run_experiment(spec, registry)
        self.assertEqual(summary['status'], 'completed')
        events = [json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines()]
        trials = [event for event in events if event['event'] == 'trial_completed']
        self.assertTrue(trials)
        for event in trials:
            self.assertIn('native_execution', event)
            self.assertEqual(event['native_execution']['outer_evaluation']['count'], 1)
            self.assertEqual(event['metrics']['native_outer_evaluation_count'], 1)
            result = run / event['agent_id'] / event['harness_id'] / 'trials' / event['trial_id'] / 'result.json'
            self.assertEqual(json.loads(result.read_text())['native_execution'], event['native_execution'])
            self.assertNotIn('PRIVATE-SENTINEL', json.dumps(event['native_execution']))
        report = json.loads((run / 'report.json').read_text())
        self.assertEqual(len(report['native_execution']), len(trials))
        self.assertTrue(report['native_execution'][0]['evidence_paths'])
        self.assertNotIn('PRIVATE-SENTINEL', (run / 'report.html').read_text())

    def test_overflow_sidecar_keeps_completed_outer_trial_records(self):
        config = write_native_selection(ROOT, 'baseline', cids=['cid002'], rows=self.rows,
                                        dataset=self.data, source=self.source, evaluator=self.evaluator)
        spec = load_experiment(config)
        registry = Registry()
        registry.load_project(ROOT)
        def harness_run(adapter, request):
            from agent_optimizer.workspace import digest
            descriptor = json.loads((request.task_dir / 'native-task.json').read_text())
            (request.task_dir / 'rtl/result.sv').write_text('module result; endmodule')
            request.logs.mkdir(parents=True)
            payload = {'schema_version': 1, 'execution_mode': 'native', 'task_id': descriptor['id'],
                'candidate_hash': digest(request.agent_dir), 'profile': 'ace-native',
                'source_revision': 'fead921f18bb57345b5a41ef93ba625be208e99c', 'source_hash': 'a' * 64,
                'status': 'completed', 'native_wall_time_seconds': 10 ** 400}
            (request.logs / 'native-execution.json').write_text(json.dumps(payload))
            return ExecutionResult('completed', 0, .01, '', '')
        with patch.object(registry.resolve('harnesses', 'ace_native'), 'run', harness_run), patch.object(registry.resolve('evaluators', 'cvdp_native'), 'evaluate', return_value=Evaluation('passed', {'passed': 1.0})):
            run, summary = run_experiment(spec, registry)
        self.assertEqual(summary['status'], 'completed')
        trials = [json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines()
                  if json.loads(line)['event'] == 'trial_completed']
        self.assertEqual(len(trials), 2)
        for event in trials:
            self.assertEqual(event['status'], 'passed')
            self.assertEqual(event['metrics']['passed'], 1.0)
            self.assertNotIn('native_execution', event)
            self.assertEqual(event['native_execution_diagnostic'], {'code': 'missing_or_invalid_sidecar'})
            result = run / event['agent_id'] / event['harness_id'] / 'trials' / event['trial_id'] / 'result.json'
            self.assertEqual(json.loads(result.read_text())['status'], 'passed')
        self.assertTrue((run / 'report.html').is_file())

    def test_native_changes_after_preparation_regenerate_real_configuration(self):
        import asyncio
        from textual.widgets import Input, OptionList
        from agent_optimizer.tui import OptimizerApp
        other_source = self.base / 'other-source'
        shutil.copytree(self.source, other_source)
        (other_source / 'native/guidance.md').write_text('변경된 공개 guidance')
        async def flow(action):
            app = OptimizerApp(ROOT)
            app.selections = {'Agent': 'ace-rtl', 'Harness': 'ace-native', 'Optimizer': 'baseline', 'Dataset': 'cvdp'}
            app.native_values = {'cids': ['cid002'], 'rows': dict(self.rows), 'dataset': str(self.data),
                                 'source': str(self.source), 'evaluator': dict(self.evaluator)}
            async with app.run_test() as pilot:
                async def prepare():
                    app._prepare()
                    for _ in range(100):
                        await pilot.pause(.02)
                        if not app.busy:
                            break
                    self.assertTrue(app.preparation_complete, app.preparation_error)
                async def choose(identifier):
                    options = app.query_one(OptionList)
                    options.highlighted = options.get_option_index(identifier)
                    options.focus()
                    await pilot.press('enter')
                    await pilot.pause()
                await prepare()
                previous = app.experiment
                app.doctor_report = {'ready': True, 'checks': []}
                app.doctor_error = '이전 진단'
                app._show('Native')
                if action == 'rows-json':
                    app.native_field = 'rows'
                    app.on_input_submitted(Input.Submitted(app.query_one(Input), json.dumps({'row-validation': 'validation', 'row-test': 'validation'})))
                elif action == 'row-picker':
                    await choose('rows.pick')
                    await choose('row-test')
                    await choose('remove')
                    await choose('row-train')
                    await choose('validation')
                    await choose('native.back')
                else:
                    app.native_field = 'source'
                    app.on_input_submitted(Input.Submitted(app.query_one(Input), str(other_source)))
                await pilot.pause()
                self.assertIsNone(app.experiment)
                self.assertFalse(app.preparation_complete)
                self.assertIsNone(app.doctor_report)
                self.assertIsNone(app.doctor_error)
                expected = json.loads(json.dumps(app.native_values))
                app.action_back()
                app._show('Native')
                await choose('native.continue')
                app._show('Review')
                self.assertEqual(app.native_values, expected)
                await prepare()
                self.assertNotEqual(app.experiment, previous)
                self.assertTrue(previous.is_file())
                spec = load_experiment(app.experiment)
                self.assertEqual({task.id: task.split for task in spec['_tasks']}, expected['rows'])
                self.assertEqual(str(spec['_agents'][0].source.path), expected['source'])
                self.assertEqual(spec['final_test'], 'test' in expected['rows'].values())
                runtime_requests = []
                class RuntimeHarness:
                    @staticmethod
                    def validate_experiment(spec, profile):
                        from agent_optimizer.native_selection import verify_native_selection
                        verify_native_selection(spec, profile)
                    def __init__(self, config=None):
                        pass
                    def run(self, request):
                        descriptor = json.loads((request.task_dir / 'native-task.json').read_text())
                        runtime_requests.append((descriptor['id'], descriptor['split'], request.profile['native']['dataset'],
                                                 (request.agent_dir / 'native/guidance.md').read_text()))
                        (request.task_dir / 'rtl/result.sv').write_text('module result; endmodule')
                        return ExecutionResult('completed', 0, .01, '', '')
                class RuntimeEvaluator:
                    def __init__(self, config=None):
                        pass
                    def evaluate(self, task, output_dir, timeout_seconds):
                        return Evaluation('passed', {'passed': 1.0})
                original_resolve = Registry.resolve
                def resolve(registry, kind, name):
                    if (kind, name) == ('harnesses', 'ace_native'):
                        return RuntimeHarness
                    if (kind, name) == ('evaluators', 'cvdp_native'):
                        return RuntimeEvaluator
                    return original_resolve(registry, kind, name)
                with patch.object(Registry, 'resolve', resolve):
                    app._run()
                    for _ in range(100):
                        await pilot.pause(.02)
                        if not app.busy:
                            break
                self.assertEqual(app.run_result['status'], 'completed', app.run_result)
                wanted = {(row_id, split) for row_id, split in expected['rows'].items() if split != 'train'}
                self.assertEqual({(row_id, split) for row_id, split, _, _ in runtime_requests}, wanted)
                self.assertEqual({dataset for _, _, dataset, _ in runtime_requests}, {expected['dataset']})
                self.assertEqual({text for _, _, _, text in runtime_requests}, {(Path(expected['source']) / 'native/guidance.md').read_text()})
        with patch.dict(os.environ, {'AGENT_OPT_MODEL_BASE_URL': 'http://127.0.0.1:12345/v1', 'AGENT_OPT_MODEL_ID': 'fixture', 'AGENT_OPT_MODEL_API_KEY': 'KEY-SENTINEL'}):
            for action in ('rows-json', 'row-picker', 'source'):
                with self.subTest(action=action):
                    asyncio.run(flow(action))

    def test_native_review_split_counts_match_generated_final_test(self):
        import asyncio
        from agent_optimizer.tui import OptimizerApp
        async def flow():
            app = OptimizerApp(ROOT)
            app.selections = {'Agent': 'ace-rtl', 'Harness': 'ace-native', 'Optimizer': 'baseline', 'Dataset': 'cvdp'}
            app.native_values = {'cids': ['cid002'], 'rows': {'row-train': 'validation', 'row-validation': 'validation', 'row-test': 'test'},
                                 'source': str(self.source), 'dataset': str(self.data), 'evaluator': self.evaluator}
            async with app.run_test() as pilot:
                app._show('Review')
                self.assertIn('train 0 / validation 2 / test 1', app._review())
                self.assertIn('final_test=true', app._review())
                self.assertNotIn('train 1 / validation 1 · final_test=false', app._review())
                config = write_native_selection(ROOT, 'baseline', **{key: Path(value) if key in {'source', 'dataset'} else value for key, value in app.native_values.items()})
                app.experiment = config
                self.assertIn('train 0 / validation 2 / test 1', app._review())
                self.assertEqual(load_experiment(config)['budget']['max_trials'], 4)
        asyncio.run(flow())

    def test_native_tui_selection_prepare_matches_cli_contract(self):
        import asyncio
        from textual.widgets import OptionList
        from agent_optimizer.tui import OptimizerApp
        async def flow():
            with patch.dict(os.environ, {'AGENT_OPT_MODEL_BASE_URL': 'http://127.0.0.1:12345/v1',
                                         'AGENT_OPT_MODEL_ID': 'fixture-model', 'AGENT_OPT_MODEL_API_KEY': 'KEY-SENTINEL'}):
                app = OptimizerApp(ROOT)
                async with app.run_test() as pilot:
                    async def choose(identifier):
                        options = app.query_one(OptionList)
                        options.highlighted = options.get_option_index(identifier)
                        options.focus()
                        await pilot.press('enter')
                        await pilot.pause()
                    for identifier in ('new', 'ace-rtl', 'ace-native', 'baseline', 'cvdp'):
                        await choose(identifier)
                    self.assertEqual(app.page, 'Native')
                    app.native_values = {'cids': ['cid002'], 'rows': {}, 'dataset': str(self.data),
                                         'source': str(self.source), 'evaluator': self.evaluator}
                    await choose('rows.pick')
                    self.assertEqual(app.page, 'NativeRows')
                    for row, split in self.rows.items():
                        await choose(row)
                        self.assertEqual(app.page, 'NativeSplit')
                        await choose(split)
                    self.assertEqual(app.native_values['rows'], self.rows)
                    self.assertFalse((self.base / 'home').exists())
                    await choose('native.back')
                    await choose('native.continue')
                    self.assertEqual(app.page, 'Model')
                    self.assertEqual(app._required_model_fields(), ['AGENT_OPT_MODEL_BASE_URL', 'AGENT_OPT_MODEL_ID', 'AGENT_OPT_MODEL_API_KEY'])
                    self.assertNotIn('AGENT_OPT_MODEL', app._model_selector_fields())
                    app._show('Review')
                    self.assertIn('rtl/result.sv', app._review())
                    self.assertNotIn('KEY-SENTINEL', app._review())
                    app._prepare()
                    for _ in range(100):
                        await pilot.pause(.02)
                        if not app.busy:
                            break
                    self.assertTrue(app.preparation_complete, app.preparation_error)
                    tui_spec = load_experiment(app.experiment)
                    cli = write_native_selection(ROOT, 'baseline', cids=['cid002'], rows=self.rows,
                        dataset=self.data, source=self.source, evaluator=self.evaluator)
                    cli_spec = load_experiment(cli)
                    self.assertEqual(tui_spec['_profiles'], cli_spec['_profiles'])
                    self.assertEqual(tui_spec['_tasks'], cli_spec['_tasks'])
                    self.assertEqual(tui_spec['_agents'][0].source, cli_spec['_agents'][0].source)
                    self.assertEqual(tui_spec.get('stages', []), cli_spec.get('stages', []))
                    self.assertIn('ace-native', app._review())
        asyncio.run(flow())
