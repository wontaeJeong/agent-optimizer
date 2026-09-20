# 구조와 실행 흐름

Optimizer가 바꾸는 것은 **Agent를 구성하는 파일**입니다. Agent가 생성하는 RTL 등 과제 산출물과 다릅니다.
소스는 로컬 경로 또는 고정 Git commit으로 입력받고 실험 시작 시 한 번 확보합니다.
원본 repo에는 checkout/수정/commit/push를 수행하지 않습니다.

실험 흐름: source snapshot → baseline → optimizer 후보 생성 → train 평가(선택적) → validation 선택
→ 다음 stage → 선택 고정 → test 평가(설정 시) → 보고서.

- `contracts.py`: Agent, Candidate, Task, RunRequest, Evaluation, Optimizer 규약.
- `config.py`: TOML/과제 JSON 읽기, 키·지표·stage 순서 검증.
- `registry.py`: 내장 어댑터, 프로젝트 상대 `file.py:Symbol`, 설치 entry point 연결.
- `runner.py`: 단계 조합까지 담당. 별도 pipeline 엔진을 중복 구현하지 않는다.
- `sources.py`, `workspace.py`: 소스 확보, 허용 파일 변경, hash·diff·lineage.
- `process.py`: local/Docker 프로세스와 timeout.
- `objectives.py`, `results.py`: 지표 집계·선택·JSONL·Markdown 보고서.

Agent 여러 개는 독립된 최적화 대상이다. Agent 내부 sub-agent와는 별개다.
현재 실험은 agents × harnesses의 전체 조합이며, 지원하지 않는 조합은 설정 단계에서 거부한다.
서로 다른 호환성을 가진 Agent는 별도 실험으로 실행한다. 그룹마다 후보 계보와 결과를 분리한다.

## 평가

과제의 공개 prompt/files만 Agent workspace에 복사한다. evaluation은 evaluator에만 전달한다.
Docker 실행 시 평가 코드/데이터를 Agent 컨테이너에 마운트하지 않는다.
local 실행은 논리적 분리만 제공하며, 파일 접근 권한까지 막는 보안 격리는 아니다.
optimizer plugin 역시 신뢰한 프로세스 내부 코드다.

ACE-RTL/CVDP 연결은 examples 아래의 일반 플러그인이다. 코어에는 특별한 등록이나 분기가 없다.
첫 ACE 예제는 **OpenCode를 통한 ACE 스킬 사용**이다. ACE native runner의 자체 반복·평가·모델 호출과
동일한 실행으로 간주하지 않는다. native runner 연결 시 별도 profile과 신뢰한 evaluator를 연결한다.

## 재현성

manifest에 실험 설정, Agent resolved commit/content hash, 모델 환경변수 값, benchmark hash를 남긴다.
후보별 changes.diff와 candidate.json, trial별 로그/result.json, frozen_selection.json을 저장한다.
seed는 요청 메타데이터이며 모든 LLM backend의 결정성을 보장하지 않는다.
외부 환경 lock은 예제 setup에서 기록하고 과제 준비 시 metadata에 포함한다.

`scripts/dev.py`는 예제-local setup/checks를 연결한다. CVDP host driver만 별도 Python 3.12
환경에서 committed `requirements-cvdp-py312.txt`로 `uv pip sync`한다. 입력 upstream requirements
hash와 compiled lock hash를 확인/기록하며 offline setup 및 doctor/smoke/live 진입은 준비된 lock과
설치 목록이 달라지면 실패한다. offline은 패키지나 이미지를 네트워크로 보완하지 않는다.
공식 Dockerfile 내부 OS/도구 설치는 이 Python lock의 범위 밖이며 이미지 ID와 실제 도구 버전을 별도로 기록한다.

작은 RTL evaluator는 제한된 DUT 입력만 Yosys에 주고 성공 후 별도 디렉터리에서 생성 netlist와
private testbench를 Icarus로 검사한다. `$display`가 `$write`로 보존되는 실제 Yosys 동작 때문에
**합성만으로 임의 RTL을 정화한다고 가정하지 않는다.** 입력 정책의 system task 등 거부와
private 검사 완료(marker 한 줄 + 정상 종료)가 모두 필요하다. 이는 ACE/CVDP 공식 checker를 바꾸지 않는다.

## 실행 종료와 부분 결과

`summary.json`의 상태는 `completed`, `no_eligible_candidate`, `budget_exhausted`,
`interrupted`(Ctrl-C), `source_error`, `error`다. 소스 확보부터 전역 wall-time 예산을 사용한다.
소스/Optimizer 등 동기 Python 호출은 선점하지 않으며 호출 전후에 남은 시간을 확인한다.
소스 명령과 trial의 build/Harness/evaluator에는 남은 시간으로 제한한 timeout을 전달한다.

- 전역 deadline 때문에 평가가 중단되면 trial은 `status="interrupted"`, `valid=false`,
  `passed=null`로 기록하고 실험은 `budget_exhausted`로 끝난다. 정상적인 0점 후보로 선택하지 않는다.
  설정한 per-trial timeout만 소진된 경우에는 기존처럼 채점 가능한 실패(`passed=0`)다.
- 예약에 실패한 trial은 사용 횟수에 더하지 않는다. 실제 시도한 trial은 오류/Ctrl-C에도
  `result.json`과 `trial_completed` 이벤트를 남긴다. 이 이벤트명은 기록 종료를 뜻하며 성공을 뜻하지 않는다.
  `trial_id`, Agent/Harness/후보/과제/split/repeat, 사용량과 실행 결과(반환 전 중단이면 null)를 보존한다.
- 출력 경계 위반 등 예외는 `valid=false`, `status="error"`, `error_type`과 함께 기록한 뒤 다시 발생시킨다.
  구현 오류를 합성 결과나 정상 완료로 대체하지 않는다.
- 시작한 그룹은 부분 상태도 summary에 남는다. baseline 평가가 끝나지 않으면 `baseline=null`,
  선택 고정 전이면 `selected=[]`다. 진행 중 stage의 완료된 평가와 Optimizer 사용량을 보존한다.
  test 중 중단되면 이미 고정된 validation 선택과 완료된 test 행을 유지하고 미완료 test를 집계하지 않는다.
  소스 확보 중 종료되면 그룹 목록은 비어 있을 수 있다.
- `optimizer_usage` 이벤트는 `record_usage` 호출 시 Agent/Harness/stage ID와 함께 저장된다.
  보고하지 않은 사용량을 0으로 간주하지 않는다. report/rerank는 nullable baseline을 지원하며,
  rerank는 완료된 validation 집계만 사용하고 invalid/partial 행은 선택에서 제외한다.

CLI `run`은 정상 완료 시 0, 예산 소진·Ctrl-C·선택 불가 시 3을 반환한다. 설정/파일 오류는 2이며,
예상하지 못한 구현 오류는 summary를 저장한 뒤 호출자에게 전파된다. 결과 저장은 재시작 기능이 아니다.
