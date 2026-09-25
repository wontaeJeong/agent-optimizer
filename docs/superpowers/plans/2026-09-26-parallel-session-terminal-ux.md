# 데이터셋 병렬 실행과 터미널 UX 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 여러 데이터셋을 별도 프로세스로 제한된 수만큼 동시에 실행하고 한 터미널 화면에 상태를 표시하며 다른 순차 병목을 측정한다.

**Architecture:** `session.py`가 자식 프로세스별로 기존 `run_experiment`를 실행하고 필요한 이벤트만 Queue로 부모에 보낸다. `terminal_report.py`가 고정된 데이터셋 행을 갱신한다. `cli.py`는 입력/옵션과 기존 session index·JSON 결과를 연결한다.

**Tech Stack:** Python 3.11+, 표준 라이브러리 `multiprocessing` spawn/Queue, 기존 Typer/Rich, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-26-parallel-session-terminal-ux-design.md`

## Global Constraints

- 데이터셋마다 원본·채점·예산·독립 보고서를 유지하고 stdout의 최종 JSON을 보존한다.
- 기본 동시 실행 2개, `--jobs` 양의 정수; TUI의 복수 데이터셋은 같은 경로를 사용한다.
- 한국어 기본/영어 선택, private feedback·credential을 화면/프로세스 큐로 보내지 않는다.
- Mac/Ubuntu Python 3.11+에서 동작하며 단일 실험 내부 그룹·stage·과제/반복의 순서는 바꾸지 않는다.
- 커밋 메시지, 문서 및 사용자에게 보이는 새 문구는 한국어로 작성한다.

## 파일 책임

- `src/agent_optimizer/session.py` (신규): 데이터셋 프로세스 실행, 이벤트 전달, 완료/실패/중단 수집; 보고서 경로 계산.
- `src/agent_optimizer/terminal_report.py`: 여러 데이터셋의 TTY 행과 비TTY 상태 출력; 기존 단일 실험 표시 유지.
- `src/agent_optimizer/cli.py`: `--jobs`와 session 결과 JSON/HTML index 연결, TUI에서 동일 경로 호출.
- `src/agent_optimizer/locale.py`, `README.md`, `docs/status.md`, `docs/verification.md`: 문구/실제 지원 범위/측정 근거.
- `tests/test_progress.py`, `tests/test_cli_experience.py`: 화면·경계·병렬/실패/중단 회귀.

---

### Task 1: 데이터셋별 진행 행

**Files:** `src/agent_optimizer/terminal_report.py`, `tests/test_progress.py`, `src/agent_optimizer/locale.py`.

**Interfaces:** `SessionProgress(datasets: list[str], stream=None)`은 context manager; `start(index: int)`, `event(index: int, record: dict)`, `finish(index: int, status: str, elapsed: float)`를 노출한다. 행은 이름이 중복돼도 index로 구분한다.

- [ ] **Step 1: 실패 테스트 작성.** TTY 대용 `io.StringIO`의 `isatty()`를 True로 만들고 `with SessionProgress(["A", "B"], stream=terminal) as screen: screen.start(0); screen.start(1); screen.event(1, {"event": "agent_started", "task_id": "t2", "stage_id": "baseline", "phase": "agent"}); screen.finish(0, "completed", 1.2)` 후 화면에 A/B, 완료, t2 및 ANSI 스타일이 함께 있는지 확인한다. 일반 `StringIO`에서는 각 줄에 `[1/2]` 또는 `[2/2]`를 포함하고 stdout에 쓰지 않는지 검증한다.

```python
with SessionProgress(["A", "B"], stream=terminal) as screen:
    screen.start(0)
    screen.start(1)
    screen.event(1, {"event": "agent_started", "task_id": "t2", "stage_id": "baseline", "phase": "agent"})
    screen.finish(0, "completed", 1.2)
self.assertIn("t2", terminal.getvalue())
```
- [ ] **Step 2: 실패 확인.** `PYTHONPATH=src /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_progress.py -v` → `SessionProgress` ImportError/AssertionError.
- [ ] **Step 3: 최소 구현.** `_terminal_progress`의 Rich Progress를 재사용해 `add_task(..., start=False)`로 대기 행을 만들고 start 시 `start_task`, event 시 해당 행만 `update`, finish 시 `stop_task`한다. 비TTY는 식별자와 상태가 있는 줄을 `stream.write`/`flush`한다. record의 task/stage/phase/iteration/total/elapsed만 화면에 반영하며 사용자 문구는 locale 사전에 등록한다.

```python
def start(self, index: int) -> None:
    self.progress.start_task(self.task_ids[index])
    self.progress.update(self.task_ids[index], description=self._label(index, "실행 중"))
```
- [ ] **Step 4: 테스트 통과·커밋.** 같은 명령 및 `git diff --check` 통과 후 `git add src/agent_optimizer/terminal_report.py src/agent_optimizer/locale.py tests/test_progress.py && git commit -m "세션의 데이터셋별 진행 상태를 터미널에 표시"`.

### Task 2: 독립 워커와 제한된 스케줄러

**Files:** 신규 `src/agent_optimizer/session.py`, `tests/test_cli_experience.py`.

**Interfaces:** `run_session(experiments: list[dict], session_root: Path, *, jobs: int, progress: SessionProgress) -> list[dict]`는 입력 순서의 기존 entry 형태를 반환한다. `_worker(index: int, item: dict, run_base: Path, queue, components: dict, dependencies: dict)`는 spawn 가능한 최상위 함수이며 `("event", index, projected)` 또는 `("done", index, entry)`를 보낸다. `_project_event(record: dict) -> dict`는 아래 whitelist만 남긴다. `SessionInterrupted(KeyboardInterrupt)`는 중단된 `entries: list[dict]`를 보유한다.

- [ ] **Step 1: 실패 테스트 작성.** `test_cli_experience.py`의 기존 복수 데이터셋 fixture를 재사용하고 파일 evaluator에 두 워커가 시작했음을 기록한 뒤 짧은 대기 동안 상대 워커의 기록을 확인하는 방식을 넣는다. `run_session(..., jobs=2, ...)`는 양쪽이 동시에 시작되어 완료되고 `jobs=1`에서는 겹치지 않음을 별도 테스트로 검증한다. 동명 데이터셋은 순번별 경로를, 깨진 설정 하나는 다른 쪽의 성공 보고서와 원래 순서의 결과를 확인한다.

```python
with SessionProgress(["first", "second"], stream=io.StringIO()) as progress:
    entries = run_session(experiments, self.root / "sessions" / "check", jobs=2, progress=progress)
self.assertEqual([entry["status"] for entry in entries], ["completed", "completed"])
```
- [ ] **Step 2: 실패 확인.** `PYTHONPATH=src /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -v` → 새 함수 없음/순차 실행의 barrier 실패.
- [ ] **Step 3: 최소 구현.** `ctx = multiprocessing.get_context("spawn")`; `queue = ctx.Queue()`와 최대 `min(jobs, len(experiments))`개의 `ctx.Process(target=_worker, ...)`를 시작한다. 부모는 `queue.get(timeout=0.1)`로 이벤트를 표시하고 완료 entry를 입력 index에 보관하며 빈 슬롯에 다음 데이터셋을 예약한다. 각 워커는 `runs/{index + 1:02d}` 아래에서 자체 Registry를 사용하고 `logs.txt`에 표준 출력·오류를 격리한다. spawn이 부모의 메모리상 registry 등록을 상속하지 않으므로 `PROJECT_COMPONENTS`·`PROJECT_DEPENDENCIES`의 문자열 매핑 스냅샷을 자식에게 전달한다(파일/심볼 검증은 그대로 수행). 이벤트 전달은 `event, timestamp, dataset, stage_id, task_id, phase, iteration, total, status, metrics.task_wall_time_seconds`의 whitelist만 허용한다. 예외/비정상 종료는 해당 데이터셋만 error로 기록하고 해당 디렉터리의 실제 report가 있을 때만 상대 경로를 남긴다. KeyboardInterrupt 시 활성 워커 terminate/join, 대기 항목은 interrupted로 채운 후 `SessionInterrupted(entries)`를 상위로 전파한다. 프로세스/Queue는 finally에서 join/close한다.

```python
def _worker(index: int, item: dict, run_base: Path, queue,
            components: dict, dependencies: dict) -> None:
    from agent_optimizer.registry import PROJECT_COMPONENTS, PROJECT_DEPENDENCIES
    PROJECT_COMPONENTS.clear()
    PROJECT_COMPONENTS.update(components)
    PROJECT_DEPENDENCIES.clear()
    PROJECT_DEPENDENCIES.update(dependencies)
    run_base.mkdir(parents=True, exist_ok=True)
    with (run_base / "logs.txt").open("w", encoding="utf-8") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            spec = load_experiment(Path(item["experiment"]))
            root, result = run_experiment(spec, Registry(), run_base,
                                          on_event=lambda record: queue.put(("event", index, _project_event(record))))
    queue.put(("done", index, {"dataset": item["dataset"], "status": result["status"],
                               "report": str(root / "report.html"), "trials_used": result["trials_used"]}))
```

실제 구현은 예외 처리를 `try/finally`에 포함하며 `report`를 세션 상대 경로로 변환하고, worker 출력은 로그에만 기록한다.
- [ ] **Step 4: 테스트 통과·커밋.** 같은 명령과 `git diff --check` 확인 뒤 `git add src/agent_optimizer/session.py tests/test_cli_experience.py && git commit -m "데이터셋별 독립 프로세스로 세션을 병렬 실행"`.

### Task 3: CLI/TUI 경로와 세션 결과 통합

**Files:** `src/agent_optimizer/cli.py`, `tests/test_cli_experience.py`, `README.md`, `docs/status.md`.

**Interfaces:** `run_session_command(session: Path, output: Path | None = None, jobs: int = 2)`가 `--jobs`를 노출한다. CLI 분기는 Task 2의 `run_session(experiments, session_root, jobs=jobs, progress=...)`를 호출한다.

- [ ] **Step 1: 실패 테스트 작성.** 실제 `main(["run-session", path, "--jobs", "2"])` 호출로 stdout이 단일 JSON인지, 2개 보고서의 index가 순서대로인지, stderr에 두 식별자가 있는지 확인한다. `--jobs 0`/음수는 디렉터리 생성 전에 실패하도록, `--jobs 1`은 순차 실행하도록 검사한다. `main(["tui", ...])`의 기존 session 호출 경로도 회귀 검사한다.

```python
with contextlib.redirect_stdout(io.StringIO()) as output:
    code = main(["run-session", str(session), "--jobs", "2"])
self.assertEqual(code, 0)
self.assertEqual(json.loads(output.getvalue())["status"], "completed")
```
- [ ] **Step 2: 실패 확인.** `PYTHONPATH=src /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -v` → 미지원 옵션 또는 순차 실행으로 실패.
- [ ] **Step 3: 최소 구현.** Typer의 인수를 검증해 기존 `run-session` 순차 for-loop를 session scheduler 호출로 치환하고, `SessionProgress`를 `with`에서 사용한다. 기존 `write_session_index`, `write_json(summary.json)`, `show(...)`는 단일 부모에서만 실행한다. `SessionInterrupted`를 받아 `summary.json`에 interrupted 상태/부분 결과를 남기고 return 130, 실패 부분 실행의 return 3을 보장한다. 기존 TUI의 `main(["run-session", ...])` 연결을 유지한다. 새 동작과 자원 제한을 README/status에 기술한다.

```python
@app.command("run-session")
def run_session_command(session: Path, output: Path | None = None,
                        jobs: int = typer.Option(2, "--jobs", min=1)) -> int:
    return _invoke("run-session", session=session, output=output, jobs=jobs)
```

세션 summary에는 실제 `session_wall_time_seconds`와 중단 시 `interrupted` 상태를 기록한다.
- [ ] **Step 4: 테스트 통과·커밋.** 관련 테스트 및 `git diff --check` 확인 후 `git add src/agent_optimizer/cli.py tests/test_cli_experience.py README.md docs/status.md && git commit -m "CLI와 TUI에 병렬 세션 실행을 연결"`.

### Task 4: 병목 측정, 캡처, 통합 검증

**Files:** `docs/verification.md`, 필요할 때에만 `tests/test_cli_experience.py`.

**Interfaces:** `run_wall_time_seconds`/`stage_wall_time_seconds`/`task_wall_time_seconds`/세션 경과와 이벤트 시각을 이용해 합성 fixture 비교를 기록한다. `summary.json`의 `status`와 보고서 경로는 이전 계약을 유지한다.

- [ ] **Step 1: 실측 시나리오.** 동일한 두 합성 데이터셋 session을 `--jobs 1` 및 `--jobs 2`로 각각 실행해 전체 시간, 각 run 시간 및 trial의 agent/evaluation 시간을 기록한다. 준비·Agent×Harness·stage·과제/반복의 순차 코드 경계를 실행 결과와 대조하고 미측정 실환경은 미검증으로 쓴다.
- [ ] **Step 2: 캡처와 회귀.** 변경 전 main 버전과 변경 후 브랜치에서 실제 TTY 명령으로 화면을 남기고 PR 첨부용 이미지/재현 절차를 확보한다. `PYTHONPATH=src /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -v`, `PYTHONPATH=src /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml`, `/Users/wt.jeong/workspace/agent-optimizer/.venv/bin/ruff check .` (워크트리의 독립 `.venv`가 준비되었다면 `make lint`), `git diff --check`를 실행해 결과를 기록한다.
- [ ] **Step 3: 검증 문서·커밋.** 명령/환경/측정값/해석과 우선순위, 실제 캡처 출처를 `docs/verification.md`에 적는다. `git add docs/verification.md` 및 의도한 캡처 파일만 stage해 `git commit -m "병렬 세션 화면과 순차 병목 측정 결과 검증"`.
- [ ] **Step 4: PR.** 모든 커밋의 변경·기본 브랜치 차이·Git 상태를 검토하고 push/PR 작성. 본문에 변경 전/후 실제 화면과 재현 절차, 검증 결과, 합성/실환경의 차이를 포함한다.
