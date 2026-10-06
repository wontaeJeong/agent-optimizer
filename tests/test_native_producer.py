import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class NativeProducerTests(unittest.TestCase):
    def test_overflow_numeric_fields_reject_only_optional_summary(self):
        from agent_optimizer.native_summary import summarize_native
        with tempfile.TemporaryDirectory() as directory:
            logs = Path(directory)
            payload = {'schema_version': 1, 'execution_mode': 'native', 'task_id': 'task',
                'candidate_hash': 'a' * 64, 'profile': 'ace-native', 'status': 'completed',
                'native_wall_time_seconds': .1, 'attempts': [{'attempt': 1, 'iteration': 1}],
                'requests': [{'request_id': 'r1', 'role': 'generator', 'model': 'fixture', 'status': 'completed',
                              'duration_seconds': .1, 'input_tokens': 1, 'output_tokens': 1, 'cost_usd': None}]}
            for section, field in [('root', 'native_wall_time_seconds'), ('attempts', 'attempt'),
                                   ('attempts', 'iteration'), ('requests', 'duration_seconds'),
                                   ('requests', 'input_tokens'), ('requests', 'output_tokens'), ('requests', 'cost_usd')]:
                with self.subTest(section=section, field=field):
                    document = json.loads(json.dumps(payload))
                    record = document if section == 'root' else document[section][0]
                    record[field] = 10 ** 400
                    (logs / 'native-execution.json').write_text(json.dumps(document))
                    self.assertIsNone(summarize_native(logs, task_id='task', candidate_hash='a' * 64,
                        profile='ace-native', outer_count=1, outer_wall_time=.2))

    def test_malformed_nonfinite_numbers_do_not_become_partial_success(self):
        from agent_optimizer.native_summary import summarize_native
        with tempfile.TemporaryDirectory() as directory:
            logs = Path(directory)
            for value in ('1e999', '-1e999', '-1', 'true', '"1"', '{}'):
                with self.subTest(value=value):
                    (logs / 'native-execution.json').write_text('{"schema_version":1,"execution_mode":"native","task_id":"task","candidate_hash":"' + 'a' * 64 + '","profile":"ace-native","native_wall_time_seconds":' + value + '}')
                    self.assertIsNone(summarize_native(logs, task_id='task', candidate_hash='a' * 64, profile='ace-native',
                                                       outer_count=1, outer_wall_time=.2))

    def test_sidecar_whitelist_identity_paths_and_secret_exclusion(self):
        from agent_optimizer.native_summary import summarize_native
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'AGENT_OPT_MODEL_API_KEY': 'KEY-SENTINEL'}):
            logs = Path(directory)
            (logs / 'native').mkdir()
            (logs / 'native/safe.json').write_text('{}')
            payload = {'schema_version': 1, 'execution_mode': 'native', 'task_id': 'task', 'candidate_hash': 'a' * 64,
                       'profile': 'ace-native', 'source_revision': 'b' * 40, 'source_hash': 'c' * 64,
                       'status': 'completed', 'native_wall_time_seconds': 1.2, 'usage_status': 'partial',
                       'prompt': 'PRIVATE-SENTINEL', 'private_path': '/private/secret',
                       'attempts': [{'attempt': 1, 'iteration': 2, 'status': 'passed', 'prompt': 'PRIVATE-SENTINEL'}],
                       'generated_files': [{'path': 'rtl/result.sv', 'sha256': 'd' * 64, 'content': 'PRIVATE-SENTINEL'}],
                       'evidence_paths': ['native/safe.json', '/private/secret', '../secret'],
                       'requests': [{'request_id': 'req1', 'role': 'generator', 'model': 'KEY-SENTINEL', 'input_tokens': 0, 'output_tokens': None, 'cost_usd': None, 'duration_seconds': 0.2, 'status': 'completed', 'content': 'PRIVATE-SENTINEL'}]}
            (logs / 'native-execution.json').write_text(json.dumps(payload))
            result = summarize_native(logs, task_id='task', candidate_hash='a' * 64, profile='ace-native', outer_count=1, outer_wall_time=.3, generated_targets=['rtl/result.sv'])
            text = json.dumps(result)
            for forbidden in ('PRIVATE-SENTINEL', 'KEY-SENTINEL', '/private/secret', '../secret', 'prompt', 'content'):
                self.assertNotIn(forbidden, text)
            self.assertEqual(result['requests'][0]['input_tokens'], 0)
            self.assertIsNone(result['requests'][0]['output_tokens'])
            self.assertEqual(result['evidence_paths'], ['native/safe.json'])
            self.assertEqual(result['outer_evaluation']['count'], 1)
            self.assertIsNone(summarize_native(logs, task_id='task', candidate_hash='a' * 64, profile='ace-native',
                outer_count=1, outer_wall_time=.3, source_revision='e' * 40, source_hash='c' * 64))
            payload['task_id'] = 'other'
            (logs / 'native-execution.json').write_text(json.dumps(payload))
            self.assertIsNone(summarize_native(logs, task_id='task', candidate_hash='a' * 64, profile='ace-native', outer_count=0, outer_wall_time=None))

    def test_invalid_and_symlink_sidecar_never_blocks_outer_record(self):
        from agent_optimizer.native_summary import summarize_native
        with tempfile.TemporaryDirectory() as directory:
            logs = Path(directory)
            options = dict(task_id='task', candidate_hash='a' * 64, profile='ace-native', outer_count=0, outer_wall_time=None)
            (logs / 'native-execution.json').write_text('not json')
            self.assertIsNone(summarize_native(logs, **options))
            (logs / 'native-execution.json').unlink()
            (logs / 'native-execution.json').symlink_to('/etc/passwd')
            self.assertIsNone(summarize_native(logs, **options))
