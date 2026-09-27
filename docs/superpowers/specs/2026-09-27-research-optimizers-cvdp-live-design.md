# 세 연구 Optimizer의 실행형 CVDP 예제 검증 설계

## 목적과 주장 범위

사용자가 선택한 **고정 CVDP** 평가 환경에서 GEPA·Meta-Harness·Ecdysis의 자체 구현을 각각 1회 실행한다. 현재 ACE/OpenCode·Claude 스킬 프로필은 역할 Python 파일을 실제로 호출하지 않으므로, 그 결과로 Meta-Harness/Ecdysis의 코드 변경 효과를 주장하지 않는다. 첫 연결에는 `examples/`의 작은 **실행형 Python Agent**를 사용한다. 목표는 실제 모델·실제 코드 변경·공식 채점·선택의 연결과 경계 확인이며 성능 개선이나 upstream 재현은 완료 조건이 아니다.

## 구성과 책임

- `examples/model-rtl-agent/`에 로컬 Agent manifest, `prompts/system.md`, 실행되는 `src/agent.py`, command Harness 프로필을 둔다. `CommandHarness`의 argv로 후보 스냅샷 안의 Python 파일을 호출한다. Agent는 기존 `request.json`의 공개 prompt와 `task/`의 이미 존재하는 공개 RTL target을 읽고, 환경에서 제공한 DeepSeek OpenAI 호환 모델로 RTL을 생성해 **정확히 `task/`의 target 파일만** 작성한다. 원본 Agent 파일을 수정하지 않으며 응답 텍스트·실행 코드·채점 함수를 혼동하지 않는다.
- GEPA는 editable `prompts/system.md`를, Meta-Harness와 Ecdysis는 editable `src/agent.py`를 수정한다. Agent가 매 trial 자신의 실행 Python 파일 해시를 기록하므로 후보 snapshot/`changes.diff`와 대조해 Python 코드 변경의 실제 호출을 확인한다. 프롬프트와 코드 변경은 같은 Agent 계약 안에서 일어나고 Optimizer끼리는 서로 호출하지 않는다. 세 stage는 모두 동일 baseline에서 독립 출발하며 다른 stage의 train 이력을 받지 않는다.
- Agent 모델은 예제 전용 `DEMO_AGENT_MODEL_BASE_URL`, `DEMO_AGENT_MODEL_ID`, `DEMO_AGENT_MODEL_API_KEY`를 받고 `agent_optimizer.models.ModelSettings`/`complete`의 기존 OpenAI 호환 전송 코드를 재사용한다. Optimizer는 기존 `AGENT_OPT_MODEL_*`에 사용자가 선택한 OpenAI 모델을 연결한다. 키는 실행 셸/자식 환경에만 있고 Agent source·실험 TOML·로그·Git에 남기지 않는다. 명시적 endpoint/모델/키가 없거나 프로토콜이 맞지 않으면 실패로 기록한다. `command` Harness의 미수집 Agent 전체 토큰·비용은 `None`이며 Optimizer 사용량은 제공된 값만 기록한다.
- 기존 CVDP provider가 고정 출처의 public tasks와 분리된 private 공식 evaluator/이미지를 준비한다. 예제의 작은 준비 경로는 선택한 provider 결과에서 task ID 순서로 **서로 다른 family의 train 2개·validation 1개**를 확정해 JSON·출처/해시·세 task ID를 저장하고, 이미 검증된 evaluator 구성으로 experiment를 생성한다. 점수나 private 자료를 보고 과제를 골라내지 않는다. 데이터셋 자체를 새로 추천하거나 private 평가 자산을 Agent workspace로 복사하지 않는다. 설치 entry point, 알고리즘 코어, 공식 채점 기준, 외부 SHA는 변경하지 않는다.

## 예산·실행·검증

- 선택된 CVDP 설정의 세 stage에 GEPA iterations=1/max_trials=5, Meta-Harness iterations=1/max_trials=4, Ecdysis rounds=1/max_trials=4를 명시하고, 전체 **최대 16 trial**, final_test=false, 벽시계 3600초/trial 180초/모델 제안 60초 상한을 둔다. 두 train 과제의 실패가 없으면 Ecdysis의 `no_failures`를 사실대로 기록하고 탐색 성공으로 표현하지 않는다. validation은 후보 선택에만 사용하며 private 채점 자료/최종 test는 Optimizer에 넘기지 않는다.
- 먼저 API-free 로컬 HTTP 모델 fixture로 Agent의 target 경로·모델 요청·실행 파일 해시/원본 보존·오류 상태를 검증한다. 실제 API가 필요한 검증 전에 CVDP provider 준비·doctor와 공식 평가기의 별도 정답/오답 smoke를 확인한다. 이후 사용자가 승인한 예산 안에서 한 번의 실환경 run을 수행하고 각 stage의 모델 제안, 실제 후보 diff, 해시가 다른 Python 실행, train·validation 공식 raw, frozen selection, nullable/partial 사용량을 대조한다.
- 실제 평가가 실패하거나 유효한 후보가 없으면 상태·원인과 마지막으로 검증한 경계를 날짜별 `docs/verification.md`, `docs/status.md`에 기록한다. 실행 결과가 1회·3과제에 한정됨을 밝힌다. native ACE 역할 루프·다른 팀 외부 Agent·전체 Verilog-Eval/Ubuntu·전체 sub-agent 사용량을 검증한 것으로 표시하지 않는다.

## 후속 관계

이 예제는 세 메서드의 **독립적인 작은 실 Agent 연결 검사**다. 이후 실제 팀 Agent 또는 native ACE를 대상에 연결하려면 해당 소스의 고정 버전·실행되는 수정 파일·모델/평가 책임과 예산을 별도 프로필로 검증한다. 단일 실험 병렬 scheduler는 다른 작업에서 진행 중이므로 다루지 않는다.
