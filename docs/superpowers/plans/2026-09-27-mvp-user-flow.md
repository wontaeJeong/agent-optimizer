# MVP 사용자 첫 실행 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 마법사·TUI·CLI에서 선택과 준비, 정적 확인, 실행 결과/복구를 혼동하지 않고 첫 결과를 찾게 한다.

**Architecture:** `setup_wizard.py`는 입력 검증과 출력만, `cli.py`는 기존 명령 분기와 TUI 설정 탐색만 수정한다. 실행·평가·보고서 스키마는 그대로 둔다.

**Tech Stack:** Python 3.11+, Typer, unittest, 기존 한국어/영어 `human()` 및 `locale.py`.

**Spec:** `docs/superpowers/specs/2026-09-27-mvp-first-run-clarity-design.md`.

## Global Constraints

- 대상은 최신 `origin/main` 기반의 전용 워크트리이며 기본 저장소 `main`은 수정하지 않는다.
- JSON의 기존 키·종료 코드 보존, stdout 단일 JSON, 사람용 추가 안내는 stderr.
- 데이터셋 명시적 선택, train/validation/test 경계, 원본·private 평가 격리 및 실패 시 합성 대체 금지.
- 새 프레임워크·플러그인 자동 발견·데이터베이스·전체 화면 이력 탐색기 금지.
- 모델/Docker/공식 평가 미준비 시 실행 성공을 주장하지 않는다.

---

### Task 1: 마법사 입력 오류를 확인 전에 차단

**Files:**
- Modify: `src/agent_optimizer/setup_wizard.py:250-343`
- Test: `tests/test_cli_experience.py:1518-1580`

**Interfaces:**
- Consumes: `wizard_arguments(project_root: Path, *, execute: bool=True) -> list[str]`.
- Produces: 동일한 argv 또는 `ConfigurationError`; 오류 시 `prepare_selection`/`main(init)`을 호출하지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성.** `test_project()`에서 `wizard_arguments(self.root, execute=False)`의 입력을 `patch('builtins.input', side_effect=...)`로 바꾼다. 빈 editable, 데이터셋 `0/-1/999`, Optimizer `0/-1/999`와 빈 선택, 하네스 `0/999`를 각 case로 반복하고 `ConfigurationError`를 확인한다. `prepare_selection`을 `AssertionError`로 patch하고 `runs`가 없는지도 확인한다.

```python
with patch("builtins.input", side_effect=answers), \
     patch("agent_optimizer.setup_wizard.prepare_selection", side_effect=AssertionError("준비 호출")):
    with self.assertRaises(ConfigurationError):
        wizard_arguments(self.root, execute=False)
self.assertFalse((self.root / "runs").exists())
```

- [ ] **Step 2: 실패를 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -v`; 새 case에서 `IndexError` 또는 마지막 Optimizer 선택을 관찰한다.
- [ ] **Step 3: 최소 구현.** `name`, `agent`, `editable` 입력 직후 빈 값에 `ConfigurationError`를 던지고, 숫자 선택은 `1 <= int(value) <= len(choices)`로 인덱싱 전에 검증한다. 데이터셋 경로는 숫자 형태가 아닌 경우만 그대로 허용한다. `-1`을 경로 취급하지 않도록 `item.lstrip('+-').isdigit()`을 사용한다. `editable[0]` 접근 전에 유효한 목록을 보장한다.

```python
def listed_number(value: str, choices: list[str], label: str) -> str:
    if not value.isdecimal() or not 1 <= int(value) <= len(choices):
        raise ConfigurationError(human(f"목록의 {label} 번호를 선택하세요"))
    return choices[int(value) - 1]
```

- [ ] **Step 4: 통과 확인.** 같은 unittest 명령으로 새 case와 기존 마법사/취소 case를 통과시킨다.
- [ ] **Step 5: 커밋.** `git add src/agent_optimizer/setup_wizard.py tests/test_cli_experience.py && git commit -m '마법사 선택 오류를 준비 전에 차단'`.

### Task 2: 선택지 설명과 확인 화면

**Files:**
- Modify: `src/agent_optimizer/setup_wizard.py:250-343`, `src/agent_optimizer/locale.py`
- Test: `tests/test_cli_experience.py`, `tests/test_locale.py`

**Interfaces:**
- Consumes: Task 1 `wizard_arguments`; `Registry.factories`와 각 dataset의 `describe()`.
- Produces: 선택 전에 조건을 보여주는 stderr, 확인 직전 예산·출력 경로를 보여주는 stderr; argv 반환 형식 불변.

- [ ] **Step 1: 실패 테스트 작성.** `sample_text`, `cvdp`, `command`, `fixture`, `opencode`, `gepa`의 설명과 기본 예산/설정/HTML 예상 경로가 확인 프롬프트 **전에** 출력되는지 캡처한다. 취소 응답 `n`에서 파일과 준비 호출이 없는지, `AGENT_OPT_LANG=en`에서 주요 문구가 영어인지 확인한다.

```python
with patch("builtins.input", side_effect=answers), contextlib.redirect_stderr(terminal):
    with self.assertRaises(ConfigurationError):
        wizard_arguments(self.root, execute=False)
text = terminal.getvalue()
self.assertLess(text.index("80"), text.index("[y/N]"))
self.assertIn("runs/configs/", text)
```

- [ ] **Step 2: 실패를 확인.** CLI 경험·언어 테스트를 위와 같은 `unittest discover -p` 방식으로 실행한다.
- [ ] **Step 3: 최소 구현.** 데이터셋은 등록된 ID/설명과 카탈로그 조건을 대조해 합성/고정 자산·Docker·사용자 evaluator 요구를 표시한다. 하네스·Optimizer 설명은 내장 ID의 검증된 조건만 표시하고 팀 ID는 '팀 구현·의존성 확인'으로 안내한다. 예산은 `max_tasks=9`, 기본 최대 trial 80(선택 후 데이터에 따라 높아질 수 있음), 전체 3600초, trial 120초라고 표시하고, 다운로드/외부 도구·모델 호출 가능성을 분리한다. 예상 경로는 단일/복수 데이터셋을 구분하며 실제 run ID는 미정으로 표시한다. 새 한/영 문구는 `locale.py`에 동등하게 등록한다.

```python
print(f"  {human('기본 예산')}: max_tasks=9, max_trials>=80, "
      "max_wall_time_seconds=3600, trial_timeout_seconds=120", file=sys.stderr)
print(f"  {human('설정 위치')}: {project_root / 'runs/configs' / name}", file=sys.stderr)
print(f"  {human('예상 보고서')}: {project_root / 'runs/<run-id>/report.html'}", file=sys.stderr)
```

- [ ] **Step 4: 관련 테스트 통과.** 위 테스트 및 `test_plugin_contracts.py`를 실행해 동적 등록과 취소 동작을 확인한다.
- [ ] **Step 5: 커밋.** `git add src/agent_optimizer/setup_wizard.py src/agent_optimizer/locale.py tests/test_cli_experience.py tests/test_locale.py && git commit -m '마법사 선택 조건과 실행 전 예산 안내'`.

### Task 3: 기존 실험에 최근 생성 설정 선택 추가

**Files:**
- Modify: `src/agent_optimizer/cli.py:545-660`, `src/agent_optimizer/locale.py`
- Test: `tests/test_cli_experience.py`, `tests/test_locale.py`

**Interfaces:**
- Consumes: `args.project_root / 'runs/configs'`; TUI 1번 분기의 문자열 선택.
- Produces: `list[Path]` 최근 설정 최대 5개, 목록 번호 또는 기존 직접 경로; 4번 이전 실행 보기 유지.

- [ ] **Step 1: 실패 테스트 작성.** `runs/configs/<name>/experiment.toml` 두 개를 만들고 `os.utime`으로 순서를 정해 목록/번호 선택이 `collect_plan`에 정확한 Path를 넘기는지 확인한다. 목록 없음·명시적 절대/상대 경로·범위 밖 번호·외부 symlink·깨진 설정·입력 종료에서 기존 오류 코드와 무실행을 확인한다.

```python
with patch("sys.stdin.isatty", return_value=True), \
     patch("builtins.input", side_effect=["1", "1", "n"]), \
     patch("agent_optimizer.cli.collect_plan", return_value={"scope": "plan", "ready": True, "checks": []}) as plan, \
     contextlib.redirect_stderr(terminal):
    self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
plan.assert_called_once()
```

- [ ] **Step 2: 실패 확인.** CLI/locale 테스트 두 파일을 실행한다.
- [ ] **Step 3: 최소 구현.** `runs/configs` 아래의 정상 `experiment.toml`만 수집하고 루트 밖 symlink는 제외하며 `stat().st_mtime_ns`, 경로 이름의 순서로 정렬해 5개만 표시한다. 1번의 현재 경로 입력 직전에 목록을 보여주고 `1..N`이면 해당 경로, 나머지는 기존 명시적 경로로 처리한다. 숫자로 보이는 범위 밖 입력은 오류로 종료한다. 4번 기존 읽기 전용 결과 이력은 변경하지 않는다.

```python
if selected.isdecimal():
    number = int(selected)
    if not 1 <= number <= len(recent):
        raise ConfigurationError(human("목록의 설정 번호를 선택하세요"))
    experiment = recent[number - 1]
else:
    experiment = Path(selected).expanduser()
```

- [ ] **Step 4: 통과 확인.** 해당 tests와 명시적 ACE/TUI 4번 이력 검사를 실행한다.
- [ ] **Step 5: 커밋.** `git add src/agent_optimizer/cli.py src/agent_optimizer/locale.py tests/test_cli_experience.py tests/test_locale.py && git commit -m 'TUI에 최근 생성 설정 선택 추가'`.

### Task 4: CLI 성공/진단 출력의 의미 정리

**Files:**
- Modify: `src/agent_optimizer/cli.py:178-278, 545-767`, `src/agent_optimizer/locale.py`
- Test: `tests/test_cli_experience.py`, `tests/test_locale.py`

**Interfaces:**
- Consumes: 기존 `show(value)`, `collect_plan`, `run_experiment`, `run_session`.
- Produces: 기존 stdout JSON에 `run.report_html`만 추가; 후속 명령과 결과 위치는 stderr.

- [ ] **Step 1: 실패 테스트 작성.** 단일/복수 init·run·run-session·report와 plan/doctor의 stdout을 `json.loads` 한 번만 호출해 기존 키/상태/종료 코드를 확인한다. stderr의 다음 `doctor --plan`, `run[-session]`, `report`와 HTML/index 경로, 정적 검사·model probe 구별을 검증한다. 모델 API는 patch하고 실제 호출하지 않는다.

```python
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    code = main(["run", str(plan)])
row = json.loads(out.getvalue())
self.assertEqual(code, 0)
self.assertEqual(row["report_html"], str(Path(row["run_dir"]) / "report.html"))
self.assertIn("agent-opt report", err.getvalue())
```

- [ ] **Step 2: 실패 확인.** `test_cli_experience.py`/`test_locale.py`를 실행한다.
- [ ] **Step 3: 최소 구현.** `show()`를 한 번만 호출하고 추가 한/영 명령·HTML 안내는 stderr에 출력한다. `init`의 TTY/비대화형 두 경로, `run-session`의 `index_html`, `report` 기본/`--html`/`--csv`, TUI 1/2와 전용 ACE launcher의 기존 출력을 각각 점검한다. `plan`은 정적 상태임을 설명하고 `doctor`의 `--model` 실제 probe만 별도로 표현한다. 원래 summary/report JSON 구조와 종료 코드는 수정하지 않는다.

```python
show({"run_dir": root, "status": summary["status"],
      "trials_used": summary["trials_used"], "report_html": root / "report.html"})
print(f"{human('다음')}: agent-opt report {shlex.quote(str(root))}", file=sys.stderr)
```

- [ ] **Step 4: 통과 확인.** 위 회귀 + `test_installed_cli.py`의 기존 JSON 소비 방식 점검.
- [ ] **Step 5: 커밋.** `git add src/agent_optimizer/cli.py src/agent_optimizer/locale.py tests/test_cli_experience.py tests/test_locale.py && git commit -m 'CLI 결과 경로와 진단 범위 안내'`.

### Task 5: 흐름 확인과 사용자 문서

**Files:**
- Modify: `README.md`, `website/src/content/docs/getting-started/first-run.md`, `website/src/content/docs/getting-started/results.md`, `website/src/content/docs/guides/experiment.md`

**Interfaces:**
- Consumes: Tasks 1–4 실제 출력과 출력 키.
- Produces: 첫 실행/결과 의미 및 명시적 데이터셋 선택 안내, 링크 검증.

- [ ] **Step 1: 네 흐름의 기대 출력 표 작성.** `make setup-core`/`make doctor-core`, 사용자 `init`/`doctor --plan`/`run`/`report`, 등록 팀 fixture, 준비 없는 ACE `doctor --dataset cvdp`/`make smoke`를 직접 재확인하고 HTML 실제 파일을 확인한다.
- [ ] **Step 2: 문서 수정.** README의 첫 실행 결과와 CLI/TUI 후속 명령을 코드대로 반영하고 세 웹 가이드에는 선택 의존성·정적 검사·합성 fixture·실행 근거의 차이와 실패 후 한 단계만 명시한다. 긴 개발 옵션 설명은 `docs/development.md`로 링크한다.

```markdown
`doctor --plan`의 ready는 선언과 준비 자산의 정적 진단입니다. `run`의 `report_html`을 열고
`summary.json`의 synthetic/status 및 실제 평가 기록을 확인하세요.
```

- [ ] **Step 3: 검증.** `make lint`, `make test`, `make demo`, `git diff --check`; `website/`에서 `npm ci && npm run build`. 모델/공식 채점 미실행을 기록한다.
- [ ] **Step 4: 커밋.** `git add README.md website/src/content/docs/getting-started/first-run.md website/src/content/docs/getting-started/results.md website/src/content/docs/guides/experiment.md && git commit -m '첫 실행과 결과 해석 안내 정리'`.
