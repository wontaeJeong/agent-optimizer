# 최종 MVP G 독립 리뷰 — 코드·요구사항

검토일: 2026-10-01. 대상 HEAD `474c930`, 기준 `be41046`. **코드 verdict: 수정 필요. 요구사항 verdict: 부분 충족·승인 보류. Critical 0 / Important 3 / Minor 1.**

## 범위와 검증 수준

- 지정 `final-mvp-review-g.diff`를 먼저 읽고 G brief, G 보고서, F §6~§8, 실제 변경 소스와 `docs/SOURCES.md`를 대조했다. 파일·행은 대상 HEAD 기준이다.
- 기존 suite/build/smoke는 재실행하지 않았다. 보존된 `final-mvp-g/baseline.log:1669–1671`의 1131개·41 failure·41 error·skip 80 및 `unit-final5.log:1552–1554`의 1141개·OK·skip 80을 직접 확인했다. `build-final4.log:184`의 wheel 생성 기록과 `package_smoke.py`의 source-free subprocess/HTTP/누락 자산 복구 검사도 읽었다. 이는 G 실행 증거이며 리뷰어의 신규 통합 실행 결과가 아니다.
- 신규 확인은 공유 Python의 `-I -B -c`로 수행한 메모리 내 진단 호출뿐이다. 파일 존재·실행 결과는 필요한 부분만 mock했으며 모델·Docker·다운로드·mkdir·설치·실제 Agent 실행은 하지 않았다. 이 확인은 아래 선택/설정/redaction 오류 재현이지 native 성공 증거가 아니다.
- 하위 agent·코드 수정·커밋 없음. 허용된 이 리뷰 문서만 작성했다. 기본 저장소의 `main`, 기존 `.gitignore` 변경과 ZIP을 보존했다.

## Important

### R1 — Native 진단이 첫 Harness profile만 검사한다

**근거:** `examples/ace-rtl/native_selection.py:27–31,37–39`; 호출부 `src/agent_optimizer/readiness.py:560–564`. 실제 검증은 `examples/ace-rtl/native_selection.py:203–210`에서 전달된 profile이 native가 아니면 건너뛴다. 공통 계약은 `src/agent_optimizer/config.py:144–170`의 복수 profile·명시 pair를 지원한다.

- `collect_plan`은 profiles 중 하나라도 native이면 진단을 호출하지만, 예제 진단은 무조건 `_profiles[0]`을 선택한다. 첫 profile이 `command`이고 둘째가 `ace_native`이면 둘째 dataset/private row 검증을 실행하지 않고 `native.selection=ok`를 추가한다.
- 첫 profile이 native여도 나머지 native profile의 dataset/interpreter/evaluator를 검사하지 않는다. 전체 `_agents`에 첫 native 설정을 적용하므로 명시 pair에 따라 관계없는 Agent를 native 소스로 오진할 수도 있다.
- 읽기 전용 재현 출력: `R1 diagnosis: ok`; 같은 둘째 profile을 실제 `verify_native_selection`에 전달하면 `native 고정 dataset 경로가 필요합니다`. 전체 doctor가 반드시 ready라는 주장은 아니며, 해당 check의 거짓 성공을 확인했다.
- **영향/요구사항:** brief §2의 native 실패 진단과 복수 Agent/Harness 계약을 만족하지 못한다. profile 순서에 따라 private 검증·의존성 판정이 달라진다.
- **수정 방향:** 실제 선택된 Agent–Harness pair의 native profile마다 검증하고, profile별 결과를 구분하면서 기존 5-key check shape를 유지한다. 첫 profile 고정을 없애는 수정은 examples 정책 안에서 수행한다.

### R2 — 실제 outer Evaluator 대신 profile의 inner Evaluator만 진단한다

**근거:** `examples/ace-rtl/native_selection.py:46–76`; 실제 outer 설정은 `src/agent_optimizer/runner.py:56–61`, 자산/image 소비는 `examples/ace-rtl/evaluator.py:34–60`이다. 생성 시에는 `examples/ace-rtl/native_selection.py:321,332–335`가 두 위치에 같은 값을 쓰지만, 이후 두 설정의 동일성을 강제하는 계약은 없다.

- 진단은 `profile.native.evaluator`가 존재하면 `spec.evaluator_config`를 완전히 무시한다. 전자는 native 내부 반복 평가 설정이고 후자는 코어가 실제 최종 평가기에 전달하는 독립 설정이다.
- 읽기 전용 mock 재현에서 profile에 `/profile-good`, `/profile-python`, `profile-tag`를, top-level에 `/outer-missing`, `/outer-missing/python`, `outer-tag`를 넣었다. 실제 진단 argv는 `/profile-good`의 Git, `/profile-python` import, `profile-tag` inspect만 포함했고 `native.evaluator.*`는 모두 `ok`였다. `evaluator_settings(spec)`는 그대로 `/outer-missing`과 `outer-tag`를 반환했다.
- **영향/요구사항:** 실제 최종 평가에 필요한 repo/interpreter/image가 누락되거나 pin/identity가 틀려도 해당 진단에서 잡지 못한다. 생성 직후 중복 값이 같은 정상 fixture로는 드러나지 않으며, brief §2·§3의 evaluator 및 offline missing asset 진단이 불완전하다.
- **수정 방향:** inner 설정과 실제 outer 설정을 각각 검사한다. 둘을 독립적으로 둘 수 있는 기존 계약을 임의로 축소하지 말고, 동일 설정은 검사 재사용으로 중복 실행만 줄인다.

### R3 — 전체 문자열 redaction이 정상 retry 옵션을 파괴한다

**근거:** 신규 `src/agent_optimizer/readiness.py:121–129,420–422,630–638`; 기존 redactor의 값 수집·치환은 `src/agent_optimizer/diagnostics.py:29–31,69–84`. 보고서 오류도 `src/agent_optimizer/report_view.py:65–69`에서 전체 structured 문자열을 같은 함수로 처리한다.

- redactor는 이름에 `MODEL`이 든 환경값도 비밀로 취급하고 문자열 전체에서 무조건 치환한다. G가 정상적으로 만든 retry까지 이 redactor에 통과시키면서 모델 ID와 겹치는 command/flag/path가 손상된다.
- 읽기 전용 재현: `AGENT_OPT_MODEL_ID=model`, 별도 API key, retry `agent-opt doctor --plan /tmp/experiment.toml --model`을 `check`에 전달했다. 실제 결과는 `Retry: agent-opt doctor --plan /tmp/experiment.toml --[redacted]`였다. 명시 probe 옵션이 더 이상 실행 가능한 옵션이 아니다.
- **영향/요구사항:** brief §2와 수용 조건의 실행 가능한 Retry·원래 model 옵션 보존을 위반한다. `shlex.join`의 인용만으로 해결되지 않으며, 짧은 key나 경로와 겹치는 모델값도 structured 안내를 손상시킬 수 있다.
- **수정 방향:** 비밀값과 공개 모델 ID/명령 토큰을 구별해 처리하고 command/flag를 보존한다. 실제 비밀이 포함된 사용자 인수를 그대로 출력하는 방식으로 고치지 않는다. 겹치는 모델명 및 짧은 key에서 옵션·안내 키 보존을 확인할 필요가 있다.

## Minor

### R4 — Dataset doctor의 cache 이동 후 무변경 assertion 범위가 좁아졌다

**근거:** `tests/test_datasets.py:58–75,83–89`, 신규 cache 위치 `src/agent_optimizer/readiness.py:188–189`, fixture Home `tests/support.py:21–34`.

- 옛 cache는 `project/external/datasets/...`여서 `project.rglob` before/after에 포함됐다. 교체 후 cache는 sibling `home/cache/datasets/...`에 있지만, 무변경 비교는 계속 `project.rglob`만 사용한다.
- 따라서 dataset/plan doctor가 실제 cache의 `prepared.txt`를 바꾸거나 cache에 파일을 생성해도 이 보호 assertion은 탐지하지 못한다. cache resolver로 fixture를 옮기는 것 자체는 정당하지만 read-only 검사의 보호 범위는 약화됐다.
- **수정 방향:** project와 App Home/cache의 파일·디렉터리 상태를 모두 비교한다. 미준비 cache에서 doctor 이후 Home/cache가 생성되지 않았는지도 확인한다. 제품에 실제 cache 쓰기가 있다는 finding은 아니다.

## 82건 공유 실패 교체 판정

**대부분 legitimate이며 실패를 skip/삭제/xfail로 숨긴 변경은 발견하지 않았다. 다만 R4 때문에 모든 보호 assertion이 약화 없이 유지됐다는 일괄 승인은 할 수 없다.** baseline 실패 이름과 변경 diff를 F의 명시 인계 계약에 대조했다.

| 교체 종류 | 요구사항 의미·보호 판정 |
|---|---|
| `.venv` hardcode → `sys.executable`/module entrypoint | 워크트리 환경 사용을 바로잡음. 언어/exit 2/JSON/no traceback assertion 유지 |
| `runs/configs/<name>` → 출력 JSON의 실제 `experiment/session` | Home UUID 계약에 맞음. metric/argv/pin/budget·실제 합성 실행·보고서 검증 유지 |
| 고정 번호/Enter 횟수 → inventory/stable ID·명시 `ace-opencode` | 기존 legacy 기능을 계속 검증하며 native-first 변경과 충돌 해소. native 전용 시험을 제거하지 않음 |
| 기존 이름 충돌 실패 → 독립 UUID 성공 | 같은 이름의 새 설정 허용과 기존 사용자 sentinel 보존이라는 새 계약에 맞음. Home dangling 폴더 검사 추가는 강화 |
| seed 원본 root → `_seed_root`, symlink 경계 → Home/experiments | 실제 실행 seed의 변조·누락과 준비 전 symlink 거부를 계속 검증 |
| Endpoint password 기대 → 평문 safe URL·credential 즉시 거부 | B의 정책 변경에 맞음. `test_tui_models.py:77–98`의 즉시 render/value 비노출과 `test_tui_textual.py:18–43`의 partial typing 보호 유지 |
| TMPDIR 전체의 `opencode` substring → 실행 파일/Dockerfile 인수 | `/T/opencode/` 오탐 제거. Agent image build 금지와 offline clone/build 금지 assertion 유지 |
| asset Path mock·optional output kwargs·canonical path·dict history | 실제 반환/호출/이력 계약으로 fixture 정상화. provider/image·부모 session error·worker cleanup 보호 유지 |
| 고유 Home 격리·App Home cache 기대 | 공유 이전 이력 오염과 옛 XDG 기대 제거는 정당함. dataset read-only snapshot만 R4 보완 필요 |

## 나머지 요구사항 대조

- **읽기 전용·모델:** `collect_plan`의 새 Home 검사에는 mkdir가 없고, 실제 모델 probe는 `model=True` 분기뿐이다(`readiness.py:543–558,630–638`). native 진단은 Git/import/로컬 image inspect이며 download/pull/run 경로를 추가하지 않았다. 모델 baseline의 Agent API와 coding selector/Optimizer 역할 구분은 연결됐다. R1/R2의 진단 대상 누락은 남는다.
- **구조·출처:** native 도메인 검사 본체는 examples에 있고 코어는 `native_selection.py:80–82`의 thin 연결을 사용한다. 새 framework/daemon이나 상용 EDA 어댑터 추가 없음. ACE/CVDP/first-party pin 변경 없음. 네이티브 OS sandbox 또는 임의 plugin thread 격리로 해석하지 않는다.
- **환경 복구:** `model_input.py:64–82`의 RLock 직렬화·중첩/예외 finally 복구와 `20–23`의 원래 ambient snapshot을 확인했다. TUI의 실행 환경 생성은 `tui.py:1344–1348`에서 snapshot을 쓰고 worker 경계는 `1432,1488,1656`에서 context를 사용한다. 보호 범위는 이 context를 사용하는 프로세스 내 worker다.
- **개발 명령:** `scripts/dev.py:31–56`의 명시 기존 venv·버전/identity 검사, checkout src 사용, install/sync 없는 test/lint/demo를 확인했다. `dev_doctor.py:48–84`와 bootstrap의 override도 연결됐다. setup 설치 대상 및 옵션 없는 ACE 전체 의미를 바꾸지 않았다.
- **배포·lock:** `pyproject.toml:23–37`의 data-files가 `registry.py:41–47`의 전체 NATIVE_DEPENDENCIES와 adapter를 원래 하위구조로 포함한다. `native_selection.py:19–26`은 각 파일의 distribution metadata 선언까지 확인한다. 지정 diff의 `uv.lock` 변경은 PyYAML 6.0.2 native extra 추가이며 무관한 기존 패키지 버전 업그레이드가 없다. core Python>=3.11 유지.
- **서버:** `cli.py:49–52`의 인용 retry에 html/no-open/port 보존, `report_view.py:51–69`의 code/errno 보존 및 browser 실패와 run 상태 분리를 확인했다. R3의 redaction 경계 보완이 필요하다.
- **실행 상태의 진실성:** G 보고서는 합성·mock·실제 wheel/HTTP와 native/모델/EDA/Ubuntu/SSH/browser `not_run`을 구분한다. 보존 native JSON도 `ready=false`로 yaml/Docker/image/model 누락을 남긴다. 이 리뷰는 native 성공·OS sandbox를 주장하지 않는다.

## 최종 verdict

- **코드:** Important R1–R3 수정 후 재리뷰 필요. 기존 전체 suite 녹색 기록만으로 profile 선택·outer evaluator 설정·retry redaction 결함을 승인할 수 없다.
- **요구사항:** 기본 연결·배포·환경 복구·검증 상태 표기는 충족했으나, native 진단 대상 완전성 및 실행 가능한 retry 보존은 미충족이다. 82건 교체는 대체로 정당하며 R4의 read-only assertion 경계를 복원해야 한다.
- 후속 검증은 위 결함을 직접 겨냥한 covering으로 제한할 수 있다. 이 리뷰 과정에서는 기존 테스트 재실행·제품 변경·커밋을 수행하지 않았다.
