"""플러그인 반환값이 기록·선택·독립 stage 계약을 훼손하지 않아야 한다."""
import json
import unittest

from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError, Evaluation, ExecutionResult, OptimizationResult
from agent_optimizer.objectives import aggregate, select
from agent_optimizer.registry import Registry
from agent_optimizer.runner import run_experiment
from support import test_project


class CoreIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)
        self.spec = load_experiment(self.root / 'examples/minimal/experiment.toml')
        self.spec['_agents'] = self.spec['_agents'][:1]
        self.spec.update(stages=[], final_stages=['baseline'], final_test=False)
        self.registry = Registry()
        self.registry.factories['harnesses']['fixture'] = lambda: type('Harness', (), {
            'run': staticmethod(lambda request: ExecutionResult('completed', 0, .01, '', ''))})()
        self.spec['evaluator'] = 'controlled'
        self.registry.factories['evaluators']['controlled'] = lambda config: type('Evaluator', (), {
            'evaluate': staticmethod(lambda task, output, timeout: Evaluation('passed', {'passed': 1.0}))})()

    def optimizer(self, optimize):
        self.registry.factories['optimizers']['controlled'] = lambda: type('Optimizer', (), {
            'optimize': staticmethod(optimize)})()
        self.spec.update(stages=[{'id': 'search', 'optimizer': 'controlled'}], final_stages=['search'])

    def experiment(self):
        return run_experiment(self.spec, self.registry, self.root / 'runs')

    def test_validation_view_mutation_cannot_rewrite_frozen_selection_or_trials(self):
        def optimize(context, seeds, config):
            view = context.evaluate_validation(seeds[0])
            view['metrics']['solve_rate'] = 99.0
            view['tasks'][0]['metrics']['passed'] = 99.0
            return OptimizationResult(seeds)
        self.optimizer(optimize)
        run, summary = self.experiment()
        group = summary['groups'][0]
        self.assertEqual(group['selected'][0]['metrics']['solve_rate'], 1.0)
        frozen = json.loads((run / 'rtl-solo/fixture/frozen_selection.json').read_text())
        self.assertEqual(frozen[0]['metrics']['solve_rate'], 1.0)
        events = [json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines()]
        self.assertEqual(next(e for e in events if e['event'] == 'trial_completed')['metrics']['passed'], 1.0)

    def test_train_aggregate_mutation_cannot_poison_cached_evidence(self):
        def optimize(context, seeds, config):
            row = context.evaluate(seeds[0])
            row['metrics']['solve_rate'] = 99.0
            return OptimizationResult(seeds, {'score': context.evaluate(seeds[0])['metrics']['solve_rate']})
        self.optimizer(optimize)
        _, summary = self.experiment()
        self.assertEqual(summary['groups'][0]['stages'][0]['checkpoint']['score'], 1.0)

    def test_history_mutation_cannot_poison_later_train_evidence(self):
        def optimize(context, seeds, config):
            context.evaluate(seeds[0])
            history = context.history()
            history[0]['metrics']['passed'] = 99.0
            history[0]['execution']['status'] = 'forged'
            return OptimizationResult(seeds, {'history': context.history()})
        self.optimizer(optimize)
        _, summary = self.experiment()
        record = summary['groups'][0]['stages'][0]['checkpoint']['history'][0]
        self.assertEqual(record['metrics']['passed'], 1.0)
        self.assertEqual(record['execution']['status'], 'completed')

    def test_returned_candidate_from_another_stage_is_rejected_before_validation(self):
        candidates = []
        def first(context, seeds, config):
            candidates.append(context.propose(seeds[0], {'prompts/system.md': 'first'}, 'first'))
            return OptimizationResult(seeds)
        def second(context, seeds, config):
            return OptimizationResult(candidates)
        for name, implementation in [('first', first), ('second', second)]:
            self.registry.factories['optimizers'][name] = lambda impl=implementation: type('Optimizer', (), {
                'optimize': staticmethod(impl)})()
        self.spec.update(stages=[{'id': name, 'optimizer': name} for name in ['first', 'second']],
                         final_stages=['second'])
        with self.assertRaises(ConfigurationError):
            self.experiment()
        run = next((self.root / 'runs').iterdir())
        events = [json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines()]
        self.assertFalse(any(e['event'] == 'trial_started' and e['candidate_id'] == 'c0002' for e in events))

    def test_unknown_evaluator_status_cannot_become_a_valid_winner(self):
        self.registry.factories['evaluators']['controlled'] = lambda config: type('Evaluator', (), {
            'evaluate': staticmethod(lambda task, output, timeout: Evaluation('typo_passed', {'passed': 1.0}))})()
        with self.assertRaises(ConfigurationError):
            self.experiment()
        run = next((self.root / 'runs').iterdir())
        summary = json.loads((run / 'summary.json').read_text())
        self.assertEqual(summary['status'], 'error')
        self.assertEqual(summary['groups'][0]['selected'], [])

    def test_completed_harness_with_nonzero_exit_cannot_be_scored_as_success(self):
        self.registry.factories['harnesses']['fixture'] = lambda: type('Harness', (), {
            'run': staticmethod(lambda request: ExecutionResult('completed', 7, .01, '', ''))})()
        with self.assertRaises(ConfigurationError):
            self.experiment()

    def test_mixed_success_and_ineligible_groups_preserve_partial_success(self):
        self.spec['_agents'] = load_experiment(self.root / 'examples/minimal/experiment.toml')['_agents']
        def evaluate(task, output, timeout):
            if 'rtl-team' in output.parts:
                return Evaluation('infrastructure_error', {'passed': None})
            return Evaluation('passed', {'passed': 1.0})
        self.registry.factories['evaluators']['controlled'] = lambda config: type('Evaluator', (), {
            'evaluate': staticmethod(evaluate)})()
        _, summary = self.experiment()
        self.assertEqual([group['status'] for group in summary['groups']],
                         ['completed', 'no_eligible_candidate'])
        self.assertEqual(summary['status'], 'partial')


class MetricIntegrityTests(unittest.TestCase):
    def test_nonnumeric_or_unrepresentable_metrics_are_unavailable(self):
        objective = {'metrics': [{'name': 'score', 'direction': 'maximize'}]}
        for value in [True, '1.0', 10**400, float('nan'), float('inf')]:
            with self.subTest(value_type=type(value).__name__):
                self.assertEqual(aggregate([{'metrics': {'score': value}}], [{'name': 'score'}]),
                                 {'score': None})
                self.assertEqual(select([{'valid': True, 'metrics': {'score': value}}], objective), [])

    def test_mean_of_large_finite_scores_stays_finite(self):
        self.assertEqual(aggregate([{'metrics': {'score': 1e308}}] * 2,
                                   [{'name': 'score', 'aggregate': 'mean'}]), {'score': 1e308})

    def test_overflowing_sum_is_unavailable(self):
        self.assertEqual(aggregate([{'metrics': {'score': 1e308}}] * 2,
                                   [{'name': 'score', 'aggregate': 'sum'}]), {'score': None})
