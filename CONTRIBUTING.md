# 팀 개발

**코어 준비 → fixture → 팀 플러그인 하나** 순서로 시작합니다. 프로젝트 루트에서:

```bash
make setup ARGS="--core"
make doctor ARGS="--core"
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_plugin_contracts.py -v
make demo
```

make/Python이 없으면 `sh scripts/bootstrap.sh setup --core`를 사용합니다.
설치·활성화·offline 복구는 [개발환경](docs/development.md), 역할 선택은 [팀 템플릿](experiments/README.md).
일반 팀 확장은 `experiments/<team>/`의 파일 등록을 사용하며 registry/설치 entry point를 수정하지 않습니다.
Optimizer는 propose/evaluate, Harness는 RunRequest/ExecutionResult, 외부 Agent는 소스·실행·평가를 맡습니다.
공통 계약 변경은 팀과 합의하고 관련 예제를 함께 갱신하세요. 도메인 코드는 examples에 둡니다.

## 변경 범위별 로컬 검증

| 변경 | 필요한 검사 |
|---|---|
| 팀 플러그인·코어 | 관련 계약 회귀 → 해당 experiment `plan`/작은 fixture 실행 → `make lint`, `make test`, `make demo`, `git diff --check` |
| 패키징·의존성·릴리즈 | 위 검사 + `.venv/bin/python -m build`; 별도 venv에 wheel 설치 후 소스 밖에서 `python -I -m agent_optimizer --help`, `agent-opt --help` |
| ACE·Docker·환경 연결 | 관련 회귀 + `make setup` → `make doctor` → `make setup ARGS="--offline"` → `make smoke`; 실제 모델 연결 변경은 자격증명 준비 후 `make doctor ARGS="--model"`/작은 live |

**작은 팀 플러그인 수정마다 이미지 rebuild나 wheel 설치는 필요 없습니다.** setup 없는 lint/test/demo는
기존 `.venv`를 사용합니다. 문서 수정에는 링크·명령 대조를 수행하고 문구를 반복 검사하는 테스트를 만들지 않습니다.
계약 테스트 결과는 임시이며, minimal demo는 `runs/<run-id>/`의 보고서·summary를 남깁니다.
최소 데모는 두 합성 Agent·단일 repair stage·7 trial(solo 4/team 3)입니다.
호스트 도구 부재 skip과 실제 Docker/모델 실행 성공을 구분하고 [검증 기록](docs/verification.md)에 범위를 적습니다.

## 소유권과 재현성

- 후보는 `context.propose`로 만들고 원본·평가 기준을 수정하지 않습니다. train-only 탐색,
  validation 선택, 선택 고정 후 test를 지킵니다. 미지원 기능은 명시적 오류입니다.
- 미수집 사용량은 None, partial은 전체와 구분합니다. 로그·외부 소스·데이터·키·개인 설정은 커밋하지 않습니다.
- 외부 연동 변경 때 [SOURCES](docs/SOURCES.md)의 고정 출처/소비 파일을 대조합니다. 문서 정리로 pin을 갱신하지 않습니다.
- 의존성 변경은 pyproject.toml/uv.lock을 함께 검토합니다. 연구 라이브러리는 필요한 팀만 사용합니다.
  CVDP driver는 예제-local `requirements-cvdp-py312.txt`와 별도 Python 3.12 환경을 유지합니다.

## CI와 PR 병합

PR 코어 CI는 Python 3.11/3.12에서 lint·회귀·minimal·sdist/wheel·소스 밖 설치를 검사합니다.
Ubuntu native Yosys/Icarus 검사는 공식 CVDP 이미지 버전 재현과 별개입니다. 모델 호출은 없습니다.
공식 Docker 통합은 기존 `ci.yml`의 수동 `official_cvdp=true` 입력이며, 실행 성공은 실제 로그로 확인합니다.

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
