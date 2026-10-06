# 최종 MVP B — Textual 선택·모델 UX 구현 및 F 인계

확인일: 2026-10-01. **B 소유 범위 구현 완료, 통합 인계 사항 있음.** native/실모델/API live 성공을 의미하지 않는다.

## 1. 작업 기준·변경 파일

- 워크트리: `/Users/wt.jeong/workspace/agent-optimizer/.worktrees/final-mvp-b-20261001`, 브랜치 `feat/final-mvp-b-20261001`.
- 시작 HEAD와 준비된 `origin/main`: `edbd2b8c7b05bdd63c352d02a7adf7652168d197`. 시작 시 작업 워크트리는 깨끗했고 기본 디렉터리는 `main`이었다. 기존 워크트리를 재사용했다.
- 필수 읽기: `B_TEXTUAL_MODEL_UX.md`, 작업 `AGENTS.md`, 총괄 워크트리의 `final-mvp-p0-20261001.md` §4·§7. 현재 소스·기존 Pilot·모델 계약·`docs/FUTURE.md`를 대조했다.
- 변경: `src/agent_optimizer/tui.py`, `src/agent_optimizer/preset_tui.py`, 신규 `tests/test_tui_choices.py`, `tests/test_tui_models.py`, 이 보고서.
- `write_*`, `prepare_*`, worker/backend, registry/catalog, CLI 진입과 기존 공유 테스트는 수정하지 않았다. 하위 에이전트·install/sync·모델 다운로드·유료/외부 API 호출·서버/브라우저 실행·push/PR 없음.
- 공유 interpreter `/Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python`를 `PYTHONPATH=src`로 실행했다. 임시 fixture/output은 전용 TMPDIR 아래에 생성했고 fixture 종료 시 정리했다. 개인 Home/키 파일을 읽지 않았다.
- 이 워크트리에는 `.codegraph/`가 없어 read/grep을 사용했다. Textual 문서 조회는 Context7 quota 오류로 막혀 설치된 Textual의 실제 Pilot 결과로 확인했다.

## 2. 구현·수용 증거

| 요구 | 구현·검증 |
|---|---|
| 안정 선택 | 모든 화면 row에 `ChoiceRow`, Textual `Option.id` 제공. 실행은 `row.id`·`row.kind`로 분기한다. 같은 label·재정렬 fixture에서도 component/action을 구별한다. |
| 읽기 전용 highlight | 상세 갱신만 수행. 네 선택·disabled·뒤로가기 테스트에서 `runs`가 생성되지 않는다. |
| 상태 구분 | 미준비/비호환/설정 필요 설명 보존. ACE는 실환경 미검증을 명시한다. `docs/FUTURE.md`에 근거한 `gepa.merge`는 미구현 Planned UI metadata이며 disabled, factory 등록 없음. |
| 상세·실제 표면 | 무엇인가 → 무엇을 바꾸나 → 현재 조합 → 필요한 준비 → 제한·다음 행동. 선택한 Harness metadata의 `edit_surfaces`를 상세와 Review가 함께 소비한다. OpenCode를 native로 바꾸지 않았다. |
| 뒤로·무효화 | 안정 ID로 초점 복구, Custom/경로 draft 보존. 상위 선택 변경 때 하위 선택·초점·기존 생성 설정 포인터·진단 상태를 무효화한다. 모델 세션 값은 유지한다. |
| 모델 역할·출처 | Agent selector와 API 연결 그룹을 표시하고 Agent/Optimizer 호출 목적 및 필수 여부를 설명한다. fixture/baseline에 Optimizer API를 요구하지 않는다. native는 F metadata로만 역할/필수 API를 표시하며 coding selector를 요구하거나 유도 근거로 사용하지 않는다. |
| 선택 값 | 현재 환경/현재 세션/기존 공통 기본 모델/Custom 유지. 명시적으로 공급한 named preset은 Endpoint/Model만 허용, key·비밀 URL은 저장하지 않는다. 파일 자동 탐색이나 로컬 모델명 추측 없음. |
| URL 검증 | 기존 `ModelSettings.from_env` 기준을 재사용하고 포트 범위/빈 포트/경로 dot segment도 검증. userinfo(빈 userinfo 포함), query/fragment(빈 구분자 포함), 완성된 chat-completions, 비loopback HTTP, 잘못된 scheme/port를 입력 확정 및 Review 계속 전에 거부한다. 오류에는 URL 원문을 넣지 않는다. |
| 마스킹·비밀 | Endpoint/ID는 평문, credential input만 password. 기존 비밀 포함 환경 URL은 `자격증명 포함 URL—분리 필요`이며 Custom에 원문을 채우지 않는다. API key는 설정 여부·출처만 표시하고 세션 dict/draft repr에서 숨긴다. 기존 로그/예외/event의 `_redact_secrets`는 유지했다. 짧은 key로 정상 라벨·URL을 무차별 치환하지 않는다. |
| 충돌·유도 | 명시한 compatible selector와 API ID가 다르면 Model/실행 전 계속을 차단하고 수정하도록 안내한다. ID가 없으면 compatible selector에서 유도하고 출처를 표시한다. 입력/유도로 `os.environ`을 바꾸지 않는다. |
| 범위·화면 | 이번 세션 override는 선택한 조합에 필요한 field만 실행 환경에 덧붙인다. q는 입력 중 문자로 처리된다. 50/60열 Pilot, 한글/영어 상세 키보드 스크롤, Review/Result 스크롤, worker 동안 상태/종료 차단은 검증했다. 80열 SVG 캡처도 확보했다. |
| 보고서 연결 | History report row와 Result의 `report.open` → 공통 `action_open_report`. 현재는 기존 안전 검증 후 경로를 표시하며 F의 server/browser 연결점이다. Home에 `#home-status`/`set_home_status`를 제공한다. |

신규 테스트는 기준 코드에서 11개 실행 시 **15 failure subtest·1 error**로 시작했다. 이후 추가한 Planned/preset key 배제/native metadata/상위 선택 무효화/입력 범위/상세 스크롤도 각각 실패를 확인하고 구현했다. 최종 17개에는 캡처·SVG 비밀 부재 검증이 포함된다.

## 3. 정확한 최종 검증 명령·결과

아래 명령의 CWD는 모두 B 워크트리다. 최종 검증은 `env -i`로 개인 모델 환경/자격증명 상속을 차단했다. 모델 회귀의 HTTP는 테스트가 만든 **로컬 mock 서버**이며 외부 모델 호출이 아니다.

```bash
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/tmp HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/cache B_TUI_CAPTURE=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/captures/after-model.svg B_TUI_SECRET_CAPTURE=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/captures/after-key.svg /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p 'test_tui_*.py' -v
```

**17개 / 14.898초 / OK / 종료 코드 0**, skip 없음.

```bash
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/tmp HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_textual_tui.py -v
```

**37개 / 33.691초 / 36 통과·1 실패 / 종료 코드 1**. 실패는 `test_custom_model_endpoint_input_masks_credentials_without_hiding_safe_urls`의 `test_textual_tui.py:619`가 URL input에 `password=True`를 기대하는 옛 요구다. 최신 B/P0의 Endpoint 평문 요구와 상충하므로 제품 코드를 옛 정책으로 되돌리거나 테스트를 몰래 skip하지 않았다. G/F가 공유 테스트 한 개를 최신 URL 거부/평문 정책으로 갱신해야 한다. 기존 비밀 URL 오류/event redaction·키 마스킹·worker·실제 합성 실행·경로 안전 검증 테스트는 통과했다.

```bash
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/tmp HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p 'test_model*.py' -v
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/tmp HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_preset_tui.py -v
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m ruff check . --no-cache
git diff --check
```

- 모델 계약/입력/RTL fixture 회귀: **22개 / 14.810초 / OK**, 종료 코드 0.
- 프리셋 회귀: **45개 / 0.564초 / OK (skipped=32)**, 실행 13개 통과. skip은 기존 직접 terminal 테스트의 Pilot 대체이며 B가 추가하지 않았다.
- Ruff: **All checks passed!**, 종료 코드 0. diff whitespace 검사 통과.
- 전체 unit, real TTY/설치 wheel, 큰 창의 별도 캡처, 외부 모델/native 실도구 실행은 **not_run**. 전체 환경 baseline과 공통 테스트 갱신은 G/I 범위다. 실제 준비·외부 API 성공을 합성 Pilot로 주장하지 않는다.

## 4. 변경 전·후 Textual SVG

캡처 루트: `/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/captures/`.

- `before-model.svg`: 제품 수정 전, 비밀 없는 `https://fixture.example/v1`, `compatible/fixture-model`, key 미설정의 Model 화면, 80×28.
- `after-model.svg`: 같은 비밀 없는 fixture/같은 키 입력 순서/같은 크기의 변경 후 화면.
- `after-key.svg`: 테스트 전용 sentinel을 password input으로 입력한 변경 후 화면. SVG에 실제 sentinel이 없음을 `export_screenshot` 검사로 확인했다. 실제 개인 키를 사용하지 않았다.

재현은 §3 첫 명령이다. `B_TUI_CAPTURE` 없이 실행하면 캡처용 테스트 한 개만 skip하고 기능 테스트는 그대로 실행한다. 변경 전 캡처는 기준 코드에서 `B_TUI_CAPTURE=.../before-model.svg`로 최초 RED 테스트 실행 때 저장했으며 저장된 파일은 그때의 화면이다.

## 5. 새 API/결과 schema 및 F 연결점

### 안정 row 계약

`preset_tui.ChoiceRow(id: str, kind: str, label: str, description: str, enabled: bool=True, reason: str='')`는 frozen dataclass다. 기존 read-only tuple consumer를 위해 `[0..3]`/`len`만 호환 제공한다. **새 action 실행은 반드시 `id/kind`를 사용한다.** `preset_options(...) -> list[ChoiceRow]`.

- component ID는 실제 선택 ID: `ace-rtl`, Agent manifest ID, `ace-opencode`, `fixture`, `gepa`, `meta_harness`, `baseline`, `file_variants`, `cvdp`, `sample_text`, 기존 registry의 다른 ID.
- 프리셋 이동 action: `advanced`, `existing`; Home: `new`, `existing`, `history`, `advanced`, `quit`.
- Review: `model.edit`, `prepare`, `cancel`; Preparing: `prepare.retry`, `doctor`, `review`; Doctor: check ID(`kind=check`), `run`, `doctor.retry`, `review`; Result: `doctor`, `home`, `report.open`.
- Existing row ID는 설정 경로(`kind=configuration`), 직접 입력은 `path.custom`. History row ID는 기존 run ID(`kind=report`). A의 확장 이력 row로 변환하는 부분은 F 소유다.
- Model field ID는 환경 field 이름(`kind=model.field`), 값 선택은 `environment`, `session`, `default`, `preset:<name>`, `custom`(`kind=model.choice`), 입력은 field ID(`kind=model.input`).
- `gepa.merge`, `kind=planned`, `enabled=False`는 표시 전용이다. 등록하거나 선택/준비 경로에 전달하지 않는다.

### 모델 결과·metadata

- `OptimizerApp.model_presets = {name: {'AGENT_OPT_MODEL_BASE_URL': url, 'AGENT_OPT_MODEL_ID': model}}`: F가 명시적으로 선택한 비밀 없는 설정을 공급한다. setter는 이 두 field만 보존하고 유효하지 않은 값/key를 버린다. getter는 복사본을 반환한다. 키와 설정 파일 저장/탐색 책임은 이 API에 없다.
- `model_values`/`input_drafts`는 세션 메모리이며 secret field의 repr는 값 대신 설정 표시다. `model_sources` 값은 `environment/default/session/file/derived/missing`. `derived`는 coding compatible selector에서 ID가 비어 있을 때만 사용한다.
- `model_configuration() -> {'fields': {field: {'value': str | None, 'configured': bool, 'source': str}}, 'usage': str}`: UI/Review용 안전 metadata. credential `value`는 항상 `None`; 비밀 URL도 안전한 설명만 반환한다. **실행 설정으로 이 표시값을 쓰지 않는다.**
- `_execution_environment() -> dict[str,str]`: 기존 process environment의 복사본에 필요한 session field만 덧붙이고 compatible ID를 정규화/충돌 검사한다. 이 실행 전용 결과에는 credential이 있으므로 repr/log/TOML/report로 저장하지 않는다. 입력 과정에서 `os.environ`을 수정하지 않는다.
- `validate_endpoint(value) -> None`은 값 없는 `ConfigurationError`로 거부한다. `display_endpoint(value) -> str`은 안전한 평문 또는 분리/수정 필요 설명이다. backend 공통 검증을 바꾸지 않았다.
- `component_metadata[component_id]`: 선택 description/`edit_surface` override. `component_metadata[harness_id]`의 `edit_surfaces: {optimizer_id: path}`, `execution_mode: 'native'`, `requires_model_api: bool`, `model_roles: list[str]`를 소비한다. F가 C의 실제 metadata를 연결해야 한다. native registry/default/writer/실행 연결은 B에서 만들지 않았다.
- role별 모델 override가 C metadata에 있으면 F가 실제 소비 계약과 함께 표시를 확장해야 한다. B의 현재 native 표시 확장점은 공통 endpoint/model/key와 역할 이름이며 role-provider 플랫폼을 추가하지 않았다.

### 보고서·공통 파일 인계

1. **F:** `action_open_report(report: Path, status: str='completed')`에서 A의 `verified_report(row)`를 소비한 뒤 E의 `start_report_server`/browser를 연결한다. 현재는 legacy `verified_run_report`로 재검증 후 경로만 보여 준다. Result/History는 이 한 action으로 들어온다.
2. **F:** `set_home_status(text: str)`/`#home-status`에 실제 server URL/상태를 공급하고 종료·보고서 교체 시 handle을 close한다. B hook은 자원을 만들지 않는다.
3. **F/G:** 기존 `model_input.session_environment`는 worker의 실행 경계 동안 `os.environ`을 임시 수정한 뒤 finally에서 복구한다. 기존 직렬 복구 회귀는 통과했으나 **서로 겹치는 같은 프로세스의 세션/worker 완전 격리는 증명하지 못했다**. 완전 격리가 필요하면 backend의 명시 env 전달/프로세스 경계에서 해결해야 한다. B는 금지된 worker/backend를 수정하지 않았다.
4. **G/F:** 앞서 명시한 공유 Pilot 한 개의 옛 Endpoint password 기대를 최신 정책으로 변경한다. 신규 전용 테스트가 평문·URL 거부·비밀 부재를 검증한다.
5. **G:** 새로운 사람용 문구는 한국어로 작성했다. 공통 locale 취합 시 `Agent 설정`, `API 연결`, `API 모델 ID`, `Optimizer API: 필수/불필요`, `Agent/Optimizer 사용량`, `named preset/파일`, `자격증명 포함 URL—분리 필요`, `잘못된 URL—수정 필요`, URL 검증 오류, `HTML 보고서 보기` 및 Planned 설명을 반영한다. 기존 `_tr` 영어 UI와 한글/영어 좁은 화면 Pilot은 유지했다.

## 6. 완료 판정

**DONE / concerns:** B 전용 테스트·Ruff·관련 모델/프리셋 회귀는 통과했다. 공유 옛 요구 테스트 한 개 실패와 F/G 연결 책임을 숨기지 않는다. 변경 전후 캡처와 새 API를 이 보고서에 기록하고 지정 소유 파일만 로컬 한국어 커밋한다. 기본 디렉터리의 사용자 `.gitignore` 변경 및 zip, 다른 작업 워크트리를 보존한다.

## 7. 수정 라운드 1 — 중요 리뷰 finding 처리

시작 기준: `520f4a7225eeb3e0a3ce7952f57e18fedee844d0`. `final-mvp-b-review-20261001.md` 전체를 읽고 B-01~B-05를 실제 Pilot로 재현했다. 리뷰 보고서는 의도된 인계 파일로 함께 커밋하며 원래 판정과 근거를 보존한다. 아래 결과는 최초 보고 이후의 새 증거이고, selector 유도 범위와 URL draft 처리의 앞선 설명은 이 절을 기준으로 읽는다.

| finding | 수정 | 의미 있는 회귀 |
|---|---|---|
| B-01 · fixture 누락/중복 | fixture row append를 manifest 존재 분기 안으로 복구. 같은 ID는 하나의 row로 정리하며 연결된 enabled row를 우선한다. | examples 없는 실제 임시 workspace, solo만/team만 있는 workspace, 두 manifest가 같은 ID를 가리키는 경우 모두 새 최적화 → Agent가 정상 진입하고 ID가 유일함. |
| B-02 · URL draft 비밀 노출 | `ModelInput.validate_value`가 Textual reactive 저장·render·Changed 메시지 생성 **이전**에 userinfo/query/fragment 및 비숫자 port 형태의 미완성 user:password를 빈 문자열로 바꾼다. 거부 메시지에는 원문을 넣지 않는다. draft 저장/뒤로/재진입에서도 검사하고 Endpoint의 dict repr는 안전한 표시값만 반환한다. | credential URL을 대입한 직후, Enter 전부터 value/render에 sentinel 없음. Esc·Custom 재진입·SVG·legacy draft repr에도 없음. 실제 키 입력에서 거부된 비밀의 나머지도 제거. 긴 정상 HTTPS 경로와 loopback IPv6/숫자 port는 plaintext이고 API key만 password. |
| B-03 · bare selector 표시/실행 불일치 | `_model_value`의 유효값을 schema/Review/실행 환경이 함께 소비. bare `team-model`은 `compatible/team-model`, API ID 없음은 `team-model`/derived로 표시·실행한다. 원래 환경값은 덮어쓰지 않는다. | 기본 및 사용자 정의 bare selector에서 schema의 ID/selector/source와 `_execution_environment` 결과가 일치하며 Review를 통과. |
| B-04 · 사용자 selector 충돌 미차단 | `_model_selector_fields(spec=None)`가 실제 선택한 profile의 `model_env` 목록을 구한다. 모든 compatible selector를 공통 API ID와 비교하고 오류에는 해당 field 이름만 안내한다. 서로 다른 profile에서 하나의 implicit API ID를 임의로 고르지 않는다. | `TEAM_AGENT_MODEL` 충돌로 Model 계속 및 Review의 준비 action 차단·busy=False·runs 미생성. 명시적 API ID 수정 후 계속 가능. 두 번째 profile의 다른 selector도 차단하고 환경값 보존. |
| B-05 · Workspace 선택 덮어쓰기 | Workspace 확정은 경로만 변경하고 네 component 선택을 유지한다. | 설치형 분기에서 Baseline/Meta-Harness 각각 선택·Workspace 입력·Model·뒤로를 실제 Pilot로 검증. OpenRouter Baseline에 Optimizer API를 추가 요구하지 않음. |

URL 거부 후에는 정상 URL을 통째로 붙여넣거나 Esc → 직접 입력으로 재설정할 수 있다. 거부된 typing/paste의 뒤따르는 문자열을 빈 입력에 다시 노출하지 않도록 유지한다. 숫자 port/IPv6 같은 정상 Endpoint 구문을 password로 전환하지 않으며, 일반 host/port 입력을 비밀이라는 이유로 무차별 마스킹하지 않는다. API key는 기존 별도 입력과 세션 메모리 계약을 유지한다.

### 실제 검증 명령·결과

CWD·공유 Python·임시 Home/cache/TMPDIR 정책은 §3과 같고 최종 명령은 모두 `env -i`로 실행했다. 제품 수정 전 RED는 **23개 / 18.547초 / failures=10, errors=4, skipped=1**이었다. manifest의 `UnboundLocalError`/`DuplicateID`, URL draft 원문, bare 모델값, 사용자 충돌, Workspace 덮어쓰기를 확인했다. 새 `test_tui_textual.py`의 부분 credential 키 입력도 수정 전 **1개 / 1.020초 / failure=1**을 확인했다.

```bash
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/tmp HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/cache B_TUI_CAPTURE=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/captures/round1-model.svg B_TUI_SECRET_CAPTURE=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/captures/round1-key.svg /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p 'test_tui_*.py' -v
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/tmp HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_textual_tui.py -v
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/tmp HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p 'test_model*.py' -v
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/tmp HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_preset_tui.py -v
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-b/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m ruff check . --no-cache
git diff --check
```

- `test_tui_choices` 9개 + `test_tui_models` 14개 + 신규 `test_tui_textual` 1개: **24개 / 24.170초 / OK**, 종료 코드 0, skip 없음.
- 기존 공유 `test_textual_tui`: **37개 / 32.856초 / 36 통과·1 실패**, 종료 코드 1. 실패는 앞서 기록한 `test_custom_model_endpoint_input_masks_credentials_without_hiding_safe_urls`의 `password=True` 옛 요구(`:619`) 하나뿐이다. 이 라운드에도 공유 테스트 변경/skip 추가 없이 남겨 G/F에 전달한다.
- 모델 회귀: **22개 / 14.840초 / OK**, 종료 코드 0. 로컬 mock HTTP 외 live 모델 호출 없음.
- 프리셋 회귀: **45개 / 0.558초 / OK (skipped=32)**, 실행 13개 통과. 기존 skip 사유 유지.
- Ruff **All checks passed!**, diff whitespace 검사 통과.
- 비밀 없는 fixture의 새 캡처: 기존 전용 captures 루트의 `round1-model.svg`, `round1-key.svg`. credential URL의 Esc/재진입 화면은 저장 전에 `export_screenshot`에서 sentinel 부재를 검증했다.
- 전체 unit/native 실모델/설치 wheel·실 TTY는 이번 수정 라운드에도 **not_run**이다. 검증 수준을 확장해 주장하지 않는다.

### F 최소 연결 요구·소유권

이번 **B-01~B-05 수정 자체에 F generation 변경은 필요하지 않았다**. `write_*`, `prepare_*`, worker/backend, registry/catalog/CLI 진입 및 다른 담당자의 파일은 수정하지 않았다. F의 기존 연결에서는 다음 작은 계약만 보존하면 된다.

1. 표시/schema와 실행에는 같은 `_model_value(field)` 유효값을 사용하고, 실행 환경은 `_execution_environment()` 결과를 그대로 소비한다. 기본 `AGENT_OPT_MODEL` 하나를 다시 해석하거나 다른 profile의 `model_env`를 덮어쓰지 않는다. 반환 environment를 기록/직렬화하지 않는 비밀 계약은 그대로다.
2. Workspace writer/prepare 입력은 `self.workspace`와 사용자가 고른 `self.selections['Optimizer']`이다. UI가 고른 Baseline/Meta-Harness를 GEPA로 다시 대체하지 않는다. 현재 기존 `prepare_work`의 인자 전달은 이 계약을 이미 소비하므로 B는 generation을 수정하지 않았다.
3. `#entry`는 `Input` subclass `ModelInput`이다. 공통 UI 재구성 시 `endpoint_mode`는 Endpoint input에서만 켜고 재진입 때 거부 상태를 재설정하는 `_show` 계약을 유지한다. URL을 value로 직접 복구하기 전에 `endpoint_contains_credentials`/안전 표시 검사를 우회하지 않는다. 새 거부 설명은 G 공통 locale 취합 대상이다.
4. §5의 native 역할 metadata, 보고서 서버 연결, 기존 worker의 전역 환경 임시 변경 및 공유 옛 정책 테스트 갱신은 이전과 같은 F/G 통합 범위다. 이번 URL/선택/모델 UI 결함을 그 인계사항으로 미루지 않았다.

**라운드 1 판정:** 중요 finding 5건 수정·전용 Pilot 검증 완료. 공유 옛 정책 실패 한 건과 실환경 미검증 영역은 별도로 유지한다. 리뷰 원문에 새 리뷰 승인 판정을 덧씌우지 않으며 제품/증거 변경을 로컬 후속 커밋으로 기록한다.
