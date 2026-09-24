# 범용 Optimization Report 설계

## 목적과 범위

독립 실행형 `report.html`을 열면 각 Agent × Harness 그룹의 개선 여부, 탐색 경로, 실제 선택된 후보, 실패 근거, 재현 정보를 빠르게 확인할 수 있어야 한다. 새로운 Optimizer를 추가해도 HTML 생성기가 Optimizer 이름을 분기하지 않아야 한다. 기존 실행 기록과 CLI를 최대한 유지하고, 합성 fixture를 실제 모델 성능으로 표현하지 않는다. 서로 다른 그룹 또는 데이터셋의 점수를 합쳐 하나의 best를 만들지 않는다. validation에서 확정된 선택과 이후 test 결과를 분리한다.

## 현재 구현 감사

`runner.py`는 스키마 v1 `summary.json`에 그룹별 baseline·stage·validation 선택·최종 test를, `manifest.json`에 설정·출처·목적 함수를, `events.jsonl`에 과제별 trial과 반복·병합·검토 이벤트를 기록한다. 후보별 `candidate.json`에는 부모 ID·변경 파일이, `changes.diff`에는 패치가 있다. 과제 실행별 `result.json`과 로그도 있다. 현재 trial은 후보 × 과제 × split × 반복 실행 한 건이다. 후보 한 개는 여러 번 평가되거나 생성 후 한 번도 평가되지 않을 수 있다. 선택 점수는 과제별 trial이 아닌 validation 집계 행이다. stage의 checkpoint는 Optimizer별 비정형 자료다.

현재 HTML과 Markdown은 서로 별도 로직으로 원시 파일을 읽는다. HTML 첫 화면에는 큰 run ID와 그룹·stage·trial·과제 시간 합계가 강조되고 실험명·목적 함수·예산·baseline 대비 결과가 없다. 세 개의 반복 점수표, 중첩 패널, 길게 잘리는 feedback, 선택 후보의 diff만 연결한 링크가 정보 밀도를 낮춘다. 표는 최소 폭 650px에 caption과 scope가 없고 여러 종류의 metric을 한 셀에 몰아둔다. CSS는 내장, JS는 없으며 기존 `<details>`, CSP, HTML 이스케이프, 상대 링크, 앵커와 session index는 보존해야 한다. 기준 전체 테스트 424개 통과(환경 의존 15개 skip), 합성 데모는 두 그룹의 과제별 trial 7건이다.

## 데이터 흐름과 호환성

원본 v1 아티팩트 → `report_model.py`의 정규화 → `report.json`·`report.md`·`report.html` 렌더링으로 구성한다. `report_schema_version`을 별도로 부여한 `report.json`은 파생 결과이며 기존 `summary.json`이나 선택 알고리즘을 대체하지 않는다. HTML·Markdown은 같은 메모리 내 canonical model을 사용하고 winner·카운트·개선량을 각자 다시 계산하지 않는다. `agent-opt report RUN --html`은 기존 원본에서 모델을 다시 생성하므로 오래된 `report.json`을 신뢰하지 않는다. 기존 스키마 v1, CLI 출력·CSV·session index·상대 링크를 유지한다.

## Canonical model

`ReportRun`은 실험 식별자·상태·합성 여부, benchmark·목적 함수·예산·재현 근거, 실행 기록·집계, 순서가 있는 그룹을 포함한다. 각 `ReportGroup`은 `(agent_id, harness_id)`로 구분하며 baseline validation 집계, `summary.json`에 기록된 selected validation 집계, 별도 최종 test 집계, stage·후보·평가·실패·선택적 탐색 구조를 포함한다. 선택 후보를 새로 추정하지 않는다. 선택 기록이 없으면 best도 없다. 숫자 `None`은 0이 아니다. 비교는 동일 그룹의 유효한 validation 집계와 목적 함수의 순서·방향·집계 방식을 따라 표시한다. 우선순위 낮은 지표로 높은 지표의 결과를 뒤집지 않는다. 동률의 선택 사유를 지어내지 않는다. 비율 지표임이 명확한 경우에만 `%`와 pp를 사용한다.

`Candidate`는 그룹-qualified 식별자, 원본 ID, 부모 ID들, producer, 변경 파일, 안전한 diff·snapshot 참조와 선택적인 생성 메타데이터를 가진다. `Evaluation`은 `trial_completed` 한 건에 대응한다. 기록된 `trial_id`를 evaluation ID로 쓰고 후보 참조·stage·task·split·repeat/seed·상태·유효성·원본 metric·관측 시간·feedback·execution·artifact를 유지한다. 집계 행은 별도 자료로 두어 단일 과제 점수를 전체 score처럼 표시하지 않는다. 실패 분류는 명시적 status/execution/error_type에 근거한 timeout, infrastructure, unsupported, interrupted, optimizer/run error, 원인 미확인 scored failure로 제한한다. feedback 내용만으로 Agent·시뮬레이터 실패를 추측하지 않는다.

실제 완료 평가 건수·통과·실패는 기록된 평가에서 세고, `trials_used`는 예약된 예산 사용량으로 구분한다. 과제 시간 합계는 총 실행 시간으로 이름 붙이지 않는다. 새 실행에서 실측한 벽시계 시간을 기록할 수 있으나 구 결과에 없다면 미수집으로 표시한다. 없는 command·git revision·simulator·전체 토큰 사용량은 생성하지 않는다. JSONL 끝의 손상된 줄은 앞의 정상 이벤트를 지우지 않는다. 파일 경로는 `safe_path`로 제한하고 원문은 이스케이프한다.

## 알고리즘 독립 탐색 구조

`structure`에는 선택적인 kind·표시 label·순서가 있는 unit을 둔다. unit은 ID, 선택적 부모 unit ID, 열린 문자열 type/label, 후보·평가 참조를 가진다. 후보↔복수 부모 관계는 unit 계층과 별도다. phase → iteration, generation → population, branch와 merge를 같은 표현으로 수용한다. 모든 Optimizer가 모든 차원을 채울 필요는 없다.

새 실행에는 실제 후보 생성·stage 경계 이벤트를 추가하고, Optimizer는 기존 `context.emit`을 이용해 범용 `report_unit` 메타데이터를 선택적으로 기록한다. 기존 iteration/merge 이벤트는 Optimizer 이름이 아닌 공통 필드에 근거해 투영한다. 과거 checkpoint는 원문으로 유지하고 구조를 추측하지 않는다. 후보 ID의 숫자나 trial 순서에서 세대·깊이를 만들어내지 않는다. 메타데이터가 없으면 기록된 후보 계보/이벤트만 보여주며 항상 시간순 평가 표로 fallback한다.

렌더러는 알고리즘 이름이 아닌 계층 unit·부모 관계·순서의 유무로 표시 방식을 선택한다. 기록된 집계 점수가 있는 작은 순서형 데이터는 압축 trajectory, 그룹형은 iteration/generation/phase 목록, 분기형은 제한된 계보 또는 best path를 사용한다. 임의 보간, split 결합, 순서 변경, 의미 없는 차트는 하지 않는다. 구조형 표시가 있어도 공통 평가 표는 항상 남긴다.

## HTML·Markdown 구성

첫 화면은 실험명·상태·합성 근거와 benchmark 경로·목적 방향·예산·Optimizer·Agent/Harness를 작은 metadata 영역에 보여준다. 공통 KPI는 근거 있는 완료·통과·실패 건수 등만 강조한다. 성능은 그룹별 baseline↔선택 validation 점수와 방향을 해석한 차이로 비교한다. 최종 test는 별도 영역이다. 이어서 탐색 journey, 공통 평가 표, 그룹별 선택 후보와 부모·변경·평가 이력, 실패 원문, stage·checkpoint·관측 usage, 설정, 재현 정보를 배치한다. 원시 설정·로그·긴 feedback은 `<details>`로 접고 복사 가능한 텍스트와 안전한 상대 링크를 보존한다.

디자인은 밝은 neutral 중심과 OS 다크 모드, system/monospace 글꼴, 1280~1440px의 최대 폭, 조밀한 표, 절제한 상태색을 사용한다. 숫자 열 오른쪽 정렬, caption/scope, 키보드 focus, 색 외의 상태 표기, 경로·에러 줄바꿈을 지원한다. 좁은 화면에서는 metadata/KPI가 감싸지고 표만 국소 스크롤된다. 불필요한 큰 hero·gradient·중첩 카드·외부 라이브러리는 사용하지 않는다. 작은 JS는 선택 사항이고 JS 없이 핵심 내용이 보여야 한다. session index와 standalone CSP도 유지한다.

Markdown에도 같은 그룹별 비교·건수·선택 후보·구조·실패·재현 근거를 표시한다. 기존 partial usage 주의사항을 보존한다. 세 출력은 정규화 모델만 소비한다.

## 검증 기준

v1 이전 결과 변환, 후보별 복수 평가와 미평가 후보, 복수 그룹, minimize/maximize·동률·결측, 실패 분류, 긴 비신뢰 입력, 모르는 Optimizer, 선형·반복·세대·분기 구조 및 fallback을 단위 테스트한다. HTML·Markdown·JSON의 동일한 선택·개선량·카운트를 확인한다. 새 합성 데모와 실패 실행을 생성하고 이전 v1 결과를 재생성한다. 전체 테스트·lint 이후 실제 브라우저에서 standalone 파일을 1440/1024/768px로 열어 가독성·넘침·상세 토글·상대 링크를 검사한다. 예약 trial ≠ 완료 평가, 과제 시간 합계 ≠ 총 실행 시간, stage 내부 결정 ≠ 최종 validation 선택이라는 구분을 유지한다.
