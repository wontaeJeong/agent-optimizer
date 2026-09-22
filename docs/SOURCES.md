# 출처와 고정 버전 확인

확인일: **2026-09-20**. 요구사항의 근거는 사용자 인수인계([CONTEXT.md](CONTEXT.md))이며,
아래 외부 자료는 기술 사실과 연결 방식 검토의 근거다. 자료를 읽었다는 것은 외부 도구를 실행하거나
논문 결과를 재현했다는 뜻이 아니다. upstream `SKILL.md`의 실행·역할 Agent 생성 지시는 검토 자료로만 읽었다.

## 고정 버전

| 대상 | 전달 당시 고정 SHA | 현재 로컬 설정과 대조 |
|---|---|---|
| ACE-RTL | `fead921f18bb57345b5a41ef93ba625be208e99c` | `examples/ace-rtl/source.toml`의 revision과 `environment/setup.py`의 REPOS가 모두 일치 |
| CVDP | `8e894cf74414ab1eaea1e2b4e80a02f123df07b6` | `examples/ace-rtl/environment/setup.py`의 REPOS가 일치 |

두 SHA는 최신 버전이라는 뜻이 아니다. MVP hardening에서도 변경하지 않았다.
아래 고정 URL의 본문은 같은 SHA의 raw 파일 및 실제 checkout과 대조했다.
Task 5/6에서 실제 setup/평가를 실행한 범위는 [verification.md](verification.md)에 별도로 기록한다.

## 판단별 1차 출처

로컬 파일은 프로젝트 루트 기준이다.

| 출처 | 뒷받침하는 판단·사용 로컬 파일 | 실제 확인 범위 / 변경 시 재확인 |
|---|---|---|
| [ACE README](https://github.com/NVlabs/ACE-RTL/blob/fead921f18bb57345b5a41ef93ba625be208e99c/README.md) | 코딩 Agent의 스킬 사용과 직접 native runner 실행 경로가 모두 안내되어 있다. `examples/ace-rtl/README.md`, `source.toml`, `adapter.py`의 프로필 구분 근거. | 본문 확인. native 명령, 모델 경로, Python 의존성, 평가 환경을 버전 변경 시 다시 대조. 실행 성공·성능 수치는 확인하지 않음. |
| [ACE SKILL](https://github.com/NVlabs/ACE-RTL/blob/fead921f18bb57345b5a41ef93ba625be208e99c/skills/ace-rtl/SKILL.md) | 역할 구성·벤치마크 준비·반복 평가 지침이 포함된다. `source.toml`의 prompt_file이며 `adapter.py`는 데이터 다운로드·ACE benchmark runner 호출을 금지하는 별도 안내를 앞에 붙인다. | 본문 확인. 두 안내가 실제로 어떻게 해석되는지는 미검증. 스킬 경로·내용·상용 EDA 안내와 로컬 제한의 충돌을 재확인. |
| [ACE 구성 요소](https://github.com/NVlabs/ACE-RTL/blob/fead921f18bb57345b5a41ef93ba625be208e99c/skills/ace-rtl/references/agent-components.md) | `ace_agent_runner.py`, `ace_cvdp_native_runner.py`, Generator/FocusedDebugger/FreshStartCoordinator 위치 안내. `source.toml`의 editable 역할 파일과 향후 native 어댑터 검토 근거. | 구성 지도 확인. 파일 위치 안내만으로 해당 코드가 로컬 실행에서 호출된다고 주장하지 않음. 새 프로필에서는 실제 호출 경로·trace 확인 필요. |
| [ACE 역할·실행 흐름](https://github.com/NVlabs/ACE-RTL/blob/fead921f18bb57345b5a41ef93ba625be208e99c/skills/ace-rtl/references/agent-workflow.md) | 원본 지침에는 평가 보고서 기반 반복·재시작·역할 상태·병렬 시도가 있다. `adapter.py` 및 `runner.py`의 단일 Harness 호출 후 외부 평가와 구별하는 근거. | 문서상 루프 확인. 원본 Python 전체 호출 그래프·런타임 동작은 미검증. 반복 중 피드백 경계와 예산을 native 연결 전에 재검토. |
| [CVDP README](https://github.com/NVlabs/cvdp_benchmark/blob/8e894cf74414ab1eaea1e2b4e80a02f123df07b6/README.md) | 공식 OSS 이미지 빌드, Python 3.12 권장, golden/LLM/agentic 경로 및 heavy 데이터의 별도 요구사항. `examples/ace-rtl/environment/setup.py`, `setup.sh`, `evaluator.py`의 환경·범위 판단에 사용. | 본문 확인. `run_benchmark.py`의 옵션·제출 처리 전체를 검증한 것은 아님. 이미지 변수, 데이터 형식, golden 모드에서 후보 output.context 평가 여부를 한 문제로 재확인. |
| [공식 Dockerfile.sim](https://github.com/NVlabs/cvdp_benchmark/blob/8e894cf74414ab1eaea1e2b4e80a02f123df07b6/docker/Dockerfile.sim) | Icarus `v13_0`, Yosys `yosys-0.40`, Verilator `v5.038` 설치 단계가 있다. `environment/setup.py`가 변경 없이 재사용한다. | ARM64 및 native Ubuntu x86_64 실제 빌드/도구 실행·정답/오답 smoke 확인. Mac amd64 에뮬레이션 실패 및 Ubuntu 첫 FROM 참조 실패와 `10baa46` 수정 후 통과를 verification에 구분해 기록. |
| [CVDP report.py](https://github.com/NVlabs/cvdp_benchmark/blob/8e894cf74414ab1eaea1e2b4e80a02f123df07b6/src/report.py) | binary 문제는 test result=0을 통과로 집계하지만 score-based 범주는 별도 처리한다. `examples/ace-rtl/evaluator.py`의 binary 판정과 `prepare.py`의 제한 범위 근거. | 소스 확인. 로컬 evaluator는 공식 report 전체를 재현하지 않으며 빈 tests는 거부한다. raw_result 구조, 범주별 점수 의미, 환경 오류 분류를 버전 변경 시 재검토. |
| [CVDP 데이터셋](https://huggingface.co/datasets/nvidia/cvdp-benchmark-dataset) | 공식 데이터 배포처. `prepare.py`의 importer와 데이터 사용 조건 근거. | 아래 고정 HF revision/신뢰 hash로 full no_commercial 파일을 확보. 302개 중 71개 지원 형태·231개 제외. 이는 71개 시뮬레이션 통과가 아니며 실제 evaluator smoke는 별도 고정 repo LFSR 예제. |
| [OpenCode CLI](https://opencode.ai/docs/cli/) | `opencode run`, `--format json`, `--model`, `--agent`의 비대화형 실행 계약. `src/agent_optimizer/harnesses/opencode.py`, `examples/rtl-debugger/Dockerfile`에서 사용. | 공식 문서/Context7 및 실제 1.18.31 CLI/config 확인. URL은 가변 문서다. 모델 inference trace·child session 전체 사용량은 미검증. |
| [Yosys 0.40 read_verilog](https://yosyshq.readthedocs.io/projects/yosys/en/0.40/cmd/read_verilog.html), [write_verilog](https://yosyshq.readthedocs.io/projects/yosys/en/0.40/cmd/write_verilog.html), [synth 구현](https://github.com/YosysHQ/yosys/blob/yosys-0.40/techlibs/common/synth.cc) | `examples/rtl-debugger/iverilog.py`의 `-sv`, `-noautowire`, `-noattr`, `synth -top ... -flatten -noabc` 및 hierarchy 검사 근거. | 공식 ARM64 이미지에서 실도구 9개 통과. 실제 `$display` → netlist `$write` 보존 확인: 합성 단독 정화 주장은 틀리며 입력 제한과 private mismatch/nonzero-exit 검사가 필수. |

상용 EDA를 제외한다는 결정은 **사용자 요구사항**이다. upstream에 상용 경로가 존재해도 이 제품의
지원 범위가 되지 않는다. 외부 소스/데이터의 포함·사용 조건은 [THIRD_PARTY.md](../THIRD_PARTY.md)도 확인한다.

## 연구 Optimizer 출처: 후보 조사와 채택 확정을 구분

과거 `src/agent_optimizer/optimizers/{gepa,meta_harness,ecdysis}.py`의 오류 슬롯은 현재
`deferred/src/agent_optimizer/optimizers/*.py.txt`에 보존하며 [복원 경로](../deferred/README.md)를 따른다.
현재 팀 연결 소비 경로는 `experiments/optimizer-template/`의 명시적 파일 플러그인이다.
기존 로컬 문서에는 논문·공식 repo·버전 연결 근거가 없었다. 2026-09-20 GitHub 이름 검색 후
다음 README를 직접 확인했다. **외부 후보의 존재와 README의 논문 링크는 확인됨**이지만,
원래 대화에서 의도한 대상인지, 팀이 채택할 구현·버전인지는 모두 **미확정**이다.

| 보류 슬롯 원래 파일명 | 조사에서 확인한 후보 README와 그 안의 논문 링크 | 남은 확인 |
|---|---|---|
| `gepa.py` | [gepa-ai/gepa](https://github.com/gepa-ai/gepa/blob/main/README.md) → [GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning](https://arxiv.org/abs/2507.19457) | 채택 대상, 논문 버전, 패키지/commit, 연결 API 미확정 |
| `meta_harness.py` | [stanford-iris-lab/meta-harness](https://github.com/stanford-iris-lab/meta-harness/blob/main/README.md) → [Meta-Harness: End-to-End Optimization of Model Harnesses](https://arxiv.org/abs/2603.28052) | reference 구현과 별도 artifact 중 대상, 논문 버전, commit 미확정 |
| `ecdysis.py` | [cuiyu-ai/Ecdysis](https://github.com/cuiyu-ai/Ecdysis/blob/main/README.md) → [Ecdysis: Efficient and Effective Training of Runtime Harnesses for LLM Agents](https://arxiv.org/abs/2609.11677) | 동명 프로젝트와 구별, 원래 의도와의 일치, 논문 버전, commit 미확정 |

이 표는 채택 결정이나 공식성에 대한 독립 검증이 아니다. 링크된 논문 본문·성능 수치·실험 재현은
검증하지 않았으며 README의 수치를 제품 문서에 옮기지 않는다. `main`은 조사 시점의 가변 참조다.
첫 알고리즘 담당자가 저자/논문과 repo 관계를 대조하고 채택 SHA 또는 release를 고정한 뒤,
이 표를 갱신하고 공통 계약·train/validation 경계에 맞춰 연결한다.

## Task 5 pinned data / provider inspection (2026-09-20)

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

## Task 6 Python driver lock / CI 확인

입력은 [고정 CVDP requirements.txt](https://github.com/NVlabs/cvdp_benchmark/blob/8e894cf74414ab1eaea1e2b4e80a02f123df07b6/requirements.txt)이며
SHA-256은 `f79bf21e2e98b96016cf7992afb6a4df4bcfac64d07ff811195d22ddf0af6ad2`다.
upstream 12개 직접 pin을 그대로 사용하여 uv 0.10.7로 32개 전이 포함 pin을 생성했다.

```bash
uv pip compile --universal --python-version 3.12 --no-annotate --no-header external/cvdp_benchmark/requirements.txt
```

출력과 provenance 주석을 `examples/ace-rtl/environment/requirements-cvdp-py312.txt`에 보존했다.
lock SHA-256: `8de4e036b1fd7c670fc9cca44d7d3f5cac2f31cf320ce96b2593a4db6883d039`.
setup은 입력 hash를 검증하고 `uv pip sync`로 별도 driver를 맞춘다. 환경 lock에 compiled hash와
실제 설치 목록을 남기며 offline/doctor/smoke에서 drift를 거부한다. 재생성은 명시적 유지보수 작업이며
setup에서 dependency resolution을 새 버전으로 갱신하지 않는다. 배포 wheel hash나 Docker 내부
OS package까지 고정하는 hermetic lock은 아니다.

Context7 `/astral-sh/uv`에서 universal compile, Python target, sync, offline 계약을 확인했다.
`/websites/github_en_actions`에서 boolean dispatch 입력과 `gh workflow run --ref`를 확인했다.
`.github/workflows/ci.yml`은 이미 존재하는 workflow의 수동 입력을 확장한다. 원격 Ubuntu 실행 결과는
초기 run `35513674595`(코어 통과), `35513687494`(공식 setup/offline 통과·첫 smoke 실패)를 보존한다.
`10baa46`의 후속 run `35515595857`(PR 코어 통과), `35515600629`(공식 통합 포함 전체 통과)는
수정 후 로컬 ARM64 검증과 구분한다. 정확한 범위는 [verification.md](verification.md#2026-09-20-native-ubuntu-repeat--passed)를 따른다.

최종 수정에서 같은 고정 CVDP `src/repository.py`의 `apply_template_substitution`과 `log_run`을
재확인했다. `OSS_SIM_IMAGE`는 Dockerfile에도 그대로 치환되며 Compose build/launch 실패도
`result=1, error_msg=null`로 저장할 수 있다. Context7 `/docker/docs`의
[FROM 문법](https://docs.docker.com/reference/dockerfile/#from)은 `<image>:<tag>` 또는
`<image>@<digest>`이며 로컬 config image ID와 registry manifest digest는 다르다.
`environment/setup.py:verified_sim_image`는 로컬 tag의 inspect ID/platform을 lock과 대조하고
`scripts/dev.py`가 이 tag를 공식 driver에 전달한다. `evaluator.py`는 owned prefix에서 검증한
private log의 Docker 오류를 환경 실패로 분류한다. upstream SHA/파일 변경은 없다.

## 개발환경 온보딩 설치 출처 (2026-09-21)

Context7 `/astral-sh/uv`, `/docker/docs`로 아래 설치 계약을 확인하고 실제
`scripts/bootstrap.sh`, `scripts/dev.py`, `examples/ace-rtl/environment/diagnostics.py`와 대조했다.
소비 문서는 [development.md](development.md), README와 CONTRIBUTING이다. 아래 URL은 가변 설치
안내이며 기존 ACE/CVDP/HF SHA·driver lock·OpenCode/uv 신규 설치 pin은 갱신하지 않았다.

| 공식 출처 | 확인·사용 범위 |
|---|---|
| [uv 설치](https://docs.astral.sh/uv/getting-started/installation/), [installer 설정](https://docs.astral.sh/uv/reference/installer/) | 버전별 installer URL, `UV_INSTALL_DIR`, `UV_NO_MODIFY_PATH`. bootstrap은 `https://astral.sh/uv/0.10.7/install.sh`와 repo-local 경로를 사용하며 기존 uv는 재사용한다. |
| [uv Python 설치](https://docs.astral.sh/uv/guides/install-python/), [CLI reference](https://docs.astral.sh/uv/reference/cli/) | 필요한 Python 자동 준비, offline 네트워크 차단과 `UV_PYTHON_DOWNLOADS=never`. 신규 환경 Python 3.12와 frozen sync 명령 안내 근거. |
| [Docker Desktop Mac](https://docs.docker.com/desktop/setup/install/mac-install/) | CPU별 설치와 Desktop 시작. 이 작업의 실제 실행은 기존 Colima Docker daemon이며 Desktop 신규 설치를 재현한 것은 아니다. |
| [Docker Engine Ubuntu](https://docs.docker.com/engine/install/ubuntu/), [Compose plugin](https://docs.docker.com/compose/install/linux/) | Docker apt 저장소에서 Engine/Buildx/Compose plugin 설치. 현재 작업에서 Ubuntu OS 설치를 실행한 것은 아니다. |
| [daemon 시작](https://docs.docker.com/engine/daemon/start/), [Linux 후속 설정](https://docs.docker.com/engine/install/linux-postinstall/) | `sudo systemctl start docker`, 사용자 socket 접근과 docker 그룹 권한 안내. |

## 선택적 네트워크 설정 출처 (2026-09-21)

- Context7 `/docker/docs`: [proxy build args](https://docs.docker.com/engine/cli/proxy/),
  [named contexts](https://docs.docker.com/build/building/context/#named-contexts),
  [Compose environment](https://docs.docker.com/reference/compose-file/services/#environment).
  `network.py`의 이름 기반 proxy 전달·CA 전용 context와 `network_driver.py`의 null 환경 참조 근거.
- Context7 `/astral-sh/uv`: `SSL_CERT_FILE`은 PEM bundle이며 기본 trust를 대체한다.
  `network.py`는 전체 번들을 명시적으로 요구하고 TLS 검증을 해제하지 않는다.
- 온보딩 통합 시 [uv 0.10.7 installer](https://astral.sh/uv/0.10.7/install.sh)의
  curl/wget archive 다운로드를 대조했다. `scripts/bootstrap.sh`는 curl/uv CA 환경과
  wget의 임시 `WGETRC`를 installer 자식에도 전달한다. 신규 설치는 격리된 계약 테스트로 확인했다.
- [OpenCode network](https://opencode.ai/docs/network/): HTTP_PROXY/HTTPS_PROXY/NO_PROXY,
  NODE_EXTRA_CA_CERTS 지원 및 localhost 우회 지침. `network.py`와 `docs/network.md`에서 사용.
  문서는 가변 출처이며 이번 실제 확인은 1.18.31 설치/버전·이미지 설정까지다.
- 위 고정 CVDP `Dockerfile.sim`과 `src/repository.py`를 재열람했다. Dockerfile의 첫 apt 뒤
  Git/curl/uv 설치와, driver가 private harness Compose를 복원하여 `compose run`으로 실행하는 경로에
  적용한다. upstream SHA·도구 버전·채점 코드는 변경하지 않았다.

## 버전 변경 절차

### 2026-09-22 모델 endpoint 연결 확인

- Context7 `/anomalyco/opencode`의 custom provider(`@ai-sdk/openai-compatible`), 환경 치환,
  로컬 plugin의 `config` hook 문서를 확인했다.
- 위 고정 OpenCode **v1.18.31**의 `packages/opencode/src/provider/provider.ts`에서 config hook 이후
  provider 옵션을 읽고 custom `fetch`를 감싸는 경로를 대조했다. 소비 파일은
  `examples/rtl-debugger/{compatible.json,endpoint-plugin.mjs}`다.
- bundled SDK의 `/chat/completions` 조립을 유지하되 지정된 전체 endpoint로 fetch 대상만 변경한다.
  실제 고정 OpenCode Docker + 로컬 API fixture에서 단수형 경로, Bearer, 모델 override,
  SSE와 bash tool 호출/결과 후속 요청을 확인했다. 실제 배포 endpoint의 실행 증거는 아니다.
- Context7 `/docker/docs`의 build args/runtime env와 daemon proxy 설정을 대조했다.
  daemon의 이미지 pull trust와 이미지 내부 설치/runtime CA 전달은 별개다.
- ACE/CVDP/HF SHA와 OpenCode 버전은 변경하지 않았다. 신규 train priority encoder는 고정 HF의
  `cid003`, 명시적 `rtl/priority_encoder.v`, OSS Compose/Icarus 형태를 대조했다.

### 절차

1. 변경 대상의 고정 출처와 로컬 소비 파일을 위 표에서 찾는다. ACE SHA 두 곳은 함께 대조한다.
2. upstream diff에서 경로·CLI·입출력·채점·의존성 변화를 확인한다. 문서 정리를 이유로 자동 최신화하지 않는다.
3. 소스 SHA와 데이터 hash, OpenCode 버전, 이미지 ID/digest, 모델·예산을 기록한다.
   dev의 Docker run은 평가/Agent 이미지 ID를 사용하고 공식 FROM/Compose는 ID 검증된 로컬 tag를 쓴다.
   직접 작성한 profile도 선택 ID에 맞추고 모델 서비스의 가변성을 별도로 기록한다.
4. 모의 계약 테스트 후 지원하는 OSS 한 문제를 실환경 검증한다. 결과와 미검증 영역을
   [verification.md](verification.md), [status.md](status.md)에 갱신한다.
