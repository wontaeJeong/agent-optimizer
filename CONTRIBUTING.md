# 팀 개발

| 담당 | 주 작업 위치 | 완료 조건 |
|---|---|---|
| 공통 실행/계약 | src/agent_optimizer/ | 최소 데모와 계약 테스트 통과 |
| 알고리즘별 담당 | optimizers/gepa.py, meta_harness.py, ecdysis.py | propose/evaluate/usage 규약 연결, 상태표 갱신 |
| Agent/Harness | harnesses/, examples/ | 원본 보존, 실행 명령·오류·사용량 범위 문서화 |
| RTL 데모/환경 | examples/ace-rtl/, rtl-debugger/ | 공식 OSS 평가로 한 문제 검증 |

모듈 소유자는 해당 파일과 필요한 테스트를 함께 수정합니다. 공유 계약 변경은 먼저 팀 내 합의하고
예제를 같이 갱신합니다. 실제 담당자 이름이나 CODEOWNERS는 팀에서 정하세요.

[Mac/Ubuntu 사전 설치](docs/development.md)를 마치고 `make setup`으로 시작합니다.
make/Python이 없으면 `sh scripts/bootstrap.sh setup`이 uv·Python부터 준비합니다.
모든 Make 명령은 `sh scripts/bootstrap.sh <명령> [옵션]`으로도 실행할 수 있습니다.
코어만 개발할 때는 기존 uv로 `uv sync --frozen --python 3.12 --extra dev`을 실행합니다.
PR 전 아래 명령을 실행합니다.

```bash
make help
make lint
make test
make demo
.venv/bin/python -m build
git diff --check
```

`make lint`, `make test`, `make demo`는 환경을 활성화하거나 의존성을 자동 설치하지 않고 `.venv`를 사용합니다.
직접 CLI를 쓸 때는 `. .venv/bin/activate` 후 `agent-opt --help`를 실행하고 `deactivate`로 나옵니다.
기존 `python3 scripts/dev.py <명령>`도 유지됩니다. setup으로 설치한 uv를 직접 쓰려면
`export PATH="$PWD/.cache/uv/bin:$PATH"`로 현재 shell에만 추가합니다.

전체 실환경 검증은 `make setup` → `make doctor` → `make setup ARGS="--offline"` →
`make smoke` 순서입니다. 호스트 도구가 없는 `make test`의 skip과 Docker 실도구 smoke는
별도로 기록하세요. smoke는 모델 호출이 없으며 로그는 `runs/dev-smoke-*/`에 남습니다.

wheel은 별도 venv에 설치하고 소스 밖 작업 디렉터리에서 `python -I -m agent_optimizer --help`와
`agent-opt --help`를 확인합니다. 로컬 임시 환경은 Git 제외 `runs/` 아래에 둘 수 있습니다.

의존성을 추가하면 pyproject.toml과 `uv lock`을 함께 커밋합니다. 알고리즘 라이브러리는 가능하면
optional dependencies로 분리해 최소 데모가 무거운 연구 의존성을 요구하지 않도록 합니다.
공식 CVDP host driver는 별도 Python 3.12 환경과 예제-local
`examples/ace-rtl/environment/requirements-cvdp-py312.txt`를 사용합니다. 이 lock은 고정 upstream
requirements를 uv 0.10.7의 `pip compile --universal --python-version 3.12`로 전이 의존성까지
고정한 것입니다. 갱신 절차·입력 hash는 [SOURCES.md](docs/SOURCES.md)에 있습니다.
upstream checkout을 수정하지 말고 lock diff 검토 후 위 전체 실환경 검증을 실행하세요.
환경 lock은 생성물이며 Git에 추가하지 않습니다.

PR에는 문제/변경/검증/미검증 영역을 짧게 적습니다. 외부 API 실행은 모델·데이터·예산을 기록합니다.
실험 로그, 외부 소스, 데이터셋, API 키, 개인 IDE/Agent 설정은 커밋하지 않습니다.
이 배포본은 조직의 공개 배포 라이선스를 임의로 선택하지 않았습니다. 외부 공개 시 팀에서 결정하세요.

## CI와 PR 병합

`core-tests`는 PR, main push, 수동 실행에서 Python 3.11/3.12로 lint, 테스트, 최소 데모,
sdist/wheel 빌드, 소스 트리 밖 wheel 설치와 CLI 실행을 검사합니다. uv 0.10.7을 격리 설치하고
`uv sync --frozen --python <matrix version> --extra dev`로 프로젝트 lock을 사용합니다.
lint는 문법 오류·일부 확정적인 코드 오류만 차단합니다.
Hosted Ubuntu는 apt의 Yosys/Icarus를 설치하며 세 실행 파일(`yosys`, `iverilog`, `vvp`)이 없으면
실패합니다. 실제 도구 테스트 9개가 전체 suite에서 실행됩니다. 이 CI 편의 설치는 공식 CVDP 이미지의
정확한 버전 재현을 대신하지 않습니다. PR CI에 외부 live/model 호출이나 공식 이미지 빌드는 없습니다.

공식 Docker 평가는 **기존 `ci.yml`**의 수동 boolean 입력 `official_cvdp=true`로 실행합니다.
Docker Engine/Compose가 필요하며 native 플랫폼에서 `make setup` → `make doctor` →
`make setup ARGS="--offline"` → `make smoke`와
실제 OpenCode config 검사를 수행합니다. 모델 키·inference는 사용하지 않습니다.
GitHub.com에서는 setup lock/logs와 smoke 산출물을 7일 artifact로 보존합니다. 다른 서버에서는
runner의 해당 경로와 job 로그를 직접 보존하세요.

```bash
# 해당 브랜치가 원격에 올라간 후 (기존 ci.yml은 default branch에 있어야 함):
gh workflow run ci.yml --ref YOUR_BRANCH -f official_cvdp=true
```

수동 분기 실행 지원은 workflow 구성이지 실행 증거가 아닙니다. native Ubuntu x86_64의 실제
결과는 이 job 실행 후 [검증 기록](docs/verification.md)에 추가하세요. `10baa46`의 native Ubuntu
통과는 과거 공식 통합 근거입니다. 온보딩 `cbca34f`의 Ubuntu Python 3.11/3.12 코어 CI도
통과했으며, 이번 수동 공식 Docker job 재실행과는 구분합니다. 실제 결과는 검증 기록을 따릅니다.

저장소 관리자는 main의 branch protection/ruleset에서 다음을 설정합니다.

- PR을 통한 병합과 리뷰 1명 요구, 새 커밋 시 기존 승인 무효화
- `Python 3.11`, `Python 3.12`를 필수 상태 검사로 지정 (첫 CI 실행 후 UI에서 선택)
- force push와 브랜치 삭제 금지

이 설정은 YAML만으로 적용되지 않습니다. 태그 `v*` 생성 권한도 릴리즈 담당자로 제한하세요.

## 데모 릴리즈

1. pyproject.toml의 version을 갱신하고 `uv lock`을 실행한 PR을 main에 병합합니다.
2. 병합된 커밋에 해당 버전 태그를 만들고 push합니다. 예: `v0.3.0`.
3. `release`가 전체 CI를 다시 실행하고 태그와 패키지 버전 일치를 검사합니다.
4. wheel, sdist, SHA256SUMS를 Draft Release에 첨부한 후 게시합니다.

GitHub.com과 GHES 모두 해당 저장소의 Releases에 게시됩니다. PyPI나 실행 서버 배포는
포함하지 않습니다. 설치는 릴리즈에서 wheel을 내려받아 `python -m pip install <wheel 경로>`로 합니다.
동일 태그의 기존 릴리즈는 덮어쓰지 않습니다. 실패로 Draft가 남으면 원인을 해결하고
Draft를 삭제한 뒤 실패 job을 재실행하세요. 이미 게시한 버전 수정은 새 버전 태그를 사용합니다.

## GHES / self-hosted 전환

- 저장소 Actions variable `CI_RUNNER_LABELS`를 JSON 배열로 설정합니다.
  예: `["self-hosted", "linux", "x64"]`. 미설정 시 `["ubuntu-latest"]`입니다.
- Linux 러너에 bash, make, Git, Python venv/pip 지원, `sha256sum`, GitHub CLI(`gh`)를 준비합니다.
  self-hosted에서는 Yosys, Icarus/vvp도 미리 설치해야 하며 없는 도구를 skip으로 처리하지 않습니다.
  수동 공식 integration에는 Docker Engine/Compose 및 이미지 빌드 공간도 필요합니다.
  `actions/setup-python@v5`가 Python 3.11/3.12를 확보할 수 있어야 합니다.
  폐쇄망에서는 러너 tool cache를 미리 구성하고 내부 패키지 인덱스를 설정하세요.
- `actions/checkout@v4`, `actions/setup-python@v5`의 GHES 제공/미러링과 Node 20 지원
  러너 버전을 확인합니다. 실제 GHES 버전과 네트워크 정책에 맞게 액션 참조를 조정하세요.
- uv 0.10.7 및 격리된 패키지 빌드에 필요한 의존성(build, ruff, setuptools 등)을 내부 인덱스에
  준비합니다. pip 인덱스와 사내 CA는 러너 환경/credential store에서 설정합니다.
- 릴리즈는 `github.server_url`과 `GITHUB_TOKEN`으로 해당 서버에 인증합니다.
  publish job만 `contents: write`를 요청하며, 조직 정책에서 허용되어야 합니다.
  GHES 호환성이 다른 Actions artifact 업로드를 경유하지 않고 Releases에 직접 첨부합니다.
- self-hosted는 신뢰한 팀 PR용으로 운영하세요. 외부 fork PR까지 받는 경우 격리된 일회성
  러너 또는 별도 실행 정책이 필요합니다. checkout 청소는 러너 OS 격리를 대신하지 않습니다.

GHES 이전 후 PR 검사와 실제 태그 릴리즈를 한 번씩 실행해 설치·인증·파일 첨부를 확인합니다.
