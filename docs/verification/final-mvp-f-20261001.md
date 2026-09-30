# 최종 MVP F — 제품 연결·검증·G 인계

확인일: 2026-10-01. **F 제품 연결과 전용/관련 검증 완료. 전체 suite는 G의 환경·공유 assertion 정리가 남아 실패하며, native 실환경과 실제 wheel 배포는 not_run이다.**

## 1. 기준·소유 범위

- 지정 워크트리 `.worktrees/final-mvp-20261001`, 브랜치 `feat/final-mvp-20261001`, 시작 HEAD `ff0d6dc`.
- `F_PRODUCT_WIRING.md`를 먼저 읽고 P0·A~E 검증 문서의 계약 및 마지막 수정 handoff를 소비했다. CodeGraph 인덱스는 없으며 만들지 않았다.
- 수정: `cli.py`, `tui.py`, `preset_tui.py`, `setup_wizard.py`, `catalog.py`, `registry.py`, 연결에 필요한 `config.py`·`integrations.py`·`runner.py`.
- 신규: `native_selection.py`, `native_summary.py`, `report_view.py`; 전용 테스트 `test_cli_entry.py`, `test_product_wiring.py`, `test_product_tui.py`, `test_product_package.py`, `test_native_product.py`, `test_native_producer.py`.
- C 내부 native loop·예제, D renderer, G의 `models.py/contracts.py/locale.py/pyproject.toml/uv.lock/readiness.py`와 기존 공유 테스트는 수정하지 않았다. 총괄의 의도된 `final-mvp-progress-20261001.md` 변경을 보존하고 함께 로컬 커밋한다.
- 하위 에이전트·설치/sync·다운로드·live 모델·실 Docker/EDA·push/PR 없음. 공유 Python은 실행에만 사용했다. Home/output/cache 및 신규 fixture는 승인된 `/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f` 아래다.

## 2. 실제 제품 연결

| 요구 | 구현·검증 |
|---|---|
| 진입 | 무인자 + stdin/stdout/stderr TTY + 정상 TERM + CI 아님이면 기존 Textual 앱. pipe/nonTTY/CI/dumb·unknown TERM은 기존 help 종료 2. `--help`는 도움말, 명시 `tui` 계약 유지 |
| Home 설정 | 새 설정은 `Home/experiments/<이름>-<uuid12>/experiment.toml`. `project_root` 절대 provenance와 `config_root="."`; Agent/Harness/tasks만 설정 경계 상대 참조. 새 `output_dir` 생략. 동일 이름 재생성도 독립 경로 |
| 원본 참조 | custom/등록 플러그인은 원본 project 기준. local source와 local Git locator는 원본 절대경로 보존. source checkout·package-only에서 다른 CWD의 생성→plan→doctor→run→JSON 검증 |
| 자산·cache | 등록 provider는 A cache resolver, CustomDataset은 기본 Home cache. source checkout의 선택형 helper는 해시별 `Home/assets/<integration>-<digest16>`에 복사하여 준비. 충돌 파일은 보존·거부. 기존 명시 workspace/pointer 유지 |
| output/session | A `resolve_run_base` 우선순위 유지, session 기본 `Home/sessions`. all-error session summary를 error로 정렬. spawn/jobs 및 독립 dataset 평가 유지 |
| native 기본 선택 | ACE-RTL의 첫 Harness는 Python native. CLI `ace_native`/`ace-native` 모두 수용; adapter ID는 `ace_native`, C 원본 profile ID는 `ace-native`, Agent ID는 `ace-rtl-native`, Evaluator ID는 `cvdp_native` |
| native 선택 | 명시 CID·row→split 필수. TUI는 고정 데이터의 row 목록·target·도구·지원/제외 원인을 표시하고 train/validation/test를 직접 선택. 자동 dataset/row 추천 없음. JSON 직접 입력도 유지 |
| 실제 수정 표면 | C의 `source-native.toml`·`harness-native.toml`을 소비. GEPA `native/guidance.md`, Meta-Harness `native/orchestration.py`/`guidance`. 존재·editable·Python 구문/symbol 확인. coding guidance/scaffold로 대체하지 않음 |
| 모델 | native Agent 세 역할은 공통 API 세 환경값만 필요. Baseline은 Optimizer API를 추가 요구하지 않지만 native Agent API는 필요. coding selector와 기존 프로필 보존. B의 실행 환경을 worker에 소비하며 키는 TOML/argv/보고서에 쓰지 않음 |
| private 보호 | native preflight/prepare에서 public descriptor·prompt·files·trusted 평가 row/targets를 고정 JSONL과 재대조. 복사된 legacy benchmark는 준비 원본과 바이트 대조. benchmark를 candidate seed로 복사하는 것은 실행 생성 전 거부 |
| 이력 | A 원래 dict row/inode를 보존. 실패·중단·report 없음·session 및 선택한 기존 실험/Result의 명시 output parent 조회. session은 실제 child 결과 선택. 조회만으로 Home·평가·모델·서버를 만들지 않음 |
| 보고서 | A 재검증→E HTML-only 서버. CLI foreground/Ctrl+C, TUI 별도 worker·epoch/lock·종료 cleanup. 같은 run도 기존 handle을 닫고 재시작하여 HTML 재생성을 반영 |
| 브라우저 | URL 먼저 표시. 별도 소유 Python helper를 argv/shell=False로 실행, 5초 상한·출력 폐기·모델 credential 미전달·timeout 시 소유 process group 회수. 실패에도 직접 URL과 SSH localhost 의미 안내 |

연구 알고리즘은 기존 자체 구현이며 upstream 완전 재현으로 표현하지 않는다. Planned 옵션은 disabled 상태를 유지한다. native/in-process 플러그인은 OS 보안 sandbox가 아니다.

## 3. 새 CLI·경로 계약

### native init

추가 옵션: `--cid`(반복), `--rows`(ID→split JSON), `--native-dataset`, `--native-source` 또는 `--native-upstream`, `--native-python`, `--native-evaluator`(repo/python/sim_image/sim_image_id JSON).

아래는 **사용법 예시이며 실환경 실행하지 않았다**. 실제로 준비한 절대경로를 지정해야 한다.

```bash
agent-opt init --agent-preset ace-rtl --harness-profile ace_native --dataset cvdp --optimizer gepa --cid cid002 --cid cid016 --rows '{"cvdp_copilot_64b66b_decoder_0001":"train","cvdp_copilot_32_bit_Brent_Kung_PP_adder_0001":"validation"}' --native-source /absolute/prepared-source --native-dataset /absolute/pinned-data.jsonl --native-evaluator '{"repo":"/absolute/cvdp","python":"/absolute/driver/bin/python"}' --yes
```

- `--native-upstream`은 사용자가 고른 **로컬 고정 checkout**을 C helper로 export한다. Home/assets 안의 임시 staging→검증→고유 source publish이며 원본은 변경하지 않는다. 자동 fetch/설치/online 복구는 없다.
- 네 CID를 선택할 수 있지만 C의 row 판정이 우선이다. CID007 PNR·상용 helper 등 제외 row를 골랐으면 이유와 함께 실패한다. 그 row를 삭제하여 성공 설정으로 바꾸지 않는다.
- native는 지정한 row 전체를 그대로 생성한다. 일반 `max_tasks`로 몰래 재샘플링하지 않는다. train/validation/test와 final_test는 명시 split에 따른다. Review와 writer는 같은 예약 trial budget을 사용한다.
- `AGENT_OPT_MODEL_BASE_URL`, `AGENT_OPT_MODEL_ID`, `AGENT_OPT_MODEL_API_KEY`는 환경/현재 세션에서만 전달한다. NVIDIA key·`AGENT_OPT_MODEL`은 native 필수값이 아니다.
- native component 출처는 명시 workspace → 실행 코어의 source checkout → 설치 distribution이 선언한 `share/agent-optimizer` 자산이다. 임의 CWD를 원본 프로젝트로 가장하지 않는다. custom/기존 실험의 원본 project 참조는 유지된다.

### report

```bash
agent-opt report RUN --serve
agent-opt report RUN --html --serve --no-open --port 0
agent-opt report RUN --json
```

- `--serve`: 저장된 HTML만, 고정 loopback/자동 포트/기본 브라우저 요청. `--html --serve`: 명시 재생성 후 serve. Ctrl+C 종료 130, finally close. stdout은 비우고 URL/안내는 stderr.
- `--json --serve`, `--csv --serve`, `--csv --html`, `--csv --json`, serve 없는 `--no-open/--port`, 범위 밖 port는 파일 읽기/생성·bind·browser 전에 종료 2.
- `--json` 및 기존 기본 report stdout은 JSON 한 값. `--html --json`은 재생성 결과 JSON 한 값. E allowlist는 HTML 한 파일뿐이며 session child는 별도로 선택한다.

## 4. loader 충돌과 additive schema

**C loader 충돌:** 기존 harness allow-list가 `native`·`compatibility`를 Unknown keys로 거부했다. 두 객체와 알려진 키/타입/절대경로·iteration/timeout을 검증하는 최소 loader 연결을 추가했다. 알 수 없는 credential 필드는 거부한다.

**Home seed:** 새 optional `candidate_seed_root="project"|"config"`와 내부 `_seed_root`. 기본은 기존 project 그대로다. 새 legacy Meta-Harness의 패키지 scaffold 복사본만 `config`를 명시하여 Home 밖 원본 프로젝트에 파일을 쓰지 않는다. editable/build 검증·snapshot 생성·seed hash 기록은 유지하고 private benchmark seed는 거부한다.

### native producer → D

- `RunRequest.logs`는 native만 `<group>/trials/<trial>/logs`; 기존 프로필의 `harness_logs`는 유지. D의 실제 evidence prefix와 맞췄다.
- `summarize_native(logs, *, task_id, candidate_hash, profile, outer_count, outer_wall_time, generated_targets=(), source_revision=None, source_hash=None) -> dict | None`.
- `native-execution.json`을 일반 파일/no-follow/nonblock/1 MiB로 읽고 version/mode·outer identity·원본 candidate source-lock provenance를 대조한다. source-lock도 원본 candidate에서 제한적으로 읽는다.
- P0 version 1 whitelist 필드를 같은 `record.native_execution`으로 `result.json` 및 `trial_completed`에 저장한다. 임의 중첩 필드·prompt/RTL 본문·원 private 절대경로·키는 복제하지 않는다. 요청 ID 중복은 합산하지 않고, 실제 선언 target만 생성 파일 목록에 남긴다.
- source provenance는 nullable, 수치는 유한 비음수·tokens/iteration은 정수, 미수집은 null. usage는 partial/unreported이며 전체 사용량으로 승격하지 않는다.
- additive `outer_evaluation={purpose:"trusted_final", owner:"GroupRunner.trial", count, wall_time_seconds}`, 안전한 `active_surface_hashes`, `readiness_checks[id/ready]`, `cleanup.status`를 보존한다. PID/network/raw diagnostic은 복제하지 않는다.
- 실제 outer Evaluator 진입을 계측한 `metrics.native_outer_evaluation_count`와 `native_outer_evaluation_wall_time_seconds`를 추가한다. Agent/native wall time·요청 시간·inner 횟수를 합쳐 같은 이름으로 쓰지 않는다.
- 손상/누락 요약은 optional native만 제외하고 `native_execution_diagnostic.code="missing_or_invalid_sidecar"`를 남긴다. outer 평가 자체를 삭제하거나 성공으로 바꾸지 않는다.
- D의 v3 normalized native 섹션은 기존 whitelist 그대로 소비한다. 위 additive 진단/outer 객체는 raw result/events에 보존되며 D가 새 그림으로 재설계하지 않았다. outer 계측 지표는 일반 metrics에도 있다.

공개 소비 함수: `report_view.report_row/start_view/open_browser/view_status`, `integrations.launch_existing/stage_local_integration/verify_local_helpers`, `setup_wizard.recent_configurations`, `native_selection.write_native_selection/available_rows/inspect_selection/verify_native_selection/resolve_native_project/native_trial_budget`.
`prepare_ace_selection`은 준비한 asset `Path`를 반환하고 `write_ace_selection(..., asset_root=...)`가 이를 소비한다. `execute_ace_selection/run_ace_selection`은 optional `output`을 runner에 전달한다.

## 5. 정확한 검증 명령·결과

모든 CWD는 지정 통합 워크트리다. `env -i`로 개인 모델 환경/키 상속을 차단했다. 신규 tests는 전용 TMPDIR 아래 고유 TemporaryDirectory를 사용한다.

### F 전용 및 선행 계약 회귀 — 최종

```bash
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/home TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/tmp /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest test_cli_entry test_product_wiring test_product_tui test_native_producer test_native_product test_product_package test_app_paths test_history test_native_ace test_native_cvdp test_final_report test_report_server test_plugin_contracts test_research -q
```

**175개 / 18.824초 / OK / 종료 0 / skip 없음**. F 신규 31개와 관련 144개다. 직전 확장 회귀도 172개/18.715초 OK였다. 마지막 dedicated 실행은 timeout test 추가 전 30개/4.290초 OK이며, 추가 1개도 최종 175개에 포함해 통과했다.

검증 수준:

- 실제 fixture CLI init→run→HTML/history→localhost GET→SIGINT(130)→socket 종료; TUI worker 재열람·재생성·session child·명시 output 이력·앱 종료 cleanup.
- 실제 source checkout 및 examples/marker 없는 **package-only 복사 레이아웃**에서 두 subprocess CWD의 custom Agent/채점기 생성→plan→정적 doctor→run→JSON. 설치 distribution native 자산 출처는 모의 metadata+실제 복사된 파일로 검증.
- native writer는 C 파일·파서·실제 registry/config/runner/report를 소비하되 F native 실행/outer 평가와 dataset SHA는 명시 fixture 경계로 대체했다. 실모델/실 native 도구 성공 증거가 아니다.
- C 기존 테스트는 고정 upstream/데이터를 읽기 전용으로 사용하고 모델·평가를 모의한다. yaml stub은 C test-local 조건이며 제품 fallback이 아니다.
- CLI browser 성공/오류는 외부 실행만 모의하고 실제 HTTP GET·close를 확인했다. timeout은 실제 소유 sleep process를 짧은 wait fixture로 종료·reap했으며 OS 브라우저는 열지 않았다.
- RED에서 진입/Home/JSON 누락 3개, sidecar producer 부재, copied private benchmark 보호 2개, benchmark seed 보호를 재현했다. 이후 최종 GREEN. 중간 Native 페이지명·uuid local shadow·baseline stages 누락도 수정하여 최종 검사에 반영했다.
- 첫 Home RED가 워크트리 `runs/configs/f-fixture`에 만든 네 파일/빈 디렉터리는 본 작업 산출물임을 확인하여 제거했다. 최종 실험 산출물은 전용 임시 경계만 사용한다.

### 전체 suite — 최종, 녹색 아님

```bash
env -i PATH=/Users/wt.jeong/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests AGENT_OPT_LANG=ko HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/finish-user-home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/finish-home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/finish-cache TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/tmp UV_PROJECT_ENVIRONMENT=/Users/wt.jeong/workspace/agent-optimizer/.venv UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -c "import unittest; from unittest.mock import patch; suite=unittest.defaultTestLoader.discover('tests'); browser=patch('agent_optimizer.report_view.open_browser', return_value=False); browser.start(); result=unittest.TextTestRunner(verbosity=1).run(suite); browser.stop(); raise SystemExit(not result.wasSuccessful())"
```

**1121개 / 149.111초 / FAILED(failures=41, errors=41, skipped=80), 종료 1.** browser 외부 경계만 전체 실행에서 모의했고 F browser 전용 테스트는 그 안에서 실제 helper를 복원하여 자신의 외부 실행 fixture로 검증했다. 테스트를 삭제/skip하거나 `.venv` symlink를 만들지 않았다.

- 오류 15건: P0의 worktree-local `.venv/bin/python/agent-opt` hardcode 그대로.
- 나머지는 Home UUID 설정 경로·seed의 `_seed_root`·dict history·native-first/추가 row 단계·안정 ID 대신 숫자/Enter 횟수·새 asset Path 반환 및 output kwargs를 기대하지 않는 기존 공유 fixture/assertion이다. Endpoint password 옛 기대, XDG cache 기대, TMPDIR의 `opencode` substring 오인도 유지된다. G가 아래 계약대로 취합해야 한다.
- 로그: `/Users/wt.jeong/.local/share/opencode/tool-output/tool_0f425c91a001tl0VFh2vh8j4ne`. 이전 전체 실행 1118개/148.849초 및 1112개/146.572초도 같은 41 failure/41 error/80 skip이었다. 이전 로그는 `tool_0f3fde8cd001WLVLLDjPEOA9j1`, `tool_0f3d4b774001FPiRaCFFmg101p`다.

### lint·캡처·배포 환경 확인

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m ruff check . --no-cache
git diff --check
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/home TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/tmp /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python /var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/capture_product.py
/Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -c "import importlib.util; print({name: importlib.util.find_spec(name) is not None for name in ('build','setuptools','wheel')})"
```

Ruff `All checks passed!`, diff 검사 종료 0. 캡처 80×30 SVG:
`final-mvp-f/captures/{before-harness,after-harness,after-native-selection,after-native-rows}.svg`.
변경 전은 `git archive ff0d6dc src/agent_optimizer`를 전용 임시 경계에 추출해 같은 Harness 화면을 재현했다. 새 row 화면은 public fixture이며 실제 데이터/모델 성공 캡처가 아니다.

배포 환경 확인은 `build=True, setuptools=False, wheel=False`. 따라서 설치/sync 없이 **실제 wheel build/install은 blocked/not_run**이다. package-only/모의 distribution 검증을 실제 wheel 검증으로 표현하지 않는다.

## 6. G 정확한 인계·남은 검증

1. **`readiness.collect_plan` native 검사:** `native_selection.verify_native_selection(spec)`를 읽기 전용 fixed dataset/public/evaluation check로 소비. C `preparation(spec['_root']).readiness(agent.source.path, profile['native']['python'])` 결과를 native_source/native_python check로 연결. `ps`, native Python 3.12/yaml/pydantic_settings, CVDP repo/driver Git pin·OSS_SIM image identity·native baseline 포함 Agent API 세 환경값을 검사. 모델 호출은 기존 `model=True`에만 허용. `cvdp_native` 및 nullable provenance/cleanup을 소비하며 coding readiness로 대체하지 말 것.
2. **Home/seed/legacy readiness:** `_seed_check`의 source 기준을 `spec.get('_seed_root', spec['_root'])`로 변경하고 benchmark seed 거부를 runner와 일치시킬 것. `_ace_asset_check`와 dataset doctor는 생성 config의 evaluator asset root/`resolve_dataset_cache`를 사용. 원본 `_root` 및 오래된 explicit TOML의 의미는 유지. `prepare_ace_selection` 반환 Path와 원본 프로젝트 provenance를 혼동하지 말 것.
3. **공유 tests:** 각 fixture의 AGENT_OPT_HOME을 자기 TemporaryDirectory로 격리. init 결과 JSON의 `experiment/session`을 정본으로 사용하여 `runs/configs/<name>` hardcode 제거; old explicit output 회귀는 유지. seed는 `_seed_root`, history는 `row['run_id']/run_dir/status/report_path`와 원래 row를 사용. legacy 모델 시험은 `ace-opencode` ID를 명시 선택하고 numeric index/고정 Enter 횟수를 없앨 것. native-first 시험은 NativeRows/NativeSplit을 직접 선택. preparation mock은 실제 준비 asset Path를 반환, 실행 mock은 optional `output` kwargs 수용. Endpoint 평문·credential 거부 정책 및 native unsupported/private 경계 시험은 약화하지 말 것.
4. **기존 환경 오류:** interpreter/entrypoint를 `sys.executable`·module entrypoint로 바꾸고, XDG 기본 기대를 App Home cache로 변경. `test_dev_environment.py:686`은 argv 전체 경로 substring 대신 실제 executable/image 인수를 구분. 전체 suite 로그의 실패 이름을 기반으로 취합하며 skip/hide 금지.
5. **배포/dep:** source-free native 소비 hook은 구현됐다. G는 `pyproject.toml` wheel data-files에 `registry.NATIVE_DEPENDENCIES`와 `examples/ace-rtl/native_adapter.py`를 **원래 하위 구조 그대로** `share/agent-optimizer/examples/ace-rtl/...`에 포함해야 한다(특히 두 TOML·native_artifacts/native_cleanup·기존 evaluator/network driver·guidance/orchestration). distribution.files/locate_file로 출처를 소비하는 계약이다. native Python의 yaml 의존성을 선택형 준비/lock에 취합하고 Core Python 범위를 무단 축소하지 말 것. 기존 first-party pin `ae0874...`은 native를 포함하지 않아 자동 pin 갱신/다운로드로 대체하지 않았다. 자산 없는 old wheel은 명시적으로 실패한다.
6. **locale/모델 환경:** Native/NativeRows/NativeSplit/SessionHistory, CID·row·target·split, URL/browser/SSH·재생성/진단 안내를 locale에 취합. B의 worker `session_environment` 전역 env 임시 변경은 아직 같은 프로세스의 겹치는 worker 완전 격리를 증명하지 못했으므로 G의 실행 경계 취합 대상이다. F는 `models.py/contracts.py` 변경을 요구하지 않는다.

**not_run:** 실제 native 모델/API·실 CVDP Docker/EDA·Ubuntu x86_64·실 브라우저/SSH·실 wheel build/install·G 준비 후 통합 native 실행. F는 실제 loopback HTTP·OS process/SIGINT·합성 runner·계약/Pilot 증거까지 완료했으며, 이 미검증 영역을 성공으로 기록하지 않는다.

최종 자체 검토는 요청 계획·소유권·flat 계약·비밀·snapshot·private/test·JSON·server 수명을 diff와 위 검사로 대조했다. 하위 에이전트 리뷰/자동 merge 없이 지정 워크트리에 한국어 로컬 커밋만 남긴다.

## 7. 수정 라운드 1 — 독립 리뷰 R1~R4 대응

확인일: 2026-10-01. 기준 HEAD `0a9fe842eaf13d1a5b8b5be3ebbe5fc4c73513a4`. `final-mvp-f-review-20261001.md` 전체를 읽고 Important 3건·Minor 1건을 재현했다. 총괄이 승인한 예제 소유 변경을 사용하며 리뷰 원문은 보존하여 이번 의도된 커밋에 포함한다.

### 실제 수정

- **R1 — 선택 무효화:** Native JSON/경로 입력과 NativeSplit의 변경·제거가 같은 `_invalidate_native_configuration()`을 호출한다. 변경된 값은 보존하고 이전 `experiment`, 준비 완료/오류, doctor 결과/오류, stale target preview만 무효화한다. 원래 TOML은 삭제하지 않는다. 동일 값 재확정은 설정을 무효화하지 않는다. source/rows를 실제 UI 경계에서 바꾸고 Back→재확인→실제 writer→실제 runner/TUI execute까지 새 source/task/split이 소비됨을 검증했다. 모델/Agent·평가 실행만 계약 fixture이며 live 호출은 없다.
- **R2 — optional 오류 격리:** 숫자 검사에서 Python int를 `math.isfinite`로 float 변환하지 않는다. `sys.float_info.max`를 넘는 정수와 비유한/음수/bool/문자열/객체 숫자는 안전한 `ValueError`로 optional 요약을 제외한다. None/수집된 0은 유지하고 `OverflowError`도 요약 경계에서 차단한다. runner의 optional evidence/summary 단계 오류 역시 native만 제외해 `missing_or_invalid_sidecar` diagnostic을 남긴다. 실제 완료된 outer 평가·`result.json`·`trial_completed`·HTML은 유지된다.
- **R3 — examples 정책 경계:** 코어 `native_selection.py`는 출처 해석·helper 로드·인자 전달만 남긴 thin 연결이다. CID 범위, row eligibility·private 평가 원본 대조, native profile 제한, source pin/target evidence, guidance/orchestration 파일·symbol, stage/budget 정책, CLI/TUI native 선택 필드 검증은 **`examples/ace-rtl/native_selection.py`**에 있다. 예제 생성은 기존 generic `app_paths`/`setup_wizard.write_experiment`를 소비하며 공통 Home·config_root·소스 provenance·writer를 예제로 복제하지 않았다.
- **runner 연결:** `ACENative.validate_experiment(spec, profile)`과 `native_evidence(candidate, task, profile)`을 예제에서 제공한다. core preflight는 등록 Harness의 optional 검증 hook을 호출하며 CVDP row/schema를 재구성하지 않는다. native mode는 일반 execution_mode metadata를 소비하고 source-lock 위치·target 추출은 예제 hook이 담당한다. 새 범용 provider 계층은 추가하지 않았다.
- **loader:** 공통 loader는 native 객체·공통 compatibility metadata의 구조를 처리한다. ACE의 iteration/timeout·CVDP evaluator 필드 제한은 예제 `validate_profile`에서 생성/실행 전 검증한다. 다른 팀 native 설정도 자기 Harness 정책을 거칠 수 있으며 private 보호를 완화하지 않았다.
- **R4 — Review:** 준비 전은 선택된 rows, 준비/기존 설정은 실제 `_tasks`와 `final_test`에서 train/validation/test 수를 표시한다. native Dataset 설명도 명시 row 선택으로 바꿨고 legacy 두 과제 설명은 legacy Harness에만 남겼다. validation 2/test 1의 Review와 생성 TOML이 `train 0 / validation 2 / test 1`, `final_test=true`, trial budget 4로 일치한다.

### 의미 있는 covering·RED→GREEN

- 신규 covering 8개: 7개 native 필드의 설정/진단 무효화, JSON row 변경·row-picker split 변경/삭제·source 변경 후 실제 재생성/실행, 준비 전/후 Review final_test 일치, optional 숫자 7개 위치의 `10**400`, `1e999/-1e999/음수/bool/문자열/객체`, overflow 후 실제 outer trial 파일/event/보고서 보존, 예제 eligibility 변경의 thin facade 소비, 일반 팀 Harness의 native 설정·검증 hook.
- 최초 R1/R2/R4 실행: **4개/1.212초 FAILED(failures=2, errors=10)**. 7개 숫자 위치와 실제 trial finally의 OverflowError, 이전 TOML 재사용, Review 불일치를 확인했다. R1 assertion 직후 테스트 종료에 남은 Highlight 메시지가 추가 NoMatches를 만들었으며 `pilot.pause()`로 UI 경계를 동기화했다. 이후 같은 4개는 **1.736초 OK**였다.
- 추가 비유한/잘못된 숫자 RED: **1개/0.007초 FAILED(failures=6)**. 숫자를 null로 바꾸어 optional을 남기는 경로를 확인하고 optional 전체 제외로 수정했다.
- 보호 의미는 유지: private 평가 row 변조의 실행 생성 전 거부, source/template/active 파일 대조, benchmark seed 거부, train/test 경계, sidecar identity/provenance, 키 sentinel 부재, JSON/serve/server cleanup 회귀를 모두 포함한다. true bug를 skip으로 숨기거나 기존 공유 assertion을 변경하지 않았다.

### 정확한 최종 명령·결과

모든 CWD는 지정 통합 워크트리이며 shared Python 실행만 사용했다. `env -i`와 F 전용 Home/TMPDIR 경계를 유지했다.

```bash
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/home TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/tmp /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest test_cli_entry test_product_wiring test_product_tui test_native_product test_native_producer test_product_package -v
```

**39개/6.844초 OK**, 종료 0, skip 없음. 기존 F 31개 + 라운드 1 covering 8개다.

```bash
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/home TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-f/tmp /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest test_cli_entry test_product_wiring test_product_tui test_native_product test_native_producer test_product_package test_native_ace test_native_cvdp test_plugin_contracts test_research test_run_lifecycle test_app_paths test_history test_final_report test_report_server -q
PYTHONDONTWRITEBYTECODE=1 /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m ruff check . --no-cache
git diff --check
```

**209개/22.264초 OK**, 종료 0, skip 없음. 직전 확대 실행은 비유한 숫자 covering 추가 전 208개/22.399초 OK였다. Ruff `All checks passed!`, diff whitespace 검사 종료 0. asyncio debug가 동기 fixture run의 약 0.1초 task 관측을 출력했으나 테스트 실패/생략은 없다.

### 후속 소비·미검증 범위

- G의 native wheel data-files/선택형 dependency 및 fingerprint에 새 **`examples/ace-rtl/native_selection.py`**를 포함해야 한다. `NATIVE_DEPENDENCIES`에는 추가했다. 고정 upstream SHA는 바꾸지 않았다.
- G readiness는 기존 thin `verify_native_selection`을 소비할 수 있고, 일반 Harness 검증은 optional `validate_experiment(spec, profile)`을 사용할 수 있다. native profile의 도메인 제한은 `examples/ace-rtl/native_selection.validate_profile`을 소비한다. G 공통 models/contracts/locale/dep·공유 assertion 수정 책임은 기존 인계를 유지한다.
- 전체 공유 suite는 이번 수정 라운드에 재실행하지 않았다. §5의 1121개/41 failure/41 error/80 skip은 이전 시점 증거이며 R1~R4 통과와 구분한다. 전체 녹색 또는 새 G 준비 완료를 주장하지 않는다.
- 실제 native/모델/Docker/EDA/Ubuntu/wheel/브라우저·SSH 및 새 화면 캡처는 이번 라운드 **not_run**이다. 변경 내용은 actual fixture/Pilot/runner/record/evidence 검증으로 확인했다. 사용자 Home, install/sync/live, 하위 에이전트, push/PR 없음.
