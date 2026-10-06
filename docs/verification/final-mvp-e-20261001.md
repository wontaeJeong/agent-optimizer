# 최종 MVP E — loopback HTML 서버 검증·F 인계

확인일: 2026-10-01. **E backend와 전용 테스트 완료. CLI/TUI/browser 연결은 F 담당이며 아직 실행하지 않았다.**

## 범위와 작업 격리

- 작업 디렉터리: `/Users/wt.jeong/workspace/agent-optimizer/.worktrees/final-mvp-e-20261001`.
- 브랜치: `feat/final-mvp-e-20261001`, 시작 HEAD 및 `origin/main`: `edbd2b8c7b05bdd63c352d02a7adf7652168d197`. 총괄이 생성한 기존 워크트리를 재사용했다.
- 지시 `prompts/E_REPORT_LOCAL_SERVER.md`, 작업 `AGENTS.md`, P0 보고서 §4 E→F/§7을 읽고 대조했다. `workspace.safe_path`의 경계 규칙과 `cli._history_run`의 `dir_fd`·`O_NOFOLLOW`·`O_NONBLOCK`·`fstat` 방식을 조사했다. 후보 안전성 helper는 수정하지 않았다.
- 변경 파일은 신규 `src/agent_optimizer/report_server.py`, `tests/test_report_server.py`, 이 보고서뿐이다. CLI/TUI/renderer/공유 테스트/의존성은 수정하지 않았다.
- 기본 디렉터리는 시작 시 `main...origin/main`이며 사용자 `.gitignore` 변경과 지시 ZIP을 보존했다. 다른 워크트리 변경·정리, 하위 에이전트, install/sync, 공유 `.venv` 변경, push/PR은 수행하지 않았다.
- 최종 Python 실행은 공유 `/Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python`, `PYTHONPATH=src`를 사용했다. Home/cache/output/TMPDIR는 아래 E 전용 임시 경계로 지정했다. 개인 Home·비밀·모델 API·외부 데이터는 검증 입력으로 사용하지 않았다.
- 초기 플러그인 baseline 1회는 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_plugin_contracts.py -v`로 실행되어 기본 OS 임시 경계에 fixture가 생성됐다(18개, 2.361초 OK). 이후 E 전용 TMPDIR/Home/cache를 지정해 아래 명령으로 다시 검증했다. 임시 fixture는 테스트의 자동 cleanup 대상이며 개인 Home에 결과를 생성하지 않았다.

## 공개 인터페이스와 제공 규칙

```python
from pathlib import Path
from agent_optimizer.report_server import ReportServerError, start_report_server

handle = start_report_server(Path("RUN/report.html"), port=0)
try:
    url = handle.url
finally:
    handle.close()
```

- 정확한 계약: `start_report_server(report_path: Path, *, port: int = 0) -> ReportServerHandle`; `url: str`, `close() -> None`. import는 파일 읽기·bind·browser 실행을 하지 않는다. port는 bool을 제외한 정수 0~65535이며 host 인수/public bind 옵션은 없다.
- 고정 주소는 `127.0.0.1`; port=0은 실제 OS 선택 포트다. URL은 `http://127.0.0.1:<실제포트>/report.html` 또는 `/index.html`. 명시 포트 실패를 다른 포트로 대체하지 않는다.
- 승인 파일명은 기존 writer 산출물 `report.html`과 `index.html`이다. **호출당 선택한 HTML 한 개만** 허용한다. `/`는 같은 파일을 제공하며 listing/child route/asset 탐색은 없다. JSON/MD/summary/manifest/events/log/source/candidate/private/.env는 공개하지 않는다. 파일 내용이 보고서인지 추측하거나 raw JSON을 자동 승인하지 않는다.
- startup에서 일반 파일·단일 hardlink·no-follow를 검증해 HTML bytes를 고정한다. 디렉터리와 파일 descriptor를 유지해 inode 재사용을 막고 GET/HEAD마다 원래 경로를 다시 no-follow로 열어 디렉터리·파일의 device/inode를 대조한다. symlink/root/file 교체·특수파일은 404다. 같은 inode의 in-place 변경에도 원래 승인 bytes만 제공한다. **보고서 재생성 후에는 이전 handle을 닫고 새로 시작해야 갱신된다.**
- 절대 파일 경로는 사용자 입력으로 허용하고 상대 파일 경로는 시작 시 CWD에 고정한다. `..`, backslash, 제어문자와 임의 파일명은 거부한다. 모든 디렉터리 구성요소를 `O_DIRECTORY | O_NOFOLLOW`로 연다. macOS 표준 `/var`, `/tmp` host 별칭만 먼저 canonicalize하며 사용자 symlink ancestor는 따라가지 않는다.
- HTTP request target은 raw 문자열과 exact route를 비교한다. percent encoding 자체를 허용하지 않으므로 단일/이중 인코딩·encoded separator·traversal 우회가 없다. query(빈 `?` 포함), fragment가 실제 요청에 포함된 경우(빈 `#` 포함), backslash, absolute-form URL, `//`, `./`, trailing slash도 404다. 정상 HTML의 `#anchor`는 브라우저가 서버에 전송하지 않으므로 사용 가능하다.
- Host는 실제 URL의 `127.0.0.1:<포트>` 하나만 허용한다. 임의 도메인/중복 Host를 허용하지 않는다. 다른 hostname으로 URL을 바꾸지 말고 `handle.url`을 사용한다.
- GET/HEAD만 제공하고 나머지 메서드는 405 및 `Allow: GET, HEAD`다. 성공 응답은 `text/html; charset=utf-8`, 정확한 `Content-Length`, `nosniff`, `Cache-Control: no-store`를 사용한다. CORS wildcard는 없다.
- 오류 응답은 한국어 일반 문구이며 요청 경로/파일 내용/원본 private 경로/하위 예외를 포함하지 않는다. HTTP access/error log를 출력하지 않는다. 외부 공개 서버 또는 OS 보안 sandbox가 아니다.

## 오류 매핑 — F/G 소비

`ReportServerError`는 기존 `ConfigurationError`의 하위 타입이다. `code: str`, `errno: int | None`을 제공하고 `str(error)`는 한국어 안전 진단이다. OS 원문 예외는 사용자 응답에 복제하지 않는다.

| code | errno/조건 | F/G 복구 안내 |
|---|---|---|
| `invalid_port` | 타입/범위 오류, errno 없음 | 0 또는 1~65535 정수 사용 |
| `unsafe_report` | 미승인 경로/파일명, symlink, hardlink, special, 디렉터리, `ELOOP`/`ENOTDIR`/`EINVAL` 등 | A의 안전한 보고서 선택 결과 재확인; 일반 HTML 파일 선택 |
| `missing_report` | `ENOENT` | `agent-opt report RUN --html`로 명시 생성한 뒤 재시도; 서버는 생성하지 않음 |
| `report_unreadable` | 읽기 `EACCES`/`EPERM` | 보고서·디렉터리 읽기 권한 확인 |
| `port_in_use` | bind `EADDRINUSE` | `127.0.0.1:<요청포트>` 안내; 기존 서버 종료 또는 `--port 0` 재시도 |
| `bind_failed` | 나머지 bind errno | loopback 네트워크 권한·주소·포트 확인 |
| `start_failed` | thread 시작 실패, errno 없음 | 소켓·파일 자원 회수 후 명시 재시도 |

HTTP에서 파일이 삭제/교체되거나 승인되지 않은 route를 요청하면 404이며 파일 경로를 노출하지 않는다. 정상 GET/HEAD는 200, 미지원 메서드는 405다. 잘못된 HTTP 문법/헤더의 표준 parser 오류도 본문을 일반 문구로 바꾼다.

## 생명주기와 F/H 연결점

- 단일 non-daemon thread가 표준 `HTTPServer.serve_forever`를 실행한다. child process/daemon/PID 파일은 없다. TUI에서 서버 시작 후 응답을 기다리는 foreground loop를 실행할 필요가 없다.
- `close()`는 lock으로 중복·동시 호출을 직렬화한다. 활성 HTTP 연결을 먼저 shutdown하여 계속 조금씩 헤더를 보내는 클라이언트도 종료를 막지 못한다. 그 뒤 서버 shutdown/thread join/socket close/승인 파일 descriptor close를 수행한다. 종료 후 URL은 값으로 남지만 서버는 닫혀 있다.
- F: 열람 직전 A의 `verified_report(row)`를 호출하고 E에 반환된 Path를 전달한다. CLI는 Ctrl-C/예외의 `finally`, TUI는 종료·보고서 교체 때 `close()`를 반드시 호출한다. 동일 run을 다시 열 때 기존 살아 있는 handle을 F가 재사용하거나 닫고 새로 시작한다. E는 전역 cache를 만들지 않는다.
- F: `--json --serve` 등 충돌 검증은 서버/browser/mkdir 부작용 전에 한다. `--serve`는 저장 보고서 읽기만, `--html --serve`는 명시 재생성 후 새 handle 시작으로 연결한다.
- P0에서 browser는 F 소유로 확정했으므로 E에 browser helper는 추가하지 않았다. F는 bind 성공 후 한 번 열고 실패/예외/headless에서 `handle.url`을 그대로 안내한다. browser 성공·실패 mock과 CLI/TUI 통합 테스트는 F가 추가한다. E는 브라우저를 열었다고 주장하지 않는다.
- 세션 `index.html`도 HTML 한 파일만 제공한다. child report/summary 링크는 승인하지 않아 404다. 손상·미검증 child 링크도 공개하지 않는다. F는 우선 검증된 child report 선택으로 안내하고, 비공개 자료 링크의 이용 불가 설명은 F/D가 renderer/UI에서 처리한다. 서버가 manifest를 파싱해 Home이나 session tree를 공개하지 않는다.
- H: loopback 전용임을 안내하고 SSH에서는 원격 서버가 실행되는 동안 포트포워딩 후 `127.0.0.1:<포트>` URL을 사용하도록 문서화한다. SSH 환경에서 로컬 브라우저가 열렸다고 단정하지 않는다.

## 정확한 최종 검증 명령·결과

아래 명령의 CWD는 E 워크트리다. 각 명령 종료 코드 0. 로컬 실제 HTTP는 loopback fixture이며 모델 호출이 아니다.

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-e/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-e/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-e/cache TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-e/output /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p 'test*report*.py' -v
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-e/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-e/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-e/cache TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-e/output /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_plugin_contracts.py -v
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-e/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-e/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m ruff check . --no-cache
```

- 보고서 관련 **96개/3.415초 OK**: 기존 HTML/normalized model 79개와 E 신규 17개 모두 통과.
- 플러그인 계약 **18개/2.485초 OK**. Ruff **`All checks passed!`**.
- E 테스트: 실제 GET/HEAD/root/404/405·헤더·private 파일 차단·raw URL/단일·이중 인코딩·Host·symlink ancestor/open 직전 swap·root/file 교체·FIFO/디렉터리/hardlink·in-place 변경의 고정 bytes·포트 충돌/타입·errno 진단·import 무부작용·반복 열람·동시 idempotent close·thread 제거·socket 재접속 실패·동일 포트 restart·미완성/지속 전송 클라이언트 종료·thread 시작 실패 cleanup·단일 세션 HTML과 미승인 child 링크 차단을 검증했다.
- TDD 증거: backend 부재를 검증하는 전용 명령은 13개 assertion failure로 실패한 뒤 최초 구현에서 13개 통과했다. 추가 17개 실행에서는 느린 클라이언트 종료 1개가 실패했고 활성 소켓 shutdown으로 수정했다. 이후 cleanup의 이미 닫힌 client `shutdown` 오류를 테스트에서 안전 처리하고 최종 96개를 통과했다. 이들은 최종 통과 결과와 분리한 개발 중 실패다.
- 직접 코드 검토: P0 인터페이스/HTML-only/무모델/소유권/경로 격리/파일 descriptor와 socket/thread 수명/오류 누출을 대조했다. 하위 에이전트 리뷰는 금지 지시에 따라 수행하지 않았다.
- Ubuntu x86_64 실행, 실제 browser/SSH/CLI/TUI serve flow, native Agent·실모델 평가는 **not_run**이다. E에서 Mac의 실제 loopback HTTP와 fixture/mock 기반 코어 회귀를 검증했다.

### 전체 unit — 기존 환경 의존과 지정 TMPDIR 충돌

추가 최종 명령(CWD 동일):

```bash
env -u AGENT_OPT_TEST_VERILOG_EVAL_ROOT PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-e/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-e/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-e/cache TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-e/output UV_PROJECT_ENVIRONMENT=/Users/wt.jeong/workspace/agent-optimizer/.venv UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -v
```

- **`Ran 970 tests in 124.879s`, `FAILED (failures=1, errors=15, skipped=79)`**, 종료 코드 1. 전체 녹색으로 보고하지 않는다. E 신규 17개는 전체 실행에서도 통과했다.
- 오류 15건은 P0와 동일하게 `test_dev_onboarding.py:744`, `test_locale.py`의 워크트리-local `.venv/bin/python`/`agent-opt` 하드코딩에 의한 `FileNotFoundError`다. 공유 Python/`UV_PROJECT_ENVIRONMENT`로 시작해도 기존 subprocess argv가 바뀌지 않는다.
- 추가 assertion failure는 `DriverLockTests.test_selected_cvdp_setup_preserves_full_ace_lock_and_never_prepares_agent_image`의 `test_dev_environment.py:686`이다. 기존 `any("opencode" in str(cmd).lower() for cmd in commands)`가 실행 도구 이름뿐 아니라 임시경로 인수 전체도 검사한다. 이번 필수 TMPDIR 경계 `/.../T/opencode/final-mvp-e/output`가 fixture argv에 들어가 false positive를 발생시킨다. 해당 테스트의 외부 setup/subprocess/network는 mock이고 실제 OpenCode 설치·실행을 뜻하지 않는다. E에서는 공유 테스트를 수정하거나 지정 TMPDIR를 우회하지 않았다.
- G 인계: `.venv` 하드코딩을 공유 실행 환경 계약에 맞추고, 위 검사는 경로 전체 substring 대신 실제 executable 또는 관련 인수를 구분하도록 보완한다. I에서 최종 전체 회귀를 다시 확인한다.
- 건너뜀 79개에는 선택형 도구/network/직접 터미널 대체·실 Verilog-Eval이 포함되며 실환경 성공 증거가 아니다. 최종 원본 로그: `/Users/wt.jeong/.local/share/opencode/tool-output/tool_0f32ab4710018wn8WvabYmLZ2H`.

## 완료 인계

E 구현은 F가 새 모듈과 전용 테스트를 통합할 수 있는 상태다. 미결 연결은 F의 CLI/TUI/browser lifecycle·세션 child 선택, F/D의 비공개 링크 설명, G의 새 오류 진단, H의 loopback/SSH 안내다. 서버 bind에 실패하면 한국어 `ReportServerError`와 정확한 code/errno로 처리하고 기존 기능이나 다른 포트로 자동 대체하지 않는다.
