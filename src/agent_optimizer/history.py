"""보고서 생성과 무관한 읽기 전용 실행 이력과 최소 lifecycle 기록."""
from __future__ import annotations

import contextlib
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.workspace import safe_path


_ID = re.compile(r'([0-9]{8}T[0-9]{6}Z)-[0-9a-f]{8}')
_STATUSES = {'running', 'completed', 'partial', 'no_eligible_candidate', 'interrupted',
             'budget_exhausted', 'source_error', 'error', 'failed', 'scored_failure'}
_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
_MAX_JSON = 16 * 1024 * 1024


class HistoryRows(list[dict]):
    """일반 list와 호환되며 건너뛴 자료의 진단도 조회할 수 있다."""

    def __init__(self, rows, diagnostics: list[str]):
        super().__init__(rows)
        self.diagnostics = diagnostics


def _created(run_id: str) -> str | None:
    match = _ID.fullmatch(run_id)
    if match is None:
        return None
    try:
        return datetime.strptime(match[1], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def record_lifecycle(root: Path, *, status: str, kind: str = 'run',
                     experiment_name: str | None = None, session_id: str | None = None,
                     created_at: str | None = None, children: list[dict] | None = None) -> dict:
    if status not in _STATUSES or kind not in {'run', 'session'}:
        raise ConfigurationError('lifecycle의 종류 또는 상태가 올바르지 않습니다')
    safe_path(root, '.')
    root.mkdir(parents=True, exist_ok=True)
    target = safe_path(root, 'lifecycle.json')
    now = datetime.now(timezone.utc).isoformat()
    data = {'schema_version': 1, 'kind': kind, 'run_id': root.name,
            'created_at': created_at or _created(root.name) or now, 'updated_at': now,
            'status': status, 'experiment_name': experiment_name, 'session_id': session_id}
    if children is not None:
        data['children'] = [{key: child[key] for key in (
            'dataset', 'status', 'run_dir', 'report', 'trials_used') if key in child} for child in children]
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=root,
                                         prefix='.lifecycle-', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return data


@contextlib.contextmanager
def _open_directory(path: Path):
    # macOS host aliases are outside the controlled boundary, not user symlinks.
    absolute = path.absolute()
    if sys.platform == 'darwin' and absolute.parts[1:2] in {('var',), ('tmp',)}:
        absolute = Path('/private').joinpath(*absolute.parts[1:])
    fd = os.open(absolute.anchor, _DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, _DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _read(fd: int, name: str) -> str:
    with os.fdopen(os.open(name, _FILE, dir_fd=fd), 'r', encoding='utf-8') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('일반 파일이 아닙니다')
        text = stream.read(_MAX_JSON + 1)
    if len(text) > _MAX_JSON:
        raise ValueError('이력 자료가 크기 제한을 초과했습니다')
    return text


def _json(fd: int, name: str, diagnostic: list[str]) -> dict:
    try:
        value = json.loads(_read(fd, name))
        if not isinstance(value, dict):
            raise ValueError('객체가 아닙니다')
        return value
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, UnicodeError, RecursionError):
        diagnostic.append(f'{name}: 손상되었거나 안전하게 읽을 수 없습니다')
        return {}


def _regular(fd: int, name: str) -> bool:
    try:
        child = os.open(name, _FILE, dir_fd=fd)
        try:
            return stat.S_ISREG(os.fstat(child).st_mode)
        finally:
            os.close(child)
    except OSError:
        return False


def _row(fd: int, root: Path, *, kind: str, session_id: str | None = None) -> dict | None:
    created = _created(root.name)
    if created is None:
        return None
    diagnostic: list[str] = []
    summary = _json(fd, 'summary.json', diagnostic)
    manifest = _json(fd, 'manifest.json', diagnostic)
    lifecycle = _json(fd, 'lifecycle.json', diagnostic)
    if lifecycle and (type(lifecycle.get('schema_version')) is not int
                      or lifecycle['schema_version'] != 1 or lifecycle.get('run_id') != root.name
                      or lifecycle.get('kind') != kind):
        diagnostic.append('lifecycle.json: 실행 식별자 또는 schema가 올바르지 않습니다')
        lifecycle = {}
    if summary and kind == 'run' and (type(summary.get('schema_version')) is not int
                                     or summary['schema_version'] != 1
                                     or summary.get('run_id') != root.name
                                     or not isinstance(summary.get('groups'), list)
                                     or type(summary.get('trials_used')) is not int
                                     or summary['trials_used'] < 0):
        diagnostic.append('summary.json: 실행 식별자 또는 schema가 올바르지 않습니다')
        summary = {}
    status = summary.get('status')
    if not isinstance(status, str) or status not in _STATUSES or status == 'running':
        status = lifecycle.get('status', status)
    if not isinstance(status, str) or status not in _STATUSES:
        status = 'unknown'
        try:
            for line in _read(fd, 'events.jsonl').splitlines():
                event = json.loads(line)
                if isinstance(event, dict) and event.get('event') in {
                        'interrupted', 'error', 'source_error', 'budget_exhausted'}:
                    status = event['event']
        except FileNotFoundError:
            pass
        except (OSError, ValueError, UnicodeError, RecursionError, TypeError):
            diagnostic.append('events.jsonl: 손상되었거나 안전하게 읽을 수 없습니다')
    if status == 'running':
        status = 'stale'
        diagnostic.append('종료 기록이 없습니다. 현재 실행 여부는 확인되지 않았습니다')
    elif status == 'unknown':
        diagnostic.append('유효한 실행 상태 기록이 없습니다')
    experiment = manifest.get('experiment', {})
    name = experiment.get('name') if isinstance(experiment, dict) else None
    name = name if isinstance(name, str) else lifecycle.get('experiment_name')
    name = name if isinstance(name, str) else None
    filename = 'index.html' if kind == 'session' else 'report.html'
    report = root / filename if _regular(fd, filename) else None
    if report is None:
        diagnostic.append('보고서가 없거나 안전한 일반 파일이 아닙니다')
    info = os.fstat(fd)
    recorded_session = session_id or (root.name if kind == 'session' else lifecycle.get('session_id'))
    if not isinstance(recorded_session, str) or _created(recorded_session) is None:
        recorded_session = None
    return {'run_id': root.name, 'run_dir': str(root), 'created_at': created,
            'status': status, 'experiment_name': name, 'session_id': recorded_session,
            'report_path': str(report) if report is not None else None,
            'diagnostic': '; '.join(diagnostic) or None, 'kind': kind,
            'trials_used': summary.get('trials_used'),
            '_directory_identity': (info.st_dev, info.st_ino)}


def _scan_base(base: Path, *, kind: str, session_id: str | None = None,
               diagnostics: list[str] | None = None) -> list[dict]:
    found = []
    diagnostics = [] if diagnostics is None else diagnostics
    try:
        with _open_directory(base) as fd:
            base = base.resolve()
            with os.scandir(fd) as children:
                names = sorted(child.name for child in children if _created(child.name) is not None)
            for name in names:
                try:
                    child_fd = os.open(name, _DIRECTORY, dir_fd=fd)
                except OSError as exc:
                    diagnostics.append(f'{base / name}: 안전한 실행 디렉터리가 아닙니다 ({type(exc).__name__})')
                    continue
                try:
                    row = _row(child_fd, base / name, kind=kind, session_id=session_id)
                    if row is not None:
                        found.append(row)
                        if row['diagnostic']:
                            diagnostics.append(f'{row["run_dir"]}: {row["diagnostic"]}')
                finally:
                    os.close(child_fd)
    except FileNotFoundError:
        pass
    except OSError as exc:
        diagnostics.append(f'{base}: 이력 경로를 안전하게 읽을 수 없습니다 ({type(exc).__name__})')
    return found


def _session_children(root: Path, session_id: str, diagnostics: list[str]) -> list[dict]:
    found = []
    try:
        with _open_directory(root / 'runs') as fd:
            with os.scandir(fd) as entries:
                slots = [entry.name for entry in entries if re.fullmatch(r'[0-9]+', entry.name)]
            for slot in sorted(slots):
                found.extend(_scan_base(root / 'runs' / slot, kind='run', session_id=session_id,
                                        diagnostics=diagnostics))
    except FileNotFoundError:
        pass
    except OSError as exc:
        diagnostics.append(f'{root}: session child 경로를 안전하게 읽을 수 없습니다 ({type(exc).__name__})')
    return found


def list_history(*, app_home: Path, project_root: Path | None = None,
                 run_bases=(), limit: int = 10) -> list[dict]:
    if type(limit) is not int or limit < 0:
        raise ConfigurationError('이력 limit은 0 이상의 정수여야 합니다')
    bases = [(Path(app_home) / 'runs', 'run'), (Path(app_home) / 'sessions', 'session')]
    if project_root is not None:
        bases.extend((Path(project_root) / 'runs' / name, 'run') for name in ('', 'dev-live'))
    bases.extend((Path(base), 'run') for base in run_bases)
    rows: dict[str, dict] = {}
    diagnostics: list[str] = []
    for base, kind in bases:
        for row in _scan_base(base, kind=kind, diagnostics=diagnostics):
            if kind == 'session':
                children = _session_children(Path(row['run_dir']), row['run_id'], diagnostics)
                row['child_runs'] = [child['run_dir'] for child in children]
                for child in children:
                    rows[child['run_dir']] = child
            rows.setdefault(row['run_dir'], row)
    by_id: dict[str, dict] = {}
    for row in rows.values():
        by_id.setdefault(row['run_id'], row)
    return HistoryRows(sorted(by_id.values(), key=lambda row: (row['created_at'], row['run_dir']),
                              reverse=True)[:limit], list(dict.fromkeys(diagnostics)))


def verified_report(row: dict) -> Path:
    try:
        root = Path(row['run_dir'])
        kind = row.get('kind', 'run')
        if not root.is_absolute() or kind not in {'run', 'session'} or row['run_id'] != root.name:
            raise ValueError('실행 경로가 올바르지 않습니다')
        expected = root / ('index.html' if kind == 'session' else 'report.html')
        if row.get('report_path') != str(expected):
            raise ValueError('기록된 보고서 경로가 올바르지 않습니다')
        with _open_directory(root) as fd:
            current = _row(fd, root, kind=kind, session_id=row.get('session_id'))
            if (current is None or current['report_path'] is None
                    or current['status'] != row['status']
                    or current['_directory_identity'] != row.get('_directory_identity')):
                raise ValueError('이력 조회 이후 실행 경로 또는 상태가 변경됐습니다')
        return expected
    except (OSError, ValueError, TypeError, KeyError):
        raise ConfigurationError('보고서를 안전하게 확인할 수 없습니다. 이력을 다시 조회하세요') from None
