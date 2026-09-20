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
