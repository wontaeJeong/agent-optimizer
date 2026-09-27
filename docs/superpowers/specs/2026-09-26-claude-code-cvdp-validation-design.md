# Claude Code 하네스와 DeepSeek–CVDP 첫 실검증 설계

## 결정과 범위

첫 묶음은 범용 `claude_code` 하네스를 wheel에 포함하고, 별도 ACE-RTL 스킬 프로필에서 DeepSeek 모델과 공식 CVDP 채점까지 실제로 실행한다. 선택한 데이터셋은 CVDP이며 첫 실행 상한은 4 trial이다. 같은 저장소의 OpenCode 프로필, native ACE runner, 다른 연구 Optimizer의 성능 검증과 결과를 혼동하지 않는다.

외부 CLI를 `command`로 감싸는 대신 내장 하네스를 택한다. CLI 결과의 오류·사용량을 명시적으로 해석해야 하기 때문이다. 팀 파일 플러그인만 제공하면 소스 밖 wheel에서 바로 선택할 수 없으므로 범용 어댑터는 코어에 둔다. 도메인별 ACE 지침과 예제 구성은 `examples/ace-rtl/`에 둔다.

## 구성과 데이터 흐름

1. `src/agent_optimizer/harnesses/claude_code.py`에 `HarnessAdapter` 계약을 구현하고 `Registry`에 `claude_code`를 등록한다. `agent-opt plugins`, 대화형 하네스 목록, `init --harness claude_code`가 기존 등록·설정 생성 흐름을 사용한다. 설치한 wheel은 Python 어댑터만 포함하며 `claude` 실행 파일을 설치하거나 자체적으로 업데이트하지 않는다.
2. 일반 실험은 기존 `AgentSpec`의 고정 Git 또는 로컬 소스, editable, 공개 `task_dir`와 기존 evaluator를 그대로 사용한다. 로컬 trial 작업공간을 `cwd`로 하여 `claude -p`를 argv 배열로 실행하고, `--output-format stream-json`의 원본 로그를 보존한다. `process.execute`의 process-group timeout과 `shell=False`를 재사용한다. 실제 과제 산출물을 evaluator가 task 디렉터리에서 읽으며, CLI의 자기보고는 점수로 쓰지 않는다.
3. 일반 하네스는 특정 provider나 모델을 강제하지 않는다. 첫 검증에서는 사용자의 로컬 `.env`에 있는 DeepSeek 키를 **실행 셸에서만** `ANTHROPIC_AUTH_TOKEN`에 연결하고, 공식 Anthropic 호환 주소 `https://api.deepseek.com/anthropic`와 명시적 DeepSeek 모델을 전달한다. 앱은 `.env`를 자동 로딩하지 않으며 키·토큰·실제 URL의 자격증명 값은 argv, 예제 파일, 결과물, 커밋에 기록하지 않는다. 실행 후 모델과 endpoint의 비밀이 아닌 식별 정보만 검증 기록에 남긴다.
4. ACE 예제에는 기존 `with_ace_guidance`를 재사용하는 Claude Code용 별도 프로필/실험 경로를 둔다. 선택한 CVDP는 기존 고정 출처의 provider가 준비하고 기존 공식 evaluator가 분리된 private 자산을 채점한다. 기존 OpenCode 고정 프로필은 그대로 구별한다. 예제에서는 준비된 데이터·평가 이미지의 해시/ID와 고정 ACE 소스 commit을 사용하며, 미준비 자산을 합성 결과로 대체하지 않는다.

## 버전, 실패, 사용량

- 범용 하네스는 외부 `claude`의 실제 버전을 검사·기록하되 전체 wheel 사용자를 2.1.261로 제한하지 않는다. 이번 ACE–CVDP 재현 프로필만 실제 확인한 **Claude Code 2.1.261**과의 일치를 요구하고 다른 버전이면 모델 호출 전에 명시적으로 실패한다. 새 버전은 별도 검증 후 예제 pin을 갱신한다.
- 명령/인증/프로토콜/설치 오류와 구조화된 오류 이벤트는 구별해 기록하며, 인증·환경 실패는 `infrastructure_error`, 평가 지표 `None`으로 처리한다. 과제 실행 자체의 실패와 trial timeout은 기존 runner의 종료·예산 계약을 유지한다. 정상 종료만으로 RTL 통과를 주장하지 않고 실제 CVDP evaluator 결과를 사용한다.
- JSON에서 확인 가능한 호출별 토큰·비용만 `harness_reported_*` partial 지표로 표시한다. sub-agent를 포함한 전체 Agent 사용량이 확인되기 전에는 `agent_tokens`와 `agent_cost_usd`를 `None`으로 유지한다. 파싱 불가 로그는 성공으로 추정하지 않고 원본 로그와 오류 근거를 남긴다.

## 첫 실검증과 완료 기준

- 먼저 mock CLI와 격리된 fixture로 argv, 환경 전달, 2.1.261 예제 버전 차단, timeout, 인증 실패, 결과 이벤트 파싱, 원본/editable/private 평가 경계를 회귀 검사한다. 코어 전체 테스트와 lint, wheel 설치 후 하네스 등록/선택을 검사한다.
- CVDP를 명시적으로 준비·진단한 후 실제 DeepSeek–Claude Code로 공개 train 1개와 validation 1개를 사용한다. baseline train/validation과 한 번의 train 근거 수정 후보 train/validation으로 **최대 4 trial**, `final_test=false`로 실행한다. 성공의 기준은 실제 Claude 도구 호출·생성한 과제 산출물·공식 raw 채점 결과·비교 가능한 보고서이며, 개선 수치 자체를 보장하지 않는다. 실패도 실제 명령·환경·원인을 구분해 `docs/verification.md`와 `docs/status.md`에 기록한다.
- 저장소 최초 코어 기준 검사는 `make setup-core` 후 unittest **총 628건(성공 613, 외부 도구 조건부 skip 15)**이었다. 이번 실검증과는 별도 증거로 둔다.

## 후속 묶음과 경계

두 번째 묶음은 저장소 예제와 실제 평가를 사용한 GEPA·Meta-Harness·Ecdysis별 제한 예산 검증이다. 세 번째 묶음은 기존 결과에서 보고서로 이동하는 최소 실행 이력 조회와 호환 조합 중 원하는 Agent–Harness 쌍을 명시하는 기능이다. 같은 실험 내부 병렬화는 진행 중인 다른 작업과 충돌하므로 이 묶음에서 수정하지 않는다. 외부 팀 Agent 성능, native ACE, Verilog-Eval 전체 Ubuntu x86_64 실행, 전체 sub-agent 사용량은 첫 4-trial의 결과로 검증 완료라고 표기하지 않으며 해당 환경·대상·실행 근거가 갖춰졌을 때 별도 검증한다.

참고: [Claude Code headless CLI](https://code.claude.com/docs/en/headless), [DeepSeek의 Claude Code 연동](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code), [고정 외부 출처](../../SOURCES.md).
