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

## 2026-09-20 Task 5 실제 환경 검증 — 전체 smoke는 차단 상태

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

### Controller 결정이 필요한 T4 차이

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
