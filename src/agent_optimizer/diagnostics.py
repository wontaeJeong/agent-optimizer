"""Small, secret-safe summaries for subprocess and setup failures."""
from __future__ import annotations

import os
import re
import shlex
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class CommandOutcome:
    """Captured subprocess state; never serialize this object into a public report."""

    command: str
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    error_kind: str | None = None
    elapsed_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and self.error_kind is None and not self.timed_out


_SECRET_ENV_MARKERS = (
    "KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "AUTH", "CREDENTIAL", "MODEL",
)
_CA_ENV_NAMES = {
    "AGENT_OPT_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    "GIT_SSL_CAINFO", "PIP_CERT", "NODE_EXTRA_CA_CERTS", "NPM_CONFIG_CAFILE",
}
_SECRET_KEY = (
    r"(?:[a-z0-9]+[_-])*(?:api[_-]?key|access[_-]?(?:key|token)|refresh[_-]?token|"
    r"client[_-]?secret|private[_-]?key|signing[_-]?key|authorization|secret|password|passwd|pass|token|auth|credential)"
    r"(?:[_-][a-z0-9]+)*"
)
_URL_USERINFO = re.compile(r"(?i)\b((?:https?|socks[45]h?)://)[^/\s@]*@")
_AUTHORIZATION_VALUE = re.compile(
    r"(?i)\bauthorization(?:[ \t]*[:=][ \t]*|[ \t]+)(?:\"[^\"]*\"|'[^']*'|[^,;]+)"
)
_JSON_SECRET_ASSIGNMENT = re.compile(
    r"(?i)[\"']" + _SECRET_KEY
    + r"[\"'][ \t]*:[ \t]*(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^,}\s]+)"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(" + _SECRET_KEY + r")(?:[ \t]*[:=][ \t]*|[ \t]+(?:is[ \t]+)?)"
    r"(?:bearer[ \t]+)?"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_BEARER_CREDENTIAL = re.compile(r"(?i)\bbearer[ \t]+(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)")
_SECRET_MARKER = re.compile(r"(?i)\b" + _SECRET_KEY + r"\b")
_TOKEN_SHAPE = re.compile(r"(?i)\b(?:sk|gh[pousr])-[A-Za-z0-9_-]{8,}\b")
_MEANINGFUL = re.compile(
    r"(?i)(error|fatal|failed|failure|denied|permission|x509|certificate|tls|dns|resolve|"
    r"connect|socket|cache|not found|no such|invalid|lock|platform|timeout|timed out|"
    r"refused|unreachable|no space)"
)
_DOCKER_SOCKET = re.compile(r"(?i)(docker.{0,40}(?:socket|daemon)|(?:socket|daemon).{0,40}docker)")
_TLS = re.compile(r"(?i)(x509|certificate|tls|ssl|unknown authority)")
_DNS = re.compile(r"(?i)(name resolution|resolve host|dns|temporary failure|connection refused|network is unreachable)")
_CACHE = re.compile(r"(?i)(offline|cache.{0,30}(?:missing|miss|not found)|not found.{0,30}cache)")
_LOCK = re.compile(r"(?i)(lock.{0,30}(?:differ|mismatch|invalid)|platform.{0,30}mismatch)")


def _environment_values(environment: Mapping[str, str] | None) -> list[str]:
    values = dict(os.environ)
    if environment is not None:
        values.update({key: value for key, value in environment.items()
                       if isinstance(key, str) and isinstance(value, str)})
    return sorted((value for key, value in values.items()
                   if value and (key.upper() in _CA_ENV_NAMES or
                                 any(marker in key.upper() for marker in _SECRET_ENV_MARKERS))),
                  key=len, reverse=True)


def redact_text(text: str, environment: Mapping[str, str] | None = None) -> str:
    """Remove secrets while preserving line structure for structured diagnostics."""
    safe = str(text)
    for value in _environment_values(environment):
        safe = safe.replace(value, "[redacted]")
    safe = _URL_USERINFO.sub(r"\1[redacted]@", safe)
    safe = _JSON_SECRET_ASSIGNMENT.sub("\"[redacted]\":\"[redacted]\"", safe)
    safe = _AUTHORIZATION_VALUE.sub("[redacted]", safe)
    safe = _BEARER_CREDENTIAL.sub("[redacted]", safe)
    safe = _SECRET_ASSIGNMENT.sub("[redacted]", safe)
    safe = _SECRET_MARKER.sub("[redacted]", safe)
    safe = _TOKEN_SHAPE.sub("[redacted]", safe)
    safe = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", safe)
    return safe.replace("\r", "")


def redact_guidance(text: str, environment: Mapping[str, str] | None = None) -> str:
    """Public guidance is not raw process output: model IDs and CA paths are public."""
    values = dict(os.environ)
    if environment is not None:
        values.update(environment)
    credentials = sorted({value for key, value in values.items()
                          if isinstance(key, str) and isinstance(value, str) and value
                          and any(marker in key.upper() for marker in _SECRET_ENV_MARKERS if marker != 'MODEL')},
                         key=len, reverse=True)
    safe = str(text)
    for value in credentials:
        if len(value) < 4:
            safe = re.sub(r'(?<![\w])' + re.escape(value) + r'(?![\w])', '[redacted]', safe)
        else:
            safe = safe.replace(value, '[redacted]')
    safe = _URL_USERINFO.sub(r'\1[redacted]@', safe)
    safe = _JSON_SECRET_ASSIGNMENT.sub('"[redacted]":"[redacted]"', safe)
    safe = _AUTHORIZATION_VALUE.sub('[redacted]', safe)
    safe = _BEARER_CREDENTIAL.sub('[redacted]', safe)
    # Keep required environment-variable labels; redact explicit assignments only.
    safe = re.sub(r'(?i)\b(' + _SECRET_KEY + r')[ \t]*[:=][ \t]*(?:"[^"]*"|\x27[^\x27]*\x27|[^\s,;]+)',
                  '[redacted]', safe)
    safe = _TOKEN_SHAPE.sub('[redacted]', safe)
    return re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', ' ', safe).replace('\r', '')


def safe_retry(command: str, environment: Mapping[str, str] | None = None) -> str:
    """Never offer a command whose user argument had to be replaced by redaction."""
    unavailable = '자격증명 또는 잘못된 인수 때문에 재실행 명령을 표시할 수 없습니다. 경로/옵션에서 자격증명을 분리한 뒤 재시도하세요'
    try:
        argv = shlex.split(command)
    except (ValueError, TypeError):
        return unavailable
    if not argv or any(ord(char) < 32 or ord(char) == 127 for char in command):
        return unavailable
    public_commands = {'doctor', 'report', 'prepare', 'plan', 'run', 'run-session', 'datasets', 'catalog', 'init'}
    public_flags = {'--model', '--plan', '--serve', '--no-open', '--html', '--port',
                    '--offline', '--core', '--output', '--dataset', '--json', '--csv'}
    for index, argument in enumerate(argv):
        # Values after flags remain user data even if they match a command/flag label.
        is_value = index > 0 and argv[index - 1] in {'--plan', '--port', '--output', '--dataset'}
        structural = (index == 0 and argument == 'agent-opt' or
                      index == 1 and argv[0] == 'agent-opt' and argument in public_commands or
                      index == 2 and argv[:2] in [['agent-opt', 'datasets'], ['agent-opt', 'catalog']]
                      and argument in {'list', 'show', 'prepare', 'doctor'} or
                      argument in public_flags)
        if not is_value and structural:
            continue
        if redact_guidance(argument, environment) != argument or '[redacted]' in argument:
            return unavailable
    return shlex.join(argv)


def sanitize_text(text: str, environment: Mapping[str, str] | None = None) -> str:
    """Remove secrets and collapse one diagnostic fragment to a single safe line."""
    return " ".join(redact_text(text, environment).replace("\n", " ").split())


def _meaningful_lines(text: str, environment: Mapping[str, str] | None, *, limit: int) -> list[str]:
    rows = []
    for line in text.splitlines():
        if not _MEANINGFUL.search(line):
            continue
        safe = sanitize_text(line, environment).strip()
        if safe and safe != "[redacted]":
            rows.append(safe[:240])
    return rows[-limit:]


def _category(outcome: CommandOutcome, output: str) -> str:
    lowered = output.lower()
    if outcome.error_kind in {"missing", "not_found", "command_not_found"}:
        return "missing"
    if outcome.timed_out or outcome.error_kind == "timeout":
        return "timeout"
    if _DOCKER_SOCKET.search(outcome.command + " " + output):
        return "docker_socket"
    if "permission" in lowered or "operation not permitted" in lowered or outcome.error_kind == "permission":
        return "permission"
    if _TLS.search(output):
        return "tls"
    if _DNS.search(output):
        return "dns"
    if _CACHE.search(output):
        return "cache"
    if _LOCK.search(output):
        return "lock"
    if "no such file" in lowered or "file not found" in lowered:
        return "missing_file"
    if outcome.returncode is not None and outcome.returncode != 0:
        return "nonzero"
    if outcome.error_kind:
        return "unknown"
    return "unknown"


def summarize_failure(outcome: CommandOutcome, *, environment: Mapping[str, str] | None = None) -> str:
    """Return a short, classified failure; raw captured output is never returned wholesale."""
    command = sanitize_text(outcome.command, environment) or "command"
    output = "\n".join((outcome.stderr, outcome.stdout))
    lines = _meaningful_lines(output, environment, limit=3)
    category = _category(outcome, output)

    if category == "missing":
        return f"{command} executable not found"
    if category == "timeout":
        detail = f": {lines[-1]}" if lines else ""
        return f"{command} timed out{detail}"
    if outcome.returncode is not None and outcome.returncode != 0:
        prefix = f"{command} exited {outcome.returncode}"
    elif category == "permission":
        prefix = f"{command} could not run: permission denied"
    elif outcome.error_kind:
        prefix = f"{command} could not run ({sanitize_text(outcome.error_kind, environment)})"
    else:
        prefix = f"{command} failed"

    if category == "docker_socket":
        label = "Docker daemon/socket failure"
    elif category == "permission":
        label = "permission denied"
    elif category == "tls":
        label = "TLS/certificate failure"
    elif category == "dns":
        label = "DNS/connection failure"
    elif category == "cache":
        label = "offline cache miss"
    elif category == "lock":
        label = "lock/platform mismatch"
    elif category == "missing_file":
        label = "required file is missing"
    elif category == "nonzero":
        label = "command returned a non-zero exit code"
    else:
        label = "unknown failure"

    detail = lines[-1] if lines else label
    if category in {"docker_socket", "tls", "dns", "cache", "lock"}:
        detail = f"{label}: {detail}" if lines else label
    elif not lines:
        detail = label
    return f"{prefix}: {detail}"


def summarize_exception(exc: BaseException, *, environment: Mapping[str, str] | None = None) -> str:
    """Keep a useful exception reason while removing environment-owned secrets."""
    if isinstance(exc, FileNotFoundError):
        return "required file or executable not found"
    if isinstance(exc, PermissionError):
        detail = sanitize_text(str(exc), environment)
        return detail[:240] if detail else "permission denied"
    if isinstance(exc, TimeoutError) or type(exc).__name__ == "TimeoutExpired":
        return "operation timed out"
    detail = sanitize_text(str(exc), environment)
    return detail[:240] if detail else f"{type(exc).__name__} failure"


def summarize_log(path: Path, *, environment: Mapping[str, str] | None = None,
                  limit: int = 3) -> list[str]:
    """Read only a bounded suffix and return at most ``limit`` safe error lines."""
    if limit < 1:
        return []
    try:
        with Path(path).open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            start = max(0, size - 64 * 1024)
            stream.seek(start)
            data = stream.read(64 * 1024).decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = data.splitlines()
    if start:
        lines = lines[1:]
    selected = deque(maxlen=limit)
    for line in lines:
        if _MEANINGFUL.search(line):
            safe = sanitize_text(line, environment)
            if safe and safe != "[redacted]":
                selected.append(safe[:240])
    return list(selected)
