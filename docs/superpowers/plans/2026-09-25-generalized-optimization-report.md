# 범용 Optimization Report 구현 계획

> **구현 담당자:** 작업별 검토와 검증을 위해 superpowers:executing-plans를 적용한다. 아래 확인란을 진행에 맞춰 갱신한다.

**목표:** 기존 실행 결과와 호환되는 공통 report model로 Markdown/HTML/JSON을 생성하고, 다양한 탐색 구조를 정확하고 읽기 쉬운 독립형 HTML로 표시한다.

**구조:** 저장된 v1 summary/manifest/events/candidate 정보를 정규화한 뒤 버전이 있는 파생 `report.json`을 기록한다. Markdown과 HTML은 동일한 모델을 사용하며, 새 Optimizer는 선택적으로 범용 구조 이벤트를 남긴다. 기존 선택 로직과 공개 결과 파일은 유지한다.

**기술:** Python 3.11+ 표준 라이브러리, `unittest`, 내장 HTML/CSS, 필요할 때만 vanilla JS. 런타임 의존성 추가 없음.

**설계:** `docs/superpowers/specs/2026-09-25-generalized-optimization-report-design.md`

## 공통 제약

- `summary.json`, `manifest.json`, `events.jsonl`, 후보 파일, CSV, CLI 응답, session index를 보존한다.
- 다른 Agent × Harness/데이터셋 점수를 한 순위로 묶거나 test로 후보를 재선택하지 않는다.
- 예약된 trial을 완료 평가로, 과제 시간 합계를 총 실행 시간으로, partial 사용량을 전체로 표시하지 않는다.
- 없는 값·원인·명령·버전·시뮬레이터를 추측하지 않는다. HTML은 standalone·이스케이프·CSP·상대 링크를 유지한다.
- 전체 테스트와 lint, 실제 합성 report 생성, 브라우저의 1440/1024/768px 렌더링을 확인한다.

## 파일별 책임

- `src/agent_optimizer/report_model.py` 신설: v1 정규화, 비교·건수·분류, 구조, JSON 호환 dict.
- `src/agent_optimizer/runner.py` 수정: 실제 후보·stage 이벤트, 관측 실행 시간(가능할 때만).
- `src/agent_optimizer/results.py` 수정: 모델 기반 Markdown 및 출력 조정.
- `src/agent_optimizer/html_report.py` 수정: 모델 기반 독립형 HTML 및 기존 session index.
- `src/agent_optimizer/cli.py` 수정: `report --html` 재생성 경로 통합.
- `tests/test_report_model.py` 신설, `tests/test_results.py`·`tests/test_html_report.py`·`tests/test_run_lifecycle.py` 수정: 정확성·호환·렌더링·실패 경계.

---

### Task 1: 구 실행 증거를 canonical model로 정규화

**파일:** `src/agent_optimizer/report_model.py` 신설, `tests/test_report_model.py` 신설.

**입출력:** `build_report(root: Path, summary: dict) -> dict`. 결과에는 `report_schema_version`, `identity`, `configuration`, `provenance`, `objective`, `counts`, `groups`, `events`가 있다. 그룹에는 `key`, `baseline`, `selected`, `final_test`, `stages`, `candidates`, `evaluations`, `structure`, `comparison`, `counts`를 둔다. 후보/평가 참조는 그룹-qualified ID로 구분한다.

- [ ] **1. 실패 테스트 작성:** `TemporaryDirectory`에 두 그룹과 `minimize` 목적의 manifest, 부모가 있는 `candidate.json` 두 개, 동일 후보·다른 repeat의 완료 이벤트 두 건을 기록한다. 평가 두 개의 후보 참조가 같고 그룹 ID는 다르며 `selected`가 summary와 정확히 같은지 확인한다. 평가 없는 후보도 목록에 있어야 한다.

```python
report = build_report(root, summary)
self.assertEqual(report["report_schema_version"], 1)
self.assertEqual(len(report["groups"][0]["evaluations"]), 2)
self.assertEqual(report["groups"][0]["selected"], summary["groups"][0]["selected"])
self.assertEqual(report["groups"][0]["candidates"][1]["parents"], ["c0001"])
```

- [ ] **2. 실패 확인:** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_report_model.py -v`를 실행해 `report_model` import 오류를 확인한다.
- [ ] **3. 최소 구현:** manifest 부재는 빈 dict, 손상된 JSONL 줄은 건너뛰고 정상 이벤트는 원래 순서로 유지한다. `trial_completed` 한 건을 Evaluation 한 건으로 복제하고 원래 trial ID·metrics·feedback·execution을 남긴다. 후보는 기록된 ID 집합을 사용하고 `safe_path(root, f"{agent}/{harness}/candidates/{candidate_id}/candidate.json")` 범위만 읽는다. diff는 길이를 제한한 미리보기와 원본 상대 링크만 둔다. 집계 행은 원본을 유지하고 재선택하지 않는다.

```python
def build_report(root: Path, summary: dict) -> dict:
    manifest = _read_json(root / "manifest.json", {})
    events = _read_events(root / "events.jsonl")
    groups = [_group(root, group, events, manifest) for group in summary.get("groups", [])]
    return {"report_schema_version": 1,
            "identity": {"run_id": summary.get("run_id"), "status": summary.get("status"),
                         "synthetic": summary.get("synthetic")},
            "configuration": manifest.get("experiment", {}), "provenance": manifest,
            "objective": manifest.get("experiment", {}).get("objective", {}),
            "counts": _counts(groups, summary), "groups": groups, "events": events}
```

- [ ] **4. 통과 확인:** 위 모델 테스트와 `test_html_report.py`를 실행하고 `json.dumps(report, allow_nan=False)`도 확인한다.
- [ ] **5. 커밋:** `git status --short`, `git diff`, `git log --oneline -10` 확인 후 두 파일만 stage, `git diff --cached --check`, `git commit -m "저장된 결과의 공통 리포트 모델 추가"`.

### Task 2: 비교·실패·건수를 한 번만 계산

**파일:** `src/agent_optimizer/report_model.py`, `tests/test_report_model.py` 수정.

**입출력:** `build_report`의 그룹 `comparison`에 `{name, direction, baseline, selected, delta, trend}`를, 그룹·실행 `counts`에 완료·통과·실패·예산 사용량을, 실패에는 `{category, message}`를 추가한다.

- [ ] **1. 실패 테스트 작성:** minimize latency 12→9의 개선과 `delta=-3`, lexicographic 1순위 동률에서 2순위 비교, 결측 baseline의 `delta=None`, 예산 4회 예약/완료 이벤트 3건의 구별, `infrastructure_error`·`timeout`·`failed`의 상이한 분류, test 점수를 비교에 넣지 않는 경우를 검사한다.

```python
self.assertEqual(group["comparison"][0]["trend"], "improved")
self.assertEqual(group["comparison"][0]["delta"], -3)
self.assertEqual(report["counts"]["evaluations"], 3)
self.assertEqual(report["counts"]["trials_used"], 4)
self.assertEqual(group["failures"][0]["category"], "infrastructure")
```

- [ ] **2. 실패 확인:** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_report_model.py -v`; 비교/분류 필드가 없어서 실패해야 한다.
- [ ] **3. 최소 구현:** 유효한 동일 그룹 validation 집계만 비교한다. `selected - baseline` 원값과 direction별 개선·유지·퇴보를 계산하고 전체 판단은 목적 함수 지표의 첫 차이에 한정한다. `passed` 기반 분수형 rate로 확인된 경우만 pp를 계산한다. 명시적 status/execution/error_type만 실패 분류에 사용한다. 완료 evaluation 수와 `trials_used`를 분리한다.

```python
def _trend(before, after, direction):
    if before is None or after is None:
        return "unknown"
    if after == before:
        return "unchanged"
    return "improved" if (after > before) == (direction == "maximize") else "regressed"
```

- [ ] **4. 통과 확인:** 같은 모델 테스트 재실행.
- [ ] **5. 커밋:** status/diff/log 확인 후 모델·테스트만 stage하고 검사해 `git commit -m "리포트 비교와 평가 실패 정보 정규화"`.

### Task 3: 선택적 탐색 구조와 실제 이벤트

**파일:** `src/agent_optimizer/report_model.py`, `src/agent_optimizer/runner.py`, `tests/test_report_model.py`, `tests/test_run_lifecycle.py` 수정.

**입출력:** 추가 이벤트 `candidate_created`에는 그룹·stage·candidate·parent·producer, `report_unit`에는 `unit_id`, 선택적 `parent_unit_id`, `unit_type`, `label`, `candidate_ids`가 있다. `group["structure"]`에는 `kind`, `units`, `edges`가 있으며 Optimizer 이름 분기는 없다. 기존 `context.emit`으로 `report_unit` 기록 가능하다.

- [ ] **1. 실패 테스트 작성:** 순서 있는 iteration, generation 0/1의 후보 다수, A→B/C→D merge와 알 수 없는 Optimizer의 fallback을 각각 합성 이벤트로 검사한다. 실제 runner에서는 `candidate_created`가 해당 평가 완료 전에 나오고 동일 그룹과 후보를 가리키는지 확인한다.

```python
self.assertEqual([u["unit_id"] for u in group["structure"]["units"]], ["g0", "g1"])
self.assertEqual(group["structure"]["edges"][-1]["parents"], ["B", "C"])
self.assertTrue(any(e["event"] == "candidate_created" for e in report["events"]))
```

- [ ] **2. 실패 확인:** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_report_model.py -v` 및 `-p test_run_lifecycle.py -v` 실행.
- [ ] **3. 최소 구현:** `GroupRunner.run`의 baseline 생성 직후와 `Context.propose` 성공 직후 후보 생성 이벤트를 기록한다. stage 시작/종료도 실제 시점에 기록한다. `report_unit`과 기존 공통 iteration 필드, 후보 부모를 unit/edge로 정규화하며 checkpoint 내부의 Optimizer별 내용은 해석하지 않는다. 기록할 수 있는 경우에만 새 실행 요약에 단조시계 기반 run wall time을 추가한다. 기존 trial·split·선택 경계는 바꾸지 않는다.

```python
context.emit("report_unit", unit_id="generation-1", parent_unit_id=None,
             unit_type="generation", label="Generation 1", candidate_ids=[candidate.id])
```

- [ ] **4. 통과 확인:** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_report_model.py -v`, 같은 명령의 `-p test_run_lifecycle.py -v` 및 `-p test_research.py -v`를 차례로 실행한다.
- [ ] **5. 커밋:** status/diff/log 확인 후 위 네 파일만 stage, 검사, `git commit -m "Optimizer 독립 탐색 구조 기록과 정규화"`.

### Task 4: 공통 모델에서 Markdown·JSON·HTML 호출

**파일:** `src/agent_optimizer/results.py`, `src/agent_optimizer/runner.py`, `src/agent_optimizer/cli.py`, `tests/test_results.py`, `tests/test_html_report.py` 수정.

**입출력:** 기존 `write_report(root, summary)`는 유지하고 선택적인 `report=None`을 받는다. `write_report_artifacts(root: Path, summary: dict) -> Path`는 모델을 한 번 생성해 `report.json`을 원자적으로 기록하고 Markdown/HTML에 전달한다. `write_html_report(root, summary, report=None)`도 직접 호출과 호환한다.

- [ ] **1. 실패 테스트 작성:** 기존 직접 Markdown 생성 테스트를 유지한다. 두 그룹 합성 실행에서 `report.json`의 각 선택 행이 summary와 같고 Markdown·HTML의 그룹별 비교·완료 건수가 일치하는지 확인한다. `agent-opt report RUN --html`을 구 실행에 적용해 파생 파일 재생성 후 원본 `summary.json`·CSV 경로가 바뀌지 않았는지 검사한다.

```python
model = json.loads((run / "report.json").read_text())
self.assertEqual(model["groups"][0]["selected"], summary["groups"][0]["selected"])
self.assertIn("rtl-solo", (run / "report.md").read_text())
self.assertIn("rtl-solo", (run / "report.html").read_text())
```

- [ ] **2. 실패 확인:** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_results.py -v`와 `-p test_html_report.py -v` 실행.
- [ ] **3. 최소 구현:** runner의 `finally`에서 기존 두 출력 호출을 공통 조정 함수로 교체한다. CLI `--html`도 같은 조정 함수를 쓰되 JSON 응답 `{html, status}`를 유지한다. Markdown은 정규화된 group 비교·건수·선택·실패·stage·usage만 사용하고 비신뢰 문자열의 Markdown 표 구분자를 이스케이프한다. 원래 partial 사용량을 합산 가능할 때만 보이던 규칙을 모델로 이동한다.

```python
def write_report_artifacts(root: Path, summary: dict) -> Path:
    from agent_optimizer.html_report import write_html_report
    from agent_optimizer.report_model import build_report
    report = build_report(root, summary)
    write_json(root / "report.json", report)
    write_report(root, summary, report=report)
    return write_html_report(root, summary, report=report)
```

- [ ] **4. 통과 확인:** `test_results.py`, `test_html_report.py`, `test_run_lifecycle.py` 각각 실행.
- [ ] **5. 커밋:** status/diff/log 확인, 이 작업 파일만 stage·검사, `git commit -m "공통 증거 모델에서 리포트 출력 생성"`.

### Task 5: 분석용 standalone HTML·CSS

**파일:** `src/agent_optimizer/html_report.py`, `tests/test_html_report.py` 수정. CSS가 커지면 `src/agent_optimizer/report_style.py`로 스타일 문자열만 분리한다.

**입출력:** `write_html_report(root, summary, report=None) -> Path`는 모델만 렌더링하고 기존 원자적 교체와 `write_session_index(root, entries)`를 유지한다.

- [ ] **1. 실패 테스트 작성:** 실제 minimal 실행에서 실험명·benchmark ID/경로·목적 방향·예산·합성 경고·그룹별 0→1 및 1→1·7개 완료 평가·solo의 c0002/team의 c0001·별도 test·candidate diff와 bundle 링크를 확인한다. caption/scope, 이스케이프된 긴 `<script>` feedback 원문과 `details`, 명시적 infrastructure 실패, manifest 없는 알 수 없는 Optimizer fallback을 검사한다.

```python
page = (run / "report.html").read_text()
self.assertIn("multi-agent-demo", page)
self.assertIn('scope="col"', page)
self.assertIn("<caption", page)
self.assertIn("Synthetic fixture", page)
self.assertNotIn('src="https://', page)
```

- [ ] **2. 실패 확인:** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_html_report.py -v` 실행.
- [ ] **3. 최소 구현:** 헤더/핵심 건수/metadata, 그룹별 baseline→selected, 분리된 held-out test, 구조형 journey 또는 fallback, 항상 있는 평가 표, 선택 후보 변경·평가 이력, 실패 원문·로그 참조, stage/checkpoint/usage, 재현 설정을 렌더링한다. 표 helper에 caption, scope, 숫자 정렬을 넣고 긴 메시지는 `details` 안에 전체를 남긴다. `safe_path`로 기존 상대 링크를 보존하며 HTML에서 선택·점수 재계산을 하지 않는다.

```python
def write_html_report(root: Path, summary: dict, report: dict | None = None) -> Path:
    if report is None:
        from agent_optimizer.report_model import build_report
        report = build_report(root, summary)
    temporary = root / "report.html.tmp"
    temporary.write_text(_render_report(root, report), encoding="utf-8")
    target = root / "report.html"
    temporary.replace(target)
    return target
```

- [ ] **4. CSS와 fallback:** 밝은 neutral 변수와 `prefers-color-scheme: dark`, system/mono 폰트, 최대 폭 1360px, 접히는 metadata grid, 국소 table 스크롤, 긴 code/error 줄바꿈, focus/hover/BEST/실패 의미색을 구현한다. CSP를 유지하고 JS 없이 모든 핵심 내용을 읽을 수 있게 한다. 구조가 없으면 이벤트/평가 표를 표시한다.

```css
:root{--background:#f8f9fa;--surface:#fff;--text:#20252d;--muted:#56606d;--border:#dce1e6}
@media(prefers-color-scheme:dark){:root{--background:#10141a;--surface:#171d24;--text:#e9edf2;--muted:#afb8c4;--border:#37424e}}
.table-scroll{max-width:100%;overflow-x:auto}pre,code{overflow-wrap:anywhere}
```

- [ ] **5. 통과·커밋:** HTML/Markdown/model 집중 테스트 후 status/diff/log를 살피고 관련 파일만 stage·검사, `git commit -m "독립형 실험 분석 리포트 개선"`.

### Task 6: 실제 생성·브라우저·통합 검증

**파일:** 검증에서 드러난 결함이 있을 때만 `src/agent_optimizer/report_model.py`, `src/agent_optimizer/html_report.py`, 해당 테스트 수정. `docs/architecture.md`에는 파생 `report.json`·범용 structure 이벤트 설명 추가.

**입출력:** 새 공개 API 없음. 모델과 실제 보고서의 값·상태·링크 일치 확인.

- [ ] **1. 전체 검증:** `PYTHONPATH=src python3 -m unittest discover -s tests -v` 및 준비된 환경에서 `make lint` 실행. 필요한 경우 `make setup ARGS="--core"`로 개발 환경 준비 후 lint. `PYTHONPATH=src python3 -m agent_optimizer run examples/minimal/experiment.toml`로 새 report 생성, 앞서 생성한 v1 실행에 `PYTHONPATH=src python3 -m agent_optimizer report runs/20260924T163428Z-eae573e5 --html` 수행.
- [ ] **2. 데이터 대조:** 새 실행의 `summary.json`, `report.json`, `report.md`, `report.html`, `candidate.json`, `changes.diff`를 실제로 대조한다. 그룹별 독립 비교, 평가 7건, solo c0002/team c0001, 목적 방향, test 분리와 링크를 확인한다. 기존 `test_html_report.py`의 실패 fixture를 실행해 오류·원문을 확인하고 없는 명령·git SHA는 미수집으로 남기는지 살핀다.
- [ ] **3. 브라우저 검증:** 생성된 독립형 HTML을 file URL 또는 로컬 서버로 열고 1440/1024/768px 스크린샷을 검사한다. `document.documentElement.scrollWidth <= innerWidth`, anchor·details·상대 diff 링크·긴 path와 에러·선택 결과 위치·console error를 확인한다. 실제 문제를 수정했다면 관련 테스트와 브라우저 검사만 다시 수행한다.
- [ ] **4. 문서·커밋:** `docs/architecture.md`에 v1 → model → 출력, 범용 unit 메타데이터와 fallback을 한국어로 기록한다. 상태/diff/log 확인 후 해당 파일만 stage·검사, `git commit -m "범용 리포트 구조와 검증 근거 문서화"`.
- [ ] **5. 마무리:** 기본 디렉토리·워크트리 상태와 `origin/main` 대비 전체 diff를 확인하고 작업 브랜치를 push한 뒤 `gh`로 PR을 만든다. 링크·실제 테스트 결과·브라우저 폭·미지원 항목을 보고하고 병합은 명시적 승인 후 진행한다.
