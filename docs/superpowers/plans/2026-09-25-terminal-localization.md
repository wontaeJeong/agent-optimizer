# 터미널·리포트 한영 지원 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 이 저장소는 명시적인 사용자 요청이 없는 한 에이전트를 위임하지 않으므로 현재 세션에서 직접 실행한다.

**목표:** 개발 명령부터 CLI/TUI·리포트까지 한국어를 기본으로 하고 `AGENT_OPT_LANG=en`을 선택할 수 있게 한다.

**구조:** Python의 한 모듈에서 언어 결정과 고정 문구를 담당한다. Python 실행 전 셸의 자체 문구는 같은 환경 변수 규칙을 직접 처리한다. 실행 데이터의 코드/영문 원문은 유지하고 출력 경계와 HTML/Markdown 생성 단계에서만 번역한다.

**기술:** Python 3.11+, Typer 0.27, Rich 14, POSIX sh, unittest, Ruff.

**설계:** `docs/superpowers/specs/2026-09-25-terminal-localization-design.md`

## 전체 제약

- `AGENT_OPT_LANG`는 빈 값/미설정/`ko`일 때 한국어, `en`일 때 영어; 그 밖의 값은 실행 전 오류. OS `LANG`와 CLI 플래그를 사용하지 않는다.
- JSON/JSONL/CSV 키·상태·진단 원문, ID, 평가 근거, 자격증명과 외부 도구 출력은 그대로 둔다.
- 한국어 도움말과 한글 HTML의 기존 내용·링크·보안 이스케이프를 유지한다.
- 실행 언어는 `summary.json`의 `report_language`에 저장한다. 재생성 시 명시적 환경 값만 한 번 덮어쓰며 저장한 언어는 유지한다.
- 이전 실행은 기존 `report.html`의 `html lang`을 우선 감지하고 미확정이면 영어로 재생성한다.
- 저장소 `.env`는 기본 워크트리에만 있으므로 검증 프로세스에서만 읽어 사용하고 값/토큰을 출력하거나 커밋하지 않는다.

## 파일 책임

- `src/agent_optimizer/locale.py`: 환경 선택, 고정 문구 카탈로그, 안전한 형식화 및 보고서 언어 결정.
- `scripts/bootstrap.sh`: Python 부재 상태의 안내/검증/진행 문구 선택.
- `src/agent_optimizer/{cli,korean_help,terminal_style,setup_wizard,terminal_report}.py`: 사용자 도움말·질문·진행·오류 표시.
- `scripts/{dev,dev_doctor,menu}.py` 및 `examples/ace-rtl/environment/*.py`: 저장소 소유 개발·예제 문구 표시. 내부 JSON 진단은 유지.
- `src/agent_optimizer/{runner,results,html_report}.py`: 실행 언어 기록, Markdown/HTML 현지화, 재생성.
- `tests/{test_locale,test_cli_experience,test_dev_onboarding,test_html_report,test_results}.py`: 기본/영어/재생성/기계 출력/예외 경로.

---

### Task 1: 언어 결정과 Python 없는 개발 진입점

**파일:** 새 `src/agent_optimizer/locale.py`, 새 `tests/test_locale.py`; 수정 `scripts/bootstrap.sh`, `tests/test_dev_onboarding.py`.

**인터페이스:** `current_language(raw: str | None = None) -> str`, `t(key: str, *, lang: str | None = None, **values: object) -> str`를 후속 작업에 제공한다. 빈 환경 변수는 `ko`; 보고서의 별도 기록 해석은 Task 4가 담당한다.

- [ ] **Step 1: 실패 테스트 작성.** `patch.dict(os.environ, {'AGENT_OPT_LANG':'en'})`에서 `current_language() == 'en'`, 미설정·빈 값은 `ko`, `ja`는 `ValueError`인지 검사한다. `subprocess.run(['sh','scripts/bootstrap.sh','help'], env={...})`에서 `en`은 `Development commands`, 기본은 `개발 명령`, `ja`는 종료 코드 2이고 설치 파일을 만들지 않는지 검사한다.
- [ ] **Step 2: 실패 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_locale.py -v` 및 `-p test_dev_onboarding.py -k language -v`: 신규 기능 부재로 실패해야 한다.
- [ ] **Step 3: 최소 구현.** 다음 인터페이스를 구현하고 고정 문구는 키마다 한국어/영어 쌍으로 둔다. 셸은 스크립트의 명령 분기 전에 언어를 검증하고 자체 문구를 `case "$AGENT_OPT_LANG" in en) ... ;; *) ... ;; esac`로 선택한다. JSON을 출력하는 경로에는 진단 원문을 사용한다.

```python
def current_language(raw: str | None = None) -> str:
    selected = os.environ.get('AGENT_OPT_LANG', '') if raw is None else raw
    if selected in ('', 'ko'):
        return 'ko'
    if selected == 'en':
        return 'en'
    raise ValueError('AGENT_OPT_LANG must be ko or en')

def t(key: str, *, lang: str | None = None, **values: object) -> str:
    ko, en = MESSAGES[key]
    return (en if (lang or current_language()) == 'en' else ko).format(**values)
```

- [ ] **Step 4: 통과 확인.** Task 1 테스트와 기존 `make help`, `AGENT_OPT_LANG=en make help`, `AGENT_OPT_LANG=ja make help`를 확인한다.
- [ ] **Step 5: 이 작업 파일만 커밋.** 메시지 `한국어 기본 터미널 언어 선택과 셸 진입점 지원`.

### Task 2: 사용자 CLI/TUI·개발 명령의 안내/오류

**파일:** 수정 `src/agent_optimizer/{cli,korean_help,terminal_style,setup_wizard,terminal_report}.py`, `scripts/{dev,dev_doctor,menu}.py`, 저장소 소유 `examples/ace-rtl/environment/*.py` 중 화면 출력 파일, `tests/{test_cli_experience,test_dev_onboarding,test_menu}.py`.

**인터페이스:** Task 1의 `current_language()`/`t()` 사용. `localize_click_help(command: click.Command) -> None`는 현재 실행용 명령 객체의 고정 도움말만 재귀적으로 바꾼다. Typer의 명령·옵션 이름은 그대로 두고 help/epilog/docstring을 렌더 시에만 선택한다. `show()`로 출력하는 JSON과 `doctor --json`은 손대지 않는다.

- [ ] **Step 1: 실패 테스트 작성.** 기본 `main(['--help'])`에서 한국어 설명, `AGENT_OPT_LANG=en`에서 영어 설명과 `Usage:`, `main(['tui'])`의 TTY 오류 한영, 개발 `scripts/dev.py --help` 및 번호 메뉴의 영어 안내를 검증한다. 같은 진단 입력의 `--json`과 이벤트 저장 결과가 두 언어에서 같고 `error`·`status` 코드가 영어인지 검증한다. `AGENT_OPT_LANG=ja`에서는 명령 실행 전 종료 코드 2를 확인한다.
- [ ] **Step 2: 실패 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -k language -v` 및 개발 환경/메뉴 언어 테스트를 실행한다.
- [ ] **Step 3: 최소 구현.** Typer `app`에서 만들어진 Click 명령 객체의 `help`/`epilog`/option `help`를 실행 시 `t()`로 설정하여 import 이후 환경 변경도 반영한다. `localize_click_help`는 `command.help`, `command.epilog`, 각 `param.help`, `command.commands.values()`에 재귀 적용하며 카탈로그에 있는 문자열만 변환한다. `KoreanArgumentParser`는 한국어일 때만 제목·`사용법:`을 적용한다. CLI, TUI, 메뉴, 진행·준비 표시, 개발 진행·진단 출력과 자체 예제 오류를 문구 키로 전환한다. 코드·메트릭·가변 경로는 `.format()` 인자로만 삽입한다. JSON의 `message`/`remedy`는 기존 문자열 그대로 둔다.

```python
command = typer.main.get_command(app)
if current_language() == 'en':
    localize_click_help(command)  # 명령과 하위 명령의 help/epilog/parameter help만 변환
return command.main(args=argv, prog_name='agent-opt', standalone_mode=False) or 0
```

- [ ] **Step 4: 통과 확인.** 변경한 CLI/개발/메뉴 테스트를 실행하고 영어 출력에 한국어로 고정된 사용자 문구가 남지 않았는지 실제 `--help`, `doctor --core`, `datasets list`로 점검한다.
- [ ] **Step 5: 이 작업 파일만 커밋.** 메시지 `CLI와 개발 명령의 안내 및 진행 문구 한영 지원`.

### Task 3: 진단·오류 표시의 원문 보존

**파일:** 수정 `src/agent_optimizer/{locale,cli,readiness}.py`, `scripts/{dev,dev_doctor}.py`, `tests/{test_cli_experience,test_dev_doctor}.py`.

**인터페이스:** `render_diagnostic(check: dict, lang: str) -> tuple[str, str]`는 사람용 문구만 반환한다. 예상 가능한 프로젝트 오류는 출력 지점의 문구 키를 `t()`로 출력하고, 나머지 예외는 `str(error)`를 유지한다. 저장된 `check`·exception·원문 로그를 수정하지 않는다.

- [ ] **Step 1: 실패 테스트 작성.** 같은 실패 진단을 `--json`으로 출력한 결과를 두 언어에서 동등 비교하고, 일반 출력에서는 `Remedy:`/`해결:` 및 알려진 `check['id']` 문구가 바뀌는지 확인한다. 외부 원문 문자열에 `<`/영어 메시지가 들어간 경우 누락·임의 치환되지 않는지 검사한다.
- [ ] **Step 2: 실패 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_dev_doctor.py -k language -v`와 CLI 언어 진단 테스트 실행.
- [ ] **Step 3: 최소 구현.** 고정 진단은 기존 `id`로 현지화된 안내를 선택하되 수집·JSON의 영문 원문을 유지한다. CLI가 직접 생성하는 설정 오류와 개발 명령의 자체 접두어·수리 안내를 렌더 경계에서 번역한다. 알 수 없는 외부 오류는 `str(error)` 그대로 붙인다.

```python
message, remedy = render_diagnostic(check, current_language())
print(f"[{check['status']}] {check['id']}: {message}")
if remedy:
    print(f"  {t('remedy')}: {remedy}")
```

- [ ] **Step 4: 통과 확인.** 진단 테스트 및 기존 `doctor --core --json`의 stdout 단일 JSON·ANSI 없음·영문 원문 유지를 확인한다.
- [ ] **Step 5: 이 작업 파일만 커밋.** 메시지 `진단의 기계 원문과 사람이 읽는 번역 분리`.

### Task 4: 보고서 언어 기록 및 Markdown

**파일:** 수정 `src/agent_optimizer/{locale,runner,results,cli}.py`, `tests/{test_results,test_html_report,test_run_lifecycle}.py`.

**인터페이스:** `report_language(summary: dict, root: Path, *, override: str | None = None) -> str`; `write_report(..., language: str | None = None)`·`write_report_artifacts(..., language: str | None = None)`. `override`는 이번 출력에만 적용하며 기록 변경을 금한다. 기존 direct 호출은 기본 한국어, CLI의 레거시 재생성은 파일의 `html lang`을 검출한다.

- [ ] **Step 1: 실패 테스트 작성.** 영어 환경에서 fixture를 실행해 `summary.json['report_language'] == 'en'`, `report.md` 제목 영어, 원본 이벤트·평가·메트릭 동일을 확인한다. 기본 환경의 한국어 보고서, 레거시 영어/한국어 HTML 감지, 영어 실행의 기본 재생성 및 명시적 `AGENT_OPT_LANG=ko`의 일회성 재생성과 기록 불변을 테스트한다.
- [ ] **Step 2: 실패 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_results.py -v` 및 `-p test_html_report.py -k language -v`.
- [ ] **Step 3: 최소 구현.** 실행 `summary` 생성 때 `current_language()`를 기록하고 실패·중단에도 보존한다. 기존 HTML의 선두 1KB 이내 `<html lang="ko">`/`<html lang="en">`만 인식하며 그 밖은 `en`으로 둔다. `results.py`의 정적 제목·설명·상태 표시만 번역하고 표 셀의 상태/지표/JSON 블록 원문은 유지한다. `report --html`에서 명시적 비어 있지 않은 환경 변수를 override로 전달한다.

```python
summary = {'schema_version': 1, 'report_language': current_language(), 'status': 'running'}
language = report_language(data, args.run_dir,
    override=os.environ.get('AGENT_OPT_LANG') or None)
target = write_report_artifacts(args.run_dir, data, language=language)
```

- [ ] **Step 4: 통과 확인.** 결과·수명주기·CLI 재생성 테스트 및 `summary.json`/`report.json` 원문 불변을 확인한다.
- [ ] **Step 5: 이 작업 파일만 커밋.** 메시지 `실행 언어를 보존하고 Markdown 리포트 한영 제공`.

### Task 5: HTML/세션 보고서 한영·접근성

**파일:** 수정 `src/agent_optimizer/{html_report,cli}.py`, `tests/test_html_report.py`.

**인터페이스:** `write_html_report(root, summary, report=None, *, language=None)` 및 `write_session_index(root, entries, *, language=None)`; 기본 출력 언어는 새 실행의 `report_language`/현재 언어다. Task 4의 `write_report_artifacts`가 동일한 언어를 HTML에 전달한다.

- [ ] **Step 1: 실패 테스트 작성.** 영어 리포트·세션에서 `<html lang="en">`, 제목/탐색/설명/툴팁/상태/접근성 문구가 영어인지 확인한다. 기본 한국어 HTML 기존 검사를 유지한다. `<script>` 피드백과 악의적 데이터셋 이름은 두 언어 모두 HTML 이스케이프된 채 유지되어야 한다.
- [ ] **Step 2: 실패 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_html_report.py -k language -v`.
- [ ] **Step 3: 최소 구현.** `HELP`, `SPLITS`, `STATES`, `EVENTS` 등 고정 표시 사전을 한영으로 전환하고 `_term()`, `_display()`가 문구만 locale에 따라 선택하게 한다. 본문을 완성한 뒤 문자열 치환하지 말고 기존 `text()` 이스케이프 이전에 정적 캡션·네비게이션·툴팁을 선택한다. ID·링크·JSON 코드 블록은 변경하지 않는다. 세션의 실행 오류 상세는 원문 그대로 `text()`로 이스케이프한다.

```python
def _term(label, language):
    shown, explanation = TERMS[language].get(label, (label, None))
    return text(shown) if explanation is None else (
        f'<abbr class="help" title="{text(explanation)}" tabindex="0">{text(shown)}</abbr>')
```

- [ ] **Step 4: 통과 확인.** `tests/test_html_report.py` 전체, 두 언어로 생성된 HTML의 `lang`·링크·피드백 이스케이프를 검사한다.
- [ ] **Step 5: 이 작업 파일만 커밋.** 메시지 `HTML과 데이터셋 세션 리포트 한영 지원`.

### Task 6: 사용법, 전체 검증, UI 캡처

**파일:** 수정 `README.md`, `docs/development.md`; 생성 `docs/superpowers/` 아래의 언어별 UI 캡처(기존 PR 작성 규칙에 따라 위치 선택).

**인터페이스:** 새 옵션 없이 기존 사용법에 `AGENT_OPT_LANG=en` 예제만 추가한다. `.env`는 Git에 추가하지 않는다.

- [ ] **Step 1: 실패 테스트 작성.** 언어별 도움말·HTML·JSON 보존 통합 테스트에 문서 예제의 명령 형태를 그대로 사용한다. 기존 테스트가 커버하는 주제는 중복 테스트를 만들지 않는다.
- [ ] **Step 2: 실패 확인.** 통합 테스트의 영어 경로를 먼저 실행하여 누락 문구가 검출되는지 확인한다.
- [ ] **Step 3: 최소 변경.** README/개발 문서에 기본 한국어·영어 선택·기계 출력 고정·보고서 재생성을 적는다. `.env` 값은 출력하지 않고 검증 프로세스에서만 읽는다. `make help` 및 보고서 변경 전/후 화면을 동일한 폭에서 캡처한다.
- [ ] **Step 4: 검증.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`, `make lint`, `make demo`를 실행한다. 별도 `.env`를 읽은 자식 프로세스에서 모델 설정 읽기/계획 진단을 실행하되 출력은 상태와 종료 코드만 남기고 자격증명은 기록하지 않는다. 실제 모델 호출을 했다면 호출 범위와 결과를 별도로 구분한다.
- [ ] **Step 5: 변경 문서·캡처만 커밋.** 메시지 `한영 사용법과 실제 UI 검증 근거 정리`.

## 독립 회귀 처리

`tests/test_dev_onboarding.py`의 잠금 파일 테스트는 상위 프로세스의 `AGENT_OPT_MODEL_BASE_URL`이 남아 있는 상황에서 `AGENT_OPT_MODEL_ENDPOINT`를 모의 지정해 실패한다. 이 회귀는 다국어 기능과 독립이므로 `origin/main`에서 별도 워크트리를 만들어 환경 변수 격리 테스트를 먼저 실패 확인하고, 기존 `patch.dict(..., clear=True)` 패턴으로 테스트를 격리한다. 해당 브랜치에서 `.venv`를 준비해 단위 테스트/전체 테스트/린트를 확인하고 별도 PR로 제출한다. 최초 워크트리의 `.venv` 부재는 코드 수정 사유가 아니라 준비 명령으로 해결했다.
