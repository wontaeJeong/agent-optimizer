# 이식 가능한 환경 준비 구현 계획

> **구현 시 필수 스킬:** 작업별로 superpowers:subagent-driven-development 또는 superpowers:executing-plans를 적용한다. 단계는 체크박스로 추적한다.

**목표:** 별도 mirror 계층 없이 고정 Git 소스 재작성을 검증하고 CI·네트워크의 실제 준비 조건을 명확히 한다.

**구조:** Git 자식 프로세스는 기존 `url.*.insteadOf`를 따르며 제품은 source commit과 데이터
해시를 검사한다. 인터넷을 사용하지 않는 통합 테스트로 이를 확인한다. 별도 전송 API 대신
Git·uv/pip·Docker의 표준 설정을 활용하고, 로컬 CI 유사 검사와 원격 workflow 실행을 구분한다.

**기술:** Python 3.11+ 표준 `unittest`, Git, uv, 선택적 Docker 통합, GitHub Actions YAML.

**설계:** `docs/superpowers/specs/2026-09-25-readiness-followup-design.md`

## 공통 제약

- 고정 revision/해시를 유지하고 대체 전송 경로도 pin 검사를 우회하지 않는다.
- proxy/CA는 선택적이며 기존 전체 PEM bundle·대소문자 proxy·`NO_PROXY` 계약을 유지한다.
- 일반 CI는 모델 없이 실행하고 공식 Docker 통합은 선택적으로 유지한다.
- 인증정보·비공개 endpoint·proxy 값을 프로젝트 파일에 넣지 않는다.
- 현재 환경에서는 실제 모델·원격 러너 성공을 검증할 수 없다.

---

## 파일 책임

- `tests/test_integrations.py`: 임시 로컬 저장소를 통한 Git rewrite·고정 commit 검사.
- `docs/network.md`: 표준 전송 경로와 대체 cache 준비 안내.
- `CONTRIBUTING.md`: 자체 러너의 도구·연결 조건과 CI 유사 명령.
- `.github/workflows/ci.yml`: 점검 후 실제 결함이 있을 때만 수정.

### 작업 1: 소스 재작성 후에도 고정 commit 유지

**파일:** `tests/test_integrations.py`, `docs/network.md`

**입력/출력:** `materialize_agent(agent: AgentSpec, target: Path)`와 기존
`SourceSpec(kind="git", url=..., revision=...)`를 사용한다. 로컬 저장소로 재작성해도
source lock에 요청·확정 commit이 같고 원래 공개 URL이 기록되는 것을 검증한다.

- [ ] **1. 실제 Git 통합 테스트.** 임시 Git 저장소에 `prompts/system.md`와 editable 파일을
  만들고 `git -c user.name=... -c user.email=... commit`으로 커밋하여 전체 SHA를 구한다.
  공개 형식 URL `https://github.com/example/pinned-agent.git`을 사용한 `AgentSpec`을 만들고
  `patch.dict(os.environ, {"GIT_CONFIG_COUNT":"1", "GIT_CONFIG_KEY_0":"url.file://<임시 저장소 절대경로>.insteadOf", "GIT_CONFIG_VALUE_0":"https://github.com/example/pinned-agent.git"})` 안에서
  `materialize_agent`를 호출한다. `source-lock.json`의 `requested_commit`·`resolved_commit`
  일치, 원본 URL·파일 내용, 잘못된 SHA 요청의 거부를 확인한다.
- [ ] **2. 단독 테스트 실행.** `PYTHONPATH=src:tests .venv/bin/python -m unittest test_integrations.SourceTests.test_git_url_rewrite_preserves_pinned_source_identity -v`를 실행한다. 이미 통과하면 기존 기능의 검증 증거로 사용하고 불필요한 소스 추상화는 추가하지 않는다.
- [ ] **3. `docs/network.md` 안내.** 셸 범위 Git rewrite(`GIT_CONFIG_COUNT`,
  `GIT_CONFIG_KEY_0`, `GIT_CONFIG_VALUE_0`), `UV_DEFAULT_INDEX`/`PIP_INDEX_URL`, Docker
  daemon registry 책임을 예제로 적는다. 공개 기본 URL과 commit/해시 검사는 유지하고,
  현재 `uv.lock`의 공개 절대 URL은 index만 바꿔도 재작성되지 않는다고 밝힌다.
  데이터만 미리 넣은 첫 setup은 online 경로를 사용하고, offline 재사용에는 환경 lock·driver·
  이미지·uv cache까지 필요하다. 인증정보·실제 비공개 주소는 넣지 않는다.
- [ ] **4. 집중 검사와 커밋.** `PYTHONPATH=src:tests .venv/bin/python -m unittest test_integrations.SourceTests test_network.NetworkTests -v`를 실행하고 해당 테스트·문서만 커밋한다.

### 작업 2: 기존 CI 계약과 실행 한계 확인

**파일:** `CONTRIBUTING.md:44-63`, `.github/workflows/ci.yml` 및 `release.yml`(점검)

**입력/출력:** `CI_RUNNER_LABELS` JSON 라벨 배열, 기존 `make help/lint/test/demo`, 고정 uv,
선택적 `workflow_dispatch` Docker 검사를 사용한다. 자체 러너 필수 조건을 기록하되
로컬 명령을 원격 CI 실행으로 주장하지 않는다.

- [ ] **1. 각 job의 조건 조사.** Python 3.11/3.12, Node 22, `yosys`·`iverilog`·`vvp`,
  uv/pip, 선택적 Docker/Compose/Buildx, Action 제공, proxy/CA와 artifact 처리를 확인한다.
  실제 오류가 확인된 경우에만 workflow를 수정한다.
- [ ] **2. `CONTRIBUTING.md`에 준비 계약 기록.** `CI_RUNNER_LABELS` JSON 예,
  자체 러너 사전 설치 도구, proxy/CA 및 Python/Git/image 공급 경로, 기존 선택적 Docker job
  실행 명령을 적는다. 로컬 성공과 CI 결과를 구분하고 현재 artifact 업로드 조건을 그대로 설명한다.
- [ ] **3. 실제 로컬 명령 확인.** `make help`, `make lint`, `make test`, `make demo`,
  `.venv/bin/python -m build`, Node가 있으면 `node --test tests/endpoint-plugin.test.mjs`,
  `make doctor ARGS="--core --json"`을 실행한다. Docker daemon·Buildx가 둘 다 가능할 때만
  `AGENT_OPT_NETWORK_DOCKER=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_network.DockerNetworkIntegrationTests -v`를 실행하고 skip/차단 이유를 기록한다.
- [ ] **4. 변경 검토 및 커밋.** 변경된 문서와 필요한 경우에만 수정한 workflow를 확인한다.
  원격 workflow나 ACE live가 실제로 실행되지 않았으면 완료 근거로 쓰지 않는다.

## 인계 검증

설계와 두 계획의 범위를 다시 대조하고 `git diff --check` 및 실제 검증 결과를 보고한다.
모델 자격증명과 실행 환경이 준비되면 `make setup`, `make doctor`,
`make setup ARGS="--offline"`, `make smoke`, 명시적 `make doctor ARGS="--model"`,
작은 `make live ARGS="--iterations 3"`를 순서대로 수행한다. 원격 workflow는 해당
러너에서 실행해 따로 확인한다. 인증정보 부재를 합성 성공으로 대체하지 않는다.
