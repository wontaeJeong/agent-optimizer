# 최종 MVP A — App Home·경로·실행 이력 backend 인계

확인일: 2026-10-01. **A backend 구현과 전용/관련 테스트는 완료했다. 제품 CLI/TUI/writer 연결은 F 작업이며 전체 suite는 아래 명시한 17건 때문에 녹색이 아니다.**

## 1. 기준·변경 파일·작업 범위

- 작업 디렉터리: `/Users/wt.jeong/workspace/agent-optimizer/.worktrees/final-mvp-a-20261001`.
- 브랜치: `feat/final-mvp-a-20261001`. 시작 HEAD와 생성 기준 `origin/main`: `edbd2b8c7b05bdd63c352d02a7adf7652168d197`.
- `prompts/A_APP_HOME_HISTORY.md`, 작업 `AGENTS.md`, P0 인계 §4·§7 및 `docs/SOURCES.md`를 대조했다. `.codegraph/`는 없으며 인덱싱하지 않았다.
- 기본 디렉터리는 `main`이다. 기존 `.gitignore` 변경과 지시 ZIP·다른 담당자의 작업은 보존했다. 하위 에이전트 생성, 설치/sync, push/PR, merge는 하지 않았다.
- 신규: `src/agent_optimizer/app_paths.py`, `src/agent_optimizer/history.py`, `tests/test_app_paths.py`, `tests/test_history.py`.
- 경로/lifecycle 수정: `config.py`, `runner.py`, `session.py`, `sources.py`, `datasets.py`, `integrations.py`.
- `workspace.py`/CandidateStore, CLI/TUI/설정 writer/보고서 renderer, 공통 기존 테스트, 고정 SHA는 수정하지 않았다.
- `requesting-code-review`의 검토 항목을 직접 diff·소스로 점검했다. 사용자 금지에 따라 별도 reviewer를 생성하지 않았다. 로컬 커밋과 워크트리 보존은 사용자 지정 완료 방식이다.

## 2. 공개 경로 API와 우선순위

```python
resolve_app_home(env: Mapping[str, str] | None = None, *, cwd: Path | None = None) -> Path
app_path(name: str, *, app_home: Path | None = None) -> Path
resolve_run_base(spec: dict, output: Path | None = None) -> Path
resolve_session_base(output: Path | None = None) -> Path
resolve_dataset_cache(selection: str, cache_dir: Path | None = None) -> Path
```

- `resolve_app_home`: 없거나 빈 `AGENT_OPT_HOME`은 `Path.home()/'.agent-optimizer'`, 값이 있으면 `expanduser()`한 절대경로. **상대 override는 `ConfigurationError`로 거부**한다. P0의 상대경로 고정 제안은 최신 사용자 결정으로 대체했다. `cwd`는 공유 signature 호환용이며 상대경로를 허용하는 근거가 아니다.
- `app_path`: `experiments/runs/sessions/assets/cache/logs`만 허용한다. `safe_path`로 앱 경계와 symlink/특수 파일을 확인한다.
- 모든 resolver는 mkdir/download/모델 호출을 하지 않는다. 잘못된 Home/경로·권한을 다른 기본값으로 대체하지 않는다.
- `resolve_run_base`: 명시 `output` > TOML에 있는 `output_dir` > App Home/runs. 명시 CLI 상대 output은 기존대로 호출 CWD에서 `resolve()`한다. TOML 상대 output은 `_root` 기준 `safe_path`로 해석한다. `output_dir="runs"`도 **명시값**이다.
- 반환값은 run의 **부모 디렉터리**다. runner의 UTC `YYYYMMDDTHHMMSSZ-xxxxxxxx` ID, `sources/`·Agent/Harness·candidate·trial 레이아웃은 그대로다. UUID와 배타적 mkdir로 기존 실행을 덮어쓰지 않으며 두 동시 실행의 독립 산출물을 검증했다.
- `resolve_session_base`: explicit output의 기존 부모 의미를 유지하고 새 기본은 App Home/sessions다. session root 생성 호출부는 F가 연결한다.

### 설정 경계

`load_experiment`는 optional `config_root`를 허용하고 `_config_root: Path`를 추가한다.

- 없으면 `_config_root == _root`로 기존 실험이 그대로 동작한다.
- 있으면 절대경로 또는 **experiment 파일 부모 기준** 상대경로로 해석한다. 값은 비어 있지 않은 문자열이며 설정 경계의 symlink/특수 파일을 거부한다.
- `agents`, `harnesses`, `benchmark`만 `_config_root` 안의 안전한 상대경로다. `..`·절대 파일 경로를 `safe_path`에 허용하지 않았다.
- `project_root`/`_root`, 파일 플러그인·dependency·`candidate_seed_files`는 원본 프로젝트 기준이다. runner의 benchmark hash 소비도 `_config_root`를 사용한다.
- local Agent source는 기존처럼 **Agent manifest 부모 기준**으로 해석하여 절대 `SourceSpec.path`와 source-lock provenance를 보존한다. F가 생성 manifest를 이동할 때 원본에서 해석한 절대 source를 써야 한다. 로컬 Git locator도 원본 manifest 기준을 잃지 않게 보존해야 한다.
- 외부 config_root + 원본 프로젝트 evaluator/seed + 실제 합성 runner 실행을 전용 테스트로 검증했다.

## 3. cache·source writer 계약

- `acquire_integration(..., cache_dir=None)`: App Home/cache/integrations/<고정 commit>. 이번부터 XDG는 이 기본값을 결정하지 않는다. 명시 `cache_dir`가 우선이다.
- `prepare_catalog_dataset(workspace, selection, *, offline=False, cache_dir=None)`: 기본 provider cache는 App Home/cache/datasets/<selection>. 준비와 doctor에 같은 cache를 전달한다. 기존 명시 workspace의 선택형 파일 획득/충돌 검사·등록 경계는 유지한다.
- `CustomDataset.prepare(cache=None, *, offline=False)`: 기본 App Home/cache/datasets/custom/<stem>-<source sha256 앞 16자리>. 명시 cache는 기존 `<cache>/custom/<stem>.json` 레이아웃이다. scorer·split 검증 후 배타적 원자 publish를 하며 기존 파일 내용이 다르면 보존하고 오류를 낸다.
- `acquire_pinned_git`는 offline miss를 online으로 보완하지 않는다. 두 게시자가 rename 시점에 충돌하면 **이미 게시된 checkout의 pin/dirty 검증을 통과할 때만** 재사용한다. 다른 실패·변경된 checkout은 성공으로 바꾸지 않는다.
- Agent Git의 임시 checkout은 명시된 run source target 내부에서 생성하고 제거한다. source snapshot/hash/pin, 원본 미수정, credential 제외 규칙은 그대로다.
- 옛 XDG cache·프로젝트 cache를 자동 이동/삭제/검색하지 않는다. `assets/`, `experiments/`, `logs/`의 앱 경로는 resolver로 제공한다. 기본 준비 workspace·생성 설정·최상위 안내 로그 호출부의 선택은 F 소유다.

## 4. History API·row·안전 경계

```python
list_history(*, app_home: Path, project_root: Path | None = None,
             run_bases=(), limit: int = 10) -> list[dict]
verified_report(row: dict) -> Path
record_lifecycle(root: Path, *, status: str, kind: str = 'run',
                 experiment_name: str | None = None, session_id: str | None = None,
                 created_at: str | None = None, children: list[dict] | None = None) -> dict
```

- `list_history`는 읽기 전용이다. 주어진 Home의 runs/sessions, **명시한** project_root의 `runs`·`runs/dev-live`, 호출자가 넘긴 output parent만 확인한다. 전체 디스크·source acquisition·모델·브라우저·보고서 생성·metadata 갱신이 없다.
- session child는 실제 `session/runs/<숫자 slot>/<run ID>` 레이아웃만 제한적으로 조회한다. JSON에 있는 외부/절대/URI child 링크를 따라가지 않는다.
- row 필수 필드: `run_id`, 절대 문자열 `run_dir`, UTC ISO 문자열 `created_at`, `status`, nullable `experiment_name/session_id/report_path/diagnostic`.
- additive 필드: `kind="run"|"session"`, nullable `trials_used`, session의 실제 절대 child 경로 목록 `child_runs`, 재검증용 내부 `_directory_identity=(st_dev, st_ino)`.
- 반환 객체는 일반 list/JSON 배열과 호환되는 `HistoryRows`이며 `.diagnostics: list[str]`에 건너뛴 unsafe 경로·손상 기록·보고서 없음의 요약이 있다. 실행 row가 없어도 진단을 확인할 수 있다. JSON으로 목록만 직렬화하면 이 속성은 자동으로 포함되지 않는다.
- 최신 시각 순으로 limit을 적용하며 canonical path와 run ID 중복을 제거한다. 동일 ID 복사본은 Home 등 먼저 지정된 조회 경계가 우선이다.
- 정상 terminal summary가 정본이며 부족하면 lifecycle와 실제 실패/중단 events를 보완한다. `completed`, `no_eligible_candidate` 등 채점/선택 상태, `error/source_error`, `interrupted`, `partial/budget_exhausted`를 원래 의미대로 보존한다. 점수 0을 인프라 오류로 재해석하지 않는다.
- 종료가 없는 `running`은 `stale`, 유효한 상태가 없으면 `unknown`이다. PID를 조회하거나 현재 살아 있다고 추측하지 않는다. preflight 거부에는 가짜 run을 만들지 않는다.
- HTML이 없어도 row가 나온다. `report_path=None`과 한국어 diagnostic을 제공한다. run은 `report.html`, session은 `index.html`만 보고서 후보로 인정한다.
- 경로의 모든 사용자 구성요소를 directory-relative `O_DIRECTORY|O_NOFOLLOW`, 파일을 `O_NOFOLLOW|O_NONBLOCK`과 `fstat(S_ISREG)`로 확인한다. macOS 시스템 `/var`·`/tmp` 별칭만 `/private`에 대응한다. JSON/events 읽기는 16 MiB 문자 제한이다. 손상 JSON·schema·symlink·FIFO·없는 경로가 전체 목록을 깨지 않는다.
- `verified_report`는 전달받은 **원래 row**의 root ID·고정 보고서 파일명·현재 상태·디렉터리 inode를 재검증한다. URI/외부 보고서 경로, root/report symlink 교체, 손상 row를 `ConfigurationError`로 거부한다. row에서 내부 필드를 제거한 뒤 다시 구성하지 말고 재조회하거나 원래 row를 보존한다.
- 반환 Path는 열린 FD가 아니다. F의 browser/server 시작 직전에 재검증하고 E도 자신의 FD/allowlist 경계를 다시 검증해야 한다. 이것을 native 플러그인의 OS 보안 격리로 표현하지 않는다.

### lifecycle.json schema 1

```json
{
  "schema_version": 1,
  "kind": "run",
  "run_id": "20261001T000000Z-12345678",
  "created_at": "2026-10-01T00:00:00+00:00",
  "updated_at": "2026-10-01T00:00:01+00:00",
  "status": "completed",
  "experiment_name": "fixture",
  "session_id": null
}
```

- 고유 temporary 파일에 기록·flush/fsync한 뒤 replace한다. run 생성 직후 `running`, 기존 runner finally의 첫 단계에서 terminal status를 기록하므로 summary/report writer 실패에도 최소 이력이 남는다.
- session은 생성/종료/중단/failure에 같은 schema와 `kind="session"`, optional `children`을 기록한다. child는 `dataset/status/run_dir/report/trials_used`만 보존하고 raw exception/feedback/키는 추가하지 않는다.
- child의 `run_dir`와 `report`는 session root 기준 상대 경로다. `run_dir`는 HTML과 독립적이며 preflight 실패·미실행이면 null이다. 기존 `report`·`trials_used` 필드를 유지했다.
- worker spec의 내부 `_session_id`만 additive로 전달하여 run lifecycle에 부모 ID를 남긴다. 복수 dataset spawn/jobs 동시 실행·입력 순서를 보존한다. 부모 callback 오류에도 worker/Agent 정리를 시도하고 error lifecycle을 기록한다.

## 5. 수용 검증 범위와 정확한 명령

모든 CWD는 A 워크트리다. 공유 `/Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python`을 실행에만 사용했다. **실제 사용자 Home 이력은 읽거나 변경하지 않았다.** 테스트/명시 cache/output은 승인 임시 `.../T/opencode/final-mvp-a` 하위다. 전용 테스트는 고유 `TemporaryDirectory(dir=...)`를 사용한다. 최종 검토에서 Mac 고정 temp 경로를 `tempfile.gettempdir()/agent-optimizer-final-mvp-a`로 바꿔 Linux에서도 실행 가능하게 했고, 아래 명시 TMPDIR로 승인 경계 안에 고정하여 관련 회귀를 재실행했다.

최초 RED에서 옛 implicit runs 경로를 재현한 동시 실행 2개가 A 워크트리의 `runs/20260930T162112Z-{90fd599c,f60dc632}`에 생성됐다. 테스트를 임시 프로젝트로 바꾸고 두 **직접 생성한** 디렉터리만 확인 후 제거했다. 사용자 데이터나 다른 작업 디렉터리는 정리하지 않았다.

### 신규·핵심 관련 회귀

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-a/regression-src-20261001-home TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-a /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -c "import unittest; names = ('test_app_paths.py', 'test_history.py', 'test_plugin_contracts.py', 'test_research.py', 'test_datasets.py', 'test_run_lifecycle.py'); suite = unittest.TestSuite(unittest.defaultTestLoader.discover('tests', pattern=name) for name in names); result = unittest.TextTestRunner(verbosity=2).run(suite); raise SystemExit(not result.wasSuccessful())"
```

**최종 111개/9.742초 OK**, 종료 0. 같은 명령의 직전 실행도 111개/9.437초 OK였다. 신규 **30개**(`test_app_paths` 13 + `test_history` 17), 플러그인 18, 연구 13, datasets 24, run lifecycle 26이다.

검증한 동작: 기본/빈 override/expanduser/상대 env 거부/한글·공백 경로/permission fixture, 명시 output·옛 TOML 우선순위, 원본 프로젝트 플러그인/seed·source provenance, 외부 config_root 실행·escape 거부, 두 동시 run, local pinned Git 획득·offline cache miss·사용자 파일 충돌·동시 게시 race, fresh Home help/catalog/plan/정적 doctor 무생성, reportless 성공/실패/중단/unknown/stale, 실제 spawn session child·중단·setup/callback 오류 정리, malformed/schema/symlink/FIFO/외부 URI/root 교체·중복 제거·skip diagnostic이다.

권한 오류와 일부 예외/race는 의도적인 fixture 주입이다. Git 획득은 **고유 로컬 fixture repo**이고 네트워크 upstream 다운로드가 아니다. runner는 기존 synthetic fixture Agent/evaluator다. 실제 native/모델/EDA 성공 증거로 사용하지 않는다.

### 기존 session 회귀

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-a/session-regression-20261001-home TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-a /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -k session -v
```

**11개/4.368초 OK (skipped=1)**, 종료 0. 실제 통과 10개. jobs overlap/직렬, worker 실패, Ctrl-C worker/Agent child 정리, 보고서 연결·JSON·순서 보존을 검증했다. skip은 기존 TUI multi-dataset 대신 CLI를 제공한다는 테스트다.

### 전체 suite

```bash
env -u AGENT_OPT_TEST_VERILOG_EVAL_ROOT PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src AGENT_OPT_LANG=ko AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-a/final-20261001-home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-a/final-20261001-cache TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-a UV_PROJECT_ENVIRONMENT=/Users/wt.jeong/workspace/agent-optimizer/.venv UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -v
```

**983개/125.293초, FAILED (failures=2, errors=15, skipped=79)**, 종료 1.

1. 기존 P0 baseline 오류 15건: `test_dev_onboarding.py:744`, `test_locale.py`의 worktree-local `.venv/bin/python`·`.venv/bin/agent-opt` hardcode. 모두 `FileNotFoundError`; G 담당이다. symlink·설치·skip으로 숨기지 않았다.
2. `test_integrations.OptionalIntegrationTests.test_acquire_optional_integration_uses_selected_cache_directory`: 기존 `XDG_CACHE_HOME/agent-optimizer/integrations` 기대값이다. 승인된 새 기본 App Home/cache/integrations와 충돌한다. G가 AGENT_OPT_HOME 기준 기대로 수정하고 explicit cache 우선순위를 유지해야 한다. A의 신규 실제 local Git/cache 테스트는 통과했다.
3. `test_dev_environment.DriverLockTests.test_selected_cvdp_setup_preserves_full_ace_lock_and_never_prepares_agent_image`: `:686`에서 argv 전체의 `"opencode"` 문자열을 검사한다. 이번 필수 TMPDIR의 `/T/opencode/final-mvp-a` 때문에 uv/python/git 등의 **경로 인수**도 오인한다. G가 실행 파일/명시 Docker image 등 의미 있는 토큰만 검사해야 한다. 모델·OpenCode를 실제 실행한 증거가 아니다.

중간 전체 실행은 978개/121.751초, failures=3/errors=15/skipped=79였다. 추가 1건은 신규 test의 manifest hash key 기대가 실제 `file:symbol` 대신 `kind/id`였던 fixture 오류이며 수정 후 통과했다. 남은 2건은 위와 동일하다.

전체 최종 로그: `/Users/wt.jeong/.local/share/opencode/tool-output/tool_0f337ba9c0011NpBLQxPPMfBd7`. 중간 로그: `tool_0f32cf236001e4nn9VgWbPPtwG`. 이 로컬 증거는 배포 산출물이 아니다.

### Ruff·diff

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m ruff check . --no-cache
git diff --check
```

둘 다 종료 0, Ruff `All checks passed!`. `make lint` 대신 공유 interpreter로 같은 Ruff 검사를 실행하여 worktree-local 환경 설치를 피했다.

마지막 fixture 문자열 한국어 정리 후 다음 좁은 재검증도 **1개/0.007초 OK**, 종료 0이었다. 제품 코드는 위 최종 전체 검증 이후 변경하지 않았다.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_history.py -k structurally -v
```

## 6. F/G/C/E 연결점과 미검증

| 담당 | 파일·함수 | 필요한 연결 |
|---|---|---|
| F | `cli._dispatch("init")`, `setup_wizard.write_experiment`, preset 설정 writer | 기본 생성 부모를 `app_path('experiments')`로 선택하고 unique ID+배타적 mkdir 사용. 새 설정은 `output_dir` 생략. 원본 `project_root` 절대 provenance와 `config_root="."`를 쓰고 agent/harness/tasks만 설정 경계 상대경로로 기록. 기존 명시 workspace/output은 보존 |
| F | `setup_wizard.prepare_selection` | 등록 provider에 현재 넘기는 project/external/datasets 경로도 `resolve_dataset_cache`로 통일. 사용자 명시 cache는 유지. CustomDataset은 default prepare를 활용할 수 있음 |
| F/C | 기본 ACE/선택형 준비 workspace | `app_path('assets')` 또는 앱이 소유한 명시 workspace를 선택해 runtime을 임의 설치/source tree에 쓰지 않도록 연결. 예제 helper의 `ROOT/external` 실행환경 경계는 C/F가 실제 소비 경로와 함께 확인 |
| F | `cli._dispatch("run-session")` | default base를 `resolve_session_base(args.output)`로 연결. `run_session`은 전달받은 정확한 session_root에서 이미 lifecycle/child 기록을 수행한다. 기존 CLI session summary의 all-error를 단순 partial로 만드는 분류도 backend error 상태와 정렬 |
| F | `cli.recent_runs/verified_run_report`, TUI History/Result | 원래 row를 보존하고 `list_history(app_home=resolve_app_home(), project_root=명시값, run_bases=명시값)` 사용. HTML 필수 필터 제거, None report·unknown/stale/diagnostic 표시. 열람 직전 `verified_report(row)` |
| F/E | server/browser action | A 재검증 직후 E `start_report_server` 호출. E의 allowlist/FD 검증은 별도로 필요. browser/server는 A 조회 함수 안에서 실행하지 않음 |
| G | `readiness.collect_dataset/collect_plan`, CLI dataset doctor 연결 | 기본 cache를 `resolve_dataset_cache`와 맞추고 명시 cache/benchmark provenance는 유지. fresh Home 읽기 전용 진단은 mkdir/acquire를 호출하지 않음 |
| G | 기존 tests | 위 15개 interpreter 오류와 XDG 기대값 1개·경로 문자열 오인 1개를 단독 취합하여 수정 |

**not_run:** 외부 모델/API, 원본 native ACE/네 CID 실평가, 실제 Docker/EDA·Ubuntu, F 통합 이후 fresh-home 제품 전체 flow, E 서버 연결, 실제 UI 변경 캡처. A가 UI를 변경하지 않아 캡처는 대상이 아니다. 현재 검증은 synthetic/local Git/fixture/모의 계약과 기존 regression이며 실환경 통합 완료 선언이 아니다.
