# 최종 MVP D — 보고서 정합성·native 소비·반응형 검증

확인일: 2026-10-01. **D 소유 구현과 로컬 검증 완료. native 실실행·F producer·E 제품 서버 통합은 미검증이다.**

## 1. 작업 기준·조사

- 지정 워크트리: `.worktrees/final-mvp-d-20261001`, 브랜치 `feat/final-mvp-d-20261001`.
- 시작 HEAD/추적 기준 `origin/main`: `edbd2b8c7b05bdd63c352d02a7adf7652168d197`. 준비된 워크트리를 재사용했다.
- 기본 저장소는 `main...origin/main`. 시작 시 사용자 `.gitignore` 변경과 ZIP이 있었으며 수정하지 않았다.
- 지시 `D_REPORTS_VISUALIZATION.md`, 작업 `AGENTS.md`, P0 검증 문서 §4 C→D/F·§7을 읽었다. CodeGraph 인덱스가 없어 전용 read/grep으로 조사했다.
- 실제 흐름: `GroupRunner.trial`의 `result.json`·`trial_completed` → `candidate_evaluated` → 단계 summary/checkpoint → `frozen_selection.json` → final test → `build_report` → `write_report_artifacts`의 JSON/MD/HTML.
- `runner.py`, GEPA/Meta-Harness/Ecdysis의 실제 이벤트 생산 코드는 읽기 전용으로 대조했다. C 워크트리 `native_bridge.py:241–265`의 작업 중 payload 형식도 읽기 전용으로 확인했다. 이는 C 전체 구현 또는 native 실실행 검증이 아니다.
- 수정 파일: `report_model.py`, `html_report.py`, `report_style.py`, `report_visualizations.py`, `results.py`, 새 `tests/test_final_report.py`, 이 문서. CLI/TUI/runner/C bridge/공유 테스트 변경 없음.
- 공유 `.venv/bin/python` 실행만 사용했다. 설치·sync·다운로드·실모델 호출·하위 에이전트·push/PR 없음. 지정 워크트리와 임시 증거만 보존하고 한국어 로컬 커밋으로 인계한다.

## 2. 기존 기능과 실제 수정

기존 report v3는 이미 단일 정본, validation/test 분리, 그룹별 비교, unknown fallback, 다중 부모, escaping, offline SVG/CSS, 누락·부분 사용량·legacy 테스트를 제공했다. 재구현하지 않고 아래 차이만 수정했다.

1. **native optional 소비 누락:** `trial_completed.native_execution`을 v3 최상위 optional 목록으로 정규화하고 HTML/MD가 같은 자료를 표시한다. 내부 attempt/iteration·Agent 역할별 요청은 outer trial·trusted 평가와 분리한다. native wall time과 요청 duration을 합치지 않는다.
2. **단계별 최고점 혼합:** 종전 진행 곡선은 이전 단계 최고점을 다음 단계로 이어갔다. 단계별 leader를 공유 baseline에서 독립적으로 시작하고 SVG 선도 단계 경계에서 분리했다. 실제 기록된 validation 집계만 사용하며 train 탐색 곡선으로 표현하지 않는다.
3. **집계 유효성 누락:** HTML의 final/stage 집계에 partial/valid/미수집 의미를 표시한다. MD final test에도 상태를 표시하며 빈 metrics의 기록을 ‘최종 테스트 없음’으로 오인하지 않는다.
4. **알고리즘 근거 표시 누락:** `algorithm_trail`이 실제 이벤트의 iteration/role/review pass/accepted/status/split과 기록된 checkpoint frontier를 연결한다. GEPA·Meta-Harness·Ecdysis를 이름만으로 추측하지 않는다. baseline/file_variants에 임의 반복을 만들지 않고 unknown은 실제 이벤트·기존 계보·평가 표를 유지한다.
5. **비유한 JSON 지수:** JSON의 `1e999`가 Infinity로 읽혀 파생 JSON 쓰기를 막는 경로를 확인했다. 정규화 자료에서 null로 바꾸고 `nonfinite_values` 경고를 기록한다. 원본 summary/events는 변경하지 않는다. NaN/Infinity 리터럴 줄은 기존 invalid-line 정책을 유지한다.
6. **안전한 연결:** 임의 Evaluator artifact/루트 credential 파일은 HTML convenience 링크로 만들지 않는다. 자신의 trial/logs 아래 명시 stdout/stderr만 기존 로컬 링크를 유지한다. 상대경로·원본 절대경로를 지원하고 symlink·숨김 경로는 차단한다. native 근거는 경로 metadata만 표시하며 파일 내용을 읽거나 링크를 생성하지 않는다.
7. **큰 이벤트 기록:** 알고리즘 상세 표·generic 원본 이벤트 표시를 200건으로 제한하고 전체 자료가 `report.json`에 남는다고 명시한다. normalized JSON의 이벤트는 삭제하지 않는다.
8. **좁은 화면:** 긴 경로/목적 지표/그룹 설정은 정의 목록 전체 폭을 사용하고 480px 이하 설정은 한 열로 표시한다. 브라우저에서 native 표 첫 열이 23.44/26.38px로 눌리는 문제를 확인해 열 최소 폭·표 내부 스크롤·키보드 focus 영역을 추가했다. 수정 후 native 헤더 최소 폭은 75.25px이다.

## 3. C→D→F optional schema

공개 함수 시그니처 변경 없음. `report_schema_version=3` 유지. 기존 소비자는 아래 새 필드를 생략한 v3도 계속 읽을 수 있다.

### 입력

`trial_completed.native_execution`은 다음 최소형을 소비한다:

```json
{
  "schema_version": 1,
  "execution_mode": "native",
  "source_revision": "고정 revision",
  "source_hash": "소스 해시",
  "profile": "프로필 ID",
  "task_id": "outer 과제 ID",
  "candidate_hash": "후보 해시",
  "status": "completed",
  "attempts": [],
  "requests": [],
  "generated_files": [],
  "evidence_paths": [],
  "native_wall_time_seconds": null,
  "usage_status": "unreported"
}
```

- `attempts`: `attempt`, `iteration`, `status`, optional `hash`, `generated_files`, `evidence_paths` 또는 C의 단일 `evidence_path`.
- `generated_files`: 문자열 경로 또는 C의 `{path, sha256, evidence_path}` 항목. 출력은 문자열 경로 목록과 별도 `generated_file_hashes` 사전으로 정규화한다. 본문·임의 필드는 버린다. sha256은 64자리 hex일 때만 보존한다.
- `requests`: trial 안에서 유일한 `request_id`, `role`, `model`, `status`, `duration_seconds`, `input_tokens`, `output_tokens`, `cost_usd`. 중복/빈 ID는 합산하거나 새 요청으로 세지 않고 첫 기록만 남기며 경고한다.
- 비음수 유한 수만 사용한다. tokens/attempt/iteration은 정수이며 bool을 수로 취급하지 않는다. 없는 값은 null이다.
- schema/mode 불일치, outer task/candidate hash 불일치, summary에 없는 그룹은 native 자료만 제외하고 경고한다. outer 평가 자체를 삭제하거나 성공으로 바꾸지 않는다.
- 근거 경로는 run 상대 `<agent>/<harness>/trials/<trial>/logs/...` 또는 C의 logs 상대 `native/...`, `native`, `native-execution.json`을 소비한다. logs 상대 경로는 해당 outer trial 아래로 고정한다. 존재하는 일반 파일/디렉터리만 경로 metadata로 남기고 symlink·상위 이동·URL·숨김 경로를 거부한다. 디렉터리를 열람/공개하거나 평가 원문을 읽지 않는다.
- `prompt`, RTL 본문, private evaluator, 임의 중첩 필드는 native whitelist에서 제외한다. 알려진 식별자 필드의 값 자체가 이미 안전해야 하므로 F는 producer 경계에서 credential/본문 redaction을 반드시 유지한다.

### 출력

- 최상위 `native_execution: list[dict]`는 유효 payload가 있을 때만 추가한다. 없는 legacy run에 빈 그림·native 섹션을 만들지 않는다.
- 각 항목은 위 안전한 필드와 `group_key`, `evaluation_ref`, `trial_id`, `stage_id`, `candidate_id`, `split`, `generated_file_hashes`, `warnings`를 포함한다. `evaluation_ref`는 `<agent>/<harness>/<outer-trial>`이며 기존 evaluation과 연결된다.
- normalized `events`의 native 필드도 whitelist 결과로 교체한다. **디스크의 raw events/summary/result는 쓰지 않는다.** HTML/MD는 이 정본을 사용한다.
- `usage_status=complete`는 producer가 전체 수집을 선언하고 모든 요청의 input/output tokens·cost가 있으며 중복·수치/근거 경고가 없을 때만 인정한다. 수집된 0은 0으로 유지한다. 불완전한 complete 선언은 partial로 내리고 `usage_incomplete`를 기록한다. 관측값이 전혀 없는 요청은 기본 unreported이며 partial 선언은 partial로 유지한다.
- 전체 token/비용/native time을 추정·합산하지 않는다. 요금 근거 없는 cost는 producer가 null로 보내야 한다.
- `evidence.warnings` additive 코드: `native_execution_invalid`, `native_execution_warning`, `nonfinite_values`. 세 renderer가 같은 경고를 표시한다.
- 그룹별 optional 소비용 `algorithm_trail`은 `stage_id`, `optimizer`, `status`, 실제 `events`, 기록된 `frontier`만 가진다. 검토 완료·반성·merge·협업을 새로 만들어 넣지 않는다.

**F hook:** A 경로 변경 이후 `GroupRunner.trial`의 기존 `record` 작성 지점에서 C의 안전 검증된 sidecar 요약을 optional `native_execution`으로 추가하면 동일 record를 쓰는 `result.json`과 `trial_completed`가 연결된다. metrics에 중첩 JSON을 넣지 않는다. `execution`/artifacts/metric 이름·평가/선택 절차를 변경할 필요가 없다. D는 sidecar를 직접 찾거나 실행하지 않는다.

## 4. E allowlist·자산 인계

- **필수 공개 자산: 선택한 `report.html` 한 파일뿐.** inline CSS/SVG/시스템 폰트로 완결되며 JS/CDN/font/chart 요청 없음.
- CSS/JS/image 하위 자산 신규 추가 없음. `report.md`, `report.json`, `summary.json`, `events.jsonl`, manifest, diff, bundle, 로그, native 근거는 자동 공개 목록에 추가하지 않는다.
- 기존 summary/events/MD·후보 diff/bundle·명시 stdout/stderr 링크는 **검증된 로컬 run 열람용**이다. 상대 링크가 있다는 이유로 E가 공개 목록을 넓히면 안 된다. 서버에서 원본 링크가 거부되는 것은 공개 경계에 따른 동작이며 HTML 본문·집계·SVG·안전 metadata 열람에는 필요하지 않다.
- native `evidence_paths`는 href로 렌더링하지 않는다. arbitrary Evaluator artifact는 convenience 링크를 만들지 않는다.
- `write_report_artifacts(root, summary, language=...)`는 저장된 증거로 JSON/MD/HTML만 생성한다. source/frozen selection 수정·evaluator 재실행·후보 재선택 없음. 전용 회귀 테스트가 raw events/summary와 실제 경로 `agent/harness/frozen_selection.json`의 바이트 보존을 검증한다.
- F/E/G 수용 fixture는 `tests/test_final_report.py`의 `fixture`·`native_payload` 및 C 형태 `generated_files`/logs 상대 근거 테스트다. 모두 로컬 합성/계약 fixture이며 native 성공 증거가 아니다.

## 5. 정확한 검증 명령·결과

모든 명령 CWD: `/Users/wt.jeong/workspace/agent-optimizer/.worktrees/final-mvp-d-20261001`.

### 보고서 회귀와 Ruff

```bash
TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src AGENT_OPT_LANG=ko AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p '*report*.py' -v
TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src AGENT_OPT_LANG=ko AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_results.py -v
PYTHONDONTWRITEBYTECODE=1 /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m ruff check . --no-cache
git diff --check
```

- report: **98개 / 2.739초 / OK**(기존 79 + 신규 19). results: **16개 / 0.058초 / OK**. 고유 테스트 총 114개, 실패/skip 없음.
- Ruff: **All checks passed!**, `git diff --check`: 출력 없음, 종료 0.
- 실제 `frozen_selection.json` 경로로 바이트 보존 fixture를 정리한 뒤 같은 환경 prefix의 `-p test_final_report.py -v`를 추가 실행했다: **19개 / 0.162초 / OK**. 제품 코드는 앞선 98+16개 검증 이후 바뀌지 않았다.
- 처음 기존 79개 baseline은 2.586초 OK였다. 이 한 실행은 TMPDIR 지정 이전으로 기존 테스트의 자동 정리되는 기본 임시 디렉터리를 사용했다. 이후 검증은 모두 D 전용 TMPDIR로 고정했다. 개인 Home/이력/자격증명은 읽지 않았다.
- 첫 신규 9개는 구현 이전 9 failure로 누락/결함을 재현했다. 후속 빈 final metrics·outer identity·C 생성 파일 record·절대 stdout 경로도 수정 전 failure를 확인했다. 구현 중 한 번 발생한 MD 문자열 연결 SyntaxError와 후속 assertion 실패는 수정 후 최종 위 검사에서 해소됐다.
- 기존 테스트는 success/error run, legacy v3, missing/invalid events, null/zero/overflow/NaN 줄, 선택/테스트 없음, ties/improved/regressed, multi-group/session, unknown/branching/multi-parent, 긴 이름, HTML/Markdown injection을 검증한다. 신규 테스트는 optional native parity/중복/partial/null/본문 제외/근거 symlink/outer identity/C payload/집계 유효성/상한을 보완한다.
- 전체 저장소 unit는 재실행하지 않았다. P0의 unrelated 워크트리-local `.venv` baseline 오류와 report 검증을 구분한다. `make lint` 대신 공유 interpreter의 Ruff를 사용했다.

### 실제 runner로 생성한 합성 데모

```bash
TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src AGENT_OPT_LANG=ko AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml --output /var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/output/demo
```

종료 0, `status=completed`, `trials_used=7`. `summary.json`의 **synthetic=true**를 직접 확인했다. run은 `/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/output/demo/20260930T163954Z-bd391e66`; UTC run ID이며 확인일의 한국 날짜와 다를 수 있다. JSON/MD/HTML 모두 생성됐다. 외부 모델/실 Agent 성능 근거가 아니다.

## 6. 브라우저·offline·성능·캡처

브라우저 fixture 생성에 실제 실행한 명령:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -c 'from pathlib import Path; import json,time; from test_final_report import fixture,native_payload; from agent_optimizer.results import write_report_artifacts; base=Path("/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/output");
for name,lang in (("after","ko"),("native","ko"),("english","en"),("empty","ko"),("stress","ko")):
 root=base/name; summary,events=fixture(root)
 if name in ("native","english"):
  events[-1]["native_execution"]=native_payload(); events += [{"event":"optimizer_iteration_completed","agent_id":"agent","harness_id":"harness","stage_id":"search","iteration":1,"candidate_id":"chosen","accepted":True}]
 if name=="empty": summary={"status":"partial","synthetic":None,"groups":[]}; events=[]
 if name=="stress": events += [{"event":"optimizer_probe_completed","agent_id":"agent","harness_id":"harness","stage_id":"search","candidate_id":f"probe-{i}"} for i in range(1000)]
 (root/"events.jsonl").write_text("\n".join(map(json.dumps,events))); start=time.perf_counter(); path=write_report_artifacts(root,summary,language=lang); print(name, f"{time.perf_counter()-start:.4f}s",path.stat().st_size,"bytes")'
```

최종 생성: after 0.0116초/41,102 bytes, native 0.0039초/46,417 bytes, english 0.0034초/44,264 bytes, empty 0.0015초/23,721 bytes, stress **1,004 events / 0.0166초 / 166,597 bytes**. 한 머신·fixture의 관측값이며 일반 성능 보장이 아니다.

브라우저 로딩용 실제 명령:

```bash
/Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m http.server 18764 --bind 127.0.0.1 --directory /var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/output > /var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/browser-server.log 2>&1 &
```

- 임시 합성 fixture 전용 로딩 서버다. E 제품 서버/allowlist 검증으로 계산하지 않는다. 검증 후 `lsof -iTCP:18764 -sTCP:LISTEN -n -P`로 해당 PID 18946을 확인하고 `kill 18946`으로 종료했다.
- MCP Chromium Playwright에서 `http://127.0.0.1:18764/{before,after,native,english,empty,stress}/report.html`을 로딩했다. `file:` 직접 열기는 도구가 차단했고 require/import를 통한 파일 접근도 제한되어 loopback 로딩을 사용했다.
- 최초 성공한 `playwright_browser_navigate`가 기본 저장소 `.playwright-mcp/page-2026-09-30T16-23-08-418Z.yml`에 자동 snapshot 한 개를 생성했다. 시작 상태에는 없었고 해당 도구 응답의 파일명과 대조한 뒤 본 작업의 자동 산출물 한 파일만 제거했다. 이후 브라우저 실행은 `run_code_unsafe`와 절대 캡처 경로를 사용했다. 기본 저장소의 tracked 파일은 수정하지 않았다.
- offline 검증은 `page.content()` → `page.context().setOffline(true)` → `page.goto('about:blank')` → `page.setContent(markup)`로 실행했다. 모든 details를 열고 1440×1000/360×800 두 크기를 검사했다. **5종 × 2크기 모두 document scrollWidth=viewport width, script=0, 발생 request=[]**였다. 외부 서비스 없이 이미 로딩된 self-contained 문서가 렌더링됨을 확인한 것이며 OS `file://` 열람 자체를 검증한 것은 아니다.
- 키보드: native 요청 표 region에 `focus()` 후 `keyboard.press('ArrowRight')`, `waitForFunction(...scrollLeft>0)` 실행. 최종 focused=true, scrollLeft=2px. 표 내부 가로 스크롤만 있고 문서 전체 가로 넘침 없음.
- print: `page.emulateMedia({media:'print'})`에서 final test의 display=block 확인. 기존 print CSS 유지.
- 전후 동일 fixture는 native가 없는 같은 내용이다. 한글/영어/native/빈 자료/많은 이벤트를 별도 fixture로 검사했다.

캡처 위치(로컬 전용, 커밋 자산 아님):

`/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/captures/`

| 변경 전 | 변경 후 | 내용 |
|---|---|---|
| `before-desktop.png` | `after-desktop.png` | 1440×1000 개요 |
| `before-360.png` | `after-360.png` | 360×800 개요·설정 한 열 |
| `before-config-360.png` | `after-config-360.png` | 긴 경로·설정 정의 목록 |
| 해당 없음 | `native-offline-360.png` | optional native 내부 표·metadata |

## 7. 완료·남은 연결

- D 범위의 normalized v3·optional native 소비·HTML/MD/JSON 의미·실제 알고리즘 근거·안전 metadata·반응형·offline 회귀 검증 완료.
- requesting-code-review·verification-before-completion·finishing-a-development-branch 절차를 사용하되, 사용자 지시에 따라 자체 diff 검토·로컬 커밋·워크트리 보존으로 완료한다. 하위 에이전트/merge/push/PR 없음.
- **C/F:** 실제 sidecar producer 연결 및 실제 native 실행은 `not_run`. P0 hook과 위 C payload 대응 테스트를 사용해 통합해야 한다. C의 실모델·평가 결과로 이 fixture를 대체해 주장하지 않는다.
- **E/F:** HTML-only 공개 경계·제품 serve/TUI action은 D에서 구현/검증하지 않았다. 로컬 원본 링크와 static allowlist를 혼동하지 않는다.
- **G/I:** 전체 unit의 기존 환경 오류 해결 및 최종 통합 수용검증은 별도다. D 검사에는 차단된 외부 API/GPU/시뮬레이터/다운로드가 필요하지 않았다.

## 8. 수정 라운드 1 — 범위 한정 리뷰 반영

확인일: 2026-10-01. 시작 HEAD `cb63f694ed9cea4dc2fdc3cef0c0ecaf0ffe32ce`. `docs/verification/final-mvp-d-review-20261001.md`를 읽고 I-1·I-2·M-1을 실행 재현한 뒤 D 소비/정규화 범위에서 수정했다. 시작 시 리뷰 문서만 미추적 상태였고, 사용자의 명시 요청에 따라 해당 문서도 이번 의도된 로컬 커밋에 포함한다.

### 수정과 회귀 근거

- **I-1:** 집합 조회 이전에 `agent_id`/`harness_id`/`trial_id` 문자열 여부를 검사한다. 배열/객체 identity의 native payload는 `native_execution_invalid` 경고로 제외하며 기존 outer 평가·선택·renderer를 보존한다. native 경로의 NUL은 `unsafe_path`로 거부하고, 경로 검증/조회에서 발생하는 예상 가능한 `ConfigurationError`·`OSError`·`ValueError`는 사용할 수 없는 근거로 처리한다. 파일 내용을 읽거나 native 시간/토큰/비용을 추정하지 않는다. 미수집 비용·출력 토큰은 null을 유지한다.
- **I-2:** 공통 `_validation_eligible()`을 metric 비교와 visualization baseline에 사용한다. validation split·같은 Agent×Harness·valid=True·partial 아님을 모두 만족해야 최고점 초기값·baseline 표식·과제 비교에 사용한다. 부적격 baseline은 충돌 대조에서도 제외하여 같은 후보 ID의 실제 validation 기록까지 숨기지 않는다. baseline 수치 0.9가 train/test/다른 그룹이면 비교 baseline/Δ는 null이고, 실제 validation 0.3→0.5의 최고점도 0.3→0.5로 표시한다.
- **M-1:** Markdown 알고리즘 표에 `pass_number`의 검토 회차 열을 추가했다. iteration 1의 같은 역할이라도 회차 1/2를 구분하고 미수집 회차는 null로 표시한다. HTML/JSON과 같은 normalized 기록을 사용한다.
- 신규 covering test 6개: NUL(근거/생성 파일/attempt 근거), 배열·객체 outer identity, 파일 경로 접근 오류, 부적격 baseline의 곡선 억제 방지·최고점 혼입 방지, MD 검토 회차 1/2/null. identity 6종 및 baseline split/그룹/valid/partial 조합은 subtest로 검증했다.

### 정확한 명령·결과

CWD 및 공유 interpreter·전용 Home/cache/TMPDIR는 §5와 동일하다. 설치/sync·하위 에이전트·타 소유 수정·기본 저장소 수정·push 없음.

```bash
TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src AGENT_OPT_LANG=ko AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_final_report.py -v
TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src AGENT_OPT_LANG=ko AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p '*report*.py' -v
TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src AGENT_OPT_LANG=ko AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-d/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_results.py -v
PYTHONDONTWRITEBYTECODE=1 /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m ruff check . --no-cache
git diff --check
```

- 수정 전 첫 명령: **24개 / 0.196초 / FAILED(failures=8, errors=6)**. 실패/오류는 subtest 포함 건수다. NUL의 ValueError, 배열/객체 identity의 TypeError, 경로 PermissionError, 부적격 baseline의 곡선 억제, MD 회차 누락을 확인했다.
- 추가 I-2 재현: `PYTHONPATH=src:tests`와 같은 TMPDIR에서 `python -m unittest test_final_report.FinalReportTests.test_ineligible_unobserved_baseline_does_not_supply_validation_best -v` 실행, **1개 / 0.008초 / FAILED(failures=4)**. 다른 split/그룹 baseline 0.9가 실제 validation 0.3→0.5의 최고점으로 혼입됨을 확인했다.
- 각 항목 수정 후 해당 신규 테스트를 개별 실행해 I-1 **3개/0.047초 OK**, I-2 **2개/0.044초 OK**, M-1 **1개/0.013초 OK**를 확인했다.
- 최종 전용 테스트: **25개 / 0.221초 / OK**. 전체 report 패턴: **104개 / 2.829초 / OK**(기존 79 + 전용 25). results: **16개 / 0.066초 / OK**. 고유 테스트 총 **120개**, 실패/skip 없음.
- Ruff **All checks passed!**, `git diff --check` 종료 0/출력 없음. 제품 수정 이후 위 회귀를 실행했으며 문서 추가로 제품 코드를 바꾸지 않았다.
- 이번 라운드는 정규화/표시 데이터 회귀로 검증했다. 브라우저 재캡처·native 실실행·C/F/E 통합·전체 저장소 unit는 새로 실행하지 않았다. 앞선 캡처·실환경 미검증 범위는 §6–7의 기록과 구분한다.
