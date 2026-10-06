# C — Python native ACE·CVDP 구현·검증·인계

확인일: 2026-10-01. **예제 native 구현 및 fixture 검증 완료; live는 `not_run`.**
작업: `/Users/wt.jeong/workspace/agent-optimizer/.worktrees/final-mvp-c-20261001`,
브랜치 `feat/final-mvp-c-20261001`, 기준 `origin/main=edbd2b8c7b05bdd63c352d02a7adf7652168d197`.
하위 에이전트·외부 모델·다운로드·실시뮬레이터·실 Docker 평가·install/sync를 실행하지 않았다.
공유 `.venv/bin/python`은 절대경로 실행만 했다. 개인 `.env`/키를 읽지 않았다.

## 1. 변경 범위와 실제 연결

소유 예제에만 `native_adapter.py`, `native_worker.py`, `native_bridge.py`,
`native_cvdp.py`, `native_evaluator.py`, `native_prepare.py`, `source-native.toml`,
`harness-native.toml`, `native/guidance.md`, `native/orchestration.py`, `NATIVE.md`를 추가했다.
새 전용 테스트는 `tests/test_native_ace.py`·`tests/test_native_cvdp.py`다.
코어 CLI/catalog/registry/runner/report와 기존 coding 예제·공유 테스트는 수정하지 않았다.

호출 경로:

1. `ACENative.run(RunRequest)` → 독립 `native_worker.py`.
2. 후보 `request.agent_dir`에서 고정 원본 `ace_cvdp_native.cli.run_attempt` 및 원본
   `FocusedDebugger`·`FreshStartCoordinator` import.
3. 원본 `run_attempt`가 generation → inner 평가 → pass/infra → coordinator → reflector →
   다음 iteration/fresh-start를 그대로 소유한다. 단일 trial의 attempt는 1개다.
4. trusted 예제 bridge가 public-only processor, 안전한 `AceIterationModel` 출력 처리,
   세 역할 모델 client와 private context/feedback 경계를 연결한다.
5. `NativeCVDPEvaluator`는 기존 공식 CVDP subprocess 평가를 재사용한다.
   inner pass는 최종 성적이 아니며, 정상 실행 후 기존 `GroupRunner.trial`의 outer
   Evaluator가 제출 target을 다시 판정한다.

원본 다중 datapoint CLI/main·원본 native harness patch·상용 실행 경로는 실행하지 않는다.
public-only processor는 private CVDP generation workspace를 만들지 않으며 원본
`run_attempt`의 `src.dataset_processor` 경계에만 연결한다. 이는 원본 전체 CLI 실행이나
논문 재현 선언이 아니다. 후보 Python은 기존 trusted plugin 계약이며 OS sandbox가 아니다.

## 2. 고정 출처와 실제 row 확인

- upstream 읽기 전용: 기본 repo `external/ACE-RTL`, pin
  `fead921f18bb57345b5a41ef93ba625be208e99c`.
- `docs/SOURCES.md`와 같은 CVDP pin:
  `8e894cf74414ab1eaea1e2b4e80a02f123df07b6`.
- 데이터: `external/cvdp-data/5b807d945f6a99aa645f7e43a64a2115e281b4bf/`의
  `cvdp_v1.1.0_nonagentic_code_generation_no_commercial.jsonl`.
- 실제 파일 SHA-256:
  `cbcd81295561ebb16e4d857e096f4d9908d042c33aff3b58abf236e868411857`.
  302개 row 중 선택 네 CID는 224개다. 기본 repo datasets와 external 데이터는 읽기만 했다.
- `.references/ace-rtl`은 다른 pin이라 native 근거로 사용하지 않았다.
- 소스 export의 `source_hash`:
  `55daa1319e5cba858c3f152f2b6bad1065daa11552e57e59373d121f7dde2a09`.
  이는 export된 upstream scripts/prompts의 digest이며 후보 전체 hash와 구분한다.

### CID 판정표

`eligible`는 검토된 row 형태/실행 경계의 허용 판정이다. **실도구 통과/Agent 정답률이 아니다.**
모든 row의 public input/context·output target 수·이미지/도구 선언을 대조했다.

| CID | 전체/eligible | 원본 target shape | 도구·공식 판정 | 차단 |
|---|---:|---|---|---|
| cid002 | 94/94 | 90개 single, 2개 two-file, 2개 three-file; `rtl/*.sv` 또는 `.v` | Icarus/cocotb/pytest, binary `tests[].result`; OSS_SIM 직접 image 또는 추가 설치 없는 alias Dockerfile | 없음(정적 row 검토) |
| cid004 | 55/55 | 54개 single, 1개 two-file; 공개 기존 RTL 수정 | Icarus/cocotb/pytest, 동일 binary 판정 | 없음(정적 row 검토) |
| cid007 | 40/13 | 모두 single RTL; lint와 synthesis/area가 혼재 | 허용 13개는 Icarus sanity + Verilator `--lint-only` + pytest; 두 서비스 모두 result=0 필요 | 25개 PNR/합성 자산 필요 + lint-only 2개에 상용 실행 helper 포함. 우선 사유 기준 PNR 17·상용 경로 10 |
| cid016 | 35/35 | 모두 single RTL; 공개 증상·기존 RTL의 bug fix | Icarus/cocotb/pytest, binary 판정 | 없음(정적 row 검토) |

CID007의 상용 경로 10개 중 8개는 PNR row와 겹친다. `src/harness_library.py`에
`xrun -coverage ...` 실행 함수가 실제로 들어 있다. 이것이 선택 서비스에서 항상 호출된다는
주장은 하지 않는다. 해당 helper의 비호출을 입증하지 않은 상태에서는 보수적으로 제외했다.
no-commercial 파일명만으로 모든 helper가 OSS-only라고 가정하지 않는다.
PNR Dockerfile에는 `FROM __OSS_PNR_IMAGE__`, 외부 pip bootstrap `ADD`·pytest 설치 `RUN`이
있어 준비하지 않았다. Yosys `src/synth.py`의 cells/wires 감소 임계값 비교도 확인했으나,
이 자산과 objective의 실제 검증 없이 binary 기능 성공으로 대체하지 않았다.

원본 representative row:

| CID | 실제 row ID | public input/context | 원본 output.context |
|---|---|---|---|
| cid002 | `cvdp_copilot_64b66b_decoder_0001` | 부분 64b66b decoder 구현 명세; input context 없음 | `rtl/decoder_64b66b.sv: ""` |
| cid004 | `cvdp_copilot_64b66b_encoder_0009` | control-only/mixed mode 확장; `rtl/encoder_64b66b.sv` 1,274자 | 동일 target 1개·빈 reference |
| cid007 | `cvdp_copilot_64b66b_encoder_0022` | cells/wires area 최적화; 공개 encoder RTL 7,833자 | 동일 target 1개; PNR 자산으로 차단 |
| cid007 lint | `cvdp_copilot_IIR_filter_0019` | 공개 IIR RTL의 LINT code review | `rtl/iir_filter.sv`; sanity/lint binary 서비스로 허용 |
| cid016 | `cvdp_copilot_32_bit_Brent_Kung_PP_adder_0001` | 공개 expected/actual 증상·기존 RTL 2,809자 | `rtl/brent_kung_adder.sv: ""` |

실제 three-file row `cvdp_copilot_axis_border_gen_0014`의 선언은
`rtl/axis_border_gen_with_resize.sv`, `rtl/axis_image_border_gen.sv`,
`rtl/axis_image_resizer.sv`다. native fixture에서 세 파일 모두 생성·평가·최종 제출을 확인했다.
추가 nested/reordered fixture도 지원하며 누락·중복·미선언·빈 section·traversal·symlink를 거부한다.

## 3. 모델·private·최적화 표면

- 세 역할 모두 `ModelSettings.from_env`와 `models.complete`를 소비한다.
  `AGENT_OPT_MODEL_BASE_URL`, `AGENT_OPT_MODEL_ID`, `AGENT_OPT_MODEL_API_KEY`를 공유한다.
  `AGENT_OPT_MODEL` provider selector·NVIDIA key는 native 필수 설정이 아니다.
- Generator의 script 호출과 Reflector/Coordinator의 직접 NVIDIA backend 차이를
  trusted worker에서 연결했다. API/429/auth/invalid response/timeout은 실패로 종료하며
  다른 provider나 baseline으로 대체하지 않는다.
- 실제 호출마다 역할·모델·고유 request ID·응답 usage만 기록한다. Coordinator가 정책상
  모델을 호출하지 않은 iteration에는 가짜 request를 추가하지 않는다.
- private row의 harness/golden·trusted evaluator 구현 path/content·private feedback을 모델에
  전달하지 않는다. reflector harness context와 coordinator immutable context helper를 차단하고
  feedback은 공식 binary 상태·개수만 허용한다. private sentinel을 golden/harness/feedback에
  넣어 실제 모델 입력과 sidecar에 없음을 확인했다.
- GEPA 파일: `native/guidance.md`. Meta-Harness 파일: `native/orchestration.py`, 필수 함수
  `guidance(role, text) -> str`. 실제 import·실행된 Python과 guidance hash를 기록한다.
  CandidateStore A/B의 실제 request 차이·candidate hash 일치·원본 후보 불변을 확인했다.
  upstream, 평가 bridge, source lock은 editable 밖이며 coding `role-guidance.md`를 재사용하지 않았다.
- split은 `prepare_dataset(..., splits=...)`가 Task와 public descriptor에 같이 기록한다.
  기본은 validation-only다. F가 held-out 정책에 맞는 명시적 split/family 선택을 해야 한다.
  Optimizer 이력·선택 고정은 기존 코어 정책을 사용한다.

## 4. API·readiness·산출물 계약

| 연결 | API/필드 |
|---|---|
| Agent/adapter/profile | `ace-rtl-native` / `ace_native` / `ace-native` |
| Harness | `native_adapter.ACENative(config=None).run(RunRequest) -> ExecutionResult` |
| 최종 평가 | `native_evaluator.NativeCVDPEvaluator(config=None).evaluate(Task, output_dir, timeout_seconds) -> Evaluation` |
| 소스 준비 | `native_prepare.prepare_source(upstream, destination)`; 반환 `path/revision/source_hash/editable` |
| 데이터 준비 | `native_prepare.prepare_dataset(dataset, output, *, cids, splits=None)`; 고정 hash·row별 exclusions |
| engine 진단 | `native_prepare.readiness(source, python)`; source pin/asset, Python 3.12, yaml/pydantic_settings |
| profile `[native]` | `python`, `dataset` 절대경로, `max_iterations` 기본 3(1~30), `llm_timeout` 기본 60초, `evaluator_timeout` 기본 120초, 기존 evaluator config |
| outer 상한 | `RunRequest.timeout_seconds`; readiness/준비 시간을 차감하고 worker·inner LLM/evaluator에 잔여 시간만 전달 |

sidecar: **`request.logs/native-execution.json`, schema_version=1**.
필수 P0 필드 `execution_mode="native"`, `source_revision`, `source_hash`, `profile`, `task_id`,
`candidate_hash`, `status`, `attempts`, `requests`, `generated_files`, `evidence_paths`,
`native_wall_time_seconds`, `usage_status`를 제공한다.

- attempts: `attempt`, `iteration`, `status`, `generated_files[{path,sha256,evidence_path}]`,
  `evidence_path`. 근거 경로는 logs 기준 상대경로다.
- requests: `request_id`, `role`, `model`, `status`, `duration_seconds`, `input_tokens`,
  `output_tokens`, `cost_usd`. 없는 값은 null이다. content/키/credential URL은 넣지 않는다.
- additive: `active_surface_hashes`, `evaluations[{purpose="native_inner",iteration,status,wall_time_seconds,evidence_paths}]`,
  `outer_evaluation{purpose="trusted_final",owner="GroupRunner.trial",count=null,wall_time_seconds=null}`.
  inner `evidence_paths`와 최상위 `evidence_paths`에는 실제 공식 `raw_result`의 검증된 상대경로를
  기록한다. upstream 이름을 유지한 `real_evaluator_result.json`은 bridge의 안전한 집계 summary이며,
  원본 private raw 결과와 구분한다.
- usage는 `partial` 또는 `unreported`; 응답 token이 있어도 전체 Agent 사용량으로 가장하지 않는다.
  `ExecutionResult.metrics.agent_tokens/agent_cost_usd`는 null이다. inner 평가 횟수만 별도 숫자로 준다.
  모델 요청 시간 합계·native wall time·outer 평가를 합쳐 같은 metric으로 이름 붙이지 않는다.
- 중단 전 `native-requests.json`·`native-progress.json`을 기록하여 API 실패/outer timeout에도
  완료 iteration과 실제 요청을 보존한다. `cleanup.json`에는 process group/관측 child PID가 있다.
- 공식 평가 전 `native-owned-network.json`을 기록한다. 정상·취소·timeout 후 원본 process group,
  새 session의 evaluator/model descendants 및 해당 network container만 정리한다.
  실제 Docker cleanup 호출은 이번 검증에서 모의이며 일반 child 종료는 실제 OS process로 검증했다.
- raw evidence·candidate·private 평가 산출물을 report server 공개 asset으로 노출하지 않는다.

## 5. 정확한 검증 명령과 결과

모든 CWD는 지정 C 워크트리다. 공유 Python 3.12.12, 새 native fixture는 사용하지 않는
`yaml` import만 test-local stub으로 제공했다. public processor와 평가 모의는 YAML parser를
호출하지 않는다. **실제 dependency readiness는 여전히 false이며 이 stub은 제품 fallback이 아니다.**

### 최종 unit·회귀

```bash
HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/home PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/tmp AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest test_native_ace test_native_cvdp test_ace_demo test_claude_code test_plugin_contracts test_research -q
```

최종 **`Ran 93 tests in 9.019s`, `OK`, 종료 코드 0, skip 없음**.
native 23개 + 기존 ACE/coding·Claude·plugin·연구 회귀 70개다.
테스트 이름의 live는 기존 모의 lifecycle 계약 이름이며 실제 외부 호출이 아니다.
전체 unit은 이번 C에서 재실행하지 않았다. P0의 기존 953개·15개 환경 오류 결과를 전체 녹색으로 바꾸어 기록하지 않는다.

핵심 증거:

- pinned `run_attempt`에서 실패 iteration 1 → reflector → 통과 iteration 2.
- 실제 coordinator API 경로가 실패 iteration 12에서 실행되고, RESTART 결정 뒤 iteration 13의
  previous candidate가 비워져 fresh-start 생성으로 이어짐.
- 실제 `native_worker.main` payload/독립 process/sidecar fixture.
- 세 역할 동일 transport/env 모델 설정; malformed completion/429/auth/timeout의 fail-closed.
- 실제 multi-file·nested/reordered bundle, private sentinel, 공식 pass/mismatch/infra/빈 결과.
- wrong pin/asset/Python/의존성 진단, child timeout·cancel 후 종료(새 OS process를 실행해 상태 확인).
- 후보 A/B의 active prompt·실제 imported code·hash 차이, usage 미제공 null.

TDD 중 누락 모듈 실패 → 구현 → 통과를 확인했다. 이후 중단 progress 누락과 reordered nested
target root 오류를 각각 재현하여 수정했다. CID 정밀화에서는 실제 lint-only와 alias build fixture가
기존 gate에서 실패하는 것을 확인한 뒤 public shape 검토에 맞춰 수정했다.
최종 diff 검토에서 source manifest의 미허용 metadata와 outer 준비 시간 미차감도
실패 테스트로 재현한 뒤 수정했다. harness 신규 필드의 loader 연결은 소유 밖이라 F/G에 명시적으로 인계했다.

### lint

```bash
HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/home PYTHONDONTWRITEBYTECODE=1 /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m ruff check . --no-cache
```

`All checks passed!`, 종료 코드 0. 기존 `make lint`의 워크트리-local `.venv` 경로 대신 공유
interpreter로 동일 Ruff 검사를 실행했다.

### 명시적 로컬 prepare

```bash
HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/home PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/tmp AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python examples/ace-rtl/native_prepare.py --upstream /Users/wt.jeong/workspace/agent-optimizer/external/ACE-RTL --source-output /var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/prepared-source-final --dataset /Users/wt.jeong/workspace/agent-optimizer/external/cvdp-data/5b807d945f6a99aa645f7e43a64a2115e281b4bf/cvdp_v1.1.0_nonagentic_code_generation_no_commercial.jsonl --task-output /var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/tasks-final.json --cid cid002 --cid cid004 --cid cid007 --cid cid016
```

종료 코드 0, 고정 소스 export와 **197개 validation-only task·27개 exclusion** 확인.
원본 private row는 임시 trusted tasks manifest에만 있다. 초기 정밀화 이전 `tasks.json`은
최종 판정 증거가 아니며 `tasks-final.json`이 최종 결과다. runtime 성공을 주장하지 않는다.

실제 `readiness(prepared-source-final, sys.executable)` 결과: `native_source=true`,
`native_python=false`(공유 코어 환경의 yaml 없음), `ready=false`, `live="not_run"`.
실모델·도구·Docker/network cleanup 성공·Ubuntu x86_64 live·F의 CLI 전체 연결은 미검증이다.

## 6. F/D/G/H 인계

**F**

- registry 파일 factory: `ace_native → examples/ace-rtl/native_adapter.py:ACENative`,
  native 최종 evaluator는 `native_evaluator.py:NativeCVDPEvaluator`.
- source/profile ID와 metadata는 §4·두 TOML을 사용한다. native를 기존 coding lifecycle로
  라우팅하지 않는다. source writer는 준비 반환 `path`를 local source 절대경로로 기록한다.
- 현재 `config.load_experiment`의 harness profile allow-list에는 `native`·`compatibility`가 없다.
  F/G가 예제 profile의 이 두 필드를 허용·검증하는 최소 loader 연결과 native preflight capability를
  추가해야 한다. Agent source TOML은 기존 `load_agent` 계약으로 직접 읽히며 별도 schema 확장이 없다.
- `native.dataset`은 public task manifest가 아닌 고정 원본 HF jsonl의 trusted 절대경로다.
  그 파일을 후보/task workspace로 복사하거나 symlink하지 않는다. Task의 native public descriptor는
  adapter가 pinned 원본과 비교한다. split 변경은 `prepare_dataset(..., splits=...)`로 descriptor와 동기화한다.
- 모델 입력은 기존 세 환경값이며 baseline/file_variants에는 Optimizer API를 요구하지 않는다.
  native Agent 모델 요구와 연구 Optimizer 모델 요구를 별도로 표시한다.
- GEPA `file="native/guidance.md"`, Meta-Harness `file="native/orchestration.py"`,
  `required_symbol="guidance"`. 별도 build argv/옛 coding scaffold seed가 필요하지 않다.
- 기존 first-party 설치 pin `ae0874fb94d94284a07a17d84ef60058ed9a97b6`은 이 신규 파일을 포함하지 않는다.
  배포 pin/selected_files/연관 dependency fingerprint를 F가 명시적으로 연결해야 한다.
  native adapter의 sibling 파일들과 기존 `evaluator.py`·network driver도 배포/ fingerprint 대상이다.
- `GroupRunner.trial`의 `result.json/trial_completed.native_execution` producer에서 sidecar를 안전 검증해
  요약하고 outer 평가 횟수/시간을 실제 최종 평가 자료로 연결한다. C의 inner pass를 최종 점수로 쓰지 않는다.

**D**: P0 sidecar의 optional `native_execution`만 소비한다. 금액/usage/outer count가 null인 의미,
inner/outer 목적과 부분 사용량을 보존하고 raw prompt/RTL/private 자료를 renderer로 가져오지 않는다.

**G**: source pin/lock/asset drift·Python 3.12/yaml/pydantic_settings·`ps` availability,
고정 dataset hash/public descriptor mismatch·CVDP repo/driver pin·OSS_SIM 이미지 identity,
모델 URL/auth/429/invalid response·inner/outer timeout·고유 network cleanup 실패를 진단에 연결한다.
engine readiness와 평가/모델 readiness를 합칠 때 검사만으로 모델·다운로드·Docker 실행을 만들지 않는다.
CID007 PNR/상용 helper exclusion은 설치 오류로 위장하거나 합성 fallback으로 처리하지 않는다.

**H**: 위 exact 명령과 준비 자산·ID·모델 환경·validation-only 기본을 안내한다.
live 성공/197개 정답/논문 재현을 주장하지 않는다. 기존 coding 프로필은 별도 선택으로 보존한다.

## 7. 최종 상태

기본 저장소 `main`·사용자 `.gitignore` 변경과 ZIP을 보존했다. 다른 워크트리·upstream·prepared 데이터는
수정하지 않았다. C 소유 파일과 이 보고서만 한국어 로컬 커밋하며 push/PR은 사용자 지시로 하지 않는다.
통합 소비자 등록·배포·실환경 준비/검증은 위 인계의 후속 작업이다.

## 8. 수정 라운드 1 — 실패 증거·종료 시간 보완

2026-10-01, `final-mvp-c-review-20261001.md`의 **I1·I2·M1·M2를 보완했다**.
원래 §5의 93개 결과는 최초 구현 시점의 증거이며, 이번 라운드의 covering 검증은 아래와 같다.

- 모든 worker 예외와 adapter 종료에 `native_artifacts.finalize`를 적용하여 실제 요청 journal을
  최종 sidecar에 대체 병합한다. output 검증/evaluator/API 오류 후에도 완료 request·duration·응답 token을
  보존하고 input/output 중 하나만 있으면 `partial`이다. 없는 사용량·비용은 null이며 prompt/private/키는 복제하지 않는다.
- native 전용 `native_cleanup.py`가 기존 evaluator의 무제한 누적 cleanup을 대체한다.
  adapter와 inner evaluator는 예산의 `min(1초, 10%)`를 정리에 예약한다. 모든 Docker 명령은
  같은 deadline의 잔여 시간 이하(개별 최대 1초)로 제한되고, 완료 marker는 건너뛴다.
  `ps`/wait도 outer deadline으로 제한한다. 미완료는 `incomplete/deferred`로 남기며
  정리 실패를 정답/정리 성공으로 바꾸지 않는다. 동기 filesystem 기록과 OS scheduling의 소규모 지연은
  테스트 허용 오차에 포함되며 iteration별 별도 15초 예산은 사라졌다.
- 준비 시작부터 sidecar를 기록하고 readiness checks·안전한 diagnostic/error_type을 보존한다.
  검증할 수 없는 source revision/hash/candidate hash/task ID는 null이다. 요청 미실행은 빈 requests·unreported,
  cleanup 미시작은 `not_started`다. F/D/G 소비자는 nullable provenance와 additive cleanup/checks를 허용해야 한다.
- F 배포·dependency fingerprint에 `native_artifacts.py`·`native_cleanup.py`를 추가해야 한다.

실행 CWD는 동일 C 워크트리이며 정확한 명령:

```bash
HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/home PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/tmp AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest test_native_ace test_native_cvdp -q
HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/home PYTHONDONTWRITEBYTECODE=1 /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m ruff check . --no-cache
```

**28개/4.788초 OK, skip 없음, Ruff 통과; 두 명령 모두 종료 코드 0.**
실제 worker main→adapter 예외 보존, output-only usage, 완료 network 재정리 금지,
지연 Docker 모의의 전체 종료 상한, nullable readiness/unsupported sidecar를 검증했다.
실모델·실 Docker 정리·실도구는 여전히 `not_run`이다. 소유 밖 수정·설치·push·하위 에이전트는 없다.
