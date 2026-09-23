# 구조와 실행 흐름

데이터셋 명시적 선택·준비 → source snapshot → baseline validation → **각 Optimizer를 baseline에서 독립 실행**
→ stage별 validation winner → 기본적으로 모든 stage winner 비교 → 선택 고정 → 선택적 test → HTML/JSON 보고서.
Optimizer의 `evaluate/evaluate_batch/history`는 train 전용이며 `evaluate_validation`은 후보별
private 자료를 제외한 validation 수치만 반환한다. baseline train 측정은 cache를 공유할 수 있지만
다른 stage의 후보 trial은 history에 보이지 않는다. `final_stages`를 명시하면 최종 비교 대상을 제한한다.

| 모듈 (`src/agent_optimizer/`) | 책임 |
|---|---|
| `contracts.py` | Agent/Candidate/Task, RunRequest/ExecutionResult/Evaluation, Optimizer 계약 |
| `config.py`, `registry.py`, `catalog.py` | TOML·과제·호환성 검사, 내장 및 팀 manifest의 명시적 `file.py:Symbol` 등록 |
| `datasets.py`, `examples/benchmarks/` | 고정 Git source·명시적 dataset 준비, CVDP/Verilog-Eval 평가 자료의 공개/비공개 경계 |
| `runner.py` | Agent × Harness 그룹, 독립 stage, train/validation/test·예산 소유 |
| `sources.py`, `workspace.py` | 원본 보존, editable 스냅샷·hash·diff·계보·산출물 경계 |
| `process.py`, `models.py` | argv 프로세스/timeout, 모델 요청 전체 deadline worker |
| `objectives.py`, `results.py`, `html_report.py` | lexicographic keep=1·mean/sum 집계, 시간 이벤트·JSONL/Markdown/HTML/CSV |
| `setup_wizard.py`, `terminal_report.py`, `cli.py` | 사용자 dataset 선택·팀 컴포넌트 탐색·설정 생성·TUI/CLI 진행 화면 |

복수 Agent/Harness 전체 조합을 유지하며 모든 Agent가 모든 adapter를 지원해야 한다.
독립 Agent와 내부 sub-agent는 별개다. 조합별 후보·결과를 분리하며 임의 pair matrix는 없다.
팀 확장은 `experiments/<team>/`, 도메인 연결은 `examples/`에 둔다. 별도 pipeline/plugin manager는 없다.
여러 dataset을 선택하면 서로 다른 evaluator를 가진 독립 run을 session 안에서 순차 실행한다.
session index는 각 `report.html`을 연결하지만 이질적 점수를 하나로 순위화하지 않는다.

## 격리와 평가

- 원본 소스는 수정하지 않는다. 허용된 텍스트 변경만 `context.propose`로 생성하며 후보 metadata와
  실제 파일 hash를 cache 반환 전에도 검증한다. 직접 수정·위조 후보는 거부한다.
- 공개 prompt/files만 Agent workspace로 복사한다. private evaluation은 evaluator에만 전달한다.
  Docker Agent에는 평가 데이터/Docker socket을 마운트하지 않는다. local 실행과 신뢰한 in-process
  파일 플러그인의 논리적 분리는 OS 보안 격리가 아니다. `plan`도 Python plugin 코드를 로딩한다.
- evaluator가 실제 결과를 판정한다. Agent 자기보고를 성공 근거로 사용하지 않는다.
  환경 오류/unsupported가 포함된 split의 집계는 null이며 정상 행만 남겨 분모를 줄이지 않는다.
- ACE 스킬 프로필은 OpenCode 호출 후 외부 CVDP 평가다. native 역할 루프와 같지 않다.
  작은 RTL evaluator의 Yosys 합성도 임의 RTL을 정화하지 않으므로 입력 제한·private 검사가 필요하다.

## 재현 자료

manifest/source-lock에 설정·resolved commit/content hash·benchmark/plugin/helper hash를 남긴다.
후보 `candidate.json`/`changes.diff`, trial 로그/`result.json`, 버전·timestamp·dataset/iteration/phase를 가진
`events.jsonl`, `frozen_selection.json`, `summary.json`/`report.md`/`report.html`을 보존한다.
seed가 모든 backend의 결정성을 보장하지는 않는다.
모델 ID 등 재현 정보와 인증정보를 구분한다. 사용량은 관측된 값만 기록하고 전체/partial을 섞지 않는다.
`optimizer_usage`에는 Agent/Harness/stage/**optimizer** 이름이 포함되며 미보고를 0으로 해석하지 않는다.
checkpoint와 결과 저장은 resume가 아니다.

## 실행 종료와 부분 결과

summary 상태는 `completed`, `partial`, `no_eligible_candidate`, `budget_exhausted`, `interrupted`,
`source_error`, `error`다. 소스 확보부터 전역 wall-time을 사용하고 build/Harness/evaluator에는
남은 시간으로 제한한 timeout을 전달한다. 동기 Python Optimizer는 호출 전후 시간 검사이며 선점 실행이 아니다.

- 전역 예산 중단 trial은 interrupted/valid=false/passed=null이며 선택에서 제외한다.
  per-trial timeout만 소진하면 채점 가능한 실패(passed=0)다. 예약 실패는 trial 수에 더하지 않는다.
- 개별 stage.max_trials 소진 시 해당 stage만 `budget_exhausted`로 기록하고 다음 stage를 실행한다.
  일부 stage만 완료한 run은 `partial`이며 완료된 후보만 최종 validation 비교 대상이다.
- 실제 시작한 trial은 오류/Ctrl-C에도 result와 `trial_completed` 이벤트를 남긴다. 이 이름은 기록 종료이지 성공이 아니다.
- baseline 미완료면 null, 선택 전이면 selected=[]다. 완료한 평가/usage는 보존하고 미완료 split은 선택하지 않는다.
  test 중 중단되면 이미 고정한 validation 선택을 유지한다. 구현 오류를 합성 결과로 대체하지 않는다.
- CLI run: 완료 0, 예산/Ctrl-C/선택 불가 3, 설정/파일 오류 2. 예상 밖 구현 오류는 summary 저장 후 전파한다.

확장 API는 [adding-components](adding-components.md), 보류 기능과 복원 위치는 [FUTURE](FUTURE.md)를 따른다.
