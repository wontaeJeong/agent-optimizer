---
title: 실험 구성
description: 내 Agent의 소스와 실행 명령, 수정 범위, 데이터셋과 별도 평가기를 명시적으로 연결합니다.
---

**먼저:** [첫 실행](/agent-optimizer/getting-started/first-run/)의 코어를 준비하고, 대상 Agent의 실행법과 과제·채점 기준을 정하세요. 직접 실행할 때는 로컬 Agent·과제·평가기의 위치가 필요합니다. 이 페이지의 `<경로>` 표기는 설명용이므로 실제 실행에는 자신의 값으로 바꿔야 합니다.

## 네 선택을 조회하고 재현하기

Agent는 수정할 **원본 소스**, Harness는 후보를 실행할 **프로필/adapter**, Optimizer는
후보를 만드는 **알고리즘**, Dataset은 공개 과제와 별도 **평가기**입니다.
`.venv/bin/agent-opt catalog list --kind agent`에서 목록을 보고, `--kind`를
`harness`, `optimizer`, `dataset`으로 바꿔 살펴볼 수 있습니다. `catalog show optimizer meta_harness --json`으로 제약을 확인합니다.
등록/구현 상태는 외부 모델·Docker 성공을 뜻하지 않습니다. TTY에서 `agent-opt tui` 5번의
네 선택은 [첫 실행의 CLI 프리셋 예](/agent-optimizer/getting-started/first-run/)와
같은 `experiment.toml` 설정 경로를 사용합니다. 각 `init` 출력 경로를 보관하면 CI에서도 재실행할 수 있습니다.

ACE-RTL + OpenCode(`ace-opencode`) + CVDP에서는 GEPA가 후보의
`skills/ace-rtl/references/role-guidance.md`를 고치고 ACE adapter가 **그 후보의 내용**을
OpenCode prompt에 붙입니다. Meta-Harness는 후보에 삽입된 활성 `.py` scaffold를 고치며
trial마다 공개 과제 전처리로 실행합니다. 두 경우 모두 외부 CVDP 평가기는 별도로 실행하고
private 자료는 후보에게 전달하지 않습니다. 기본 예약량은 공개 train/validation 1개씩,
3회 반복에서 9 trial이며 최종 test는 실행하지 않습니다. `init --yes`/`prepare`에는
다운로드·Docker 빌드가, `run`에는 모델/공식 평가의 시간·비용이 발생할 수 있습니다.
`run_dir`의 `summary.json`, `events.jsonl`, `candidates/*/changes.diff`, `report.html`에서
stage·후보·평가를 대조하고, 유효 후보가 없거나 점수가 같으면 개선으로 해석하지 마세요.

## 1. Agent 소스와 실행 범위 정하기

| 선택 | 지정 방법 | 경계 |
|---|---|---|
| 로컬 Agent | `--agent <로컬 Agent 경로>` | 원본을 보존하고 후보 스냅샷 생성 |
| 외부 Agent | `--agent <Git URL> --revision <전체 commit SHA>` | 전체 commit으로 소스 고정 |
| 실행 방법 | `--command 'python3 agent.py --input {task_dir}'` | `command` 하네스 전용 argv; 셸 확장·파이프·리다이렉션 없음 |
| 변경 범위 | `--editable configs/strategy.json` | 실제 허용 파일만; 테스트·평가 기준 변경 불가 |

지침 파일을 사용하는 구성은 `--prompt-file`도 지정합니다. OpenCode 등의 전용 하네스에는 `--command`를 전달하지 않습니다. ACE-RTL은 준비된 [프로필](https://github.com/wontaeJeong/agent-optimizer/blob/main/examples/ace-rtl/experiment.toml)을 이용합니다. 역할별 데이터 흐름은 [동작 원리](/agent-optimizer/concepts/overview/)에서 볼 수 있습니다.

## 2. 데이터셋과 평가기 선택하기

**데이터셋은 사용자가 직접 선택**하며 자동 추천하지 않습니다. 아래 표는 선택 가능한 입력의 예시이지, 그대로 한꺼번에 실행할 명령이 아닙니다.

| 입력 예시 | 준비물과 채점 |
|---|---|
| `--dataset cvdp` | 고정 버전 CVDP 자산, Docker 기반 공식 평가 환경 |
| `--dataset verilog-spec` 또는 `--dataset verilog-completion` | 고정 버전 Verilog-Eval 자산, 별도 평가 환경 |
| `--dataset path/to/tasks.json --evaluator path/to/evaluator.py:Evaluator` | 사용자 과제와 **별도 구현한** 채점기 |

공개 과제 입력과 private 평가 자료는 Agent 작업공간에서 분리합니다. 사용자 evaluator가 `passed` 외의 지표를 반환하면 `--metric <이름> --direction maximize|minimize`를 지정합니다. 두 개 이상의 데이터셋은 **각각 독립된 실험·보고서**를 만들며 점수를 한 순위로 합치지 않습니다.

## 3. Optimizer·모델 지정하기

먼저 `--optimizer baseline`으로 연결을 확인하고 필요할 때 `--optimizer gepa --optimizer meta_harness`처럼 독립 stage를 추가합니다. GEPA·Meta-Harness·Ecdysis는 저장소의 **자체 메서드 구현**으로 upstream 논문 재현 결과가 아닙니다. train 과제와 수정할 텍스트/.py 파일 및 모델 API가 필요합니다. `file_variants`에는 변형 파일/설정이 필요합니다. stage는 모두 공통 baseline에서 시작합니다.

모델을 쓰는 구성은 환경/credential store에 `AGENT_OPT_MODEL_BASE_URL`(기본 URL, `/chat/completions` 제외)과 `AGENT_OPT_MODEL_API_KEY`를 설정합니다. 필요하면 `AGENT_OPT_MODEL_ID`를 지정하세요(생략 시 `glm5.3-flash`). TUI는 없는 값을 세션에서만 묻습니다. OpenCode 하네스의 `AGENT_OPT_MODEL`은 별도 선택자입니다. 키를 설정 파일이나 Git에 저장하지 마세요. [첫 실행](/agent-optimizer/getting-started/first-run/)의 합성 예제에는 모델이 필요하지 않습니다.

## 4. 계획 진단 → 실행 → 결과 확인

아래는 **첫 실행 페이지에서 `guide-fixture`를 만든 뒤에만** 복사해 실행할 수 있는 예시입니다. 새 설정을 만들지 않았다면 먼저 [2-trial 설정 만들기](/agent-optimizer/getting-started/first-run/#선택-내-손으로-2-trial-설정-만들기)를 완료하세요.

```bash
.venv/bin/agent-opt datasets list
.venv/bin/agent-opt doctor --plan runs/configs/guide-fixture/experiment.toml --json
.venv/bin/agent-opt run runs/configs/guide-fixture/experiment.toml
```

**예상 결과:** `doctor --plan`은 선언과 선택 자산을 읽기 전용으로 점검하고 JSON에 `"scope": "plan"`과 준비 여부를 표시합니다. 이는 실제 모델 호출·채점 성공과 별개입니다. `run`의 `run_dir`에서 [결과 읽기](/agent-optimizer/getting-started/results/) 순서로 보고서를 확인하세요. 새 데이터셋은 선택 자산의 준비 상태를 따로 확인합니다. 시간과 횟수는 `init`의 `--max-wall-time-seconds`, `--max-trials`, `--trial-timeout-seconds`로 지정합니다.

TTY에서는 `.venv/bin/agent-opt init`으로 설정만 만들거나 `.venv/bin/agent-opt tui` 1번에서 최근 생성 설정 또는 직접 경로를 선택할 수 있습니다. 2번은 새 실험, 3번은 기존 ACE 예제, 4번은 이전 결과 경로, 5번은 네 프리셋 선택입니다. 팀 구현을 추가하려면 [컴포넌트 연결](/agent-optimizer/developer/components/)로 이동하세요.
