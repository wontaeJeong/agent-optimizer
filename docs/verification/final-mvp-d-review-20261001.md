# 최종 MVP D — 범위 한정 코드 리뷰

확인일: 2026-10-01. 대상: `edbd2b8` → `cb63f69`, 지정 D 워크트리.

**판정: spec 부분 충족 / code 수정 후 재검토. Critical 0건, Important 2건, Minor 1건.**

## 검토 기준·증거

- `D_REPORTS_VISUALIZATION.md`의 정본·정합성, 실제 알고리즘 기록, optional native 소비, 안전한 원본 연결, offline·반응형 요구를 기준으로 지정 diff와 실제 소스·관련 테스트를 대조했다.
- `docs/verification/final-mvp-d-20261001.md`의 기존 report 98개·results 16개·Ruff 성공 및 브라우저 기록을 읽었다. **이는 기존 작업의 보고된 검증 결과이며 이번 리뷰에서 재실행하지 않았다.** 아래 입력 예시는 코드 경로를 따라 도출한 것으로, 새 실행 재현 결과가 아니다.
- 기존 `after-desktop.png`, `after-config-360.png`, `native-offline-360.png` 캡처를 직접 열어 확인했다. 위치: `/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/captures/`.
- C/F producer, 실제 native 실행, E 서버 통합은 판정 범위 밖이다. 하위 에이전트·코드 수정·테스트 재실행·커밋·푸시는 수행하지 않았다. 이 리뷰 문서만 추가했다.

## Critical

발견 없음.

## Important

### I-1. 잘못된 optional native 입력이 전체 보고서 생성을 중단한다

**위치:** `src/agent_optimizer/report_model.py:247–258`, `:95–99`, `:712–713`.

- `paths()`의 필터는 NUL 문자를 거부하지 않는다. 정상 outer identity의 native payload에 JSON 문자열 `"native/bad\u0000.json"`을 `evidence_paths`로 기록하면 prefix를 붙인 뒤 `_relative_path()` → `safe_path()`로 전달된다.
- `src/agent_optimizer/workspace.py:25–28`의 `component.lstat()`는 embedded NUL에 `ValueError`를 발생시키는데, `_relative_path()`는 `ConfigurationError`만 잡는다. 따라서 `evidence_unavailable` 경고로 처리하지 못하고 `build_report()`까지 예외가 전파된다.
- 별도 진입 경로에서도 같은 경계 문제가 있다. native 필드를 가진 이벤트의 `agent_id`가 JSON 배열이면 `:713`의 tuple-set membership에서 `TypeError: unhashable type: 'list'`가 발생한다. `:221–225`의 문자열 identity 검증에 도달하기 전이다.
- `results.py:309–312`는 이 호출 이후에 JSON/MD/HTML을 작성하므로, optional 자료 하나 때문에 outer 평가를 포함한 전체 파생 보고서 작성이 중단된다. native 자료만 제외하고 경고해야 한다는 소비 계약(`final-mvp-d-20261001.md:60`)과 안전한 확장 요구(brief §4)에 어긋난다.

**권고:** 집합 조회 전에 outer identity 타입을 검증하고, native 경로의 NUL 및 예상 가능한 경로 오류를 해당 자료의 경고/제외로 정규화한다. outer 평가 기록과 나머지 renderer는 유지해야 한다. 기존 신규 테스트에는 NUL·배열 identity 사례가 없다.

### I-2. validation 최고점의 초기값에 다른 split/그룹 baseline이 섞인다

**위치:** `src/agent_optimizer/report_model.py:587–597`.

- 새 단계별 leader 초기값은 baseline의 `valid`·`partial`·지표 수치만 검사한다. baseline의 `split == 'validation'` 및 해당 Agent×Harness 일치 여부를 검사하지 않는다.
- 반면 같은 파일 `:363–371`의 `_metric_value()`는 split·그룹을 확인하여 비교 표의 baseline을 null로 처리한다. 두 파생 결과가 같은 정본에서도 서로 다른 적격성 기준을 사용한다.
- 예: summary baseline이 `split='train'`, `valid=True`, `solve_rate=0.9`이고 실제 validation 이벤트가 search 단계의 후보 0.3 → 0.5뿐인 경우, `:580–585`의 충돌 검사에는 baseline 후보의 validation 이벤트가 없어 걸리지 않는다. 새 leader는 0.9로 시작하고 두 후보 모두 `regressed`, `best_metrics=0.9`가 된다. 선택 비교의 baseline/Δ는 null이지만 HTML validation 최고점 선은 train 점수 0.9를 사용한다. 다른 그룹 baseline도 같은 경로를 탄다.
- 이는 brief §1의 split·숫자·누락 의미 일치 및 §3의 실제 validation 수치만 연결한다는 요구에 어긋난다. 기존 단계 독립성 테스트(`tests/test_final_report.py:138–145`)는 정상 validation baseline만 사용한다.

**권고:** leader 초기값에도 비교 표와 동일한 baseline 적격성 검사를 적용한다. baseline이 부적격하면 초기 최고점은 null이며 첫 유효 validation 관측부터 시작해야 한다.

## Minor

### M-1. Markdown 알고리즘 기록에서 실제 검토 회차가 누락된다

**위치:** `src/agent_optimizer/results.py:207–217`.

- 정본 `algorithm_trail`은 `report_model.py:351–353`에서 `pass_number`를 보존하며, HTML은 `html_report.py:349–360`에서 검토 회차 열을 표시한다. 실제 Ecdysis producer도 `optimizers/ecdysis.py:85–86`에서 해당 값을 기록한다.
- 새 Markdown 표에는 `pass_number` 열이 없다. 같은 iteration에서 여러 검토가 진행된 경우 역할은 남지만 검토 회차를 본문에서 구분할 수 없다. 전체 JSON 원본 링크가 있어 데이터 자체가 유실되는 것은 아니므로 Minor다.
- `tests/test_final_report.py:174–190`은 회차 2를 입력하지만 Markdown에서 회차가 표시되는지는 확인하지 않는다.

**권고:** Markdown에도 검토 회차를 표시하여 HTML의 실제 알고리즘 과정과 대응시킨다.

## 요구별 판정

| 항목 | 판정·근거 |
|---|---|
| normalized v3·legacy·선택/재생성 경계 | 단일 `build_report()` → JSON/MD/HTML 흐름 유지(`results.py:305–312`), v3 및 additive 필드 유지. raw/frozen-selection 보존 테스트 확인. 적격성 parity는 I-2 보완 필요. |
| null/zero/partial·평가/예산·실패 구분 | nonfinite summary/manifest/events 정규화, null/0 보존, final 집계의 partial/valid 표시 및 빈 metrics 기록 보완 확인. 예약·완료 차이와 scored/infra/timeout 구분 유지. 테스트 성공은 기존 기록에 한정. |
| 알고리즘별 실제 과정·계보 | 실제 optimizer/report-unit 이벤트와 checkpoint frontier만 사용. 이름만으로 반성·협업·merge를 생성하는 새 분기 없음. 단계별 leader 분리와 SVG 경계 단절 확인. baseline/file_variants 및 unknown의 generic 경로 유지. M-1 보완 권고. |
| optional native·안전 schema | whitelist·outer task/hash 검사·request ID 중복 제외·partial downgrade·내부/outer 구분·legacy에서 섹션 생략 확인. sidecar 본문을 읽거나 native 근거 href를 생성하지 않음. 잘못된 optional 입력 격리는 I-1로 미충족. |
| HTML/JSON 문자열·MD delimiters | HTML `text()` 및 `<pre>` JSON escape, SVG 문자열 escape, MD `_cell()`의 HTML/Markdown/파이프 escape를 확인. 신규 native injection 테스트와 기존 injection 테스트 대조. 실행 가능한 새 script/JSON-in-script 경로 없음. |
| unsafe links·공개 경계 | HTML 로그 링크를 자기 trial의 명시 stdout/stderr로 제한하며 safe_path·symlink·숨김/상위 이동 차단을 사용. arbitrary artifact 편의 링크 제외. native 근거는 metadata만 표시. 로컬 diff/bundle/원본 링크는 기존 계약이고 E 공개 allowlist를 늘리는 근거가 아님. |
| offline·반응형·접근성 | inline CSS/SVG·시스템 폰트·CSP, 새 외부 의존성 없음. 480px 설정 한 열·긴 경로 wrap·표 내부 스크롤·focus·print 스타일 확인. 기존 캡처에서 desktop/360px 배치와 native 표 focus 확인. offline 요청 0·한/영·빈 run·stress는 기존 검증 기록을 근거로 하며 이번 브라우저 재실행 없음. |
| 소유 범위·실환경 주장 | 지정 diff의 7개 파일 모두 D 소유 코드/전용 테스트/검증 문서. C/F 연결 및 실제 native 미검증을 명시하며 합성 fixture를 실환경 성공으로 주장하지 않음. |

## 최종 verdict

- **Spec: 부분 충족.** 핵심 구조·안전한 표현·offline/반응형 보완은 요구에 부합하지만, 잘못된 optional native 자료의 격리와 validation baseline 적격성 일치가 남아 있다.
- **Code: 수정 후 재검토.** I-1·I-2를 D 소비/정규화 범위에서 해결해야 한다. C/F producer 미연결을 D의 실패로 계산하지 않았다. M-1은 과정 표현의 경미한 누락이다.
- 기존 테스트 재실행 없이 소스·테스트·검증 문서·저장 캡처를 검토했다. 새 입력 예시의 실행 재현과 수정 검증은 이번 리뷰의 결과에 포함하지 않는다.

## 수정 라운드 1 — 구현 담당의 반영 기록

확인일: 2026-10-01. 위 리뷰는 `cb63f69`에 대한 당시 판정이며, 아래는 D 구현 담당이 해당 입력을 실행 재현하고 수정한 결과다. 독립 재리뷰 결과로 표현하지 않는다.

| 지적 | 반영·검증 |
|---|---|
| I-1 | 집합 조회 전에 native outer identity 타입 검사, NUL 경로 거부, 예상 가능한 경로 오류의 warning 처리. malformed native만 제외/경고하고 기존 outer 보고서와 null 사용량 보존. NUL·배열/객체 identity·경로 접근 거부 회귀 추가. |
| I-2 | metric 비교와 validation baseline의 공통 적격성 검사 적용. 부적격 baseline을 초기 최고점·표식·충돌 대조·과제 비교에서 제외. 같은 후보 ID의 실제 validation 기록 억제와 train/test/다른 그룹 baseline 0.9의 최고점 혼입을 각각 재현·검증. |
| M-1 | Markdown 알고리즘 표에 검토 회차 열 추가. 같은 iteration/역할의 pass_number 1/2/null 구분 검증. |

정확한 실행 명령·수정 전 실패·수정 후 결과는 [D 검증 보고서 §8](final-mvp-d-20261001.md#8-수정-라운드-1--범위-한정-리뷰-반영)에 추가했다. 최종 전용 25개, 전체 report 104개, results 16개 및 Ruff 통과. C/F producer·native 실환경·E 제품 서버·전체 저장소 unit의 새 검증 주장은 없다. 사용자 지시에 따라 이 리뷰 문서도 의도된 한국어 로컬 커밋에 포함한다.
