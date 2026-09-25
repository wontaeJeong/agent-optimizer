# Optimization 과정 시각화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 유효한 validation 집계와 실제 trial 기록으로 개선·선택·실행 경로를 한눈에 읽는 독립 HTML을 만든다.

**Architecture:** runner의 aggregate 결과를 이벤트에 기록하고 report_model이 그룹별 분석 데이터를 만든다. 독립 `report_visualizations.py`는 그 데이터만으로 SVG/CSS 조각을 만들고 `html_report.py`는 요약→진행→탐색→근거 순서로 배치한다.

**Tech Stack:** Python 3.11+, 표준 라이브러리, 인라인 SVG/CSS, unittest, 브라우저 캡처.

**Spec:** `docs/superpowers/specs/2026-09-25-optimization-visualization-design.md`

## Global Constraints

- 다른 그룹·데이터셋·split의 점수를 합치지 않는다. train minibatch와 validation도 섞지 않는다.
- 선택은 기존 `summary.selected`만 따르고, invalid/partial은 best-so-far에서 제외한다.
- 전체 비용·시간 구성비를 추정하지 않으며 없는 데이터는 `None`으로 둔다.
- 외부 CDN·JS 없이 보고서를 열고 인쇄할 수 있어야 한다.
- 사람용 문구는 한국어로 작성하고 기존 안전 링크·HTML 이스케이프·CSP를 유지한다.

---

### Task 1: 검증 집계의 실제 시점 기록

**Files:** Modify `src/agent_optimizer/runner.py:248-267`; Test `tests/test_run_lifecycle.py`.

**Interfaces:** `candidate_evaluated` 이벤트는 `candidate_id`, `stage_id`, `split`, `valid`, `metrics`, `trial_ids`를 포함한다. `EventStore`가 timestamp를 붙인다.

- [x] **Step 1: 실패하는 테스트 작성:** 최소 실행에서 `candidate_evaluated`의 validation 행·trial ID가 실제 `trial_completed`와 대응하고 cache hit마다 중복되지 않는지 검사한다.
- [x] **Step 2: 실패 확인:** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_run_lifecycle.py -v`.
- [x] **Step 3: 최소 구현:** `GroupRunner.evaluate()`의 `row` 저장 직후 `self.events.append({"event": "candidate_evaluated", "stage_id": self.current_stage["id"] if self.current_stage else "baseline", "trial_ids": [r["trial_id"] for r in records], **row, ...})`를 추가한다. 후속 final test도 split은 test로 남긴다.
- [x] **Step 4: 관련 테스트 통과 후 커밋:** 기존 선택 점수·summary 변경이 없어야 한다.

### Task 2: 증거에 근거한 시각화 모델

**Files:** Modify `src/agent_optimizer/report_model.py:345-398`; Test `tests/test_report_model.py`.

**Interfaces:** 그룹 `visualization = {"progress": [...], "trial_timeline": [...], "task_comparison": [...], "outcomes": {...}}`. progress 행은 `candidate_id`, `stage_id`, `metrics`, `best_metrics`, `improvement`, `selected`, `source`를 포함한다. 이전 데이터는 timestamp를 확정할 수 있는 경우에만 그린다.

- [x] **Step 1: 실패하는 테스트 작성:** 다중 목적, 미선택 최고점, cache 반복, invalid/partial, 한 trial, missing events, 같은 task/repeat의 baseline·selected를 한 그룹 안에서만 확인한다.
- [x] **Step 2: 실패 확인:** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_report_model.py -v`.
- [x] **Step 3: 최소 구현:** 이벤트의 유효 validation 집계를 시간순/그룹별로 투영하고 baseline과 실제 선택의 `summary` 집계로 정합성을 검사한다. 선택 벡터는 objective의 metric 순서·direction을 사용한다. timeline은 완료 이벤트의 실제 task wall time만 사용한다. task 비교는 동일 validation task의 `passed` 반복값이 모두 finite하고 0/1로 일치할 때만 통과/실패로 정규화한다.
- [x] **Step 4: 테스트 통과 후 커밋:** `report_schema_version` 증가와 이전 summary를 통한 최소 비교 fallback을 확인한다.

### Task 3: 보고서의 시각적 이야기

**Files:** Create `src/agent_optimizer/report_visualizations.py`; Modify `src/agent_optimizer/html_report.py`, `src/agent_optimizer/report_style.py`; Test `tests/test_html_report.py`.

**Interfaces:** `render_progress(group, objective)`, `render_comparison(group, objective)`, `render_landscape(group, objective)`, `render_trail(group)`, `render_tasks(group)`, `render_timeline(group)`, `render_outcomes(group)`는 HTML 문자열을 반환하며 근거가 없으면 빈 문자열을 반환한다.

- [x] **Step 1: 실패하는 테스트 작성:** generated HTML의 baseline/best SVG, trial vs best 분리, 결과 라벨/접근성, 긴 ID, 2지표 landscape, 빈·실패 실행, 외부 script 부재를 검사한다.
- [x] **Step 2: 실패 확인:** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_html_report.py -v`.
- [x] **Step 3: 최소 구현:** `svg` title/desc, axes·데이터 레이블, 목적 방향을 반영한 시각 요소를 그리고 정보 흐름을 hero→progress→comparison→trail→tasks→trial/failure→details 순으로 변경한다. legacy 원본 상세와 앵커는 유지한다.
- [x] **Step 4: 전체 검증과 브라우저 검수:** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`, `make lint`, 실제 합성 run 생성, 1440px/좁은 화면·dark/print 및 콘솔 오류 확인. PR용 변경 전·후 캡처를 만든다.
- [ ] **Step 5: 검토·커밋·푸시·PR:** `git diff --check`, `git status`, 변경 전·후 캡처와 재현법을 PR 본문에 기록한다.
