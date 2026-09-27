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

## 선택: 실제 ACE-RTL/CVDP 경로

이 경로는 **선택형 실환경 실행**입니다. Python 3.11+, Git, uv, Docker Engine/Compose, 사용할 모델 설정·인증 및 공식 평가 환경이 필요합니다. macOS에서는 Docker Desktop에 공유 가능한 작업공간을 사용합니다. 코어 합성 결과로 대체되지 않습니다.

```bash
.venv/bin/agent-opt catalog list --kind agent
.venv/bin/agent-opt catalog show harness ace-opencode
.venv/bin/agent-opt init --name ace-gepa-guide --agent-preset ace-rtl \
  --harness-profile ace-opencode --optimizer gepa --dataset cvdp --yes
.venv/bin/agent-opt prepare runs/configs/ace-gepa-guide/experiment.toml
.venv/bin/agent-opt doctor --plan runs/configs/ace-gepa-guide/experiment.toml --json
.venv/bin/agent-opt plan runs/configs/ace-gepa-guide/experiment.toml
# 모델 설정과 인증을 환경/credential store에 준비한 후에만 실행:
.venv/bin/agent-opt run runs/configs/ace-gepa-guide/experiment.toml
```

`init --yes`는 선택 CVDP 데이터와 고정 ACE 소스·driver·Docker 이미지를 준비합니다. `prepare`는 같은 자산을 검증해 재사용하며 `run`은 부족한 자산을 자동 설치하지 않습니다. `init` JSON의 `experiment`를 뒤 명령에 쓰고, `run` JSON의 `run_dir`에서 `agent-opt report <run_dir> --html`로 보고서를 다시 생성하세요. **Meta-Harness**는 다른 `--name ace-meta-guide --optimizer meta_harness`로 같은 단계를 실행합니다. 기존 `init --profile ace-rtl --workspace PATH` pointer 경로도 유지됩니다. `doctor --plan`은 정적 검사이며 실제 모델·공식 CVDP 채점의 성공 여부는 **실행 근거와 보고서**에서 확인합니다. 이 ACE 예제는 OpenCode 스킬 프로필과 외부 공식 평가기 연결이지 native ACE 실행이 아닙니다. TTY에서는 `.venv/bin/agent-opt tui`에서 **5번 프리셋 선택형 새 최적화**를 고르고 `ACE-RTL → OpenCode → GEPA 또는 Meta-Harness → CVDP`를 각각 확정할 수 있습니다. [실험 구성](/agent-optimizer/guides/experiment/)에서 자체 Agent·데이터셋을 명시적으로 선택하는 법을 확인하세요.

5번의 `↑/↓`는 초점과 설명만 변경하고 `Enter`로 확정합니다. `Esc`/`b`는 이전 단계,
`Ctrl+C`는 취소입니다. 마지막 확인 화면에서 수정 대상과 두 모델 역할(`AGENT_OPT_MODEL`과
별도의 `AGENT_OPT_MODEL_BASE_URL`/`AGENT_OPT_MODEL_API_KEY`), 공식 evaluator, 준비 작업,
최대 trial/시간, 설정·보고서 위치를 확인합니다. `y` 전에 다운로드·빌드·모델 호출은 하지 않습니다.
ACE 두 알고리즘의 기본 예산은 각 9 trial/5760초, 공개 train 1·validation 1,
`final_test=false`이며 결과는 `runs/<run-id>/report.html`에서 확인합니다. GEPA는 후보의
`role-guidance.md`를 OpenCode prompt에 반영하고 Meta-Harness는 후보별 `agent_opt_scaffold.py`를
공개 과제에 실제 실행합니다. 둘 모두 자체 구현이며 실제 공식 CVDP/모델 성공·성능 향상 주장은
실환경 보고서로만 확인합니다.

OpenCode Agent 모델을 `openrouter/<모델>`로 선택하면 `OPENROUTER_API_KEY`를 환경에서 전달합니다.
`compatible/<모델>`이면 모델 API URL·키가 필요하며, 현재 고정 이미지의 plugin에서
`AGENT_OPT_MODEL_ID`와 선택자의 모델명이 같아야 합니다. Optimizer 모델 호출은
`AGENT_OPT_MODEL_BASE_URL`/`AGENT_OPT_MODEL_ID`/`AGENT_OPT_MODEL_API_KEY`를 사용합니다.

같은 5번에서 `rtl-solo`/`rtl-team → Fixture → Baseline`/`FileVariants → sample_text`를 고르면
모델·Docker 없는 합성 예제를 실행할 수 있습니다. 내 구성요소·기존 `experiment.toml`은
각 종류의 보조 선택지로 진입하고 고급 입력에서 다시 명시합니다. TUI 1번은 기존 설정,
2번은 고급 새 설정, 3번은 **고정 `simple_feedback` ACE 예제**, 4번은 과거 보고서 경로입니다.
자동화에는 비대화형 `init`·`doctor --plan`·`run`을 사용하세요.
