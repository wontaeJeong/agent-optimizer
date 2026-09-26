# 첫 실행

**목표:** 외부 모델·Docker 없이 설치, 코어 진단, 보고서 생성까지 확인합니다. 저장소에서 개발할 때는 Mac 또는 Ubuntu에서 Git과 `make`를 준비하고 저장소 루트에서 실행하세요. `make`가 없으면 `sh scripts/bootstrap.sh setup --core`로 시작할 수 있습니다. wheel만 설치한 사용자는 아래 대화형 경로의 선택형 예제를 별도로 준비할 수 있습니다.

## 1. 코어 준비

```bash
make setup-core
make doctor-core
.venv/bin/agent-opt --help
```

`setup --core`는 필요한 Python·개발 환경을 준비하고 **7 trial 합성 데모**를 실행합니다. 처음에는 의존성 다운로드가 필요할 수 있습니다. `make doctor-core`의 `코어 개발 환경: 준비됨`을 확인하세요(`AGENT_OPT_LANG=en`이면 `Core development environment: ready`). 코어 준비는 모델·공식 평가 데이터·Docker 이미지 준비 완료를 뜻하지 않습니다.

!!! tip "설치가 막히면"
    프록시·사내 CA가 필요한 환경은 저장소의 [네트워크 안내](https://github.com/wontaeJeong/agent-optimizer/blob/main/docs/network.md)를 확인하세요. `make doctor-core`로 부족한 코어 도구를 다시 진단할 수 있습니다.

## 2. 작은 실험 직접 만들기

아래 예제는 로컬 Agent와 직접 지정한 합성 과제·평가기만 사용합니다. TTY에서는
`.venv/bin/agent-opt init`으로 질문에 답하면 **설정만** 만들 수 있습니다. 명시적 인수가
필요한 자동화에서는 다음처럼 실행하세요. 동일한 이름으로 다시 만들 때는 `--name`과
이후의 설정 경로를 함께 바꾸세요. 기존 설정을 덮어쓰지 않습니다.

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

`doctor --plan`은 선언·선택 자산의 준비 상태를 읽기 전용으로 검사합니다. JSON의 `"scope": "plan", "ready": true`를 확인하세요. `run`이 완료되면 출력된 `run_dir`의 `report.html`을 브라우저에서 엽니다. 이 예제의 `trials_used`는 2입니다. 설정 점검 통과와 실제 Agent 실행 성공은 별개입니다.

## 3. 대화형 경로

```bash
.venv/bin/agent-opt tui
```

터미널에서 기존 `experiment.toml`을 선택하면 정적 계획 진단과 확인 뒤 실행합니다. 새 실험을
선택하면 Agent·editable 범위·Optimizer·**데이터셋**을 차례로 고르며, 실행 명령은
`command` 하네스에서만 입력합니다. TUI는 데이터셋을 자동 추천하지 않습니다.
**3번 ACE-RTL + CVDP 예제**를 직접 선택하면 Git 소스·driver·Docker 준비 내용을 보여주고
승인을 받은 뒤 작업공간에 고정 버전 자산을 준비합니다. 모델 값이 없으면 현재 세션에서만
숨김 입력을 받고, 계획 진단 뒤 실행을 다시 확인합니다. 저장소 없는 wheel 사용자도 같은 경로를 사용합니다.

```bash
agent-opt init --profile ace-rtl --workspace "$HOME/agent-opt-ace"
agent-opt prepare "$HOME/agent-opt-ace/experiment.toml"
# 모델 설정/키를 환경에서 제공한 경우에만:
agent-opt run "$HOME/agent-opt-ace/experiment.toml"
```

Python 3.11+, Git, uv, Docker Engine/Compose가 필요하고, macOS에서는 작업공간을
Docker Desktop에 공유할 수 있는 경로에 둡니다. `prepare --offline`은 검증된 캐시만
재사용하며 `run`은 자산을 자동 설치하지 않습니다.
선택적 `agent-opt doctor --plan "$HOME/agent-opt-ace/experiment.toml" --json`은
실제 모델/채점이 아닌 정적 계획을 진단합니다.
사용자 Agent와 자체 과제는
`--agent`·`--dataset <tasks.json>`·`--evaluator <file.py:Symbol>`로 연결합니다.
ACE 선택형 경로는 OpenCode 스킬 프로필의 실제 준비·공식 CVDP 평가이며 native ACE 실행은
아닙니다. [실험 구성](experiment.md)과
[결과 읽기](results.md)를 참고하세요.
