# 작은 RTL Agent

OpenCode로 공개 RTL을 수정하고, 분리된 evaluator에서 **Yosys 합성 후 private Icarus 검사**를 수행합니다.
평가 도구는 CVDP 공식 OSS 이미지 안의 Yosys·Icarus·vvp를 재사용합니다.

```bash
bash examples/ace-rtl/setup.sh
# 사용하려는 OpenCode 버전을 명시적으로 선택해 기록합니다.
export OPENCODE_VERSION=<설치할-정확한-버전>
docker build --build-arg OPENCODE_VERSION="$OPENCODE_VERSION" -t agent-optimizer-opencode:local -f examples/rtl-debugger/Dockerfile .
export AGENT_OPT_MODEL=provider/model
# 해당 provider 인증도 환경변수로 설정. harness.toml env_passthrough를 함께 확인.
uv run agent-opt run examples/rtl-debugger/experiment.toml
```

OpenCode 프로필은 기본 CLI 에이전트를 사용합니다. 예제 Agent overlay 설정을 수정할 수 있습니다.
실제 통합은 이 ZIP 제작 환경에서 실행하지 않았습니다.

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
입력 정책은 system task/function(`$finish`, `$display`, `$readmemh`, `$clog2` 등),
preprocessor/include, `#` 지연/parameter override, 문자열, escaped identifier, attribute,
`initial`/`final`/`specify`/`force`/`release`/assertion 및 `translate_off/on`을 명시적으로 거부합니다.
일반 `assign`, `always @*`/`always @(*)` 등의 나머지 RTL은 Yosys의 지원 범위와 합성 검사에 따릅니다.
이 정책은 일부 정상 RTL도 제외합니다. 언어 전체의 구문/보안 검증기는 아니며, local 실행은 OS 파일 접근
격리를 제공하지 않습니다. Yosys/Icarus 자체의 취약점이나 모든 RTL 의미 보존을 보장하지 않습니다.

## 회귀 검증

```bash
PYTHONPATH=src:tests python3 -m unittest test_rtl_evaluation test_adapters -v
```

실도구 테스트는 **yosys·iverilog·vvp가 모두 PATH에 있을 때** 실행합니다. 올바른 DUT/오답,
후보의 `TEST_PASS`+`$finish`, 실제 private testbench timeout, 모든 예제 task의 정답/오답을 검사합니다.
추가 characterization 테스트는 직접 Yosys를 실행해 `$display`의 합성 로그와 생성 netlist를 구분하고
`$finish`의 실제 거부 동작을 확인합니다. Mock 계약 테스트만으로 이 도구 동작을 입증하지 않습니다.

Task 4 개발 호스트(macOS arm64)에는 세 도구가 없어 실도구 테스트는 skip입니다.
공식 CVDP 이미지의 도구 버전에서 이 테스트를 실제 실행하는 검증과 전체 환경 구성은 Task 5에 남습니다.
Ubuntu x86_64 및 실제 OpenCode/모델 통합 결과는 아직 없습니다.
