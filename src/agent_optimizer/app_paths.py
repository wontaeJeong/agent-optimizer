"""앱 생성 경로의 읽기 전용 해석. 디렉터리는 쓰기 경계에서만 만든다."""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.workspace import safe_path


APP_DIRECTORIES = frozenset({'experiments', 'runs', 'sessions', 'assets', 'cache', 'logs'})


def resolve_app_home(env: Mapping[str, str] | None = None, *, cwd: Path | None = None) -> Path:
    # cwd is retained for the shared API; relative overrides are deliberately rejected.
    values = os.environ if env is None else env
    value = values.get('AGENT_OPT_HOME', '')
    if not value:
        return Path.home() / '.agent-optimizer'
    try:
        path = Path(value).expanduser()
    except (TypeError, ValueError, RuntimeError):
        raise ConfigurationError('AGENT_OPT_HOME은 유효한 절대경로여야 합니다') from None
    if not path.is_absolute() or '\0' in str(path):
        raise ConfigurationError('AGENT_OPT_HOME은 절대경로여야 합니다. 상대경로는 허용하지 않습니다')
    return path


def app_path(name: str, *, app_home: Path | None = None) -> Path:
    if name not in APP_DIRECTORIES:
        raise ConfigurationError('지원하지 않는 앱 생성 디렉터리입니다')
    return safe_path(resolve_app_home() if app_home is None else app_home, name)


def resolve_run_base(spec: dict, output: Path | None = None) -> Path:
    if output is not None:
        return Path(output).resolve()
    if 'output_dir' in spec:
        value = spec['output_dir']
        if not isinstance(value, str):
            raise ConfigurationError('output_dir는 프로젝트 기준 상대경로여야 합니다')
        return safe_path(spec['_root'], value)
    return app_path('runs')


def resolve_session_base(output: Path | None = None) -> Path:
    return Path(output).resolve() if output is not None else app_path('sessions')


def resolve_dataset_cache(selection: str, cache_dir: Path | None = None) -> Path:
    return Path(cache_dir) if cache_dir is not None else safe_path(app_path('cache') / 'datasets', selection)
