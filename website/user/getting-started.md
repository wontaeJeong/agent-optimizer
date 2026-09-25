# 첫 실행

**목표:** 외부 모델·Docker 없이 설치, 코어 진단, 보고서 생성까지 확인합니다. Mac 또는 Ubuntu에서 Git과 `make`를 준비하고 저장소 루트에서 실행하세요. `make`가 없으면 `sh scripts/bootstrap.sh setup --core`로 시작할 수 있습니다.

## 1. 코어 준비

```bash
make setup ARGS="--core"
make doctor ARGS="--core"
.venv/bin/agent-opt --help
```

`setup --core`는 필요한 Python·개발 환경을 준비하고 **7 trial 합성 데모**를 실행합니다. 처음에는 의존성 다운로드가 필요할 수 있습니다. `doctor`의 `Core development environment: ready`를 확인하세요. 코어 준비는 모델·공식 평가 데이터·Docker 이미지 준비 완료를 뜻하지 않습니다.

!!! tip "설치가 막히면"
    프록시·사내 CA가 필요한 환경은 저장소의 [네트워크 안내](https://github.com/wontaeJeong/agent-optimizer/blob/main/docs/network.md)를 확인하세요. `make doctor ARGS="--core"`로 부족한 코어 도구를 다시 진단할 수 있습니다.

## 2. 작은 실험 직접 만들기

아래 예제는 로컬 Agent와 직접 지정한 합성 과제·평가기만 사용합니다. 동일한 이름으로 다시 만들 때는 `--name`과 이후의 설정 경로를 함께 바꾸세요. 기존 설정을 덮어쓰지 않습니다.

```bash
.venv/bin/agent-opt init --name guide-fixture \
  --agent examples/minimal/agents/solo \
  --command-json '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]' \
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

터미널에서 Agent·실행 argv·editable 범위·Optimizer·**데이터셋**을 차례로 선택합니다. TUI는 데이터셋을 자동 추천하지 않습니다. 바로 사용자 실험을 구성하려면 [실험 구성](experiment.md)을, 보고서를 읽으려면 [결과 읽기](results.md)를 확인하세요.
