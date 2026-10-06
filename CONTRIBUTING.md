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
| 개발 명령·CLI UX | `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_dev_onboarding.py -v` 및 `test_menu.py`·`test_dev_doctor.py`·`test_cli_experience.py` 관련 회귀 → `make lint`, `make test`, `make demo`, `git diff --check`; 합성/명령 전달 성공은 ACE 실행 성공과 구분 |
| 팀 플러그인·코어 | 관련 계약 회귀 → `.venv/bin/agent-opt datasets list` / `doctor --dataset ID` / `doctor --plan PATH` / 작은 fixture 실행 → `make lint`, `make test`, `make demo`, `git diff --check` |
| 패키징·의존성·릴리즈 | 위 검사 + `.venv/bin/python -m build`; 아래 명령으로 현재 버전의 wheel 하나와 메타데이터를 확인하고 저장소 밖에서 목록·TUI 거절·사용자 Agent/채점기 init/doctor/run/report 검증 |
| ACE·Docker·환경 연결 | 관련 회귀 + `make setup` → `make doctor` → `sh scripts/bootstrap.sh setup --offline` → `make smoke`; 수동 공식 CI는 모델 없이 평가 경로와 ACE CLI의 인증 실패를 검사. 실제 모델 E2E는 자격증명 준비 후 앱의 `agent-opt tui` 또는 `agent-opt run examples/ace-rtl/experiment.toml`로 확인하고, 개발 중에는 `sh scripts/bootstrap.sh doctor --model`로 연결만 별도 진단 |

선택형 ACE의 wheel 실도구 검증은 저장소 밖 가상환경에 빌드된 wheel을 설치한 뒤
`agent-opt init --profile ace-rtl --workspace <공유 작업공간>` →
`agent-opt prepare <공유 작업공간>/experiment.toml` →
`agent-opt doctor --plan <공유 작업공간>/experiment.toml --json` 순서로 확인합니다.
Docker Desktop이 파일을 공유하는 작업공간을 cwd로 하여 설치된 Python으로
`/path/to/agent-optimizer/tests/test_installed_ace.py`를 실행하면 공식 LFSR의 정답·오답 raw test를 각각 검사합니다.
이 스크립트는 모델을 호출하지 않고, 참조 RTL은 신뢰한 검사 경로에서만 읽습니다.
모델 키 없는 `agent-opt run`의 `blocked_auth`도 별도로 검사하세요.

```bash
wheel=$(.venv/bin/python scripts/select_wheel.py dist)
.venv/bin/python tests/test_installed_cli.py "$wheel"
```

`dist/`에 이전 wheel이 남아 둘 이상이면 선택이 실패합니다. 기존 빌드 산출물을 확인해
필요한 것만 명시적으로 치운 뒤 다시 빌드하세요. 고정 버전 파일명을 가정하지 않습니다.

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
회귀는 `.venv/bin/python scripts/run_tests.py --jobs 2`로 평평한 `tests/test*.py` 모듈을
두 격리 프로세스에 나눕니다. 프로세스 안에서는 직렬 실행하여 전역 patch 간섭을 피하고,
완료된 프로세스부터 로그를 출력한 뒤 테스트·skip·실패·오류 수와 느린 테스트 상위 10개를 합산합니다.
실패·import 오류·worker 비정상 종료·빈 테스트는 CI 실패이며, 취소 시 worker와 같은 프로세스 그룹의
하위 프로세스를 제한 시간 안에 종료합니다. 로컬 `make test`는 직렬 재현 명령으로 유지합니다.
CI와 release는 고정 uv 0.10.7의 `uv build`로 sdist를 만들고 그 sdist에서 wheel을 빌드합니다.
GitHub.com release의 publish 단계는 같은 run의 Python 3.11에서 빌드·설치 검증한
`release-packages` artifact를 재사용합니다. 별도 빌드와 앱·개발 의존성 재설치가 없습니다.
다른 서버에서는 기존 고정 uv 재빌드 경로를 사용합니다.
GitHub.com에서는 uv/pip 다운로드 캐시를 OS·arch·Python·lock 입력별로 재사용하고, 공식 CVDP의
`external/cvdp-data`는 복원 후 기존 SHA-256 검사를 다시 수행합니다. 가상환경·이미지 lock·자격증명은
캐시에 넣지 않습니다. 그 밖의 서버에서는 cache action을 건너뛰고 동일한 설치·검증 명령을 실행합니다.
Ubuntu native Yosys/Icarus 검사는 공식 CVDP 이미지 버전 재현과 별개입니다. 모델 호출은 없습니다.
공식 Docker 통합은 기존 `ci.yml`의 수동 `official_cvdp=true` 입력이며, 실행 성공은 실제 로그로 확인합니다.
GitHub 제공 러너에서는 고정 Buildx v0.21.3의 local layer cache를 사용합니다. 이미지를 daemon에
`--load`한 뒤 기존 source·driver·데이터 hash·실도구·이미지 ID 검사를 수행하며, cache hit 자체를
환경 검증 성공으로 취급하지 않습니다. Icarus v12의 완료된 export는 전체 평가 실패와 독립적으로 보존합니다.
native Yosys/Icarus의 `.deb`만 실제 러너 이미지 버전별로 보존하며 apt의 서명·설치·버전 확인을 유지합니다.
Pages는 문서와 무관한 PR에서만 설치·빌드를 생략하고 `build` 체크를 완료합니다. main push와 수동 실행은
전체 문서·링크 검사 및 기존 게시 흐름을 사용합니다.

Mac/Linux에서 직접 Docker layer cache를 쓸 때는 `AGENT_OPT_BUILD_CACHE_DIR`에 쉼표·줄바꿈 없는
절대 경로와 local exporter를 지원하는 Buildx builder를 지정합니다. 캐시는 이미지 태그별로 잠금하며,
빌드 실패는 기존 캐시를 보존하고 성공한 export만 교체합니다. cache 내부 symlink·특수 파일은 거부합니다.
교체 복구에 실패한 `.previous` 디렉터리는 보존되고 후속 실행이 명시적으로 실패하므로 기존 자료를
확인해 복구해야 합니다. 변수 미지정과 offline setup은 기존 빌드·읽기 전용 재검증 흐름을 사용합니다.

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
gh workflow run ci.yml --ref YOUR_BRANCH -f verilog_eval_full=true -f verilog_jobs=2
```

PR에는 변경·검증·skip·미검증 영역을 적습니다. Python 3.11/3.12 결과를 집계한 **CI Gate**와
리뷰를 확인하고 **squash-only** 정책으로 병합합니다. linear history를 유지하며,
대화 해결을 필수로 요구합니다. 과거 CI 성공을 새 변경의 실행 증거로 재사용하지 않습니다.
러너 변경 시 `CI_RUNNER_LABELS`와 필요한 도구/액션 지원을 확인하고 실제 CI·릴리즈를 별도 검증합니다.

### PR / Merge Queue 2단계

- PR의 `pull_request`: 현재 변경을 검사하고 `CI Gate` 통과 후 병합 또는 큐 진입을 허용합니다.
- 큐의 `merge_group` (`checks_requested`): 최신 main과 앞선 큐 항목을 합친 임시 커밋에서
  동일한 검사를 다시 실행합니다. PR의 성공을 큐 검사 대신 사용하지 않습니다.
- 필수 체크 이름은 두 단계 모두 **CI Gate** 하나입니다. 단계별로 서로 다른 필수 체크를
  등록하면 다른 이벤트에서 체크가 생성되지 않아 병합이 대기할 수 있습니다.
- Gate는 Python matrix 전체 성공만 허용합니다. 실패·취소·예상치 못한 job 건너뜀은 실패입니다.
  수동 `official-cvdp`·`verilog-eval-full`은 PR/큐의 필수 검사가 아닙니다.
- 이벤트별 concurrency를 분리하고 큐 실행의 자동 취소를 끕니다. workflow 수준 path 필터로
  필수 체크 실행을 건너뛰지 않습니다.

### 보호 규칙 적용과 큐 활성화

`.github/rulesets/main.json`은 큐 활성화 전 기본 정책입니다. 기존 ruleset을 **갱신**하여
중복 규칙을 만들지 않습니다. 기본 브랜치 생성·삭제·강제 push·직접 push를 차단하고,
관리자 우회도 허용하지 않습니다. 필수 승인 수는 기존 0을 유지합니다.
필수 체크는 GitHub Actions (`integration_id=15368`)에서만 받습니다. 다른 서버에서는
해당 서버의 Actions 앱 ID를 확인하여 바꿔야 합니다.

먼저 CI 변경 PR에서 새 `CI Gate`의 실제 성공을 확인한 뒤 기존 ruleset의 필수 체크를 교체합니다.
이 PR을 squash로 병합해야 이후 PR에도 새 Gate가 생성됩니다. 저장소 설정도
`allow_squash_merge=true`, `allow_merge_commit=false`, `allow_rebase_merge=false`로 맞춥니다.
큐 활성화 전에는 최신 main 반영 필수(`strict_required_status_checks_policy=true`)를 유지합니다.

GitHub.com의 Merge Queue는 Organization 소유 공개 저장소 또는 Enterprise Cloud의
Organization 소유 비공개 저장소에서 지원합니다. 개인 소유 저장소에서는 이벤트 처리와
큐 규칙 파일만 준비하며 큐가 활성화되었다고 간주하지 않습니다.

지원되는 Organization으로 이전하고 CI 변경이 기본 브랜치에 반영된 뒤, 기존 ruleset에
`.github/rulesets/merge-queue-rule.json`을 추가하고 strict를 해제합니다.
기본 큐 값은 squash, 모든 항목 성공(ALLGREEN), 동시 빌드 2개, 병합 단위 1개,
최소 1개·대기 0분, 체크 응답 제한 30분입니다. 현재 Python job 제한 15분과 Gate 2분에
러너 대기 여유를 둡니다. 자체 러너 대기가 길면 응답 제한을 조정하세요.

```bash
# 이전 후 실제 저장소와 기존 ruleset ID를 지정합니다.
REPO=YOUR_ORG/agent-optimizer
RULESET_ID=YOUR_EXISTING_RULESET_ID
jq --slurpfile queue .github/rulesets/merge-queue-rule.json \
  '.rules += $queue | (.rules[] | select(.type == "required_status_checks") | .parameters.strict_required_status_checks_policy) = false' \
  .github/rulesets/main.json |
  gh api --method PUT "repos/$REPO/rulesets/$RULESET_ID" --input -
```

활성화 후 검증용 PR을 큐에 넣어 `merge_group` 실행·`CI Gate` 성공·squash 결과를 확인합니다.
큐에서 실패한 항목이 제거되는지도 실제 실행으로 확인해야 하며, 이벤트 설정이나 JSON 검증은
큐 통합 성공의 증거가 아닙니다.

근거: [Merge Queue 지원·설정](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue),
[필수 체크와 merge_group](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks),
[ruleset API](https://docs.github.com/en/rest/repos/rules#update-a-repository-ruleset).

## 패키징·릴리즈

버전과 lock을 갱신한 PR 병합 후 대응 `v*` 태그로 release workflow를 실행합니다.
전체 CI와 태그/버전 일치 검사를 거친 wheel·sdist·SHA256SUMS가 Draft Release에 첨부됩니다.
게시 전 확인하고, 이미 게시한 버전은 덮어쓰지 않습니다. PyPI/실행 서버 자동 배포는 포함하지 않습니다.
배포 라이선스는 팀에서 결정합니다. 자세한 현재 구현은 `.github/workflows/`를 기준으로 확인하세요.

게시 없이 release의 검사·artifact 재사용·checksum 생성을 검증하려면
`gh workflow run release.yml --ref YOUR_BRANCH`를 사용합니다. 수동 실행은 태그를 생성하지 않고
release를 게시하지 않으며 `release-verification` artifact만 남깁니다. 실제 태그 실행의 버전 검사와
게시 API는 이 dry-run 성공과 구분합니다.
