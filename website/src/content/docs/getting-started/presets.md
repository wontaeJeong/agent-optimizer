---
title: ACE 프리셋 TUI/CLI
description: ACE-RTL·OpenCode·GEPA 또는 Meta-Harness·CVDP를 선택하고 준비, 실행, 공식 평가 근거를 확인합니다.
---

**이 경로는 실제 모델·공식 CVDP 평가를 사용할 수 있는 선택형 데모입니다.** 모델·Docker 없이 CLI/보고서를 먼저 확인하려면 [7-trial 합성 첫 실행](/agent-optimizer/getting-started/first-run/)부터 시작하세요. 명령은 코어 설치를 마친 **소스 저장소 루트**에서 실행합니다.

## 무엇을 선택하나요?

좁은 화면에서는 표 안을 좌우로 밀어 나머지 열을 읽으세요.

| TUI 선택 | CLI 값 | 역할과 실제 수정 대상 |
|---|---|---|
| Agent: ACE-RTL | `--agent-preset ace-rtl` | 고정 Git 소스의 ACE **스킬 프로필**. native ACE runner가 아닙니다. |
| Harness: OpenCode | `--harness-profile ace-opencode` | `ace_opencode` adapter가 후보를 공개 과제에 실행합니다. |
| Optimizer: GEPA **또는** Meta-Harness | `--optimizer gepa` **또는** `--optimizer meta_harness` | GEPA는 후보 `skills/ace-rtl/references/role-guidance.md` 내용을 OpenCode prompt에 넣습니다. Meta-Harness는 후보 `skills/ace-rtl/scripts/agent_opt_scaffold.py`의 `prepare_task`를 공개 과제 선행 단계에서 실행합니다. 각각 **별도 설정·실행**입니다. |
| Dataset: CVDP | `--dataset cvdp` | 고정 공개 train 1·validation 1, 별도 공식 `cvdp` evaluator; `final_test=false`입니다. |

두 Optimizer는 연구 이름을 쓴 **자체 구현**이며 upstream 방법이나 native ACE의 완전 재현이 아닙니다. 다른 Agent·Harness·Dataset이 카탈로그에 보여도 이 네 선택과 임의로 호환되지는 않습니다.

## 준비와 모델 역할

Mac 또는 Linux에서 Git, Python 3.11+, uv, Docker Engine/Compose(맥은 공유 가능한 Docker Desktop 작업공간), 첫 준비에 필요한 네트워크와 고정 ACE/CVDP 소스·driver·이미지 준비가 필요합니다. `make setup-core`로 `.venv`를 만든 뒤 아래 경로를 따라가세요. 다운로드/빌드·실행 비용과 시간은 환경에 따라 다릅니다. 프록시·CA 및 Docker 준비는 [개발 명령 기준](https://github.com/wontaeJeong/agent-optimizer/blob/main/docs/development.md)과 [네트워크 안내](https://github.com/wontaeJeong/agent-optimizer/blob/main/docs/network.md)를 확인하세요.

| 역할 | 환경 설정 | 확인할 것 |
|---|---|---|
| OpenCode **Agent** 모델 | `AGENT_OPT_MODEL` | `openrouter/<모델>`에는 `OPENROUTER_API_KEY`가 필요합니다. `compatible/<모델>`은 모델 API URL·키가 필요하고 현재 고정 OpenCode 이미지의 plugin에서는 `<모델>`이 `AGENT_OPT_MODEL_ID`와 일치해야 합니다. TUI에 `deepseek-flash`처럼 접두어 없는 ID를 입력하면 compatible 모델로 연결하며, ID가 다르면 변경 여부를 확인합니다. |
| **Optimizer** 모델 | `AGENT_OPT_MODEL_BASE_URL`, `AGENT_OPT_MODEL_API_KEY`, 필요하면 `AGENT_OPT_MODEL_ID` | 모델 API의 기본 URL(`/chat/completions` 제외), 인증과 ID를 설정합니다. Agent 모델 선택자와 별개입니다. |

키는 환경 또는 credential store에만 두세요. `.env`를 자동 로딩하거나 설정 파일에 키를 저장하지 않습니다. OpenRouter Agent와 Optimizer 모델은 서로 달라도 됩니다. `catalog` 조회나 `doctor --plan` 성공은 모델 인증·도구 호출이나 공식 채점 성공을 확인하지 않습니다.

## TTY에서 네 항목 고르기

```bash
.venv/bin/agent-opt tui
```

Home에서 **New Optimization**을 고른 뒤 Agent **ACE-RTL** → Harness **OpenCode** → Optimizer **GEPA** 또는 **Meta-Harness** → Dataset **CVDP** 순서로 선택합니다. 이후 Model Setup → Review → Preparing → Doctor → Running → Result로 진행하며 `↑/↓`로 이동, `Enter`로 확정, `Esc`로 직전 단계로 돌아갑니다. 선택 불가능한 조합에는 이유와 대안이 표시됩니다. `Existing Experiment`와 `Advanced Setup`은 Home의 별도 경로입니다.

Review에서 수정 파일, 모델 값/source, 평가·자산 준비, 외부 호출, 최대 trial budget과 보고서 위치를 확인합니다. 실행을 고르면 Preparing에서 기존 준비 출력을 보고 완료 후 `Continue to Doctor`를 선택합니다. Doctor의 readiness 및 필요한 경우 실제 model connectivity probe 결과를 확인합니다. Doctor가 실패하거나 blocked면 run하지 않으며, 통과 뒤에도 `Run Optimization`을 명시적으로 선택해야 합니다. 준비된 설정은 `runs/configs/<생성-ID>/experiment.toml`에 보관되고, model input은 TUI 세션에만 유지됩니다.

## 자동화용 CLI: GEPA 한 번 구성하기

다음은 **위 환경과 모델 인증을 준비한 뒤** 실행하는 GEPA 예시입니다. `init --yes`는 고정 CVDP 데이터·ACE 소스·driver·Docker 이미지 다운로드/빌드를 **승인**하고, 뒤의 `prepare`는 해당 자산을 다시 검사·재사용합니다. 둘 다 무해한 조회 명령이 아닙니다. 같은 이름의 설정은 덮어쓰지 않으므로 재시도 시 이름과 경로를 함께 바꾸세요.

```bash
.venv/bin/agent-opt catalog list --kind agent
.venv/bin/agent-opt catalog list --kind harness
.venv/bin/agent-opt catalog list --kind optimizer
.venv/bin/agent-opt catalog list --kind dataset
.venv/bin/agent-opt catalog show optimizer gepa
.venv/bin/agent-opt init --name ace-gepa-guide --agent-preset ace-rtl \
  --harness-profile ace-opencode --optimizer gepa --dataset cvdp --yes
.venv/bin/agent-opt prepare runs/configs/ace-gepa-guide/experiment.toml
.venv/bin/agent-opt doctor --plan runs/configs/ace-gepa-guide/experiment.toml --json
.venv/bin/agent-opt plan runs/configs/ace-gepa-guide/experiment.toml
.venv/bin/agent-opt run runs/configs/ace-gepa-guide/experiment.toml
```

`init` JSON의 **`experiment`**를 이후 명령의 경로로 사용합니다. `catalog list/show`는 설명·`ready`·`reason` 조회일 뿐 모델/도구 검사나 준비가 아닙니다. `doctor --plan`과 `plan`도 정적 검사입니다. `run`에서만 모델과 외부 공식 평가가 실제 호출될 수 있고, 준비되지 않은 자산을 자동 설치하지 않습니다. 환경이 부족하면 준비 조건을 확인하고 `prepare` 후 `doctor --plan`을 다시 수행하세요. 모델 자체의 연결 확인에는 별도의 실제 호출 진단(`sh scripts/bootstrap.sh doctor --model`)이 필요하며 비용이 들 수 있습니다.

**Meta-Harness**는 위 `init` 명령에서 `--name ace-meta-guide --optimizer meta_harness`로 바꾸고 후속 `runs/configs/ace-meta-guide/experiment.toml`을 사용하세요. GEPA 설정에서 Optimizer만 바꿔 재사용하지 않습니다. Meta는 생성된 설정 옆의 seed `ace_scaffold.py`에서 후보 `.py`를 만들고, 후보 복사본을 공개 과제의 build 선행 단계에 실행합니다. 두 경로의 기본 설정은 각각 **3 iteration, 최대 9 trial·5760초, trial당 600초**이며 예약 상한이지 실측이나 개선 보장이 아닙니다.

## 결과와 검증 범위

`run` JSON의 `run_dir`와 `report_html`을 확인하세요. `report_html`을 브라우저에서 열고, 저장된 결과만 다시 생성하려면 **출력된 실제 `run_dir`**로 아래처럼 실행합니다.

```bash
.venv/bin/agent-opt report "runs/<run-id>" --html
```

`summary.json`의 `synthetic`, `status`, `trials_used`(성공 수가 아닌 예약 평가 횟수), 그룹별 baseline/selected와 `final_test`를 읽으세요. `events.jsonl`·`candidates/*/changes.diff`는 후보 파일 변경과 선택 근거이며, 실제 후보 사용과 공식 채점은 해당 trial의 입력/선행 실행 근거와 **존재하는 경우에만** `cvdp_evaluation/work/raw_result.json`으로 확인합니다. `report.html`/`report.md`/`report.json`은 실행 기록에서 만든 파생물입니다. [결과 읽기](/agent-optimizer/getting-started/results/)의 화면은 **합성 7-trial 캡처**로, ACE 실환경 보고서 이미지가 아닙니다.

[2026-09-28 날짜별 검증 기록](https://github.com/wontaeJeong/agent-optimizer/blob/main/docs/verification.md#2026-09-28-선택형-gepameta-harness-실모델공식-cvdp-후속-검증)은 준비된 **Mac ARM64 source checkout**에서 GEPA와 Meta-Harness를 **각각 별도 1 iteration, 실제 4/최대 5 trial**로 실행한 결과입니다. 후보 `role-guidance.md`의 prompt 반영, 후보 `.py`의 선행 실행 및 두 실행의 공식 CVDP raw 결과(각 4건에서 `result=0`, `passed=1.0`)가 확인됐습니다. 두 validation은 baseline과 후보가 동점이어서 **baseline 선택**, `final_test=[]`입니다. 기본 3회/9 trial 실행, 일반 성능 향상, 전체 CVDP 검증은 아닙니다. 설치형 wheel은 고정 first-party commit을 사용하므로 이 기록의 GPT-5 OpenCode plugin 후속 수정이 자동 반영되지 않습니다. 기록의 Git 제외 `runs/`는 공개 다운로드 파일이 아닙니다.

`init --profile ace-rtl --workspace PATH`는 고정 `simple_feedback` ACE 예제이며 TUI Home의 `New Optimization`에서 네 항목을 고르는 선택형 GEPA/Meta 흐름과 수정 대상·설정 경로가 다릅니다. 내 Agent/팀 구현은 [실험 구성](/agent-optimizer/guides/experiment/)과 [컴포넌트 연결](/agent-optimizer/developer/components/)을 참고하세요.
