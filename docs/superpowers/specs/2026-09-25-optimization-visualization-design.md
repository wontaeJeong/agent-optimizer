# Optimization 과정 시각화 설계

## 현황과 선택

`runner.py`는 `summary.json`에 그룹별 baseline/선택 validation 집계와 stage winner를, `events.jsonl`에 과제별 trial·시각·상태를 기록한다. `report_model.py`가 이를 `report.json`으로 정규화하고 `html_report.py`가 독립 HTML을 생성한다. 후보 메타데이터에는 부모 관계가 있고 `report_unit`/iteration 이벤트는 알고리즘별 탐색 단위다. 현재 HTML은 개선의 시점, 시도와 누적 최고점, 과제별 변화, 실행 이상을 대부분 표·로그에서 찾아야 한다. `trial`은 후보×과제×split×반복의 1회 실행이지 후보 점수가 아니다. 서로 다른 그룹/데이터셋, train minibatch/validation, validation/test를 섞지 않는다.

접근법은 (1) HTML에서 trial 점수로 후보 점수를 추측하는 방식, (2) 외부 차트 라이브러리를 포함하는 방식, (3) upstream의 후보별 집계를 기록하고 작은 inline SVG/CSS를 생성하는 방식이다. (1)은 데이터 의미를 왜곡하고 (2)는 오프라인 파일·MVP 크기에 비해 크다. **(3)을 선택한다.** JS 없이 파일을 열거나 인쇄해도 값과 범례가 보인다.

## 데이터와 표현 inventory

| 시각화 | 데이터 | 채택 기준 |
|---|---|---|
| validation progress + best-so-far | baseline/최종 집계는 있음; 중간 validation 집계는 부분적으로만 있음 | 집계 완료 이벤트를 upstream에서 기록하고 그룹별·동일 split·동일 objective로 표시 |
| baseline ↔ 최종 선택 | 그룹별 유효 validation 집계와 목적 방향 | 지표별 독립 비교 막대, delta와 단위를 병기 |
| trial 실행 궤적·결과 | trial별 status·시간·stage·후보·split | 작은 데이터는 compact 목록, 많은 데이터는 상세 접기; duration은 실제 `task_wall_time_seconds` |
| 목적 지표 간 trade-off | 완전한 후보별 validation 집계 | 2개 지표일 때만 scatter; 선택 규칙은 lexicographic으로 명시 |
| 후보 계보·반복 단위 | 부모 ID, 선택적 unit·iteration | 기록된 부모/단위가 있을 때 best path와 주요 후보, 전체 목록은 상세 영역 |
| 과제별 변화 | 같은 그룹/과제/validation의 baseline·선택 평가 | 관측된 동일 과제만; 반복값이 다르면 혼합/미확인 표기 |
| 실패 분포 | 분류된 trial failure | 충분한 건수에서 원인별 막대와 상세 링크 |
| 비용 효율·정확한 비용 분해 | 벽시계 측정은 있음, 일부 usage만 관측 | 전체 비용/단계별 분해가 없어 생략; 총 wall time은 독립 표시 |

## 파생 report 데이터

새 실행의 `GroupRunner.evaluate()`는 실제 집계가 끝났을 때 `candidate_evaluated` 이벤트에 후보, split, stage, 유효성, aggregate metrics, trial ID 목록을 기록한다. cache hit은 재평가가 아니므로 이벤트를 중복 기록하지 않는다. 이 이벤트는 점수 계산이나 선택 정책을 변경하지 않고, private feedback/test를 Optimizer에 노출하지 않는다. 이전 실행에는 summary의 baseline/stage evaluated/selected 집계만 근거로 사용한다. 이전 데이터의 시간 순서가 검증되지 않으면 진행 곡선을 임의로 복원하지 않는다.

`report_model.py`는 `report_schema_version`을 증가시키고 그룹별 `visualization` 아래 순서가 보장된 validation 후보 집계(시각, stage, 후보, metric, 유효성, 근거 trial 참조), trial duration/status, task 비교, 관측된 상태·실패 집계를 정규화한다. 더 오래된 기록에도 보고서가 생성된다. 파생 값의 결측은 `None`, invalid/partial은 best-so-far에서 제외한다. 후보별 누적 최고는 목적함수의 지표 우선순위·방향을 따르고, 최종 선택 표식은 실제 `summary.selected`만 따른다. 독립 stage는 baseline을 각자의 시작점으로 삼고 stage별 경계를 표시한다. test는 최종 선택 이후 별도 표에만 둔다.

## 정보 흐름과 시각화

문서 상단은 실험명·상태·합성 근거 및 간결한 목적/benchmark/예산을 보여준다. 성능 hero는 여러 그룹의 점수를 합치지 않고 각 그룹별 최종 선택과 baseline 차이를 보여준다. 바로 아래 그룹별 validation progress(실제 후보점, best-so-far, baseline, 선택 후보), 짧은 확정적 주석, 지표별 비교를 배치한다. 이후 데이터가 있을 때만 2지표 landscape, stage/iteration·후보 계보, 과제별 matrix, trial duration/status 궤적과 실패 분포를 이어 붙인다. raw config, 이벤트, checkpoint, diff, 로그는 끝의 상세 영역으로 내려간다. 기존 anchor, 이스케이프, 안전한 상대 링크, Markdown, session index, CSP를 유지한다.

SVG에는 title/desc·축/눈금/레이블·점 기호를 넣고 실제 수치를 인접한 HTML로도 읽을 수 있게 한다. 막대/매트릭스/계보는 의미와 값이 텍스트로도 표현된다. 작은 그래프는 좁은 화면에서 `viewBox`로 축소하되 축 레이블은 필요한 경우 HTML 목록으로 대체한다. 1회 trial이나 유효 점수 없음은 없는 곡선을 그리지 않는다. 모르는 Optimizer는 공통 이벤트/부모 관계를 소비하며, 향후 알고리즘은 `context.emit("report_unit", ...)` 및 기존 iteration/선택 이벤트로 명시적인 구조를 제공한다. Optimizer 이름별 HTML 분기는 없다.

## 검증

기존/새 실행의 HTML 생성, 단일 trial, 빈/실패 실행, 무효·부분 집계, 다중 목적 함수와 minimize, 과제·후보 이름의 긴 비신뢰 입력, 복수 그룹·split 격리, 동률 및 최종 선택 제외 후보, 오프라인/CSP·스크립트 부재를 검사한다. 새 합성 fixture와 실패 fixture를 생성해 1440px/좁은 화면·밝음/어둠·인쇄에서 생성된 실제 HTML 전체를 확인하고 캡처를 PR에 남긴다. 총 실행 시간·비용·성능을 추정하지 않으며 오래된 보고서도 재생성할 수 있어야 한다.
