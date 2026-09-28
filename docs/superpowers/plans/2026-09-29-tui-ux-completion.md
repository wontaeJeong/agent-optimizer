# Textual TUI UX 완성 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Home부터 결과까지 기존 Textual TUI에서 선택·설정·준비·진단·실행 상태를 단계적으로 이해하고 안전하게 완료할 수 있게 한다.

**Architecture:** 기존 `OptimizerApp` 상태 흐름과 preset/readiness/runner callback을 유지한다. model default는 공통 상수로 사용하고 진행 상태/이벤트 해석은 `terminal_report.py`의 작은 공유 helper에 둬 CLI와 TUI가 재사용한다. 화면만 단계별로 정리하며 CLI 명령 contract와 runner event schema는 변경하지 않는다.

**Tech Stack:** Python 3.11+, Textual 6–7, Rich `RichLog`, `unittest`, existing PTY installed-wheel harness, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-29-tui-ux-completion-design.md`

## Global Constraints

- `contracts.py`를 공통 계약으로 사용하고 Runner/event schema 및 callback signature를 보존한다.
- CLI command/JSON/stdout/stderr contract를 보존한다.
- credentials는 환경과 앱 세션에서만 사용하고 파일에 기록하지 않으며 모든 TUI 텍스트/오류/debug에서 마스킹한다.
- `collect_plan`/`render_diagnostic`/`prepare_selection`/`prepare_ace_selection`/`ProgressDisplay` 등 기존 기능을 재사용한다.
- 새 UI framework, config/profile system, credential store, TUI 전용 runner/doctor, generic form engine을 추가하지 않는다.
- 한국어/영어 UI와 50x20 terminal 사용성을 유지한다.
- `max_trials`는 예정 task 수가 아니라 최대 trial budget으로 표시하며 근거 없는 ETA를 추가하지 않는다.

---

### Task 1: 공통 모델 기본값과 진행 상태 정규화

**Files:**
- Modify: `src/agent_optimizer/models.py`
- Modify: `src/agent_optimizer/model_input.py`
- Modify: `src/agent_optimizer/terminal_report.py`
- Test: `tests/test_models.py`
- Test: `tests/test_model_input.py`
- Test: `tests/test_progress.py`

**Interfaces:**
- `models.DEFAULT_MODEL_ID: str`는 유일한 `AGENT_OPT_MODEL_ID` 기본값이다.
- `terminal_report.ProgressState(max_trials: int | None = None)`는 `configure_budget(max_trials)`와 `update(event: dict) -> bool`를 제공한다. `completed`, `max_trials`, `remaining`, `stage`, `task`, `phase`, `iteration`, `total`을 보유하고 `trial_completed`에서 완료 수를 증가시킨다.
- `terminal_report.format_progress_event(event: dict, *, humanize: bool = False) -> str | None`은 지원하는 중요 이벤트만 기존 CLI 또는 TUI용 설명으로 반환한다. 모르는/비표시 이벤트는 `None`이다.
- `ProgressDisplay`는 기존 출력 형식과 JSON/stdout 분리를 유지하면서 같은 `ProgressState`/formatter를 사용한다.

- [x] **Step 1: 기본값 공유 회귀 테스트 작성.** `test_models.py`에 명시적인 model ID가 없을 때 `DEFAULT_MODEL_ID`를 사용하는 검사, `test_model_input.py`에 `ensure_model_api`가 기본 ID를 사용하는 검사를 추가한다.
- [x] **Step 2: 회귀 테스트 실행.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_models.py -v`와 `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_model_input.py -v`를 실행해 새 기대가 먼저 실패하는지 확인한다.
- [x] **Step 3: 공통 상수 적용.** `models.py`에 `DEFAULT_MODEL_ID = "glm5.3-flash"`를 정의해 EnvironmentSettings와 explicit mapping이 사용하게 하고 `model_input.py`의 prompt fallback도 이를 참조하게 한다.
- [x] **Step 4: 진행 정규화 테스트 작성.** `test_progress.py`에서 공유 state의 event 누적/완료 budget/iteration·task/phase와 중요 event만 출력하는 formatter를 검증한다.
- [x] **Step 5: 진행 helper 구현.** `ProgressState`와 `format_progress_event`를 `terminal_report.py`에 추가하고 `ProgressDisplay`가 기존 완료 수/remaining 의미를 유지하면서 이를 사용하게 한다.
- [x] **Step 6: task 검증.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_progress.py -v`와 모델 테스트 두 개를 실행한다. 기존 CLI progress assertions도 그대로 통과해야 한다.

### Task 2: Home-first navigation과 구조화된 선택 설명

**Files:**
- Modify: `src/agent_optimizer/tui.py`
- Modify: `src/agent_optimizer/preset_tui.py`
- Test: `tests/test_textual_tui.py`

**Interfaces:**
- `OptimizerApp.on_mount()`은 `_show("Home")`으로 시작한다.
- Home은 5개 행(New Optimization, Existing Experiment, Run History, Advanced Setup, Quit)을 제공한다. 새 wizard의 첫 선택은 Agent이며 기존 ACE workspace shortcut은 별도 Home 행 없이 네 선택 wizard로 통합한다.
- `_detail(index)`은 선택 row의 구조화 정보/비호환 reason/remedy/alternative를 표시하고 highlight에서 갱신된다.
- breadcrumb는 현재 flow/page와 선택한 component id만 표시하고 긴 환경 설정은 표시하지 않는다.

- [x] **Step 1: Home/navigation 테스트 작성.** 앱 첫 화면 Home, New Optimization → Agent, Agent부터 각 단계 Esc back, 이전 선택/포커스 유지, Home의 다섯 메뉴를 실제 Pilot 키 입력으로 확인한다.
- [x] **Step 2: 테스트 실행.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_textual_tui.py -v`에서 기존 Agent-first 기대와 새 테스트가 실패하는지 확인한다.
- [x] **Step 3: Home-first 구현.** 초기 page를 Home으로 변경하고 New Optimization 행이 selection state를 초기화한 뒤 Agent로 이동하도록 한다. Home의 기존 ACE shortcut 진입은 제거하고 ACE는 일반 선택 경로에서 유지한다.
- [x] **Step 4: detail 회귀 테스트 작성.** 두 항목 highlight에 따라 detail이 달라지고, disabled optimizer/harness에 “Why unavailable”과 “Try instead” 의미의 설명이 포함되며 Enter가 화면을 무반응으로 남기지 않는지 테스트한다.
- [x] **Step 5: detail/navigation 구현.** 선택 설명의 redundant available 문구를 줄이고 agent/harness/optimizer/dataset별 수정 대상·필요 조건·실행/평가 방식·다음 단계를 표시한다. incompatible row의 기존 disabled 원칙은 보존하고 원인과 기존 실험/Advanced/호환 preset 대안을 보여준다. `Esc`를 단계별 직전 화면으로 정리한다.
- [x] **Step 6: task 검증.** `test_textual_tui.py`와 `tests/test_preset_tui.py`를 실행한다. Home/Esc/choice invalidation 관련 기존 Pilot 테스트도 통과해야 한다.

### Task 3: Model Setup 선택 UI와 Review 계층화

**Files:**
- Modify: `src/agent_optimizer/tui.py`
- Modify: `src/agent_optimizer/locale.py`
- Test: `tests/test_textual_tui.py`
- Test: `tests/test_model_input.py`

**Interfaces:**
- 기존 `OptimizerApp._missing_model_fields()`의 선택/환경변수 요구 사항은 유지하되 Model 화면은 variable-by-variable 빈 Input이 아니라 source/Custom 선택과 필요 시 Input을 제공한다.
- 화면에 보이는 source label은 `environment`, `project profile`, `default`, `session`에 대응하는 번역 문구다. 현재 정의되지 않은 project profile이나 endpoint/model을 합성하지 않는다.
- Review는 Selection, Model, Budget, Preparation/external calls, Output 영역과 `Edit Model Settings` 진입을 제공한다.

- [x] **Step 1: 모델 화면 회귀 테스트 작성.** 환경 URL/selector/key 자동 인식, model ID default source, environment → Custom 선택, custom 값 저장/재진입, Review Edit, 모델이 필요 없는 fixture, API key mask, 다음 non-secret Input의 password reset, Back 후 값 유지, `.env` 미자동 로드 및 secret 미노출을 Pilot 테스트에 추가한다.
- [x] **Step 2: 테스트 실행.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_textual_tui.py -v`와 `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_model_input.py -v`를 실행해 새 UX 테스트의 실패를 확인한다.
- [x] **Step 3: model picker 구현.** existing env 값과 `DEFAULT_MODEL_ID`만 실제 선택지로 제공한다. Base URL은 현 environment 또는 Custom, model selector는 현 environment 또는 Custom, `AGENT_OPT_MODEL_ID`는 environment/default/Custom을 제공한다. API key/token은 configured 표시 또는 masked custom Input만 사용한다.
- [x] **Step 4: session/back/focus 구현.** model value와 출처를 앱 수명 안에서만 보존한다. Review Edit 진입은 값을 불러오고 Custom 확정은 필요한 변수만 덮어쓴다. `_show` 시작 시 `Input.password = False`를 명시한 뒤 secret Input에 한해서만 True로 설정한다.
- [x] **Step 5: Review와 localization 구현.** Review를 제목/구획별 텍스트로 렌더링하고 model/agent model/endpoint/key configured source, budget/timeout, edit target, preparation/download/build, external model call, output report를 표시한다. key value는 출력하지 않는다. 모든 신규 문구를 ko/en으로 추가한다.
- [x] **Step 6: task 검증.** Textual/model-input 관련 테스트를 실행하고 `tests/test_models.py`를 재실행해 model ID default 일관성을 확인한다.

### Task 4: 사용자에게 보이는 Preparing과 정식 Doctor

**Files:**
- Modify: `src/agent_optimizer/tui.py`
- Modify: `src/agent_optimizer/preset_tui.py` (필요한 경우 기존 준비 함수에 progress stream만 연결)
- Modify: `src/agent_optimizer/locale.py`
- Test: `tests/test_textual_tui.py`

**Interfaces:**
- Review 확정은 Preparing으로 이동한다. 기존 config는 자산 준비를 자동 실행하지 않고 그 사실을 표시한다.
- 신규 preset 준비는 기존 `prepare_selection`/`prepare_ace_selection`을 사용하고 output/status를 사용자에게 전달한다.
- Doctor worker는 `collect_plan(experiment, Registry(), model=needs_model_probe)`를 사용한다. 성공/실패/blocked는 기존 row contract로 표시한다.
- Doctor failed/blocked는 Retry checks 또는 Back to Review만 제공한다. ready면 Run Optimization과 Back to Review를 제공한다.

- [x] **Step 1: Doctor 차단 테스트 작성.** static readiness failure, blocked row 및 remedy 표시, model probe failure, 실패 후 retry, 각 실패에서 `run_experiment` 호출 0회를 검증한다.
- [x] **Step 2: 테스트 실행.** `test_textual_tui.py`를 실행해 새 Doctor 단계/차단 test가 실패하는지 확인한다.
- [x] **Step 3: Preparing 테스트 작성.** preparation stream event가 화면에 누적되고, 기존 experiment에서는 준비가 생략되며, 준비 오류가 발생하면 Doctor/run을 시작하지 않고 실패 단계와 reason을 보이는지 검증한다.
- [x] **Step 4: Preparing 화면 구현.** 선택형 ACE와 dataset 준비에 기존 preparation status/output stream을 연결해 단계 출력과 실패 위치를 보인다. 완료 후 `Continue to Doctor`를 명시적으로 제공하고, 기존 experiment는 자동 자산 준비가 생략됐음을 표시한 뒤 같은 버튼으로 진단에 이어간다. 준비 실패 시 Preparing에 머물고 Retry Preparation과 Back to Review만 제공한다.
- [x] **Step 5: Doctor 테스트/구현.** static readiness success/failure/blocked row, remedy, model probe failure, retry/back과 실패 시 runner 호출 0회를 검증한다. 테스트를 먼저 작성해 실패를 확인한 뒤 `collect_plan` 결과의 원래 id/area/status/message/remedy와 상태 symbol/text/color를 표시한다. 검사가 진행 중이면 indeterminate activity를 보여준다.
- [x] **Step 6: model probe gating 테스트/구현.** 모델 필요/불필요 실험 각각에서 probe 호출 여부를 먼저 검증한다. 필요한 실행에서만 `model=True`로 호출하고 실제 외부 API 요청임을 알린다. 성공은 probe 연결성만 증명한다고 표시한다.
- [x] **Step 7: 명시적 실행 선택 구현.** Doctor가 ready일 때에만 Run Optimization을 활성화하고, Enter 전까지 `run_experiment`/dedicated launcher를 호출하지 않는다. Retry는 준비 단계를 다시 실행하지 않고 Doctor만 재수행한다.
- [x] **Step 8: task 검증.** 관련 Textual 테스트를 실행하고 readiness report의 machine field/schema가 바뀌지 않았음을 `tests/test_cli_experience.py` focused tests로 확인한다.

### Task 5: Running dashboard, secret-safe error, Result 화면

**Files:**
- Modify: `src/agent_optimizer/tui.py`
- Modify: `src/agent_optimizer/terminal_report.py` (Task 1 shared helper only if integration tests require a narrow correction)
- Test: `tests/test_textual_tui.py`
- Test: `tests/test_progress.py`

**Interfaces:**
- Running consumes existing runner event callback and updates the Task 1 `ProgressState`.
- Running event panel is append-oriented and capped at 300 lines; current state uses a separate widget so log appends do not overwrite it.
- `_finish` transitions to Result, which accepts a status, trials_used, run directory, artifact paths, and safe failure details; it does not expose full traceback by default.
- `OptimizerApp._redact_secrets(text: object) -> str` replaces nonempty values from environment/session variables whose names indicate key/token/secret/password before rendering notifications, details, events, exception text, or debug traceback.

- [x] **Step 1: dashboard test 작성.** test callback with multiple known events; assert append history remains, latest stage/task/phase and iteration update, `completed / maximum` budget wording is accurate, elapsed updates, no ETA/planned total appears, and error event is visible.
- [x] **Step 2: error/result/secret tests 작성.** Assert completed/failed Result separates from Running and shows report/run/artifact paths; force exceptions containing a session secret and assert it is absent from all visible widgets/notification/debug output.
- [x] **Step 3: 테스트 실행.** Textual test module에서 dashboard/result/redaction tests가 우선 실패하는지 확인한다.
- [x] **Step 4: Running widget 구현.** Context7 library lookup was attempted but the service reported its monthly quota was exceeded. The installed Textual runtime was inspected directly: `RichLog` accepts `max_lines`, `min_width`, `wrap`, `highlight`, `markup`, and `auto_scroll`, and provides `write`, `scroll_end`, and `is_vertical_scroll_end`. `RichLog(max_lines=300, min_width=1, wrap=True, highlight=False, auto_scroll=False)` is used with a separate state panel and elapsed timer. Known events are formatted through `format_progress_event`; auto-scroll occurs only when the user was already at the bottom.
- [x] **Step 5: Result와 오류 구현.** 성공/partial/failure 상태, 완료 trial 수/최대 budget, run directory, 실제 존재하는 report/summary/events/markdown 경로를 표시한다. `run_root`와 exception diagnostic은 redaction 후 요약해 표시하고 redacted traceback은 Textual log로만 남긴다.
- [x] **Step 6: 안전한 종료 구현.** worker가 Preparing/Doctor/Running 동안 `Esc`/`q`로 종료되지 않게 하고 알림을 띄운다. idle Result는 예측 가능한 Esc/q navigation을 사용한다.
- [x] **Step 7: 좁은 화면/상태 테스트.** 50x20 및 50x24에서 focus 이동, Doctor/Review/log scrolling과 현재 핵심 상태 노출을 검증하고 언어별 Running/Result labels를 확인한다.
- [x] **Step 8: task 검증.** `test_textual_tui.py` 및 `test_progress.py`를 실행한다. 기존 CLI `ProgressDisplay` output assertions와 event dict serialization은 변경하지 않는다.

### Task 6: README/가이드, 실제 설치 PTY 및 화면 근거

**Files:**
- Modify: `README.md`
- Modify: `docs/development.md`
- Modify: `examples/ace-rtl/README.md`
- Modify: `website/src/content/docs/getting-started/presets.md`
- Modify: `website/src/content/docs/guides/experiment.md`
- Modify: `website/src/content/docs/concepts/overview.md`
- Modify: `website/src/content/docs/getting-started/first-run.md`
- Modify: `tests/test_installed_cli.py`
- Modify: `docs/verification.md`
- Create: `scripts/capture_tui_ux.py`
- Use: `docs/assets/tui-after.svg` (the pre-change Agent-first Textual capture on `origin/main`)
- Create: `docs/assets/tui-ux-home.svg`
- Create: `docs/assets/tui-ux-selection.svg`
- Create: `docs/assets/tui-ux-model.svg`
- Create: `docs/assets/tui-ux-review.svg`
- Create: `docs/assets/tui-ux-preparing.svg`
- Create: `docs/assets/tui-ux-doctor.svg`
- Create: `docs/assets/tui-ux-doctor-blocked.svg`
- Create: `docs/assets/tui-ux-running.svg`
- Create: `docs/assets/tui-ux-result.svg`
- Create: `docs/assets/tui-ux-result-failed.svg`

**Interfaces:**
- README와 개발 가이드는 새 Home-first 흐름, 단계, Esc/Enter/q, TUI와 static/model Doctor의 차이를 설명한다.
- 설치형 테스트는 실제 `agent-opt tui` PTY에서 Home-first, 선택/Review/Model/Doctor 선택, safe quit을 키 입력으로 확인하며 외부 network/Docker는 모의하거나 실행하지 않는다.
- 설치형 TUI는 실제 PTY output으로 검증한다. SVG 화면 캡처는 Textual compositor의 실제 rendered screen에서 export하며, 사용한 합성 model/readiness/event fixture를 명시한다.

- [x] **Step 1: PTY test flow 작성/수정.** `test_installed_cli.py`의 첫 화면 ACE-RTL 기대와 Escape로 Home에 가는 조작을 Home-first sequence로 바꾸고, 새 선택 wizard에 진입한 뒤 취소 시 파일/자산이 생성되지 않는지 확인한다. 필요한 경우 설치 wheel의 기존 temporary workspace에 fixture experiment를 추가한다.
- [x] **Step 2: 설치형 PTY 검증.** `.venv/bin/python -m build --wheel`로 wheel을 만들고 `PYTHONPATH=src .venv/bin/python tests/test_installed_cli.py dist/agent_optimizer-0.3.0-py3-none-any.whl`을 실행해 설치 환경의 키 조작과 rendered markers를 검증한다. 외부 model/API call이 포함된 run은 실행하지 않는다.
- [x] **Step 3: 문서 갱신.** README, `docs/development.md`, ACE 예제 README와 TUI를 직접 설명하는 website 네 문서에서 Agent-first/Esc-home/기존 ACE shortcut 설명을 새 Home-first 흐름으로 교체한다. Home→wizard→Review→Preparing→Doctor→Running→Result, 기존 config의 준비 정책 및 keyboard 동작을 설명한다.
- [x] **Step 4: 실제 화면 근거 기록.** 변경 전 화면은 `origin/main`에 보존된 실제 Agent-first Textual PTY 캡처 `docs/assets/tui-after.svg`를 사용한다. `PYTHONPATH=src:tests .venv/bin/python scripts/capture_tui_ux.py`로 100x30 Textual compositor의 Home, selection, Model Setup, Review, Preparing, Doctor ready/blocked, Running, Result completed/failed SVG를 생성한다. 설치형 `agent-opt tui`는 실제 PTY에서 50x20으로 key-driven 실행하며 `docs/verification.md`에 command, terminal size, screenshot source, synthetic/mock 범위, API/Docker 미검증 범위를 기록한다.
- [x] **Step 5: 문서/PTy 검사.** installed PTY test와 `website/`의 build/link 검사를 실행하고 README/가이드 키 동작 설명 및 `git diff --check`를 확인한다.

### Task 7: 전체 회귀 검증 및 PR 준비

**Files:**
- Verify: Task 1–6 changes
- Update: `docs/verification.md` 실제 검증 결과

- [x] **Step 1: focused test set.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_textual_tui.py -v`, `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_progress.py -v`, `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_model_input.py -v`, `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_models.py -v`, `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -v`를 실행했다. 최종 TUI 보안 회귀를 포함한 결과는 34/34, 23/23, 3/3, 10/10, 134건 중 104 통과·30 skip이다. 설치 PTY는 Task 6 wheel script로 수정 이후 다시 검증했다.
- [x] **Step 2: 전체 테스트.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`는 906건 중 827 통과·79 skip·실패 0으로 완료했다.
- [x] **Step 3: 합성 demo와 Ruff.** `PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml`은 synthetic `completed`/7 trial이고, `make lint`도 통과했다.
- [ ] **Step 4: 최종 diff 검사.** `git diff --check`, `git status --short --branch`, `git diff`를 확인한다. 모델 API 및 ACE Docker 자산이 준비되지 않으면 실환경 connectivity/optimization 검증은 미실행이라고 기록한다.
- [ ] **Step 5: PR 준비.** 최근 commit, branch upstream, base diff, status와 실제 캡처를 확인하고 한국어 PR 본문에 UX before/after 캡처와 재현 방법, Architecture changes, Reused components, Tests, Remaining limitations를 정리한다. PR 생성 후 merge는 별도 승인이 있을 때만 한다.
