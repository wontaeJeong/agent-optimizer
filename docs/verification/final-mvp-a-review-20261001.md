# 최종 MVP A 코드 리뷰 — App Home·실행 이력 backend

검토일: 2026-10-01. 대상: `edbd2b8c7b05bdd63c352d02a7adf7652168d197` → `b665efe5c2e5cb4d04185cb9ed18e588523d2e25`.

## 판정

- **요구사항 준수 verdict: 수정 필요.** 경로 계약의 핵심은 충족하지만, 명시/legacy session 조회와 종료 근거·손상 session 판별에 A 소유 backend 결함이 있다.
- **코드 품질 verdict: 수정 필요.** 작은 모듈 분리, 읽기 전용 조회, FD 기반 no-follow, 원자적 lifecycle 게시와 실질적인 회귀 테스트는 적절하다. 아래 Important 3건은 연결 전 수정해야 한다.
- **Critical 0 / Important 3 / Minor 1.** 발견 사항은 정적 소스·호출 흐름에 근거하며 이번 리뷰에서 재현 실행이나 테스트 재실행은 하지 않았다.

## 검토 범위와 기준

지정 brief `prompts/A_APP_HOME_HISTORY.md`, 인계 `docs/verification/final-mvp-a-20261001.md`, 지정 diff를 먼저 읽고 현재 변경 소스 및 관련 기존 호출부·테스트를 대조했다. 현재 A HEAD는 지정한 `b665efe`이며 검토 시작 시 A 워크트리는 깨끗했다.

- 상대 `AGENT_OPT_HOME` 거부는 최종 확정 요구로 취급했다. P0의 상대허용 제안은 적용하지 않았다.
- F의 CLI/TUI/설정 writer 연결은 A 판정에서 제외했다. 기존 CLI는 legacy session 저장 레이아웃과 summary 형식을 확인하는 근거로만 읽었다.
- 수정 제안은 A backend 범위다. 제품 코드·테스트 수정, 커밋·푸시·PR, 하위 에이전트 사용은 하지 않았다. 유일한 변경은 이 문서다.

## Important

### I1. 명시 custom/legacy session 부모를 전달해도 session 이력을 읽을 수 없다

**위치:** `src/agent_optimizer/history.py:236-245` (특히 `239`), 관련 `133-145`, `170-171`.

`list_history`는 Home의 `sessions`만 `kind='session'`으로 스캔한다. 모든 `run_bases`는 무조건 `kind='run'`이며 `project_root` 조회도 `runs`와 `runs/dev-live`뿐이다. 따라서 Home 밖에서 `run_session`으로 만든 session 부모를 명시적으로 전달해도 다음 문제가 발생한다.

1. 유효한 `kind='session'` lifecycle은 요청 kind와 다르다는 이유로 폐기된다.
2. 기존 session summary는 run schema가 아니어서 폐기된다.
3. session `index.html` 대신 `report.html`을 찾고, `runs/<slot>/<run ID>` child 조회도 실행하지 않는다.

결과는 실제 session의 상태·보고서·child 링크를 잃은 `kind='run', status='unknown', report_path=None` row다. 기존 CLI의 session 기본 위치 역시 Home 밖의 `sessions`이고 explicit `--output`도 지원한다(`src/agent_optimizer/cli.py:698-704`, `714-718`). 명시된 session 부모를 현재 공개 API로 전달해도 해결되지 않으므로 단순 F 연결 누락이 아니다.

**요구 근거:** A brief 29행의 explicit output 보존, 44행의 명시 legacy/custom output 조회 및 실제 session child 참조, 51행의 session→child 수용 테스트.

**수정 방향:** 명시 session 부모를 표현할 수 있는 인자를 추가하거나, 안전하게 읽은 lifecycle/기존 session summary로 실제 kind를 식별한다. 명시 경계만 스캔하고 JSON의 외부 child 링크는 계속 무시해야 한다.

**누락된 검증:** Home 밖 custom session과 기존 summary-only session을 명시 부모로 조회하여 상태·`index.html`·실제 child 링크를 확인하는 테스트. 현재 session 테스트는 모두 Home의 `sessions` 아래에 배치된다(`tests/test_history.py:97-109`, `141-160`, `185-198`).

### I2. running summary/lifecycle이 있으면 실제 종료 이벤트를 무시한다

**위치:** `src/agent_optimizer/history.py:146-163` (특히 `149-152`).

이벤트 fallback은 상태가 허용 상태 집합 밖일 때만 실행된다. `running`은 집합 안에 있으므로 유효한 running lifecycle이나 legacy running summary가 있으면 `events.jsonl`을 읽지 않고 곧바로 `stale`로 바꾼다.

정적 재현 조건은 초기 `status='running'` lifecycle과 `{"event":"interrupted"}` 또는 `{"event":"source_error"}`가 있는 events, terminal summary가 없는 run이다. 반환 상태는 각각 interrupted/source_error가 아니라 stale이며, 진단까지 “종료 기록이 없습니다”라고 말한다. runner는 먼저 종료 이벤트를 기록하고 finally에서 terminal lifecycle을 게시하므로 이 중간에 중단되거나 lifecycle 게시가 실패하면 실제로 이 조합이 남을 수 있다(`src/agent_optimizer/runner.py:497-517`).

**요구 근거:** A brief 42-43행의 기존 summary/manifest/events 우선 활용과 실패·중단·불완전 종료 구분. 인계 문서 70행도 실제 실패/중단 events의 보완을 약속한다.

**수정 방향:** terminal summary/lifecycle이 없으면 running 상태에서도 안전하게 종료 events를 확인하고, 종료 근거가 없을 때만 stale을 사용한다. 정상 terminal summary의 우선순위는 유지한다.

**누락된 검증:** `running lifecycle + terminal event`와 `running summary + terminal event`. 현재 이벤트 테스트는 summary를 삭제하고 lifecycle도 없는 경우만 확인한다(`tests/test_history.py:111-121`).

### I3. session summary에는 구조 검증이 없어 손상 기록이 성공을 만들 수 있다

**위치:** `src/agent_optimizer/history.py:138-148`.

summary 구조 검증은 `kind == 'run'`에만 적용된다. session에서는 JSON 객체이기만 하면 `status`를 그대로 정본으로 채택한다. 예를 들어 유효한 error lifecycle이 있는 session의 `summary.json`이 `{"status":"completed","experiments":"손상"}`으로 손상되어도 completed가 반환되고 손상 진단이 없다. `{"status":"completed"}`처럼 실제 기존 session summary의 필수 `experiments`가 없는 객체도 동일하다.

기존 session 형식에 `schema_version/run_id`가 없다는 사실은 그대로 지원해야 하지만(`src/agent_optimizer/cli.py:717-719`), 이는 `experiments` 배열과 child entry 구조를 전혀 검증하지 않는 근거가 되지는 않는다. 이 문제는 기존 CLI의 all-error→partial 분류를 F가 수정하는 연결 작업과 별개다.

**요구 근거:** A brief 43행의 근거 없는 성공 방지·상태 구분과 45행의 손상 JSON 안전 처리. 정상 terminal **summary**가 정본이라는 규칙은 유효한 구조에만 적용해야 한다.

**수정 방향:** 실제 legacy session summary 형식을 검증하고, 손상/불완전 구조이면 진단을 남긴 뒤 유효 lifecycle 또는 unknown/stale로 보완한다. Home session 및 I1의 명시 session 경계에 같은 검증을 적용한다.

**누락된 검증:** 손상 session summary + 유효 error/interrupted lifecycle, summary-only legacy session의 정상/손상 구조. 현재 구조 손상 테스트는 run에만 적용된다(`tests/test_history.py:253-261`).

## Minor

### M1. 실제 CWD 변경과 explicit 상대 output의 보존 계약을 함께 검증하지 않는다

**위치:** `tests/test_app_paths.py:38-39`, `52-59`; `tests/test_history.py:37-50`.

resolver 테스트의 `cwd`는 의도적으로 미사용인 호환 인자이며, history 테스트는 `Path.cwd`만 patch하고 실제 프로세스 CWD를 변경하지 않는다. output 우선순위 테스트도 explicit 절대경로만 사용한다. 현재 구현의 절대 Home 기반 조회는 정적으로 타당하지만, 이 테스트들만으로 brief가 요구한 서로 다른 실제 CWD에서의 동일 이력과 CLI 상대 output의 기존 CWD 기준 의미까지 검증했다고 보기는 어렵다.

**보완 방향:** 임시 두 CWD를 사용하는 별도 프로세스에서 같은 이력을 조회하고, 각 CWD에서 explicit 상대 output이 그 CWD의 output 부모로 해석되는지 확인한다. 실제 사용자 Home은 계속 격리한다.

## 계약별 대조

| 계약 | 정적 검토 결과 |
|---|---|
| pure resolver / Home override | `app_paths.py:15-52`는 mkdir/acquisition이 없고 상대 env를 `ConfigurationError`로 거부한다. 기본 Home·expanduser·한글/공백 경로를 다룬다. |
| explicit output / 기존 TOML | explicit output > 명시 `output_dir` > Home/runs를 보존한다. `output_dir='runs'`도 기존 명시값이다. explicit 상대 output은 CWD 기준 resolve이며 run 부모 의미와 run ID/layout을 유지한다. M1의 테스트 공백은 남는다. |
| project_root / config_root | `config.py:194-209`, `215`, `240`에서 설정 파일 경계와 원본 프로젝트를 분리한다. runner benchmark hash는 설정 경계를 사용하고 플러그인·seed는 원본 프로젝트 기준이다(`runner.py:457-464`). local source의 manifest 기준 해석을 유지하며, 이동 writer의 절대 provenance 기록은 F 인계 사항이다. |
| cache / source writer | integration 및 selected dataset 기본 cache가 Home으로 바뀌며 explicit cache는 우선한다. offline miss는 실패한다. custom artifact는 배타적 hard-link 게시로 기존 수정 파일을 보존하고 pinned checkout 게시 충돌은 pin/dirty 확인 후 재사용한다. Git Agent 임시 checkout은 run target 안에 생성된다. |
| read-only / no-follow | History는 directory-relative `O_DIRECTORY|O_NOFOLLOW`, 파일 `O_NOFOLLOW|O_NONBLOCK` 및 일반 파일 확인을 사용한다. symlink/FIFO/손상 JSON은 진단으로 처리하며 디스크 전체 검색·모델·브라우저·metadata 수정은 없다. `verified_report`는 고정 파일명·상태·root inode를 재검증한다. 반환 Path 이후 서버의 추가 검증 필요성도 명시되어 있다. |
| history / legacy | report 없는 run도 row로 반환하며 절대 경로·ID·시각·상태와 중복 제거를 제공한다. 명시 session 경계, running+종료 event, session summary 구조는 I1-I3 때문에 미충족이다. |
| lifecycle / session | 고유 임시 파일·flush/fsync·replace, runner 생성/종료 기록 및 session child 상대 run 경로가 구현되어 있다. 부모 callback 오류의 worker 정리와 setup 오류 기록 테스트도 있다. History의 해석 결함과 writer 연결 범위를 구분해야 한다. |

## 테스트와 증거의 평가

신규 테스트는 단순 구현 복사만 하지 않는다. 실제 합성 runner, 두 동시 run, 로컬 Git checkout 및 게시 race, 수정 artifact 충돌, 실제 spawn session child, interruption/callback 오류 정리, report writer 실패 뒤 lifecycle, symlink/FIFO/URI/root 교체를 검증한다. 외부 config_root와 원본 프로젝트 plugin/seed를 함께 실행하는 검증도 의미 있다.

인계 문서의 **기존 실행 결과**는 관련 111개 OK, session 11개 중 통과 10/skip 1, 전체 983개에서 failures 2/errors 15/skipped 79, Ruff 및 당시 diff check 종료 0이다. 이 리뷰가 테스트 통과를 새로 확인한 것은 아니다. 보고된 전체 실패의 XDG 기대값·워크트리 interpreter·임시 경로 문자열 문제는 F/G 인계와 구분하여 A 코드 결함으로 추가 집계하지 않았다.

사용자 지시에 따라 테스트·모델·네트워크·설치 작업을 재실행하지 않았다. 실환경 성공 및 제품 전체 연결 완료 판정도 하지 않는다. I1-I3에 해당하는 경계 조합은 현재 테스트에서 빠져 있으므로, 기존 관련 테스트 통과만으로 A 요구사항 전체 충족을 판단할 수 없다.
