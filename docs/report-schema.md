# 보고서 파생 데이터와 근거

`agent-opt run examples/minimal/experiment.toml`은 실행 폴더에 `summary.json`, `manifest.json`, `events.jsonl`(원본 스키마 v1)과 `report.json`, `report.md`, `report.html`(파생 결과)을 만듭니다. `agent-opt report RUN --html`은 저장된 **원본 파일을 다시 읽어** 세 보고서를 재생성합니다. 기존 `report.json`을 입력으로 삼거나 `summary.json`·`events.jsonl`의 선택·평가를 수정하지 않습니다.

## `report.json` 버전

| 버전 | 의미와 호환성 |
|---|---|
| v2 | `identity`, `configuration`, `provenance`, `objective`, `counts`, `groups`, `events`를 포함한 파생 보고서. 원본 `summary.json` 스키마 버전과 독립적입니다. |
| v3 | v2의 필드·선택·집계 의미를 유지하고 최상위 `evidence`를 추가했습니다. 새 필드를 사용하는 후처리기는 `report_schema_version >= 3`을 확인해야 합니다. 과거 원본 v1 실행도 `agent-opt report RUN --html`로 v3 보고서를 만들 수 있습니다. |

`groups[].baseline`과 `groups[].selected`의 비교는 동일 Agent × Harness의 유효한 **validation 집계**만 사용합니다. `groups[].final_test`는 선택 고정 후의 test 집계이며 개선 후보 선택에 쓰지 않습니다. `groups[].comparison`은 목적 지표 순서와 maximize/minimize 방향에 따른 값·차이·변화이며, `comparison_trend`는 먼저 차이가 난 지표의 방향입니다. 비교할 지표·유효한 집계가 없으면 변화는 `unknown`이고 결측 숫자는 `null`입니다. `groups[].evaluations`는 읽힌 `trial_completed` 한 건당 하나이고, 그룹별 `counts.completed_evaluations`는 **읽힌** 이벤트 수입니다. `counts.trials_used`는 예약된 평가 예산으로, 완료 건수와 다를 수 있습니다.

## `evidence` (v3)

| 필드 | 의미 |
|---|---|
| `events_file_present` | `events.jsonl`이 존재하는지 여부. 없으면 `false`이고 읽힌 건수 0이 전체 평가 0건이라는 뜻은 아닙니다. |
| `valid_lines`, `invalid_lines` | 읽힌 JSON 객체 줄 수와 비어 있지 않지만 UTF-8/JSON 객체로 읽지 못한 줄 수. 빈 줄은 세지 않습니다. 유효한 줄은 손상된 줄 전후 모두 보존합니다. |
| `completed_events` | 읽힌 모든 그룹의 `trial_completed` 줄 수. 그룹을 식별할 수 없는 이벤트도 이 수에 포함됩니다. |
| `status` | `warning`: 아래 불일치가 있음. `consistent`: 파일이 존재하고 모든 그룹의 기록된 `trial_count`가 읽힌 완료 이벤트와 일치함. `unknown`: 경고는 없지만 독립적인 대조 기준이 부족함. `consistent`도 원본 파일 밖에서 유실된 정보까지 증명하지는 않습니다. |
| `warnings` | 코드별 근거 차이 배열. 각 항목은 `code`, `group_key`, `expected`, `observed`를 포함합니다. 해당 범위/건수가 없으면 `null`입니다. |

| 경고 코드 | 해석 |
|---|---|
| `events_missing` | 이벤트 파일이 없습니다. 건수를 단정할 수 없습니다. |
| `events_invalid_lines` | 읽지 못한 줄 수가 `observed`에 기록됩니다(`expected=0`). 정상 줄은 계속 집계합니다. |
| `group_trial_count_mismatch` | `group_key`가 있으면 해당 그룹의 `summary.groups[].trial_count`와 완료 이벤트가 다릅니다. `group_key=null`이면 그룹별 건수는 일치하지만, 그룹 전체에 속하지 않은 완료 이벤트가 있어 그룹 건수 합계와 이벤트 전체가 다릅니다. |
| `reserved_completed_gap` | `summary.trials_used`와 읽힌 완료 이벤트 수가 다릅니다. 예산 예약 뒤 중단되었을 수도 있으므로 **이 차이만으로 기록 유실로 단정하지 않습니다.** |

과거 실행에 `trial_count`나 예산 기록이 없으면 비교 기준 자체를 만들지 않고 `unknown`/`null`로 둡니다. 미수집 metric·비용·토큰은 0이 아닌 `null`입니다. 일부 평가에서만 기록된 하네스 토큰·비용은 전체 합계로 표시하지 않습니다. `report.md`/`report.html`은 같은 v3 모델의 경고와 선택·건수를 보여주며, 원문과 후보 변경은 원본 파일로 연결합니다. 기존 v2 `report.json`에 새 필드는 없으므로 신호가 없다는 사실을 '완전함'으로 해석하면 안 됩니다.

## 알고리즘·optional native 근거

JSON/MD/HTML은 같은 normalized model을 사용합니다. `algorithm_trail`은 실제 stage/iteration/role/pass_number/accepted/status/split 이벤트와 기록된 frontier를 소비하며 baseline/file_variants나 unknown 알고리즘에 가짜 반복을 만들지 않습니다. stage 진행 곡선은 각 baseline에서 독립 시작하며 유효한 같은 그룹 validation만 비교합니다. `frozen_selection.json`과 원본 summary/events는 보고서 재생성으로 바뀌지 않습니다.

유효 payload가 있을 때만 optional `native_execution`을 표시합니다. attempt/iteration·역할별 유일 request·generated target/hash·안전 evidence path metadata를 outer trial에 연결하고 private/prompt/RTL 본문은 가져오지 않습니다. 실제 source/candidate/task identity와 일치하지 않거나 손상된 sidecar는 native만 제외하며 outer 평가/선택은 유지합니다. native wall time·요청 duration·inner 횟수/time과 outer trusted 평가 계측은 별도입니다. 현재 native usage는 partial/unreported, 없는 값은 null이며 비용/전체 토큰을 추정하지 않습니다.

추가 warning은 `native_execution_invalid`, `native_execution_warning`, `nonfinite_values` 등입니다. 비유한 파생 숫자는 null·경고로 정규화하고 원본은 보존합니다. 상세 HTML/MD 이벤트 표는 200건 상한이지만 전체 normalized 이벤트는 report.json에 남습니다. native evidence는 경로 metadata이지 href/공개 asset이 아닙니다. [D 근거](verification/final-mvp-d-20261001.md), [F producer](verification/final-mvp-f-20261001.md)를 따릅니다.

## loopback 제공·History

`agent-opt report RUN --serve --no-open --port 0`은 저장된 HTML을, `--html --serve`는 명시 재생성 후 새 서버 handle을 사용합니다. 고정 127.0.0.1·선택 report.html 또는 index.html **한 파일만** 허용합니다. JSON/MD/summary/events/log/source/candidate/private/session child route는 404이며 child는 별도 선택합니다. 포트 충돌은 code/errno와 retry를 제공하고 자동 fallback하지 않습니다. browser 실패는 URL/SSH 안내를 남기며 run status를 바꾸지 않습니다. Ctrl+C는 종료 130·자원 정리입니다. `--json/--csv` serve 충돌·serve 없는 port/no-open은 부작용 전에 종료 2입니다. History 조회는 report 없음·실패/중단도 보존하며 열람 action 전에 원래 row/inode와 서버 FD를 재검증합니다.
