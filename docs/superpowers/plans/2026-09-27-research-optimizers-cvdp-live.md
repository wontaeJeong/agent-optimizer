# 실행형 CVDP 연구 Optimizer 검증 구현 계획

> **작업 에이전트:** `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans`로 아래 작업을 순서대로 실행하고 체크박스를 추적한다.

**목표:** 실행되는 로컬 Python Agent를 공식 CVDP에 연결해 GEPA·Meta-Harness·Ecdysis의 자체 구현을 독립 stage로 실제 모델·채점 환경에서 한 번 검증한다.

**구조:** 예제 Python Agent만 추가하고 기존 `CommandHarness`, 모델 전송, CVDP provider/evaluator, Optimizer 계약을 사용한다. 선택한 데이터셋은 고정 provider에서 공개 family가 다른 과제만 2 train/1 validation으로 추려 생성 설정에 provenance를 남긴다. 모델 키는 실행 자식 환경에만 둔다.

**기술:** Python 3.11+/3.12, `unittest`, 표준 `http.server` 모델 fixture, Docker 공식 CVDP, OpenAI 호환 Chat Completions.

**설계:** [승인된 설계](../specs/2026-09-27-research-optimizers-cvdp-live-design.md).

## 전역 제약

- 전용 `.worktrees/research-live-eval`, branch `test/research-live-eval`. 기본 checkout `main`을 수정하지 않으며 `origin/main`을 갱신한 뒤 필요하면 아직 게시하지 않은 브랜치만 선형 통합한다.
- 세 연구 알고리즘은 코어의 자체 구현을 사용한다. GEPA `prompts/system.md`, Meta-Harness/Ecdysis `src/agent.py`를 실제 후보 스냅샷에서 변경한다. stage는 baseline에서 독립 시작, train 근거만 mutation에 사용한다.
- 사용자가 명시적으로 선택한 CVDP 고정 입력의 공개 단일 RTL target을 가진 train 2 family·validation 1 family만 사용한다. 공식 private 평가 기준/파일·upstream SHA는 변경하지 않는다. final_test=false.
- GEPA iterations=1/max_trials=5, Meta-Harness iterations=1/max_trials=4, Ecdysis rounds=1/max_trials=4; 실험 max_trials=16/max_wall_time_seconds=3600/trial_timeout_seconds=180, 모델 요청 60초 이내. 예산을 소진하면 추가 API 호출 전에 중단하고 기록한다.
- Agent DeepSeek 연결은 예제 전용 `DEMO_AGENT_MODEL_BASE_URL`/`_ID`/`_API_KEY`, Optimizer OpenAI 연결은 `AGENT_OPT_MODEL_BASE_URL`/`_ID`/`_API_KEY`에만 둔다. `.env` 자동 로딩·키 argv/코드/보고서 저장 금지. 실제 성능 향상·native ACE·외부 팀 Agent 효과를 주장하지 않는다.
- 시작 전 API-free 회귀, 실제 CVDP 준비/doctor/smoke를 분리하고 한 번의 승인된 최대 16 trial 실실행 결과만 실환경 증거로 표시한다. 다른 데이터셋을 자동 추천·선택하지 않는다.

## 파일 책임 지도

- `examples/model-rtl-agent/agent/src/agent.py`, `agent/prompts/system.md`, `agent.toml`, `harness.toml`, `adapter.py`: 공개 입력·모델 생성·출력, 실제 수정 가능한 prompt/코드, command 기반 프로필과 모델 연결 오류 상태 분리.
- `examples/model-rtl-agent/prepare.py`: 사용자 지정 `cvdp` provider의 준비된 공개 tasks 2+1 선택, provenance/evaluator 설정과 세 독립 stage를 설정 생성에 전달.
- `tests/test_model_rtl_agent.py`: HTTP fixture로 실제 argv/Agent 소스·출력·모델 환경 분리·오류·원본 보존 검사.
- `tests/test_research_cvdp_example.py`: 고정 provider 계약을 모의한 과제 준비/정적 계획·독립 stage와 공식 evaluator ID 테스트. 실제 모델/공식 채점 근거와 구분.
- `examples/model-rtl-agent/README.md`, `docs/verification.md`, `docs/status.md`, 필요할 때 `docs/SOURCES.md`: 재현·실제 명령/관측·미검증 범위.

---

### Task 1: 공개 RTL을 생성하는 실제 Python Agent

**Files:**
- Create: `examples/model-rtl-agent/agent/src/agent.py`
- Create: `examples/model-rtl-agent/agent/prompts/system.md`
- Create: `examples/model-rtl-agent/agent.toml`
- Create: `examples/model-rtl-agent/harness.toml`
- Create: `examples/model-rtl-agent/adapter.py`
- Create: `tests/test_model_rtl_agent.py`

**Interfaces:**
- Consumes: `CommandHarness`의 `request.json`, `task_dir`, `ModelSettings.from_env(mapping)`·`complete`, 공개 target 선언.
- Produces: `python agent/src/agent.py <task_dir>`가 선언된 `task/rtl/*.v|*.sv`만 쓰고 실행 코드 SHA를 비밀 없는 stdout으로 기록. `ModelRTLCommand(CommandHarness)`는 모델 인증·전송 오류 표시만 `infrastructure_error`로 분리.

- [ ] **Step 1: 환경 준비·RED.** `make setup-core`로 이 worktree의 `.venv`와 합성 데모를 만든다. 임시 task 디렉터리(비어 있는 `rtl/example.sv`)와 실제 `request.json`을 준비해 Python subprocess가 공개 prompt의 `Write target files: rtl/example.sv`를 소비하는 테스트를 작성한다. 표준 `http.server` 로컬 fixture가 `/v1/chat/completions`의 `model`/`messages`/Bearer 요청을 받았는지 확인하고, 공개 RTL만 응답한다. DEMO 모델 변수 누락/인증 오류는 `ModelRTLCommand.run`에서 `infrastructure_error`·`passed=None`이어야 한다. 경로 이탈, 선언에 없는 출력, 빈/비문자 모델 응답, 잘못된 status는 성공 파일/유효한 공식 점수로 변환하지 않아야 한다. 원본 `agent/src/agent.py`, 공개 파일, private 형식의 바깥 파일 hash 보존도 검사한다. `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_model_rtl_agent.py -v`가 구현 부재로 실패하는지 확인한다.
- [ ] **Step 2: 최소 구현.** 실제 `src/agent.py`는 최상위 `def main()`과 `if __name__ == "__main__": main()`을 제공한다(Meta-Harness의 required_symbol). `Path(sys.argv[1])`, `Path.cwd()/request.json`과 요청의 공개 `prompt`만 읽는다. 반환된 모델 콘텐츠는 RTL target 하나에 대한 전체 텍스트로 취급하고, target 두 개 이상일 때는 단일 텍스트를 임의 복제하지 말고 명시적으로 거부한다. `safe_path`로 task_dir 이탈/symlink를 거부하고 모델 호출 전 정확한 공개 target 존재를 검사한다. `ModelSettings.from_env`에 예제 전용 환경을 복사해 넣어 `complete(messages, settings=settings, timeout=60)`로 호출한다. target 파일에 쓰기 전 응답 형태를 확인하고 stdout에는 실행 파일 SHA, 공개 상대 target과 모델 ID만 JSON으로 출력한다.

```python
agent_env = {"AGENT_OPT_MODEL_BASE_URL": os.environ.get("DEMO_AGENT_MODEL_BASE_URL", ""),
             "AGENT_OPT_MODEL_ID": os.environ.get("DEMO_AGENT_MODEL_ID", ""),
             "AGENT_OPT_MODEL_API_KEY": os.environ.get("DEMO_AGENT_MODEL_API_KEY", "")}
settings = ModelSettings.from_env(agent_env)
reply = complete([{"role": "system", "content": system_prompt},
                  {"role": "user", "content": public_task_prompt}],
                 settings=settings, timeout=60)
text = reply["choices"][0]["message"]["content"]
```

  공개 target은 importer가 마지막에 추가한 선언만 읽는다. Agent source 문서에 같은 문장이 있어도 이를 target 선언으로 채택하지 않는다:

```python
match = re.search(r"\nWrite target files: ([^\n]+)\nTask files are in \./task\. Modify only task outputs\.$",
                  request["prompt"])
if match is None:
    raise ConfigurationError("Missing public RTL target declaration")
targets = [item.strip() for item in match.group(1).split(",")]
if len(targets) != 1:
    raise ConfigurationError("This small Agent requires one public RTL target per task")
output = safe_path(task_dir, targets[0])
if not output.is_file() or output.suffix not in {".v", ".sv"}:
    raise ConfigurationError("Declared public RTL target is missing")
```

  모델 설정/연결 예외를 받은 Agent는 비밀 없는 `{"status":"model_unavailable"}`를 stdout에 쓰고 종료 코드 2로 끝낸다. 예제 `adapter.py`는 비정상 종료에서 해당 JSON 상태가 정확히 확인될 때만 `ExecutionResult.status="infrastructure_error"`로 바꾼다. stdout이 없거나 형식이 다르면 기존 process_error를 유지하며 0점/성공으로 꾸미지 않는다.

  `agent.toml`은 local `source.path="agent"`, `prompt_file="prompts/system.md"`, `editable=["prompts/system.md", "src/agent.py"]`, `supported_harnesses=["model_rtl_command"]`. `harness.toml`은 `adapter="model_rtl_command"`, `allow_local=true`, argv `['{python}', '{agent_dir}/src/agent.py', '{task_dir}']`, runtime.kind local이며 이미지/셸 실행 설정이 없다. `adapter.py:ModelRTLCommand`는 `CommandHarness`의 실행을 재사용하고, Agent가 모델 실패를 JSON 상태로 보고한 비정상 종료만 `infrastructure_error`로 분리한다. 그 외 task 오류는 합성 성공으로 대체하지 않는다. 선언/소스 코드의 .env 파일은 제외된다.
- [ ] **Step 3: GREEN·커밋.** 위 focused 테스트와 `test_adapters.py`, `make lint`를 확인한다. 변경 파일만 status/diff/log로 검토해 커밋한다. 메시지: `CVDP용 실행형 Python Agent 예제 추가`.

### Task 2: 명시적으로 선택한 고정 CVDP 2+1 설정 생성

**Files:**
- Create: `examples/model-rtl-agent/prepare.py`
- Create: `tests/test_research_cvdp_example.py`

**Interfaces:**
- Consumes: `setup_wizard.prepare_selection(project_root, "cvdp")`, `write_experiment`, Task 1 로컬 Agent 경로, CVDP provider의 `benchmark`/`evaluator`/`evaluator_config`/`provenance`.
- Produces: `runs/configs/model-rtl-research/experiment.toml`, `tasks.json`(2 train/1 validation), provenance와 고정 evaluator 설정.

- [ ] **Step 1: 실패 테스트 작성.** 임시 provider 결과(서로 다른 family의 train 최소 2·validation 최소 1, 복수 target/비 RTL 행도 포함, test와 동일 family 중복 및 private `evaluation.row` 분리)를 제공해, 공개 단일 `rtl/*.v|*.sv` target의 task ID 정렬로 선택한 세 공개 과제와 가족/출처/해시가 기록되는지 검사한다. 유효한 두 train family 또는 validation family가 없으면 설정 디렉터리·모델 호출 없이 실패, 이미 존재하는 설정 덮어쓰기 거부, command의 실제 argv/두 editable 파일/세 independent stage config와 budgets가 `load_experiment`·`doctor --plan`에서 유효한지 검사한다. `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_research_cvdp_example.py -v`가 구현 부재로 실패하는지 확인한다.
- [ ] **Step 2: 최소 구현.** 명시 `--dataset cvdp` 인수만 수용하는 예제 준비 명령을 만들고, 시작 시 `runs/configs/model-rtl-research`가 이미 있으면 provider 호출과 subset 기록 전에 명시적으로 실패한다. 기존 `prepare_selection(root, "cvdp", offline=...)`의 결과만 사용한다. provider의 공개 JSON에서 `evaluation.targets`가 정확히 한 개인 `rtl/*.v|*.sv` 행만 ID 순으로 추려, 서로 다른 family train 2와 train과 family가 다른 validation 1을 선택한다. 원본 전체 파일이나 private evaluator source는 수정하지 않으며 별도 공개 subset JSON을 `external/datasets/cvdp-research/subset.json`에 기록한다(기존 설정 디렉터리를 미리 만들지 않는다). 이어 `write_experiment`에 해당 subset의 benchmark 경로와 provider의 `evaluator=cvdp`/evaluator_config/provenance, Task 1 Agent, command argv, 두 editable 경로와 아래 stage config를 전달한다. `write_experiment`가 새 `runs/configs/model-rtl-research/tasks.json`을 생성하고 provenance를 부여한다. bounded tasks는 subset 문서가 이미 3개이므로 `max_tasks=3`으로 원래 split 그대로 유지한다.

```python
stages = [
    {"id": "gepa", "optimizer": "gepa", "max_trials": 5,
     "config": {"file": "prompts/system.md", "iterations": 1,
                "batch_size": 2, "request_timeout_seconds": 60}},
    {"id": "meta", "optimizer": "meta_harness", "max_trials": 4,
     "config": {"file": "src/agent.py", "iterations": 1,
                "required_symbol": "main", "request_timeout_seconds": 60}},
    {"id": "ecdysis", "optimizer": "ecdysis", "max_trials": 4,
     "config": {"file": "src/agent.py", "rounds": 1,
                "refinement_passes": 2, "request_timeout_seconds": 60}},
]
```

  `write_experiment`의 harness에 `adapter="model_rtl_command"`와 command argv를 넘기고 `plugins={"harnesses": {"model_rtl_command": "examples/model-rtl-agent/adapter.py:ModelRTLCommand"}}`를 명시한다. `name="model-rtl-research"`, max_trials=16, wall_time=3600, trial_timeout=180, objective passed/maximize, final_test=false를 확인한다. CVDP 소스/HF SHA는 provider lock을 검증하고 저장할 뿐 갱신하지 않는다.
- [ ] **Step 3: GREEN·커밋.** focused 테스트, `test_catalog.py`, `test_plugin_contracts.py`, `make lint`를 실행한다. repo root 외부 작업공간 경로, plugin ID/evaluator config, 소스·데이터 분리를 재검토해 두 파일만 커밋한다. 메시지: `선택 CVDP 과제로 독립 연구 stage 설정 생성`.

### Task 3: API-free 연구 stage 실제 실행 경계

**Files:**
- Modify: `tests/test_research_cvdp_example.py`
- Modify: `tests/test_model_rtl_agent.py` (발견된 필수 계약 회귀만)
- Modify: `examples/model-rtl-agent/prepare.py` (모의 실행에서 드러난 필요한 수정보다 확장 금지)

**Interfaces:**
- Consumes: Task 1의 실제 command Agent와 Task 2 생성 설정. 로컬 HTTP 응답 fixture·신뢰한 test evaluator가 공개 RTL만 판정한다.
- Produces: 세 stage가 baseline 시작, prompt/실행 코드 변경, 해시/원본 보존, frozen selection 순서로 실행된 fixture 증거.

- [ ] **Step 1: 경계 실패 테스트.** 세 stage의 모델 답변을 각각 구분해 반환하는 loopback HTTP fixture를 준비하고 evaluator는 공개 target 존재/내용만 판정해 private 파일 접근을 거부한다. baseline의 서로 다른 두 train 중 하나는 의도적으로 실패하게 만들어 Ecdysis가 `no_failures`로 끝나지 않고 모델 검토·후보 제안 경로를 실제로 밟게 한다. 실제 `run_experiment`로 스냅샷 Python subprocess를 실행하여 `summary.groups[0].stages`가 `["gepa", "meta", "ecdysis"]` 순서인지, 후보 diff가 각 editable file 한정인지, candidate trial stdout의 실행 파일 SHA가 실제 snapshot/원본과 맞는지, optimizer history가 train만 포함하고 final_test가 없는지 확인한다. 모델 답변을 의도적으로 무효로 돌릴 때 잘못된 API/Agent 출력을 합성 성공 점수로 대체하지 않는지도 검사한다. 새 계약이 부족하면 실패를 재현한 뒤 수정하고 성공 케이스만을 근거로 full 성능을 주장하지 않는다.
- [ ] **Step 2: API-free GREEN.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_research_cvdp_example.py -v`, `-p test_research.py -v`를 실행한다. 테스트 fixture는 실제 Chat Completion 형식과 공식 CVDP 평가를 혼동하지 않는다.
- [ ] **Step 3: 커밋.** 작은 필수 경계 수정과 테스트만 diff/status/log를 확인해 커밋한다. 메시지: `연구 stage의 실행 코드와 train 경계 검증`.

### Task 4: 선택 CVDP 준비·실모델 검증과 정직한 기록

**Files:**
- Create: `examples/model-rtl-agent/README.md`
- Modify: `docs/verification.md`
- Modify: `docs/status.md`
- Modify: `docs/SOURCES.md` (새 외부 사용 경로가 있을 때만)
- Modify: `tests/test_model_rtl_agent.py` / `tests/test_research_cvdp_example.py` (실실행에서 발견한 계약 오류의 TDD 회귀만)

**Interfaces:**
- Consumes: Task 1~3의 준비 명령·생성 설정과 사용자가 승인한 최대 16 trial.
- Produces: DeepSeek Agent/명시적 OpenAI Optimizer→공식 CVDP 원시 점수, 수정 코드 실행 근거 또는 명시적 차단 결과.

- [ ] **Step 1: 공식 환경 준비.** `make doctor-core`를 확인한 뒤 선택한 `cvdp` provider를 `agent-opt datasets prepare cvdp`/`doctor --dataset cvdp --json`으로 고정 자산 준비·진단한다. 공식 정답/오답 근거는 기존 `make setup`→`make smoke`의 CVDP LFSR 경로를 재사용해 확인하고, 두 준비 범위의 lock/이미지 ID를 혼동하지 않는다. 최초 다운로드/Docker 비용·인증 실패는 환경 장애로 기록한다.
- [ ] **Step 2: 모델 없는 계획 진단.** `.venv/bin/python examples/model-rtl-agent/prepare.py --dataset cvdp`로 subset+실험 설정을 만들고 출력된 세 task ID/family/source SHA를 확인한다. `.venv/bin/agent-opt doctor --plan runs/configs/model-rtl-research/experiment.toml --json`에서 static `ready`를 확인한다. 이 단계는 모델 API·공식 과제 점수 성공 근거가 아니다.
- [ ] **Step 3: 한정 실모델 실행.** 승인된 로컬 `.env`에서 DeepSeek 키와 OpenAI API 키/모델을 **출력 없이** 자식 셸 환경에만 매핑한다. Agent 전용 `DEMO_AGENT_MODEL_BASE_URL=https://api.deepseek.com`, `DEMO_AGENT_MODEL_ID=deepseek-flash`, `DEMO_AGENT_MODEL_API_KEY`←DeepSeek 키, Optimizer `AGENT_OPT_MODEL_BASE_URL=https://api.openai.com/v1`, `AGENT_OPT_MODEL_ID`←`OPENAI_MODEL`, `AGENT_OPT_MODEL_API_KEY`←`OPENAI_API_KEY`를 설정한다. `max_trials=16`을 코드와 설정에서 재검사하고 `.venv/bin/agent-opt run runs/configs/model-rtl-research/experiment.toml`을 **한 번** 실행한다. 설정/모델/평가 오류 시 반복 재호출하지 않고 중단·기록한다.

```bash
test -n "$AGENT_OPT_ENV_FILE"  # 사용자가 지정한 Git 제외 로컬 .env 경로
set -a
. "$AGENT_OPT_ENV_FILE"
set +a
export DEMO_AGENT_MODEL_BASE_URL=https://api.deepseek.com
export DEMO_AGENT_MODEL_ID=deepseek-flash
export DEMO_AGENT_MODEL_API_KEY="$AGENT_OPT_MODEL_API_KEY"
export AGENT_OPT_MODEL_BASE_URL=https://api.openai.com/v1
export AGENT_OPT_MODEL_ID="$OPENAI_MODEL"
export AGENT_OPT_MODEL_API_KEY="$OPENAI_API_KEY"
unset AGENT_OPT_MODEL_ENDPOINT
.venv/bin/agent-opt run runs/configs/model-rtl-research/experiment.toml
```

  이 셸 명령은 실행 값이 이미 사용자가 준비한 환경에만 있으며 앱 코드에 `.env` 자동 로딩을 추가하지 않는다. API 키의 실제 문자열을 출력·복사하지 않고, 결과물에 포함됐는지 검사한다.
- [ ] **Step 4: 원시 증거·회귀.** train/validation `result.json`과 공식 `cvdp_evaluation/work/raw_result.json`의 존재·integer 결과·환경 실패 로그를 대조하고, 선택 고정, 후보 diff, 실제 실행 Python SHA, stage-local history, usage `None`/partial을 기록한다. `docs/verification.md`에 명령·모델 ID/환경·실제 trial/점수/한계, `status.md`에 검증 수준, 예제 README에 재현 조건을 기록한다. 모델 개선을 주장하지 않는다. `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`, `make lint`, 기본 합성 데모 7 trial로 회귀를 확인한다. 상태/diff/log와 키 누출을 검사하고 의도 파일만 커밋한다. 메시지: `연구 Optimizer의 실제 CVDP 실행 범위 기록`.

## 완료·인계

각 Task 구현 뒤 별도 리뷰를 받고 전체 브랜치 리뷰까지 마친 뒤 origin/main과의 차이, CLI/CI 결과, 비밀정보 부재를 확인해 PR을 연다. 사용자 승인 전에는 PR을 병합하지 않는다. 병렬 scheduler·native ACE·다른 데이터셋을 이 계획에 섞지 않는다.
