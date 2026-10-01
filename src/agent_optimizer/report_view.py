"""제품 보고서 열람: 읽기 전용 이력 재검증 후 loopback 서버 시작."""
from pathlib import Path
import os
import signal
import subprocess
import sys
import shlex

from agent_optimizer.app_paths import resolve_app_home
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.history import list_history, verified_report
from agent_optimizer.report_server import ReportServerError, start_report_server


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


def start_view(row: dict, *, port: int = 0, retry: str | None = None):
    try:
        return start_report_server(verified_report(row), port=port)
    except ReportServerError as exc:
        from agent_optimizer.diagnostics import redact_text
        fixes = {
            'missing_report': 'agent-opt report RUN --html로 명시 생성하세요',
            'unsafe_report': '승인된 일반 report.html/index.html 파일을 다시 선택하세요',
            'report_unreadable': '보고서와 상위 디렉터리의 읽기 권한을 확인하세요',
            'invalid_port': '0 또는 1~65535의 정수 포트를 지정하세요',
            'port_in_use': f'127.0.0.1:{port}의 기존 서버를 종료하거나 --port 0으로 명시 재시도하세요',
            'bind_failed': 'loopback 주소와 네트워크 권한을 확인하세요',
            'start_failed': '소켓·파일 자원을 확인한 뒤 재시도하세요',
        }
        retry = retry or f"agent-opt report {shlex.quote(row['run_dir'])} --serve --port {port}"
        raise ReportServerError(exc.code, redact_text(
            f"보고서 서버 시작 실패\nStage: report.serve\nCause: {exc}\n"
            f"Blocked by: {exc.code}\nFix: {fixes.get(exc.code, '저장 보고서와 loopback 설정을 확인하세요')}\nRetry: {retry}"),
            error_number=exc.errno) from None


def view_status(url: str, opened: bool) -> str:
    from agent_optimizer.locale import t
    return (f"HTML {t('보고서')}: {url}\n{t('브라우저')}: " + t('열기 요청 성공' if opened else '자동 열기 없음/실패; URL을 직접 여세요') +
            '\n' + t('localhost는 실행 머신입니다. SSH에서는 포트포워딩이 필요합니다. HTML 한 파일만 제공됩니다.'))
