"""trusted native worker 엔트리. 소스 snapshot 밖 bridge에서 private 평가를 소유한다."""
import json
import sys
import time
from pathlib import Path

from agent_optimizer.contracts import RunRequest
from agent_optimizer.results import write_json

from native_bridge import NativeCallError, cvdp, run_native


def main():
    payload = json.loads(Path(sys.argv[1]).read_text())
    task_id = payload.pop('task_id')
    for field in ['workspace', 'agent_dir', 'task_dir', 'logs']:
        payload[field] = Path(payload[field])
    request = RunRequest(**payload)
    rows = cvdp.load_pinned_rows(request.profile['native']['dataset'])
    row = next(r for r in rows if r['id'] == task_id)
    started = time.monotonic()
    try:
        run_native(request, row)
    except NativeCallError as exc:
        sidecar = json.loads((request.logs / 'native-execution.json').read_text())
        sidecar['status'] = exc.status
        sidecar['native_wall_time_seconds'] = time.monotonic() - started
        path = request.logs / 'native-requests.json'
        sidecar['requests'] = json.loads(path.read_text()) if path.exists() else []
        sidecar['usage_status'] = 'partial' if any(r['input_tokens'] is not None for r in sidecar['requests']) else 'unreported'
        write_json(request.logs / 'native-execution.json', sidecar)
        return 2
    except Exception as exc:
        # Candidate/provider errors must not leak contents/keys via tracebacks.
        sidecar = json.loads((request.logs / 'native-execution.json').read_text())
        sidecar['status'] = 'infrastructure_error'
        sidecar['error_type'] = type(exc).__name__
        sidecar['native_wall_time_seconds'] = time.monotonic() - started
        write_json(request.logs / 'native-execution.json', sidecar)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
