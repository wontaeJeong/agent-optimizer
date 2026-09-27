# Agent–Harness 실행 쌍 선택 설계

## 목표와 선택

실험에 여러 Agent·Harness가 있을 때 **이번 실행에 필요한 쌍만** 고를 수 있게 한다. 지원 능력은 각 Agent manifest의 `supported_harnesses`가 계속 선언하고, 실행 선택은 experiment TOML이 소유한다. 별도 스케줄러·전용 UI·새 plugin 계층은 만들지 않는다.

기존 `agents`와 `harnesses`만 선언하면 지금처럼 Agent-major 순서의 전체 곱을 실행하고 모든 Agent가 모든 프로필의 adapter를 지원해야 한다. 선택이 필요한 실험은 다음처럼 optional `[[pairs]]`를 쓴다:

아래는 `examples/minimal/solo.toml`·`team.toml`과 `examples/minimal/harness.toml`을 사용하고,
두 번째 프로필은 동일 fixture adapter를 `id="fixture-alt"`로 복사한 실험의 선택 예다.

```toml
agents = ["examples/minimal/solo.toml", "examples/minimal/team.toml"]
harnesses = ["examples/minimal/harness.toml", "experiments/my-team/fixture-alt.toml"]

[[pairs]]
agent = "rtl-solo"
harness = "fixture"

[[pairs]]
agent = "rtl-team"
harness = "fixture-alt"
```

`experiments/my-team/fixture-alt.toml`은 위 예시를 실행할 때 직접 복사해 두는 프로필 파일이다. `agent`는 Agent manifest의 `id`, `harness`는 Harness 프로필의 `id`다. adapter 등록 이름이나 파일 경로로 쌍을 지정하지 않는다. 계약 테스트는 같은 파일을 임시 프로젝트에 작성하고 공개 fixture evaluator를 사용한다.

## 설정·데이터 흐름

- `config.load_experiment`는 쌍마다 딱 두 문자열 필드만 허용하고, 빈 목록·중복 쌍·알 수 없는 ID·선택한 Agent가 지원하지 않는 adapter를 **소스 확보와 trial 전에** 거부한다. `[[pairs]]`를 사용하면 선언한 모든 Agent와 모든 Harness 프로필이 적어도 한 쌍에 등장해야 한다. 미선택 선언은 삭제하도록 안내한다.
- 하나의 평평한 `selected_pairs(spec)` 조회 함수가 기존 기본 전체 곱 또는 검증된 선택 목록을 `(AgentSpec, profile)` 순서쌍으로 반환한다. 실행·예산·계획이 이를 공유한다. 명시적 쌍은 TOML 선언 순서대로 실행하며 기본 경로의 Agent-major 순서는 유지한다.
- `runner.preflight`의 baseline/stage/final test 예산 최소 예약량, `readiness._budget_check`, `summary.planned_groups`, 실제 `GroupRunner` 생성, `agent-opt plan`의 `matrix`에 모두 **선택한 쌍의 수와 순서**를 적용한다. 선택되지 않은 조합은 후보·trial·그룹·점수를 만들지 않는다. 선언한 Agent·Harness는 모두 선택 목록에 포함되므로 기존 source lock/plugin fingerprint/프로필 배선은 그대로 사용한다.
- 각 그룹의 baseline/cache와 stage-local train 이력, validation 선택 후 test, CLI/TUI 결과·report 형식은 유지한다. 기본 예제 TOML·설치 entry point·CLI 옵션과 TUI wizard 질문은 변경하지 않는다. `agent-opt tui`의 기존 실험 경로로 같은 TOML을 실행할 수 있다.

## 경계와 검증

- 두 Agent×두 Harness의 API-free fixture에서 `pairs` 생략 시 기존 4개 그룹, 명시적으로 두 쌍을 고르면 해당 2개 그룹만 실제 평가하는지 검증한다. `plan.matrix`와 doctor의 최소 trial 예산, run summary·manifest의 원본 선언/실행 근거가 일치해야 한다.
- 빈 목록·중복·오탈자·미지원 조합·사용하지 않는 Agent 또는 Harness는 설정 오류로 확인한다. 1 Agent×1 Harness 기존 실행과 plan, 여러 독립 stage, 중단/예산 오류의 기존 회귀도 유지한다.
- 출처/editable/private 평가 자료·점수 계산은 변경하지 않는다. 모델·Docker 없는 fixture는 계약 검증이며 새 조합의 실제 외부 모델 성능 성공 증거가 아니다. 검증된 명령·환경·결과와 한계를 `docs/status.md` 및 필요한 확장 안내에 기록한다.
