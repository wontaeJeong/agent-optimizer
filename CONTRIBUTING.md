# 팀 개발

**코어 준비 → fixture → 팀 플러그인 하나** 순서로 시작합니다. 프로젝트 루트에서:

```bash
make setup-core
make doctor-core
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_plugin_contracts.py -v
make demo
```

make/Python이 없으면 `sh scripts/bootstrap.sh setup --core`를 사용합니다.
설치·활성화·offline 복구는 [개발환경](docs/development.md), 역할 선택은 [팀 템플릿](experiments/README.md).
일반 팀 Dataset/Harness/Optimizer/Evaluator 구현은 `experiments/<team>/`에 두고
`src/agent_optimizer/registry.py`의 `PROJECT_COMPONENTS`에 ID→파일 경로를 등록합니다.
helper는 `PROJECT_DEPENDENCIES`에 선언하며 CLI 메뉴/설치 entry point는 수정하지 않습니다.
Optimizer는 propose/evaluate, Harness는 RunRequest/ExecutionResult, 외부 Agent는 소스·실행·평가를 맡습니다.
공통 계약 변경은 팀과 합의하고 관련 예제를 함께 갱신하세요. 도메인 코드는 examples에 둡니다.

## 변경 범위별 로컬 검증

| 변경 | 필요한 검사 |
|---|---|
| 개발 명령·CLI UX | `test_dev_onboarding.py`·`test_cli_experience.py` → `make lint`, `make test`, `make demo`; 합성/명령 전달 성공은 ACE 실행 성공과 구분 |
| 팀 플러그인·코어 | 관련 계약 회귀 → `.venv/bin/agent-opt datasets list` / `doctor --dataset ID` / `doctor --plan PATH` / 작은 fixture 실행 → `make lint`, `make test`, `make demo`, `git diff --check` |
| 패키징·의존성·릴리즈 | 위 검사 + `.venv/bin/python -m build`; `python tests/test_installed_cli.py dist/agent_optimizer-0.3.0-py3-none-any.whl`로 저장소 밖 wheel의 목록·TUI·사용자 Agent/채점기 init/doctor/run/report 확인 |
| ACE·Docker·환경 연결 | 관련 회귀 + `make setup` → `make doctor` → `sh scripts/bootstrap.sh setup --offline` → `make smoke`; 수동 공식 CI는 모델 없이 평가 경로와 ACE CLI의 인증 실패를 검사. 실제 모델은 자격증명 준비 후 `sh scripts/bootstrap.sh doctor --model`/작은 live·TUI 경로로 별도 확인 |

**작은 팀 플러그인 수정마다 이미지 rebuild나 wheel 설치는 필요 없습니다.** setup 없는 lint/test/demo는
기존 `.venv`를 사용합니다. 문서 수정에는 링크·명령 대조를 수행하고 문구를 반복 검사하는 테스트를 만들지 않습니다.
계약 테스트 결과는 임시이며, minimal demo는 `runs/<run-id>/`의 보고서·summary를 남깁니다.
최소 데모는 두 합성 Agent·단일 repair stage·7 trial(solo 4/team 3)입니다.
호스트 도구 부재 skip과 실제 Docker/모델 실행 성공을 구분하고 [검증 기록](docs/verification.md)에 범위를 적습니다.

## 소유권과 재현성

- 후보는 `context.propose`로 만들고 원본·평가 기준을 수정하지 않습니다. train 피드백만
  mutation에 사용하고 validation 수치로 내부 frontier/최종 후보를 선택합니다. 선택 고정 후 test를 지킵니다.
  미지원 기능은 명시적 오류입니다.
- 미수집 사용량은 None, partial은 전체와 구분합니다. 로그·외부 소스·데이터·키·개인 설정은 커밋하지 않습니다.
- 외부 연동 변경 때 [SOURCES](docs/SOURCES.md)의 고정 출처/소비 파일을 대조합니다. 문서 정리로 pin을 갱신하지 않습니다.
- 의존성 변경은 pyproject.toml/uv.lock을 함께 검토합니다. 연구 라이브러리는 필요한 팀만 사용합니다.
  CVDP driver는 예제-local `requirements-cvdp-py312.txt`와 별도 Python 3.12 환경을 유지합니다.

## CI와 PR 병합

PR 코어 CI는 Python 3.11/3.12에서 lint·회귀·minimal·sdist/wheel·소스 밖 설치를 검사합니다.
Ubuntu native Yosys/Icarus 검사는 공식 CVDP 이미지 버전 재현과 별개입니다. 모델 호출은 없습니다.
공식 Docker 통합은 기존 `ci.yml`의 수동 `official_cvdp=true` 입력이며, 실행 성공은 실제 로그로 확인합니다.

자체 러너를 사용할 때는 저장소 변수 `CI_RUNNER_LABELS`에 JSON 배열
`["self-hosted","linux","x64"]`처럼 **실제 등록된 라벨**을 지정합니다. 기본값은
`["ubuntu-latest"]`입니다. 자체 러너에는 Git, Bash, make, Python 3.11/3.12를 제공하는
`actions/setup-python@v5` 실행 환경, Node 22를 제공하는 `actions/setup-node@v4` 실행 환경,
Yosys·Icarus(`yosys`, `iverilog`, `vvp`)를 준비하세요. native 도구 설치 단계는
GitHub 제공 러너에서만 수행하고 자체 러너에서는 버전 실행이 실패하면 CI를 중단합니다.
`actions/checkout@v4`, setup-python/setup-node, wheel 의존성·uv 0.10.7의 pip 설치가
러너에서 이용 가능해야 합니다. 필요한 proxy/CA와 Git 소스·Python package index는
[네트워크 안내](docs/network.md)의 표준 환경/도구 설정으로 제공합니다. 모델 키는 코어 CI에
필요하지 않습니다. 선택적 공식 통합 러너는 Docker daemon/Compose, CA 포함 빌드 시
Buildx, 고정 소스·데이터·이미지의 접근 경로도 별도로 준비해야 합니다.

로컬에서는 `make setup-core` → `sh scripts/bootstrap.sh doctor --core --json` →
`make lint` → `make test` → `make demo` → `node --test tests/endpoint-plugin.test.mjs` →
`.venv/bin/python -m build`로 코어에 가까운 명령을 확인할 수 있습니다.
이는 해당 러너의 Actions 실행 증거가 아닙니다. 공식 통합 결과의 artifact upload는 현재
`github.server_url == 'https://github.com'`에서만 수행하므로 다른 서버에서는 실행 로그와
`external/setup-logs/`, `runs/dev-smoke-*/`를 별도 보존·확인해야 합니다.

```bash
gh workflow run ci.yml --ref YOUR_BRANCH -f official_cvdp=true
```

PR에는 변경·검증·skip·미검증 영역을 적습니다. Python 3.11/3.12 필수 검사와 리뷰를 확인하고
저장소의 **rebase-only** 정책으로 병합합니다. 과거 CI 성공을 새 변경의 실행 증거로 재사용하지 않습니다.
러너 변경 시 `CI_RUNNER_LABELS`와 필요한 도구/액션 지원을 확인하고 실제 CI·릴리즈를 별도 검증합니다.

## 패키징·릴리즈

버전과 lock을 갱신한 PR 병합 후 대응 `v*` 태그로 release workflow를 실행합니다.
전체 CI와 태그/버전 일치 검사를 거친 wheel·sdist·SHA256SUMS가 Draft Release에 첨부됩니다.
게시 전 확인하고, 이미 게시한 버전은 덮어쓰지 않습니다. PyPI/실행 서버 자동 배포는 포함하지 않습니다.
배포 라이선스는 팀에서 결정합니다. 자세한 현재 구현은 `.github/workflows/`를 기준으로 확인하세요.
