# 장시간 명령 진행 표시 보완 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 장시간 사용자 명령의 대기 구간에 실제 단계·경과 시간을 보이고 JSON/실패 계약을 지킨다.

**Architecture:** 이미 있는 `ProgressDisplay`로 ACE live의 runner 이벤트를 전달한다. 나머지 Python 장시간 작업은 기존 `PreparationStatus`의 일반 단계 표시를 재사용한다. Python이 없는 최초 shell setup 구간만 POSIX 셸 타이머로 보완한다.

**Tech Stack:** Python 3.11+, unittest, Rich, POSIX sh, Mac/Linux. 외부 모델·Docker는 회귀 실행에 필요하지 않다.

**Spec:** `docs/superpowers/specs/2026-09-25-command-progress-coverage-design.md`

## Global Constraints

- TTY: spinner와 경과 시간, 비TTY: stderr 단계 시작/완료/실패 한 줄씩. %/ETA 추측 금지.
- JSON stdout은 단일 결과로 유지하고, 모델 키·raw 요청·private 평가 데이터는 상태 문구에 넣지 않는다.
- 결과 판정, upstream SHA, dataset private 경계, trial 예산/이벤트 순서는 바꾸지 않는다.
- 현재 사용자의 기본 디렉토리 `main`과 진행 중인 두 실행을 수정·중단하지 않는다.
- 코드/UX PR에는 전후 캡처 또는 캡처 불가 이유와 재현 방법을 본문에 포함한다.

---

### Task 1: 단계 진행 표시의 기존 컴포넌트 확장

**Files:**
- Modify: `src/agent_optimizer/terminal_report.py:131-161`
- Test: `tests/test_progress.py:71-81`

**Interfaces:**
- Consumes: `PreparationStatus(name, stream=None)`의 기존 dataset 표기.
- Produces: `PreparationStatus(name, stream=None, *, action="prepare", subject="dataset")`, 기존 기본값 유지. 이후 작업은 `action="smoke", subject="check"`처럼 호출한다.

- [ ] **Step 1: 실패하는 행동 테스트 추가.** 다음처럼 비TTY·TTY를 각각 검사하고 기존 dataset 출력도 유지한다.

```python
def test_named_operation_keeps_stdout_clean_and_marks_failure(self):
    output, status = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(output):
        with self.assertRaisesRegex(ValueError, "fixture failure"):
            with PreparationStatus("host-api", stream=status, action="doctor", subject="check"):
                raise ValueError("fixture failure")
    self.assertEqual(output.getvalue(), "")
    self.assertIn("[doctor] check=host-api starting", status.getvalue())
    self.assertIn("[doctor] check=host-api failed", status.getvalue())
```

- [ ] **Step 2: RED 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_progress.py -v`에서 새 테스트가 미지원 인수로 실패하는지 확인한다.
- [ ] **Step 3: 최소 구현.** 생성자에서 action/subject를 저장하고 기존 `"[prepare] dataset=..."` 두 곳을 `f"[{self.action}] {self.subject}={self.name}"`로 만든다. 이미 있는 Rich spinner와 `time.monotonic()`은 그대로 사용한다.
- [ ] **Step 4: GREEN 확인.** 같은 테스트 파일과 `tests/test_terminal_colors.py`를 실행하고, 기존 dataset 라벨이 유지되는지 확인한다.
- [ ] **Step 5: `git diff --check` 후 컴포넌트·테스트만 커밋.** 메시지는 `장시간 단계 상태 표시를 명령별로 재사용`.

### Task 2: ACE live와 smoke의 실행 중 단계 연결

**Files:**
- Modify: `examples/ace-rtl/environment/checks.py:28-115`
- Test: `tests/test_progress.py`, `tests/test_dev_environment.py:813-829`

**Interfaces:**
- Consumes: Task 1의 `PreparationStatus`; 기존 `run_experiment(spec, registry, output, on_event=None)`, `ProgressDisplay.configure_budget(max_trials)`.
- Produces: `make live`에 실제 runner 이벤트, `make smoke`에 검사별 상태. 최종 JSON과 `summary.json` 구조는 변경 없음.

- [ ] **Step 1: live 실패 회귀.** `checks.live`의 느린 runner 호출만 테스트 더블로 바꾸고 저장되는 이벤트와 같은 형식의 `trial_started`와 `agent_started`를 callback에 전달한다. stderr에 `phase=agent`와 `MAX TRIAL BUDGET completed=0 remaining=4 / 4`가 나와야 하고 stdout의 마지막 줄은 JSON이어야 한다. 테스트 배치는 `tests/test_progress.py`.

```python
def fake_run(spec, registry, output, *, on_event=None):
    on_event({"event": "agent_started", "timestamp": "2026-09-25T02:00:00Z",
              "dataset": "ace-demo", "stage_id": "baseline", "task_id": "qam", "phase": "agent"})
    return output / "fixture", {"status": "completed"}
```

- [ ] **Step 2: smoke 실패 회귀.** `checks.smoke`에서 Docker 실행 경계 `execute`가 `ExecutionResult("timeout", ...)`를 반환하게 하여 조기 실패시키고 stderr에 `check=T4-real-tools starting`, `failed`가 남으며 마지막 stdout JSON은 `status=failed`인지 확인한다. 검사 데이터 내용/판정은 위조하지 않는다.

```python
class NoEvaluatorNeeded:
    def load_plugins(self, *_args):
        pass

with tempfile.TemporaryDirectory() as directory, \
        patch.object(checks, "ROOT", Path(directory)), \
        patch.object(checks, "Registry", return_value=NoEvaluatorNeeded()), \
        patch.object(checks, "execute", return_value=ExecutionResult("timeout", None, 0.1, "out", "err")), \
        contextlib.redirect_stdout(output), contextlib.redirect_stderr(progress):
    with self.assertRaises(UnavailableError):
        checks.smoke({"images": {"evaluation": {"id": "fixture-image"}}})
self.assertIn("[smoke] check=T4-real-tools failed", progress.getvalue())
self.assertEqual(json.loads(output.getvalue())["status"], "failed")
```
- [ ] **Step 3: RED 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_progress.py -v` 및 `-p test_dev_environment.py`에서 새 주장이 기존 live/smoke에서 실패하는지 확인한다.
- [ ] **Step 4: 최소 연결.** `live`의 `run_experiment` 호출을 `with ProgressDisplay() as progress: progress.configure_budget(spec["budget"]["max_trials"]); run_experiment(..., on_event=progress)`로 변경한다. smoke의 도구/각 toy/공식 CVDP 평가에 `with PreparationStatus(name, action="smoke", subject="check"):`를 적용하고 실제 판정은 기존 함수로 유지한다.
- [ ] **Step 5: GREEN·커밋.** 위 테스트와 `make demo`, `git diff --check`를 확인하고 `ACE live·smoke 진행 상황을 터미널에 표시`로 커밋한다.

### Task 3: 개발 명령 및 사용자 CLI의 무출력 호출 경계

**Files:**
- Modify: `scripts/dev.py:121-236`, `examples/ace-rtl/environment/model_checks.py:30-59`, `src/agent_optimizer/cli.py:203-456`
- Test: `tests/test_dev_onboarding.py:719-750`, `tests/test_demo_environment.py:45-69`, `tests/test_cli_experience.py`

**Interfaces:**
- Consumes: Task 1의 `PreparationStatus`와 기존 doctor/render/prepare/report 함수.
- Produces: `make setup --dataset`, `make doctor`, `make smoke/live`의 사전 환경 점검, `agent-opt doctor --dataset/--plan --model`, `agent-opt report --html/--csv`에서 stderr 단계 상태. API·파일 결과 계약 동일.

- [ ] **Step 1: JSON 및 순서 회귀.** `make doctor --json`의 stdout을 `json.loads`로 한 번만 파싱하고 stderr에 현재 `check=environment` 단계가 있는지 검사한다. `tests/test_dev_onboarding.py`의 선택 provider 테스트는 stderr에서 `dataset=sample_text` 시작/종료와 `check=dataset`를 확인한다.

```python
output, progress = io.StringIO(), io.StringIO()
with contextlib.redirect_stdout(output), contextlib.redirect_stderr(progress):
    self.assertEqual(self.main(["doctor", "--core", "--json"]), 0)
self.assertEqual(json.loads(output.getvalue())["scope"], "core")
self.assertIn("[doctor] check=environment starting", progress.getvalue())
```
- [ ] **Step 2: 모델·CLI 회귀.** 기존 `tests/test_demo_environment.py`에서 host probe/컨테이너 probe 각각의 시작·실패 문구와 비밀값 부재를 검사한다. `tests/test_cli_experience.py`에서 `doctor --plan --model`의 stdout JSON/ stderr 모델 단계, `report --html`의 JSON/ stderr 보고서 단계가 분리되는지 확인한다.

```python
self.assertIn("[doctor] check=host-api starting", diagnostic.getvalue())
self.assertIn("[doctor] check=container-tool failed", diagnostic.getvalue())
self.assertNotIn("fixture-secret", diagnostic.getvalue())
self.assertEqual(json.loads(output.getvalue())["scope"], "plan")
```
- [ ] **Step 3: RED 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_dev_onboarding.py -v` 및 `-p test_demo_environment.py`, `-p test_cli_experience.py`에서 새 단언이 실패하는지 확인한다.
- [ ] **Step 4: 최소 구현.** `scripts/dev.py`의 `collect_report`, provider.prepare 및 preflight doctor 실행을 `PreparationStatus(..., action="doctor"/"setup", subject="check"/"dataset")`로 감싼다. 모델 호스트·컨테이너 probe는 `model_checks.py`에서 별도 상태로 감싼다. CLI의 선택 doctor와 HTML/CSV 재생성은 각각 `with PreparationStatus(..., action="doctor"/"report", subject="check"):`로 감싼다. 모든 상태는 stderr, 최종 결과는 기존 stdout에 둔다.
- [ ] **Step 5: GREEN·커밋.** 세 테스트 파일과 `make lint`를 통과시키고 `개발 명령과 사용자 진단의 대기 상태를 표시`로 커밋한다.

### Task 4: Python이 없는 setup과 설치 로그의 긴 단계

**Files:**
- Modify: `scripts/bootstrap.sh:277-350`, `examples/ace-rtl/environment/setup.py:100-125,438-504`
- Test: `tests/test_dev_onboarding.py:340-380`, `tests/test_dev_environment.py`

**Interfaces:**
- Consumes: Task 1의 Python 상태 표시, 기존 setup stdout 단계/로그 경로와 POSIX 셸.
- Produces: TTY shell uv 동기화 중 경과 표시, Python 다운로드·이미지 빌드·도구 검사 중 단계 경과. 리다이렉트 시 기존 줄 단위 출력만 남긴다.

- [ ] **Step 1: 실패 회귀.** 가짜 `uv`를 짧게 지연시키는 bootstrap test에서 PTY stderr의 `elapsed=`가 종료 전에 출력되는지 확인한다. `setup.run(["python3", "-c", "import time; time.sleep(1.1)"], log=...)` 테스트는 가짜 지연 child의 시작/완료·stderr status와 로그 파일의 기존 command 기록을 확인한다.

```python
master, slave = pty.openpty()
process = subprocess.Popen(["sh", str(self.root / "scripts/bootstrap.sh"), "setup", "--core"],
                           cwd=self.root, env=self.environment, stdout=subprocess.PIPE,
                           stderr=slave, text=True)
os.close(slave)
# The fixture's uv command sleeps for 1.1 seconds; read the PTY before wait() finishes.
observed = ""
while "elapsed=" not in observed and process.poll() is None:
    readable, _, _ = select.select([master], [], [], 2)
    if readable:
        observed += os.read(master, 4096).decode(errors="replace")
self.assertIn("elapsed=", observed)
self.assertEqual(process.wait(timeout=10), 0)
os.close(master)
```
- [ ] **Step 2: RED 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_dev_onboarding.py -v`와 `-p test_dev_environment.py`에서 진행 주장이 실패하는지 확인한다.
- [ ] **Step 3: 최소 구현.** bootstrap에서 TTY stderr인 경우에만 `date +%s`·`sleep 1`을 쓰는 background heartbeat를 uv 설치/동기화 기간에 실행한다. 성공·실패·INT/TERM에서 해당 자식만 종료·wait하고, 비TTY/JSON에는 ticker를 시작하지 않는다. Python setup의 오래 걸리는 `run`과 출처·데이터·도구 검사에 Task 1의 `PreparationStatus`를 적용하며 로그 원문이나 명령 인수를 상태에 쓰지 않는다.
- [ ] **Step 4: GREEN·커밋.** bootstrap·setup 관련 회귀, `make setup ARGS="--core"`, `git diff --check` 확인 후 `설치·이미지 준비 중 경과 시간을 표시`로 커밋한다.

### Task 5: 사용자 검증 근거·UI 캡처·PR

**Files:**
- Modify: `README.md`, `docs/verification.md` (실제 확인한 실행 결과와 시간·제한만 기록)
- PR 본문에 변경 전/후 캡처 및 재현 절차; headless/터미널 캡처 불가면 이유 기록.

**Interfaces:**
- Consumes: Task 1~4의 TTY/비TTY 검증 결과와 사용자 실행 상태.
- Produces: 재현 명령, 변경 범위가 정직한 PR.

- [ ] **Step 1: 전체 검증.** `make lint`, `make test`, `make demo`, `node --test tests/endpoint-plugin.test.mjs`, `git diff --check`를 실행한다. Docker 이미지·lock을 별도 워크트리에 준비한 경우에만 `make smoke`를 실행하고 그렇지 않으면 그 한계를 기록한다.
- [ ] **Step 2: 문서·캡처.** `README.md`에 `live`/`smoke`/`doctor`의 stderr 진행과 JSON stdout 분리를 간결히 적고 `docs/verification.md`에 실제 명령/결과/미검증을 기록한다. TTY의 전후 상태를 캡처해 PR에 넣거나 캡처 불가 이유 및 같은 재현 명령을 명시한다.
- [ ] **Step 3: 전달.** `git status --short --branch`, `git diff`, `git log --oneline -10`으로 의도한 파일만 확인하고 커밋·푸시한다. `gh pr create --base main`으로 PR을 만들고 CI 상태·기본 디렉토리 `main`·워크트리 연결을 확인한다. 머지는 사용자 승인 후 수행한다.
