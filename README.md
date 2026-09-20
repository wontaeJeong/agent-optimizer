# Agent Optimizer — 팀 개발·데모 스타터

범용 Agent 최적화 실험용 Python CLI입니다. **ACE-RTL은 데모 대상이며 제품 코어가 아닙니다.**
다른 팀 Agent의 repo·실행 방식·평가 방법·수정 허용 범위를 연결해 같은 실험 흐름을 사용합니다.
실제 Agent는 별도 repo, 작은 개발용 Agent는 `examples/`에 포함합니다.
대상에 따라 실행·평가 어댑터 개발이 필요하며, 모든 Agent를 설정만으로 자동 지원하지는 않습니다.

## 후속 개발자 읽기 순서

1. [배경·확정 요구사항·설계 결정](docs/CONTEXT.md)
2. [구조와 실행 흐름](docs/architecture.md) → [공통 계약·확장 방법](docs/adding-components.md)
3. [외부 출처·고정 버전](docs/SOURCES.md) → [현재 구현 상태](docs/status.md) → [검증 기록](docs/verification.md)
4. [다음 작업과 완료 기준](docs/NEXT_STEPS.md), [개발 규칙](AGENTS.md), [팀 담당 영역](CONTRIBUTING.md)

도메인 코드는 `examples/`에 두고, 슬롯·미검증 통합을 완료로 표현하지 않습니다.
외부 기술 판단은 고정 출처와 실제 설정을 대조하며 문서 정리를 이유로 upstream 버전을 자동 갱신하지 않습니다.

## 3분 시작: API·Docker 없는 최소 데모

Python 3.11+ / Linux 기준, 프로젝트 루트에서 실행합니다.

프록시·추가 CA가 필요한 환경은 먼저 [선택적 네트워크 설정](docs/network.md)을 적용하세요.
설정하지 않으면 기존 직접 연결 방식을 사용합니다.

```bash
uv sync --frozen
uv run agent-opt run examples/minimal/experiment.toml
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
  optimizers/             알고리즘 담당자 작업 영역
  harnesses/              command / OpenCode
examples/
  minimal/                즉시 실행하는 합성 데모, 두 Agent
  rtl-debugger/           작은 RTL Agent + OpenCode + Yosys/Icarus 평가
  ace-rtl/                외부 ACE-RTL + OpenCode 스킬 + 공식 CVDP 평가
experiments/              다른 팀 Agent 연결 템플릿
scripts/                  setup / doctor / smoke / live 및 최소 데모 명령
docs/                     설계·확장·구현 상태
tests/                    의미 있는 경계·실험 검증
external/ datasets/ runs/ 다운로드·데이터·결과, Git 제외
```

## 구현 범위

- 실행 가능: 외부 Git 고정 커밋/로컬 소스 스냅샷, 복수 Agent × Harness 실험, baseline,
  파일 변경 후보 비교, 단계 조합·분기 조건, 동적 지표/제약, validation 선택 후 test 평가.
- OpenCode 및 Docker 실행 어댑터와 예제 전용 Icarus/CVDP 연결 코드를 포함합니다.
- **GEPA / Meta-Harness / Ecdysis는 팀원 구현용 슬롯**입니다. 실제 알고리즘은 포함하지 않았습니다.
  미구현 알고리즘을 실행하면 명시적으로 실패합니다.
- Claude Code / Codex / OpenAgent는 확장 규약만 제공합니다. 별도 구현 완료로 표시하지 않습니다.
- Mac Docker ARM64와 native Ubuntu x86_64에서 공식 CVDP 정답·오답과 host-Docker toy 평가를 실행했습니다.
  실제 도구 테스트 9개와 전체 smoke가 통과했습니다. 입력 제한은 필수이며 합성만으로 임의 RTL을
  정화하지 않습니다. 실제 모델 실행은 인증 부재로 미검증입니다. [검증 기록](docs/verification.md)

## 실제 데모

[ACE-RTL 예제](examples/ace-rtl/README.md)의 순서로 공식 CVDP 오픈소스 이미지를 준비하고,
OpenCode 실행 이미지를 별도로 만듭니다.

```bash
python3 scripts/dev.py setup   # uv Python 3.12, 고정 소스/데이터, 별도 Docker 이미지
python3 scripts/dev.py smoke   # 키 없이 실제 RTL/CVDP 정답·오답 검증
python3 scripts/dev.py live    # OPENROUTER_API_KEY + 명시적 openrouter/vendor/model:free 필요
```

`--platform`을 생략하면 빌드 전에 Docker daemon의 native `linux/amd64` 또는 `linux/arm64`를
선택해 기록합니다. 명시적 `--platform`은 그대로 사용하며 미지원 architecture는 오류입니다.
빌드 실패 후 다른 architecture로 자동 재시도하지 않습니다. `setup --offline`은 검증된 cache만 재사용합니다.
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
알고리즘 담당자는 [Optimizer 템플릿](experiments/optimizer-template/README.md)과
`tests/test_plugin_contracts.py`의 train/validation/test 계약부터 확인하세요.

## 결과와 제한

미수집 토큰/비용은 `null`입니다. OpenCode root 이벤트에서 관측된 사용량은 별도 partial 지표이며
sub-agent까지 합산된 Agent 전체 사용량으로 표시하지 않습니다.
실험 trial 수·벽시계·trial timeout을 제한합니다. 엄격한 API 비용 상한/호출 수 제한, 재시작 resume,
병렬 스케줄링은 아직 없습니다. 비용 상한은 사용하는 provider/proxy에서도 설정하세요.

코어 플러그인은 신뢰한 팀 코드로 실행합니다. local 모드는 OS 격리가 없으며 개발용입니다.
Docker Agent는 해당 trial workspace만 마운트하고 Docker socket을 전달받지 않습니다.
평가 데이터는 Agent workspace와 분리합니다. 공식 Docker 평가기는 호스트가 실행합니다.
