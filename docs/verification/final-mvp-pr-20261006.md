# 최종 MVP PR 검증 보완

PR: https://github.com/wontaeJeong/agent-optimizer/pull/64

## 검증과 실패 원인

- PR 생성 전 Mac에서 `make test`: 1160개 중 1080개 통과·기존 skip 80, lint 통과.
- Ubuntu CI `37478167635`: Python 3.11에서 failure 1·error 6, Python 3.12에서 failure 1·error 5. 문서 build `37478172882`는 통과.
- `TMPDIR`가 필수 환경변수라고 가정한 native/plan 테스트는 Ubuntu 기본 환경에서 KeyError. 명시 TMPDIR가 있으면 존중하고 없으면 표준 임시 디렉터리를 사용하도록 수정. plan subprocess의 임시 경계는 테스트가 소유한 디렉터리로 지정.
- 대화형 TUI 진입 테스트가 CI=true를 상속해 정상적인 제품 CI 차단을 실패로 판단. 그 테스트만 CI를 명시 해제하고 CI 강제 진입 금지 테스트는 유지.
- worker의 전역 stderr capture 중 UI thread의 asyncio 로그도 capture에 도착할 수 있으나 기존 코드는 항상 call_from_thread를 사용. 같은 UI thread에서 호출하면 RuntimeError. Textual의 thread-safe post_message와 준비 로그 메시지 handler로 전달하여 UI/worker 양쪽을 안전하게 처리. redaction은 UI handler에서 유지.
- 같은 `CI=true`·TMPDIR 미설정으로 로컬 재현했다. UI thread의 write/flush·worker write/flush·키 미노출을 확인하는 실제 Pilot 회귀는 수정 전 FAIL, 수정 후 통과.
- 최초 보완 후 Mac 전체 재현은 1161개 중 private checker 테스트 1건 실패. 기본 `/tmp`가 symlink인 Mac에서 해당 fixture의 경로가 제품 no-follow 검사에 먼저 거부됐다. 테스트 소유 경로를 canonicalize하여 private checker 변조 검사에 도달하도록 수정; 제품 symlink 거부와 원래 `differs` assertion은 유지.

## 로컬 covering 명령

```bash
env -u TMPDIR CI=true PYTHONPATH=src:tests PYTHONDONTWRITEBYTECODE=1 /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest test_cli_entry test_plan_readonly test_native_cvdp test_native_ace test_progress_capture test_textual_tui -q
env -u TMPDIR CI=true PYTHONPATH=src:tests PYTHONDONTWRITEBYTECODE=1 /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest test_datasets -q
env AGENT_OPT_CORE_PYTHON=/Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python PYTHONDONTWRITEBYTECODE=1 make lint
git diff --check
```

결과: 첫 묶음 72개 통과·두 번째 24개 통과, lint·공백 검사 통과. native 테스트는 pinned upstream·모의 모델/평가 계약이며 native 실모델·EDA 성공이 아니다. CI 수동 실행은 official_cvdp=false·verilog_eval_full=false로 코어·실제 Ubuntu Yosys/Icarus·패키징만 검증하며 전체 CVDP/모델 실행을 요청하지 않는다.

## 전체 회귀 및 설치형 smoke 보완

- 보완 후 로컬 전체 `CI=true`·TMPDIR 미설정 `make test`: **1161개 중 1081개 통과·기존 skip 80개**, 173.909초.
- CI `37480271790`: Python 3.11·3.12의 unit·lint·실제 simulator·endpoint hook·demo·sdist/wheel build 통과. 최종 설치형 smoke만 native-first 이전 PTY 입력에 의존해 실패했다.
- `tests/test_installed_cli.py`는 OpenCode legacy를 명시 선택하도록 입력을 보정하고, 생성 보고서 개수를 App Home에서 검사한다. HOME·AGENT_OPT_HOME을 해당 wheel 테스트 소유 경계로 고정하고, 취소·미구현·이력 조회의 무생성 검사를 App Home까지 강화했다. 외부 ACE 준비 mock은 실제 asset Path 반환 계약을 따른다. Mac의 `/var`·`/private/var`를 같은 실제 경로로 대조한다.
- 최초 로컬 wheel 재현도 PTY 이후 마지막 prepare 경로 비교에서 Mac canonical 경로 차이로 실패했고 실제 경로 대조로 보완했다. 제품 경로나 부작용 계약을 완화하지 않았다.

```bash
env UV_CACHE_DIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-g/uv-cache UV_PYTHON_DOWNLOADS=never uv build --wheel --out-dir /var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-pr/dist
env TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-pr UV_CACHE_DIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-g/uv-cache PYTHONDONTWRITEBYTECODE=1 /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python tests/test_installed_cli.py /var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-pr/dist/agent_optimizer-0.3.0-py3-none-any.whl
```

wheel build 종료 0, 설치형 catalog/TUI/사용자 설정 실제 실행과 legacy GEPA/Meta 생성·prepare의 외부 준비 모의 계약 통과. 이후 lint·공백 검사도 통과했다. 기존 임시 build-env의 build 모듈이 더 이상 준비돼 있지 않아 uv의 격리 build를 사용했다. 원래 공유 코어 환경은 재설치하지 않았다.

## PR CI의 PTY 프레임 경합

수동 CI `37481556906`는 Python 3.11·3.12 전체 단계 통과. 동시에 생성된 PR CI `37481563382`는 Python 3.11의 설치형 PTY 관측에서 실패했다. 입력이 없는 `준비 중` 관측이 한 번에 읽힌 동일 프레임의 `Doctor로 계속`까지 소비하여, 다음 단계가 재출력되지 않는 marker를 기다렸다. 실제 프로세스가 한 프레임에 세 marker를 출력하는 회귀로 12초 timeout을 재현했다. 관측만 하는 단계는 cursor를 유지하고 실제 입력을 보내는 단계만 이전 프레임을 소비하도록 수정했다. 제품 준비 상태·timeout·필수 marker assertion은 바꾸지 않았다.

보완 후 `PYTHONPATH=src:tests PYTHONDONTWRITEBYTECODE=1 <공유 Python> -m unittest test_installed_cli_protocol -v`는 1개/0.269초 통과. 위 실제 설치형 smoke와 lint·공백 검사도 다시 통과했다. 진행 중 main에 PR #65의 CI Gate·squash 정책이 병합되어, 해당 최신 main을 작업 브랜치에 일반 merge로 반영하고 PR CI Gate의 새 성공을 확인한다. main이나 다른 작업의 변경을 덮어쓰지 않는다.

## 최신 main 병렬 CI 통합

- PR CI `37482794880`의 Python 3.11·3.12·CI Gate와 문서 build는 모두 통과했다. 병합 직전 main에 PR #66의 격리 병렬 테스트 실행기가 추가돼, `docs/verification.md` 충돌은 양쪽 검증 기록을 모두 보존하여 해결했다.
- 새 병렬 모듈 순서에서 기존 report server import 테스트의 전역 `importlib.reload`가 다른 모듈이 이미 보유한 예외 class와 새 class의 identity를 분리했다. report_view를 먼저 import하고 server tests → port 진단 tests를 실행하는 실제 18개 회귀로 Cause 안내 누락을 재현했다. import 순수성 검사는 fresh subprocess에서 bind/browser 차단 하에 수행하도록 바꾸어 worker 내 class를 교체하지 않는다. 제품 예외 처리나 진단 assertion은 변경하지 않았다. 같은 18개 회귀는 통과했다.
- 로컬 공유 interpreter가 기본 checkout의 editable 설치를 가리키므로 병렬 실행에도 `PYTHONPATH=src:tests`를 명시해야 한다. 최초 경로 미지정 실행의 old-code import 실패는 제품 결과로 계산하지 않는다.
- `CI=true`, TMPDIR 미설정, 고유 임시 HOME·AGENT_OPT_HOME, `PYTHONPATH=src:tests`, `PYTHONDONTWRITEBYTECODE=1`로 `<공유 Python> scripts/run_tests.py --jobs 2` 실행: **1169개 중 1089개 통과·기존 skip 80개, failure/error 0, 118.631초**. 최신 main의 parallel runner와 본 작업의 신규 회귀를 함께 검증했다.
