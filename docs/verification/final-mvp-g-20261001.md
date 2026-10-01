# 최종 MVP G — 진단·개발환경·배포 통합 및 H 인계

확인일: 2026-10-01. **G 통합 완료: 전체 unit 1,141개 중 실행 1,061개 통과·기존 skip 80개, lint·합성 데모·실제 wheel build/install smoke 통과. native 실모델/실 EDA 실행은 `not_run`이다.**

## 1. 작업 기준과 경계

- 지정 통합 워크트리 `.worktrees/final-mvp-20261001`, 브랜치 `feat/final-mvp-20261001`, 시작 `be410463964cf260dcd5c19200ced681cf0c5224`; 시작 상태 깨끗함. reset/새 워크트리/하위 에이전트/push/PR/main 수정 없음.
- `G_DIAGNOSTICS_DEV_INTEGRATION.md`를 먼저 읽고 작업 AGENTS, P0 및 A~F handoff 전체, 특히 F §6/§7/§8의 examples 소유 정책·thin hook·NATIVE_DEPENDENCIES 계약을 대조했다. CodeGraph 인덱스는 없고 생성하지 않았다.
- 기본 저장소는 시작 시 main이며 기존 `.gitignore` 변경과 지시 ZIP을 보존했다. 공유 `.venv`는 실행에만 사용했고 install/sync/symlink를 만들지 않았다.
- 아래 모든 임시 Home/cache/output/build/fixture는 `G=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-g` 경계다. `/var`의 macOS 정규 경로는 `/private/var`다.
- uv 0.10.7, 공유 Python 3.12.12. 승인된 격리 build-env/wheel-env에만 코어 의존성·build/setuptools/wheel·선택형 PyYAML을 설치했다. 대형 자산/이미지/EDA/모델 다운로드와 실제 모델 호출 없음.
- Context7의 uv 문서 조회는 monthly quota 오류였다. 실제 `uv lock --help`와 실행 결과로 옵션을 대조했다. SOURCES의 ACE/CVDP/HF 및 first-party pin은 변경하지 않았다.

## 2. 실제 수정과 계약

| 영역 | 실제 변경 |
|---|---|
| Home/output | 정적 doctor가 resolver/safe_path와 기존 부모 권한만 읽어 `app.paths`를 추가한다. 상대 Home·일반 파일·unsafe 경로/권한은 명시 오류이며 mkdir/fallback 없음. 기존 output 우선순위와 명시 TOML 의미 유지 |
| dataset/legacy | doctor cache는 `resolve_dataset_cache`, legacy 자산은 생성 설정의 evaluator asset root, seed는 `_seed_root` 기준. private benchmark를 후보 seed로 쓰면 runner와 동일하게 거부 |
| native 진단 | 코어는 `diagnose_native_selection` thin 연결, ACE 정책은 `examples/ace-rtl/native_selection.diagnose_selection`. fixed row/private/target/surface 재대조, source pin/asset, Python 3.12 및 yaml/pydantic_settings, ps, CVDP repo pin/driver imports, Docker 실행 파일·로컬 simulator identity를 기존 check/Runner로 연결 |
| 등록 | 생성 native 설정의 중앙 등록과 **같은 파일 참조**는 중복 오류가 아니다. 다른 파일/builtin shadow는 계속 거부. 실제 runner 등록 의미와 doctor를 일치시킴 |
| 모델 | Baseline native도 Agent API의 endpoint/model/key 세 값 필요. coding selector/OpenCode 자산 검사를 요구하지 않음. 연구 stage의 Optimizer API와 구별. CA/private-key bundle 정적 거부, 실제 connectivity는 명시 `model=True`에만 수행 |
| retry/server | doctor retry는 `shlex.join`으로 공백/한글 경로와 `--model` 보존. 서버 오류의 code/errno를 유지하며 Stage/Cause/Blocked by/Fix/Retry 제공. CLI의 `--html/--no-open/--port`를 retry에 보존. browser 실패가 run status를 바꾸지 않음 |
| 세션 환경 | `session_environment`는 프로세스 내 실행 context를 RLock으로 직렬화하고 중첩/예외 복구. UI의 모델 출처·redaction·실행 환경 생성은 원래 ambient `environment_snapshot`을 읽어 다른 worker의 임시 키를 상속하지 않음 |
| locale | Native/NativeRows/NativeSplit/SessionHistory 제목·CID/row/target/split 안내·report/browser/SSH 문구를 공통 locale에 연결. Endpoint 평문·credential URL 즉시 거부·API key만 password 정책 유지 |
| 생성 rollback | 복수 dataset init이 배타적으로 UUID 부모를 소유하고 실패 시 부모까지 rollback. 데이터 오류/stdout 오류 후 빈 Home 실험 폴더가 남던 실제 결함 수정. 기존 사용자 디렉터리·session sentinel은 보존 |
| UI 종료 | 이미 queued된 highlight가 detail panel unmount 뒤 도착할 때만 무시. 실제 mount 상태의 상세/선택 검증은 그대로 수행 |
| 개발 명령 | `AGENT_OPT_CORE_PYTHON=/절대/기존-venv/bin/python` 명시 override. venv identity·Python>=3.11 검사 후 현재 checkout의 src로 test/lint/demo 실행. bootstrap·doctor-core도 동일 override 소비. setup 설치 대상·기본 .venv·명령 범위는 유지 |
| wheel | 모든 NATIVE_DEPENDENCIES와 native_adapter를 원래 `share/agent-optimizer/examples/ace-rtl/{native,environment,...}` 계층으로 배포. source-free loader는 각 파일이 distribution metadata에 선언됐는지도 확인. 누락 자산/불완전 metadata는 명시 실패 |
| lock | optional `native=[PyYAML==6.0.2]`만 추가. 기존 코어·dev 및 전이 버전은 모두 동일. core Python>=3.11은 유지하고 native interpreter만 3.12 검사 |

직렬 context는 같은 프로세스의 제품 worker 실행 경계에 대한 안전성이다. 임의 plugin thread가 직접 `os.environ`을 읽는 것까지 격리하는 OS sandbox가 아니며 독립 run-session의 spawn/jobs 계약은 유지한다. driver import 준비 및 정적 pin 검사는 실모델/전체 native run 성공이 아니다.

## 3. F 실패 82건의 실제 원인과 교체 의미

F 로그 `tool_0f425c91a001tl0VFh2vh8j4ne`를 읽고 동일 원인을 현재 HEAD에서 재현했다. G baseline은 F 리뷰 covering 10개가 더해져 **1131개/152.438초, failures=41/errors=41/skipped=80**이었다. 전체 traceback·subtest 이름은 `G/baseline.log`에 보존했다.

| 실패 파일/대상 | 실제 원인·해결 |
|---|---|
| test_dev_onboarding의 direct core doctor, test_locale의 CLI/developer/help/error/TUI/doctor 언어 subtest 15건 | 존재하지 않는 워크트리 `.venv/bin/python/agent-opt` subprocess hardcode. `sys.executable` 및 `-m agent_optimizer`로 같은 실행 환경 소비. 언어·JSON·종료 2·no traceback assertion 유지 |
| test_cli_experience의 custom metric/DEL 문자열/GEPA allowance/argv quoting/OpenCode/pinned Git/glob/sampling/budget/structured flow | 생성 설정을 `project/runs/configs/<name>`으로 재구성하여 FileNotFoundError. stdout JSON의 `experiment`을 정본으로 소비. metric·config·pin·실제 합성 실행·report assertion 유지 |
| 같은 파일의 interactive init·wizard harness/glob/English/team 확장 | 숫자를 builtin Registry 목록에서 계산하지만 wizard는 중앙 native/sample 등록까지 포함. 실제 inventory에서 선택 ID의 번호 계산. 뒤의 argv/confirmation 입력 밀림·취소·StopIteration 해소 |
| 같은 파일의 preview/실패 생성/retry/multi-output | 옛 runs/configs preview·동일 이름 충돌 기대. Home UUID·독립 설정과 기존 sentinel 보존으로 교체. 실제 Home의 dangling 폴더 검사를 **추가**하여 제품 rollback 누락 2건을 재현·수정 |
| test_dev_environment의 selected CVDP setup | argv 전체의 `opencode` substring 검사에 필수 TMPDIR `/T/opencode/`가 걸림. executable basename 및 명시 Agent Dockerfile 인수로 판정; 불필요 Agent image 준비 금지 assertion 유지 |
| test_integrations의 selected cache | XDG 기본 cache 기대가 최신 App Home과 불일치. 고유 Home/cache/integrations를 검사; explicit cache 우선순위는 기존 회귀 유지 |
| test_preset_cli의 GEPA/Meta/init budget/prepare/tampered profile | 준비 mock이 반환해야 하는 asset Path 대신 MagicMock을 반환. 실제 root 반환, UUID 이름·`_seed_root` 기대 반영. 준비 전 symlink 거부는 현재 Home/experiments 경계로 이동 |
| test_preset_tui의 independent seed/tampered seed/missing seed | 원본 프로젝트에서 seed를 읽고 변경해 실제 config seed를 건드리지 않음. `_seed_root`를 소비하여 실제 변조/누락 거부 확인 |
| 같은 파일의 selected OpenCode provider 2 subtest·noninteractive lifecycle | 실행 mock이 새 optional `output` kwargs를 받지 않음 및 macOS canonical path 차이. output=None 수용/검사와 resolved 경로 기대. provider/image assertion 유지 |
| test_textual_tui·test_tui_models·test_tui_textual의 모델/URL/키/출처/Review/back/좁은 화면 | 기본 native-first 뒤 추가 Native 페이지인데 고정 Enter 횟수로 legacy Model/Review라 가정. stable ID로 `ace-opencode`를 명시 선택. default native 자체는 F native tests에서 계속 검증 |
| test_tui_choices의 installed workspace/meta surface | 같은 native-first/인덱스 문제. 선택한 legacy Harness ID와 metadata를 실제 소비하며 Baseline/Meta 선택 보존·surface assertion 유지 |
| test_textual_tui의 Endpoint password | 옛 URL 전체 password=True 정책. 새 요구인 평문 정상 URL·즉시 빈 값으로 credential/query URL 거부·sentinel 부재·정상 재입력으로 교체. 실제 partial typing·key masking tests도 계속 실행 |
| 같은 파일의 history/filter/replaced report/run output/English Review | tuple 대신 원래 dict row, 프로젝트 runs 대신 Home output, 실제 Home 보고서 경로. 공유 Home의 이전 실행이 fixture보다 먼저 선택되던 오염은 test_project별 고유 Home으로 해소; inode·symlink 교체 거부 유지 |

추가로 전체 반복에서 나온 `test_history...callback_failure`는 **UTC 날짜 경계 이후 child가 session보다 최신**이어서 첫 row의 interrupted를 읽었다. parent session ID로 고정하여 부모 error와 worker cleanup을 검증한다. `test_native_changes...row-picker`의 늦은 highlight/unmount 오류는 제품 종료 경계 regression으로 재현하여 수정했다. 실패를 재실행만으로 숨기지 않았다.

개발 중 결과도 보존한다: `regression1.log` 268개/9 failure/13 error(초기 test helper signature 오류 포함), `full2.log` 1102개/5 failure/1 error(초기 test indentation 오류로 TUI 모듈 로드 실패), `regression3.log` 102개 OK/기존 skip 1, `unit-final.log` 1139개/4 error(새 locale의 report key 누락), `unit-final2.log` 1140개/2 failure(강화 Home rollback 검사), `unit-final3.log` 1140개 OK, `unit-final4.log` 1140개/1 failure/1 error(UTC parent 선택·highlight 종료 race), 최종은 아래와 같다. native driver smoke에서 잘못 추가했던 docker **Python SDK** import는 고정 driver requirements/기존 diagnostics imports와 대조하여 제거했고, 실제 고정 driver의 12개 import가 `ok`임을 확인했다.

## 4. 정확한 최종 검증 명령·출력

다음 변수는 실행한 절대경로의 단순 약기다. CWD는 지정 워크트리다.

```bash
G=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-g
PY=/Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python
```

### 전체 unit·lint·lock

```bash
env -i PATH=/Users/wt.jeong/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests AGENT_OPT_LANG=ko HOME="$G/home" AGENT_OPT_HOME="$G/app" TMPDIR="$G/tmp" UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never "$PY" -m unittest discover -s tests -v > "$G/unit-final5.log" 2>&1
env AGENT_OPT_CORE_PYTHON="$PY" PYTHONDONTWRITEBYTECODE=1 make lint
git diff --check
env UV_CACHE_DIR="$G/uv-cache" UV_PYTHON_DOWNLOADS=never uv lock --check --offline --python "$PY"
```

**`Ran 1141 tests in 173.523s`, `OK (skipped=80)`**. 실행 1061개 통과, 실패/오류 0. 기존 skip 사유(직접 터미널 Pilot 대체, 선택형 실도구/live 자산, 명시 SVG 캡처 등)를 유지했고 skip/삭제/xfail을 추가하지 않았다. 전체 실행에 전역 browser/model patch를 씌우지 않았다. browser/모델 성공 assertion은 해당 테스트의 fixture/mock 경계이며 OS 브라우저 성공은 미검증이다. Ruff `All checks passed!`, diff 검사 종료 0; frozen/offline lock 검사 `Resolved 25 packages` 종료 0.

추가 RED→GREEN: overlapping 환경 context, config seed/root·private benchmark seed, relative/file Home, native baseline API·private row drift·CA private key, distribution metadata 누락, quoted server retry, 실제 panel unmount. G 신규 10개와 기존 보호 회귀를 최종 전체 suite에 포함했다.

### uv 격리 build/install·실제 wheel

```bash
env UV_CACHE_DIR="$G/uv-cache" UV_PYTHON_DOWNLOADS=never uv lock --python "$PY" --no-progress
env UV_CACHE_DIR="$G/uv-cache" UV_PYTHON_DOWNLOADS=never uv venv --python "$PY" "$G/build-env"
env UV_CACHE_DIR="$G/uv-cache" UV_PYTHON_DOWNLOADS=never uv pip install --python "$G/build-env/bin/python" build==1.2.2.post1 setuptools wheel
env UV_CACHE_DIR="$G/uv-cache" UV_PYTHON_DOWNLOADS=never uv export --frozen --no-dev --no-emit-project --extra native --format requirements-txt --output-file "$G/wheel-requirements.txt"
env UV_CACHE_DIR="$G/uv-cache" UV_PYTHON_DOWNLOADS=never uv venv --python "$PY" "$G/wheel-env"
env UV_CACHE_DIR="$G/uv-cache" UV_PYTHON_DOWNLOADS=never uv pip install --python "$G/wheel-env/bin/python" --requirements "$G/wheel-requirements.txt" "$G/dist/agent_optimizer-0.3.0-py3-none-any.whl"
```

lock 변경은 `Added pyyaml v6.0.2`만. 격리 build-env는 build 1.2.2.post1/setuptools 84.0.0/wheel 0.48.0, wheel-env의 코어 버전은 기존 uv.lock 그대로다. 첫 wheel build는 위 설치 전에 같은 build 명령으로 수행했다. 최종 제품 수정 이후 실행한 명령:

```bash
env PYTHONDONTWRITEBYTECODE=1 "$G/build-env/bin/python" -m build --wheel --no-isolation --outdir "$G/dist" > "$G/build-final4.log" 2>&1
env UV_CACHE_DIR="$G/uv-cache" UV_PYTHON_DOWNLOADS=never uv pip install --offline --reinstall-package agent-optimizer --no-deps --python "$G/wheel-env/bin/python" "$G/dist/agent_optimizer-0.3.0-py3-none-any.whl"
env PYTHONDONTWRITEBYTECODE=1 "$PY" "$G/package_smoke.py"
```

`Successfully built agent_optimizer-0.3.0-py3-none-any.whl`, 종료 0. smoke 출력:

```text
배포 provenance·native 하위구조·yaml: .../wheel-env/share/agent-optimizer
{'ready': True, 'reason': ''}
wheel CLI init→plan→doctor→합성 run→report→HTTP 200/private 404: 2
자산 누락 명시 실패·서버 종료 130·비밀 파일 배포 제외: OK
```

실제 설치 wheel subprocess는 `-I -B -m agent_optimizer`, source/examples/marker 없는 다른 CWD와 공백·한글 project, 새 Home을 사용했다. explicit custom scorer와 local fixture Agent로 설정 생성→plan→read-only doctor→baseline synthetic 2 trial→report JSON→실제 HTTP 200/private summary 404→SIGINT 130을 검증했다. distribution origin·모든 native sibling/하위자산·yaml probe, 설치 자산 하나를 제거했을 때 명시 실패 및 byte 복구, wheel의 `.env*`/IDE 자산 배제도 확인했다. 이것은 native Agent/EDA 성공이 아니다.

### 실제 make·합성 demo·직접 bootstrap

```bash
env PYTHONDONTWRITEBYTECODE=1 "$PY" "$G/make_smoke.py"
```

script는 현재 소스와 Makefile/scripts/examples를 **고유 공백·한글 임시 checkout**에 복사하고 `AGENT_OPT_CORE_PYTHON="$PY"`로 `make help`, `make doctor-core`, `make lint`, `make demo`, `sh scripts/bootstrap.sh doctor --core --json`을 실행했다. 모두 종료 0. demo **`completed 7 synthetic=True`**, report 생성. `.venv` 생성/설치 없음. 처음 원래 checkout에서 실행한 `make demo`도 7 trial completed였으나 옛 TOML의 명시 `output_dir="runs"` 때문에 워크트리 runs에 생성됐다. 본 작업의 ID `20260930T233955Z-9aa75a93`/synthetic 정본을 대조한 뒤 `G/initial-make-demo`로 보존하고 자신이 만든 빈 runs만 제거했다. 명시 output 의미를 Home으로 바꾸어 숨기지 않았다.

## 5. 실제 native 정적 진단·help와 H 인계

```bash
env PYTHONDONTWRITEBYTECODE=1 "$PY" "$G/diagnostic_smoke.py"
```

이 script는 명령별 실제 argv와 반환코드를 assertion으로 검증한다. `cli-help.txt`, `init-help.txt`, `prepare-help.txt`, `doctor-help.txt`, `report-help.txt`가 **최종 실제 help**다. help만 읽은 새 Home은 생기지 않았다. 재실행 중 이전 Home을 재사용한 script assertion 1건은 fixture를 UUID Home으로 고쳐 독립성을 확보했다.

실제 local pinned ACE checkout을 export하고 고정 HF 파일의 CID002 decoder/CID016 adder 두 row를 **명시 validation**으로 native init했다. 최종 생성 경로는 `G/native-static-home-5636ca8ce698/experiments/native-fffa8d221988/experiment.toml`이다. source·원본 HF/CVDP는 읽기 전용이며 fetch/download 없음. `doctor --plan ... --json`은 종료 2, `ready=false`; `prepare ... --offline`도 종료 2이고 설정 바이트는 그대로이며 runs 없음.

| 최종 실제 상태 | 근거 |
|---|---|
| ok | schema·등록·Home·source/active surface·fixed row/private 대조·native source pin·ps·CVDP repo pin·driver Python/실제 고정 의존성 imports·budget |
| blocked 준비 | `native_python`: 공유 코어에는 yaml 없음. `native.docker`: 정적 smoke PATH에는 Docker 실행 파일 없음. `native.simulator.lock`: image/identity 미지정. `model.configuration`: 실제 endpoint/model/key 미설정 |
| not_run | 모델 connectivity/API, 원본 native Agent run, 실제 CVDP Docker/EDA/child Docker cleanup, Ubuntu x86_64, SSH/OS browser 성공 |

H가 안내할 최종 사용법(아래는 임의 경로를 사용한 **설명 예시**, 실환경 실행 완료 선언 아님):

```bash
agent-opt init --agent-preset ace-rtl --harness-profile ace_native --dataset cvdp --optimizer baseline --cid cid002 --rows '{"명시_ROW_ID":"validation"}' --native-dataset /absolute/pinned.jsonl --native-upstream /absolute/pinned-ACE --native-python /absolute/native-venv/bin/python --native-evaluator '{"repo":"/absolute/pinned-cvdp","python":"/absolute/driver/bin/python","sim_image":"local-reviewed-tag","sim_image_id":"sha256:reviewed-identity"}' --yes
agent-opt doctor --plan /absolute/Home/experiments/UUID/experiment.toml --json
agent-opt prepare /absolute/Home/experiments/UUID/experiment.toml --offline
agent-opt report /absolute/RUN --serve --no-open --port 0
agent-opt report /absolute/RUN --html --serve --no-open --port 0
```

- Home 기본 `~/.agent-optimizer`, override는 절대경로. `experiments/runs/sessions/assets/cache/logs`, 새 UUID 설정은 provenance project_root·config_root 분리. output은 CLI explicit > 명시 TOML > Home이며 부모 의미다.
- native Python은 **별도 Python 3.12 환경 + 선택형 native extra(PyYAML)**, 평가 driver는 기존 고정 CVDP lock 준비가 필요하다. `prepare --offline`은 누락 환경을 설치하거나 online으로 보완하지 않는다. core `setup-core`가 native/EDA 전체 준비를 대신한다는 안내는 금지한다.
- 네 CID 선택은 row별 지원 판정이며 CID007 PNR/상용 helper exclusion 유지. dataset/row/split 자동 추천 없음. GEPA/Meta는 실제 native guidance/orchestration 표면을 소비하며 test는 선택 고정 뒤만 실행한다.
- doctor JSON의 기존 scope/ready/checks와 check 5-key shape·exit 0/2 유지. 새 checks는 additive. 명시 `--model`만 실제 connectivity probe이며 probe 성공을 전체 native 성공으로 쓰지 않는다.
- report serve는 loopback/HTML 한 파일, 저장 보고서만 조회; `--html`은 명시 재생성. `--json/--csv` serve 충돌은 부작용 전에 거부. browser unavailable에는 URL/SSH 안내, port 오류에는 code/errno와 실행 가능한 retry. Ctrl+C=130·handle cleanup.
- setup-core는 코어 의존성 설치·합성 demo, doctor-core는 읽기 전용, test/lint/demo는 기존 코어 환경 사용. 옵션 없는 setup/doctor와 smoke/live는 기존 ACE 전체 범위이며 native로 의미를 바꾸지 않았다. live/doctor --model만 실모델 범위다.

## 6. 최종 검토·잔여 검증

요청/소유 경계·diff·실패 traceback·native producer/renderer 경로·HTML-only allowlist·private/키 redaction·pin·rollback·같은 프로세스 환경 복구·source-free provenance를 직접 검토했다. 하위 에이전트 리뷰는 수행하지 않았다. G는 실제 unit/Pilot/subprocess/HTTP/합성 runner/wheel 증거를 제공하며, live/EDA/Ubuntu 및 임의 plugin thread의 완전 환경 격리는 별도 검증이다. 설치형 old first-party pin에 native가 있다고 주장하거나 자동 갱신하지 않는다. 지정 intended files를 한국어 로컬 커밋으로 인계하고 워크트리를 보존한다.
