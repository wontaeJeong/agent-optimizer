# 실험 구성

**직접 지정할 항목:** Agent 소스, 수정 가능한 파일, 데이터셋과 채점 기준, 선택한 하네스의
실행 방법. 기존 실험은 `.venv/bin/agent-opt tui`에서 설정 파일을 선택하고, 새 설정만
만들려면 `.venv/bin/agent-opt init`을 TTY에서 실행하세요. 비대화형 설정 생성은 저장소
루트에서 명시적 옵션과 `--yes`로 수행합니다.

## Agent와 실행 범위

- 로컬 소스는 `--agent <로컬 Agent 경로>`, 외부 소스는 `--agent <Git URL> --revision <전체 commit SHA>`로 고정합니다. 원본은 수정하지 않고 스냅샷에서 후보를 만듭니다.
- `command` 하네스의 실행은 `--command 'python3 agent.py --input {task_dir}'`처럼 적습니다.
  인용을 분리한 argv 배열로 저장하며 셸 변수 확장·파이프·리다이렉션을 실행하지 않습니다.
  OpenCode 등 자체 실행 하네스에는 명령을 전달하지 않습니다. ACE-RTL은 준비된
  `examples/ace-rtl/experiment.toml`의 하네스 프로필을 재사용합니다.
- `--editable configs/strategy.json`은 실제로 바꿀 수 있는 파일만 적습니다. 허용 범위 밖 파일, 테스트, 평가 기준은 Optimizer가 수정할 수 없습니다. 지침 파일을 쓰는 경우 `--prompt-file`도 지정할 수 있습니다.

## 데이터셋과 평가기

데이터셋은 **사용자가 명시적으로 고릅니다.** 다음은 가능한 입력 형태를 보여 주는 예이며 자동 추천 목록이 아닙니다.

| 입력 | 준비/채점 |
|---|---|
| `--dataset cvdp` | 고정 버전 CVDP 자산을 선택적으로 준비. Docker 기반 평가 환경 필요 |
| `--dataset verilog-spec` 또는 `--dataset verilog-completion` | 고정 버전 Verilog-Eval 선택 자산 준비. 전용 평가 환경 필요 |
| `--dataset path/to/tasks.json --evaluator path/to/evaluator.py:Evaluator` | 사용자가 과제와 별도 채점기를 제공 |

공개 과제와 private 평가 자료는 Agent workspace에서 분리합니다. 사용자 evaluator가 `passed` 이외 지표를 반환하면 `--metric <이름> --direction maximize|minimize`도 지정하세요. 두 개 이상의 데이터셋을 선택하면 각각 독립 실험으로 실행하며 서로 다른 채점기의 점수를 하나의 순위로 합치지 않습니다.

## Optimizer와 모델

`--optimizer baseline`으로 연결을 확인한 다음 필요하면 `--optimizer gepa --optimizer meta_harness`처럼 여러 독립 stage를 지정합니다. GEPA·Meta-Harness·Ecdysis는 저장소의 **자체 구현**이며 논문 실험을 그대로 재현한 것은 아닙니다. 각 stage는 공통 baseline에서 출발합니다.

모델을 사용하는 구성에는 `AGENT_OPT_MODEL_BASE_URL`(기본 URL; `/chat/completions` 제외)과 `AGENT_OPT_MODEL_API_KEY`를 환경 또는 credential store에 설정합니다. TUI에서는 값이 없을 때 URL·모델 ID·키를 현재 세션에만 묻습니다. `AGENT_OPT_MODEL_ID`를 생략하면 `glm5.3-flash`가 사용됩니다. OpenCode 하네스의 `AGENT_OPT_MODEL` 선택자는 별도 설정입니다. 키를 실험 설정이나 Git에 저장하지 마세요. 모델 없는 합성 예제에는 필요하지 않습니다.

## 실행 전에 확인

```bash
.venv/bin/agent-opt datasets list
.venv/bin/agent-opt doctor --plan runs/configs/guide-fixture/experiment.toml --json
.venv/bin/agent-opt run runs/configs/guide-fixture/experiment.toml
```

위 `guide-fixture`는 [첫 실행](getting-started.md)에서 만든 설정의 예입니다. 새 데이터셋을 고른 경우 해당 자산의 준비/진단 상태를 별도로 확인하세요. `doctor --plan`은 실제 모델 호출이나 채점 성공을 보증하지 않습니다. 시간·trial 수가 필요한 경우 `init`의 `--max-wall-time-seconds`, `--max-trials`, `--trial-timeout-seconds`를 조정할 수 있습니다. 결과는 [결과 읽기](results.md)에서 확인합니다.
