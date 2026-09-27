# 모델 설정과 앱 실행 경로 단순화 구현 계획

> **실행 담당:** 이 계획의 체크박스를 순서대로 진행하고, 각 기능은 실패 테스트 → 최소 구현 → 통과 테스트로 확인한다. 현재 세션에서 직접 실행한다.

**목표:** 단일 `AGENT_OPT_MODEL_BASE_URL` 설정과 설치형 앱 중심의 ACE/CVDP E2E 경로를 제공하고 실제 중복 공개 명령/옵션을 제거한다.

**구조:** 공통 모델 HTTP 계약은 `models.py`, 대화형 일시 입력은 평평한 `model_input.py`에 둔다. TUI는 연구 stage·하네스의 선언된 환경 전달 값만 읽어 모델 입력을 세션에서 받고, 실행 승인 전 플러그인을 import하지 않는다. 앱 CLI의 기존 `init`/`prepare`/`run` 호출 경계와 ACE lifecycle을 재사용한다.

**기술:** Python 3.11+, Typer, unittest, `shlex`, Docker/CVDP(선택적 실환경).

**설계:** `docs/superpowers/specs/2026-09-26-model-settings-cli-ux-design.md`

## 공통 제약

- 표준 OpenAI 호환 모델 URL은 `{AGENT_OPT_MODEL_BASE_URL.rstrip('/')}/chat/completions` 하나이다.
- 토큰은 환경/credential store 또는 TUI 세션에만 보관한다. `.env`는 앱이 자동 읽지 않는다.
- 공식 채점과 Agent 스냅샷 경계는 변경하지 않는다. 실행은 argv 배열과 `shell=False`이다.
- 기존 작업 워크트리 `fix/model-config-app-ux`의 기준 테스트는 628개 중 15 skip, 실패 0이다.
- 사람이 읽는 문서·메시지·커밋·PR은 한국어로 쓴다. 과거 검증 근거의 문구는 갱신하지 않는다.

## 파일 지도

- `src/agent_optimizer/models.py`: 단일 모델 URL 입력 검증/요청 URL 조립.
- `src/agent_optimizer/model_input.py`(신규): 셸에 없는 필수 값만 숨김·일시 입력, 환경 복구.
- `src/agent_optimizer/cli.py`, `src/agent_optimizer/readiness.py`, `src/agent_optimizer/locale.py`: 중복 CLI 명령 제거, TUI 선택 흐름, 진단.
- `examples/ace-rtl/{adapter.py,harness.toml,environment/{setup.py,diagnostics.py,model_checks.py}}`, `scripts/menu.py`: 선택형 ACE 모델 설정과 도구 진단의 URL 단일화.
- `tests/test_{models,menu,cli_experience,dev_environment,dev_doctor,demo_environment,feedback_optimizer,research,locale}.py`, `tests/endpoint-plugin.test.mjs`, `tests/opencode_endpoint_fixture.py`: 계약/회귀 fixture.
- `README.md`, `.env.example`, `docs/{development,adding-components}.md`, `experiments/simple-feedback/README.md`, `examples/ace-rtl/README.md`, `website/user/{getting-started,experiment}.md`, `CONTRIBUTING.md`, `.github/workflows/ci.yml`: 사용 경로·설정 안내.

---

### 작업 1: 모델 URL 계약과 ACE/개발 진단

**인터페이스:** `ModelSettings.from_env(env: Mapping[str,str] | None) -> ModelSettings`의 반환 필드 `endpoint`, `model`, `api_key`는 유지한다. `AGENT_OPT_MODEL_ENDPOINT`가 있으면 `ConfigurationError`로 즉시 거부한다.

- [ ] `tests/test_models.py`에서 정상 요청의 입력을 `AGENT_OPT_MODEL_BASE_URL=url+'/v1'`로 바꾸고 `/v1/chat/completions` 도달, localhost 허용, HTTPS 검사, `AGENT_OPT_MODEL_ENDPOINT` 단독/중복 입력의 명시적 이전 안내와 토큰 비노출을 실패 테스트로 추가한다.
- [ ] `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_models.py -v`에서 새 계약의 실패를 확인한다.
- [ ] `models.py`의 Settings에서 `endpoint` 입력을 제거하고 `base_url` 필수 여부, 기존 URL 검사, 위 `legacy` 거부, 표준 URL 조립을 구현한다. 예: `if env.get('AGENT_OPT_MODEL_ENDPOINT'): raise ConfigurationError('AGENT_OPT_MODEL_ENDPOINT 대신 AGENT_OPT_MODEL_BASE_URL을 사용하세요')`; 결과 DTO의 `endpoint`는 그대로 사용한다.
- [ ] ACE의 모델 `env_passthrough` 두 위치, 진단 문구, 개발 메뉴 URL 모드 선택을 BASE_URL 하나로 바꾸고 관련 테스트/endpoint-plugin fixture를 표준 경로로 갱신한다. 메뉴의 ID·비밀 토큰은 기존의 원자적 입력/숨김 동작을 유지한다.
- [ ] 관련 `test_models.py`, `test_menu.py`, `test_dev_environment.py`, `test_demo_environment.py`, `test_dev_doctor.py`, `tests/endpoint-plugin.test.mjs`를 실행하고 통과를 확인한다. 이 기능을 별도 커밋한다.

### 작업 2: 중복 공개 CLI와 내부 argv

**인터페이스:** `init --command '<quoted argv>'`만 받으며 wizard는 `shlex.join(command)`을 전달한다. `plan`은 유지, `validate`와 인수 없는 `doctor`는 명확히 사용 오류로 처리한다.

- [ ] `tests/test_cli_experience.py`에 `main(['validate', ...])` 거부, `main(['doctor'])`의 `--plan`/`--dataset` 안내, wizard의 공백/따옴표 포함 argv 왕복, `--command-json` 거부를 실패 테스트로 적는다.
- [ ] `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -v`에서 새 동작의 실패를 확인한다.
- [ ] `cli.py`에서 `validate` 등록·분기와 `--command-json` 인자/분기를 제거하고 `setup_wizard.py`의 `wizard_arguments()`는 `['--command', shlex.join(command)]`을 사용한다. `doctor`의 dataset/plan 없는 분기는 `ConfigurationError('agent-opt doctor --plan PATH 또는 --dataset ID를 지정하세요')`를 반환한다. `--command`는 기존 `shlex.split()`·argv 검증을 유지한다.
- [ ] 공개 호출을 쓰는 활성 테스트를 `--command`로 갱신하고 인용/argv 분리의 결과가 이전과 동일한지 검증한다. `plan`의 계산/출력 및 명시적 doctor는 계속 검증한다. 관련 테스트 통과 후 별도 커밋한다.

### 작업 3: 앱 TUI의 세션 모델 입력

**인터페이스:** `model_input.ensure_model_api(env: dict[str,str]) -> dict[str,str]`, `model_input.ensure_model_selector(env: dict[str,str], key: str) -> dict[str,str]`, `model_input.session_environment(env: dict[str,str])` context manager. 반환값은 새 매핑이며 취소·입력 오류에서는 원본 환경을 변경하지 않는다. ACE 전용 하네스의 선언된 `runtime.env_passthrough`에는 URL·키가 모두 있어 모델 API 입력 필요성을 판정한다.

- [ ] `tests/test_cli_experience.py`의 ACE 기존 실험/TUI 3번 및 일반 연구·OpenCode 실험에 대해 누락된 값만 묻고 토큰을 출력하지 않는 테스트, 취소 시 실행 없음, 종료 뒤 원래 환경 복구, 이미 값이 있으면 추가 프롬프트 없음, 비TTY `run`에서는 입력 요구 없이 환경 부족 오류를 유지하는 테스트를 작성한다.
- [ ] 새 TUI 회귀가 실패하는지 `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -v`로 확인한다.
- [ ] `model_input.py`에 `getpass.getpass`와 `GetPassWarning` 거부, `ModelSettings.from_env()` 검증, 부족한 URL·키·선택자만 질문하는 함수와 `try/finally` 환경 복구를 구현한다. 예: `staged = dict(env); staged['AGENT_OPT_MODEL_BASE_URL'] = input('AGENT_OPT_MODEL_BASE_URL: ').strip()`; `session_environment`는 기존 관련 변수를 복원한다.
- [ ] TUI의 `collect_plan()` 전에 선택된 optimizer의 API 요구/하네스 `model_env`/전용 하네스가 선언한 URL·키 전달을 판정해 세션 입력을 적용한다. 일반 `opencode`가 선택적으로 전달하는 API 키는 강제하지 않는다. 승인 전 플러그인을 import하지 않고 ACE 전용 다운로드·채점 로직은 예제 launcher에 둔다. 기존 확인/취소·JSON stdout·오류 코드는 보존한다.
- [ ] TUI/메뉴/ACE CLI 회귀를 통과시키고 비밀 값이 stdout/stderr/실험 파일에 나오지 않는지 확인한다. 기능을 별도 커밋한다.

### 작업 4: 사용자/개발 문서와 최종 검증

- [ ] 현재 README·앱 가이드·CLI 도움말의 첫 ACE E2E 경로를 `agent-opt tui`와 설치형 `init`→`prepare`→`run`으로 맞추고 개발용 `make`/bootstrap 단계는 분리 표기한다. `.env.example`은 BASE_URL만 예시하고 로딩 시 `set -a; source .env; set +a`를 안내한다. `--command-json`, `validate`, 인수 없는 doctor 및 이중 URL 선택을 현재 문서/도움말/CI의 사용 경로에서 제거한다.
- [ ] `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`, `make lint`, `make demo`, `node --test tests/endpoint-plugin.test.mjs`, `.venv/bin/python -m build`, `git diff --check`를 실행한다. 설치 wheel CLI 검사와 Docker/CVDP 가능 여부는 `CONTRIBUTING.md` 순서대로 확인한다.
- [ ] 모델 키/자산이 준비된 경우에만 공식 평가·실모델 E2E를 실행하고 결과를 분리 기록한다. 없으면 해당 검증의 미실행 상태를 명시한다.
- [ ] CLI/TUI 전·후 캡처와 재현 명령을 PR에 넣고, status/diff/log 확인 후 의도한 파일만 커밋·푸시해 PR을 만든다. 머지는 사용자 승인을 기다린다.
