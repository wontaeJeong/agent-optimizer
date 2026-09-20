# 검증 기록

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

**수정 후 native Ubuntu/BuildKit 공식 smoke는 controller의 push·원격 재실행 대기 중이다.**
이 로컬 smoke의 build 로그는 legacy `Step 1/2` 형식이며 native Ubuntu fix 검증을 대신하지 않는다.
본 wave는 모델 inference를 실행하지 않았다. 새 원격 정답/오답 raw 결과를 확인하기 전 native 공식
통합 완료로 표시하지 않는다.
