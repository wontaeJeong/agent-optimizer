# 모델 기반 RTL Agent · 선택 CVDP 연구 예제

저장소에 포함된 작은 Python Agent의 `prompts/system.md`·`src/agent.py`를 수정 가능한
스냅샷으로 사용합니다. Agent는 공개 과제의 단일 `rtl/*.v`/`rtl/*.sv` target에
DeepSeek OpenAI 호환 completion으로 RTL을 쓰고, 외부 **공식 CVDP 채점기**가
결과를 판정합니다. GEPA·Meta-Harness·Ecdysis는 각각 같은 baseline에서 시작하는
자체 구현 stage이며 upstream 연구 코드의 실행이나 논문 재현이 아닙니다.

## 준비 및 실행 조건

Mac/Linux, Python 3.12 프로젝트 환경, Git, Docker daemon/Compose와 고정 CVDP
소스·데이터·driver·공식 평가 이미지가 필요합니다. 저장소 루트에서:

```bash
make doctor-core
.venv/bin/agent-opt datasets prepare cvdp
.venv/bin/agent-opt doctor --dataset cvdp --json
make setup
make smoke
.venv/bin/python examples/model-rtl-agent/prepare.py --dataset cvdp
.venv/bin/agent-opt doctor --plan runs/configs/model-rtl-research/experiment.toml --json
```

`make setup`/`make smoke`의 전체 ACE lock과 정답·오답 LFSR 검사는 **별도** 공식
평가기 근거입니다. 선택 CVDP provider는 `external/datasets/cvdp/evaluation-lock.json`과
`agent-optimizer-cvdp-eval:*` 이미지로 평가 자산만 준비합니다. `doctor --plan`의
`ready=true`는 정적 설정·자산 검사이며 Agent 인증, 모델 호출, 과제 채점은 하지 않습니다.
`prepare.py`는 이미 생성된 동명 설정을 덮어쓰지 않습니다.

승인된 실행에서 사용하는 환경 매핑(키의 실제 값은 환경/credential store에서만 전달):

| 역할 | 환경 변수 | 값 / 공급원 |
|---|---|---|
| Agent | `DEMO_AGENT_MODEL_BASE_URL`, `DEMO_AGENT_MODEL_ID`, `DEMO_AGENT_MODEL_API_KEY` | `https://api.deepseek.com`, `deepseek-flash`, DeepSeek 키 |
| Optimizer | `AGENT_OPT_MODEL_BASE_URL`, `AGENT_OPT_MODEL_ID`, `AGENT_OPT_MODEL_API_KEY` | `https://api.openai.com/v1`, 승인된 `OPENAI_MODEL`, `OPENAI_API_KEY` |

기존 `AGENT_OPT_MODEL_ENDPOINT`는 **실행 자식 환경에서만** 제거합니다. 앱은 로컬
`.env`를 자동 로딩하지 않습니다. 설정의 `max_trials=16`, GEPA 5 / Meta 4 /
Ecdysis 4, 두 train family·별도의 validation family와 `final_test=false`를
확인한 뒤 승인받은 **한 번의** 실행만 수행합니다:

```bash
.venv/bin/agent-opt run runs/configs/model-rtl-research/experiment.toml
```

모델 호출·공식 평가에는 비용과 시간이 들며 위 명령은 자동 재시도/이어하기가
아닙니다. 결과는 Git 제외 `runs/<run-id>/`의 `summary.json`, `events.jsonl`,
`<agent>/<harness>/trials/*/result.json`, `cvdp_evaluation/work/raw_result.json`
(실제 채점한 trial만), 후보 스냅샷·`changes.diff`·stage checkpoint에서 확인합니다.
Agent의 전체 토큰/비용은 미수집이면 `null`; Optimizer usage와 혼합하지 않습니다.
채점 결과가 없는 trial은 실패 점수 0으로 대체하지 않습니다.

## 2026-09-27 한정 실행 결과

Mac ARM64에서 승인된 DeepSeek `deepseek-flash` Agent와 OpenAI `gpt-5.4`
Optimizer로 **실험을 한 번 실행**했습니다. Optimizer 모델 제안은 GEPA·Meta
각 1회(총 2회)였고 Ecdysis 모델 호출은 없었습니다. `runs/20260927T161048Z-0acbf977`은
`synthetic=false`, **9/16 trial 사용 후 `status=error`**입니다. QAM16 train의
Agent 모델 요청 두 건은 60초 제한에서 `infrastructure_error`/`passed=null`,
공식 raw 없음으로 종료됐습니다. GEPA/Meta의 개별 validation은 공식 raw 각 1/1
통과했으나 Ecdysis가 공유 baseline의 무효 train 집계를 거부했으므로 **전체
선택 고정·최종 test는 없고 개선 결론도 없습니다**. Meta 후보는 모델 오류 시
빈 초기 target을 유지하는 fallback을 만들었고 해당 QAM16 train은 출력 누락
0점(공식 raw 없음)이었습니다. 실행별 원시 상태는
[검증 기록](../../docs/verification.md)을 참고하세요.

## 2026-09-28 두 번째 독립 실행

Agent 요청 120초, Optimizer 제안·검토 60초, trial 180초, 전체 최대 16 trial을
유지한 채 승인된 실험을 **새로 한 번** 실행했습니다. 첫 run은 그대로 보존됩니다.
`runs/20260927T165230Z-67533d5b`는 Mac ARM64에서 `synthetic=false`,
**11/16 trial `completed`**이며 모두 실제 공식 CVDP raw를 가집니다(통과 8,
오답 3). GEPA·Meta·Ecdysis는 각각 baseline에서 출발해 끝났고, 최종 고정
선택은 baseline `c0001`(validation `solve_rate=1.0`)입니다. Meta의 수정 코드
후보는 train 2/2·validation 1/1 통과했어도 baseline과 동점이라 선택되지
않았습니다. Ecdysis 후보는 train 1/2로 baseline보다 나아지지 않아 후보
validation을 실행하지 않았습니다. 최종 test는 설정대로 실행하지 않았습니다.
과제별 공식 raw·실제 후보 코드 SHA·Optimizer/Agent 사용량 구분은
[두 번째 실행 근거](../../docs/verification.md#2026-09-28-연구-optimizer-선택-cvdp-두-번째-독립-실모델-실행)에 있습니다.
