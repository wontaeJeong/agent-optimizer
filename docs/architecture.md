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
