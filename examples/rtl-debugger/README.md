# 작은 RTL Agent

OpenCode로 공개 RTL을 수정하고, 분리된 evaluator에서 **Yosys 합성 후 private Icarus 검사**를 수행합니다.
평가 도구는 CVDP 공식 OSS 이미지 안의 Yosys·Icarus·vvp를 재사용합니다.

```bash
python3 scripts/dev.py setup
# external/environment-lock.json의 선택 이미지 ID를 다음 두 곳에 설정:
# harness.toml: runtime.image (Agent), experiment.toml: evaluation_runtime.image (평가)
export AGENT_OPT_MODEL=openrouter/vendor/model:free
# OPENROUTER_API_KEY도 shell 환경에 설정한 뒤:
.venv/bin/python -m agent_optimizer run examples/rtl-debugger/experiment.toml
```

공유 OpenCode 1.18.31 이미지의 기본 provider 설정은 OpenRouter입니다. `harness.toml`은
`AGENT_OPT_MODEL`, `OPENROUTER_API_KEY`를 컨테이너에 이름으로 전달합니다. 사용 가능한 명시적
`:free` 모델을 선택하세요. 이전 OpenAI/Anthropic/NVIDIA 환경변수만 설정하는 방법은 이 기본 설정과
맞지 않습니다. 프로필은 overlay의 `rtl` primary agent를 사용하며 실제 모델 호출은 아직 미검증입니다.

### 명시적 OpenAI-compatible 대안

일반 endpoint는 별도 공개 template을 선택합니다. 기본 OpenRouter 설정이나 인증 실패의 자동 대체가 아닙니다.
아래 파일에는 실제 인증 값 대신 `{env:...}`만 있으며 Agent 소스 snapshot에 포함할 수 있습니다.

```bash
cp examples/ace-rtl/environment/openai-compatible.json examples/rtl-debugger/agent/provider-compatible.json
export OPENCODE_CONFIG=/work/agent/provider-compatible.json
export MODEL_BASE_URL=https://your-endpoint.example/v1
export MODEL_ID=your-model-id
export AGENT_OPT_MODEL="compatible/$MODEL_ID"
# MODEL_API_KEY는 shell 환경에만 설정
.venv/bin/python -m agent_optimizer run examples/rtl-debugger/experiment.toml
```

같은 profile이 `OPENCODE_CONFIG`, `MODEL_BASE_URL`, `MODEL_ID`, `MODEL_API_KEY`를 전달합니다.
호스트 credential store를 마운트하지 않습니다. 기본 OpenRouter로 돌아가려면 `OPENCODE_CONFIG`를
unset하고 무료 모델/auth 환경을 다시 선택하세요. 설정은 새 컨테이너 실행 시 읽습니다.

## 작은 합성 가능 RTL의 평가 계약

- `evaluation.design_sources`와 `design_top`은 후보 DUT 입력 파일과 top을 명시합니다.
  `sources`는 DUT 파일과 `private_files`의 합집합, `top`은 별도 private testbench top입니다.
  두 파일 집합은 겹칠 수 없으며 누락·중복·경로 이탈·symlink는 거부합니다.
- 후보 출력 옆의 새 `rtl-evaluation-*/design`에 선언된 DUT만 고정 파일명으로 복사합니다.
  Yosys `read_verilog -sv -noautowire`, `synth -top ... -flatten -noabc`, `check -assert`,
  `write_verilog -noattr`로 netlist를 생성합니다. 원래 후보 RTL은 Icarus에 전달하지 않습니다.
- 합성 성공 이후에만 별도 `simulation` 디렉터리에 netlist와 신뢰한 `private_files`를 복사합니다.
  Icarus는 명시한 testbench top을 컴파일하고 vvp로 실행합니다. 각 Docker 실행은 해당 phase
  디렉터리 하나만 마운트합니다. 후보가 제출한 testbench·netlist·실행 파일은 소비하지 않습니다.
- vvp의 정상 종료와 stdout의 **완전한 한 줄** `pass_marker`가 모두 있어야 통과합니다.
  합성/컴파일 로그의 `TEST_PASS`나 문자열 일부 일치는 통과 근거가 아닙니다.
  하나의 wall-time deadline을 파일 준비·합성·컴파일·시뮬레이션이 공유합니다.
- 도구/이미지 실행 불가와 합성 성공 후 netlist 누락은 `infrastructure_error`, `passed=null`입니다.
  잘못된 DUT·지원 밖 구문·합성/검증 실패는 `failed`, 시간 초과는 `timeout`이며 둘 다 0점입니다.
  phase별 stdout/stderr와 생성 netlist는 trial 옆에 보존하고 `Evaluation.artifacts`로 참조합니다.

**범위:** 작은 합성 가능 RTL용 예제이며 임의 Verilog 보안 sandbox가 아닙니다.
입력 정책은 system task/function(`$finish`, `$display`, `$write`, `$readmemh`, `$clog2` 등),
preprocessor/include, `#` 지연/parameter override, 문자열, escaped identifier, attribute,
`initial`/`final`/`specify`/`force`/`release`/assertion 및 `translate_off/on`을 명시적으로 거부합니다.
일반 `assign`, `always @*`/`always @(*)` 등의 나머지 RTL은 Yosys의 지원 범위와 합성 검사에 따릅니다.
이 정책은 일부 정상 RTL도 제외합니다. 언어 전체의 구문/보안 검증기는 아니며, local 실행은 OS 파일 접근
격리를 제공하지 않습니다. Yosys/Icarus 자체의 취약점이나 모든 RTL 의미 보존을 보장하지 않습니다.
**입력 제한은 필수입니다.** 실제 Yosys 0.40은 제한을 우회한 `$display`를 netlist의 `$write`로
보존합니다. 합성만으로 임의 RTL의 시뮬레이션 부작용이 제거되지는 않습니다. 출력 marker가
있어도 private testbench mismatch와 vvp 비정상 종료는 실패입니다.

## 회귀 검증

```bash
PYTHONPATH=src:tests python3 -m unittest test_rtl_evaluation test_adapters -v
```

실도구 테스트는 **yosys·iverilog·vvp가 모두 PATH에 있을 때** 실행합니다. 올바른 DUT/오답,
후보의 `TEST_PASS`+`$finish`, 실제 private testbench timeout, 모든 예제 task의 정답/오답을 검사합니다.
추가 characterization 테스트는 입력 제한을 우회한 netlist가 marker를 출력하더라도
private mismatch/비정상 종료가 유지됨을 확인하고,
`$finish`의 실제 거부 동작을 확인합니다. Mock 계약 테스트만으로 이 도구 동작을 입증하지 않습니다.

Task 4 개발 호스트(macOS arm64)에는 세 도구가 없어 호스트 실도구 테스트는 skip입니다.
Task 5에서 공식 CVDP ARM64 이미지로 실제 도구 테스트 9개 및 host-Docker 정답/오답/조기 종료
검사를 모두 통과했습니다. 정확한 명령과 결과는 [검증 기록](../../docs/verification.md)을 확인하세요.
Ubuntu x86_64 및 실제 OpenCode/모델 통합 결과는 아직 없습니다.
