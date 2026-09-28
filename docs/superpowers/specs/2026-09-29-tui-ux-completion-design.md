# Textual TUI UX 완성 설계

## 목표

기존 Textual 앱에서 사용자가 선택한 조합, 필요한 설정, 실행 가능 여부, 현재 진행 상황,
최종 결과를 앱 안에서 이해할 수 있도록 단계와 정보를 정리한다. 새로운 UI 프레임워크,
별도 router/state 시스템, TUI 전용 runner/doctor는 추가하지 않는다.

## 현행 동작과 확인된 문제

- `OptimizerApp`은 시작하자마자 Agent 선택을 보여주며 Home은 `Esc`로 접근한다.
- 프리셋 선택 설명은 한 문단과 반복적인 사용 가능 상태 중심이고, 비호환 사유/대안이 충분하지 않다.
- 모델이 누락된 경우 변수 이름별 빈 Input을 순서대로 보여준다. 기본 모델 ID는 `models.py`와
  `model_input.py`에 중복되어 있고, TUI는 이를 기본값으로 사용하지 않는다.
- 모델 Input 뒤 다른 Input에서 password 모드가 초기화되지 않을 수 있고 Model 화면의 `Esc`는
  세션 입력을 전부 삭제한다.
- Review는 줄바꿈 문자열이며, 준비·`collect_plan`·실행이 하나의 Running 상태에 포함된다.
- readiness는 `collect_plan`에 이미 구현되어 있고 `model=True`는 실제 model probe를 수행한다.
  CLI doctor는 정적 plan 확인과 `--model`의 실제 API 확인을 구분한다.
- 실행 이벤트는 Runner callback을 제공하지만 TUI는 한 `Static`을 덮어쓴다. CLI 진행 집계는
  `terminal_report.ProgressDisplay`에 있고 요청된 `progress.py` 파일은 없다.
- ACE asset 준비 출력을 TUI가 버린다. 실행 예외와 traceback도 TUI 표시/로그에서 credential을
  포함할 수 있다.

## 승인된 접근 방식

기존 단일 `OptimizerApp`을 유지하며 필요한 화면 상태와 작은 공통 진행 상태 helper를 추가한다.
개별 Page class/router로 분할하거나 overlay만 추가하는 방식은 택하지 않는다. 별도 Home의 ACE
바로가기는 없애고 `New Optimization`의 기존 ACE preset 선택에 통합한다.

## 사용자 흐름

초기 화면은 Home이며 메뉴는 `New Optimization`, `Existing Experiment`, `Run History`,
`Advanced Setup`, `Quit` 순이다. 새 실험은 Agent → Harness → Optimizer → Dataset → Model Setup →
Review → Preparing → Doctor → Running → Result 순으로 진행한다. 모델이 필요하지 않은 조합도
Model Setup에서 필요 없음을 명시한다. 기존 실험은 기존 설정을 자동으로 준비하거나 수정하지 않고,
Preparing에서 이를 알린 다음 readiness 검사로 간다.

`Esc`는 현재 사용자 단계의 직전 단계로 이동하며 선택과 session-only 모델 설정을 보존한다.
Review에서 모델 편집 경로를 제공한다. 실행/진단 worker가 동작 중일 때 `Esc`와 `q`는 종료하지
않고 실행 중임을 알린다. Review 이후에는 Prepare, Doctor, Running, Result가 각각 별도 상태로
표시된다.

## 선택 상세와 상태 표현

선택 화면 상세는 항목별 정보를 짧은 제목/값 구조로 렌더링한다. 가능한 필드는 수정 대상,
요구사항, task/split, 평가 방식, runtime/preparation, 다음 단계다. 항목 highlight만으로 설명이
갱신된다. 선택 불가 항목은 계속 dim/disabled 처리하고, highlight detail에 이유와 가능한 대안을
표시한다. `Available` 등 반복 상태 문구는 필요한 경우 외에는 제거한다.

화면 상태 표시는 symbol/text와 semantic color를 함께 사용하며, 내부 readiness/event status는
기존 값을 유지한다. readiness 행은 원본 `id`, `area`, `status`, `message`, `remedy`를 사용하고
`render_diagnostic`으로 기존 localization을 재사용한다.

## Model Setup과 Review

선택한 실험에서 요구하는 model variable만 안내한다. 우선순위는 실행 환경 값, 존재하는
비밀이 아닌 프로젝트 profile, 이미 정의된 앱 기본값, Custom이다. 현재 저장소에는 model profile이
없으며 `.env.example`은 자동 로드되지 않는다. 따라서 실제 환경 endpoint가 있으면 그 값만 제안하고,
없으면 endpoint를 임의로 채우지 않는다. 모델 ID 기본값 `glm5.3-flash`는 공통 상수로 이동해
`models.py`, `model_input.py`, TUI가 함께 사용한다. 모델 selector는 실존하는 환경 값이 있을 때만
기존 값을 선택지로 보이고, 별도 모델 목록이 정의되어 있지 않으면 Custom 입력으로 연결한다.

Base URL/selector는 선택 UI 이후 필요한 경우에만 Custom Input을 연다. API key/token은 이미
설정된 경우 configured/source만 표시하고, 누락된 경우 masked Input에서만 받는다. 자격증명은 앱
세션의 환경 overlay에만 보관하며 파일로 기록하지 않는다. Input mode 진입마다 password 상태를
명시적으로 설정한다. Review는 Selection, Model, Budget, Preparation/external calls, Output으로
구분하고 secret value 대신 출처/설정 여부만 노출한다. Model Setup에서 뒤로 가거나 Review에서
수정해도 session 값은 유지한다.

TUI의 사용자 표시 텍스트, event/error/debug, 알림에 credential redaction을 적용한다. 기본 화면은
전체 traceback 대신 요약 원인과 다음 행동을 보여주고 기술 세부는 보조 debug 영역에 둔다. debug
출력도 동일하게 redaction한다.

## Preparing과 Doctor

새 ACE 선택은 현재 `prepare_ace_selection`/lifecycle을, fixture dataset 준비는 기존
`prepare_selection` 경로를 사용한다. 현재 숨겨지는 preparation status/output은 TUI에 단계적으로
보이며 실패한 준비 단계를 식별한다. 준비가 끝나면 사용자가 `Continue to Doctor`를 선택해 사전
검사로 이동한다. 선택형 ACE의 다운로드/Docker 준비 가능성을 Review에서 미리 알린다. 기존
experiment는 암묵적으로 자산 다운로드/빌드를 하지 않고 생략 상태를 보여준 뒤 같은 명시적
Doctor 단계로 이어진다.

Doctor는 기존 `collect_plan(experiment, Registry())` report를 표시하고, 필요한 model 설정이 있는
실험에서만 `collect_plan(..., model=True)`로 connectivity probe를 수행한다. probe는 실제 외부 API
요청임을 Review/Doctor에서 알리며, 성공은 probe 호출 가능성만 확인하고 Agent optimization 성공을
보증하지 않는다고 표시한다. Doctor 실패 또는 blocked 결과는 절대로 runner를 시작하지 않는다.
실패 시 Retry checks와 Back to Review를 제공하고, 모두 통과한 경우에도 사용자가 Run Optimization을
명시적으로 선택해야 한다. CLI `doctor` 동작은 변경하지 않는다.

## Running과 Result

Runner의 기존 event callback을 유지한다. 공통 진행 해석은 `terminal_report.py`의 작은 helper가
담당하고 CLI `ProgressDisplay`와 TUI renderer가 함께 사용한다. CLI의 명령/JSON/stdout/stderr 의미와
runner event schema는 바꾸지 않는다.

Running은 전체 상태, optimizer/stage, iteration, task, phase, elapsed, 현재 trial budget 집계,
누적 human-readable events를 동시에 보인다. budget은 CLI와 동일하게 완료 trial 기준으로 계산하고
`completed / maximum`으로 표시하며 `max_trials`를 예정된 task 총수나 ETA로 해석하지 않는다.
누적 이벤트는 Textual `RichLog` 또는 동등한 append widget을 사용하고, 사용자 스크롤을 허용하며
최대 300 line으로 제한한다. 저빈도/정보성 이벤트만 번역해 append하고 원시 event JSON은 기본 화면에
출력하지 않는다.

Result는 Running과 분리한다. 성공/partial/failure 상태, 실제 `trials_used`, run directory,
report.html, 존재하는 summary/events/report artifacts를 표시한다. 예외에 `run_root` 또는 이미 생성된
artifact가 있으면 실패 화면에 경로를 표시한다. dedicated launcher처럼 run directory를 제공하지
않는 경우에는 반환된 종료 코드와 확인 가능한 설정 경로만 표시한다.

## 호환성과 localization

- CLI command, machine-readable JSON 및 stdout/stderr contract를 보존한다.
- Runner/event JSON schema와 실행 callback signature를 보존한다.
- 한국어/영어 UI를 유지하고 새 user-facing 문구도 localization에 포함한다.
- 좁은 터미널에서도 Home/선택 상세/Review/Model/Doctor/Running/Result가 scroll 가능하고
  50x20에서 키보드 focus와 핵심 상태를 사용할 수 있어야 한다.
- 새 framework, config/profile system, credential persistence, 일반화된 form engine은 추가하지 않는다.

## 검증 계획

- 기존 Textual Pilot 스타일에 Home-first/navigation/selection/detail/password/source/model/back/review/
  readiness/retry/block/progress/result/secret/localization/narrow-screen 회귀를 추가한다.
- readiness/model probe failure가 run을 차단하는지와 preparation 단계 출력/실패가 보이는지 검증한다.
- 여러 runner event가 누적되고 현재 상태와 budget/elapsed가 함께 갱신되는지 검증한다.
- CLI ProgressDisplay의 기존 계약/진행 semantics를 유지하는 `test_progress.py` 회귀를 확인한다.
- 설치형 TUI의 실제 PTY workflow를 업데이트해 Home, Review, Doctor, 실행/결과의 설치형 키 조작을
  확인한다. `docs/assets/tui-*.svg` 및 `docs/verification.md`의 기존 capture 절차를 참고해 실제 화면
  근거를 갱신한다.
- README 및 `docs/development.md`의 TUI 시작/키/단계 설명을 현재 UX로 갱신한다.
- 전체 unittest, 지정된 합성 demo, `make lint`를 실행한다. 모델 API/Docker가 필요한 실환경 검증은
  준비된 자격증명과 자산 없이 통과로 기록하지 않는다.

## 초기 검증 기준

`origin/main` 기준 격리 worktree에서 `make setup-core`가 통과했고, 변경 전 `make test`는 885개 중
806개 통과·79개 skip·실패 0, `make lint`도 통과했다. 79개 skip에는 호스트 RTL 도구 및 선택형
환경 의존 테스트가 포함된다.
