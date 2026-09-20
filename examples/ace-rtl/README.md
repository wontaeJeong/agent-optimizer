# ACE-RTL 데모 연결

**기본 데모 대상은 외부 NVlabs/ACE-RTL입니다.** 원본 소스를 이 repo에 vendoring하지 않습니다.
source.toml이 고정 commit을 지정하고 실행 시 후보 스냅샷을 만듭니다.
setup은 별도로 `external/ACE-RTL`에 원본을 확보해 확인할 수 있게 합니다. 두 경로 모두 Git 제외입니다.

## 실행 프로필의 의미

현재 연결은 **OpenCode에서 ACE-RTL 스킬을 읽고 공개 RTL 과제를 수행하는 프로필**입니다.
ACE의 native runner / 자체 반복 루프 / 역할별 모델 호출과 동일하지 않습니다.
원본 전체 러너를 평가하려면 [upstream 실행 안내](https://github.com/NVlabs/ACE-RTL/blob/fead921f18bb57345b5a41ef93ba625be208e99c/README.md)를 따르고 별도 Harness 프로필을 연결하세요.
이 예제의 adapter.py에서 원본 스킬의 데이터셋 다운로드/자체 평가 지시를 외부 평가 방식에 맞게 제한합니다.
이는 v0.3.0의 초기 구현 선택이며 사용자가 원본 runner 대체를 확정한 것은 아닙니다.
역할 Python 파일의 실행 여부, 주장 가능한 최적화 범위, native baseline 연결 조건은
[상태 문서](../../docs/status.md#ace-rtl-실행-프로필), 고정 출처는 [SOURCES.md](../../docs/SOURCES.md)를 확인하세요.

## 준비

Linux, Python 3.11+(CVDP는 upstream Python 3.12 권장), Git, Docker Engine/Compose가 필요합니다.
프로젝트 루트에서 실행합니다.

```bash
uv sync --frozen
bash examples/ace-rtl/setup.sh
export OPENCODE_VERSION=<사용할-정확한-버전>
docker build --build-arg OPENCODE_VERSION="$OPENCODE_VERSION" -t agent-optimizer-opencode:local -f examples/rtl-debugger/Dockerfile .
bash examples/ace-rtl/environment/doctor.sh
export AGENT_OPT_MODEL=provider/model
# provider 인증 환경변수도 설정한 뒤:
uv run agent-opt plan examples/ace-rtl/experiment.toml
uv run agent-opt run examples/ace-rtl/experiment.toml
```

setup은 고정 버전 CVDP를 내려받고 별도 Python venv에 의존성을 설치하며 공식 Dockerfile.sim을 빌드합니다.
Icarus, Verilator, Yosys를 호스트에 각각 설치할 필요가 없습니다. OpenCode 컨테이너는 평가용 이미지와 별개입니다.
상용 EDA 이미지·라이선스는 제공하지 않습니다. setup 재실행 시 변경된 기존 checkout은 덮어쓰지 않습니다.
모델 API 호출 비용은 환경 설치와 별개입니다.

## 평가

기본 데이터는 upstream의 비상용 공개 예제 한 문제입니다. `prepare.py`가 input/context와 출력 대상
경로만 공개 과제로 만들고, private harness는 evaluation에만 보관합니다. reference output은 지웁니다.
Agent 컨테이너에는 과제와 ACE 후보 소스만 마운트합니다.
`evaluator.py`는 산출 RTL을 official row의 output.context에 넣고 공식 `run_benchmark.py`로 재평가합니다.
여기서 upstream golden 모드는 **제출한 후보 RTL 평가**에 사용되며 정답을 Agent에 제공하지 않습니다.

실제 test 결과가 있는 raw_result.json만 파싱합니다. 알려진 환경 실패는 `passed=null`로 반환하며,
코어는 해당 후보·split 집계 전체를 무효화합니다. 정상 trial만으로 성공률을 재계산하는 방식이 아닙니다.
초기 범위는 cid003 기능 검증/rtl 출력입니다. coverage/PPA/agentic-heavy 등은 지원하지 않고 제외합니다.
상용 도구 문자열·비공식 base image가 발견되어도 제외 보고서에 기록합니다. 범위를 넓힐 때는
공식 harness 의존성과 채점 의미를 검토하고 importer/evaluator 테스트를 갱신하세요.

## 최적화

experiment.toml은 원본과 짧은 role-guidance 후보를 비교합니다. 알고리즘은 실제 연구 optimizer가 아닌
file_variants입니다. 팀원이 GEPA 등 구현을 연결하면 같은 source/evaluator를 사용합니다.
이 한 문제는 validation-only smoke이므로 일반화 성능 근거가 아닙니다. 본 실험은 서로 다른 family의
train/validation/test 과제를 준비하고 호출·시간 예산 및 모델을 맞추세요.

기본 timeout은 OpenCode + CVDP 평가 합산입니다. 첫 Docker 빌드는 setup에서 완료해야 합니다.
토큰 전체 합산은 미지원이며 partial 지표만 관측됩니다. API 응답/trace에는 민감정보가 있을 수 있으므로
runs를 Git에 추가하지 마세요.

## 현재 검증 범위

과제 공개/비공개 분리와 공식 결과 형식 처리는 오프라인 테스트합니다.
실제 OpenCode·Docker·LLM 연결은 제작 환경에서 실행하지 못했습니다.
source/evaluator 버전이 바뀌면 한 문제로 입출력과 보고서 형식을 먼저 검증하세요.

외부 CVDP 프로세스가 timeout/강제 중단되면 Docker daemon의 평가 컨테이너 정리가 필요할 수 있습니다.
해당 trial의 생성된 Compose 작업 공간을 확인해 정리하세요. 자동 resume은 지원하지 않습니다.
