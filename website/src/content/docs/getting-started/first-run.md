---
title: 첫 실행
description: make setup-core로 7-trial 합성 데모를 실행하고 상태와 HTML 보고서를 확인합니다.
---

**목표:** 모델 키나 Docker 없이 코어 설치·정적 계획 진단·합성 보고서 읽기까지 확인합니다. 처음에는 아래 **7-trial 기본 경로**만 따라 하세요. 여기의 점수는 실제 모델이나 외부 Agent의 성능이 아닙니다.

## 준비물

- 저장소를 내려받은 **Mac 또는 Linux**, Git, `make`, 첫 설치에 필요한 네트워크. 명령은 **저장소 루트**에서 실행합니다.
- `make`가 없다면 첫 명령 대신 `sh scripts/bootstrap.sh setup --core`를 사용합니다. Python과 uv·개발 의존성은 코어 준비 과정에서 설치합니다.

## 1. 코어를 준비하고 데모 실행하기

```bash
make setup-core
make doctor-core
.venv/bin/agent-opt doctor --plan examples/minimal/experiment.toml --json
.venv/bin/agent-opt run examples/minimal/experiment.toml
```

`make setup-core`는 코어를 설치하면서 **첫 7-trial 합성 데모를 이미 한 번 실행**합니다. 마지막 `run`은 보고서를 직접 찾아보도록 같은 예제를 **별도 실행**으로 한 번 더 만드는 명령입니다. 각 실행의 `run_dir`은 다릅니다.

## 2. 예상 상태와 보고서 열기

`make doctor-core`는 `코어 개발 환경: 준비됨`(`AGENT_OPT_LANG=en`이면 `Core development environment: ready`)을 표시합니다. `doctor --plan`의 JSON에서는 `"scope": "plan"`, `"ready": true`를 확인하세요. 이는 **선택 자산과 설정의 정적 검사**이며 모델 호출이나 실제 채점 성공의 보증이 아닙니다.

마지막 `run`의 출력에서 `"status": "completed"`, `"trials_used": 7`, `"report_html"`에 표시된 경로(`…/runs/<run-id>/report.html`)를 확인합니다. 해당 파일을 파일 관리자에서 열거나 브라우저에 끌어놓으세요. 별도 웹 서버는 필요하지 않습니다. [결과 읽기](/agent-optimizer/getting-started/results/)의 화면도 이 **7-trial 합성 데모**이며 실행 ID와 실행 시간은 매번 달라집니다.

:::note[점수의 범위]
`examples/minimal/experiment.toml`은 두 합성 Agent와 `fixture` 하네스, 로컬 텍스트 과제로 배선을 확인합니다. `trials_used`는 예약된 평가 횟수이지 성공 횟수가 아닙니다. 점수 변화는 실제 Agent나 모델의 성능 향상이 아닙니다.
:::

:::tip[설치가 막히면]
프록시·사내 CA가 필요한 환경은 [네트워크 안내](https://github.com/wontaeJeong/agent-optimizer/blob/main/docs/network.md)를 확인하세요. `make doctor-core`로 부족한 코어 도구를 다시 진단합니다.
:::

## 선택: 내 손으로 2-trial 설정 만들기

위 7-trial 데모와 **다른 실행**입니다. 코어 준비 후 저장소 루트에서 아래 명령을 실행합니다. 예제 Agent·과제·평가기와 `baseline`만 사용하며 Docker·모델이 필요하지 않습니다. `init`은 같은 이름의 설정을 덮어쓰지 않으므로 재시도할 때 `--name` 및 뒤의 설정 경로를 함께 바꾸세요.

```bash
.venv/bin/agent-opt init --name guide-fixture \
  --agent examples/minimal/agents/solo \
  --command '{python} {agent_dir}/src/fixture_agent.py {task_dir}' \
  --editable configs/strategy.json \
  --dataset examples/minimal/tasks.json \
  --evaluator examples/minimal/evaluator.py:TextFixtureEvaluator \
  --optimizer baseline --yes
.venv/bin/agent-opt doctor --plan runs/configs/guide-fixture/experiment.toml --json
.venv/bin/agent-opt run runs/configs/guide-fixture/experiment.toml
```

`doctor --plan`의 `"scope": "plan"`, `"ready": true`와 `run`의 `"trials_used": 2`를 확인하세요. JSON의 **`report_html`**을 열면 위 **7-trial 캡처와 내용이 다른** 이 실행의 보고서를 볼 수 있습니다. 계획 진단은 정적 검사이며 실제 Agent 실행 성공과 별개입니다. 자신의 Agent를 연결하려면 [실험 구성](/agent-optimizer/guides/experiment/)으로 이동하세요.

## 다음 경로: ACE 프리셋 또는 내 Agent

Docker·고정 자산과 별도의 Agent/Optimizer 모델을 준비했다면 [ACE 프리셋 TUI/CLI 가이드](/agent-optimizer/getting-started/presets/)로 이동하세요. TUI는 프리셋 선택 화면에서 바로 시작하며 `ACE-RTL → OpenCode → GEPA 또는 Meta-Harness → CVDP`를 고르거나 같은 네 선택을 CLI로 지정하는 실환경 경로입니다. 첫 화면에서 `Esc`로 번호 메뉴에 들어가면 3번의 고정 `simple_feedback` ACE 예제를 선택할 수 있습니다. 모델·Docker 없이 선택 화면을 둘러볼 수도 있지만 ACE의 실제 실행에는 준비가 필요합니다.

자신의 소스·Harness·데이터셋·별도 평가기를 연결하려면 [실험 구성](/agent-optimizer/guides/experiment/)으로 이동하세요. 위 7-trial 캡처와 2-trial 직접 생성은 모두 합성 경로입니다.
