# 팀 개발

| 담당 | 주 작업 위치 | 완료 조건 |
|---|---|---|
| 공통 실행/계약 | src/agent_optimizer/ | 최소 데모와 계약 테스트 통과 |
| 알고리즘별 담당 | optimizers/gepa.py, meta_harness.py, ecdysis.py | propose/evaluate/usage 규약 연결, 상태표 갱신 |
| Agent/Harness | harnesses/, examples/ | 원본 보존, 실행 명령·오류·사용량 범위 문서화 |
| RTL 데모/환경 | examples/ace-rtl/, rtl-debugger/ | 공식 OSS 평가로 한 문제 검증 |

모듈 소유자는 해당 파일과 필요한 테스트를 함께 수정합니다. 공유 계약 변경은 먼저 팀 내 합의하고
예제를 같이 갱신합니다. 실제 담당자 이름이나 CODEOWNERS는 팀에서 정하세요.

`uv sync --frozen --extra dev`으로 시작합니다. PR 전 아래 명령을 실행합니다.

```bash
uv run --frozen --extra dev ruff check .
uv run --frozen --extra dev python -m unittest discover -s tests -v
uv run --frozen --extra dev python -m agent_optimizer run examples/minimal/experiment.toml
uv run --frozen --extra dev python -m build
```

의존성을 추가하면 pyproject.toml과 `uv lock`을 함께 커밋합니다. 알고리즘 라이브러리는 가능하면
optional dependencies로 분리해 최소 데모가 무거운 연구 의존성을 요구하지 않도록 합니다.

PR에는 문제/변경/검증/미검증 영역을 짧게 적습니다. 외부 API 실행은 모델·데이터·예산을 기록합니다.
실험 로그, 외부 소스, 데이터셋, API 키, 개인 IDE/Agent 설정은 커밋하지 않습니다.
이 배포본은 조직의 공개 배포 라이선스를 임의로 선택하지 않았습니다. 외부 공개 시 팀에서 결정하세요.

## CI와 PR 병합

`core-tests`는 PR, main push, 수동 실행에서 Python 3.11/3.12로 lint, 테스트, 최소 데모,
sdist/wheel 빌드, 소스 트리 밖 wheel 설치와 CLI 실행을 검사합니다. CI는 별도 venv에서
`pip install -e '.[dev]'`를 사용합니다. 개발 도구 버전은 pyproject.toml에 고정하며,
uv.lock의 전이 의존성까지 CI에 강제하는 구성은 아닙니다.
lint는 문법 오류·일부 확정적인 코드 오류만 차단합니다. 외부 모델/API/Docker는 실행하지 않습니다.
Icarus가 없는 러너에서는 실제 Icarus smoke가 skip됩니다.

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
- Linux 러너에 bash, Git, Python venv/pip 지원, `sha256sum`, GitHub CLI(`gh`)를 준비합니다.
  `actions/setup-python@v5`가 Python 3.11/3.12를 확보할 수 있어야 합니다.
  폐쇄망에서는 러너 tool cache를 미리 구성하고 내부 패키지 인덱스를 설정하세요.
- `actions/checkout@v4`, `actions/setup-python@v5`의 GHES 제공/미러링과 Node 20 지원
  러너 버전을 확인합니다. 실제 GHES 버전과 네트워크 정책에 맞게 액션 참조를 조정하세요.
- pip 및 격리된 패키지 빌드에 필요한 의존성(build, ruff, setuptools 등)을 내부 인덱스에
  준비합니다. pip 인덱스와 사내 CA는 러너 환경/credential store에서 설정합니다.
- 릴리즈는 `github.server_url`과 `GITHUB_TOKEN`으로 해당 서버에 인증합니다.
  publish job만 `contents: write`를 요청하며, 조직 정책에서 허용되어야 합니다.
  GHES 호환성이 다른 Actions artifact 업로드를 경유하지 않고 Releases에 직접 첨부합니다.
- self-hosted는 신뢰한 팀 PR용으로 운영하세요. 외부 fork PR까지 받는 경우 격리된 일회성
  러너 또는 별도 실행 정책이 필요합니다. checkout 청소는 러너 OS 격리를 대신하지 않습니다.

GHES 이전 후 PR 검사와 실제 태그 릴리즈를 한 번씩 실행해 설치·인증·파일 첨부를 확인합니다.
