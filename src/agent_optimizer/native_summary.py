"""Native sidecar의 공개 요약 producer. private 원문·임의 필드는 복제하지 않는다."""
import json
import math
import os
from pathlib import Path
import re
import stat
import sys

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.workspace import safe_path


def summarize_native(logs: Path, *, task_id: str, candidate_hash: str, profile: str,
                     outer_count: int, outer_wall_time: float | None,
                     generated_targets=(), source_revision=None, source_hash=None) -> dict | None:
    try:
        file = safe_path(logs, 'native-execution.json')
        with os.fdopen(os.open(file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), encoding='utf-8') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return None
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            return None
        data = json.loads(raw)
        if (not isinstance(data, dict) or type(data.get('schema_version')) is not int or data['schema_version'] != 1 or
                data.get('execution_mode') != 'native' or data.get('task_id') not in (None, task_id) or
                data.get('candidate_hash') not in (None, candidate_hash) or data.get('profile') not in (None, profile)):
            return None
        if ((source_revision is not None and data.get('source_revision') not in (None, source_revision)) or
                (source_hash is not None and data.get('source_hash') not in (None, source_hash))):
            return None
        secrets = [value for key, value in os.environ.items() if value and any(term in key.upper() for term in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD'))]

        def text(value):
            if (isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:+-]{0,127}', value)
                    and '://' not in value and not any(secret in value for secret in secrets)):
                return value
            return None

        def number(value, integer=False):
            if value is None:
                return None
            if type(value) not in ({int} if integer else {int, float}):
                raise ValueError('native 숫자 형식이 잘못됐습니다')
            if type(value) is int and value > int(sys.float_info.max):
                raise ValueError('native 숫자가 지원 범위를 벗어났습니다')
            if value < 0 or type(value) is float and not math.isfinite(value):
                raise ValueError('native 숫자는 유한한 비음수여야 합니다')
            return value

        def status(value):
            return value if value in ('started', 'completed', 'passed', 'failed', 'error',
                'infrastructure_error', 'unsupported', 'timeout', 'interrupted', 'process_error',
                'api_error', 'agent_incomplete') else None

        def digest(value, size):
            return value if isinstance(value, str) and re.fullmatch(r'[a-fA-F0-9]{' + str(size) + '}', value) else None

        def paths(values, evidence=False):
            result = []
            for value in values if isinstance(values, list) else []:
                if (not text(value) or Path(value).is_absolute() or ':' in value or
                        any(part in {'', '.', '..'} or part.startswith('.') for part in value.split('/'))):
                    continue
                if evidence:
                    target = safe_path(logs, value)
                    if not (target.is_file() or target.is_dir()) or not (value == 'native' or value.startswith('native/') or value == 'native-execution.json'):
                        continue
                if value not in result:
                    result.append(value)
            return result

        def files(values):
            result = []
            for item in values if isinstance(values, list) else []:
                name = item.get('path') if isinstance(item, dict) else item
                if name in generated_targets and paths([name]):
                    result.append({'path': name, 'sha256': digest(item.get('sha256'), 64) if isinstance(item, dict) else None})
            return result

        result = {'schema_version': 1, 'execution_mode': 'native',
                  'task_id': task_id, 'candidate_hash': candidate_hash, 'profile': profile,
                  'source_revision': digest(data.get('source_revision'), 40), 'source_hash': digest(data.get('source_hash'), 64),
                  'status': status(data.get('status')), 'native_wall_time_seconds': number(data.get('native_wall_time_seconds')),
                  'attempts': [], 'requests': [], 'generated_files': files(data.get('generated_files')),
                  'evidence_paths': paths(data.get('evidence_paths'), True),
                  'outer_evaluation': {'purpose': 'trusted_final', 'owner': 'GroupRunner.trial',
                                       'count': outer_count, 'wall_time_seconds': outer_wall_time}}
        for item in data.get('attempts', []) if isinstance(data.get('attempts'), list) else []:
            if isinstance(item, dict):
                result['attempts'].append({'attempt': number(item.get('attempt'), True),
                    'iteration': number(item.get('iteration'), True), 'status': status(item.get('status')),
                    'generated_files': files(item.get('generated_files')),
                    'evidence_paths': paths(item.get('evidence_paths', [item.get('evidence_path')]), True)})
        seen = set()
        for item in data.get('requests', []) if isinstance(data.get('requests'), list) else []:
            if not isinstance(item, dict):
                continue
            request_id = text(item.get('request_id'))
            if request_id is None or not re.fullmatch(r'[A-Za-z0-9_.-]+', request_id) or request_id in seen or item.get('role') not in ('generator', 'reflector', 'coordinator'):
                continue
            seen.add(request_id)
            result['requests'].append({'request_id': request_id, 'role': item['role'], 'model': text(item.get('model')),
                'status': status(item.get('status')), **{key: number(item.get(key), key.endswith('tokens'))
                for key in ('duration_seconds', 'input_tokens', 'output_tokens', 'cost_usd')}})
        measured = any(item[key] is not None for item in result['requests'] for key in ('input_tokens', 'output_tokens', 'cost_usd'))
        result['usage_status'] = 'partial' if measured or data.get('usage_status') == 'partial' else 'unreported'
        result['active_surface_hashes'] = {name: value for name, value in data.get('active_surface_hashes', {}).items()
            if name in ('guidance', 'orchestration') and digest(value, 64)} if isinstance(data.get('active_surface_hashes'), dict) else {}
        result['readiness_checks'] = [{'id': text(item.get('id')), 'ready': item.get('ready') if type(item.get('ready')) is bool else None}
            for item in data.get('readiness_checks', []) if isinstance(item, dict) and item.get('id') in ('native_source', 'native_python')] if isinstance(data.get('readiness_checks'), list) else []
        cleanup = data.get('cleanup')
        if isinstance(cleanup, dict):
            value = cleanup.get('status')
            result['cleanup'] = {'status': value if value in ('completed', 'incomplete', 'deferred', 'not_started') else None}
        return result
    except (OSError, ValueError, TypeError, OverflowError, RecursionError, ConfigurationError):
        return None
