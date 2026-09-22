# Agent Optimizer — 팀 개발·데모 스타터

범용 Agent 최적화 실험용 Python CLI입니다. **ACE-RTL은 데모 대상이며 제품 코어가 아닙니다.**
다른 팀 Agent의 repo·실행 방식·평가 방법·수정 허용 범위를 연결해 같은 실험 흐름을 사용합니다.
실제 Agent는 별도 repo, 작은 개발용 Agent는 `examples/`에 포함합니다.
대상에 따라 실행·평가 어댑터 개발이 필요하며, 모든 Agent를 설정만으로 자동 지원하지는 않습니다.

## 개발환경 빠른 시작

Mac/Ubuntu와 **Git**부터 준비하고 프로젝트 루트에서 실행하세요. 코어 개발에는 Docker·Compose·Buildx나
모델 키가 필요 없습니다. uv가 없으면 installer 다운로드용 curl 또는 wget이 필요합니다.
프록시·추가 CA가 필요한 환경은 먼저 [네트워크 설정](docs/network.md)을 적용하세요.

```bash
make setup ARGS="--core"          # frozen 개발 도구 + 코어 진단 + 첫 최소 데모
make doctor ARGS="--core"         # 코어만 읽기 전용 진단
make menu                        # 1/2번: 코어 설치/진단, 3번: fixture 테스트
make demo                        # 비대화형 최소 데모
# make/Python이 없으면 시작 명령 대신:
sh scripts/bootstrap.sh setup --core
```

`setup --core`는 기존 uv 설치 경로를 사용해, uv가 없으면 0.10.7을 로컬에 설치하고
Python 3.12·frozen 개발 의존성을 `.venv`에 준비합니다. **최초 준비에는 의존성 다운로드가 필요할 수 있지만,
최소 데모와 로컬 HTTP fixture 실행은 외부 모델·Docker를 사용하지 않습니다.**
코어 준비는 ACE/CVDP 소스·데이터·이미지를 준비하지 않으며 모델/평가 환경의 준비 완료를 뜻하지 않습니다.
설치 로그는 `external/setup-logs/`에 보존합니다. 완료 시 출력된
`runs/<run-id>/report.md`, `summary.json`을 확인하세요. 최소 데모는 두 합성 Agent·한 repair stage·7 trial(solo 4/team 3)의
연결 검증이며 실제 모델 성능 수치가 아닙니다. API 키는 **live 및 명시적 모델 연결 검사**에 필요합니다.

메뉴는 Python 3.11+와 TTY가 필요하며 모델 토큰은 숨김 입력, 설정은 세션에만 유지됩니다.
**7번은 선택적 ACE 전체 환경 준비**이며 4/5번의 실제 모델·평가 실행 전에 사용합니다.
[메뉴·OS별 설치 안내](docs/development.md#번호-메뉴)

| 명령 | 용도 |
|---|---|
| `make` / `make help` | 설치·Docker 조회 없는 도움말 |
| `make setup ARGS="--core"` | 코어 준비·진단·합성 데모 |
| `make doctor ARGS="--core"` / `make doctor ARGS="--core --json"` | 코어만 읽기 전용 진단 / `scope=core` 단일 JSON |
| `make setup ARGS="--core --offline"` | 준비한 uv/Python/패키지 cache만 재사용 |
| `make setup` / `make doctor` | 선택적 ACE 전체 준비 / 전체 진단 (`--json` 지원) |
| `make lint` / `make test` / `make demo` | `.venv`에서 일상 개발 검사·데모 |
| `make setup ARGS="--offline"` | ACE 전체 자산·캐시 검증 및 재사용 |
| `make smoke` | 모델 호출 없는 실제 RTL/CVDP 정답·오답 검사 |
| `make live` | 설정한 OpenAI 호환 모델로 ACE 지침 최적화 반복 |

make가 없으면 모든 명령을 `sh scripts/bootstrap.sh <명령> [옵션]`으로 실행합니다.
가상환경 활성화·PATH·offline 복구는 [개발환경 가이드](docs/development.md), 일상 작업과
담당 영역은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

## 담당별 시작

위 빠른 시작 → [Optimizer / Harness / 외부 Agent 템플릿](experiments/README.md) →
[관련 공통 계약](docs/adding-components.md) 순서로 시작하세요. 팀 코드는 `experiments/<team>/`에 둡니다.
외부 연동 변경 시 [SOURCES](docs/SOURCES.md)를 대조하며 [날짜별 검증](docs/verification.md)은 과거 증거입니다.
현재 상태·후속 순서는 [status](docs/status.md) / [NEXT_STEPS](docs/NEXT_STEPS.md), 개발 규칙은 [AGENTS](AGENTS.md)입니다.

도메인 코드는 `examples/`에 두고, 슬롯·미검증 통합을 완료로 표현하지 않습니다.
외부 기술 판단은 고정 출처와 실제 설정을 대조하며 문서 정리를 이유로 upstream 버전을 자동 갱신하지 않습니다.

## 코어만 실행: API·Docker 없는 최소 데모

Python 3.11+ / Linux 기준, 프로젝트 루트에서 실행합니다.

프록시·추가 CA가 필요한 환경은 먼저 [선택적 네트워크 설정](docs/network.md)을 적용하세요.
설정하지 않으면 기존 직접 연결 방식을 사용합니다.

```bash
make setup ARGS="--core"
make doctor ARGS="--core"
make demo
```

uv 없이도 코어와 최소 데모는 실행 가능합니다.

```bash
PYTHONPATH=src python3 -m agent_optimizer run examples/minimal/experiment.toml
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

`runs/<run-id>/report.md`, `summary.json`, `events.jsonl`을 확인하세요.
최소 데모는 두 개의 독립적인 합성 Agent를 실행합니다. 첫 Agent는 설정 변경 후 검증 점수가
0 → 1로 바뀝니다. 이는 연결 검증을 위한 **의도적으로 만든 결과**이며 RTL/LLM 성능 개선 증거가 아닙니다.

## 폴더

```text
src/agent_optimizer/       공통 계약·실험 실행·소스 스냅샷·결과
  optimizers/             내장 baseline / file_variants
  harnesses/              command / OpenCode
examples/
  minimal/                즉시 실행하는 합성 데모, 두 Agent
  rtl-debugger/           작은 RTL Agent + OpenCode + Yosys/Icarus 평가
  ace-rtl/                외부 ACE-RTL + OpenCode 스킬 + 공식 CVDP 평가
experiments/              팀별 Optimizer / Harness / 외부 Agent 파일 플러그인
scripts/                  setup / doctor / smoke / live 및 최소 데모 명령
docs/                     설계·확장·구현 상태
tests/                    의미 있는 경계·실험 검증
external/ datasets/ runs/ 다운로드·데이터·결과, Git 제외
```

## 구현 범위

- 실행 가능: 외부 Git 고정 커밋/로컬 소스 스냅샷, 복수 Agent × Harness 실험, baseline,
  여러 독립 파일 Optimizer 비교, 단순 LLM 피드백 반복, validation 선택 후 test 평가.
- 모든 stage는 baseline에서 시작하며 train 이력은 baseline과 자기 stage만 포함합니다.
  기본 최종 비교는 모든 stage winner, 선택은 lexicographic keep=1·mean/sum입니다.
- OpenCode 및 Docker 실행 어댑터와 예제 전용 Icarus/CVDP 연결 코드를 포함합니다.
- 연구 알고리즘은 팀 파일 플러그인으로 구현합니다. 미구현 템플릿은 명시적으로 실패합니다.
  고급 조합/선택과 연구 슬롯의 보류·복원 위치는 [FUTURE](docs/FUTURE.md)에 있습니다.
- Claude Code / Codex / OpenAgent는 확장 규약만 제공합니다. 별도 구현 완료로 표시하지 않습니다.
- Mac Docker ARM64와 native Ubuntu x86_64에서 공식 CVDP 정답·오답과 host-Docker toy 평가를 실행했습니다.
  실제 도구 테스트 9개와 전체 smoke가 통과했습니다. 입력 제한은 필수이며 합성만으로 임의 RTL을
  정화하지 않습니다. 실제 모델 실행은 인증 부재로 미검증입니다. [검증 기록](docs/verification.md)

## 선택적 ACE 전체 준비와 실제 데모

[ACE-RTL 예제](examples/ace-rtl/README.md)는 기본 3회 **train 평가 → ACE 지침 수정 → 재평가** 후
별도 validation으로 후보를 선택합니다. 기본 모델은 `glm5.3-flash`이며 설정으로 교체합니다.
Python 3.11+, uv, Git, Docker Engine/Compose가 필요합니다. Ubuntu 시스템 CA 사용 시 Buildx도 필요합니다.
호스트에 OpenCode·시뮬레이터를 별도로 설치하지 않습니다.
기본 `setup`/`doctor`는 기존 전체 경로입니다. 첫 이미지 컴파일은 수십 분 걸릴 수 있습니다.
`--core`는 setup/doctor에서만 지원하며 `--platform` 또는 `doctor --model`과 함께 사용할 수 없습니다.

```bash
# 실제 주소·토큰은 셸/credential store에서 설정; .env.example은 자동 로딩하지 않음
export MODEL_ENDPOINT=https://model.example/v1/chat/completion
export MODEL_ID=glm5.3-flash
# MODEL_API_KEY도 export. 표준 API는 MODEL_ENDPOINT 대신 MODEL_BASE_URL 사용.
make setup                         # Python 환경·소스·데이터·두 이미지 일괄 준비
make doctor                        # 준비 상태와 실패 조치; 모델 호출 없음
make doctor ARGS="--model"          # 실제 호스트 API + 컨테이너 OpenCode 도구 호출
make smoke                         # 모델 키 없이 실제 RTL/CVDP 정답·오답 검증
make live ARGS="--iterations 3"     # 기본 8 trial: 후보 4개 × train/validation
```

Ubuntu에서는 기존 proxy 환경과 `/etc/ssl/certs/ca-certificates.crt`를 사용합니다.
명시적 `AGENT_OPT_CA_BUNDLE`이 우선합니다. [proxy/CA 안내](docs/network.md)를 확인하세요.
`doctor --json`은 자동화용 결과와 실패 종료 코드 2를 제공합니다. 코어 `agent-opt doctor`는
단순 바이너리 목록이며, **ACE 데모 준비 검사는 위 `scripts/dev.py doctor`**를 사용합니다.
uv/Python이 없으면 `sh scripts/bootstrap.sh setup`이 프로젝트 전용 환경을 준비합니다.

`--platform`을 생략하면 빌드 전에 Docker daemon의 native `linux/amd64` 또는 `linux/arm64`를
선택해 기록합니다. 명시적 `--platform`은 그대로 사용하며 미지원 architecture는 오류입니다.
빌드 실패 후 다른 architecture로 자동 재시도하지 않습니다. 예: `make setup ARGS="--platform linux/arm64"`.
`make setup ARGS="--offline"`은 검증된 cache만 재사용합니다.
Python 3.12 CVDP driver는 예제의 [전이 의존성 lock](examples/ace-rtl/environment/requirements-cvdp-py312.txt)으로
동기화하며 lock hash와 실제 설치 목록을 기록합니다. 이전 환경은 한 번 online setup으로 갱신하세요.
상용 EDA 도구·라이선스 설정은 제공하지 않습니다. 플랫폼별 검증/차단 결과는 [검증 기록](docs/verification.md)을 따릅니다.

PR CI는 Python 3.11/3.12와 Ubuntu native Yosys/Icarus로 코어·실제 RTL·패키징을 검사합니다.
공식 Docker 통합은 기존 `ci.yml`의 수동 `official_cvdp` 입력으로 실행합니다. 두 경로 모두 모델 호출은 없습니다.
`10baa46`의 Ubuntu 코어 CI와 공식 setup/offline/smoke·provider config 검사가 통과했습니다.
첫 공식 smoke의 FROM 참조 실패와 수정 후 native 정답·오답 근거는
[최종 재검증 기록](docs/verification.md#2026-09-20-native-ubuntu-repeat--passed)에 보존합니다.
브랜치 실행 명령과 준비 조건은 [CONTRIBUTING.md](CONTRIBUTING.md#ci와-pr-병합)를 참고하세요.

## 다른 팀에 적용

1. `experiments/customer-template/` 복사.
2. Agent 소스 repo/고정 커밋과 editable 범위 설정.
3. Harness 명령 또는 어댑터, 평가 함수 연결.
4. 작은 baseline을 확인한 후 담당 Optimizer 연결.
5. 동일 데이터·모델·예산으로 비교하고 diff와 지표 공유.

[확장 가이드](docs/adding-components.md) · [구조](docs/architecture.md) · [팀 개발](CONTRIBUTING.md)
알고리즘 담당자는 [API-free 회귀·최소 구현](experiments/optimizer-template/README.md)부터 확인하세요.
[단순 LLM Optimizer](experiments/simple-feedback/README.md)는 모델 준비 후 선택적으로 연결합니다.
새 CLI 연결은 [Harness 템플릿](experiments/harness-template/README.md)을 사용합니다.

## 결과와 제한

미수집 토큰/비용은 `null`입니다. OpenCode root 이벤트에서 관측된 사용량은 별도 partial 지표이며
sub-agent까지 합산된 Agent 전체 사용량으로 표시하지 않습니다.
실험 trial 수·벽시계·trial timeout을 제한합니다. 엄격한 API 비용 상한/호출 수 제한, 재시작 resume,
병렬 스케줄링은 아직 없습니다. 비용 상한은 사용하는 provider/proxy에서도 설정하세요.

코어 플러그인은 신뢰한 팀 코드로 실행합니다. local 모드는 OS 격리가 없으며 개발용입니다.
Docker Agent는 해당 trial workspace만 마운트하고 Docker socket을 전달받지 않습니다.
평가 데이터는 Agent workspace와 분리합니다. 공식 Docker 평가기는 호스트가 실행합니다.
