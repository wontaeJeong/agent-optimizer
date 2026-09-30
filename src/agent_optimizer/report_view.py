"""제품 보고서 열람: 읽기 전용 이력 재검증 후 loopback 서버 시작."""
from pathlib import Path
import os
import signal
import subprocess
import sys

from agent_optimizer.app_paths import resolve_app_home
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.history import list_history, verified_report
from agent_optimizer.report_server import start_report_server


def report_row(run_dir: Path, *, project_root: Path | None = None) -> dict:
    directory = run_dir.absolute()
    rows = list_history(app_home=resolve_app_home(), project_root=project_root,
                        run_bases=(directory.parent,), limit=10000)
    row = next((row for row in rows if Path(row['run_dir']) == directory.resolve()), None)
    if row is None:
        raise ConfigurationError('저장된 실행 이력을 확인할 수 없습니다; agent-opt report RUN --html로 명시 생성하세요')
    return row


def open_browser(url: str) -> bool:
    process = None
    try:
        environment = {key: value for key, value in os.environ.items() if key in {
            'PATH', 'HOME', 'USER', 'LOGNAME', 'DISPLAY', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS',
            'XDG_RUNTIME_DIR', 'XDG_CONFIG_HOME', 'BROWSER', 'LANG', 'LC_ALL', 'SYSTEMROOT'}}
        environment['PYTHONDONTWRITEBYTECODE'] = '1'
        command = 'import sys,webbrowser; sys.exit(0 if webbrowser.open(sys.argv[1]) else 1)'
        process = subprocess.Popen([sys.executable, '-c', command, url], env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            shell=False, start_new_session=True)
        return process.wait(timeout=5) == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                process.wait(timeout=.2)
            except subprocess.TimeoutExpired:
                pass


def start_view(row: dict, *, port: int = 0):
    return start_report_server(verified_report(row), port=port)


def view_status(url: str, opened: bool) -> str:
    return (f'HTML 보고서: {url}\n브라우저: ' + ('열기 요청 성공' if opened else '자동 열기 없음/실패; URL을 직접 여세요') +
            '\nlocalhost는 실행 머신입니다. SSH에서는 포트포워딩이 필요합니다. HTML 한 파일만 제공됩니다.')
