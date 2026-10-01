# I — 최종 통합 수용검증·실제 결함 수정

확인일: 2026-10-01. **DONE / concerns: 완료 29·부분 1·차단 0. 전체 1157개 중 실행 1077 통과·기존 skip 80, 실패/오류 0. native 실모델·EDA live는 `not_run`이다.** ‘완료’는 아래 요구별 명시된 fixture/계약/실제 제품 실행 범위이며, 모든 실제 Agent의 성능 검증을 뜻하지 않는다. R16은 실행 배선·고정 upstream fixture를 검증했지만 실제 native 데모의 모델/공식 EDA 실행 근거가 없어 부분이다.

## 1. 기준·소유 경계·SHA

- 작업: `/Users/wt.jeong/workspace/agent-optimizer/.worktrees/final-mvp-20261001`, `feat/final-mvp-20261001`.
- 시작 SHA: `51b905d46023b648d8e3e1ed7884fe3eb6a43ed6`. 검증된 수정 코드 SHA: **`17d350198a83910da7b832fda971b495db58f819`**. 이 보고서를 담는 후속 문서 커밋은 코드 검증 대상을 바꾸지 않으며 최종 반환 SHA는 그 문서 커밋이다.
- `I_FINAL_ACCEPTANCE.md`를 먼저 읽고 `02_REQUIREMENTS_MATRIX.md`, P0·A~H 보고서의 최신 append, progress ledger를 읽었다. A~H 독립 리뷰/fix 승인은 사용자 인계를 소비했고 I가 독립 reviewer를 새로 실행했다고 주장하지 않는다.
- 기본 repo `main`의 기존 `.gitignore` 변경·지시 ZIP 및 다른 worktree를 보존했다. `.codegraph/`가 없어 인덱싱하지 않았다. 하위 에이전트·push/PR·live·외부 자산 다운로드·공유 `.venv` 설치/수정 없음. 한국어 로컬 커밋만 수행했다.
- 공유 Python `/Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python`은 실행만 사용했다. Python 3.12.12, 기존 uv 0.10.7. I의 모든 fixture/Home/cache/build/wheel/output은 아래 고유 경계다. 실제 개인 Home/키는 검증 입력으로 사용하지 않았다.

```bash
I=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-i
G=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-g
PY=/Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python
```

macOS의 `/var`와 `/private/var`는 같은 승인 경계다. 아래 변수는 **실제 실행한 절대경로의 약기**다. 기본 CWD는 작업 worktree이며 별도 표시한 명령만 다른 CWD다. G의 준비된 build interpreter/cache/requirements를 읽기·실행 재사용했고, 실제 설치는 I의 새 wheel-env에만 했다.

## 2. 발견 → 원인 → 최소 수정 → 회귀

| 발견 | 실제 RED·원인 | 수정·GREEN |
|---|---|---|
| 일반 fixture/custom CONFIG의 `prepare --offline` 종료 2 | 실제 source CLI init 후 prepare가 `선택형 연동 실험 선언 형식` 오류. integration/preset/native가 아닌 실험까지 ACE pointer로 보냈다. `test_final_acceptance...test_fixture_prepare_checks_existing_experiment_without_ace_or_run`도 1 failure RED | 기존 `load_experiment`·`runner.preflight`를 소비해 일반 실험의 준비 확인으로 분기. `scope=preflight`, `live=not_run` 명시. 기존 등록/평가/seed/미구현 거부를 유지하고 설치·모델 호출·run 생성 없음. source·실제 wheel CLI 여정을 재실행 |
| native `prepare`가 `source.subdir` 무시 | nested `container/active`의 유효 고정 source가 prepare 종료 2. doctor/runtime은 active를 쓰지만 prepare는 container를 검사했다. covering 1 failure RED | 기존 `safe_path(agent.source.path, agent.source.subdir)`로 실제 root를 검사. 같은 fixture의 active pin 파일 변조는 여전히 종료 2, sibling 원본으로 대체하지 않음 |
| 실제 `make test`에서 개발 명령 테스트 4 failure | `AGENT_OPT_CORE_PYTHON` 상속으로 프로젝트-local/누락 Python/Ruff/PATH-discovery fixture가 공유 interpreter를 잘못 소비. 제품 override는 정상 동작 | 해당 default-project fixture에서 override만 제거하고 원래 argv·exit·설치 금지 assertion 보존. override 자체의 별도 G 회귀도 실행. 관련 48개 OK, override를 명시한 실제 전체 make 1157개 OK |

수정 파일: `src/agent_optimizer/integrations.py`, `cli.py`, `locale.py`, `tests/test_final_acceptance.py`(신규 2개), `tests/test_dev_onboarding.py`, `tests/test_menu.py`, `README.md`. 최종 근거 연결은 이 보고서·`docs/status.md`·`docs/verification.md`·progress ledger만 최소 갱신한다. upstream pin/계약/lock/스케줄러/알고리즘/평가 기준은 수정하지 않았다.

개발 중 I 도구 자체의 잘못된 assertion도 숨기지 않는다. Markdown에 run ID가 반드시 표시된다고 가정한 검사, Markdown의 `solve\_rate` escaping을 고려하지 않은 검사, Preparing 뒤 Doctor가 자동 진행한다고 가정한 검사가 각각 실패했다. 실제 renderer·명시 Doctor action 계약을 대조하고 **제품이 아닌 검증 도구**를 바로잡았다. source.subdir의 최초 fixture도 TOML 따옴표 치환이 적용되지 않아 마지막 변조 assertion에서 실패했으며, `load_experiment`의 실제 subdir를 확인한 뒤 올바른 RED를 다시 확보했다. 이 실패들을 native/성능 성공으로 계산하지 않는다.

## 3. 실제 명령·passed/failed/skipped/not_run

### make·회귀

다음 전체 명령은 환경·argv 그대로 실행했다. 처음 `AGENT_OPT_HOME="$I/test-app"`/`make-test.log`에서는 **1155개/171.721초, failures=4/skipped=80, make exit 2**였고 §2에서 수정했다. 일반 prepare 수정 후 `final-test-app`/`make-test-final.log`는 1156개/171.093초 OK였다. **native subdir 수정까지 포함한 최종 명령**:

```bash
env -i PATH=/Users/wt.jeong/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin HOME="$I/home" AGENT_OPT_HOME="$I/verified-test-app" TMPDIR="$I/tmp" PYTHONDONTWRITEBYTECODE=1 AGENT_OPT_CORE_PYTHON="$PY" UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never make test > "$I/make-test-verified.log" 2>&1
env -i PATH=/usr/bin:/bin HOME="$I/home" AGENT_OPT_HOME="$I/lint-app" TMPDIR="$I/tmp" PYTHONDONTWRITEBYTECODE=1 AGENT_OPT_CORE_PYTHON="$PY" make lint
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$PY" "$I/make_demo.py"
env -i PATH=/usr/bin:/bin HOME="$I/home" TMPDIR="$I/tmp" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests "$PY" -m unittest test_final_acceptance test_preset_cli test_native_product test_integrations test_g_review -q
```

- 최종 make test: **`Ran 1157 tests in 171.268s`, `OK (skipped=80)`, exit 0**. 실제 실행 1077 통과·failure/error 0. 전역 browser/model patch·테스트 삭제·skip 추가·assertion 약화 없음.
- lint: `All checks passed!`, exit 0. focused: **56개/6.354초 OK**, skip 0. override 관련 별도 회귀는 `PYTHONPATH=src:tests`, 동일 Home/TMPDIR, `AGENT_OPT_CORE_PYTHON="$PY"`, `-m unittest test_dev_onboarding.DeveloperCommandsTests test_menu.MenuEntrypoints test_g_integration.EnvironmentBoundaryTests -v`: **48개/2.704초 OK**(`$I/make-env-regression.log`). 일반 prepare만 먼저 고친 focused 실행은 41개/5.606초 OK였다.
- **실제 `make demo`**: `$I/make_demo.py`가 현재 Makefile/scripts/src/examples/experiments를 `$I/make-checkout`에 복사하고 `AGENT_OPT_CORE_PYTHON="$PY"`로 `make demo` 실행, exit 0·**completed/7 trial/synthetic=true**. 원본 legacy TOML의 명시 `output_dir="runs"`를 보존했다. 공유 `.venv` 생성/설치 없음. stdout/stderr: `$I/make-demo.{stdout,stderr}`. 원래 worktree/main에 실행 산출물을 만들지 않았다.
- skip 80개의 **정확한 test 이름·원문 이유**는 `$I/skipped-tests.json`, 전체 로그는 `$I/make-test-verified.log`. 모듈별: adapters 1(선택 Docker image), cli_experience 30(Pilot/CLI로 대체된 직접 terminal), locale 2(Pilot 대체), network 4(BuildKit 2·YAML/driver 2), preset_tui 32(Pilot 대체), rtl_evaluation 9(Yosys/Icarus/vvp 없음), tui_choices 1(명시 캡처 미지정), verilog_live 1(선택 자산 미지정). native_ace **20**, native_cvdp **8**, native_producer **4**, native_product **14**는 실제 실행됐고 skip 없다. 전체가 optional live를 검증했다는 뜻은 아니다.

### source·실제 wheel·CLI/TUI/PTy·HTTP

```bash
env -i PATH=/usr/bin:/bin HOME="$I/home" TMPDIR="$I/tmp" PYTHONDONTWRITEBYTECODE=1 "$G/build-env/bin/python" -m build --wheel --no-isolation --outdir "$I/dist" > "$I/build-verified.log" 2>&1
env UV_CACHE_DIR="$G/uv-cache" UV_PYTHON_DOWNLOADS=never uv venv --offline --python "$PY" "$I/wheel-env"
env UV_CACHE_DIR="$G/uv-cache" UV_PYTHON_DOWNLOADS=never uv pip install --offline --python "$I/wheel-env/bin/python" --requirements "$G/wheel-requirements.txt" "$I/dist/agent_optimizer-0.3.0-py3-none-any.whl"
# 최종 제품 수정 후 같은 wheel-env에 실제 offline 재설치:
env UV_CACHE_DIR="$G/uv-cache" UV_PYTHON_DOWNLOADS=never uv pip install --offline --reinstall-package agent-optimizer --no-deps --python "$I/wheel-env/bin/python" "$I/dist/agent_optimizer-0.3.0-py3-none-any.whl"
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$PY" "$I/reuse_smoke.py" package_smoke
env -i PATH=/usr/bin:/bin HOME="$I/home" AGENT_OPT_HOME="$I/journey-app" TMPDIR="$I/tmp" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests "$PY" "$I/acceptance.py" > "$I/acceptance-verified.log" 2>&1
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$PY" "$I/command_git.py"
# CWD=$I/home, source/tests가 sys.path에 없는 실제 설치 wheel:
env -i PATH=/usr/bin:/bin HOME="$I/home" AGENT_OPT_HOME="$I/wheel-tui-app" TMPDIR="$I/tmp" PYTHONDONTWRITEBYTECODE=1 AGENT_OPT_LANG=en "$I/wheel-env/bin/python" -I -B "$I/wheel_tui.py"
```

모두 exit 0. 새 wheel-env에는 core/native 20개 패키지를 기존 G uv cache에서 **offline** 설치했다. build/install은 최초·일반 prepare 수정 후·최종 subdir 수정 후 실행했으며 최종 build 로그는 `build-verified.log`다. package smoke는 G 도구의 BASE만 I로 바꿔 재사용했으며 G env/assets를 수정하지 않았다.

- `$I/commands.json`은 최신 acceptance의 **각 실제 CLI argv/CWD/exit/stdout/stderr 절대경로**다. stdout은 JSON decoder가 한 값 뒤 남은 자료가 없음을 검증했고 오류/serve는 stdout 비움·stderr 안내·exit 2/130을 검증했다.
- source와 wheel의 각각 fresh Home에서 무인자 nonTTY 종료 2/no hang, help/catalog/Home 무생성, **실제 PTY 무인자 Textual Home → q 종료 0**(`source-noarg.tty`, `wheel-noarg.tty`)를 확인했다.
- CLI custom fixture init → prepare offline → doctor/plan → run → normalized JSON/MD/HTML → 서로 다른 실제 subprocess CWD의 같은 History → 실제 GET → port 충돌 종료 2 → SIGINT 130 → socket 접속 불가를 assertion으로 확인했다. doctor/plan과 report JSON은 before/after 디렉터리 inode/mode/mtime/바이트 snapshot이 같았다. 점수/상태/split·run ID/report 관계를 대조했고 파일 존재만 검사하지 않았다.
- source TUI는 60×28 Pilot의 stable ID로 **new→rtl-solo→fixture→baseline→sample_text→Model(불필요 API 없음)→Review→prepare→명시 Doctor→명시 run→Result→History→실제 HTTP→앱 종료 socket 정리**를 수행했다. 모델·Agent·evaluator를 가짜 성공으로 바꾸는 patch는 없고 OS browser만 False 모의였다. 별도 실제 wheel은 source 없는 다른 CWD·fresh Home·50×24 영어 Pilot에서 **Existing 입력→Review→Preparing→Doctor→Run→History**와 실제 설치 import provenance를 확인했다.
- `$I/command_git.py`는 source/wheel × local/pinned Git **4조합**에서 실제 command Harness가 `{python} {agent_dir}/src/fixture_agent.py {task_dir}`를 실행하도록 별도 init/prepare/doctor/run했다. 고유 로컬 fixture Git의 full SHA checkout·원본 clean·unpinned `main` 거부를 확인했다. 모두 completed/2 trial, 공개 fixture repair=true의 validation solve_rate=1.0. 외부 Git fetch/모델 성능이 아니다. 경로·pin은 `$I/command-git-artifacts.json`.
- 설치 wheel의 native 자산 계층·distribution metadata·Python/yaml probe ready를 실제 확인했다. 명시 설치 자산을 제거하면 loader가 실패하고 바이트 복구, `.env*`/IDE 배포 제외를 확인했다. wheel native 복수 profile·별도 outer 누락·read-only·retry도 실행했다. 이는 native 실모델 실행 근거가 아니다.

### 현재 source·wheel·TUI의 실제 설정/run/report 절대경로

공통 prefix `P=/private/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-i`는 실제 절대경로다. 각 run의 **`report.json`, `report.md`, `report.html`, `summary.json`, `events.jsonl`, `lifecycle.json`**을 실제 대조했다. 상태 completed/2 trial/synthetic=true이며 fixture 완료이지 native 성공/성능 향상은 아니다.

| 실행 | CONFIG (`P/` 뒤) | RUN (`P/` 뒤) |
|---|---|---|
| 최종 source CLI | `journey-d76f00fb/source/app/experiments/i-acceptance-f8363b602cfc/experiment.toml` | `journey-d76f00fb/source/app/runs/20261001T023029Z-c64ee052` |
| 최종 wheel CLI | `journey-d76f00fb/wheel/app/experiments/i-acceptance-1e22e1a84cf7/experiment.toml` | `journey-d76f00fb/wheel/app/runs/20261001T023031Z-864fd571` |
| 최종 source TUI | `journey-d76f00fb/tui/app/experiments/fixture-939e7a7744c7/experiment.toml` | `journey-d76f00fb/tui/app/runs/20261001T023033Z-2e89295b` |
| wheel 영어 Existing TUI | `journey-38945db9/wheel/app/experiments/i-acceptance-99717c34f520/experiment.toml` | `wheel-tui-app/runs/20261001T023028Z-384fc2b7` |
| make demo | `make-checkout/examples/minimal/experiment.toml` | `make-checkout/runs/20261001T022303Z-0f7e7143` (7 trial) |

전체 경로 정본은 `$I/artifacts.json`, `$I/wheel-tui.json`, `$I/make-demo.stdout`다. custom command 네 실행은 별도 JSON에 보존한다. 중간 fixture도 보존했다. `commands.json`과 번호별 stdout/stderr는 acceptance를 재실행할 때 갱신되는 **최종 실행** 자료이며, 이전 실패는 §2 및 당시 도구 출력과 구분한다.

## 4. native·호환성·private·보고서·보안의 실제 실행 범위

- 최종 make가 `test_native_ace`·`test_native_cvdp`를 실제 수행했다. 고정 로컬 upstream **`fead921f18bb57345b5a41ef93ba625be208e99c`**의 `ace_cvdp_native.cli.run_attempt`를 import·실행해 mismatch→reflector→pass(2 iterations), **iteration 12 coordinator API→RESTART→iteration 13 fresh-start**를 검증했다. OpenCode 호출로 대신하지 않는다. unused yaml import만 test-local stub이고 모델 completion·trusted 공식 evaluator는 명시 mock/fixture다.
- `test_candidate_store_changes_consumed_prompt_and_imported_code`: CandidateStore A/B의 `native/guidance.md`·실제 import/실행한 `native/orchestration.py`가 **실제 generator request 문자열**을 바꾸며 원본·editable 밖 upstream 수정은 거부된다. 세 역할은 같은 `ModelSettings` transport를 소비하고 실제 요청 journal·고유 ID·실패/timeout·부분/없는 usage를 대조했다.
- 고정 HF 파일의 실제 row 302개를 읽고 CID002 **94/94**, CID004 **55/55**, CID007 **40/13**, CID016 **35/35**, multi-file/nested/reordered target 및 unsupported PNR/상용 helper 사유를 재검증했다. 공식 raw-result schema의 all-zero pass·mismatch·infra·empty·private feedback/golden sentinel 미노출, inner/outer 평가·잔여 budget·실제 OS child timeout/cancel cleanup을 수행했다. **실 Docker/EDA 채점 및 Docker network 정리는 mock이며 실성공으로 기록하지 않는다.**
- 실제 native 정적 명령: `env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$PY" "$I/reuse_smoke.py" diagnostic_smoke`(exit 0). 실제 init CONFIG=`P/native-static-home-74b62ad79803/experiments/native-8d2b8bf72e15/experiment.toml`. 명시 CID002 decoder·CID016 adder를 validation으로 고른 고정 로컬 source export/HF rows다. doctor --plan JSON은 예상 exit 2/ready=false, prepare --offline도 예상 exit 2이며 TOML 불변/runs 없음. `$I/native-doctor.json`, `$I/native-prepare-offline.txt`, help 5개 파일이 정본이다.
- native 정적 source/row/등록/ps·inner/outer CVDP pin·driver Python/import는 ok. **격리 환경**에는 모델 URL/ID/key·sim image identity가 미설정이며 `/usr/bin:/bin` PATH에서 Docker가 보이지 않는다. 공유 core Python은 yaml 없음으로 native_python error. 이것을 개인 머신 전체에 Docker/모델 설정이 없다는 주장으로 확대하지 않는다. I wheel-env yaml probe는 별도로 ready다. **`agent-opt run NATIVE_CONFIG`, `doctor --model`, native EDA/live/Docker cleanup/Ubuntu x86_64/OS browser·SSH는 미승인 또는 실행환경 조건 미충족으로 `not_run`**이다.
- legacy OpenCode/Claude Code 설정·argv/model selector·오류/usage와 custom evaluator, local Git pin/hash·offline cache/CA/proxy, 복수 dataset spawn/jobs/session 실패/중단·Agent child cleanup, stage-local train/독립 baseline/validation 선택·고정 뒤 test는 최종 make의 해당 회귀를 실제 실행했다. 선택형 실도구 skip과 fixture 통과를 구분한다.
- `test_history`·`test_app_paths`·제품/Pilot에서 completed/error/interrupted/reportless/stale/unknown, 손상 summary/events/session, duplicate canonical ID/path, legacy/custom output, symlink/FIFO/root 교체를 실제 fixture와 subprocess로 확인했다. 조회는 모델/download/mkdir를 유발하지 않는다.
- `test_final_report`·`test_report_model`·`test_html_report`·`test_results`는 동일 normalized model의 수치/상태/선택/split/missing/partial/null·unknown/branch/multi-parent/empty와 escaping을 검사했다. raw summary/events/frozen selection 불변, 부적격 baseline 혼입 방지·native identity/유효성 경고·MD 검토 회차도 실행했다.
- source/wheel 실제 HTTP와 `test_report_server`의 **실제로 존재하는** 비공개 sentinel 파일 fixture에서 report/root GET/HEAD만 허용, env/credential/private evaluator/candidate/log/JSON/MD/encoded traversal/query/Host/dir listing·symlink/hardlink/FIFO/path swap 차단을 수행했다. auto port·명시 conflict·browser 실패/timeout·느린 HTTP client·동시 close·재열람·CLI Ctrl+C/TUI 종료 후 socket/thread 회수를 확인했다. public bind/전체 run static 공개를 추가하지 않았다.

## 5. offline HTML·사이트·안내 검증

- `$I/visual_reports.py`를 `PYTHONPATH=src:tests`·I Home/TMPDIR로 실행해 native ko/영어/empty/1000 probe-event stress의 실제 보고서를 만들고 제품 HTML-only 서버로 GET했다. Chromium Playwright에서 **4종×1440/360px=8개**를 실제 로딩, markup을 확보한 뒤 context offline·about:blank·setContent·모든 details 열기를 수행했다. 각 `document.scrollWidth==viewport`, `script=0`, 외부 src 없음, **발생 request=[]**였다. 캡처 `$I/{native,english,empty,stress}-{1440,360}.png`. OS `file://` 직접 열기 자체를 검증한 것은 아니다.
- 보고서 시각화 fixture 로딩 포트 59719~59722는 검증 뒤 자기 PID 52569의 script 경로를 확인하고 종료했다. nohup helper의 SIGINT가 무시되어 SIGTERM으로 종료했고 최종 `lsof ... -sTCP:LISTEN` 출력 없음. 이것을 제품 CLI Ctrl+C 근거로 사용하지 않는다; 제품 foreground SIGINT 130·socket 정리는 별도 acceptance에서 통과했다.
- 실제 website CWD=`worktree/website`, 기존 H node_modules만 사용:

```bash
env -i PATH=/opt/homebrew/bin:/usr/bin:/bin HOME="$I/home" npm run build > "$I/site-build.log" 2>&1
env -i PATH=/opt/homebrew/bin:/usr/bin:/bin HOME="$I/home" npm run check:links > "$I/site-links.log" 2>&1
```

둘 다 exit 0·10 pages·`All internal links are valid.` **실제 check:links script는 astro build**다. H 최신 원고/수정 책임표가 포함됐고 Node/npm 설치·다운로드는 하지 않았다. 기존 Vite directive 2건·404 content warning은 그대로이며 새 실패가 아니다. help의 native flag·report serve/port/no-open/json·doctor --model 및 Home/explicit output 계약을 실제 CLI argv와 대조했다.
- 현재 Markdown 검색의 OpenCode 기본/native 보류 매치는 과거 `docs/superpowers/*`, 당시 CONTEXT 선택·날짜별 verification 또는 명시 legacy 범위였다. 현재 README/status/native/site 가이드는 native-first와 live not_run을 구분한다. 과거 본문을 삭제/소급 성공으로 바꾸지 않았다.
- 최종 문서 검사 `env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$PY" "$I/check_report.py"`: exit 0, 로컬 링크/anchor/코드 펜스 **56개 오류 0**, 기존 날짜별 verification 본문 보존, R01~R30의 정확한 30행/29완료·1부분 및 실제 절대 config/run의 normalized identity/status/trials 일치 확인. `git diff --check`도 exit 0이다.

## 6. R01~R30 exact 최종 상태

원문 기준은 지시 세트 **`02_REQUIREMENTS_MATRIX.md`**다. 모든 근거의 tests는 I가 최종 make에서 **실제로 실행한** 경로이며, presence만으로 완료 판정하지 않았다. 표의 src 경로는 `src/agent_optimizer/` 기준이다.

| ID | 최종 요구(원문) | 상태 | 실제 근거 paths/tests·남은 범위 |
|---|---|---|---|
| R01 | 범용 Agent Optimizer, 다른 팀 Agent·기존 플러그인 유지 | 완료 | `contracts.py`, `registry.py`; `test_plugin_contracts` 18·`test_research` 13, custom local/Git command source/wheel 4실행, 코어의 ACE thin hook 유지 |
| R02 | DEMO/MVP, 오버엔지니어링 억제 | 완료 | I diff는 기존 preflight/경로/회귀 연결·2 covering tests. DB/daemon/framework/resume 추가 없음; 실제 make·source/wheel 실행 |
| R03 | Textual + Typer, 공통 실행·설정 경로 | 완료 | `cli.py`, `tui.py`, `setup_wizard.py`; acceptance CLI와 TUI의 같은 fixture/baseline/splits/status/2 trial, wheel Existing Pilot 실행 |
| R04 | `agent-opt` 무인자 TTY는 TUI, 명시 CLI 보존 | 완료 | source/wheel 실제 PTY Home→q 0; pipe no-hang 2, --help 0, `test_cli_entry`, stdout singleJSON/serve stderr |
| R05 | 프리셋 명시 선택·설명 패널·Enter/Esc·반응형 | 완료 | `test_tui_choices`, `test_textual_tui`, source 60×28/wheel 영어 50×24 actual Pilot; stable ID/back/상위 reset |
| R06 | 미구현 옵션도 Planned로 보이되 실행 차단 | 완료 | ChoiceRow disabled Planned·미준비/비호환, `test_tui_choices`, `test_product_wiring`; fake factory/실행 없음 |
| R07 | Endpoint/Model preset + 환경/기본/직접 입력 | 완료 | `test_tui_models`·`test_model_input`의 preset/Custom/source labels·세션 유지·selector 충돌; 임의 endpoint 추측 없음 |
| R08 | API key만 마스킹, Endpoint 평문·검증 | 완료 | `test_tui_models`, `test_tui_textual`, `test_textual_tui`; 정상 URL 평문·secret password·완성/부분 credential URL reactive 저장 전 제거·sentinel 없음 |
| R09 | Agent 모델과 Optimizer 모델/API 역할 구분 | 완료 | fixture Model API 불필요 실제 Pilot, native Baseline Agent API 체크·Optimizer 조건, `test_native_ace` transport·usage 분리 |
| R10 | App Home `~/.agent-optimizer`, `AGENT_OPT_HOME` override | 완료 | `app_paths.py`, `test_app_paths`·fresh source/wheel/TUI, 실제 different CWD History·explicit output; 개인 Home 실행은 없음 |
| R11 | 원본 프로젝트와 실행 저장소 분리·source provenance | 완료 | `config.py`, `sources.py`, writer; `$I/artifacts.json`, local/Git command 외부 CWD, `test_product_package`·`test_app_paths` |
| R12 | run/session 이력 저장·조회 일치 | 완료 | `history.py`, `session.py`; actual success ID/report 관계, `test_history`·`test_run_lifecycle`·spawn session/error/interrupted/reportless |
| R13 | 기존 경로 호환·자동 migration 금지 | 완료 | 원래 TOML로 실제 make demo 7 trial/명시 runs, legacy/custom mixed History·output 우선순위·원본 불변 tests |
| R14 | CLI JSON·exit·prepare/doctor/plan 부작용 계약 유지 | 완료 | actual source/wheel `commands.json`·snapshot·decoder·exit 0/2/130/stderr, 신규 일반 prepare preflight와 native subdir 회귀 |
| R15 | setup/doctor 원인·로그·Fix·Retry | 완료 | `test_diagnostics`·`test_dev_doctor`·`test_g_review`, actual native doctor 2/원인별 checks·port conflict retry; 성공 fallback 없음 |
| R16 | 기본 실제 데모 Python native ACE + CVDP | **부분** | native-first registry/profile·실제 pinned upstream run_attempt fixture·정적 init/doctor/prepare 완료. **실모델/공식 Docker·EDA native 데모는 not_run**; 격리 API/image/native Python 조건 부족·live 미승인 |
| R17 | 기존 OpenCode/Claude Code 프로필 별도 보존 | 완료 | `test_ace_demo`·`test_claude_code`·`test_preset_cli/tui`, actual catalog/native와 legacy ID 구분. 이번 coding live는 not_run |
| R18 | GEPA/Meta-Harness 변경이 native 실행에 실제 반영 | 완료 | `test_native_ace.test_candidate_store_changes_consumed_prompt_and_imported_code`: 실제 pinned loop의 요청 내용·imported Python이 A/B 변경; 단순 파일 hash만 검사하지 않음 |
| R19 | `cid002,cid004,cid007,cid016` 지원 검토·명시 | 완료 | `test_native_cvdp` 실제 pinned 302-row 검토·지원 197/exclusion27·multi-file/OSS gate, CID007 PNR/상용 사유. 실제 CID 정답률/EDA pass 선언 아님 |
| R20 | Native 역할 호출을 기존 제품 모델 설정과 일관되게 연결 | 완료 | `test_native_ace` 세 역할 transport/env·iteration12 실제 coordinator·13 fresh-start·모델 실패/usage journal; live transport 성공은 not_run |
| R21 | snapshot/editable·공식 채점·private/test 격리 | 완료 | `test_boundaries`·`test_core`·native/public/private sentinel·공식 result fixture·`test_research` stage train/validation/frozen test; trusted local plugin은 OS sandbox 아님 |
| R22 | HTML/MD/JSON 수치·상태·출처 정합성 | 완료 | normalized `report_model.py`·`test_final_report`·`test_report_model`·`test_results`; actual source/wheel 같은 run 상태/splits/metrics·partial/null/missing |
| R23 | 알고리즘별 trail/계보/시간/실패·unknown fallback | 완료 | `test_final_report` unknown/branch/multi-parent·stage baseline 재시작·MD 회차·실제 events만 소비, 임의 iteration/edge 없음 |
| R24 | 보기 좋은 offline HTML·표·반응형·접근성 | 완료 | report tests·Chromium 4×2 actual offline rendering/request=[]/가로 document overflow 없음·stress table·8 캡처; file://·개별 assistive device는 별도 |
| R25 | CLI report serve + TUI HTML 열람 | 완료 | source/wheel actual GET/SIGINT130, source TUI actual HTTP/앱 종료 socket close·browser failure fixture·port conflict |
| R26 | report server private/env/source 노출 방지 | 완료 | `test_report_server` 존재 private 파일·encoded traversal·symlink/FIFO/Host/inode swap, source/wheel 실제 HTTP 200/404·HTML 한 파일 |
| R27 | README/Starlight/개발·ACE 가이드 동기화 | 완료 | H 최신 responsibility 표·실제 help/argv 비교, 실제 site build/link 10pages, I README 일반 prepare와 최신 status/verification 근거 연결 |
| R28 | 개발 커맨드·offline/CA/proxy 진단 유지·보완 | 완료 | **실제 make lint/test/demo**, env override 4failure 수정, `test_network`·`test_datasets`·`test_dev_environment`·CA/proxy·offline/pin·hash 회귀 |
| R29 | 전체 실행 이력/결과/진단 연결 검증 | 완료 | fresh source/wheel/TUI config→prepare→snapshot doctor/plan→2trial run→JSON/MD/HTML→different CWD History→HTTP→shutdown, actual command Git/local 추가 |
| R30 | 모든 작업 실제 수정·회귀 테스트·handoff | 완료 | §2 실제 제품 결함 2건·make 테스트 격리 1건 수정, RED→GREEN·전체/배포/사이트 재실행·근거 문서·한국어 로컬 커밋. push 없음 |

**집계: 완료 29 / 부분 1(R16) / 차단 0.** 검증되지 않은 live를 완료로 바꾸지 않았다. native live 내부의 차단 조건은 R16/§4에 남고, 부분 구현 전체를 차단 상태로 중복 집계하지 않는다.

## 7. 검증된 새 사용법·잔여 위험

```bash
# source에서 실제 검증한 API-free 선택(환경의 Home은 절대경로):
agent-opt init --agent-preset rtl-solo --harness-profile fixture --optimizer baseline --dataset sample_text --yes
# 위 JSON의 실제 experiment 경로:
agent-opt prepare CONFIG --offline
agent-opt doctor --plan CONFIG --json
agent-opt plan CONFIG
agent-opt run CONFIG
# run JSON의 실제 run_dir:
agent-opt report RUN --json
agent-opt report RUN --serve --no-open --port 0
```

source의 위 fixture 선택·writer는 actual Pilot/회귀에서 실행됐고, source-free wheel은 별도 custom local/Git/Existing 경로를 실제 실행했다. 설치 wheel이 모든 source-only sample preset을 자동 제공한다고 확대하지 않는다. 무인자 TTY는 Home TUI, nonTTY는 명시 CLI를 쓴다. Home의 UUID 설정 경로·run ID는 출력값을 사용하고 고정 이름을 추측하지 않는다. 일반 prepare `ready=true`는 preflight만, native prepare는 source/interpreter·outer benchmark의 제한된 검사만, 전체 정적 진단은 doctor이며 실제 API는 명시 --model이다.

남은 concerns: native 실모델/공식 Docker·EDA 및 Docker cleanup·Ubuntu x86_64/SSH/OS browser는 not_run; CID007의 27 제외 row는 지원 대상으로 바뀌지 않음; 동일 사용자 trusted plugin의 논리적 private 경계는 OS sandbox가 아님; partial 사용량은 전체 토큰/비용이 아님; 연구 이름의 자체 구현과 fixture 개선은 논문 재현/일반 성능 증거가 아님; 기존 사이트 경고는 비차단 잔여다. 하위 reviewer를 새로 만들지 않고 실제 diff/계약/실행 근거로 자체 검토했다. 작업 worktree를 보존하고 사용자 지시대로 로컬 커밋만 남긴다.
