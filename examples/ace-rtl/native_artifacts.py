"""모든 native 종료 경로의 공개 metadata journal 복구."""
import json

from agent_optimizer.results import write_json
from agent_optimizer.workspace import safe_path

REQUEST_FIELDS = ('request_id', 'role', 'model', 'status', 'duration_seconds',
                  'input_tokens', 'output_tokens', 'cost_usd')


def finalize(logs, *, status=None, error_type=None, elapsed=None):
    path = safe_path(logs, 'native-execution.json')
    sidecar = json.loads(path.read_text())
    if status is not None:
        sidecar['status'] = status
    if error_type is not None:
        sidecar['error_type'] = error_type
    if elapsed is not None:
        sidecar['native_wall_time_seconds'] = elapsed
    journal = safe_path(logs, 'native-requests.json')
    if journal.is_file():
        try:
            records = json.loads(journal.read_text())
            if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
                raise ValueError()
            # Replace, never append: journal and sidecar describe the same calls.
            sidecar['requests'] = [{k: r.get(k) for k in REQUEST_FIELDS} for r in records]
        except (OSError, ValueError):
            sidecar['request_journal_status'] = 'invalid'
    for record in sidecar['requests']:
        if record['status'] == 'started':
            record['status'] = 'interrupted'
    sidecar['usage_status'] = 'partial' if any(
        r.get('input_tokens') is not None or r.get('output_tokens') is not None
        for r in sidecar['requests']) else 'unreported'
    progress = safe_path(logs, 'native-progress.json')
    if progress.is_file() and not sidecar['attempts']:
        try:
            data = json.loads(progress.read_text())
            sidecar['attempts'] = data['attempts']
            sidecar['evaluations'] = data['evaluations']
            sidecar['generated_files'] = sidecar['attempts'][-1]['generated_files'] if sidecar['attempts'] else []
            sidecar['evidence_paths'] = ['native', *[p for e in sidecar['evaluations'] for p in e.get('evidence_paths', [])]]
        except (OSError, ValueError, KeyError, TypeError):
            sidecar['progress_journal_status'] = 'invalid'
    write_json(path, sidecar)
    return sidecar
