# 개발환경 온보딩

프로젝트 루트에서 **코어 개발 환경부터** 준비합니다. Mac/Ubuntu와 Git이 필요하고,
uv가 없으면 installer 다운로드용 curl 또는 wget도 필요합니다. Docker·Compose·Buildx와 모델 키는 필요 없습니다.

```bash
make setup ARGS="--core"
make doctor ARGS="--core"
make menu                          # 대화형: 3번 fixture 테스트
make demo                          # 비대화형 최소 데모
# make/Python이 없으면 시작 명령 대신:
sh scripts/bootstrap.sh setup --core
```

`setup --core`는 기존 uv 설치·frozen sync 경로로 `.venv`를 준비한 뒤 코어 doctor와 최소 데모를
실행합니다. uv가 없으면 0.10.7을 `.cache/uv/bin`에 설치하며 신규 Python은 3.12입니다.
기존 호환 venv(Python >=3.11)는 재사용합니다. **준비 중 의존성 다운로드는 발생할 수 있지만,
합성 데모·로컬 HTTP fixture 실행은 외부 모델과 Docker를 사용하지 않습니다.**
ACE/CVDP 소스·데이터·driver·이미지는 준비하지 않습니다. 여러 팀 Agent/Optimizer의 연결 계약은
이 코어 환경에서 개발하며, 실제 대상별 실행·평가 의존성은 별도로 준비합니다.
프록시·CA가 필요하면 먼저 [네트워크 설정](network.md)을 적용하세요.

기본 `make setup`/`make doctor`는 기존 전체 ACE 경로입니다(아래 선택적 준비 참고).
제품 모델 호출은 `make live` 또는 명시적 `make doctor ARGS="--model"`에서 수행합니다.

## 번호 메뉴

```bash
make menu
# make가 없으면:
sh scripts/bootstrap.sh menu
# 코어 준비 후 같은 메뉴의 직접 Python 진입점:
.venv/bin/python scripts/dev.py menu
```

메뉴 시작에는 **Python 3.11+와 입출력 TTY**만 필요합니다. Python이 없으면
`sh scripts/bootstrap.sh setup --core`부터 실행하세요. 메뉴 자체는 시작 시 설치·진단·모델 호출·결과
생성을 하지 않습니다. `make menu ARGS="--help"`는 비대화형 환경에서도 도구 조회 없이 동작합니다.

| 번호 | 동작과 준비 조건 |
|---|---|
| 1. 코어 개발 환경 설치 | `setup --core` 실행. Git·uv/Python·frozen 개발 의존성만 준비하고 코어 doctor·최소 데모를 확인합니다. |
| 2. 코어 환경 진단 | `doctor --core` 실행. 읽기 전용으로 코어 준비 상태와 복구 방법을 표시하며 ACE/모델 준비 여부는 검사하지 않습니다. |
| 3. LLM 없이 데모·최적화 반복 테스트 | 1번으로 준비한 프로젝트 `.venv`에서 실제 최소 합성 데모 후 `test_feedback_optimizer.py` 회귀 테스트를 실행합니다. 로컬 HTTP fixture를 사용하며 외부 LLM·Docker가 필요 없습니다. 실제 모델 최적화나 성능 검증은 아닙니다. |
| 4. 모델 설정·연결 검사 | 정확한 endpoint 또는 표준 base URL을 고르고 모델 ID·숨김 Bearer 토큰을 입력한 뒤 **실제 `doctor --model` 호출**. 모델 서비스와 7번으로 준비한 Docker/예제 환경이 필요합니다. |
| 5. ACE 최적화 실행 | 설정한 모델로 **실제 `live --iterations N` 호출**. 기본 3회, 1..20회만 허용하며 7번 전체 준비와 4번 모델 설정이 필요합니다. |
| 6. 실행 결과·보고서 확인 | 기존 `runs/<run-id>/report.md` 및 ACE `runs/dev-live/<run-id>/report.md`를 번호로 선택해 현재 내용을 표시합니다. setup 없이 사용 가능하며 경로 직접 입력·symlink 보고서는 허용하지 않습니다. |
| 7. ACE 전체 환경 준비 | 기존 전체 `setup` 실행. 아래 Docker·Compose 사전 조건을 확인하고 고정 소스·데이터·driver·이미지를 준비합니다. 모델 API 호출은 하지 않습니다. |
| 0. 종료 | EOF도 종료, Ctrl-C는 130으로 안전하게 종료합니다. |

4번은 기존 `MODEL_*` 환경을 기본값으로 사용합니다. 빈 입력은 해당 기존 값을 유지하고 모델 ID가
없으면 `glm5.3-flash`를 사용합니다. URL 방식 변경 시 사용하지 않는 URL 변수는 제거합니다.
토큰은 표시하지 않으며 숨김 입력이 불가능하면 취소합니다. 입력·검증이 모두 끝난 설정만 메뉴의
자식 환경에 반영하며 shell 환경이나 `.env`·credential 파일에는 저장하지 않습니다. 연결 검사가
실패해도 완료된 세션 설정은 남으므로 4번에서 수정할 수 있습니다. 메뉴 종료 시 설정은 사라집니다.

잘못된 번호는 작업 없이 다시 묻고, 명령 실패는 종료 코드와 함께 표시한 뒤 메뉴로 돌아옵니다.
실패를 성공으로 표시하거나 자동 재시도하지 않습니다. 3번의 데모가 실패하면 회귀 테스트도 시작하지
않습니다. 파이프 입력/출력은 exit 2로 거부하므로 자동화에는 기존 명시적 명령을 사용하세요.

## 1. 선택적 ACE 전체 환경: Mac / Ubuntu 사전 요구사항

| 환경 | 준비 |
|---|---|
| Mac | `xcode-select --install`로 Git/make 개발 도구를 준비합니다. [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/)을 CPU에 맞게 설치하고 실행합니다. 이미 작동하는 Docker/Compose 환경도 사용 가능합니다. |
| Ubuntu | `sudo apt-get update` 후 `sudo apt-get install git make curl`. [공식 Engine 설치](https://docs.docker.com/engine/install/ubuntu/)에 따라 apt 저장소와 Engine·Buildx·Compose plugin을 설치합니다. |
| Ubuntu daemon/권한 | 필요하면 `sudo systemctl start docker`. [Linux 후속 설정](https://docs.docker.com/engine/install/linux-postinstall/)으로 현재 사용자의 socket 접근을 구성한 뒤 다시 로그인합니다. docker 그룹은 root 수준 권한을 부여하므로 해당 문서의 권한 설명을 확인합니다. |

```bash
git --version
docker info
docker compose version
```

Compose가 없으면 Mac은 Docker Desktop을 확인하고, Ubuntu는 Docker apt 저장소의
`docker-compose-plugin`을 설치합니다([설치 안내](https://docs.docker.com/compose/install/linux/)).
make가 없어도 아래 shell 진입점은 동작합니다. uv가 없을 때 installer를 받으려면 curl 또는 wget이
필요합니다. Git·Docker·Compose는 setup이 OS에 자동 설치하지 않습니다.

## 2. 선택적 ACE 전체 준비와 첫 결과

```bash
make help
make setup
# make/Python이 없으면 대신:
sh scripts/bootstrap.sh setup
make doctor
make doctor ARGS="--json"
# MODEL_ENDPOINT(또는 MODEL_BASE_URL), MODEL_API_KEY, 선택적 MODEL_ID 설정 후:
make doctor ARGS="--model"  # 실제 호스트 API와 컨테이너 도구 호출
make live ARGS="--iterations 3"
make demo
```

새 환경에서는 uv 0.10.7을 `.cache/uv/bin`에 설치하고 Python 3.12 및 frozen 개발 의존성을
`.venv`에 준비합니다. 기존 uv와 호환되는 프로젝트 venv(Python >=3.11)는 재사용하며
사용자 shell 설정을 수정하지 않습니다. CVDP driver는 별도의 `external/cvdp-venv` Python 3.12입니다.
setup은 고정 소스·데이터, 공식 평가 이미지와 OpenCode 이미지를 준비한 뒤 doctor와 최소 데모를 실행합니다.

첫 빌드는 네트워크·CPU·Docker cache에 따라 수십 분 걸릴 수 있습니다. 단계 시작/완료와
로그 경로가 출력되며 긴 컴파일 중에는 터미널 출력이 잠시 없을 수 있습니다.
`external/setup-logs/{project-uv,driver-uv,evaluation-build,agent-build}.log`를 확인하세요.
uv 신규 설치 로그는 `bootstrap-uv.log`입니다. 실패하면 해당 단계와 복구 안내를 확인하고 같은
setup을 재실행합니다. 기존 checkout/venv를 강제로 초기화하지 않습니다.

완료 시 표시한 `runs/<run-id>/report.md`, `summary.json`, `events.jsonl`이 첫 결과입니다.
최소 데모는 두 합성 Agent·7 trial(solo 4/team 3)의 연결 검사입니다. 실제 RTL/모델 성능 개선 근거는 아닙니다.
환경 기록은 `external/environment-lock.json`, 생성 데이터는 `datasets/ace-demo/`에 있습니다.
이들 로그·자산은 Git 제외이며 다른 checkout의 writable venv/외부 소스를 공유하지 마세요.

## 3. 일상 개발과 offline 재사용

```bash
make lint
make test
make demo
. .venv/bin/activate
agent-opt --help
deactivate
make setup ARGS="--core --offline"
```

lint/test/demo는 `.venv`에서 실행하며 Docker나 API가 필요하지 않습니다. 설치가 부족하면 실패하고
`setup --core`를 안내합니다. 이미 설치한 uv의 `uv sync --frozen --python 3.12 --extra dev`도 사용할 수 있습니다.
`setup`은 부모 shell을 활성화하지 않으므로 직접 명령은 `.venv/bin/python`을 사용하거나 위처럼 명시적으로 활성화하세요.
직접 uv를 호출할 때 bootstrap 로컬 설치가 PATH에 없으면
`export PATH="$PWD/.cache/uv/bin:$PATH"`를 사용합니다. Make/shell 진입점은 이 경로를 자동 연결합니다.

`setup --core --offline`은 준비된 uv·Python·패키지 cache만 재사용하며 다운로드하지 않습니다.
누락분은 online `setup --core`로 먼저 준비합니다. 코어 진단과 데모는 여전히 수행합니다.
전체 `make setup ARGS="--offline"`도 다운로드·이미지 빌드를 하지 않습니다. 전체 모드는 준비된
Python/패키지 cache·고정 소스·데이터·이미지가 모두 필요하며, 누락분은 online 전체 setup으로 먼저 준비합니다.
전체 offline도 로컬 의존성 동기화,
데이터 생성·진단·최소 데모는 수행하므로 읽기 전용 명령은 아닙니다.

전체 ACE 경로의 플랫폼 기본값은 Docker daemon native `linux/amd64` 또는 `linux/arm64`입니다.
명시적 선택은 `make setup ARGS="--platform linux/arm64"`처럼 전달하고 doctor/smoke에도 같은 값을
사용합니다. 실패 뒤 다른 플랫폼으로 자동 대체하지 않습니다. smoke 결과와 phase 로그는
`runs/dev-smoke-*/summary.json` 아래에서 확인합니다. 호스트 simulator 미설치로 test가 skip해도
smoke는 공식 이미지에서 실제 도구 및 host-Docker·공식 CVDP 정답/오답을 검증합니다.

## 4. Doctor 문제 해결

`make doctor ARGS="--core"`는 network/core collector만 실행하며 Docker·ACE loader·모델을
조회하지 않는 읽기 전용 진단입니다. `make doctor ARGS="--core --json"`은 `scope="core"`,
`areas={"core": ...}`만 포함하며 `ready`와 종료 코드는 코어 준비 상태만 뜻합니다.
ACE 평가/모델 준비 완료로 해석하지 마세요. `--core`는 setup/doctor 전용이며
`--platform`, `doctor --model`과 함께 지정하면 실행 전에 거부합니다.

기본 doctor는 설치·다운로드·모델 호출 없이 독립 검사를 계속합니다. 이미지가 준비되면 network=none의
임시 컨테이너로 도구를 실행하고 정리합니다. `error`는 해당 검사 실패, `blocked`는 표시된 선행
검사 문제로 실행하지 못했다는 뜻입니다. core/evaluation 준비 여부가 종료 코드를 정하며,
live 설정 부재만으로는 setup/doctor가 실패하지 않습니다. 성공은 smoke/inference 성공과 다릅니다.

| 실제 진단 ID / 오류 | 복구 |
|---|---|
| `network.configuration` | `AGENT_OPT_CA_BUNDLE`을 수정하거나 unset. 개인키 없는 유효한 전체 PEM trust bundle을 사용하세요. 잘못된 CA도 나머지 로컬 진단을 중단하지 않습니다. |
| `core.git`, `source.git` | Git 설치 및 `git --version` 확인. |
| `core.uv`, `driver.uv` | 코어는 `sh scripts/bootstrap.sh setup --core`, ACE driver는 전체 setup. 직접 uv 호출은 위 PATH 안내 확인. |
| `core.python`, `core.venv`, `core.package`, `core.cli`, `core.ruff`, `core.build` | `setup --core` 재실행. 호환되지 않는 기존 `.venv`는 내용을 보존해 명시적으로 옮긴 뒤 재실행. |
| `docker.cli`, `docker.daemon`, `docker.compose` | 위 OS별 설치·daemon·socket 권한 복구 후 `docker info`, `docker compose version` 재확인. |
| `docker.platform`, `environment.platform` | 준비된 플랫폼과 동일한 `--platform` 사용 또는 의도한 플랫폼으로 setup. |
| `environment.lock` | 누락이면 setup. 손상된 lock은 내용을 보존해 명시적으로 옮긴 뒤 setup으로 재생성; 자동 덮어쓰지 않음. |
| `source.ACE-RTL`, `source.cvdp_benchmark` | 로컬 변경을 보존하고 고정 revision의 clean checkout을 준비한 뒤 setup. 강제 reset하지 않음. |
| `data.cvdp_v1.1.0_nonagentic_code_generation_no_commercial.jsonl`, `data.LICENSE`, `data.NOTICE` | online setup으로 검증된 자산 확보. hash 실패 시 원인 확인; pin을 바꿔 통과시키지 않음. |
| `driver.python` | 기존 `external/cvdp-venv`가 잘못되면 보존해 옮긴 뒤 setup으로 Python 3.12 준비. |
| `driver.lock`, `driver.packages`, `driver.imports` | 고정 requirements와 설치 상태 확인 후 online setup. 소스·lock drift는 검토 없이 pin 갱신하지 않음. |
| `image.evaluation`, `image.agent`, `tools.evaluation`, `tools.opencode` | setup으로 이미지 identity/platform·실도구 복구; `external/setup-logs/` 확인. |
| `setup offline: uv missing` / offline sync 실패 | online setup으로 uv/Python/패키지 cache를 준비한 뒤 offline 재실행. |
| `live.key`, `live.model` | `MODEL_API_KEY`, `MODEL_ENDPOINT` 또는 `MODEL_BASE_URL`, 선택적 `MODEL_ID`(기본 `glm5.3-flash`) 설정. |
| `environment.ca` | 준비 시점과 CA가 다름. 명시한 전체 bundle 또는 Ubuntu 시스템 CA를 확인하고 online setup 재실행. |
| `live.execution` | `doctor --model`의 실제 모델/도구 호출 실패. endpoint/auth·proxy/NO_PROXY·CA와 `runs/doctor-model-*/logs` 확인. |

Python >=3.11 자체가 없으면 doctor 대신 `sh scripts/bootstrap.sh setup --core`부터 실행하세요.
JSON은 `make doctor ARGS="--json"` 또는 `sh scripts/bootstrap.sh doctor --json`의 stdout에 단일 문서로
출력됩니다. 키 값은 문서·설정 파일·로그에 넣지 않습니다. 기본 live 설정 검사는 인증 성공이나 모델의
현재 가용성을 검증하지 않습니다. `doctor --model`은 실제 API·컨테이너 도구 호출을 추가하고,
실패하면 종료 코드 2를 반환합니다. 다른 모델로 자동 대체하지 않습니다.

실제 실행 근거와 미검증 플랫폼은 [verification.md](verification.md), 설치 문서 출처는
[SOURCES.md](SOURCES.md#개발환경-온보딩-설치-출처-2026-09-21)를 따릅니다.
