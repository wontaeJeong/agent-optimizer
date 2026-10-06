"""trusted native worker 엔트리. 소스 snapshot 밖 bridge에서 private 평가를 소유한다."""
import json
import sys
import time
from pathlib import Path

from agent_optimizer.contracts import RunRequest

from native_bridge import NativeCallError, cvdp, run_native
from native_artifacts import finalize


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
        finalize(request.logs, status=exc.status, elapsed=time.monotonic() - started)
        return 2
    except Exception as exc:
        # Candidate/provider errors must not leak contents/keys via tracebacks.
        finalize(request.logs, status='infrastructure_error', error_type=type(exc).__name__, elapsed=time.monotonic() - started)
        return 2
    finalize(request.logs)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
