"""검토된 binary CID의 공식 CVDP 최종 평가. Agent pass flag를 소비하지 않는다."""
import importlib.util
import json
import types
import uuid
import time
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, Evaluation
from agent_optimizer.results import write_json


def sibling(name):
    spec = importlib.util.spec_from_file_location('_native_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


official = sibling('evaluator')
cvdp = sibling('native_cvdp')
cleanup = sibling('native_cleanup')


class NativeCVDPEvaluator(official.CVDPEvaluator):
    def validate_benchmark(self, tasks, metadata):
        super().validate_benchmark(tasks, metadata)
        for task in tasks:
            verdict = cvdp.inspect_row(task.evaluation['row'])
            if not verdict['supported']:
                raise ConfigurationError(verdict['reason'])

    def evaluate(self, task, output_dir, timeout_seconds):
        deadline = time.monotonic() + timeout_seconds
        verdict = cvdp.inspect_row(task.evaluation['row'])
        if not verdict['supported']:
            return Evaluation('unsupported', {'passed': None}, verdict['reason'])
        if task.evaluation['targets'] != verdict['targets']:
            raise ConfigurationError('trusted native target 계약 불일치')
        try:
            cvdp.read_outputs(output_dir, verdict['targets'])
        except ConfigurationError:
            return Evaluation('failed', {'passed': 0.0}, '필수 native target 누락/잘못된 출력')
        # The inherited evaluator owns a Docker network. Journal its exact ID
        # before launching so an outer SIGKILL can still clean its containers.
        identity = uuid.uuid4().hex
        network = 'agent-opt-cvdp-' + identity
        marker = output_dir.parent / 'native-owned-network.json'
        write_json(marker, {'network': network, 'status': 'pending'})
        previous = official.uuid
        previous_cleanup = official.cleanup_network
        def bounded_cleanup(network, logs):
            result = cleanup.cleanup_network(network, logs, deadline=deadline)
            write_json(marker, {'network': network, 'status': result['status'], 'cleanup_reason': result['reason']})
        official.cleanup_network = bounded_cleanup
        official.uuid = types.SimpleNamespace(uuid4=lambda: types.SimpleNamespace(hex=identity))
        try:
            result = super().evaluate(task, output_dir, max(.001, timeout_seconds - min(1, timeout_seconds * .1)))
        finally:
            official.uuid = previous
            official.cleanup_network = previous_cleanup
        if result.status not in {'passed', 'failed'}:
            return result
        artifact = result.artifacts.get('raw_result')
        if not artifact:
            return Evaluation('infrastructure_error', {'passed': None}, '공식 CVDP 결과 누락')
        try:
            record = json.loads(Path(artifact).read_text())[task.id]
            status, feedback = cvdp.classify_result(record)
            return Evaluation(status, {'passed': 1.0 if status == 'passed' else 0.0 if status == 'failed' else None},
                              feedback, result.artifacts)
        except (OSError, ValueError, KeyError):
            return Evaluation('infrastructure_error', {'passed': None}, '공식 CVDP 결과 스키마 오류')
