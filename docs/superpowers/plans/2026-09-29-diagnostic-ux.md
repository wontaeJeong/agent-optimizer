# setup·doctor 진단 UX 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**목표:** setup/doctor/dataset/ACE 실패의 원인·조치·로그·재시도 정보를 비밀정보 노출 없이 터미널에 보여준다.

**구조:** 내부 `CommandOutcome`과 공통 sanitizer/classifier로 subprocess 실패 정보를 보존한다. doctor JSON의 기존 5개 check 필드에 Cause/Blocked by/Retry를 문자열로 전달하고, 사람 출력은 이를 별도 줄로 렌더링한다. setup Python과 bootstrap은 로그를 유지하되 안전한 요약만 표시하며 CLI/TUI는 원인을 끝까지 보여준다.

**기술:** Python 3.11+ 표준 라이브러리, `unittest`, 기존 Rich/Textual 출력 계층, POSIX `sh`.

**설계 문서:** `docs/superpowers/specs/2026-09-29-diagnostic-ux-design.md`

## 전역 제약

- doctor check JSON 필드 `id`, `area`, `status`, `message`, `remedy` 및 report 구조를 유지한다.
- stdout/stderr 원문·proxy URL userinfo·민감한 환경값·CA 경로를 사용자 출력이나 doctor JSON에 노출하지 않는다.
- doctor는 read-only, bytecode 미생성, 독립 오류 집계, blocked 의존성 유지, 일반 경로 모델 API 미호출, Docker pull/build 금지, 기존 container cleanup 안전성을 유지한다.
- setup log는 보존하되 최대 1~3개의 정제된 의미 있는 오류 줄만 터미널에 표시한다.
- setup human output과 `doctor --json` machine output을 분리하고 JSON stdout은 단일 document로 유지한다.
- 기존 모듈 흐름을 유지하며 logging framework, telemetry, tracing backend, 새 daemon/service 또는 광범위한 exception hierarchy를 추가하지 않는다.
- 모든 사람용 문구는 한국어로 작성한다. 코드 식별자·경로·명령·고유 명칭은 원문을 쓴다.

---

## 파일 변경 지도

| 파일 | 책임 |
|---|---|
| `src/agent_optimizer/diagnostics.py` | 내부 `CommandOutcome`, 환경 기반 secret redaction, 안전한 원인 분류 및 제한된 로그 요약 |
| `src/agent_optimizer/readiness.py` | `Runner.run/probe`, blocked/cause 전달, plan·dataset broad catch의 safe cause 유지 |
| `scripts/dev_doctor.py` | 코어·ACE 검사에서 실제 command 원인 보존, human 출력 Cause/Fix/Retry, 기존 JSON 구조 유지 |
| `examples/ace-rtl/environment/diagnostics.py` | Docker/driver/image/tool readiness 실패를 실제 원인과 함께 수집 |
| `examples/ace-rtl/environment/setup.py` | subprocess·Git·dataset·driver·Docker·image·simulator/OpenCode 준비 실패와 setup log 요약 |
| `examples/benchmarks/cvdp.py`, `examples/benchmarks/verilog_eval.py` | 선택형 dataset cache/runtime 실패의 원인 보존 |
| `src/agent_optimizer/datasets.py` | Verilog-Eval 등 고정 Git dataset clone/checkout 실패 원인 보존 |
| `scripts/bootstrap.sh` | Python 준비 전 uv/download/sync/daemon 오류 allow-list 진단 |
| `scripts/dev.py` | setup human 실패/완료 결과와 final doctor 결과 전달 |
| `src/agent_optimizer/locale.py`, `src/agent_optimizer/cli.py`, `src/agent_optimizer/tui.py`, `src/agent_optimizer/preset_tui.py`, `scripts/dev_doctor.py` | check 문자열을 Cause/Blocked by/Fix/Retry로 렌더링하고 TUI/ACE preset 경로에서 모든 실패 check 유지 |
| `docs/development.md` | stdout/stderr 원문 표시 및 setup 실패 동작 설명 갱신 |
| `tests/test_diagnostics.py` | sanitizer·분류·log excerpt 단위 계약 |
| `tests/test_dev_doctor.py`, `tests/test_demo_environment.py` | runner outcome·doctor aggregation·blocked·read-only·JSON 보안 |
| `tests/test_dev_environment.py`, `tests/test_datasets.py` | ACE/dataset/setup subprocess 실패와 안전한 log 원인 요약 |
| `tests/test_dev_onboarding.py` | bootstrap uv/sync failure 및 human setup output |
| `tests/test_cli_experience.py`, `tests/test_textual_tui.py`, `tests/test_locale.py`, `tests/test_claude_code.py`, `tests/test_preset_tui.py` | CLI/TUI 원인·조치/재시도 표시 및 기존 stdout 계약 |

## Task 1: 공통 진단 결과와 정제 helper

**파일:** `src/agent_optimizer/diagnostics.py` 생성, `tests/test_diagnostics.py` 생성.

**제공 인터페이스:** `CommandOutcome`은 `command: str`, `returncode: int | None`, `stdout: str`, `stderr: str`, `timed_out: bool`, `error_kind: str | None`, `elapsed_seconds: float` 필드를 가진 frozen dataclass다. `succeeded`는 return code가 0이며 timeout/exception이 없을 때만 참이다. 공통 함수는 `sanitize_text(text: str, environment: Mapping[str, str] | None = None) -> str`, `summarize_failure(outcome: CommandOutcome, *, environment=None) -> str`, `summarize_log(path: Path, *, environment=None, limit: int = 3) -> list[str]`다.

- [x] **Step 1: 실패 테스트 작성**

  `tests/test_diagnostics.py`에 다음 테스트를 추가한다.

```python
class DiagnosticTests(unittest.TestCase):
    def test_sanitize_removes_secret_values_proxy_userinfo_and_ca_path(self):
        environment = {
            "OPENROUTER_API_KEY": "SECRET_API_123",
            "CUSTOM_TOKEN": "TOKEN_VALUE_456",
            "HTTPS_PROXY": "http://proxy-user:proxy-pass@proxy.example",
            "AGENT_OPT_CA_BUNDLE": "/private/certs/SECRET-ca.pem",
        }
        text = sanitize_text(
            "key=SECRET_API_123 token=TOKEN_VALUE_456 "
            "proxy=http://proxy-user:proxy-pass@proxy.example "
            "ca=/private/certs/SECRET-ca.pem",
            environment,
        )
        for secret in ("SECRET_API_123", "TOKEN_VALUE_456", "proxy-user", "proxy-pass",
                       "/private/certs/SECRET-ca.pem"):
            self.assertNotIn(secret, text)

    def test_failure_classifier_names_missing_timeout_permission_docker_tls_dns_and_cache(self):
        cases = [
            (CommandOutcome("uv", None, error_kind="missing"), "not found"),
            (CommandOutcome("uv sync", None, timed_out=True, error_kind="timeout"), "timed out"),
            (CommandOutcome("docker info", 1, stderr="permission denied"), "permission"),
            (CommandOutcome("docker info", 1, stderr="cannot connect to docker socket"), "daemon"),
            (CommandOutcome("docker build", 1, stderr="x509 certificate signed by unknown authority"), "TLS"),
            (CommandOutcome("git clone", 1, stderr="temporary failure in name resolution"), "DNS"),
            (CommandOutcome("uv sync", 1, stderr="package not found in cache"), "cache"),
        ]
        for outcome, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected.lower(), summarize_failure(outcome).lower())

    def test_log_summary_only_returns_bounded_redacted_error_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "build.log"
            log.write_text("download started\n" * 50 + "ERROR x509 proxy=http://u:SECRET@proxy\n")
            rows = summarize_log(log, environment={"TOKEN": "SECRET"}, limit=3)
        self.assertLessEqual(len(rows), 3)
        self.assertTrue(any("x509" in row.lower() for row in rows))
        self.assertNotIn("SECRET", "\n".join(rows))
```

- [x] **Step 2: 테스트를 실행해 실패 확인**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_diagnostics.py -v`
  Expected: FAIL because the helper module and outcome type do not exist.

- [x] **Step 3: 작은 helper 구현**

  `CommandOutcome`은 subprocess 결과만 담고 JSON serializer를 제공하지 않는다. `sanitize_text()`는 민감 key 이름에 속한 환경값을 긴 값부터 치환하고, proxy URL userinfo·Bearer/API key/token 문법·CA 경로를 처리한다. `summarize_failure()`는 timeout/missing/permission/Docker socket/TLS/DNS/cache/non-zero/unknown 순으로 고정 분류 문구를 만들고, 원문 줄은 모두 정제한 뒤 최대 3줄·각 240자로 제한한다. `summarize_log()`는 파일 끝 최대 64 KiB만 읽고 error/fatal/failed/certificate/permission/connect/cache 등 의미 있는 행만 고른다.

```python
@dataclass(frozen=True)
class CommandOutcome:
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
```

- [x] **Step 4: helper 테스트 재실행**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_diagnostics.py -v`
  Expected: PASS; 입력의 secret, proxy userinfo, CA 경로가 결과 문자열 어디에도 없음.

- [x] **Step 5: Task 1 commit**

  ```bash
  git add src/agent_optimizer/diagnostics.py tests/test_diagnostics.py
  git commit -m "진단 실패 원인 요약과 비밀정보 제거 추가"
  ```

## Task 2: readiness Runner와 doctor 원인 전달

**파일:** `src/agent_optimizer/readiness.py`, `scripts/dev_doctor.py`, `examples/ace-rtl/environment/diagnostics.py`, `tests/test_dev_doctor.py`, `tests/test_demo_environment.py`.

**인터페이스:** Task 1의 `CommandOutcome` 및 요약 함수를 사용한다. `Runner.run(argv: Sequence[str], *, cwd: Path | None = None, timeout: float = 15, label: str | None = None) -> CommandOutcome`로 바꾸고, `Runner.probe(name: str, argv: Sequence[str], message: str, remedy: str, *, requires: Sequence[str] = (), expected: str | None = None, timeout: float = 15, retry: str | None = None) -> CommandOutcome | None`는 outcome 기반으로 결과를 기록한다. 선행 check에 막힌 probe는 `None`을 반환하고 check에는 blocked row를 기록한다. check public key는 5개 그대로다.

- [x] **Step 1: 실패 테스트 작성**

  `DoctorTests`에 다음 상황을 추가한다: missing executable, non-zero exit with safe stderr, `TimeoutExpired(output=secret)`, `PermissionError`, Docker socket permission, TLS certificate error, prerequisite blocked, 한 Docker 검사 timeout 이후 source/data/live 검사가 계속 수집됨. 각 실패 검사에서 `Cause`/`Blocked by`/`Fix`/`Retry` 정보를 확인한다.

```python
def test_runner_preserves_safe_docker_failure_and_blocks_image_check(self):
    self.prepared()
    def execute(argv, **kwargs):
        if argv[:2] == ["docker", "version"]:
            return subprocess.CompletedProcess(argv, 1, "", "permission denied on docker.sock SECRET")
        return self.execute(argv, **kwargs)
    with patch.object(self.doctor.readiness.subprocess, "run", side_effect=execute):
        report = self.doctor.collect_report(self.root)
    checks = self.checks(report)
    self.assertEqual(checks["docker.daemon"]["status"], "error")
    self.assertIn("permission", checks["docker.daemon"]["message"].lower())
    self.assertIn("docker.daemon", checks["image.agent"]["message"])
    self.assertEqual(checks["source.ACE-RTL"]["status"], "ok")
    self.assertNotIn("SECRET", json.dumps(report))
```

- [x] **Step 2: 대상 테스트만 실행해 실패 확인**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_dev_doctor.py -v`
  Expected: 새 진단 정보 assertion에서 FAIL; 기존 read-only/cleanup 테스트는 계속 실행됨.

- [x] **Step 3: Runner와 check 기록 변경**

  `Runner.run()`은 `subprocess.run` success/nonzero와 `FileNotFoundError`, `PermissionError`, timeout, 기타 `OSError`를 `CommandOutcome`으로 변환한다. raw 결과는 outcome 내부에만 두고, `probe()`가 `summarize_failure()`로 안전한 cause를 만든다. `Runner.add()`는 failed prerequisites를 `blocked`와 `Blocked by:`로 표시하고 독립 check 실행은 중단하지 않는다. `check()`와 dataset provider row validation은 기존 키/값 타입을 유지한다.

```python
started = time.monotonic()
try:
    result = subprocess.run(argv, cwd=cwd or self.root, env=environment,
                            capture_output=True, text=True, timeout=timeout, shell=False)
    outcome = CommandOutcome(label, result.returncode, result.stdout, result.stderr,
                             elapsed_seconds=time.monotonic() - started)
except FileNotFoundError:
    outcome = CommandOutcome(label, None, error_kind="missing",
                             elapsed_seconds=time.monotonic() - started)
except PermissionError:
    outcome = CommandOutcome(label, None, error_kind="permission",
                             elapsed_seconds=time.monotonic() - started)
except subprocess.TimeoutExpired as exc:
    stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
    stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else exc.stderr or ""
    outcome = CommandOutcome(label, None, stdout, stderr, timed_out=True, error_kind="timeout",
                             elapsed_seconds=time.monotonic() - started)
```

- [x] **Step 4: 기존 호출부 연결 및 tests 실행**

  `scripts/dev_doctor.py`의 core probes, `readiness._dataset()`, `collect_plan()`, `_ace_asset_check()`, ACE `collect_checks()`를 outcome 사용으로 바꾼다. configuration/provider/asset broad catch는 예외 자체를 sanitizer에 보내 cause를 만든다. `doctor --model` collector는 별도 `--model` 경로만 유지한다.

  Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_dev_doctor.py -v`
  Expected: PASS; 기존 aggregate, bytecode, JSON single-document, no-pull/build, owned-container cleanup assertion 유지.

- [x] **Step 5: Task 2 commit**

  ```bash
  git add src/agent_optimizer/readiness.py scripts/dev_doctor.py examples/ace-rtl/environment/diagnostics.py tests/test_dev_doctor.py tests/test_demo_environment.py
  git commit -m "doctor에 안전한 subprocess 실패 원인 전달"
  ```

## Task 3: setup Python과 dataset 실패 진단

**파일:** `examples/ace-rtl/environment/setup.py`, `examples/ace-rtl/environment/model_checks.py`, `examples/benchmarks/cvdp.py`, `examples/benchmarks/verilog_eval.py`, `src/agent_optimizer/datasets.py`, `tests/test_dev_environment.py`, `tests/test_datasets.py`, `tests/test_demo_environment.py`.

**인터페이스:** setup helper는 기존 `ConfigurationError`/`UnavailableError`를 유지하고 안전한 stage detail은 `exc.failure_diagnostic = {"stage", "cause", "log", "fix", "retry"}` 속성으로 전달한다. 새 exception subclass는 만들지 않는다.

- [x] **Step 1: setup 실패 테스트 작성**

  `test_dev_environment.py`에 uv venv/pip sync·Docker build nonzero 및 log, Git clone/checkout, driver Python timeout/permission, Docker image inspect, simulator version, OpenCode tool, CVDP asset TLS/DNS/offline-cache 실패 사례를 추가한다. 로그가 존재할 때 출력에는 유용한 sanitized cause와 log 경로가 있고 secret은 없어야 한다. ACE `doctor.json` test는 stdout/stderr에 `SECRET`을 제공해 결과 JSON에도 저장되지 않는지 확인한다.

```python
def test_logged_docker_build_failure_has_safe_summary_and_log(self):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        log = root / "evaluation-build.log"
        def fail(*_args, **_kwargs):
            log.write_text("Step 4/8\nERROR x509 certificate signed by unknown authority SECRET\n")
            return subprocess.CompletedProcess([], 1, "", "SECRET")
        with patch.object(setup.subprocess, "run", side_effect=fail):
            with self.assertRaises(UnavailableError) as raised:
                setup.run(["docker", "build", "fixture"], cwd=root, log=log)
        diagnostic = raised.exception.failure_diagnostic
        self.assertIn("TLS", diagnostic["cause"])
        self.assertEqual(diagnostic["log"], str(log))
        self.assertNotIn("SECRET", json.dumps(diagnostic))
```

- [x] **Step 2: setup 테스트를 실행해 실패 확인**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_dev_environment.py -v`
  Expected: 새 cause/log assertions에서 FAIL; existing build/platform/cache integrity tests remain unchanged.

- [x] **Step 3: setup subprocess·asset 예외 전달**

  `setup._run()`은 log 파일을 유지하고 nonzero/OS/timeout exception을 Task 1 helper로 분류한다. `prepare_sources()`의 clone/checkout에도 기존 setup log 디렉터리 아래 command별 log를 연결하고 revision/status 확인 실패는 안전한 Git 원인을 전달한다. `fetch_asset`, `validate_platform`, `validate_driver_python`, `driver_packages`, `inspect_image`, `verify_evaluation_tools`는 TLS/DNS/permission/timeout/hash/cache/platform 원인을 안전하게 변환한다.

```python
diagnostic = {
    "stage": stage,
    "cause": summarize_failure(outcome, environment=environment),
    "log": str(log) if log is not None else None,
    "fix": fix,
    "retry": retry,
}
error = UnavailableError(diagnostic["cause"])
error.failure_diagnostic = diagnostic
raise error from None
```

- [x] **Step 4: persisted doctor와 provider 진단 변경**

  `setup.doctor()`는 internal return code와 safe cause만 반환하고 raw stdout/stderr를 결과 dict/`doctor.json`에 저장하지 않는다. `model_checks.check_models()`는 host API와 container-tool 실패 원인을 각 report check에 추가한다. CVDP cache/asset provider 및 Verilog-Eval runtime 준비의 generic `UnavailableError`를 known cause·retry로 보강한다.

- [x] **Step 5: setup 테스트 재실행**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_dev_environment.py -v`
  Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_demo_environment.py -v`
  Expected: PASS; stdout/stderr raw secret does not enter exception, report, or doctor.json.

- [x] **Step 6: Task 3 commit**

  ```bash
  git add examples/ace-rtl/environment/setup.py examples/ace-rtl/environment/model_checks.py examples/benchmarks/cvdp.py examples/benchmarks/verilog_eval.py tests/test_dev_environment.py tests/test_demo_environment.py
  git commit -m "ACE와 dataset setup 실패 원인 보존"
  ```

## Task 4: doctor human renderer와 CLI/TUI

**파일:** `src/agent_optimizer/locale.py`, `src/agent_optimizer/cli.py`, `src/agent_optimizer/tui.py`, `src/agent_optimizer/preset_tui.py`, `scripts/dev_doctor.py`, `tests/test_cli_experience.py`, `tests/test_textual_tui.py`, `tests/test_locale.py`, `tests/test_claude_code.py`, `tests/test_preset_tui.py`.

**인터페이스:** `render_diagnostic(row: dict) -> str`는 기존 `message/remedy`의 내부 line marker를 읽고 summary와 아래 들여쓰기된 Cause/Blocked by/Fix/Retry 문구를 locale 규칙으로 반환한다. doctor check JSON의 필드 구성은 바꾸지 않는다.

- [x] **Step 1: CLI/TUI 회귀 테스트 작성**

  CLI human doctor에서 cause와 retry가 독립 줄로 보이고 JSON `checks`가 정확히 5개 키를 유지하는 테스트를 추가한다. TUI readiness 실패 fixture는 최소 두 개 check를 실패시켜 두 ID와 cause/remedy/retry를 모두 표시하며 run artifact가 생성되지 않는지 확인한다.

```python
async def test_unready_experiment_shows_check_cause_and_retry_without_running(self):
    from agent_optimizer.tui import OptimizerApp
    from textual.widgets import Input, Static

    report = {"ready": False, "checks": [
        {"id": "docker.daemon", "area": "evaluation", "status": "error",
         "message": "Docker daemon access.\nCause: permission denied on docker.sock",
         "remedy": "Start Docker daemon.\nRetry: docker info"},
        {"id": "image.agent", "area": "evaluation", "status": "blocked",
         "message": "Image inspect skipped.\nBlocked by: docker.daemon",
         "remedy": "Resolve docker.daemon first.\nRetry: sh scripts/bootstrap.sh setup"},
    ]}
    with patch("agent_optimizer.readiness.collect_plan", return_value=report):
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("escape", "down", "enter")
            app.query_one(Input).value = "examples/minimal/experiment.toml"
            await pilot.press("enter", "enter")
            for _ in range(80):
                if not app.busy:
                    break
                await asyncio.sleep(0.1)
            text = str(app.query_one("#details", Static).render())
    for phrase in ("docker.daemon", "image.agent", "Cause:", "Blocked by:",
                   "Fix:", "Retry:", "docker info"):
        self.assertIn(phrase, text)
    self.assertFalse(list((self.root / "runs").glob("*/report.html")))
```

- [x] **Step 2: 관련 테스트를 실행해 실패 확인**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -v`
  Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_textual_tui.py -v`
  Expected: cause/retry visibility assertion에서 FAIL.

- [x] **Step 3: 공통 renderer와 소비자 연결**

  renderer는 기존 locale 번역 logic을 유지하면서 message suffix/line markers를 parse한다. `cli.py`와 `dev_doctor.py`는 `[status] id` 첫 줄 및 renderer가 만든 들여쓰기 줄을 출력한다. `tui.py`는 failed/blocked 전체 row를 같은 renderer로 표시하고 generic readiness 안내만으로 대체하지 않는다.

```python
def render_diagnostic(row: dict) -> str:
    message, marker, cause = row["message"].partition("\nCause: ")
    blocked_by = ""
    if not marker:
        message, marker, blocked_by = row["message"].partition("\nBlocked by: ")
    remedy, marker, retry = row["remedy"].partition("\nRetry: ")
    lines = [human(message)]
    if cause:
        lines.append(f"  {human('Cause:')} {human(cause)}")
    if blocked_by:
        lines.append(f"  {human('Blocked by:')} {human(blocked_by)}")
    if remedy:
        lines.append(f"  {human('Fix:')} {human(remedy)}")
    if retry:
        lines.append(f"  {human('Retry:')} {human(retry)}")
    return "\n".join(lines)
```

- [x] **Step 4: renderer/CLI/TUI 재검증**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -v`
  Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_textual_tui.py -v`
  Expected: PASS; `--json` locale별 document와 기존 field names 동일.

- [x] **Step 5: Task 4 commit**

  ```bash
  git add src/agent_optimizer/locale.py src/agent_optimizer/cli.py src/agent_optimizer/tui.py tests/test_cli_experience.py tests/test_textual_tui.py
  git commit -m "CLI와 TUI에 readiness 원인과 retry 표시"
  ```

## Task 5: bootstrap과 개발 setup human/machine 분리

**파일:** `scripts/bootstrap.sh`, `scripts/dev.py`, `src/agent_optimizer/locale.py`, `examples/ace-rtl/environment/setup.py`, `tests/test_dev_onboarding.py`, `tests/test_dev_environment.py`, `tests/test_terminal_colors.py`, `docs/development.md`.

**인터페이스:** setup failure renderer는 stage/cause/log/fix/retry를 stderr에 한국어/영어로 표시한다. doctor `--json` stdout은 변경하지 않는다. bootstrap 전용 shell 분류는 fixed category strings만 출력한다.

- [x] **Step 1: failing shell/python UX tests 작성**

  Fake uv installer와 `uv sync`가 x509, DNS, permission, offline cache miss를 stderr/log에 남기도록 기존 `BootstrapTests` fixture를 확장한다. 출력에 `Cause`, `Log`, `Fix`, validated setup 범위의 `Retry`가 있고 proxy credential/`SECRET`이 없음을 확인한다. `DeveloperCommandsTests`에서는 setup failure가 JSON이 아니라 `[setup] <stage>: failed`와 필수 항목을 출력하고, setup 성공 output도 사람용 안내이며, `doctor --json`은 하나의 JSON만 출력하는지 확인한다.

- [x] **Step 2: onboarding 테스트 실행해 실패 확인**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_dev_onboarding.py -v`
  Expected: safe cause/human output assertion에서 FAIL; unrelated command routing tests unchanged.

- [x] **Step 3: bootstrap safe failure summary 구현**

  uv installer/download/sync 실패 로그는 계속 `$ROOT/external/setup-logs/`에 남긴다. POSIX `case`/`awk` 기반 helper는 사전 정의한 x509/TLS, DNS/connect, permission, offline cache, lock/config, unknown category만 출력하고 raw lines는 출력하지 않는다. failure message는 실패 stage/log/fix/retry를 포함하며 `--core`, `--dataset ID`, `--offline`의 재실행 범위를 보존한다. Docker prerequisite aggregation과 no-Python 설치 경로를 유지한다.

```sh
classify_log() {
    case "$1" in
        *x509*|*certificate*|*TLS*) category=tls ;;
        *resolve*|*DNS*|*network*) category=dns ;;
        *permission*|*denied*) category=permission ;;
        *cache*|*offline*) category=cache ;;
        *lock*|*platform*|*configuration*) category=configuration ;;
        *) category=unknown ;;
    esac
    case "$category" in
        tls) printf '%s' 'TLS 인증서 검증에 실패했습니다' ;;
        dns) printf '%s' 'DNS 또는 네트워크 연결에 실패했습니다' ;;
        permission) printf '%s' '실행 권한 또는 socket 권한이 거부되었습니다' ;;
        cache) printf '%s' '오프라인 cache에 필요한 항목이 없습니다' ;;
        configuration) printf '%s' 'lock 또는 platform 설정이 일치하지 않습니다' ;;
        *) printf '%s' '명령이 실패했습니다. 로그 요약을 확인하세요' ;;
    esac
}
```

- [x] **Step 4: dev.py setup renderer 연결**

  `dev.py` 예외 경계는 setup error의 safe `failure_diagnostic`을 사용해 stage/cause/log/fix/retry를 출력하고 `json.dumps(status=blocked)`를 setup 실패 경로에서 제거한다. 정상 setup 요약은 human `ready/next` text로 출력한다. `KeyboardInterrupt`도 stage와 retry를 안내한다. `doctor --json` 예외/진행 메시지는 stdout을 오염시키지 않는다.

```python
def render_setup_failure(stage, diagnostic, *, retry):
    print(f"[setup] {human(stage)}: {human('failed')}", file=sys.stderr)
    print(f"  {human('Cause:')} {diagnostic['cause']}", file=sys.stderr)
    if diagnostic.get("log"):
        print(f"  {human('Log:')} {diagnostic['log']}", file=sys.stderr)
    print(f"  {human('Fix:')} {diagnostic['fix']}", file=sys.stderr)
    print(f"  {human('Retry:')} {diagnostic.get('retry') or retry}", file=sys.stderr)
```

- [x] **Step 5: 문서와 onboarding 테스트 갱신**

  `docs/development.md`에서 외부 Git/Docker/uv stdout/stderr가 원문 그대로 터미널에 남는다는 설명을 정제된 원인과 private log 보존 정책으로 교체한다. 관련 오류 ID의 Cause/Fix/Retry 출력 및 setup human output 계약을 추가한다.

  Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_dev_onboarding.py -v`
  Expected: PASS; shell fake failure, option scope, status code, JSON stdout 분리 회귀 유지.

- [ ] **Step 6: Task 5 commit**

  ```bash
  git add scripts/bootstrap.sh scripts/dev.py tests/test_dev_onboarding.py docs/development.md
  git commit -m "setup 실패를 사람이 읽는 안전한 진단으로 표시"
  ```

## Task 6: 종합 실패 출력·불변성 검증

**파일:** 관련 구현·테스트 전부와 `docs/superpowers/diagnostic-ux-before.png`, `docs/superpowers/diagnostic-ux-after.png`; 별도 runtime/log framework 추가 금지.

- [x] **Step 1: 대표 failure output 전후 비교**

  기존 코드의 고정된 fake 결과와 수정된 CLI 경로를 각각 실행해 아래 세 시나리오의 실제 stdout/stderr를 수집한다: Docker socket permission (`docker info`), Docker TLS build (`x509 unknown authority`), selected dataset download/cache failure (`DNS` 또는 offline miss). 기존 출력의 일반 `Command failed`/generic error와 개선 출력의 Failed stage/Cause/Log/Fix/Retry를 기록하고 출력에 fixture secret이 없는지 확인한다.

- [x] **Step 2: doctor 핵심 invariants 전체 점검**

  `test_dev_doctor.py`, `test_demo_environment.py`, `test_cli_experience.py`, `test_textual_tui.py`를 다시 실행한다. JSON stdout이 parse 가능한 document 하나이며 기존 key set이 동일한지, secret-free인지, doctor 후 project file/`*.pyc` 집합이 바뀌지 않는지, 독립 오류가 계속 보이는지 확인한다.

- [x] **Step 3: 전체 검증 실행**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`
  Run: `make lint`
  Run: `make doctor-core`
  Run: `make demo`
  Expected: 전체 unittest PASS(환경 의존 skip 수 기록), lint PASS, core doctor ready, 합성 demo completed. 실제 Docker/model/network 통합 검증은 실행하지 않았다고 기록한다.

- [x] **Step 4: 완료 전 변경 검토**

  Run: `git status --short --branch`
  Run: `git diff --check`
  Run: `git diff --stat`
  Expected: spec/plan 및 의도한 진단 코드·테스트·문서만 변경되고 whitespace 오류 없음. 이후 commit/push/PR 단계에서 기본 저장소 main 상태와 worktree 연결도 확인한다.
