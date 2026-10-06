"""저장된 HTML 한 파일만 제공하는 loopback 보고서 서버."""
from __future__ import annotations

import errno
import os
import socket
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError


class ReportServerError(ConfigurationError):
    """원본 경로나 예외 내용을 노출하지 않는 서버 진단."""

    def __init__(self, code: str, message: str, *, error_number: int | None = None):
        super().__init__(message)
        self.code = code
        self.errno = error_number


def _open_directory(path: Path) -> int:
    # Only the host's standard macOS aliases are canonicalized; user-controlled
    # ancestors, the run root and the report are all opened without following links.
    if path.parts[1:2] in (("var",), ("tmp",)):
        prefix = Path(path.anchor) / path.parts[1]
        path = prefix.resolve().joinpath(*path.parts[2:])
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _identity(descriptor: int) -> tuple[int, int]:
    value = os.fstat(descriptor)
    return value.st_dev, value.st_ino


def _open_report(directory: int, name: str) -> int:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory)
    value = os.fstat(descriptor)
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        os.close(descriptor)
        raise OSError(errno.EINVAL, "승인된 일반 HTML 파일이 아닙니다")
    return descriptor


class _ApprovedReport:
    def __init__(self, path: Path):
        self.path = path
        self.directory = _open_directory(path.parent)
        try:
            self.file = _open_report(self.directory, path.name)
            try:
                with os.fdopen(os.dup(self.file), "rb") as stream:
                    self.content = stream.read()
            except BaseException:
                os.close(self.file)
                raise
        except BaseException:
            os.close(self.directory)
            raise

    def valid(self) -> bool:
        try:
            directory = _open_directory(self.path.parent)
            try:
                if _identity(directory) != _identity(self.directory):
                    return False
                descriptor = _open_report(directory, self.path.name)
                try:
                    return _identity(descriptor) == _identity(self.file)
                finally:
                    os.close(descriptor)
            finally:
                os.close(directory)
        except OSError:
            return False

    def close(self) -> None:
        os.close(self.file)
        os.close(self.directory)


class _ReportHTTPServer(HTTPServer):
    def __init__(self, *args):
        self._connection_lock = threading.Lock()
        self._connection = None
        self._stopping = False
        super().__init__(*args)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(0.5)
        with self._connection_lock:
            if self._stopping:
                connection.close()
                raise OSError(errno.ECANCELED, "서버 종료 중")
            self._connection = connection
        return connection, address

    def shutdown_request(self, request):
        with self._connection_lock:
            self._connection = None
        super().shutdown_request(request)

    def stop_requests(self):
        with self._connection_lock:
            self._stopping = True
            if self._connection is not None:
                try:
                    self._connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def handle_error(self, request, client_address):
        # HTTP parsing, client disconnects and private paths must not enter logs.
        pass


def _handler(report: _ApprovedReport):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def version_string(self):
            return "AgentOptimizerReport"

        def send_error(self, code, message=None, explain=None):
            if code == 501:
                code = 405
            content = "보고서 요청을 제공할 수 없습니다.\n".encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            if code == 405:
                self.send_header("Allow", "GET, HEAD")
            self.end_headers()
            self.close_connection = True
            if getattr(self, "command", None) != "HEAD":
                self.wfile.write(content)

        def do_GET(self):
            # Compare the raw request target: BaseHTTPRequestHandler normalizes
            # leading //, and decoding would unnecessarily widen this allowlist.
            target = self.requestline.split()[1]
            authority = f"127.0.0.1:{self.server.server_port}"
            hosts = self.headers.get_all("Host", [])
            if (target not in {"/", "/" + report.path.name}
                    or hosts != [authority] or not report.valid()):
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(report.content)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command == "GET":
                self.wfile.write(report.content)

        do_HEAD = do_GET

    return Handler


class ReportServerHandle:
    """실제 URL과 스레드·소켓 수명을 소유하는 핸들. 종료 후 재사용 불가."""

    def __init__(self, server: _ReportHTTPServer, report: _ApprovedReport):
        self.url = f"http://127.0.0.1:{server.server_port}/{report.path.name}"
        self._server = server
        self._report = report
        self._lock = threading.Lock()
        self._closed = False
        self._thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.05},
            name=f"agent-opt-report-{server.server_port}", daemon=False,
        )

    def close(self) -> None:
        """중복·동시 호출에도 한 번만 종료하며 모든 소유 자원을 회수한다."""
        with self._lock:
            if self._closed:
                return
            try:
                self._server.stop_requests()
                self._server.shutdown()
                self._thread.join()
            finally:
                self._server.server_close()
                self._report.close()
                self._closed = True


def start_report_server(report_path: Path, *, port: int = 0) -> ReportServerHandle:
    """승인된 report.html 또는 index.html을 127.0.0.1에서 읽기 전용 제공한다."""
    if type(port) is not int or not 0 <= port <= 65535:
        raise ReportServerError("invalid_port", "보고서 포트는 0~65535 정수여야 합니다")
    if (not isinstance(report_path, Path) or report_path.name not in {"report.html", "index.html"}
            or ".." in report_path.parts or "\\" in str(report_path)
            or any(ord(character) < 32 for character in str(report_path))):
        raise ReportServerError("unsafe_report", "승인된 안전한 HTML 보고서를 선택하세요")
    try:
        report = _ApprovedReport(report_path.absolute())
    except OSError as error:
        if error.errno == errno.ENOENT:
            raise ReportServerError(
                "missing_report", "저장된 HTML 보고서가 없습니다. agent-opt report RUN --html로 생성하세요",
                error_number=error.errno,
            ) from None
        code = "report_unreadable" if error.errno in {errno.EACCES, errno.EPERM} else "unsafe_report"
        raise ReportServerError(code, "보고서를 안전하게 읽을 수 없습니다. 파일과 읽기 권한을 확인하세요",
                                error_number=error.errno) from None
    try:
        server = _ReportHTTPServer(("127.0.0.1", port), _handler(report))
    except OSError as error:
        report.close()
        if error.errno == errno.EADDRINUSE:
            raise ReportServerError(
                "port_in_use", f"127.0.0.1:{port} 포트가 사용 중입니다. 기존 서버를 닫거나 --port 0으로 재시도하세요",
                error_number=error.errno,
            ) from None
        raise ReportServerError(
            "bind_failed", f"127.0.0.1:{port}에 연결할 수 없습니다. 로컬 네트워크 권한과 포트를 확인하세요",
            error_number=error.errno,
        ) from None
    try:
        handle = ReportServerHandle(server, report)
        handle._thread.start()
    except BaseException as error:
        server.server_close()
        report.close()
        if not isinstance(error, Exception):
            raise
        raise ReportServerError("start_failed", "보고서 서버 스레드를 시작할 수 없습니다. 다시 시도하세요") from None
    return handle
