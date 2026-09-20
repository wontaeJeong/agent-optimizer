# 출처와 고정 버전 확인

확인일: **2026-09-20**. 요구사항의 근거는 사용자 인수인계([CONTEXT.md](CONTEXT.md))이며,
아래 외부 자료는 기술 사실과 연결 방식 검토의 근거다. 자료를 읽었다는 것은 외부 도구를 실행하거나
논문 결과를 재현했다는 뜻이 아니다. upstream `SKILL.md`의 실행·역할 Agent 생성 지시는 검토 자료로만 읽었다.

## 고정 버전

| 대상 | 전달 당시 고정 SHA | 현재 로컬 설정과 대조 |
|---|---|---|
| ACE-RTL | `fead921f18bb57345b5a41ef93ba625be208e99c` | `examples/ace-rtl/source.toml`의 revision과 `environment/setup.py`의 REPOS가 모두 일치 |
| CVDP | `8e894cf74414ab1eaea1e2b4e80a02f123df07b6` | `examples/ace-rtl/environment/setup.py`의 REPOS가 일치 |

두 SHA는 최신 버전이라는 뜻이 아니다. 이번 문서 작업에서 변경하지 않았다.
아래 고정 URL의 본문은 같은 SHA의 raw 파일로 열람했다. 외부 checkout 설치·실행은 하지 않았다.

## 판단별 1차 출처

로컬 파일은 프로젝트 루트 기준이다.

| 출처 | 뒷받침하는 판단·사용 로컬 파일 | 실제 확인 범위 / 변경 시 재확인 |
|---|---|---|
| [ACE README](https://github.com/NVlabs/ACE-RTL/blob/fead921f18bb57345b5a41ef93ba625be208e99c/README.md) | 코딩 Agent의 스킬 사용과 직접 native runner 실행 경로가 모두 안내되어 있다. `examples/ace-rtl/README.md`, `source.toml`, `adapter.py`의 프로필 구분 근거. | 본문 확인. native 명령, 모델 경로, Python 의존성, 평가 환경을 버전 변경 시 다시 대조. 실행 성공·성능 수치는 확인하지 않음. |
| [ACE SKILL](https://github.com/NVlabs/ACE-RTL/blob/fead921f18bb57345b5a41ef93ba625be208e99c/skills/ace-rtl/SKILL.md) | 역할 구성·벤치마크 준비·반복 평가 지침이 포함된다. `source.toml`의 prompt_file이며 `adapter.py`는 데이터 다운로드·ACE benchmark runner 호출을 금지하는 별도 안내를 앞에 붙인다. | 본문 확인. 두 안내가 실제로 어떻게 해석되는지는 미검증. 스킬 경로·내용·상용 EDA 안내와 로컬 제한의 충돌을 재확인. |
| [ACE 구성 요소](https://github.com/NVlabs/ACE-RTL/blob/fead921f18bb57345b5a41ef93ba625be208e99c/skills/ace-rtl/references/agent-components.md) | `ace_agent_runner.py`, `ace_cvdp_native_runner.py`, Generator/FocusedDebugger/FreshStartCoordinator 위치 안내. `source.toml`의 editable 역할 파일과 향후 native 어댑터 검토 근거. | 구성 지도 확인. 파일 위치 안내만으로 해당 코드가 로컬 실행에서 호출된다고 주장하지 않음. 새 프로필에서는 실제 호출 경로·trace 확인 필요. |
| [ACE 역할·실행 흐름](https://github.com/NVlabs/ACE-RTL/blob/fead921f18bb57345b5a41ef93ba625be208e99c/skills/ace-rtl/references/agent-workflow.md) | 원본 지침에는 평가 보고서 기반 반복·재시작·역할 상태·병렬 시도가 있다. `adapter.py` 및 `runner.py`의 단일 Harness 호출 후 외부 평가와 구별하는 근거. | 문서상 루프 확인. 원본 Python 전체 호출 그래프·런타임 동작은 미검증. 반복 중 피드백 경계와 예산을 native 연결 전에 재검토. |
| [CVDP README](https://github.com/NVlabs/cvdp_benchmark/blob/8e894cf74414ab1eaea1e2b4e80a02f123df07b6/README.md) | 공식 OSS 이미지 빌드, Python 3.12 권장, golden/LLM/agentic 경로 및 heavy 데이터의 별도 요구사항. `examples/ace-rtl/environment/setup.py`, `setup.sh`, `evaluator.py`의 환경·범위 판단에 사용. | 본문 확인. `run_benchmark.py`의 옵션·제출 처리 전체를 검증한 것은 아님. 이미지 변수, 데이터 형식, golden 모드에서 후보 output.context 평가 여부를 한 문제로 재확인. |
| [공식 Dockerfile.sim](https://github.com/NVlabs/cvdp_benchmark/blob/8e894cf74414ab1eaea1e2b4e80a02f123df07b6/docker/Dockerfile.sim) | Icarus `v13_0`, Yosys `yosys-0.40`, Verilator `v5.038` 설치 단계가 있다. `environment/setup.py`가 이를 재사용하므로 별도 시뮬레이터 Dockerfile을 만들지 않는다. | 파일 확인, 빌드 미실행. 베이스 이미지·도구 태그·Python 패키지·생성 이미지 ID 재확인 필요. OpenCode/ACE native 의존성 준비를 대신하지 않음. |
| [CVDP report.py](https://github.com/NVlabs/cvdp_benchmark/blob/8e894cf74414ab1eaea1e2b4e80a02f123df07b6/src/report.py) | binary 문제는 test result=0을 통과로 집계하지만 score-based 범주는 별도 처리한다. `examples/ace-rtl/evaluator.py`의 binary 판정과 `prepare.py`의 제한 범위 근거. | 소스 확인. 로컬 evaluator는 공식 report 전체를 재현하지 않으며 빈 tests는 거부한다. raw_result 구조, 범주별 점수 의미, 환경 오류 분류를 버전 변경 시 재검토. |
| [CVDP 데이터셋](https://huggingface.co/datasets/nvidia/cvdp-benchmark-dataset) | 공식 데이터 배포처. `prepare.py`의 importer 확장과 데이터 사용 조건 확인에 사용. | 배포 페이지 확인. 전체 데이터·개별 문제 호환성 미검증, HF revision 미고정. 현재 `setup.sh`는 HF 전체 다운로드 대신 고정 CVDP repo의 `example_dataset/cvdp_v1.1.0_example_nonagentic_code_generation_no_commercial.jsonl`을 사용한다. 전환 시 파일명·revision·hash·의존성·출력 대상 재검토. |
| [OpenCode CLI](https://opencode.ai/docs/cli/) | `opencode run`, `--format json`, `--model`, `--agent`의 비대화형 실행 계약. `src/agent_optimizer/harnesses/opencode.py`, `examples/rtl-debugger/Dockerfile`에서 사용. | 공식 문서 및 Context7의 명령 정의 확인. 이 URL은 고정 버전 문서가 아니다. 로컬 Dockerfile은 정확한 OPENCODE_VERSION을 요구하지만 값은 미선정. 선택 버전의 JSON 이벤트·오류·child session 사용량을 실제 trace로 검증해야 함. |
| [Yosys 0.40 read_verilog](https://yosyshq.readthedocs.io/projects/yosys/en/0.40/cmd/read_verilog.html), [write_verilog](https://yosyshq.readthedocs.io/projects/yosys/en/0.40/cmd/write_verilog.html), [synth 구현](https://github.com/YosysHQ/yosys/blob/yosys-0.40/techlibs/common/synth.cc) | `examples/rtl-debugger/iverilog.py`의 `-sv`, `-noautowire`, `-noattr`, `synth -top ... -flatten -noabc` 구문과 합성 netlist 출력 근거. frontend의 작은 SystemVerilog 부분집합, synthesis-time display 출력, process 변환 이후 netlist 출력 경계와 synth의 hierarchy 검사를 확인. | Task 4에서 Context7 우선 검색에 Yosys 결과가 없어 공식 0.40 문서/소스를 직접 확인. 실제 Yosys/Icarus 미설치로 동작 검증은 skip. `tests/test_rtl_evaluation.py`의 실제 도구 characterization과 정답/오답 검증을 공식 CVDP 이미지에서 실행해야 함. |

상용 EDA를 제외한다는 결정은 **사용자 요구사항**이다. upstream에 상용 경로가 존재해도 이 제품의
지원 범위가 되지 않는다. 외부 소스/데이터의 포함·사용 조건은 [THIRD_PARTY.md](../THIRD_PARTY.md)도 확인한다.

## 연구 Optimizer 출처: 후보 조사와 채택 확정을 구분

현재 `src/agent_optimizer/optimizers/{gepa,meta_harness,ecdysis}.py`는 오류를 내는 슬롯이며,
기존 로컬 문서에는 논문·공식 repo·버전 연결 근거가 없었다. 2026-09-20 GitHub 이름 검색 후
다음 README를 직접 확인했다. **외부 후보의 존재와 README의 논문 링크는 확인됨**이지만,
원래 대화에서 의도한 대상인지, 팀이 채택할 구현·버전인지는 모두 **미확정**이다.

| 로컬 슬롯 | 조사에서 확인한 후보 README와 그 안의 논문 링크 | 남은 확인 |
|---|---|---|
| `gepa.py` | [gepa-ai/gepa](https://github.com/gepa-ai/gepa/blob/main/README.md) → [GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning](https://arxiv.org/abs/2507.19457) | 채택 대상, 논문 버전, 패키지/commit, 연결 API 미확정 |
| `meta_harness.py` | [stanford-iris-lab/meta-harness](https://github.com/stanford-iris-lab/meta-harness/blob/main/README.md) → [Meta-Harness: End-to-End Optimization of Model Harnesses](https://arxiv.org/abs/2603.28052) | reference 구현과 별도 artifact 중 대상, 논문 버전, commit 미확정 |
| `ecdysis.py` | [cuiyu-ai/Ecdysis](https://github.com/cuiyu-ai/Ecdysis/blob/main/README.md) → [Ecdysis: Efficient and Effective Training of Runtime Harnesses for LLM Agents](https://arxiv.org/abs/2609.11677) | 동명 프로젝트와 구별, 원래 의도와의 일치, 논문 버전, commit 미확정 |

이 표는 채택 결정이나 공식성에 대한 독립 검증이 아니다. 링크된 논문 본문·성능 수치·실험 재현은
검증하지 않았으며 README의 수치를 제품 문서에 옮기지 않는다. `main`은 조사 시점의 가변 참조다.
첫 알고리즘 담당자가 저자/논문과 repo 관계를 대조하고 채택 SHA 또는 release를 고정한 뒤,
이 표를 갱신하고 공통 계약·train/validation 경계에 맞춰 연결한다.

## 버전 변경 절차

### Task 5 pinned data / provider inspection (2026-09-20)

`examples/ace-rtl/environment/setup.py` downloads exactly three files from HF dataset revision
`5b807d945f6a99aa645f7e43a64a2115e281b4bf`. Expected SHA-256 values were obtained **after**
checking downloaded bytes against the independent Git blob OIDs in the
[fixed-revision HF tree metadata](https://huggingface.co/api/datasets/nvidia/cvdp-benchmark-dataset/tree/5b807d945f6a99aa645f7e43a64a2115e281b4bf?recursive=false).
For these non-LFS files, the metadata hash is SHA-1 of `blob <byte-size>\0<content>`.
Cache acceptance subsequently uses the recorded SHA-256, not a newly observed download hash.

| File | Trusted Git blob OID | Verified SHA-256 |
|---|---|---|
| `cvdp_v1.1.0_nonagentic_code_generation_no_commercial.jsonl` | `53ffadb3c7159b192692a9e23f8fc1dbc262feda` | `cbcd81295561ebb16e4d857e096f4d9908d042c33aff3b58abf236e868411857` |
| `LICENSE` | `1dcd8913d705dd3a13df25520f6220be8a333a86` | `cedcd612607018ad841d87d7f1c877630778a50c71692610fe76acdc22700719` |
| `NOTICE` | `74a3fc2c3ec54b780888f86ec72b705dfd444fcf` | `3d8753e57eab52910ccb61a1ee09113c43e9382ccd98d5860b5621aff8d932dd` |

Inspected all 302 row metadata records (78 `cid003`), actual QAM16 rows, and the pinned CVDP
LFSR reference/checker. All 302 rows have output target keys with reference contents removed;
250 rows have no Dockerfile and use a Compose image directly. `prepare.py` supports that reviewed
shape and literal source metadata, while recording exclusion reasons for unsupported categories/images/paths.
The fixed CVDP `run_benchmark.py`, `src/dataset_processor.py`, `src/repository.py`, and
`src/network_util.py` establish candidate `output.context` evaluation in golden mode, raw result
paths, `OSS_SIM_IMAGE`, and the `--network-name` CLI. This inspection is distinct from runtime verification.

OpenCode `v1.18.31` tag resolves to `014614d35b397775e5d397a490fc72368c894ec2`.
Context7 `/anomalyco/opencode` provider docs and the
[pinned provider implementation](https://github.com/anomalyco/opencode/blob/v1.18.31/packages/opencode/src/provider/provider.ts)
were checked for OpenRouter and bundled `@ai-sdk/openai-compatible` support.
The example configs use documented `{env:VAR}` substitution and `model`/`small_model`.
The [pinned installer](https://github.com/anomalyco/opencode/blob/v1.18.31/packages/opencode/script/postinstall.mjs)
was inspected when diagnosing the amd64 image build failure. No source SHA was updated.
Context7 `/astral-sh/uv` documents the isolated `sync --frozen --python 3.12`, `venv`,
`pip install --python`, and global `--offline` flags used by setup.
Controller follow-up used Context7 `/docker/cli` for `docker version --format` server templates;
actual `{{.Server.Os}}/{{.Server.Arch}}` returned `linux/arm64`. This daemon-native selection now
replaces the original fixed-amd64 default; explicit overrides remain supported without post-failure fallback.

1. 변경 대상의 고정 출처와 로컬 소비 파일을 위 표에서 찾는다. ACE SHA 두 곳은 함께 대조한다.
2. upstream diff에서 경로·CLI·입출력·채점·의존성 변화를 확인한다. 문서 정리를 이유로 자동 최신화하지 않는다.
3. 소스 SHA와 데이터 hash, OpenCode 버전, 이미지 ID/digest, 모델·예산을 기록한다.
   현재 setup lock은 CVDP 이미지 ID와 패키지 목록을 기록하지만 OpenCode 이미지 고정까지 자동 보장하지 않는다.
4. 모의 계약 테스트 후 지원하는 OSS 한 문제를 실환경 검증한다. 결과와 미검증 영역을
   [verification.md](verification.md), [status.md](status.md)에 갱신한다.
