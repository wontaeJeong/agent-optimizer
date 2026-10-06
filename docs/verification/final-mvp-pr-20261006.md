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
