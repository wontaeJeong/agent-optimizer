# 검증 기록

## 2026-09-25 wheel 독립 실행과 ACE 예제 lifecycle 분리

Mac ARM64 / Python 3.12.12 / Docker daemon `linux/arm64`, 작업 브랜치
`design/unified-execution-flow`. 모델 API endpoint·키는 설정하지 않았다.

| 범위·실제 명령 | 결과 |
|---|---|
| 개발 코어: `make setup-core`; `make test`; `make lint`; `actionlint`; `git diff --check` | 코어 진단 ready, 전체 **547개 중 532 통과·15 skip·실패 0**, lint·워크플로 문법·공백 검사 통과. skip은 호스트 실도구와 선택형 통합 검사이며 합성 결과를 모델 실험으로 세지 않았다. |
| 설치 패키지: `.venv/bin/python -m build`; `.venv/bin/python tests/test_installed_cli.py dist/agent_optimizer-0.3.0-py3-none-any.whl` | 공백이 있는 임시 경로에 wheel 설치 후, 소스 밖에서 `agent-opt` 도움말·선택형 데이터셋 목록·TTY 시작·사용자 로컬 Agent와 지정 평가기의 init/doctor/run/report 완료. 원본 Agent 파일 불변. 실행 스크립트 shebang의 공백 경로 문제를 표준 console entry point로 수정해 재검증했다. |
| ACE 평가 실행환경: `make setup` → `make doctor` → `make smoke`; `PYTHONPATH=src .venv/bin/python -c '...lifecycle.inspect(root)...'` | 고정 소스·데이터·driver·이미지 준비, 공식 CVDP 정답/오답 smoke `runs/dev-smoke-0e3c857a4cb3/summary.json` `passed`, 재배치 가능한 lifecycle 진단 `ready=true`, 24개 검사. Docker layer는 기존 cache를 재사용했다. |
| ACE 모델 진입점: `.venv/bin/agent-opt run examples/ace-rtl/experiment.toml` | shell 재진입 없이 예제 lifecycle로 들어가며 모델 설정 부재로 exit 2. 실제 모델·후보 선택 결과는 이번 변경에서 측정하지 않았다. |

wheel 사용자용 ACE/CVDP 고정 버전 다운로드·작업공간 생성·TUI 확인 준비는 후속 연동
카탈로그 구현이 필요하다. 이 단계의 모의 lifecycle/로컬 모델 없는 검사를 실모델 E2E로
기록하지 않는다.

## 2026-09-25 터미널·리포트 한영 지원

Mac ARM64 / Python 3.12.12의 독립 워크트리에서 확인했다. 저장소 로컬 `.env`의
`AGENT_OPT_MODEL_*` 값은 프로세스 메모리에만 읽어 `ModelSettings.from_env` 유효성을 확인했고,
자격증명을 출력하거나 Git에 추가하지 않았다. 실제 모델 API 호출이나 Docker/CVDP 평가를
새로 검증한 것은 아니다.

| 실제 명령·검사 | 결과 |
|---|---|
| `env -u AGENT_OPT_MODEL_BASE_URL PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q`; `make lint`; `git diff --check` | unittest **558개 중 543 통과·15 skip·실패 0**, Ruff·공백 검사 통과. 기존 테스트가 외부 `AGENT_OPT_MODEL_BASE_URL`을 상속해 발생하는 실패는 [별도 PR #28](https://github.com/wontaeJeong/agent-optimizer/pull/28)로 수정했다. 이 PR에서는 그 환경 변수를 제외하고 전체 테스트를 실행했다. |
| `make setup ARGS="--core --offline"`; `make doctor ARGS="--core --json"`; `make demo` | 캐시 코어 준비·진단 `ready`, 7-trial 합성 데모 `completed`. JSON 키·상태 값과 진단 원문은 영어로 유지했다. |
| `AGENT_OPT_LANG=en make help`; `AGENT_OPT_LANG=en PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml`; `AGENT_OPT_LANG=en .venv/bin/agent-opt report runs/20260925T063337Z-c1bf43dd --html` | 영어 도움말, 7-trial 합성 실행 완료, `report_language=en` 기록과 `report.html` 영어 재생성 확인. 기본 한국어 HTML과 영어 HTML의 1440px 캡처: `docs/superpowers/terminal-language-before-1440.png`, `terminal-language-after-1440.png`. 실제 모델 성능 근거는 아니다. |
| 최신 `origin/main`과 PR #28 병합 내용 반영 후 `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q`; `make lint`; `sh -n scripts/bootstrap.sh` | 외부 모델 환경 변수를 유지한 채 **575개 중 560 통과·15 skip·실패 0**, Ruff·셸 문법 통과. 새 CLI/TUI의 기존 실험 선택·하네스별 명령 입력과 영어 도움말 경로를 함께 검증했다. |

CI의 좁은 터미널에서는 Rich가 `--command`를 `--comm…`으로 줄이고 ANSI 색상 코드가
단어 사이에 들어갔다. `COLUMNS=40 FORCE_COLOR=1`로 재현했고, 영어 도움말 테스트는
ANSI·줄바꿈·표 경계를 정규화해 설명 문구를 검증한다.
이 변경은 CLI 옵션 이름이나 기계 출력 형식을 바꾸지 않는다.

## 2026-09-25 개발 명령·CLI 온보딩과 ACE 실행환경 분리

Mac ARM64 / Python 3.12.12 / Docker daemon `linux/arm64`, 작업 워크트리
`chore/setup-cli-syntax`. 실제 모델 환경변수·자격증명은 설정되지 않았다. 첫 `make setup`은
이미 존재하는 Docker layer를 재사용했으며 냉간 이미지 빌드 검증은 아니다.

| 단계·실제 명령 | 결과·범위 |
|---|---|
| 개발환경: `make setup-core`, `make doctor-core`, `make help`; `PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml` | 코어 진단 ready, 간편 Make 별칭의 실제 실행 및 API-free 합성 데모 7 trial completed. ACE 평가·모델 검증과 별개다. |
| 계약: `make test`; `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -q`; `make lint`; `actionlint`; `.venv-docs/bin/mkdocs build --strict`; `git diff --check` | 최신 `origin/main`의 HTML 리포트 변경을 반영한 뒤 전체 **541개 중 526 통과·15 skip·실패 0**, CLI 회귀 **77개 통과**. Ruff·워크플로 문법·가이드 엄격 빌드·공백 검사 통과. skip에는 호스트 Yosys/Icarus 9개와 선택형 Docker 네트워크 검사가 포함된다. TUI/CLI ACE 선택은 임시 bootstrap fixture로 argv·cwd·종료 코드 전달을 검증했다. |
| ACE 평가 실행환경: `make setup` → `make doctor` → `sh scripts/bootstrap.sh setup --offline` → `make smoke` | 고정 Git/데이터/driver/이미지 확인 후 `evaluation=ready`, `live=not ready`. `runs/dev-smoke-f6448875345d/summary.json`은 `passed`: 이미지 내 실제 도구 9개, host-Docker toy 정답/오답/조기 종료, 공식 CVDP raw test 각 1개에서 정답 `passed=1`·오답 `passed=0`. 모델 호출 없음. |
| ACE 정적 계획: `.venv/bin/agent-opt doctor --plan examples/ace-rtl/experiment.toml --json` | 기존 실험 파일의 중복 CVDP evaluator 등록을 제거한 뒤 `scope=plan`, `ready=true`. 이는 실모델 호출이나 공식 평가 실행 결과가 아니다. |
| ACE 실행 진입점: `.venv/bin/agent-opt run examples/ace-rtl/experiment.toml`; pseudo-TTY에서 `.venv/bin/agent-opt tui` → `1` → `examples/ace-rtl/experiment.toml` → `y` | 둘 다 예제 `live` 경로에 도달하여 `status=blocked`, `stage=live`, 종료 코드 2를 유지. 모델 endpoint/키가 없는 환경이라 실제 모델·Agent 후보 최적화는 실행되지 않았다. |

실제 모델→ACE 스킬 프로필→CVDP→후보 선택 결과는 현재 작업에서 새로 생성하지 않았다.
이전 E2E 기록은 당시 모델·설정의 근거이며 이번 CLI/TUI 변경의 실모델 성공 근거로 재사용하지 않는다.

## 2026-09-25 장시간 명령 진행 표시 전수 보완

Mac ARM64 / Python 3.12.12 / Docker daemon `linux/arm64`. 모델 키를 사용하지 않았다.
`make live`의 원인은 ACE 예제의 `run_experiment`에 `on_event`를 전달하지 않은 것이었다.
기본 디렉토리에서 이미 실행 중이던 두 작업의 `events.jsonl`에 `agent_started`가 기록된 상태를
확인했으며 해당 프로세스는 중단·수정하지 않았다. CLI `run`·TUI·선택 데이터셋 준비·`make demo`는
기존 이벤트/상태 표시 경로가 연결됐음을 코드와 회귀로 구분해 확인했다.

| 실제 명령·검사 | 결과 |
|---|---|
| `make setup ARGS="--core"`; `make setup` | 둘 다 exit 0, 각 7-trial 합성 데모 completed. 새 워크트리에서 고정 Git·데이터·driver를 준비하고 Mac `linux/arm64` 공식 이미지·도구 진단 ready. 이미지 빌드는 기존 Docker layer cache를 사용했으므로 cold build 근거가 아니다. |
| `make smoke` | `runs/dev-smoke-dc1f6e8a5dc7/summary.json`: `status=passed`, 실제 도구 9개·toy 정답/오답·공식 CVDP 정답/오답 검사를 실행. stderr에 환경 확인부터 `official-negative`까지 시작·경과·완료 상태가 나왔고 마지막 stdout은 단일 결과 JSON이었다. |
| `make test`; `make lint`; `node --test tests/endpoint-plugin.test.mjs`; `sh -n scripts/bootstrap.sh`; `git diff --check` | unittest **525개 중 510 통과·15 skip·실패 0**, Ruff·Node 1개·셸 문법·공백 검사 통과. TTY 지연 fixture는 작업 종료 전 `elapsed=` 표시를, 직접 Python doctor `-S`는 Rich 미설치 경로와 JSON stdout 분리를 확인했다. |

실제 모델을 호출하는 새 `make live`는 이번 작업에서 실행하지 않았다. 합성 이벤트로 대기 중
단계가 표시되는지 검증했고, 평가기 성능·모델 개선 여부는 기존 E2E 기록과 구분한다.

## 2026-09-25 공식 CVDP 평가 재실행

환경: GitHub 제공 Ubuntu `linux/amd64`, Python 3.12.14, Docker 28.0.4,
Compose v2.38.2. 모델 자격증명은 사용하지 않았다. 이전 [수동 실행의 패키지 404](https://github.com/wontaeJeong/agent-optimizer/actions/runs/36030202137)를
조사할 때 `libexpat1`·`libexpat1-dev`의 동일 버전 URL이 다시 HTTP 200을 반환했다.
고정 upstream Dockerfile·source commit·데이터 hash·평가기를 수정하지 않았다.

| 실제 명령/근거 | 결과 |
|---|---|
| `gh workflow run ci.yml --ref main -f official_cvdp=true` — [실행 36034478872](https://github.com/wontaeJeong/agent-optimizer/actions/runs/36034478872) | apt 단계는 통과했고 artifact의 빌드 로그에서 Yosys 컴파일 31%까지 확인. 이후 새로운 `main` push로 workflow concurrency가 이 실행을 취소했으므로 평가 성공 증거는 아니다. |
| `gh workflow run ci.yml --ref fix/cvdp-official-evaluation -f official_cvdp=true` — [실행 36035257600](https://github.com/wontaeJeong/agent-optimizer/actions/runs/36035257600), HEAD `b8bbfaf403b9e88a93d71f34fc3a49230e23b216` | 모델 키 없는 **수동 공식 Docker job 통과**(19분 23초). `make setup`, `make doctor`, `make setup ARGS="--offline"`, `make smoke`, 이미지 설정/endpoint 도구 검사 모두 성공. Python 3.11·3.12 코어 job도 통과. |
| 실행 artifact `official-cvdp-36035257600`의 `external/environment-lock.json`, `external/setup-logs/doctor.json` | 고정 ACE `fead921f18bb57345b5a41ef93ba625be208e99c`·CVDP `8e894cf74414ab1eaea1e2b4e80a02f123df07b6`, HF `5b807d945f6a99aa645f7e43a64a2115e281b4bf`와 검증된 세 데이터 파일 hash를 기록. `doctor.ready=true`, Yosys 0.40·Icarus/vvp 13.0·OpenCode 1.18.31 실행. |
| `runs/dev-smoke-22416bc0458f/summary.json`, `real-tool-tests/stderr.log`, `cvdp-positive`·`cvdp-negative`의 공식 `raw_result.json` | smoke `status=passed`, RTL 실도구 테스트 **9/9** 통과. 호스트 Docker toy 정답 1·오답 0·조기종료 0. 공식 LFSR `cvdp_copilot_lfsr_0001`에 비어 있지 않은 raw test 각 1개: 의도한 정답 `result=0`/`passed=1`, 오답 `result=1`/`passed=0`. |
| `gh workflow run ci.yml --ref fix/cvdp-official-evaluation -f official_cvdp=true` — [최신 코드 재실행 36038288690](https://github.com/wontaeJeong/agent-optimizer/actions/runs/36038288690), HEAD `10a3ba0ebc02c061dec491c79c1167192f96c4cf` | 이후 반영된 설정·CLI·평가기 변경을 포함해 Python 3.11/3.12 CI와 수동 공식 Docker job **전부 통과**(Docker 15분 8초). `make setup`→`make doctor`→`setup --offline`→`make smoke`→이미지·endpoint 검사 각 단계 통과. |
| 재실행 artifact `official-cvdp-36038288690`의 `runs/dev-smoke-e35ac77a5d36/summary.json`, `real-tool-tests/stderr.log`, 공식 정답·오답 `raw_result.json` | smoke `status=passed`, RTL 실도구 **9/9**. 호스트 Docker toy 정답 1·오답/조기종료 0. 같은 고정 공식 LFSR의 raw test 각 1개에서 정답 `result=0`/`passed=1`, 오답 `result=1`/`passed=0`; `error_msg=null`. `doctor.ready=true`, source commit과 데이터 hash 유지. |

이는 **한 문제의 공식 채점기 정답·오답 및 실행 환경 검증**이다. 전체 CVDP 데이터셋의
성능이나 ACE/OpenCode의 배포 모델 추론·최적화 효과를 검증한 것은 아니다. 첫 404는
외부 Ubuntu 패키지 제공 상태가 회복된 뒤 같은 고정 빌드에서 재현되지 않았다.

## 2026-09-25 ACE-RTL 스킬 프로필 실제 모델 E2E

Mac ARM64 / Docker daemon `linux/arm64`, Python 3.12.12, OpenCode 1.18.31,
DeepSeek OpenAI 호환 API `deepseek-flash`. 실행 기록의 run ID와 타임스탬프는 UTC 2026-09-24다.
인증정보는 실행 프로세스 환경에만 전달했고, 이 문서와 저장소 설정에는 남기지 않았다.

| 실제 명령 | 결과 |
|---|---|
| `make setup ARGS="--core"`; `make doctor ARGS="--core --json"` | 코어 ready, 합성 최소 데모 completed / 7 trial. |
| 초기 `make setup`; `make doctor ARGS="--json"` (당시 `MODEL_*` 설정) | 고정 ACE/CVDP 소스·HF 데이터·Python driver·Docker 이미지 및 실도구 진단 ready. 평가 이미지의 upstream `apt` 설치를 포함한 Docker 단계는 **기존 layer cache 사용** (`external/setup-logs/evaluation-build.log`), cold build 성공 근거가 아니다. |
| `make smoke` | `runs/dev-smoke-c78e5ca64e4e/summary.json`: 실제 도구 9개 실행, toy 정답/오답/조기종료, 공식 CVDP LFSR 정답 1/1·오답 0/1, nonempty raw tests 확인 후 `passed`. |
| 최초 `make doctor ARGS="--model --json"` | `live.execution` 오류. 호스트 `probe_model()`을 분리 재현해 DeepSeek 기본 thinking 모드가 강제 `tool_choice`에 HTTP 400 (`Thinking mode does not support this tool_choice`)을 반환하는 것을 확인했다. 단순 completion은 HTTP 200, `tool_choice="auto"`에서는 실제 `connectivity_check` tool-call을 반환했다. |
| 강제 `tool_choice` 제거 및 관련 회귀 후 `make doctor ARGS="--model --json"` | `model_status=passed`: 실제 호스트 API의 tool-call과 Docker OpenCode의 도구 실행 모두 통과. 유효한 tool-call 이름·인수의 검증은 유지. |
| `make live ARGS="--iterations 1"` | **실제 모델·Agent·공식 평가**, `runs/dev-live/20260924T173749Z-e3d4be03/summary.json`: `synthetic=false`, `completed`, 4 trial 모두 `valid=true`·공식 CVDP 1/1 통과. baseline/후보 train 및 validation을 평가하고 `report.html`, `events.jsonl`, 후보 diff 생성. validation solve_rate는 둘 다 1.0, 비교 지표 seconds가 baseline 120.99 < 후보 126.28이므로 baseline `c0001` 선택. 최종 test는 설정상 실행하지 않았다. 최적화 성능 향상 증거가 아니다. |
| `make lint`; `make test`; `make demo`; `node --test tests/endpoint-plugin.test.mjs` | Ruff 통과, unittest **449개 중 434 통과·15 skip·실패 0**, 합성 7 trial completed, endpoint plugin 1개 통과. skip은 호스트 RTL 도구 9개, 선택적 Docker 네트워크 2개 등을 포함하며 `make smoke`에서 실제 이미지 도구 9개를 별도로 검증했다. |
| 최신 `origin/main`의 접두어 설정 변경 통합 후 `make setup ARGS="--core"`; `make setup`; `make doctor ARGS="--model --json"` (`AGENT_OPT_MODEL_*` 설정) | 최초 `--model`은 호스트 probe만 통과하고 컨테이너가 `UnknownError`를 반환했다. 기존 이미지 플러그인이 이전 `MODEL_*`을 읽는 것을 확인한 뒤, 전체 setup에서 변경된 파일을 `COPY`해 Agent 이미지를 재생성했고 host API·Docker 도구 실행 모두 `passed`. 코어 7 trial도 재확인. |
| 최신 소스로 `make live ARGS="--iterations 1"` (`AGENT_OPT_MODEL_*` 설정) | `runs/dev-live/20260924T175255Z-c4dcfafe/summary.json`: `synthetic=false`, `completed`, 4 trial 모두 공식 평가 1/1·`valid=true`; `report.html` 생성. validation 둘 다 solve_rate 1.0, baseline 78.39초·후보 180.32초여서 `c0001` 선택. 같은 두 과제·1회 수정 범위이며 최종 test 없음. |
| 접두어 설정 통합 후 `make lint`; `make test`; `make smoke`; `node --test tests/endpoint-plugin.test.mjs` | Ruff 통과, unittest **454개 중 439 통과·15 skip·실패 0**, `runs/dev-smoke-07eaaf1eace3/summary.json` passed, Node 1개 통과. doctor 실패 조치에 남아 있던 이전 `MODEL_*` 표기를 회귀로 재현한 뒤 `AGENT_OPT_MODEL_*`으로 수정했다. |
| 이후 `origin/main`의 보고서 변경(`160b570`)과 통합해 `make lint`; `make test`; `make demo`; `make live ARGS="--iterations 1"` (`AGENT_OPT_MODEL_*` 설정) | Ruff 통과, unittest **516개 중 501 통과·15 skip·실패 0**, 합성 7 trial completed. 새 보고서 경로의 실제 E2E `runs/dev-live/20260925T014552Z-8a0269e1/summary.json`은 `synthetic=false`, 4 trial completed·valid·공식 평가 1/1, `report.html` 생성. validation 두 후보 1.0 동점에서 baseline 194.45초·후보 259.36초로 `c0001` 선택, `run_wall_time_seconds=549.07`. 최종 test는 실행하지 않았다. |

이번 모델 검증은 고정 프로필의 **두 과제·1회 수정**에 한정된다. upstream native ACE runner,
전체 CVDP/Verilog-Eval, Ubuntu x86_64에서 이 모델 E2E와 DeepSeek 이외 모델은 확인하지 않았다.
이 작업의 Mac 빌드는 캐시를 사용했지만, 위의 별도 Ubuntu 수동 공식 CI에서는 과거 `apt` 404가
재현되지 않았고 공식 채점기 smoke까지 통과했다. 이 PR의 수동 공식 Docker job은 실행하지 않았다.

## 2026-09-25 사용자 설정·전송 경로·CI 재검증

Mac ARM64 / Python 3.12.12 / Docker CLI 29.2.1. 아래 명령은 작업 중 실행했으며
`origin/main`의 도움말 변경을 재배치한 뒤 전체 테스트·lint·Node 검사를 다시 실행했다.
모델 자격증명은 사용하지 않았다. 이 환경에는 Docker
Buildx와 호스트 Yosys/Icarus/vvp가 없다.

| 실제 명령/실행 | 결과 |
|---|---|
| `make setup ARGS="--core"`; `make doctor ARGS="--core --json"` | 코어 환경 준비·진단 ready, 합성 데모 completed. 전체 ACE 준비 상태는 아님. |
| `make test`; `make lint`; `actionlint`; `node --test tests/endpoint-plugin.test.mjs` | 재배치 후 전체 **433개 중 418 통과·15 skip·실패 0**, Ruff/워크플로 문법/Node 1개 통과. skip에는 호스트 RTL 도구 9개, 선택형 Docker 네트워크 2개 등이 포함된다. |
| 아래 `audit-fixed-flow` 사용자 CLI 명령 | 합성 fixture에서 모두 성공. validation·test baseline 0 → 선택 후보 1, 4 trial, `runs/20260924T162700Z-52a358be/report.html`. 실제 RTL/모델 개선 근거 아님. 복수 데이터셋 실패·출력 실패 시 신규 설정/session 정리도 별도 회귀에서 확인. |
| 임시 로컬 Git에 `GIT_CONFIG_COUNT`/`url.*.insteadOf` 적용 후 고정 Git Agent 스냅샷 테스트 | 공개 형식 URL을 로컬 저장소로 재작성해도 요청 SHA와 확보 SHA가 일치하며 잘못된 SHA는 거부. 실제 별도 서버 접속 검증은 아님. |
| `.venv/bin/python -m build`; 독립 venv에 wheel offline 설치 후 `python -I -m agent_optimizer --help`, `agent-opt --help` | sdist/wheel 생성 및 독립 설치 CLI 확인. |
| [PR #15](https://github.com/wontaeJeong/agent-optimizer/pull/15) 기본 CI [실행](https://github.com/wontaeJeong/agent-optimizer/actions/runs/36029966596) | Ubuntu Python 3.11·3.12 모두 통과. 공식 Docker job은 수동 입력이 없어 skip. |
| `gh workflow run ci.yml --ref audit/readiness-2026-09-25 -f official_cvdp=true`; `gh run rerun 36030202137 --failed` — [실행/로그](https://github.com/wontaeJeong/agent-optimizer/actions/runs/36030202137) | 고정 Git 소스·HF 데이터 hash·driver 준비는 완료. 공식 CVDP 평가 이미지의 upstream Dockerfile `apt-get update && apt-get install`에서 Ubuntu 보안 저장소 `libexpat1`/`libexpat1-dev` 지정 버전 다운로드가 **두 번 모두 404**로 실패했다. 따라서 image/doctor/offline/smoke/정답·오답 평가는 시작하지 못했다. build 로그는 해당 실행의 `official-cvdp-36030202137` artifact (재실행 ID `10821431486`)에 있다. |

`audit-fixed-flow`의 명시적 데이터셋/평가기/Optimizer 설정과 보고서 재생성 명령:

```bash
.venv/bin/agent-opt init --name audit-fixed-flow --agent examples/minimal/agents/solo \
  --argv '{python}' '{agent_dir}/src/fixture_agent.py' '{task_dir}' \
  --editable configs/strategy.json --dataset examples/minimal/tasks.json \
  --evaluator examples/minimal/evaluator.py:TextFixtureEvaluator \
  --optimizer file_variants \
  --optimizer-config '{"file_variants":{"include_seeds":true,"variants":[{"name":"enable-repair","files":{"configs/strategy.json":"{\"repair\": true}"}}]}}' --yes
.venv/bin/agent-opt doctor --plan runs/configs/audit-fixed-flow/experiment.toml --json
.venv/bin/agent-opt run runs/configs/audit-fixed-flow/experiment.toml
.venv/bin/agent-opt report runs/20260924T162700Z-52a358be --html
```

공식 CI의 404는 upstream Dockerfile이나 고정 버전을 수정해 통과시키지 않았다.
실제 모델→ACE/OpenCode→평가의 end-to-end, 자체 러너와 추가 CA를 넣은 BuildKit 이미지
통합은 아직 검증되지 않았다. `UV_DEFAULT_INDEX`만으로 기존 `uv.lock`의 공개 절대 URL이
변경되지 않으므로 대체 package index도 실제 환경과 검토된 lock/cache로 별도 확인해야 한다.

## 2026-09-24 PR #12 whole-branch review fixes

Mac ARM64 / Python 3.12.12 / Docker `linux/arm64`. 기존 고정 source·image·데이터 캐시를 사용하고,
새 Verilog build lock과 CVDP imported tasks digest는 선택 dataset 온라인 prepare로 생성했다.
완전 신규 checkout의 cold build, 배포 모델 inference·성능, 이번 변경의 Ubuntu x86_64 실행은 검증하지 않았다.

| 실제 명령 | 결과 |
|---|---|
| `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -v`; 동일한 `-p test_datasets.py`, `-p test_dev_environment.py`, `-p test_progress.py` | 각각 51, 21, 43, 10개 통과. pin 선언, build lock, CVDP manifest, 진행 표시, CLI bytecode 회귀 포함. |
| `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` | **421개: 406 통과·15 skip·실패 0 (50.601초)**. 기존 host 도구/선택 도구 skip은 아래 Task 5 기록과 동일한 범위. |
| `make lint`; `.venv/bin/python -m build`; 신규 wheel을 독립 `runs/review-wheel-venv`에 offline 설치 후 `env -u PYTHONPATH runs/review-wheel-venv/bin/agent-opt --help` | Ruff 통과, sdist/wheel 생성, 새 CLI executable 실행 성공. |
| `PYTHONPATH=src .venv/bin/python -m agent_optimizer datasets prepare verilog-spec --project-root .`; 동일한 `cvdp` | 둘 다 exit 0. 준비된 pinned Git/HF Docker cache를 사용해 Verilog v12 고정 Dockerfile 이미지 ID lock, CVDP 공개 tasks digest lock 기록. 기존 캐시의 online 재검증이며 cold build 증거가 아니다. |
| `PYTHONPATH=src .venv/bin/python -m agent_optimizer doctor --dataset verilog-spec --json`; 동일한 `cvdp` | 둘 다 exit 0/ready; 각각 4개, 10개 read-only 검사 ok. `env -u PYTHONPATH runs/review-wheel-venv/bin/agent-opt doctor --dataset verilog-spec --json`도 exit 0. |
| `AGENT_OPT_TEST_VERILOG_EVAL_ROOT=external/verilog-eval/source/c498220d0a52248f8e3fdffe279075215bde2da6 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_verilog_live.py -v`; `make smoke` | 실제 Docker Icarus v12 private testbench의 작은 정답/오답 fixture 1/1 통과; 기존 공식 CVDP 평가 smoke `status=passed` (`runs/dev-smoke-e7d40c35c659/`). 전체 benchmark나 모델 최적화 아님. |

`agent-opt doctor` 실행 스크립트는 프로젝트 import 이전에 bytecode를 막고, direct `main([...])`도
Registry 생성 전에 막는다. 별도 `python -m agent_optimizer doctor`는 CPython이 package initializer를
실행하기 전에 그 파일의 `.pyc`를 생성할 수 있으므로 fresh source의 bytecode-free 진입 경로로
주장하지 않는다. 자세한 RED/GREEN 결과와 남은 범위는 `.superpowers/sdd/2026-09-24-central-registry-readiness/final-review-fix-report.md`.

## 2026-09-24 central registration and selected readiness (Task 5)

환경: Mac ARM64, 이 작업 worktree의 `.venv` Python 3.12.12, Docker daemon `linux/arm64`.
아래 준비된 `external/` 자산은 이 worktree에 이미 존재했다. 다른 환경/새 checkout의 준비 성공을
의미하지 않는다. 이번 검사는 모델 API 키 없이 수행했다.

| 실제 명령 | 결과 |
|---|---|
| `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_plugin_contracts.py -v` | 18/18 통과. |
| `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v` | 당시 실행 410개, 395 통과·15 skip, 실패 0 (49.757초). **최신 전체 결과는 위 421개/406 통과/15 skip.** skip: 호스트 Yosys/Icarus/vvp 9, 선택적 네트워크 Docker 2, driver/YAML 2, OpenCode Docker 이미지 지정 1, v12 고정 checkout 환경 변수 1. v12은 아래 명시적 명령에서 실행. |
| `PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml` | completed, **합성 fixture** 7 trials, `runs/20260924T015541Z-8e8d23cd/report.html`. 실제 Agent·모델 성능 아님. |
| `make lint`; `.venv/bin/python -m build`; `git diff --check` | Ruff `All checks passed!`, sdist/wheel 생성 성공, diff 공백 검사 통과. wheel 설치/Ubuntu CI는 이번 검증에 포함하지 않음. |
| `.venv/bin/agent-opt --help`, `.venv/bin/agent-opt doctor --help`, `.venv/bin/agent-opt init --help`; `.venv/bin/python scripts/dev.py setup --help`, `.venv/bin/python scripts/dev.py doctor --help`; `.venv/bin/agent-opt datasets list` | exit 0. 중앙 ID `cvdp`, `verilog-spec`, `verilog-completion`, `sample_text` 표시; setup/doctor의 core/dataset/full 및 `--model` 선택 문구 확인. |
| `.venv/bin/agent-opt doctor --plan examples/minimal/experiment.toml --json` | exit 0, `scope=plan`, `ready=true`, 14개 정적 체크 ok. Agent/평가기 실행·모델 호출 없음. |
| [adding-components](adding-components.md)의 `.venv/bin/agent-opt init --name team-wiring --agent examples/minimal/agents/solo --argv '{python}' '{agent_dir}/src/fixture_agent.py' '{task_dir}' --editable configs/strategy.json --dataset sample_text --harness sample_command --optimizer sample_baseline --yes` → `.venv/bin/agent-opt doctor --dataset sample_text --json` → `.venv/bin/agent-opt doctor --plan runs/configs/team-wiring/experiment.toml --json` → `.venv/bin/agent-opt run runs/configs/team-wiring/experiment.toml` | 네 명령 모두 exit 0, dataset/plan ready, **합성 fixture** run completed / 2 trials (`runs/20260924T020116Z-d13274b1/`). 실제 팀 provider나 배포 모델 검증이 아님. |
| `make doctor ARGS="--dataset verilog-spec --json"`; `.venv/bin/agent-opt doctor --dataset cvdp --json` | 둘 다 exit 0, dataset ready. 앞 명령은 core 10+v12 고정 소스/manifest/image 4개 ok; 뒤 명령은 CVDP 평가 lock/소스/HF 3파일/driver/image 9개 ok. 사전에 준비된 Docker image/checkout에 대한 읽기 전용 검사. |
| `.venv/bin/agent-opt doctor --dataset verilog-completion --json` | **예상 exit 2**, `ready=false` 및 해당 모드의 준비 cache 없음(출처/소스/tasks/v12 image 4개 error). `agent-opt datasets prepare verilog-completion`이 복구 안내. `verilog-spec` 성공을 다른 모드에 소급 적용하지 않음. |
| `make doctor ARGS="--core --json"`; `make doctor ARGS="--json"` | 모두 exit 0. core는 10개 core check ok만 표시. 전체 ACE는 `core=true`, `evaluation=true`, `live=false`; live.key/live.model 설정 없음. full ACE와 dataset-only ready는 별개의 범위. |
| `make setup ARGS="--dataset cvdp --offline"` | exit 0, 검증된 캐시 재사용 및 선택 평가 자산 진단 ready. 별도 dataset evaluation lock; 이 명령은 ACE Agent 이미지 검증/빌드·모델 호출을 하지 않음. |
| `AGENT_OPT_TEST_VERILOG_EVAL_ROOT=external/verilog-eval/source/c498220d0a52248f8e3fdffe279075215bde2da6 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_verilog_live.py -v` | 1/1 통과: 고정 v12 Docker + private testbench의 작은 정답/오답 fixture. 전체 문제 평가 아님. |
| `make smoke` | exit 0, 기존 공식 CVDP/RTL 평가 smoke `status=passed`, `runs/dev-smoke-af0049ef4ed4/`; evaluator/tool 검사이며 모델 최적화 아님. |

HTML에 제거된 `extensions_sha256:null`이 노출되던 문제와 중앙 provider가 evaluator 파일 참조를
ID로 변환하던 문제를 재현 테스트 RED→GREEN으로 수정했다. 사용자 제공 tasks.json의 명시적
`--evaluator file.py:Symbol`은 계속 허용한다. 기존 전체 ACE의 두 소스/두 이미지 검증은
실제 `prepare_sources`를 실행하는 fixture에서 소스별 git 조회를 확인하도록 강화했다.
실제 배포 모델 호출·연구 알고리즘 end-to-end 성능, Verilog-Eval 전체 과제 및 **이번 변경의**
Ubuntu x86_64 실행/CI는 미검증이다. 과거 날짜별 기록은 당시 결과로 보존한다.

## 2026-09-24 CLI TUI and research method integration

개발 환경: Mac ARM64, 프로젝트 `.venv` Python 3.12.12 / 시스템 Python 3.14.5,
Docker daemon `linux/arm64`; `make setup ARGS="--core"`로 별도 `.venv`를 준비했다.
외부 배포 모델 자격증명은 사용하지 않았다. 아래 실행은 새 CLI/TUI·자체
알고리즘·고정 Verilog-Eval 소스의 **서로 다른 검증 수준**이며, 성능 향상 근거가 아니다.

| 실제 명령/검사 | 결과 |
|---|---|
| `make setup ARGS="--core"` | frozen Python 도구 준비 → core doctor ready → 두 합성 Agent·7 trial demo completed. `report.html` 및 원본 보존. |
| `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v` | 전체 364개: 349 통과·15 skip·실패 0 (46.773초). skip은 호스트 Yosys/Icarus 9, 선택적 Docker/driver 5 및 별도 Verilog-Eval 1. Python 3.12에서 Python 3.14와 달리 `Path.glob("configs/**")`가 파일을 반환하지 않는 문제를 재현·수정 후 재검증. |
| `make lint` | All checks passed. |
| `docker build -f Dockerfile.iverilog12 -t agent-opt/iverilog-v12:4fd52916 .` (`examples/benchmarks/`) | 첫 실행에서 upstream `autoconf.sh`의 `gperf` 의존성 누락으로 실패, Dockerfile에 추가해 재빌드 성공. 이미지 `sha256:2f3a2506d13f117b42f4dfb1d95ee8c6d883313dd5ae00288a647226d9523d9d`. |
| `docker run --rm --network none agent-opt/iverilog-v12:4fd52916 iverilog -V` | **Icarus Verilog 12.0 (stable)**. CVDP v13 이미지와 분리 확인. |
| `PYTHONPATH=src python3 -c 'from pathlib import Path; from examples.benchmarks.verilog_eval import Provider; print(Provider().prepare(Path("external/verilog-eval")))'` | 공식 Verilog-Eval `c498220d0a52248f8e3fdffe279075215bde2da6` checkout, `spec-to-rtl` public manifest와 검증된 v12 Docker runtime 설정 출력. 다운로드/캐시는 Git 제외. |
| `.venv/bin/agent-opt datasets prepare verilog-spec` / `.venv/bin/agent-opt datasets prepare cvdp` | 설치 CLI에서 Verilog-Eval 고정 Git/v12 Docker 준비, CVDP pinned 소스·HF no-commercial 3파일 SHA-256 검증·driver venv·공식 평가/Agent 이미지 준비. CVDP 이미지 ID `sha256:ee167c7cd486111a2a807a703ae6bbb30debf2d26f5bb9d0d760ec07c96a58ec`. |
| `.venv/bin/agent-opt init --name cvdp-plan --agent examples/minimal/agents/solo --argv '{python}' '{agent_dir}/src/fixture_agent.py' '{task_dir}' --editable configs/strategy.json --dataset cvdp --optimizer baseline --max-tasks 3 --yes` → `.venv/bin/agent-opt plan runs/configs/cvdp-plan/experiment.toml` | 생성·preflight exit 0, train/validation/test 각 1개 및 공식 평가 이미지 identity 확인. **plan이지 CVDP Agent 최적화 실행은 아님.** |
| `AGENT_OPT_TEST_VERILOG_EVAL_ROOT="external/verilog-eval/source/c498220d0a52248f8e3fdffe279075215bde2da6" PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_verilog_live.py -v` | 실제 v12 Docker에서 고정 `Prob001_zero`의 공식 `_ref` 기반 정답 **passed**, 의도적 오답 **failed**. private testbench는 Agent 공개 파일 밖에서 사용. 1 test / 2 subtests 통과. |
| `make smoke` | 기존 공식 CVDP OSS 평가·host-Docker toy·RTL 도구 smoke passed, 최종 산출물 `runs/dev-smoke-1e5e6c8914a2/`. 새 Agent/model 최적화 성능 근거는 아님. |
| `PYTHONPATH=src python3 -m agent_optimizer run examples/minimal/experiment.toml` | completed, 7 **합성** trial; 이벤트 기반 진행률과 `runs/20260923T171700Z-6f9d14f5/report.html`. 브라우저에서 정적 HTML 레이아웃·표·diff 링크 확인. |
| `.venv/bin/python -m build`, 별도 venv의 wheel 설치 후 `python -I -m agent_optimizer --help` 및 소스 밖 `agent-opt --help` | sdist/wheel 생성·설치 및 명령 목록 통과. |

새 팀 Dataset/Harness/Optimizer 파일 플러그인 복사 경로, CLI/TUI 비TTY 거부·wizard와 세 연구
Optimizer의 모델 응답은 로컬 fixture/모의 completion으로 검증했다. CVDP provider는 기존 고정
importer/평가 환경 준비와 smoke를 실행했지만 **새 실제 Agent/모델 최적화**는 실행하지 않았다.
배포 모델 실제 호출/성능·Verilog-Eval 전체 과제/Ubuntu x86_64 실도구는 미검증이다.

## 2026-09-22 MVP team templates

Task 3 기준 `01dfa62`, `chore/mvp-focus` worktree, macOS ARM64 / 기존 `.venv` Python 3.12.
코어 fixture와 팀 확장 배선을 검증했다. 아래 이전 날짜/작업의 9-trial·Docker·CI 기록은
**당시 증거**이며 현재 minimal은 두 Agent·한 repair stage·7 trial(solo 4/team 3)이다.

| 명령 / 검사 | 실제 결과 |
|---|---|
| `TMPDIR="$PWD/runs" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_plugin_contracts -v` | 기존 baseline 16/16, 신규 Harness 배선 2개 RED(없는 experiment), 배선 추가 후 **18/18 통과**. |
| `env -u AGENT_OPT_TEST_DOCKER_IMAGE -u AGENT_OPT_NETWORK_DOCKER TMPDIR="$PWD/runs" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v` | 전체 suite **한 번**, 297개: **283 통과·14 skip**, 실패 0 (42.178초). |
| `TMPDIR="$PWD/runs" PYTHONDONTWRITEBYTECODE=1 make lint` | All checks passed. |
| `TMPDIR="$PWD/runs" PYTHONDONTWRITEBYTECODE=1 make demo` | completed, 7 synthetic trials, `runs/20260922T011541Z-11452d29/`. |
| `PYTHONDONTWRITEBYTECODE=1 make doctor ARGS="--core --json"` | exit 0, scope=core, ready=true, 10개 검사 ok. |
| `scripts/dev.py setup --help`, `doctor --help`, `agent_optimizer --help`, `make help` (기존 Python 사용) | core 옵션·충돌/전체 경로·현재 CLI 명령을 문서와 대조. 실제 setup/model 호출 아님. |
| 로컬 링크/명령 inspection (`.superpowers/sdd/2026-09-22-mvp-focus/task-3-checks.py`) | 변경/new 문서 17개 링크/anchor 90개 통과. 두 템플릿 plan 통과, 복사 Optimizer에 README Python 예제를 넣어 실제 run/선택=1·복사 plugin hash 확인. customer placeholder는 예상 plan exit 2. minimal 4/3 trial 및 과거 검증 본문 그대로 보존 확인. |
| `git diff --check` | 통과. |

copied Harness 회귀는 템플릿을 `experiments/team-copy/`로 복사하고 세 TOML 참조를 수정한 뒤
**복사본 adapter만** synthetic FixtureHarness 기반 구현으로 교체한다. 실제 subprocess/evaluator를
실행하여 completed, summary/trial의 `team-copy=1`, 복사본 plugin SHA-256 및 Agent 원본 보존을 확인했다.
원본 Harness/Optimizer stub은 exit 2 / UnavailableError와 error summary를 확인한다.
기존 복수 파일 Optimizer·두 Agent 비교 회귀도 유지·통과했다. 테스트 임시 산출물은 정리되며
지속 결과는 위 minimal의 report/summary/events에 남는다.

skip은 호스트 RTL 도구 9, 선택적 Docker 3, PyYAML driver 2개다. 로컬 HTTP fixture는 계약 검증이며
외부 네트워크/실제 모델/전체 Docker/새 Ubuntu CI·패키징 실행은 이번 범위 밖이다.
SOURCES는 현재 소비/보류 경로만 갱신했고 pin과 외부 사실 검증 범위는 바꾸지 않았다.

## 2026-09-22 Iterative demo and environment cleanup

환경: macOS ARM64, 프로젝트/driver Python 3.12.12, uv 0.10.7, Docker 29.2.1
`linux/arm64`, Compose 5.1.3. 실제 배포 모델 자격증명은 사용하지 않았다.
PR 전 `origin/main`의 **21b9e68**(온보딩)을 병합하여 Make/bootstrap·읽기 전용 집계 doctor를
보존하고 모델 실행 검사를 별도 `environment/model_checks.py`로 통합했다.

| 명령 / 검사 | 실제 결과 |
|---|---|
| `python3 scripts/dev.py setup` (병합 전 새 worktree) | 소스·데이터 다운로드, 독립 venv, 기존 Docker layer cache를 사용한 두 이미지 준비 성공. |
| `make setup ARGS="--offline"` (병합 후) | bootstrap frozen sync, pinned source/data/image/driver 재검사, 최종 doctor와 합성 데모까지 성공. |
| `make doctor ARGS="--json"` | exit 0, core/evaluation ready. live 설정은 미준비로 false; API 호출 없음. |
| `make test` (병합 후) | **251개: 237 통과·14 skip**, 실패 0 (33.330초). skip은 호스트 simulator 9, 선택적 Docker provider 1, Docker network 2, PyYAML 2. |
| `make lint`, `node --test tests/endpoint-plugin.test.mjs`, `actionlint .github/workflows/ci.yml`, `shellcheck scripts/bootstrap.sh` | 모두 통과. |
| `make smoke` (병합 후) | **passed**, `runs/dev-smoke-00f6c8068a81/`; 실도구 9/9, host-Docker toy 1/0/0, 공식 LFSR 정답/기능 오답 1/0. |
| 실제 Agent 이미지에서 `python3 /fixture.py` (`tests/opencode_endpoint_fixture.py` readonly mount, network=none) | **passed**, 로컬 API 3회 요청, 정확한 단수형 endpoint·Bearer·모델 override·SSE·bash 실행 후 tool 결과 재전송 확인. 배포 모델 inference가 아닌 통합 fixture. |
| `AGENT_OPT_TEST_DOCKER_IMAGE=agent-optimizer-opencode:1.18.31-arm64 PYTHONPATH=src:tests .venv/bin/python -m unittest test_adapters.DockerEnvironmentTests -v` | 실제 이미지 설정 검사 1/1 통과, `runs/docker-env-regression-aecf52a88cfa/`. |
| `PYTHONPATH=src:tests external/cvdp-venv/bin/python -m unittest test_network.EvaluatorNetworkTests -v` | 5/5 통과. PyYAML wrapper subprocess 포함, 공식 평가 자체와 구분. |
| `uv run --frozen --extra dev python -m build` (병합 전) | sdist/wheel 생성 성공. |
| `PYTHONPATH=src python3 -m agent_optimizer plan examples/ace-rtl/experiment.toml` | train=1, validation=1, simple-feedback 등록 확인. 실환경 성공 판정 아님. |

새 데이터 선택은 priority encoder train과 QAM16 validation이다. trusted evaluator-only 추가 검증에서
공개 명세로 작성한 priority encoder는 1점, compile-negative는 0점, QAM16 compile-negative는
0점이었다. 모두 비어 있지 않은 공식 raw tests를 확인했다. 산출물은
`runs/selected-task-evaluation-83d77b894058/`. 이 입력은 Agent/Optimizer에 전달하지 않았다.
배포 모델의 QAM16 정답 생성이나 실제 최적화 성능을 확인한 것은 아니다.

단순 Optimizer는 로컬 API fixture와 실제 runner로 3회 생성, train 4회·validation 4회,
선택 후 test, 원본 보존·diff·nullable usage를 검증했다. 모델의 잘못된 JSON·허용 밖 변경은
실패하며 성공 후보로 대체하지 않는다. 요청 전체 timeout은 별도 프로세스로 제한한다.
리뷰에서 발견한 trickling body의 socket timeout 초과와 전역 예산 오분류를 먼저 재현한 뒤
수정·회귀 통과를 확인했다. 병합 후 손상 checkout 진단은 upstream의 안전한 Runner로 통합했다.

평가 image ID: `sha256:ee167c7cd486111a2a807a703ae6bbb30debf2d26f5bb9d0d760ec07c96a58ec`.
Agent image ID: `sha256:97682cb16ac85e1653207983f75715caa9665285734f4ad994a1de69d74216a6`.
Yosys 0.40, Icarus/vvp 13.0, Verilator 5.038, OpenCode 1.18.31. 소스·데이터·driver pin 변경 없음.

**미검증:** 실제 배포 endpoint 인증/모델과 ACE end-to-end, 실제 개선 효과, 이번 변경의
proxy 인증·추가 CA를 사용하는 전체 이미지 재빌드, Claude Code/Codex 실행. 확장 템플릿은
미구현 오류를 반환한다. 이전 네트워크 통합과 Ubuntu 검증은 아래 날짜별 근거와 구분한다.
실환경 확인 명령은 `make doctor ARGS="--model"` 후 `make live ARGS="--iterations 3"`이다.

첫 PR Ubuntu run [35624798890](https://github.com/wontaeJeong/agent-optimizer/actions/runs/35624798890)은
자동 시스템 CA가 `make test`까지 전달되어 기존 무설정 fixture의 mount 개수와 offline lock 검사에서
실패했다. bootstrap의 자동 선택을 setup/doctor/smoke/live로 한정하고 core test/lint/demo의
명시적 네트워크 설정만 유지하도록 수정했다. 실제 Linux ARM64 평가 이미지에서 신규 core 명령
CA 비전파 검사와 기존 실패 2개, 총 3개 회귀가 통과했다. 모델/평가 실행의 CA 적용은 유지한다.

### Ubuntu x86_64 최종 재검증

코드 commit **ed4fea4**의 [PR 코어 CI](https://github.com/wontaeJeong/agent-optimizer/actions/runs/35625090539)는
Python 3.11/3.12 모두 성공했다. 이어 [수동 공식 통합](https://github.com/wontaeJeong/agent-optimizer/actions/runs/35625113210)도
코어 두 버전과 공식 Docker job **모두 성공**했다. 공식 job은 18분 45초였다.

- Ubuntu native `linux/amd64`, Docker 28.0.4 / Compose 2.38.2, driver Python 3.12.14.
- 시스템 CA bundle 자동 선택과 BuildKit 적용 빌드 → `make setup` → `make doctor` →
  offline setup → 공식 smoke 성공. CA hash `ecd9dc38bc3efb7dbd6431f57e29d2f8d6a0f0d211e1464b3fef2cbfe266fcd2`.
- `dev-smoke-34a42867db3b`: 실제 도구 9/9, toy 1/0/0, 공식 정답/기능 오답 1/0.
  내려받은 양쪽 `raw_result.json`의 비어 있지 않은 tests와 `result=0/1`을 대조했다.
- OpenCode 설정 검사 1/1 및 실제 Docker+로컬 API fixture의 SSE/tool 실행·후속 요청 3회 통과.
- 평가 이미지 `sha256:421a866b2b29a94c24d6ef0f7d38c3c3e248f64bf6c764d2923329bff2b3257a`,
  Agent 이미지 `sha256:6edea939fbe16f00f81fd89988b6a0162fa27e6c86995b43eae25d32e0afa786`.
- [artifact](https://github.com/wontaeJeong/agent-optimizer/actions/runs/35625113210/artifacts/10652982722)의
  로컬 사본은 Git 제외 경로 `runs/ubuntu-ci-35625113210/`이다.

이 결과는 기본 시스템 CA와 공개 다운로드 환경의 설치·평가 검증이다. 실제 인증 proxy/TLS interception,
배포 모델 API 인증과 실제 ACE 최적화 성능은 위 미검증 범위대로 남아 있다.

## 2026-09-22 Developer onboarding final verification

기존 `4972c8f`의 최종 리뷰 수정(F1–F3)을 보존·검토하고, Mac shell의 watchdog 정리 메시지를
추가 수정한 작업 트리에서 검증했다. macOS ARM64, 프로젝트/driver Python 3.12.12,
기존 Colima Docker 환경과 worktree 소유 자산을 재사용했다. 산출물 UTC 날짜는 2026-09-21이다.

| 실제 명령 / 검사 | 결과 |
|---|---|
| `make lint`; `make test` | 최종 **229개: 215 통과·14 skip**, 실패 0 (22.512초). |
| `make demo` | exit 0, completed, 9 synthetic trial, `runs/20260921T150654Z-64e8be23/`. |
| `make doctor`; `make doctor ARGS="--json"` | exit 0, core/evaluation=true, live=false. 33개 검사 중 31 ok, live.key/live.model 미설정 2개 error. JSON은 단일 문서. |
| `AGENT_OPT_CA_BUNDLE=/nonexistent/agent-opt-review-ca.pem make doctor ARGS="--json"` | 예상 exit 2. `ready/areas/checks` 보존, `network.configuration=error`, evaluation=true. 나머지 로컬 검사와 CA별 복구 안내 유지. |
| suite의 CA·timeout·direct doctor 회귀 | 누락/잘못된 PEM/개인키 CA, 자식 전용 환경, setup/runtime fail-closed, fresh-copy direct/Make doctor의 bytecode 미생성 확인. stalled Git/Docker/Python/uname 종료와 자식 정리·별도 sentinel 보존 확인. |
| `make setup ARGS="--offline"` | 수정 후 exit 0 / ready, stderr의 잘못된 `Killed: 9` 안내 제거. frozen sync·자산 검증·최종 doctor·9-trial demo 통과, `runs/20260921T150847Z-bbbaf3a9/`. |
| `sh -n scripts/bootstrap.sh`; `shellcheck scripts/bootstrap.sh`; `actionlint .github/workflows/ci.yml`; `git diff --check` | 모두 exit 0, ShellCheck 제외 옵션 없음. |

**추가 수정 근거:** 최초 offline setup은 성공했지만 Mac `/bin/sh`가 종료한 watchdog의 job 상태를
`wait` 이전에 stderr로 출력했다. 기존 offline shell 테스트에 지연된 정상 interpreter와 깨끗한
stderr 검사를 추가해 실패를 재현한 뒤 EXIT cleanup에만 stderr 억제를 적용했다. timeout 복구 메시지는
계속 출력된다. focused 실행에서 200ms fixture deadline이 정상 startup에도 걸린 1건은 단독 실행에서
통과했으며, slow-sync 범위 테스트만 deadline 1초 / sync 1.2초로 분리했다. production 15초 제한은 유지한다.

skip 14개는 host RTL 도구 9개, 선택적 OpenCode Docker config 1개, BuildKit/Compose 네트워크 2개,
PyYAML wrapper 2개다. 이전 통합 `5db02b2`의 smoke `runs/dev-smoke-494b9ec9a41d/`는 실도구 9/9,
host-Docker 1/0/0, 공식 CVDP 정답/오답 1/0이었고 driver network suite는 18개 중 16 통과·2 skip이었다.
이번 변경은 진단/짧은 shell probe에 한정되어 전체 이미지 rebuild·smoke를 반복하지 않았다.
기존 증거를 이번 HEAD에서 재실행한 결과로 표시하지 않는다. live 모델 호출은 하지 않았다.
빈 호스트의 실제 uv 신규 설치, 인증 proxy/TLS interception, 추가 CA를 넣은 공식 이미지 전체 빌드는
이번 최종 검증 범위 밖이다. 확인한 원격 CI 결과는 아래에 별도로 기록한다.

### 최종 Ubuntu 코어 CI

`cbca34f`의 [PR #7 run 35617263750](https://github.com/wontaeJeong/agent-optimizer/actions/runs/35617263750)을
완료까지 관찰하고 job 단계와 실제 로그를 확인했다. Ubuntu Python **3.11/3.12 모두 success**:
각 **229개 중 224 통과·5 skip**, native `RealRTLTests` **9/9** 포함이다.
Make help/lint/test/demo, 9-trial 합성 데모, sdist/wheel 빌드 및 소스 밖 wheel 설치/CLI 검사도 통과했다.
skip 5개는 optional OpenCode Docker config 1개, Docker network 2개, PyYAML wrapper 2개다.
공식 CVDP Docker job은 수동 전용으로 이 PR run에서는 **skipped**이며 이번 최종 wave에서
별도 dispatch하지 않았다. 과거 공식 Docker 통합 기록과 이 native 코어 실행을 구분한다.

## 2026-09-21 Developer onboarding (Task 3)

기준 코드 `e669340`, 기존 `chore/dev-environment` worktree에서 실행. macOS arm64,
프로젝트/driver CPython **3.12.12**, uv **0.10.7**, Colima Docker **29.2.1 linux/arm64**,
Compose **5.1.3**. 산출물의 UTC 시각은 2026-09-20 18:14이다.
처음에는 프로젝트 `.venv`와 setup 로그만 존재했고 외부 source/data/driver/환경 lock은 없었다.
현재 worktree에 새로 확보했으며 다른 worktree의 writable `external/` 자산은 사용하지 않았다.
Docker daemon의 기존 layer cache는 사용 가능했다. 완전히 빈 호스트/uv 미설치 환경의 실설치
검증은 아니며 해당 bootstrap 분기는 격리된 계약 테스트로 검사했다.

| 실제 명령 | 결과 |
|---|---|
| `make help`; `python3 scripts/dev.py --help`, `setup --help`, `doctor --help` | exit 0, 문서 예제를 실제 help/source와 대조. |
| 설치 전 `make doctor` | 예상 exit 2. core ready, evaluation/live not ready. lock·두 소스·세 데이터·driver 누락을 함께 진단하고 의존 검사는 blocked 및 복구 안내. |
| 첫 `make setup` | 도구의 200초 제한으로 evaluation image build 중 SIGTERM. 성공으로 집계하지 않음. |
| `make setup` 재실행 (30분 허용) | exit 0 / ready. source/data·driver·두 이미지 준비, 최종 doctor와 9-trial 데모 성공. 결과 `runs/20260920T181404Z-0255a370/`. |
| `make doctor`; `make doctor ARGS="--json"` | 모두 exit 0. core/evaluation=true, live=false. 총 32개 검사 중 core/evaluation 30개 ok, live.key/live.model 두 항목 error. JSON stdout은 단일 문서. |
| `make setup ARGS="--offline"` | exit 0 / ready. 캐시 이미지 검증·고정 환경 재사용, 데모 `runs/20260920T181415Z-4dfc4f3f/` (9 trial). |
| `make smoke` | exit 0 / passed, `runs/dev-smoke-04f6045f16c7/`. 실제 도구 **9/9, skip 0** (1.378초), host-Docker 정답/오답/조기 종료 **1/0/0**, 공식 LFSR 정답/기능 오답 **1/0**. |
| `make lint` | `All checks passed!` |
| `make test` | **200개: 190 통과·10 skip**, 실패 0 (11.335초). 호스트 simulator 미설치 9개는 위 Docker smoke로 별도 확인; optional OpenCode config 1개는 이번 작업에서 별도 실행하지 않음. |
| `make demo` | exit 0, completed, 두 합성 Agent·9 trial, `runs/20260920T181457Z-74280161/`. 실제 모델 성능 수치 아님. |
| `.venv/bin/python -m build` | exit 0, `dist/agent_optimizer-0.3.0.tar.gz` 및 wheel 생성. README 변경 후 재빌드도 통과. |
| `uv venv --python 3.12 runs/task3-wheel`; `uv pip install --python runs/task3-wheel/bin/python dist/agent_optimizer-0.3.0-py3-none-any.whl` | 독립 wheel 설치 성공. 저장소 밖 임시 작업 디렉터리에서 해당 venv의 `env -u PYTHONPATH <python> -I -m agent_optimizer --help`, `env -u PYTHONPATH <agent-opt> --help` 모두 exit 0. import 경로가 이 venv의 site-packages임을 확인. |
| `actionlint .github/workflows/ci.yml`; `git diff --check` | exit 0. 변경된 원격 workflow의 실행 성공을 뜻하지 않음. |
| 외부 두 checkout `git status --short` | 모두 clean. 고정 SHA/driver lock 변경 없음. |

### 실제 산출물 대조

- `external/environment-lock.json`, `external/setup-logs/` 및 smoke `summary.json` 보존(Git 제외).
  평가 image ID: `sha256:ee167c7cd486111a2a807a703ae6bbb30debf2d26f5bb9d0d760ec07c96a58ec`,
  Agent image ID: `sha256:2dc784c4c05959954bc91dc8639a3f3652f058d25173c52a0ca5be92706a3601`.
  고정 소스/의존성 pin이 같아도 image ID는 이전 빌드와 다르다.
- driver 설치 32개 및 compiled lock hash
  `8de4e036b1fd7c670fc9cca44d7d3f5cac2f31cf320ce96b2593a4db6883d039` 유지.
  실행 도구 Yosys 0.40, Icarus/vvp 13.0, OpenCode 1.18.31 확인.
- `real-tool-tests/stderr.log`의 9개 ok 및 양쪽
  `cvdp-{positive,negative}/cvdp_evaluation/work/raw_result.json`을 직접 확인했다.
  각각 비어 있지 않은 test 1개, `result=0` / `result=1`, 양쪽 `error_msg=null`.
  private `cvdp_copilot_lfsr/reports/1.txt`의 정답 cocotb **3/3 PASS**, 오답 **3/3 FAIL** 확인.
  기존 cocotb deprecation 및 pytest cache-permission warning은 남아 있다.

**범위:** 이번 Task 3은 docs/CI 변경이며 새 production correctness bug는 발견하지 않았다.
모델 호출/live, 변경된 CI의 native Ubuntu 실행은 수행하지 않았다. 이전 Ubuntu 결과는 아래
`10baa46` 기록이며 이번 명령 변경을 검증한 결과로 재사용하지 않는다.

## v0.3.0 전달 당시 기록

출처: 기존 배포 문서 및 사용자가 제공한 `agent-optimizer-v0.3.0.zip` 인수인계.
아래는 **과거에 확인했다고 전달받은 기록**이며 이번 작업에서 모두 재실행한 결과가 아니다.

- Python 3.12 환경: unittest 32개 중 31개 통과, 1개 생략.
- 생략: 실제 Icarus/vvp smoke (실행 파일 미설치).
- uv lock 생성 및 uv sync --frozen 설치 성공.
- 설치된 agent-opt CLI로 최소 데모 실행 성공: 독립 Agent 2개, 9 trial.
- 솔로 fixture baseline solve_rate=0, 선택 후보=1. 합성 결과이며 모델 성능 수치 아님.
- 작은 RTL 예제의 설정/플러그인 plan 검증 성공 (실제 실행 아님).
- 고정 CVDP 공개 no_commercial 예제 변환 성공: 1개 공개 과제.
- Python/TOML 구문 검증 성공.
- Git source SHA 고정, 원본 미수정, 비공개 평가 데이터 분리, 상용 의존성 제외,
  빈 공식 결과의 실패 처리, Agent 자기보고 무시를 테스트함.
- 실제 OpenCode/Docker/LLM/공식 CVDP 시뮬레이션은 실행하지 못함.
- 사용자 인수인계에는 ZIP을 새 디렉터리에 풀어 최소 데모를 재실행했다고 추가 기록되어 있음.

## 2026-09-20 문서 인수인계 작업에서 실제 수행

- 기준 코드: `aeb732c0f1c138a568903c971baa17bfaa6b55e4`, 변경 전 worktree는 clean.
- 환경: macOS (`uname -sm`: `Darwin arm64`), `python3 --version`: `Python 3.14.5`.
  목표 Linux 서버에서의 실행 결과가 아니다. 추가 의존성 설치 없이 `PYTHONPATH=src`로 실행했다.
- 작업 루트: `.worktrees/update-project-settings` (브랜치 `chore/update-project-settings`).

| 실제 실행 명령 / 확인 | 결과와 범위 |
|---|---|
| `PYTHONPATH=src python3 -m unittest discover -s tests -v` | 32개 중 31개 통과, 1개 skip, 실패 없음. `test_real_iverilog_smoke`: Icarus binaries not installed. |
| `PYTHONPATH=src python3 -m agent_optimizer run examples/minimal/experiment.toml` | exit 0, completed, 독립 Agent 2개, 9 trial. summary의 synthetic=true 확인. |
| 생성된 `summary.json` 확인 | rtl-solo validation baseline 0 → 선택 후보 1, test도 0/1. rtl-team baseline/선택 1, 두 그룹 trial 수는 5/4. 합성 배선 검증이며 실제 Agent 성능 향상·세일즈 근거가 아님. |
| `PYTHONPATH=src python3 -m agent_optimizer plan examples/rtl-debugger/experiment.toml` | exit 0, valid=true, integrations_ready=true. 설정·플러그인 검사만 수행. |
| `PYTHONPATH=src python3 -m agent_optimizer plan examples/minimal/research-planned.toml` | exit 0, valid=true, integrations_ready=false, `optimizers/gepa: not implemented`. 알고리즘 실행 성공을 뜻하지 않음. |
| 고정 ACE/CVDP 출처 열람 및 로컬 SHA 대조 | [SOURCES.md](SOURCES.md)에 판단·소비 파일·확인 수준 기록. SHA 변경 없음. |

최소 데모 산출물은 로컬 `runs/20260920T092946Z-87d8f0f1/`에 생성됐다.
`summary.json`, `manifest.json`, `events.jsonl`, `report.md`와 그룹별 후보/trial/선택 자료는
Git 제외 대상이다. 이 경로의 로그가 다른 checkout에도 있다고 가정하지 말고 위 명령으로 재생성한다.

### 테스트가 입증하는 것과 입증하지 않는 것

- `tests/test_core.py`: 합성 Agent 실행, 그룹 분리, 후보 경계/변조 방지, 지표·선택·family 분리,
  예산 중단, 평가 자산 분리, 선택 고정/test 기록 등을 검증한다.
- `tests/test_integrations.py`: 임시 로컬 Git repo의 고정 SHA/원본 보존을 실제 확인한다.
  CVDP는 작은 모의 row와 모의 프로세스 결과로 입력 분리·상용 의존성 제외·빈 결과 거부·후보 채점을 확인한다.
  테스트명의 official은 실제 CVDP 시뮬레이터 실행을 의미하지 않는다.
- `tests/test_adapters.py`: argv/shell 비해석·timeout은 로컬 subprocess 실행이다.
  Docker 명령/정리, OpenCode JSON 이벤트, Icarus 결과 판정은 mock 기반 계약 검증이며
  유일한 실제 Icarus smoke는 skip됐다.

### 이번에 하지 않은 검증

uv 설치/lock 재생성, ZIP 재추출, 공식 CVDP 데이터 변환 재실행, 외부 환경 setup/Docker 빌드,
유료 모델 호출, 실제 OpenCode 어댑터 실행, CVDP 시뮬레이션, native runner 및 전체 benchmark 실행은 하지 않았다.
연구 알고리즘 논문 결과와 Agent 성능 개선도 검증하지 않았다.

CLI plan의 integrations_ready는 플러그인 로딩/설정 수준이며, 외부 도구 실행 성공을 의미하지 않음.
외부 모델 비교 전 환경 doctor와 한 문제 실제 평가를 먼저 실행할 것.

## 2026-09-20 MVP lifecycle/selection hardening (Task 2)

환경: `.worktrees/mvp-hardening`, macOS `Darwin arm64`, Python 3.14.5.
Ubuntu x86_64, Docker, 외부 모델/API의 실환경 실행 결과가 아니다.

| 명령 | 실제 결과 |
|---|---|
| `PYTHONPATH=src python3 -m unittest discover -s tests -p test_run_lifecycle.py -v` | 최종 18개 통과. 초기 RED는 14개 실행, failure 16건/error 3건(하위 테스트 포함). 추가 초기화 오류 RED 확인 후 GREEN. |
| `PYTHONPATH=src:tests python3 -m unittest test_core test_boundaries -v` | 44개 통과. T1 후보 검증-before-cache와 출력 경계 회귀 포함. |
| `PYTHONPATH=src python3 -m unittest discover -s tests -v` | 전체 75개 실행, 74개 통과·1개 skip, 실패 없음. 전체 suite는 이 작업에서 한 번 실행. Icarus binaries not installed. |
| `PYTHONPATH=src python3 -m agent_optimizer run examples/minimal/experiment.toml --output runs/task-2` | exit 0, `completed`, 독립 Agent 2개·9 trial. |
| `git diff --check` | 통과. |

새 테스트는 짧은 로컬 subprocess timeout 및 제어된 clock/플러그인으로 전역 deadline과 per-trial
timeout의 구분, 마지막 평가 후 deadline 검사, 예약 실패 횟수, 소스/그룹/stage/test 중단,
Optimizer 사용량의 호출 시점 저장, 출력 루트 symlink 오류의 trial 식별 기록, nullable report/rerank,
Pareto `keep` 거부와 invalid/partial 선택 제외를 확인했다. Ctrl-C는 `KeyboardInterrupt` 주입으로 검증했다.

최소 데모 산출물: `runs/task-2/20260920T105352Z-14ab82b7/` (Git 제외).
summary의 `synthetic=true` 확인. rtl-solo baseline/선택 validation 0/1, test 0/1, 5 trial;
rtl-team validation 1/1, test 1, 4 trial. 합성 연결 검증이며 실제 Agent 성능 향상 근거가 아니다.

## 2026-09-20 Task 5 초기 환경 검증 — 아래 후속 결정으로 차단 해소

환경: Mac arm64, Colima Docker Engine 29.2.1 (`linux/arm64`), Compose 5.1.3,
uv 0.10.7, isolated host Python 3.12.12. **Ubuntu x86_64 실행 결과가 아니다.**

| 실행 | 실제 결과 |
|---|---|
| 공식 Dockerfile.sim `docker build --platform linux/amd64` | Icarus 컴파일 중 `g++` segmentation fault. 변경 없이 사용한 공식 파일이며 emulation 경로 실패를 보존. |
| OpenCode 1.18.31 amd64 이미지 빌드 (2회) | npm postinstall 실패. 별도 `docker run`의 같은 버전 설치/실행은 성공하여 build-time 원인은 미해결. |
| `python3 scripts/dev.py setup --platform linux/arm64` | 공식 OSS/OpenCode 이미지 빌드·실행 doctor 성공. 초기 잘못된 LFSR live 선택은 명시적 오류; full HF에 없는 ID였음. |
| 수정 후 `python3 scripts/dev.py setup --offline --platform linux/arm64` | 성공. source/data/image ID 확인, full HF 302개 중 71개 지원·231개 제외, live는 검토한 QAM16 한 문제. |
| `python3 scripts/dev.py smoke --platform linux/arm64` | **exit 2 / blocked**. 실제 도구 테스트 9개 중 8개 통과·1개 실패·skip 0. 이후 독립 host-Docker 및 공식 CVDP 검사 결과도 보존. |
| host evaluator `runtime.kind=docker` | toy 정답 passed=1, 오답 passed=0, `$display`/`$finish` 조기 종료 후보 passed=0. 실제 합성/컴파일/시뮬레이션 phase 로그 보존. |
| 공식 CVDP LFSR 정답/기능 오답 | 비어 있지 않은 `raw_result.json`: 정답 `result=0`, 상수 출력 오답 `result=1`. 오답은 컴파일 후 cocotb 3개 테스트 모두 sequence assertion 실패. |
| `python3 scripts/dev.py live --platform linux/arm64` | `blocked_auth`: OPENROUTER_API_KEY 부재. 값은 출력하지 않았으며 모델 호출·유료 fallback 없음. |
| Python 3.12 `.venv` 전체 unittest | 128개: 119개 통과·호스트 도구 미설치로 9개 skip. 별도 공식 이미지 8/9 결과를 대체하지 않음. |
| ruff / `git diff --check` / minimal CLI | 통과. minimal은 9 trial의 합성 데모이며 실제 RTL/모델 성능 근거가 아님. |
| 실제 CVDP 무한 시뮬레이션, timeout 5초 | timeout으로 종료, 전용 network의 컨테이너 제거 성공. 별도 sentinel 컨테이너는 계속 실행 중임을 확인한 뒤 명시적으로 정리. |

공식 이미지 도구: Yosys 0.40 (`a1bb0255d`), Icarus/vvp 13.0 (`v13_0-dirty`라는 upstream
빌드 출력), Verilator 5.038, cocotb 2.0.1. 별도 Agent 이미지: OpenCode 1.18.31.

- 평가 이미지: `sha256:3d6d4609a2c9f8e842f1fea3bbec41e6b1c53b75bcfdb708b372c8b931fcb54d`
- Agent 이미지: `sha256:9deca57252c93d6f36883cabeb82641d9a30ea82d67e9267436505d6375bcd88`
- 설정/버전/hash: `external/environment-lock.json`, 빌드/doctor: `external/setup-logs/`.
- 최종 실제 smoke: `runs/dev-smoke-a4ad10789069/`; 독립 재현 netlist:
  `runs/task5-independent-runtime-venv-fixed/characterization/netlist.v`.

### 초기 T4 차이와 결정 요청 (후속 결정으로 해소)

`test_yosys_display_is_synthesis_output_not_simulation_behavior`가 실패했다.
Yosys는 입력 `initial $display("TEST_PASS")`를 netlist의 `initial $write("TEST_PASS\n")`로
보존한다. vvp stdout은 `TEST_PASS` 후 `FATAL: ... Mismatch`이고 종료 코드는 1이다.
즉, **합성 자체가 print 부작용을 제거한다는 가정은 실제 도구와 다르다.**
현재 production 입력 정책은 이 후보를 먼저 거부하고, scorer는 marker와 exit 0을 함께 요구한다.
T4 테스트/정책을 임의로 완화하지 않았다. Controller가 characterization/설명 수정 범위 또는
추가 netlist 검증을 결정한 뒤 9개 gate를 다시 실행해야 하며, 현재 전체 smoke 성공으로 표시하지 않는다.

실환경에서 기존 evaluator의 Python `.resolve()`가 venv symlink를 해제하여 PyYAML import를
실패시키는 문제를 RED/GREEN 테스트로 수정했다. 공식 driver는 subjective model 생성 문구를
로그에 출력하지만, 검토한 `cid003` + Compose 경로는 `repo.obj()`만 실행한다. Driver에
모델 자격증명을 전달하지 않는다. 공식 pytest의 cache 경로 권한 warning은 현재 남아 있다.

## 2026-09-20 Task 5 후속 결정 적용 — 실제 smoke 통과

실제 print 보존을 허용하면서 **private mismatch + nonzero exit는 실패**임을 확인하도록
characterization을 수정했다. Production 입력 거부/scorer는 변경하지 않았고 `$write` 전용
입력 정책 회귀를 추가했다. 합성만으로 임의 RTL을 정화한다는 가정은 사용하지 않는다.

`--platform` 생략 시 `docker version --format '{{.Server.Os}}/{{.Server.Arch}}'`로 daemon native를
빌드 전에 선택한다. 명시적 override는 유지하고, 미지원 architecture/daemon 조회 실패는 오류이며
실패한 빌드를 다른 architecture로 자동 재시도하지 않는다. 이번 native 선택은 `linux/arm64`다.

| 실제 명령 | 결과 |
|---|---|
| `python3 scripts/dev.py setup --offline` | exit 0 / ready, `linux/arm64` 기록, 기존 검증된 이미지/데이터 재사용 |
| `python3 scripts/dev.py smoke` | **exit 0 / passed**: 실제 도구 9/9, skip 0; host-Docker 정답/오답/조기 종료 1/0/0; 공식 CVDP 정답/기능 오답 1/0, 양쪽 raw tests 비어 있지 않음 |
| `python3 scripts/dev.py live` | exit 2 / blocked_auth, OPENROUTER_API_KEY 부재, 실제 모델 호출 없음 |
| `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v` | 134개: **125 통과, 호스트 도구 미설치 skip 9**, 실패 0 (3.637초) |
| `.venv/bin/python -m ruff check src tests scripts examples`, `git diff --check` | 통과 |

최신 실제 smoke 산출물: `runs/dev-smoke-70aff9715455/`. 이미지 ID와 데이터 SHA는 앞서 기록한 값과
동일하다. 이전 실패 로그도 보존한다. 이 결과는 Mac Docker ARM64이며 주 대상 **Ubuntu x86_64 및
실제 무료 모델 inference는 아직 미검증**이다. integration dependency lock과 나머지 minor review는 T6 범위다.

## 2026-09-20 Task 6 CI/handoff/integration

환경: macOS arm64, uv 0.10.7, 프로젝트/driver CPython 3.12.12, Colima Docker 29.2.1
(`linux/arm64`), Compose 5.1.3. 아래는 실제 로컬 명령 결과이며 **원격 CI/Ubuntu x86_64 결과가 아니다.**

| 실제 명령 | 결과 |
|---|---|
| `uv run --frozen --extra dev ruff check .` | `All checks passed!` |
| `uv run --frozen --extra dev python -m unittest discover -s tests -v` | 144개: **134 통과, 10 skip**, 실패 0 (3.837초). 호스트 simulator 미설치 9개 + 명시적 이미지 미설정 Docker config 1개를 아래 실제 실행으로 별도 확인. |
| `uv run --frozen --extra dev python -m agent_optimizer run examples/minimal/experiment.toml` | exit 0, completed, 두 Agent·9 trial, `runs/20260920T131030Z-fe45caca/`. synthetic=true; 실제 성능 수치가 아님. |
| `uv run --frozen --extra dev python -m build` | exit 0, `agent_optimizer-0.3.0.tar.gz` 및 `agent_optimizer-0.3.0-py3-none-any.whl` 생성. |
| `uv venv --python 3.12 runs/task6-wheel-NkLAAd/venv`, `uv pip install --python runs/task6-wheel-NkLAAd/venv/bin/python dist/agent_optimizer-0.3.0-py3-none-any.whl` | 독립 환경에 wheel 설치 성공. 해당 임시 디렉터리에서 `env -u PYTHONPATH venv/bin/python -I -m agent_optimizer --help` 및 `venv/bin/agent-opt --help` exit 0; 실제 import 경로는 이 venv의 site-packages. |
| `python3 scripts/dev.py setup` | exit 0 / ready. 고정 upstream 입력에서 compiled driver lock으로 32개 설치 상태 동기화, 이미지 빌드는 기존 Docker layer cache 재사용. |
| `python3 scripts/dev.py setup --offline` | exit 0 / ready. source/data/image 및 새 driver lock/설치 목록 검증; 네트워크 보완 없음. |
| `python3 scripts/dev.py smoke` | exit 0 / passed, `runs/dev-smoke-a1f349ffdf21/`. 실제 도구 **9/9, skip 0** (1.397초); host-Docker toy 정답/오답/조기 종료 **1/0/0**; 공식 LFSR 정답/기능 오답 **1/0**. |
| `AGENT_OPT_TEST_DOCKER_IMAGE=sha256:9deca57252c93d6f36883cabeb82641d9a30ea82d67e9267436505d6375bcd88 DOCKER_DEFAULT_PLATFORM=linux/arm64 PYTHONPATH=src:tests uv run --frozen --extra dev python -m unittest test_adapters.DockerEnvironmentTests -v` | 실제 config 검사 1개 통과 (1.433초), `runs/docker-env-regression-d468264713d8/`. 기본/명시 compatible/빈 override 확인, network=none, inference 없음. |
| `env -u OPENROUTER_API_KEY python3 scripts/dev.py live` | exit 2 / `blocked_auth: OPENROUTER_API_KEY is absent`. 모델 호출 없음. |
| `uv run --frozen --extra dev python -m agent_optimizer plan <example>` | RTL·Optimizer template: valid/integrations_ready=true(등록 검사만). research-planned: valid=true, integrations_ready=false, GEPA not implemented. |
| 동일 CLI의 `run examples/minimal/research-planned.toml --output runs/task6-unsupported` / `run experiments/optimizer-template/experiment.toml --output runs/task6-template` | 둘 다 exit 2, 각각 GEPA / Team optimizer 미구현 오류. baseline으로 자동 대체하지 않음. |
| 동일 CLI의 `report runs/20260920T131030Z-fe45caca --csv runs/20260920T131030Z-fe45caca/trials.csv` 및 `rerank runs/20260920T131030Z-fe45caca examples/minimal/experiment.toml` | exit 0. rerank는 validation에서 solo c0002/team c0001 선택. partial/nullable baseline은 lifecycle 회귀로 확인. |
| `actionlint .github/workflows/ci.yml`, `git diff --check` | 통과. actionlint 초기 SC2155 경고는 export와 assignment를 분리하여 해결. 원격 job 실행은 아님. |

### 환경·판정 근거

- driver lock: `examples/ace-rtl/environment/requirements-cvdp-py312.txt`, SHA-256
  `8de4e036b1fd7c670fc9cca44d7d3f5cac2f31cf320ce96b2593a4db6883d039`.
  upstream input SHA-256 `f79bf21e2e98b96016cf7992afb6a4df4bcfac64d07ff811195d22ddf0af6ad2`.
  compile 명령·출처는 [SOURCES.md](SOURCES.md). 12개 직접 pin과 전이 포함 32개 package를 보존한다.
- source/data revision·hash와 두 이미지 ID는 위 Task 5와 동일하다. Yosys 0.40, Icarus/vvp 13.0,
  Verilator 5.038, OpenCode 1.18.31 실행 확인. `external/environment-lock.json` 및 smoke summary에 기록.
- `cvdp-{positive,negative}/cvdp_evaluation/work/raw_result.json`은 각각 비어 있지 않은 service test
  `result=0` / `result=1`이다. 기능 오답은 컴파일 후 실제 private sequence assertion에서 실패한다.
- 공식 `reports/1.txt`에 cocotb `Join`/`str(handle)` deprecation과 pytest의
  `/rundir/harness/.cache` cache-permission warning이 남아 있다. 비치명적이며 checker/Compose의
  실행 의미를 바꾸지 않고 기록했다. upstream checkout 두 곳은 `git status --short`가 비어 있음.
- full HF importer는 71개 지원 형태·231개 제외(기존 Task 5 범위)이며 모든 과제의 실행 성공이 아니다.
  evaluator-only LFSR reference와 live QAM16 데이터는 별개다. live 모델은 선택/실행하지 않았으며
  개발 Harness의 모델은 제품 모델로 대체하지 않았다.

### Spec coverage audit — 8개 발견 사항

| 발견 사항 | 구현 | 의미 있는 회귀/실제 근거 |
|---|---|---|
| 산출물 루트 symlink | `workspace.py:collect_outputs`, `runner.py:trial` | `test_boundaries.OutputBoundaryTests`의 root/internal/destination/special-file 및 정상 복사, `test_runner_rejects_replaced_workspace_ancestor_before_collection` |
| 전역 예산 vs trial timeout | `runner.py:Budget`, `GroupRunner.trial` | `test_global_timeout_is_invalid_and_not_selected`, `test_configured_trial_timeout_remains_a_scored_failure`, `test_last_evaluation_cannot_finish_after_global_deadline` |
| RTL 성공 문자열 위조 | `examples/rtl-debugger/iverilog.py` | `RTLContractTests`의 입력 거부/marker+exit/phase 분리, `RealRTLTests` 9개 및 host-Docker 1/0/0. Yosys `$write` 보존과 private mismatch 실패를 구분. |
| 후보 식별·hash | `workspace.py:CandidateStore`, runner 검증-before-cache | `CandidateBoundaryTests`의 metadata 치환/다른 store/미발급 ID/내용 재hash·경로 변조/정상 계보/캐시 전 검증 |
| 중단 usage·부분 결과 | `runner.py:Context.record_usage`, `run_experiment`, `results.py` | `test_usage_is_durable_at_call_time_before_stage_exit`, stage/test/Ctrl-C/source 오류, `test_report_and_rerank_accept_nullable_baseline` |
| 평가 helper hash | `registry.py:plugin_files`, runner manifest | `test_dependency_only_edit_changes_manifest_fingerprint`, optimizer/harness helper 및 잘못된 선언-before-load |
| 외부 Agent 실행 설정 | `sources.py` 선택/인증 제외 | `SourceSelectionTests`의 explicit developer prefix 포함/포괄 패턴 기본 제외/auth·env 강제 제외, `SourceTests` 고정 Git/원본 보존 |
| Pareto keep | `config.py:validate_objective`, `objectives.py:select` | `SelectionTests` 명시 keep 거부·invalid/partial 제외, `ObjectiveTests` Pareto frontier 및 lexicographic/weighted 선택 |

추가 계약 추적:
- **소스·데이터 lock/격리:** setup의 기존 고정 SHA/HF 기대 hash, `DatasetAcquisitionTests`의
  cache/offline/hash/중단 원자성, `OfficialImportTests`의 private/targets/제외/empty-set 실패와 실제 setup.
- **팀 연결:** `experiments/optimizer-template/` 및 `PluginContractTests`의 train-only 피드백·이력,
  usage/checkpoint·runner 선택/test 소유권. Meta-Harness/GEPA/Ecdysis 상세 구현은 팀 작업.
- **driver 재현:** `DriverLockTests`는 변경 upstream 입력, compiled lock 및 installed-package drift 거부,
  online/offline의 compiled lock sync와 hash 영속화를 검사한다. 실제 public setup/offline/smoke 통과.
- **Docker 평가·모델 설정:** `EvaluatorRuntimeTests`의 venv identity/driver credential 필터/scoped cleanup,
  실제 smoke, `ShippedRTLProfileTests`/`DockerEnvironmentTests`의 provider env/이미지 기본값,
  live auth/free-model preflight. 키 없는 config 검사는 모델 endpoint/inference 검증이 아니다.

Task 6 minor fix RED/GREEN: malformed inventory에서 AttributeError/TypeError와 잘못된 diagnostic,
CR/LF marker 미거부를 먼저 재현했다. 200ms 전역 timeout 테스트는 300ms source 지연 주입 시
`groups[0]` IndexError를 재현했다. runner clock만 제어하고 subprocess timeout은 실제로 유지한 후
같은 지연 probe가 통과했다. 관련 78개 focused tests도 통과. driver lock 신규 회귀는 최초 4개
failure(하위 case 포함)를 확인한 뒤 GREEN이다.

### 남은 검증

Task 6 종료 시 native Ubuntu x86_64/원격 Actions는 미검증이었다. 이후 실제 결과는 아래에 기록한다.
무료 모델 live, native ACE 및 연구 알고리즘 성능은 여전히 미검증이다.
CI 변경은 native 도구가 없으면 실패하고 공식 통합은 수동 입력으로 실행하도록 구성했다.
이전 amd64 에뮬레이션 실패를 ARM64 성공으로 덮지 않으며 실패 뒤 플랫폼 자동 대체도 없다.
Python driver lock은 공식 Dockerfile의 mutable OS 저장소·installer까지 완전히 고정하지 않는다.

## 2026-09-20 Final fix — native Ubuntu integration

### 새 원격 근거 (`751e99f`, 수정 전)

- [PR core run 35513674595](https://github.com/wontaeJeong/agent-optimizer/actions/runs/35513674595):
  Ubuntu 24.04.5 x64, Python 3.11/3.12 모두 성공. 각 **144개 중 143 통과·1 optional Docker config skip**.
  native Yosys/Icarus, lint, minimal demo, sdist/wheel 및 독립 wheel 설치 검사 통과.
- [수동 공식 run 35513687494](https://github.com/wontaeJeong/agent-optimizer/actions/runs/35513687494):
  native `linux/amd64`, Docker 28.0.4/Compose 2.38.2. 공식 이미지 build/setup와 offline reuse 성공.
  실제 도구 9/9, host-Docker toy 정답/오답/조기 종료 1/0/0 이후 **official-positive에서 smoke 실패**.
  이후 official-negative와 별도 OpenCode config 검사는 실행되지 않았다.
- 평가 이미지 ID `sha256:f9cd9a20abbedebab153c3863d9bbb7155467351b36032562f890e73291362d4`,
  Agent 이미지 ID `sha256:889cbe091942d087b8ab10ce232a5089a21898c19abcb2a176dadd699c123531`.
  이 native 빌드 성공은 앞선 **Mac amd64 에뮬레이션 컴파일 실패**와 별개다.
- `runs/dev-smoke-301795bfb5b9/summary.json`은 official-positive를 `failed/passed=0`으로 기록했다.
  `raw_result.json`의 `result=1, error_msg=null`만으로는 환경 실패를 구별하지 못했다.
  private `cvdp_copilot_lfsr/reports/1.txt`에는 `load metadata for docker.io/library/sha256:...`,
  `pull access denied`, `insufficient_scope: authorization failed`가 있었다. **HDL 평가 실패가 아니다.**

### 수정과 실제 로컬 재검증

`scripts/dev.py`는 공식 FROM/Compose용 `OSS_SIM_IMAGE`에 준비된 로컬 tag를 전달하기 전에
`docker image inspect`의 ID/platform을 기존 lock과 비교한다. 누락·불일치는 실행 전에 중단한다.
Docker run은 locked ID를 유지한다. evaluator는 실패한 test의 private log를 읽기 전에 owned prefix
내부 경로·regular file인지 검증하고 Docker build/launch 오류를 `infrastructure_error/passed=null`로
분류한다. 로그 본문은 공개 feedback에 노출하지 않고 일반 HDL compile/기능 오답은 0점으로 유지한다.

환경: macOS arm64, 진입 Python 3.14.5, suite/driver Python 3.12.12,
Docker 29.2.1 `linux/arm64`, Compose 5.1.3. 기존 검증된 이미지와 cache를 재사용했으며 full rebuild 없음.

| 실제 명령 | 결과 |
|---|---|
| `PYTHONPATH=src:tests .venv/bin/python -m unittest test_dev_environment test_integrations -v` (수정 전) | 36/36 통과, clean baseline |
| `PYTHONPATH=src:tests .venv/bin/python -m unittest test_dev_environment.PreparedImageTests test_dev_environment.PrivateResultLogTests -v` (RED) | 신규 7개 실행, 하위 case failure 30건. bare ID 전달·tag 미검증·private log 환경 실패 오채점·unsafe path 미거부 재현. HDL/optional-log 유지 검사는 처음부터 통과. |
| `PYTHONPATH=src:tests .venv/bin/python -m unittest test_dev_environment test_integrations -v` (GREEN) | **43/43 통과**, skip 0 |
| `python3 scripts/dev.py smoke` | **exit 0 / passed**, `runs/dev-smoke-ffae02c52f35/`. 실도구 **9/9, skip 0**; host-Docker **1/0/0**; 공식 LFSR **1/0**. |
| `uv run --frozen --extra dev python -m unittest discover -s tests -v` | **151개: 141 통과·10 skip**, 실패 0 (3.749초). 호스트 simulator 미설치 9개는 위 실제 Docker 도구 검사로 확인; optional Docker config 1개는 이번 wave에서 별도 재실행하지 않음. |
| `uv run --frozen --extra dev ruff check .` | `All checks passed!` |
| `PYTHONPATH=src python3 -m agent_optimizer run examples/minimal/experiment.toml` | exit 0, completed, 9 trial, `runs/20260920T135712Z-675cebcc/`. 합성 연결 검증. |
| `git diff --check`; 두 upstream checkout의 `git status --short` / `git rev-parse HEAD` | 공백 오류 없음. ACE/CVDP 모두 clean, 기존 고정 SHA 유지. |

공식 양쪽 `reports/1.txt`에서 `FROM agent-optimizer-cvdp:8e894cf-arm64`를 확인했다.
평가/Agent image ID는 위 Task 5/6 ARM64 값과 동일하다. 양쪽 raw tests는 비어 있지 않으며 각각
`result=0` / `result=1, error_msg=null`; 오답은 cocotb sequence assertion 3개 실패로 0점 유지다.
기존 pytest cache-permission/cocotb deprecation warning은 남아 있으며 환경 실패로 오분류하지 않는다.

**이 로컬 검증 종료 당시에는 수정 후 native Ubuntu/BuildKit 공식 smoke가 원격 재실행 대기 상태였다.**
이 로컬 smoke의 build 로그는 legacy `Step 1/2` 형식이며 native Ubuntu fix 검증을 대신하지 않는다.
본 wave는 모델 inference를 실행하지 않았다. 아래 후속 원격 정답/오답 raw 결과 확인으로
native 공식 통합 재검증 대기를 해소했다.

## 2026-09-20 Native Ubuntu repeat — passed

검증한 runtime commit: `10baa467906c8ac944a56b340a7025e82dbf1408` (`10baa46`).
이 절은 완료된 원격 실행과 내려받은 실제 artifact를 대조한 문서 기록이며 테스트·빌드를 새로 실행한 결과가 아니다.

- [PR core run 35515595857](https://github.com/wontaeJeong/agent-optimizer/actions/runs/35515595857):
  Python 3.11/3.12 모두 **success**. 수동 공식 job은 이 PR run에서는 의도적으로 skipped다.
- [수동 full run 35515600629](https://github.com/wontaeJeong/agent-optimizer/actions/runs/35515600629):
  Python 3.11/3.12 및 **Official CVDP Docker 모두 success**.
  [공식 job 106090901194](https://github.com/wontaeJeong/agent-optimizer/actions/runs/35515600629/job/106090901194)은
  14:09:12–14:26:29 UTC, **17분 17초**였다.
- 플랫폼: **Ubuntu 24.04.5 x86_64**, native Docker `linux/amd64` (Mac 에뮬레이션 아님).
  공식 job은 Docker 28.0.4, Compose 2.38.2, uv 0.10.7, host CVDP driver Python 3.12.14를 사용했다.

### 명령·실제 결과

| 원격 실행 명령 / 검사 | 확인 결과 |
|---|---|
| PR 코어 `.venv/bin/python -m unittest discover -s tests -v` | Python 3.11/3.12 각각 **151개: 150 통과·1 optional Docker config skip**. native `RealRTLTests` **9/9** 포함. apt 도구는 Yosys 0.33 (`2584903a060`), Icarus 12.0. |
| PR lint / minimal / build / 독립 wheel 설치 검사 | 모두 통과. 최소 데모 **9 trial**(합성 연결 검증), sdist/wheel 생성 및 source tree 밖 설치 CLI 검사 성공. |
| `python3 scripts/dev.py setup` | 성공. 공식 OSS/OpenCode 이미지 준비, source/data/driver lock 및 실제 도구 doctor 확인. |
| `python3 scripts/dev.py setup --offline` | 성공. 준비한 환경 재사용 검사 통과. |
| `python3 scripts/dev.py smoke` | **passed**, `runs/dev-smoke-b8b127226b34/`. 공식 이미지 실도구 **9/9, skip 0** (1.833초); host-Docker 정답/오답/조기 종료 **1/0/0**; 공식 LFSR 정답/기능 오답 **1/0**. |
| lock의 Agent image ID 및 `linux/amd64`를 환경으로 지정한 `PYTHONPATH=src:tests .venv/bin/python -m unittest test_adapters.DockerEnvironmentTests -v` | **1/1 통과** (3.156초). 실제 OpenCode 기본 OpenRouter 설정·명시 compatible override·빈 env 보존 확인. inference 없음. |

### 내려받아 확인한 판정·환경 증거

[artifact `official-cvdp-35515600629`](https://github.com/wontaeJeong/agent-optimizer/actions/runs/35515600629/artifacts/10607246174)의
`external/`과 `runs/`를 확인했다. 로컬 사본은 Git 제외 경로
`.superpowers/sdd/2026-09-20-mvp-hardening/ubuntu-ci-35515600629/`에 있다.

- `external/environment-lock.json`, `external/setup-logs/doctor.json`: `linux/amd64`, ready=true.
  공식 이미지 도구는 **Yosys 0.40 (`a1bb0255d`), Icarus/vvp 13.0 (`v13_0-dirty`), Verilator 5.038**,
  별도 Agent 이미지는 **OpenCode 1.18.31**. 실제 CVDP 로그의 cocotb는 **2.0.1**이다.
- 평가 이미지 `agent-optimizer-cvdp:8e894cf-amd64`:
  `sha256:5973392d727b6a03f29f0f03be5aeb53dc628adb07934d39fa1955f9d0834294`.
  Agent 이미지 `agent-optimizer-opencode:1.18.31-amd64`:
  `sha256:3e1a56d217cb9f7c78bfee5cf39b9745610f84aa637e7817ad6f8f9a43291323`.
- Python driver lock SHA-256 `8de4e036b1fd7c670fc9cca44d7d3f5cac2f31cf320ce96b2593a4db6883d039`,
  upstream requirements SHA-256 `f79bf21e2e98b96016cf7992afb6a4df4bcfac64d07ff811195d22ddf0af6ad2` 및
  전이 포함 32개 설치 목록 확인. ACE/CVDP SHA, HF revision·파일 hash는 [기존 고정값](SOURCES.md) 그대로다.
- `runs/dev-smoke-b8b127226b34/summary.json`은 `status=passed`이며
  `real-tool-tests/stderr.log`에 실도구 9개 모두 `ok`가 있다.
  toy 오답은 private simulation 실패, 조기 종료 입력은 지원하지 않는 construct로 먼저 거부됐다.
- `cvdp-{positive,negative}/cvdp_evaluation/work/raw_result.json`은 각각 **비어 있지 않은 test 1개**,
  `result=0` / `result=1`, 양쪽 `error_msg=null`이다. evaluator 점수는 각각 passed=1 / passed=0이다.
  각 `cvdp_copilot_lfsr/reports/1.txt`에서 BuildKit의
  `FROM docker.io/library/agent-optimizer-cvdp:8e894cf-amd64` 성공과 lock의 평가 image ID를 확인했다.
  양쪽 모두 실제 Icarus compile/vvp를 실행했다. 정답은 cocotb **3/3 PASS**, 오답은
  **3/3 sequence assertion FAIL**로, Docker 환경 실패를 HDL 실패로 오채점한 이전 결과와 다르다.
- `runs/docker-env-regression-a56484403ce3/`의 OpenRouter/compatible stdout과 빈 env stdout을
  확인했다. 이는 모델 설정 검사이며 endpoint 접속·무료 모델 가용성·inference 증거가 아니다.
- 기존 pytest cache-permission 및 cocotb deprecation warning은 양쪽 공식 로그에 남아 있다.
  앞선 Mac amd64 에뮬레이션 실패와 `751e99f`의 첫 Ubuntu 공식 smoke 실패는 위 역사 기록으로 유지한다.

**남은 범위:** API 키는 여전히 없어 live는 `blocked_auth`다. 실제 OpenCode→모델→CVDP end-to-end,
native ACE runner, 전체 sub-agent 사용량 및 성능 개선은 미검증이다. Meta-Harness/GEPA/Ecdysis는
팀 구현용 슬롯이며 이번 evaluator-only 통과가 알고리즘 구현·논문 재현·성능 개선을 뜻하지 않는다.

## 2026-09-21 Optional network environment

환경: macOS arm64, 기본 Python 3.14.5 / uv 환경 Python 3.12.12, uv 0.10.7,
Docker native `linux/arm64`, Compose 5.1.3. Buildx가 기본 CLI에 없어 검증용 임시 Docker config에만
Buildx 0.37.1 darwin-arm64를 설치했다. 공식 release API SHA-256
`c3cbbc820d578b0aa8158dd62ef1af25a0c8a75ef53331dbe4e219471e1dbe8c`와 다운로드 파일을 대조했다.
기본 Docker 설정·데몬은 변경하지 않았다.

| 실제 명령 / 검사 | 결과 |
|---|---|
| `PYTHONPATH=src python3 -m unittest discover -s tests -v` | **169개 중 155 통과·14 skip**, 실패 0. skip: 기존 실도구 9·OpenCode 이미지 선택 1 + 신규 Docker 2·PyYAML 2. 아래에서 Docker/OpenCode/PyYAML을 별도 실행했다. |
| `PYTHONPATH=src python3 -m agent_optimizer run examples/minimal/experiment.toml` | exit 0, completed, 9 trial. `runs/20260920T172527Z-ae724b41/`; 합성 연결 검증. |
| `uv run --frozen --extra dev ruff check .`; `git diff --check` | 통과. |
| `PYTHONPATH=src:tests uv run --frozen --extra dev --with PyYAML==6.0.2 python -m unittest test_network.EvaluatorNetworkTests -v` | **5/5 통과**. 실제 Python wrapper → driver 계약 fixture 실행·결과 수집 포함. 공식 CVDP 시뮬레이션은 아님. |
| `AGENT_OPT_NETWORK_DOCKER=1 PYTHONPATH=src:tests python3 -m unittest test_network.DockerNetworkIntegrationTests.test_actual_build_trust_proxy_history_and_runtime_readonly_ca -v` (임시 `DOCKER_CONFIG`, 현재 context의 `DOCKER_HOST` 지정) | **1/1 통과**. 실제 BuildKit 빌드 중 CA trust/proxy 적용, proxy 비밀값의 image history·ENV 비포함, non-root runtime CA readonly mount와 환경 전달 확인. |
| `AGENT_OPT_NETWORK_DOCKER=1 PYTHONPATH=src:tests uv run --frozen --extra dev --with PyYAML==6.0.2 python -m unittest test_network.DockerNetworkIntegrationTests.test_actual_compose_receives_proxy_and_readonly_ca -v` | **1/1 통과**. 실제 Compose container에서 SSL trust·proxy/NO_PROXY 전달 확인. |
| `AGENT_OPT_CA_BUNDLE=/etc/ssl/cert.pem python3 scripts/network.py -- docker build -f examples/rtl-debugger/Dockerfile -t agent-opt-network-opencode:validation examples/rtl-debugger` (동일 임시 Docker config/host) | exit 0. 공개 CA bundle을 지정한 실제 OpenCode 1.18.31 npm 설치 및 apt Python/Git/CA 설치 통과. |
| `docker run --rm --network none agent-opt-network-opencode:validation opencode --version` 및 Python SSL trust 확인 | `1.18.31`; CA 128개 읽음. |
| `AGENT_OPT_TEST_DOCKER_IMAGE=agent-opt-network-opencode:validation PYTHONPATH=src:tests uv run --frozen --extra dev python -m unittest test_adapters.DockerEnvironmentTests -v` | **1/1 통과**. 기본/명시 provider 설정과 빈 값 동작 유지. `runs/docker-env-regression-f2d2fabc2a77/`. 모델 inference 없음. |

네트워크 회귀는 실제 로컬 HTTPS 서버의 추가 CA 신뢰/미설정 거부와 실제 HTTP proxy 및
NO_PROXY 우회를 포함한다. 프록시 자격증명은 합성 fixture 값이며 외부 proxy 서비스에 접속하지 않았다.
공통 설정의 전달 자체와 특정 배포 환경에서의 연결 성공을 구분한다.

초기 통합 fixture는 Buildx의 registry 인증도 host proxy를 사용한다는 점과 Colima의
macOS 임시 디렉터리 비공유를 반영하지 못해 실패했다. base image를 정상 환경으로 pull하고
local tag를 사용하며 runtime fixture를 공유 workspace 안에 생성하도록 수정 후 통과했다.
실제 npm/apt 빌드에는 bundle을 단일 local CA 파일로 등록하여 `rehash`의 복수 인증서 경고가
있었으나 bundle 기반 trust와 설치는 성공했다. 해당 경고를 TLS 검증 해제로 우회하지 않았다.

코드 리뷰에서 evaluator의 UUID network 이름을 설정 dict로 덮어쓰는 회귀를 발견했다.
설정 없음/있음 두 경우의 문자열 argv·동일 UUID cleanup 검사가 먼저 실패함을 확인한 뒤
변수 분리로 해결했고, 실제 wrapper subprocess 회귀 및 후속 리뷰로 재확인했다.

**이번 작업의 미검증 범위:** 실제 인증 proxy/TLS interception 환경, 추가 CA를 적용한
공식 CVDP 이미지 전체 rebuild·정답/오답 smoke, Ubuntu x86_64에서의 proxy 포함 Docker 통합,
실제 모델 API 호출. 기존 공식 평가 성공 기록은 이전 절의 별도 근거다.

### 후속 Ubuntu 코어 CI

구현 commit `a80cf85`의 [PR run 35526038105](https://github.com/wontaeJeong/agent-optimizer/actions/runs/35526038105)는
Ubuntu Python **3.11/3.12 모두 성공**했다. lint·unit/contract tests·native simulator 검사·
최소 데모·sdist/wheel 빌드·소스 트리 밖 wheel 설치 검사가 통과했다.
공식 CVDP Docker job은 수동 실행 대상이므로 이 PR run에서는 skipped다.
이는 위 Mac Docker 네트워크 통합 검사와 구별되는 원격 코어 CI 근거다.
