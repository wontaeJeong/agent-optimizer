# 최종 MVP F 독립 코드 리뷰

확인일: 2026-10-01. 기준 HEAD: `0a9fe84`, F 시작점: `ff0d6dc`.
요구: `agent-optimizer-final-prompts-20261001/prompts/F_PRODUCT_WIRING.md` 및 P0 공통 계약.
지정 `final-mvp-review-f.diff`, 현재 소스·전용/공유 테스트·F 검증 보고서·전체 실패 원본 로그를 대조했다. 하위에이전트·제품 수정·커밋·모델/다운로드/브라우저 실행 없이 본 보고서만 추가했다.

## 판정

- **명세 준수: 수정 필요.** native 선택 재설정이 실제 설정에 반영되지 않으며, CVDP 도메인 정책이 코어에 들어왔다.
- **코드 품질: 수정 필요.** optional sidecar의 숫자 하나가 최종 trial 기록을 중단할 수 있다.
- **Critical 0 / Important 3 / Minor 1.** G의 native 준비·배포 미완료와 아래 F 구현 결함은 별개다.

## Findings

### Important F-R1 — 준비 후 native 선택을 바꿔도 이전 TOML을 재사용

- 위치: `src/agent_optimizer/tui.py:922-927`, `1050-1063`, `1405-1415`.
- 원인: row/split·source·dataset·evaluator 변경은 `native_values`만 갱신한다. `_preparation_succeeded`가 저장한 `self.experiment`를 무효화하지 않아 다음 `prepare_work`는 native writer 대신 기존 experiment 분기를 선택한다. 일반 구성 선택 변경의 `850-857`에는 무효화가 있지만 native에는 없다.
- 사용자 경로: native 준비 성공 → Review/Model/Native로 돌아가기 → row의 split 또는 source 변경 → 재확인/준비. 실제 실행은 변경 전 source/tasks/splits를 사용한다. 특히 test/train 경계 변경을 적용했다고 생각하고 이전 과제를 실행할 수 있다.
- 독립 메모리 재현: 기존 `/virtual/old/experiment.toml`과 `rows={old:validation}` 상태에서 실제 `on_input_submitted`로 `{new:validation}` 제출 후 실제 worker 본체를 호출했다. 결과는 `new_rows={'new':'validation'}, writer_calls=0, prepared='/virtual/old/experiment.toml'`이었다. 쓰기/API 경계는 mock이며 파일 생성은 없었다.
- 필요 수정: native 선택 변경 시 생성 설정·진단을 무효화하고 재생성하거나 명시적 선택 fingerprint를 대조한다. 직접 JSON 입력과 NativeRows/NativeSplit 모두 같은 처리·회귀 검증이 필요하다.

### Important F-R2 — 손상된 optional sidecar가 trial 결과 기록을 막음

- 위치: `src/agent_optimizer/native_summary.py:40-41`, `109-110`; 소비: `src/agent_optimizer/runner.py:269-294`.
- 원인: `math.isfinite`는 큰 Python 정수를 float로 변환할 때 `OverflowError`를 낸다. JSON은 `10**400` 같은 정수를 정상 파싱하며 1 MiB 제한도 통과한다. 이 예외는 요약 함수의 catch 목록에 없다.
- 독립 메모리 재현: `schema_version=1`, `execution_mode='native'`, `native_wall_time_seconds=10**400`인 JSON을 일반 파일 읽기 경계에 공급하면 `OverflowError: int too large to convert to float`가 발생한다. 정상적인 숫자 필드만 바꾼 재현이며 파일·모델을 실행하지 않았다.
- 영향: 호출이 `GroupRunner.trial`의 `finally` 내부에서 `write_json(result.json)`/`trial_completed` 이전에 있으므로 이미 완료한 outer 평가 기록도 유실되고 실행 오류로 전파된다. F 보고서 `79`행의 “손상 요약은 optional만 제외” 계약과 다르다. token/cost/duration도 같은 경로다.
- 필요 수정: 정수/실수 범위를 안전하게 검사하고 숫자 변환 오류를 optional 요약 거부 또는 null 처리로 제한한다. 큰 정수 sidecar에서도 outer result/event가 남는 검증이 필요하다.

### Important F-R3 — CVDP row·private 평가 구성 정책이 범용 코어에 위치

- 위치: `src/agent_optimizer/native_selection.py:18`, `52-62`, `85-106`, `109-133`, `167-173`; 직접 결합: `src/agent_optimizer/runner.py:398-400`.
- 근거: 새 코어 모듈이 네 CID를 직접 제한하고, CVDP categories로 과제를 필터링하며, private `row`와 public `output/context`를 조합한 `expected_evaluation` 및 `native-task.json`의 정확한 형식을 직접 재구성한다. native editable 파일·symbol도 코어가 정한다. 단순 registry ID→예제 구현 등록이나 CLI/TUI 선택 전달을 넘어선 도메인 처리다.
- 명세: F brief `6`행 및 저장소 AGENTS.md는 RTL/CVDP 특화 로직을 examples에 두도록 요구한다. “알고리즘은 예제 소유”라는 모듈 설명만으로 이 경계 위반이 해소되지 않는다. private 대조 자체는 필요하며 이번 리뷰에서 이 대조를 통한 실제 golden 누출을 확인한 것은 아니다.
- 필요 수정: CVDP eligibility·public/private 검증 및 활성 표면 정책을 `examples/ace-rtl/`의 기존 helper 소유로 옮기고 코어는 그 결과를 연결한다. 새 범용 provider 계층을 만드는 방식은 필요하지 않다. F 소유 신규 모듈의 결함이며 wheel/pin/readiness를 정리하는 G 작업으로만 해결되지 않는다.

### Minor F-R4 — native Review에 legacy split·final_test 설명이 남음

- 위치: `src/agent_optimizer/tui.py:1187-1193`, `1194-1206`; 동일 설명: `src/agent_optimizer/preset_tui.py:115-120`.
- 근거: native도 먼저 `cvdp · train 1 / validation 1 · final_test=false`를 Review에 추가한 뒤 실제 row 목록만 덧붙인다. 실제 writer는 선택 row의 split을 그대로 쓰고 test가 있으면 `final_test=true`를 생성한다(`setup_wizard.py:250-253`).
- 독립 읽기 전용 재현: native baseline의 `v1/v2=validation, t1=test` 선택에서 Review는 `rows 3`, budget `4`와 함께 위 `train 1 / validation 1 · final_test=false`를 동시에 표시했다. 확인 화면의 평가 경계 설명이 생성 설정과 모순된다.
- 필요 수정: native의 split별 수·final_test 설명을 실제 row 선택에서 계산하고 legacy 두 과제 설명은 해당 프로필에만 사용한다.

## 범위별 확인

| 범위 | 리뷰 결과 |
|---|---|
| CLI 진입·호환 | 무인자 TTY/CI/TERM 분기, 명시 tui·help·기존 명령 보존 확인. native/legacy/fixture 경로와 Planned 거부 연결 존재 |
| Home·원본 provenance | 공통 resolver, 절대 project/source와 `config_root='.'`, 기존 output 우선순위, `_seed_root` 소비·seed hash 기록 확인. recent/history/catalog 조회는 디렉터리를 만들지 않음 |
| snapshot·private/golden | 스냅샷·editable 검증 유지, native public/tasks/evaluation 재대조, legacy benchmark 바이트 대조, benchmark seed 직접 노출 거부 확인. 새 누출을 입증한 finding은 없음; R3는 정책 위치 문제 |
| 공유 생성 의미·모델 | CLI/TUI 공통 writer·native stage config/budget 연결 존재. native API 세 값과 legacy selector 구분, 키 TOML/argv 저장 방지 경로 확인. 선택 재시도와 Review 의미는 R1/R4 |
| sidecar | identity/source provenance, 일반 파일·no-follow·크기 상한, whitelist, 요청 ID 중복 제거, partial/unreported, 실제 outer 평가 계측 확인. 숫자 오류 격리는 R2 |
| 이력·HTML 열람 | dict row/inode 보존, report 없음/실패/session child·명시 output parent 연결, 열람 직전 재검증 확인 |
| serve·브라우저·종료 | `--json --serve` 등 충돌은 읽기/재생성/bind 전에 거부. stdout JSON 하나, 서버 안내 stderr. HTML-only loopback, foreground finally close, TUI worker·epoch·lock/unmount close, browser helper 5초 상한·출력 폐기·credential 제외·timeout process group 회수 확인 |

위 표는 정적 코드 검토 결과다. 이번 리뷰에서 기존 suite, 실제 서버/브라우저·모델·wheel 통합을 재실행하지 않았다.

## 기존 41 failures / 41 errors 분류 검토

원본 로그: `/Users/wt.jeong/.local/share/opencode/tool-output/tool_0f425c91a001tl0VFh2vh8j4ne`의 `397-1669`행. F 보고서의 합계와 82개 실패/오류 항목을 대조했다.

- `.venv/bin/python/agent-opt` 경로 오류 15건, 기존 `runs/configs` 경로 기대, Home 미격리, 숫자/Enter 횟수 기반 Harness 선택, native 추가 단계, dict history 기대, prepare 반환 mock 및 새 `output` keyword 미수용, XDG cache·TMPDIR substring 기대가 실제 traceback/assertion과 일치한다.
- 보안 회귀처럼 보이는 `test_symlinked_config_root_is_rejected_before_ace_preparation`은 옛 project/runs 경계를 시험한다. 새 Home 경계는 `test_product_wiring.py:218-229`가 별도로 다룬다. `test_selected_meta_rejects_tampered_seed_and_objective`의 실패는 `_seed_root` 대신 project의 다른 파일을 변조한 결과다(`test_preset_tui.py:104-106`).
- `test_history_rejects_replaced_report`는 Home 미격리 상태에서 첫 row를 선택하면서 다른 legacy report를 symlink로 바꾼다(`test_textual_tui.py:805-822`). 로그 `1436`행은 다른 선택 결과의 서버 안내이며, 이것만으로 symlink 승인 회귀라고 결론 낼 수 없다. 현재 worker는 전달받은 원래 row를 `verified_report`로 재검증한다.
- 검토한 82개 항목에서 별도의 F 실행 회귀를 입증하는 실패는 확인하지 못했다. **그러나 전체 녹색 또는 회귀 없음의 증거는 아니다.** R1/R2는 기존 assertion 갱신과 별개의 결함이며 F 전용 테스트가 다루지 않는다. G가 공유 fixture를 수정할 때 위 보호 의미를 유지해야 한다.

## G 인계와 F 결함 구분

- **G 미완료/미검증:** old first-party pin의 native 자산 부재, 실제 wheel data-files·설치 검증, native Python 선택형 의존성, readiness의 native/source/API/CVDP pin·image 검사, `_seed_root`/새 cache 기준 진단, locale 및 공유 테스트 갱신. F 보고서 `134-143`행은 이를 성공으로 표시하지 않았다.
- **loader:** F의 `config.py:218-248`에 native/compatibility additive loader는 이미 구현돼 있다. 모든 native 미실행을 “loader 미구현”으로 분류하지 않는다. 실제 준비와 wheel 출처 검증은 여전히 G/I 통합 검증 대상이다.
- B의 전역 `session_environment` 동시 worker 격리 문제는 이미 기록된 선행/G 연결 과제다. 이번 F 신규 결함으로 중복 계상하지 않았다.
- R1~R4는 native 준비가 완료되어도 남는 F 구현/표시 결함이다. 실환경 native·Ubuntu·wheel not_run 상태와 분리해서 수정·검증해야 한다.

## 이번 독립 검증

저장소에서 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -`로 두 차례 메모리 probe를 실행했다(종료 0).
첫 probe는 실제 `on_input_submitted` 및 `OptimizerApp.prepare_work.__wrapped__`를 호출하고 writer/환경/UI callback 경계만 mock하여 R1을 확인했으며, `summarize_native`의 파일 descriptor 읽기를 `StringIO`/일반 파일 fstat로 대체하여 R2를 확인했다. 두 번째 probe는 native 세 row 선택의 실제 `_review()` 문자열로 R4를 확인했다. 모두 신규 파일·실제 자산 준비·API·서버 호출 없이 수행했다.

기존 175개 통과와 전체 1121개 실패 합계는 F의 저장된 실행 증거로만 인용한다. 리뷰 완료 후 허용 파일만 추가됐는지 `git status --short --branch`, `git diff --check` 및 기본 main/worktree 연결을 확인한다.
