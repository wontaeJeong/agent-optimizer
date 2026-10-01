# Python native ACE·CVDP 실행 가이드

**native 실모델·실 Docker/EDA loop는 현재 `not_run`**이다. CLI/TUI·loader·runner·진단·배포는 F/G에 통합됐고 정책은 예제 `native_selection.py`가 소유한다. 아래는 조건을 갖춘 사용자를 위한 안내이며 실행 성공 기록이 아니다. 과거 OpenCode/Claude Code·evaluator-only 성공과 구별한다.

| 구분 | native | 기존 coding(legacy) |
|---|---|---|
| 선택/Agent | `--harness-profile ace_native`(별칭 ace-native), `ace-rtl-native` | `ace-opencode`, 기존 Claude Code 프로필 |
| adapter/profile/evaluator | `ace_native` / `ace-native` / `cvdp_native` | `ace_opencode` / `ace-opencode` / `cvdp` |
| loop | 후보의 원본 run_attempt·Generator/Reflector/Coordinator | ACE 스킬을 읽는 coding CLI + 외부 평가 |
| GEPA | `native/guidance.md` | `skills/ace-rtl/references/role-guidance.md` |
| Meta-Harness | `native/orchestration.py:guidance(role,text)` 실제 import | `agent_opt_scaffold.py:prepare_task` 공개 과제 선행 build |

기존 `source.toml`·`harness.toml`·`harness-claude.toml`과 `init --profile ace-rtl --workspace PATH`, 옵션 없는 `make setup/doctor`·`make smoke/live`는 [legacy 안내](README.md)에 속한다. native 전체 준비 wrapper가 아니다.

## 1. 준비 조건

- 사용자가 고른 **로컬 고정 checkout/export**: ACE `fead921f18bb57345b5a41ef93ba625be208e99c`, CVDP `8e894cf74414ab1eaea1e2b4e80a02f123df07b6`, 아래 고정 HF JSONL. 자동 native fetch/installer는 없다.
- **별도 native Python 3.12 환경 + `native` extra(`PyYAML==6.0.2`)**와 코어의 `pydantic_settings`. 준비한 wheel의 `agent-optimizer[native]` 또는 소스의 frozen native extra를 그 환경에 설치한다. 코어는 Python>=3.11이며 `setup-core`가 native 환경까지 준비하지 않는다.
- 평가 driver는 **별도 Python 3.12 + `environment/requirements-cvdp-py312.txt` 고정 lock**. Docker/Compose·`ps`·검토한 OSS simulator **tag와 로컬 image ID**가 필요하다. 기존 `setup --dataset cvdp`는 평가 자산 준비이며 native 전체 준비가 아니다.
- 환경/credential store의 `AGENT_OPT_MODEL_BASE_URL`, `AGENT_OPT_MODEL_ID`, `AGENT_OPT_MODEL_API_KEY`. 세 native 역할은 같은 transport/API를 사용한다. URL은 `/chat/completions`를 제외하며 키는 TOML/argv에 넣지 않는다. Baseline에도 native Agent API가 필요하고 연구 stage의 Optimizer API 요구는 별도다. `AGENT_OPT_MODEL`/NVIDIA key는 native 필수가 아니다.

## 2. 명시 선택·prepare·doctor

다음 `/absolute/...`와 simulator 값은 설명용이므로 준비한 실제 값으로 바꾼다. 저장소의 준비된 코어 CLI 또는 설치한 `agent-opt`를 사용한다.

```bash
agent-opt catalog show harness ace_native --json
agent-opt init --name native-smoke --agent-preset ace-rtl \
  --harness-profile ace_native --dataset cvdp --optimizer baseline \
  --cid cid002 --rows '{"cvdp_copilot_64b66b_decoder_0001":"validation"}' \
  --native-upstream /absolute/pinned-ACE \
  --native-dataset /absolute/pinned-data.jsonl \
  --native-python /absolute/native-venv/bin/python \
  --native-evaluator '{"repo":"/absolute/pinned-cvdp","python":"/absolute/driver/bin/python","sim_image":"local-reviewed-tag","sim_image_id":"sha256:reviewed-identity"}' \
  --yes
# init JSON의 experiment 정본을 복사한다:
CONFIG='/absolute/Home/experiments/실제-UUID/experiment.toml'
agent-opt prepare "$CONFIG" --offline
agent-opt doctor --plan "$CONFIG" --json
agent-opt plan "$CONFIG"
# 실제 API 요청을 보내는 명시 probe(선택):
agent-opt doctor --plan "$CONFIG" --model --json
```

`--native-source /absolute/prepared-source`는 `--native-upstream` 대신 이미 export한 고정 소스를 사용할 때 지정한다. 두 옵션을 섞지 않는다. init은 선택 CID·row→split과 고정 로컬 소스/데이터를 검증·준비한다. **`prepare --offline`은 누락 interpreter/driver/image/모델 환경을 설치하거나 online으로 보완하지 않고 명시 오류로 끝난다.** G의 실제 정적 확인에서는 코어 yaml 누락·Docker 없음·image identity/모델 미설정으로 doctor/prepare가 종료 2였다. ready/probe 성공은 Agent/최종 평가 성공이 아니다.

## 3. 작은 smoke → 선택 CID

위 한 row Baseline을 조건을 갖췄을 때만 실행한다. 이 명령은 **실제 Agent API와 공식 평가**를 호출한다.

```bash
agent-opt run "$CONFIG"
```

그 뒤 연구 비교는 새로운 독립 설정에서 CID/rows/Optimizer를 직접 선택한다. 예를 들어 전체 init 명령의 아래 인수를 변경하고 준비한 경로를 유지한다(아래 조각만 실행하는 명령이 아님).

```text
--name native-gepa --optimizer gepa --cid cid002 --cid cid016
--rows '{"cvdp_copilot_64b66b_decoder_0001":"train","cvdp_copilot_32_bit_Brent_Kung_PP_adder_0001":"validation"}'
```

Meta는 다른 독립 init에서 `--optimizer meta_harness`로 선택한다. train/validation family와 필요 시 test를 사용자가 정하며 자동 held-out 분할은 없다. CLI/TUI는 명시 rows를 `max_tasks`로 재샘플링하지 않는다. TUI는 Home → 네 구성요소 → Native 경로/CID → row의 target·도구·지원/제외 사유 → split → Model → Review → Preparing → Doctor → 명시 실행 → Result/History다. test를 선택하면 Review의 final_test·예약 budget을 확인하고 **선택 고정 후**에만 평가한다.

## 4. CID 지원표

HF revision `5b807d945f6a99aa645f7e43a64a2115e281b4bf`의 `cvdp_v1.1.0_nonagentic_code_generation_no_commercial.jsonl`, SHA-256 `cbcd81295561ebb16e4d857e096f4d9908d042c33aff3b58abf236e868411857` 기준이다. **eligible은 정적 row 형태/실행 경계 판정이며 실도구 통과/정답률이 아니다.** C가 검토한 224개 중 197 eligible·27 제외다.

| CID | 전체/eligible | target·도구·공식 binary 판정 | 제외 |
|---|---:|---|---|
| cid002 | 94/94 | 90 single·2 two-file·2 three-file, rtl/*.sv 또는 .v; Icarus/cocotb/pytest, tests[].result | 없음(정적 검토) |
| cid004 | 55/55 | 54 single·1 two-file, 공개 기존 RTL 수정; Icarus/cocotb/pytest | 없음(정적 검토) |
| cid007 | 40/13 | single RTL; 13개는 Icarus sanity + Verilator --lint-only + pytest, 두 서비스 모두 result=0 | 25 PNR/합성 자산 + lint-only 2개 상용 helper. 우선 사유 PNR 17·상용 경로 10 |
| cid016 | 35/35 | single RTL 공개 증상/bug fix; Icarus/cocotb/pytest | 없음(정적 검토) |

CID007 상용 경로 10개 중 8개는 PNR과 겹친다. `xrun -coverage` helper의 비호출을 입증하지 않아 보수적으로 제외했고 PNR objective를 기능 binary 성공으로 대체하지 않았다. `cvdp_copilot_64b66b_encoder_0022`는 PNR로 제외, `cvdp_copilot_IIR_filter_0019`는 lint 형태 eligible이다. no-commercial 파일명만으로 전체 OSS 지원을 주장하지 않는다. [C 원문 판정표](../../docs/verification/final-mvp-c-20261001.md#cid-판정표)를 따른다.

## 5. outer/inner·trusted 경계

![outer Agent Optimizer와 inner native ACE, private은 trusted 평가기에만 전달](../../website/src/assets/diagram-native-loop.svg)

각 outer trial은 attempt **1개**다. 후보에서 고정 원본 `ace_cvdp_native.cli.run_attempt`, `FocusedDebugger`, `FreshStartCoordinator`를 import한다. 원본 loop가 generation → inner 평가 → pass/infra → reflector/coordinator → 다음 iteration/fresh-start를 소유한다. 원본 전체 CLI의 다중 datapoint/attempt·상용 경로·native harness patch는 실행하지 않는다. trusted bridge는 public-only processor·안전한 multi-file 출력·모델 transport를 연결한다.

private harness/golden/context/평가 로그는 모델 입력으로 전달하지 않는다. bridge의 inner feedback은 공식 **binary 상태/집계**만 허용한다. 정상 종료 후 `GroupRunner.trial`의 outer trusted evaluator가 제출 target을 다시 판정한다. **inner pass는 최종 점수가 아니다.** inner 설정 `profile.native.evaluator`와 outer evaluator 설정은 별도이며 서로 다른 repo/Python/tag/identity도 독립 진단한다. 다중 native pair는 실제 Agent/profile의 source·subdir/interpreter를 검사한다.

GEPA guidance와 Meta orchestration은 실제 실행 표면이며 해시/요청 근거를 기록한다. upstream/bridge/evaluator/source-lock은 editable 밖이다. local Python 후보는 trusted plugin이며 OS sandbox가 아니다. Optimizer 수정 근거는 자기 stage와 baseline의 train만, validation은 내부 선택 수치만, test는 frozen selection 이후다. 연구 자체 구현은 upstream/논문 재현이 아니다.

## 6. 결과·History·근거

```bash
RUN='/실제/run/출력/run_dir'
agent-opt report "$RUN" --json
agent-opt report "$RUN" --html --serve --no-open --port 0
```

History는 Home·선택 explicit output 부모·legacy 경계의 실패/중단/report 없음/session child도 조회한다. HTML/MD/JSON은 같은 normalized v3이며 attempt/iteration·역할별 요청·inner 횟수/time·outer 평가를 구분한다. `--serve`는 loopback HTML 한 파일만 공개한다. raw sidecar/private/RTL/로그/키는 공개 자산이 아니다. [Home/output·report 규칙](../../README.md#history와-보고서-보기)을 참고한다.

`RunRequest.logs/native-execution.json` schema 1은 source revision/hash·candidate/task identity·실제 attempts/requests/generated_files/evidence_paths·active_surface_hashes를 기록한다. 없는 provenance/token/cost는 null, usage는 partial/unreported이고 전체 사용량으로 승격하지 않는다. sidecar의 outer count/time은 null이며 runner producer가 **실제 outer 평가**를 별도 계측하여 result/events로 연결한다. 손상/누락 sidecar는 native optional만 제외하고 경고하며 outer 성적을 바꾸지 않는다.

실패에도 native-progress/native-requests journal을 보존한다. process group/관측 descendants와 소유 Docker network의 container만 deadline 안에서 정리한다. `min(1초,10%)`를 정리에 예약하고 명령은 개별 최대 1초/잔여 시간 이하다. 미완료는 incomplete/deferred이지 정리 성공이 아니다. 실 Docker cleanup은 아직 not_run이다.

## 개발 API·배포 provenance

`prepare_source(upstream,destination)`은 고정 로컬 Git tree를 새 destination에 export하며 원본/fetch/install을 변경하지 않는다. `prepare_dataset(dataset,output,*,cids,splits=None)`은 고정 hash와 row 형태를 검사하고 기본 validation-only다(제품 writer는 split 명시 요구). public descriptor는 input/빈 target만, private row는 trusted evaluation에만 있다. `readiness(source,python)`은 source/asset·3.12·yaml/pydantic_settings만 검사하고 전체 모델/평가 준비와 다르다. adapter `run(RunRequest) -> ExecutionResult`, evaluator `evaluate(Task,output_dir,timeout_seconds) -> Evaluation`은 공통 계약을 따른다. iteration 기본 3(1~30), LLM 기본 60초·inner evaluator 120초는 outer 잔여 시간에 제한된다.

helper 출처는 **명시 workspace → 실행 코어 source checkout → distribution metadata에 선언된 share/agent-optimizer 자산** 순이다. 임의 CWD를 원본으로 가장하지 않는다. G의 [최종 §7](../../docs/verification/final-mvp-g-20261001.md)는 실제 source-free wheel build/install·합성 CLI·native helper/진단/누락 실패·HTTP 검증이며 원본 native live 성공이 아니다. legacy first-party pin `ae0874fb94d94284a07a17d84ef60058ed9a97b6`은 갱신하지 않았고 신규 native 파일을 포함한다고 주장하지 않는다. 자산 없는 old wheel은 명시 실패한다. 고정 출처는 [SOURCES](../../docs/SOURCES.md)다.
