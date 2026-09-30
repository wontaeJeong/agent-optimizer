# 최종 MVP B 코드 리뷰 — 2026-10-01

## 범위와 판정

- 대상: B worktree의 `edbd2b8 → 520f4a7`. 지정 brief `B_TEXTUAL_MODEL_UX.md`, 제공 diff 전체, `docs/verification/final-mvp-b-20261001.md`, 변경 소스·전용 테스트 및 관련 모델/설정/실행 계약을 정적으로 대조했다.
- **Task-scoped spec compliance: 변경 요청.** 핵심 선택·검증은 구현됐지만 비밀 URL draft, 모델 표시와 실제 값의 불일치, 설치형 화면의 선택 보존 문제가 남는다.
- **Code quality: 변경 요청.** P1 2건, P2 3건. 누락된 fixture 파일 처리의 회귀와 입력/표시/실행 상태 간 불일치를 수정한 뒤 재검토해야 한다.
- 사용자 지시대로 테스트 재실행·제품 수정·커밋·하위 에이전트 실행은 하지 않았다. 아래 경로/행은 `520f4a7` 기준이다. 재현 조건은 소스 경로로 확인한 것이며 새 실행 결과를 주장하지 않는다.

## 중요 finding

### B-01 · P1 — fixture manifest가 없는 작업공간에서 새 실행 화면이 깨진다

**위치:** `src/agent_optimizer/preset_tui.py:64–72` (특히 67행), `src/agent_optimizer/tui.py:261–262,370–372`.

`agents.append(...)`가 `if path.is_file()` 밖으로 이동했다. 설치형/사용자 작업공간처럼 `examples/*/agent.toml`과 minimal manifest가 모두 없으면 `registered_agent`가 할당되지 않은 상태로 접근되어 `UnboundLocalError`가 발생한다. 다른 Agent만 있거나 `solo.toml`만 있으면 이전 반복의 Agent를 다시 추가하여 같은 `Option.id`가 중복된다. 예전 코드는 파일이 있을 때만 row를 추가했다.

**영향·요구 근거:** 새 최적화 → Agent 진입이 실패하거나 존재하지 않는 합성 Agent가 표시된다. brief 29행의 안정 row ID 및 기존 파일 플러그인/사용자 실험 보존 요구에 어긋나는 B 변경 회귀다. CLI/설치 생성의 F 소유권과 별개로 B의 목록 함수가 없는 파일을 견뎌야 한다.

**수정 방향:** manifest 존재 분기 안에서 해당 Agent row를 추가하고 목록 ID의 유일성을 보장한다. 신규 테스트의 `test_project()`는 전체 examples를 복사하므로 이 누락 조건을 다루지 않는다(`tests/support.py:18–26`).

### B-02 · P1 — credential URL을 Enter 대신 Esc로 나가면 draft의 repr와 재진입 화면에 비밀이 남는다

**위치:** `src/agent_optimizer/tui.py:34–40,342–345,867–871,1457–1458`.

Custom Endpoint에 `https://user:URL-SENTINEL@fixture.example/v1` 또는 query token URL을 입력하고 확정 전에 Esc를 누르는 경로다. `on_input_changed`와 `action_back`은 원문을 `input_drafts[AGENT_OPT_MODEL_BASE_URL]`에 저장한다. `ModelValues.__repr__`는 field 이름이 KEY/TOKEN/SECRET/PASSWORD일 때만 숨기므로 이 URL의 비밀은 `repr(input_drafts)`에 그대로 나온다. Custom 재진입은 현재 확정값만 `display_endpoint`로 검사한 뒤 draft를 우선 채우므로, 같은 비밀 URL이 password=False input에 다시 나타나 캡처에도 포함될 수 있다.

**영향·요구 근거:** brief 46–48행의 repr/스크린샷 비밀 부재와 credential URL 분리 요구를 충족하지 않는다. 정상 Endpoint 평문 정책 자체는 옳으며 URL password=True 복구를 요구하는 finding이 아니다. Enter 거부 경로의 삭제(`tui.py:897–907`)만으로는 Esc 경로를 막지 못한다.

**수정 방향:** credential 포함 URL은 draft 보존·재표시 단계에서도 거부/안전한 설명으로 처리하고 endpoint draft의 repr도 비밀 원문을 반환하지 않게 한다. 현재 URL 테스트는 Enter 이후 상세만 검사하며(`tests/test_tui_models.py:53–72`), SVG 테스트는 정상 URL/API key만 다룬다(178–189행).

### B-03 · P2 — bare selector의 Review 모델 ID/출처가 실제 실행값과 다르다

**위치:** `src/agent_optimizer/tui.py:461–466,956–958,1109–1118`.

ACE OpenCode에서 `AGENT_OPT_MODEL=team-model`, 명시 API ID 없음, 정상 endpoint/key가 설정된 조건이다. `_model_value(AGENT_OPT_MODEL_ID)`는 `compatible/` prefix가 있는 경우만 유도하므로 `glm5.3-flash`/default를 표시한다. 반면 `_execution_environment()`는 bare selector를 `compatible/team-model`로 정규화하고 API ID를 `team-model`로 바꾼다. 검증은 정규화한 selector를 사용하므로 이 상태로 Review를 통과할 수 있다.

**영향·요구 근거:** 화면/schema의 모델 ID·출처와 실행 모델이 다르다. brief 37·41행의 실제 모델 ID/selector 및 값 출처 표시, 기존 selector 의미 보존 요구에 어긋난다. 기존 bare 입력을 지원하는 실행 계약을 유지하면서 B 표시까지 일치시켜야 한다.

**수정 방향:** bare selector의 유도·정규화 결과를 표시와 실행이 함께 소비하게 하거나, 명시적인 UI 수정 절차를 요구한다. 현재 유도 테스트는 `compatible/fixture-model`만 사용한다(`tests/test_tui_models.py:114–121`).

### B-04 · P2 — 사용자 지정 model_env의 compatible 충돌은 Review 전에 차단되지 않는다

**위치:** `src/agent_optimizer/tui.py:1030–1053,1100–1103,1111–1121`.

기존 실험의 OpenCode profile이 `model_env=TEAM_AGENT_MODEL`을 쓰고 `TEAM_AGENT_MODEL=compatible/agent-model`, `AGENT_OPT_MODEL_ID=optimizer-model`인 경우다. `_required_model_fields()`는 해당 selector와 API field를 수집하지만 `_execution_environment()`의 정규화/충돌 검사는 `AGENT_OPT_MODEL`이 required일 때만 수행한다. `_validate_model_selection()`도 그 고정 field만 확인한다. 따라서 지정 selector와 API ID가 명시적으로 달라도 B의 계속/실행 전 검증을 통과한다.

**영향·요구 근거:** brief 41행의 명시된 compatible selector/API ID 충돌 경고·수정 요구가 기본 환경 변수에서만 성립한다. `config.py:203–225`는 `model_env`를 허용하고 실제 `OpenCodeHarness.argv`는 그 환경 변수를 사용한다(`src/agent_optimizer/harnesses/opencode.py:64–70`). 사용자 정의 실험의 정상 계약이므로 native 구현이나 CLI 생성에 인계할 문제가 아니다.

**수정 방향:** 실제 선택 profile들의 selector field를 기준으로 충돌을 검증하고, 복수 profile이 공통 API ID와 충돌하면 자동 덮어쓰기 없이 수정하도록 안내한다. 기본 `AGENT_OPT_MODEL`만 쓰는 전용 충돌 테스트로는 이 경로를 보장하지 못한다(`tests/test_tui_models.py:88–100`).

### B-05 · P2 — Workspace 확정이 앞서 고른 Optimizer를 GEPA로 바꾼다

**위치:** `src/agent_optimizer/tui.py:749–751,881–889`.

source checkout이 아닌 작업공간에서 ACE → OpenCode → Baseline 또는 Meta-Harness → CVDP를 선택하면 Workspace로 이동한다. 경로를 확정할 때 기존 `selections` 전체를 고정 ACE/OpenCode/GEPA/CVDP dict로 교체한다. 사용자가 고른 Optimizer가 상위 선택 변경 없이 사라진다. 특히 OpenRouter selector를 쓰는 Baseline에서는 원래 필요 없던 Optimizer API endpoint/key까지 추가로 요구하게 된다.

**영향·요구 근거:** brief 27·29·37행의 사용자 네 단계 선택, 뒤로/입력 보존, 상위 변경 때만 하위 무효화 요구를 충족하지 않는다. 이 대입 자체는 기준 커밋에도 있던 **잔존 수용 요구 미충족**이며 신규 회귀로 분류하지 않는다. 생성/native/CLI 구현은 F 소유지만 이 화면의 선택 의미 보존은 B 완료 조건이다.

**수정 방향:** Workspace는 경로만 갱신하고 선택한 네 component를 유지한다. 현재 신규 네 단계 테스트는 source checkout fixture만 사용하여 이 경로를 검증하지 않는다(`tests/test_tui_choices.py:35–63`, `tests/support.py:25`).

## 요구별 대조 및 소유 경계

| 검토 항목 | 정적 검토 결과 |
|---|---|
| stable ID / component-action 구분 | `ChoiceRow`, `Option.id`, `row.id/kind` 실행 분기는 개선됐다. label/index 기반 주 실행 분기는 제거됐으나 누락 manifest에서 ID가 깨지는 B-01이 남는다. |
| Planned / disabled 이유·대안·Enter 차단 | `gepa.merge`는 문서 근거의 표시 전용 planned row이며 factory 등록 없이 disabled다(`preset_tui.py:184–188`). disabled도 highlight 가능하고 Enter handler가 실행을 차단한다(`tui.py:370–372,707–713`); 상세는 준비·비호환·Planned 이유를 제시한다(592–607행). |
| Endpoint 평문 / credential 거부 / key-only masking | 정상 URL·모델 ID는 평문, key field는 password input 및 설정 여부만 표시한다. 확정 URL은 공통 계약+포트/경로 검증, 환경 credential URL은 안전한 설명을 사용한다. **draft 경로는 B-02로 미완결**이다. |
| mismatch / 값 출처 | 기본 compatible selector 충돌은 Model 계속 및 `_start`에서 차단하며 named preset은 key를 배제한다. bare selector 표시(B-03), 사용자 selector 충돌(B-04)은 미충족이다. |
| 상위 변경 / 뒤로 / 입력 | 변경된 상위 선택에 대해 하위 selection/focus와 experiment pointer·진단 상태를 비운다(738–745행). stable focus ID와 draft 복구가 있으나 Workspace의 선택 보존은 B-05로 미충족이다. |
| Agent / Optimizer 화면 의미 | 호출 목적·Optimizer 필수 여부·API와 selector 그룹은 표시한다. fixture/baseline은 field가 없다. native metadata에서 selector를 강제하지 않는 확장점은 있다. 현재 공통 API field와 역할 이름만 표현하므로 실제 C/F 역할별 override 연결 시 각 역할의 유효값·출처도 화면에 맞게 연결해야 한다. 이 리뷰는 native 실행이나 생성 구현 부재를 B 결함으로 세지 않는다. |
| 실제 수정 표면 | 선택 Harness의 `edit_surfaces`를 상세/Review가 소비한다. OpenCode를 native로 허위 재명명하지 않았다. |
| secret leak / 실행 환경 | key의 표시 metadata와 repr는 숨기며 기존 진단/예외/event redaction은 유지한다. 새 B 입력은 직접 `os.environ`을 변경하지 않는다. 다만 URL draft leak이 있다. 기존 worker의 `session_environment` 전역 변경/동시 세션 격리는 보고서가 F/G 인계로 공개한 통합 과제이며 B 신규 회귀로 세지 않는다. |
| History / Result / Home hook | `report.open`/`action_open_report`, `set_home_status` 연결점은 마련됐다. 서버·브라우저 실행은 F 소유로 인정한다. |

## 검증 증거의 해석

- B 구현 보고서는 전용 17개 통과, 모델 회귀 22개 통과, 프리셋 45개 중 32 skip, Ruff 통과를 기록한다. 이는 **보고서에 기록된 결과**이며 이번 리뷰가 재실행하여 확인한 결과는 아니다.
- 공유 `test_textual_tui.py:619`의 Endpoint password=True 기대는 최신 명시 요구로 대체됐으므로 그 실패를 제품 결함이나 양쪽 판정의 반려 근거로 사용하지 않았다.
- 이번 finding들은 전체 examples가 있는 fixture, 기본 selector 이름, Enter 확정, 정상 URL/API key 캡처 위주의 검증 밖 경로다. 전체 unit/live/native 미실행 사실은 보고서가 분리해 기록했으며 성공으로 확대 해석하지 않았다.
- 제품 수정 제안은 리뷰 기록이다. 실제 변경은 이 리뷰 문서 한 파일뿐이다.

## 구현 담당 수정 라운드 1 기록

이 절은 B 구현 담당의 처리 기록이며 위 정적 리뷰의 당시 판정/근거를 보존한다. 독립 재리뷰 승인으로 해석하지 않는다.

- B-01: 누락 fixture manifest에서만 row를 생략하고 동일 ID를 중복 표시하지 않도록 수정. 빈/solo-only/team-only/중복-ID 작업공간의 실제 Pilot 회귀 통과.
- B-02: URL 입력을 reactive 저장/렌더링 전에 검사해 비밀 포함 값을 삭제. 미완성 user:password의 후속 키 입력도 삭제하고 Esc/draft/repr/재진입/SVG에서 비밀 원문이 나오지 않도록 수정. 정상 Endpoint 평문·key만 password 유지.
- B-03: bare selector의 정규화와 API ID 유도 결과를 표시/schema/실행 환경이 공유하도록 수정. 값 출처도 derived로 일치.
- B-04: 실제 profile의 사용자 `model_env`와 복수 profile selector를 공통 API ID와 검사. 충돌은 준비 전에 차단하고 원래 환경을 덮어쓰지 않음.
- B-05: Workspace 입력에서 component dict를 덮어쓰지 않고 경로만 갱신. 설치형 Baseline/Meta-Harness의 선택·필수 API·뒤로가기 회귀 통과.
- 전용 `test_tui_choices`/`test_tui_models`/신규 `test_tui_textual` **24개 통과**, 모델 회귀 **22개 통과**, 프리셋 **실행 13개 통과·기존 skip 32개**, Ruff 통과. 기존 공유 Pilot **36개 통과·옛 Endpoint password 기대 1개 실패**는 변경하지 않고 G/F 인계로 유지.
- 정확한 명령/시간/결과, 새 캡처, F 최소 연결 요구와 미검증 범위는 [`final-mvp-b-20261001.md` §7](final-mvp-b-20261001.md#7-수정-라운드-1--중요-리뷰-finding-처리)에 추가했다. generation/backend/registry/CLI 및 다른 담당 소유 파일 수정 없음.
