# 보고서 근거 일관성 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 세 파생 보고서가 원본 이벤트 근거의 누락·불일치와 선택·평가 의미를 일치하게 전달한다.

**Architecture:** `report_model.py`에서 이벤트 진단과 경고를 한 번 만들고 HTML/Markdown은 그 결과를 표시한다. 기존 원본·선택 알고리즘을 유지하고 Markdown 구성과 다중 지표 차트 범례만 조정한다.

**Tech Stack:** Python 3.11+, unittest, 독립 HTML/CSS/SVG, Markdown, 스키마 v3

**Spec:** `docs/superpowers/specs/2026-09-27-report-evidence-consistency-design.md`

## Global Constraints

- `runner.py`의 스키마 v1 원본·CLI 및 선택 결과는 변경하지 않는다.
- 원본이 없는 값은 `null`; `trials_used`는 예약 예산이므로 완료 건수 차이가 곧 이벤트 유실은 아니다.
- 모든 사람이 읽는 문구는 한국어로 작성하고 `AGENT_OPT_LANG=en` 출력은 영어로 제공한다.
- 실행은 워크트리에서 하고 기본 저장소의 `main`은 유지한다. 서브에이전트는 사용하지 않는다.

---

### Task 1: 이벤트 근거 진단과 스키마 v3

**Files:** Modify `src/agent_optimizer/report_model.py:29-43,448-502`; Test `tests/test_report_model.py`; Test `tests/test_results.py`

**Interfaces:** `build_report(root: Path, summary: dict) -> dict`에 `evidence`를 추가한다. `evidence`는 `events_file_present: bool`, `valid_lines: int`, `invalid_lines: int`, `completed_events: int`, `status: str`, `warnings: list[dict]`를 가진다. 각 warning은 `code`, `group_key`, `expected`, `observed`를 가지며 미해당 필드는 `None`이다. 코드: `events_missing`, `events_invalid_lines`, `group_trial_count_mismatch`, `reserved_completed_gap`. 원본 `events`와 그룹 `counts`는 읽힌 이벤트만 센다.

- [ ] **Step 1: 실패 테스트 작성.** 파일 없음, 손상된 줄 전후의 유효한 이벤트, 두 그룹 중 하나의 `trial_count` 불일치, 예약량 차이, 과거 요약에 `trial_count`가 없는 경우를 `build_report()`에 주고 `evidence.status`·경고 코드·기대/관측값·기존 selected 불변을 검사한다. 예:

```python
report = build_report(root, {"trials_used": 3, "groups": [{"agent_id": "a", "harness_id": "h",
    "trial_count": 2, "selected": [], "stages": []}]})
self.assertEqual(report["evidence"]["warnings"][0]["code"], "events_missing")
self.assertEqual(report["counts"]["completed_evaluations"], 0)
```

- [ ] **Step 2: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_report_model.py -v`로 RED 확인.**
- [ ] **Step 3: `_read_events`가 (이벤트, 파일 상태, 유효/손상 줄 수)를 반환하게 확장하고 `build_report`에서 `trial_count`가 정수일 때 그룹별 비교, 예약/완료 차이는 별도 코드로 기록한다.** 유효한 JSON 객체의 비이벤트 레코드도 기존처럼 유지한다. 파일 없음은 손상 줄 0으로 구분하고, 예산값이 없으면 예약 경고를 만들지 않는다. 경고가 없고 그룹 `trial_count` 전부 확인되면 `consistent`, 경고가 있으면 `warning`, 대조 기준이 없으면 `unknown`.
- [ ] **Step 4: 관련 테스트를 다시 실행해 GREEN 확인하고 `report.json` 직렬화 및 이전 필드 유지도 검사한다.**
- [ ] **Step 5: 변경 파일만 커밋한다.**

### Task 2: Markdown의 분리된 결과·상대 근거·입력 이스케이프

**Files:** Modify `src/agent_optimizer/results.py:37-139`; Test `tests/test_results.py`; Adjust obsolete string assertions in `tests/test_html_report.py` where the Markdown layout changes.

**Interfaces:** `write_report(root, summary, report=None, language=None) -> None`의 시그니처 유지. `report["evidence"]`를 사용해 경고와 상태를 표시한다. 링크는 파일 실재·`safe_path` 검증 후 URL 인코딩된 상대 경로만 허용한다.

- [ ] **Step 1: 실패 테스트 작성.** validation과 test가 별도 제목·표로 렌더링되고 선택 ID·방향·두 지표 우선순위·평가 건수가 JSON과 일치하는지 검사한다. 존재하는 stage JSON, 후보 diff, trial `result.json`, `summary.json`/`events.jsonl` 링크를 검사하고 없는 파일이나 `../` 경로 링크는 제외한다. 사용자 문자열 `a|b <img> **bold** [link](javascript:x) \`\`\`\n# title`은 텍스트로만 남게 한다.
- [ ] **Step 2: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_results.py -v`로 RED 확인.**
- [ ] **Step 3: Markdown 전용 `_cell`/본문 이스케이프와 `_relative_link`를 구현한다.** 셀은 한 줄·길이 제한(예: 160자)으로, 링크 대상은 `safe_path`+존재 확인과 URL `quote`를 쓴다. 원문 자료는 `report.json`/원본으로 연결한다. 여러 지표나 체크포인트 JSON을 표 셀로 직렬화하지 않는다. 경고 없는 과거 보고서는 근거 `unknown`을 설명한다. 미수집 사용량은 `null`로 유지한다.
- [ ] **Step 4: `test_results.py`와 관련 `test_html_report.py`를 실행해 GREEN 확인한다.**
- [ ] **Step 5: 변경 파일만 커밋한다.**

### Task 3: HTML 경고와 다중 지표 진행 곡선 설명

**Files:** Modify `src/agent_optimizer/html_report.py:540-607`; Modify `src/agent_optimizer/report_visualizations.py:68-165`; Modify `src/agent_optimizer/report_style.py` only if warning needs contrast/overflow styles; Test `tests/test_html_report.py`.

**Interfaces:** HTML은 `report["evidence"]` 경고와 선택된 집계 필드를 읽는다. `render_progress(group, objective, index)`는 첫 지표 값과 사전식 최고 후보의 첫 지표 값을 별개로 설명하되 SVG 데이터 출처를 변경하지 않는다.

- [ ] **Step 1: 실패 테스트 작성.** 손상/누락/예약 경고 문구와 링크 및 `en` 현지화, 첫 지표 동률·두 번째 minimize 지표 개선 시 차트의 '사전식 최고 후보의 첫 지표 값' 범례 및 실제 지표 목록, 선택 결과를 검사한다.
- [ ] **Step 2: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_html_report.py -v`로 RED 확인.**
- [ ] **Step 3: 요약에 짧은 경고 블록을 넣고 경고 코드에만 대응하는 문구를 제공한다.** 무경고 `unknown`은 정상 입증 표현을 피한다. 진행 SVG 축·범례·인사이트의 '최고점'을 목적 지표 전체의 사전식 최고 후보로 정확히 한정한다. 선택 곡선의 첫 지표 값이 동일한 경우도 구별 가능하도록 보조 지표 수치와 우선순위를 목록에 남긴다.
- [ ] **Step 4: HTML 테스트를 실행해 GREEN 확인한다.**
- [ ] **Step 5: 변경 파일만 커밋한다.**

### Task 4: 문서·교차 출력·브라우저 검증

**Files:** Create `docs/report-schema.md`; Modify `README.md:30-37`; Test `tests/test_results.py` for cross-output evidence/selection/count assertions; Update `tests/test_html_report.py` expectations if needed.

**Interfaces:** `report_schema_version: 3`은 v2의 기존 필드를 유지하며 새 `evidence`만 추가한다. v1 원본 재생성과 `null`/불일치 의미를 문서화한다.

- [ ] **Step 1: 교차 출력 테스트를 작성하고 실패를 확인한다.** 한 fixture의 `summary.json`/`events.jsonl`로 `write_report_artifacts`를 실행해 JSON 경고 코드·두 그룹의 count/selection/trend가 HTML/MD에도 보이는지 확인한다.
- [ ] **Step 2: 테스트를 GREEN으로 만들고 `docs/report-schema.md`, README에 파생 스키마·원본 관계·NULL·예약량/완료량·재생성을 설명한다.**
- [ ] **Step 3: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`, `make lint`, `PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml`을 실행한다.** minimal과 손상·부분/실패 fixture에서 세 파일 대조.
- [ ] **Step 4: 독립 HTML을 데스크톱과 390px `file://`로 열어 내부·상대 링크, 키보드 focus, 표 가로 넘침을 검사하고 PR용 변경 전·후 이미지를 기록한다.**
- [ ] **Step 5: 문서와 테스트만 커밋하고 diff·status·base와 모든 포함 커밋을 검토한 뒤 푸시·PR을 생성한다.**
