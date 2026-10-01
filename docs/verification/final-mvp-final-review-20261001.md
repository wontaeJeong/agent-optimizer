# 최종 MVP — 전체 브랜치 및 I 독립 리뷰

검토일: 2026-10-01. 대상 HEAD: **`cb7fbdf`**. 전체 기준: **`edbd2b8 → cb7fbdf`**. I 기준: **`51b905d → cb7fbdf`**, 제품 수정 SHA `17d3501` 이후는 검증 문서 변경이다.

## 1. 최종 판정

| 대상 | 명세 준수 판정 | 코드 품질 판정 | 발견 수 |
|---|---|---|---|
| I task | **조건부 적합 — 경미한 안내·수용증거 보완 필요.** 일반 prepare·native subdir 수정과 테스트 환경 격리는 타당하다. R16의 live `not_run`/부분 판정은 지시가 허용한 정확한 상태다. | **제품 수정 승인, 경미 보완 권고.** I 제품 patch에 새 Critical/Important 결함을 확인하지 않았다. | Critical 0 / Important 0 / Minor 2 |
| 전체 브랜치 | **조건부 적합 — R14의 무변경 판정 범위를 보완하고 R16 부분을 유지.** 아래 대조 범위에서 나머지 연결 계약을 수용한다. | **승인, 경미 보완 권고.** 새 차단급 결함을 확인하지 않았다. 두 Minor는 통합 전후 안내·검증 정확도를 높이는 후속 사항이다. | Critical 0 / Important 0 / Minor 2 |

위 두 행은 **같은 두 finding**을 서로 다른 검토 범위에서 평가한 것이며 총 4건이라는 뜻이 아니다. M1은 I 신규 문서, M2는 기존 `plan` 경로의 잔존 부작용과 I의 검증 조건에 관한 발견이다. 승인 표현은 코드 리뷰 판정이며 병합·live 실행 승인이 아니다.

I의 기존 **1157개 중 1077 실행 통과·80 skip** 기록은 보존된 로그로 확인했다. 이번 리뷰에서 전체 suite·lint·wheel·사이트·HTTP 검증을 다시 수행했다고 주장하지 않는다.

## 2. 범위·기준·방법

- 작업 디렉터리: `/Users/wt.jeong/workspace/agent-optimizer/.worktrees/final-mvp-20261001`.
- binding 기준: 지시 세트 `02_REQUIREMENTS_MATRIX.md`, `03_SHARED_CONTRACTS.md`, `prompts/I_FINAL_ACCEPTANCE.md`, 현재 checkout의 `AGENTS.md`.
- 지정 전체 diff `final-mvp-final-review.diff`와 I diff `final-mvp-review-i.diff`, 현재 Git의 동일 범위 diff·소스·관련 테스트를 대조했다. 전체 Git diff는 121개 파일, 11788행 추가·899행 삭제다.
- `final-mvp-progress-20261001.md`, I 보고서, A~H의 최초 리뷰와 최신 수정 절을 읽고 수정된 실제 소비 경로를 다시 확인했다. 기존 승인 인계를 현재 구현의 정답으로 가정하지 않았다.
- **상대 `AGENT_OPT_HOME` 거부와 A~E 병렬 결정은 확정 판정으로 소비했다.** P0의 상대 Home 허용 제안이나 스킬의 순차 구현 기본값으로 재논쟁하지 않았다.
- 저장소에 `.codegraph/`가 없어 인덱싱하지 않았다. 검토는 정적 소스·diff·계약 교차 대조가 중심이며, 아래 두 좁은 메모리 probe만 추가했다.
- 하위 에이전트·제품/테스트 수정·커밋·push·PR·설치·다운로드·모델/EDA 실행 없음. **유일한 저장소 변경은 이 문서다.** 기존 기본 저장소 `main`의 `.gitignore` 변경·ZIP과 다른 워크트리는 보존한다.

## 3. 발견 사항

### M1 — Minor · I의 “검증된 새 사용법” fixture 명령에 필수 `--name`이 없다

**위치:** `docs/verification/final-mvp-i-20261001.md:157–170`, 특히 **159행**.
실제 거부 경로: `src/agent_optimizer/cli.py:426–436`, 특히 **435–436행**.

보고서는 다음을 source에서 실제 검증한 API-free 사용법으로 안내한다.

```bash
agent-opt init --agent-preset rtl-solo --harness-profile fixture --optimizer baseline --dataset sample_text --yes
```

현재 CLI의 fixture 프리셋 분기는 `--name`을 반드시 요구한다. 이 명령을 그대로 복사하면 설정이 생성되지 않고 **종료 2, stdout 빈 값, stderr `error: 프리셋 설정에는 --name이 필요합니다`**가 반환된다. 따라서 뒤의 `prepare CONFIG`부터 여정을 이어갈 수 없다.

이번 리뷰에서 실제 `cli.main`으로 해당 argv를 호출해 위 결과를 확인했다. 프리셋 준비 전에 실패하므로 config/run 생성이나 모델 호출은 없었다. I의 저장된 CLI 여정은 custom fixture에 `--name i-acceptance`를 전달하고, source TUI는 writer의 기본 이름을 소비한다. 그 성공 증거가 이 **이름 없는 CLI 프리셋 argv**의 성공을 증명하지는 않는다.

**근거:** I brief의 실제 새 사용법·실제 명령 기록 요구 및 R27/R30. 제품 프리셋의 이름 계약을 바꾸라는 요청이 아니다.

**최소 보완:** 보고서 명령에 `--name my-fixture` 같은 유효 이름을 넣고, 실제 CLI argv와 TUI 선택 증거를 구분한다. 기존 완료 run/테스트 결과를 취소할 필요는 없다.

### M2 — Minor · `plan`의 bytecode 쓰기를 I의 `-B` 검증 조건이 가린다

**제품 위치:** `src/agent_optimizer/cli.py:82–84`, **734–735, 752–755행**.
쓰기 원인: `src/agent_optimizer/registry.py:173–180`의 `SourceFileLoader.exec_module`.
**I 판정 위치:** `docs/verification/final-mvp-i-20261001.md:60,68–70,134`, 특히 **70행**의 doctor/plan 무변경 근거.

`main`은 `doctor`·`catalog`에만 `sys.dont_write_bytecode=True`를 적용한다. `plan`은 `preflight`를 통해 신뢰한 file plugin을 import하며, bytecode가 없는 정상 writable 프로젝트에서는 Python loader가 **원본 plugin 옆 `__pycache__/*.pyc`**를 생성할 수 있다. plugin 본체가 아무 파일도 쓰지 않아도 발생한다.

I의 실제 acceptance helper는 source prefix를 `[python, '-B', '-m', 'agent_optimizer']`, wheel prefix를 `[python, '-I', '-B', '-m', 'agent_optimizer']`로 만든다(`$I/acceptance.py:91–95`). 이 조건의 snapshot 불변 검증은 타당하지만, 일반 사용자 명령 **`agent-opt plan CONFIG`가 자체적으로 무변경을 보장한다**는 증거로 확대할 수 없다.

이번 리뷰는 실제 파일 쓰기 대신 `SourceFileLoader.set_data`를 메모리 callback으로 가로채고 `.pyc` cache miss를 강제했다. `cli.main(['plan', 'examples/minimal/experiment.toml'])`은 종료 0/정상 JSON을 반환하면서 다음 쓰기를 시도했다.

```text
examples/minimal/__pycache__/evaluator.cpython-312.pyc
examples/ace-rtl/__pycache__/native_adapter.cpython-312.pyc
examples/ace-rtl/__pycache__/native_evaluator.cpython-312.pyc
experiments/sample-team/__pycache__/provider.cpython-312.pyc
```

전체 관측은 프로젝트·venv의 13개 bytecode 대상이었다. **대상 경로만 관측했고 파일/디렉터리는 실제로 생성하지 않았다.** 이것은 cache miss 조건의 import 쓰기 시도 확인이며, 모델·Agent·평가기 실행이나 실제 디스크 변경 재현이 아니다.

**영향·심각도:** 계획 조회가 원본 프로젝트에 generated cache를 남기는 경미한 읽기 전용 계약 결함이다. 실험 설정·점수·private 자료·후보 선택을 바꾸지는 않는다. 새 I patch가 도입한 회귀로 분류하지 않는다.

**근거:** R14와 공통 계약의 정적 plan 불필요한 mkdir 방지, I brief의 read-only doctor/plan 검증. `plan`이 신뢰한 Python plugin을 로딩한다는 기존 계약 자체는 유지한다.

**최소 보완:** `plan`의 plugin import 구간에도 bytecode 억제를 적용하고, source-only 임시 plugin을 사용해 `-B`/`PYTHONDONTWRITEBYTECODE` 없이 보호 경계를 검증한다. 그 전까지 I의 R14 “완료”는 **검증 환경의 무변경 확인**으로 한정하고, 사용자 기본 환경의 무변경은 경미 보완 대상으로 남긴다. doctor의 별도 `_no_bytecode()`·모델 probe 명시성·JSON/exit 계약까지 반려하는 finding은 아니다.

## 4. I 변경 자체의 평가

| 변경 | 독립 대조 결과 |
|---|---|
| 일반 `prepare` 오분기 수정 | `integrations.py:294–321`은 integration/native/preset을 구분한 뒤 일반 실험에 기존 `load_experiment`·`preflight`를 적용한다. Registry의 파일·adapter·optimizer·evaluator 검증을 재사용하고 `scope=preflight`, `live=not_run`을 반환한다. 실행·자동 fallback·새 추상 계층을 추가하지 않았다. 준비 안내는 전체 환경 ready를 주장하지 않는다. |
| native `source.subdir` | `integrations.py:302–306`은 실제 선택 pair의 `safe_path(agent.source.path, agent.source.subdir)`를 readiness에 전달한다. `sources.py`의 materialization 및 native doctor의 동일 active root 해석과 일치한다. sibling source로 대체하지 않는다. |
| 일반 prepare 회귀 | `tests/test_final_acceptance.py:47–75`는 실제 generated fixture의 prepare JSON·Home snapshot·획득/모델 호출 금지·미구현 adapter 거부를 검증한다. 정상 schema만으로 성공시키지 않는다. |
| subdir 회귀 | 같은 파일 `:16–45`는 실제 nested source를 구성하고 로더의 subdir·성공을 확인한 뒤 **active cli.py를 변조해 종료 2**를 요구한다. pin 검사를 약화한 테스트가 아니다. interpreter readiness만 명시 mock이다. |
| make 테스트 환경 격리 | `tests/test_dev_onboarding.py:713–721`, `tests/test_menu.py:451–453`에서 default/PATH fixture에 상속된 `AGENT_OPT_CORE_PYTHON`만 제거한다. 기존 exit/argv/설치 금지 assertion을 보존한다. override의 별도 `test_g_integration.py:14–23`와 실제 make 실행 증거가 있어 제품 override를 삭제하거나 실패를 skip으로 감춘 변경이 아니다. |
| 보고서·handoff | 시작/제품 수정/후속 문서 SHA와 fixture/mock/live·실행 명령·경로·skip 사유를 구분한다. R16 live 부분은 정확하다. M1/M2의 표현·검증 조건만 보완하면 된다. |

## 5. 전체 핵심 계약 교차 검토

아래 “수용”은 **현재 정적 연결과 저장된 검증 범위**의 판정이다. live·모든 OS·모든 사용자 plugin의 실행 성공을 뜻하지 않는다.

| 요구 | 대조 경로·판정 |
|---|---|
| R01–R02 범용·flat core/MVP | `contracts.py`·`registry.py`의 기존 공통 계약을 유지한다. `src/agent_optimizer/native_selection.py:10–93`은 workspace/source/wheel 출처 해석·예제 helper 인자 전달이고, CID/row/private/active surface 정책은 `examples/ace-rtl/native_selection.py` 소유다. 새 DB/daemon/framework·단일 run scheduler·resume 추가 없음. 수용. |
| R03–R09 CLI/TUI·선택·모델 | Typer/Textual과 공통 writer/runner 연결을 유지한다. `ChoiceRow.id/kind`, unique Option ID, disabled Planned와 reason, native/fixture/legacy 분기를 확인했다. `ModelInput.validate_value`는 reactive 저장 전에 credential URL을 제거하며 Endpoint/ID 평문·key-only masking·안전 repr를 보존한다. bare/custom model_env의 유도·충돌 검사는 표시와 실행이 같은 값을 소비한다. native는 공통 API transport 세 역할이며 compatible prefix를 강제하지 않는다. named preset은 명시 공급 API만 소비하고 후보 없는 환경에서 값을 추측하지 않는다. 수용. |
| R10·R13 Home/output/legacy | `app_paths.py:15–52`는 pure resolver·절대 override 거부·CLI output > 명시 TOML > Home 기본을 유지한다. explicit output은 기존 부모 의미, 상대 CLI는 CWD, 상대 TOML은 project_root다. `config_root` 없는 옛 TOML·명시 legacy 조회를 보존하고 자동 migration 없음. 수용. |
| R11 원본 provenance | `config.py:195–211,254`, generic/preset/native writer의 절대 project/source provenance와 config_root·seed_root를 대조했다. plugin은 원본 project, 생성 manifest/tasks는 config root, local source는 manifest 기준이며 source/wheel 다른 CWD 증거와 일치한다. 수용. |
| R12 이력/lifecycle | `history.py:125–257,306–349`는 실제 run/session 종류·session summary 구조·terminal event 보완·stale/unknown·reportless를 구분한다. Home/project/explicit 부모의 실제 child만 조회하고 canonical 중복 제거·FD no-follow·재검증을 사용한다. `runner.py:467–468,548–549`, `session.py` lifecycle/worker 정리와 연결된다. 수용. |
| R14 JSON/exit/read-only | 단일 JSON·상태 stderr·nonTTY no-hang·충돌 옵션 사전 거부 및 doctor 정적/명시 model probe 분리는 수용한다. **일반 `plan` bytecode 무변경은 M2 때문에 부분/경미 보완**이다. |
| R15·R28 진단/개발/offline | native의 실제 selected pair마다 source/subdir/interpreter와 inner evaluator를 검사하고 실제 outer `evaluator_settings(spec)`를 별도로 진단한다. `redact_guidance`/`safe_retry`가 공개 모델 ID와 credential을 구분하고 retry argv/flag·errno를 보존한다. 개발 override는 기존 venv를 사용하며 test/lint/demo에 install/sync를 추가하지 않는다. offline miss/pin/hash·CA/proxy 보호 테스트의 의미가 유지된다. 수용. |
| R16 native 기본 실제 데모 | catalog/preset/native worker의 실행 배선은 있고 기존 coding launcher로 우회하지 않는다. **실모델·공식 Docker/EDA native 실행은 `not_run`/부분 유지**. 이는 I 지시가 명시 허용한 상태이며 이번 리뷰의 차단급 finding으로 세지 않는다. |
| R17 legacy 프로필 | OpenCode/Claude Code의 기존 profile/ID/argv와 legacy full setup/smoke/live 경로를 보존한다. native 이름으로 과거 성공을 재표현하지 않는다. 새 preset에서 비호환 프로필은 기존 설정 action으로 안내한다. 수용. |
| R18·R20 실제 후보 표면·역할 모델 | `native_bridge.py:57–84,157–176,260–262`는 후보 guidance를 읽고 후보 orchestration을 compile/exec한 뒤 실제 pinned `cli.run_attempt`를 호출한다. CandidateStore A/B 검증은 generator request 변경·실제 Python 실행·hash·editable 밖 수정 거부를 확인한다. iteration 12 coordinator→13 fresh-start의 upstream 경로와 공통 ModelSettings transport를 대조했다. 단순 파일 hash나 OpenCode fixture로 대신하지 않는다. 수용. |
| R19 CID·row | 고정 HF hash, 공개 input/context·모든 output target, CID002/004/007/016의 지원/제외 사유와 single/multi/nested 파일 계약을 확인했다. 197 eligible/27 제외는 정적 eligibility이며 정답률·전체 CVDP 지원이 아니다. 수용. |
| R21 snapshot/private/test | public row에서 harness/golden output을 제거하고 pinned private task/descriptor를 실행 전에 재대조한다. bridge의 reflector/coordinator context·evaluator feedback은 safe binary 집계로 제한한다. inner와 outer는 trusted 공식 평가이고 Agent pass flag를 최종 성적으로 사용하지 않는다. 기존 stage-local train/validation 수치 선택·frozen selection 뒤 test 계약과 CandidateStore editable/hash를 보존한다. trusted local Python을 OS sandbox라고 주장하지 않는다. 수용. |
| R22–R24 보고서·usage·시각화 | runner의 optional sidecar→`summarize_native` whitelist→`build_report`→JSON/MD/HTML 정본 흐름을 확인했다. 큰 정수/비유한·malformed identity/path는 optional 자료에 제한하고 outer result/event를 보존한다. requests unique ID·partial/unreported/null, wall time과 요청 duration·outer 평가 계측을 구분한다. validation baseline 적격성은 split/group/valid를 공통 검사하고 단계별 leader가 baseline에서 재시작한다. unknown·branch/multi-parent·실제 pass_number·escaping·inline CSS/SVG·상한+원본 안내를 확인했다. 수용. |
| R25–R26 서버·수명·보안 | `report_server.py:24–92,156–175,194–250`은 HTML 한 파일만 메모리에 승인하고 loopback/raw target/Host/no-follow/일반 파일·hardlink/inode 재검증을 적용한다. arbitrary run root·private/log/JSON/MD·dir listing을 공개하지 않는다. import 시 bind 없음, 느린 client shutdown·idempotent close·port conflict를 처리한다. CLI finally close와 TUI epoch/lock/unmount 회수·browser timeout/URL 대안이 연결된다. 수용. |
| R27 현재 문서·사이트 | H 수정 후 native init/prepare/doctor/--model의 책임, App Home/provenance/legacy·HTML-only/SSH·source/wheel 범위가 현재 구현과 일치한다. 기존 pin을 갱신하지 않고 과거 검증을 보존한다. **I 사용법 한 줄은 M1**. 사이트 build/link 결과는 기존 증거로만 소비했다. |
| R29–R30 통합검증·handoff | 실제 fresh source/wheel CLI/PTy·source/wheel TUI·Home run/history·HTTP/종료·custom local/pinned Git·make/site 증거를 보고서와 저장 argv/helper/log에 대조했다. 이번 리뷰에서 재실행한 성공으로 확대하지 않는다. M1/M2 외 새 Important 누락을 확인하지 않았다. |

## 6. 이전 리뷰/fix의 독립 재대조

| 선행 | 현재 코드에서 확인한 수정 |
|---|---|
| A I1–I3/M1 | explicit/legacy session kind 추론·child 조회, running+terminal event 보완, 손상 session 구조 거부, 실제 CWD/상대 output 회귀가 존재한다. 최초 리뷰의 세 Important 경로가 현재 코드에서 해소돼 있다. |
| B B01–B05 | 누락 manifest 조건부 append·ID 중복 제거, URL reactive/draft/repr 안전화, bare selector 표시/실행 일치, 사용자 model_env 충돌 검증, Workspace component 선택 보존을 확인했다. |
| C I1/I2/M1/M2 | worker/adapter 모든 종료의 `finalize` journal 병합, input/output 양쪽 usage 판정, 시작부터 nullable provenance/readiness sidecar, 하나의 outer cleanup deadline·완료 marker skip·deferred/incomplete 기록을 확인했다. 실제 Docker cleanup 성공으로 해석하지 않았다. |
| D I1/I2/M1 | NUL·배열 identity·경로 오류 격리, validation baseline 공통 적격성, Markdown pass_number 열을 현재 코드와 covering으로 확인했다. |
| E | HTML-only/raw allowlist·path swap·FD·socket/thread 정리를 현재 연결에서 확인했다. 기존 E 검증을 현재 live 성공으로 확대하지 않았다. |
| F R1–R4·workspace 추가 수정 | native 변경의 공통 무효화·새 writer 소비, optional 숫자 오류의 outer 기록 보존, examples 소유 정책/코어 thin 연결, 실제 Review split/final_test, 명시 workspace의 선택 검증·budget 출처를 확인했다. |
| G R1–R4 | 실제 selected native pair·독립 inner/outer constructor/probe, 공개 guidance와 credential redaction·executable retry 분리, project+Home/cache snapshot 보호 복원을 확인했다. |
| H R1 | 모델/driver/독립 inner 환경 전체가 prepare에서 반드시 실패한다는 문구를 현재 안내에서 제거하고 네 명령 책임을 구분했다. I source.subdir 보완도 이 책임 범위를 확대하지 않는다. |

## 7. 테스트 변경의 적법성·증거 수준

- `sys.executable`/module entrypoint로 워크트리 interpreter hardcode를 제거한 변경, stdout의 실제 UUID config 경로 사용, stable ID 선택, native-first와 명시 `ace-opencode` 분리, `_seed_root`·Home/cache 기준 전환은 최신 계약에 맞는다.
- Endpoint의 `password=True` 옛 assertion을 정상 URL 평문·credential 즉시 삭제·sentinel 부재로 바꾼 것은 보호 제거가 아니다. 별도 실제 partial typing/draft/repr/SVG 회귀가 남아 있다.
- TMPDIR의 `opencode` substring 전체 대신 실제 executable/Dockerfile 인수를 검사한 변경은 경로 오탐을 제거하며 Agent image 준비 금지·offline clone/build 금지는 유지한다.
- 손상 sidecar·private descriptor·active source 변조·symlink/FIFO/path swap·미구현 adapter 거부·frozen selection·stage 독립성의 실질적인 assertion을 확인했다. 기존 실패를 일반 skip/xfail/합성 성공으로 바꾼 변경은 확인하지 않았다.
- G의 dataset read-only snapshot은 project와 Home/cache 양쪽 mode/inode/mtime/bytes·미생성 상태를 다시 포함한다. I의 interpreter 환경 제거도 별도 override 회귀와 함께 타당하다.
- **별개로 M2는 I 도구의 `-B` 조건 때문에 사용자 기본 환경의 plan bytecode 부작용을 관측할 수 없다는 검증 공백이다.** 다른 보호 assertion이 모두 약화됐다는 뜻은 아니다.

### 직접 확인한 기존 증거

`$I=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-i`.

- `$I/make-test-verified.log:1570,1572`: `Ran 1157 tests in 171.268s`, `OK (skipped=80)`를 직접 확인했다. 이는 **I의 기존 수행 로그**다.
- `$I/commands.json`의 source/wheel 실제 argv/CWD/exit 및 `$I/acceptance.py`의 JSON decoder·snapshot·run/status/parity·다른 CWD history·HTTP·port conflict·SIGINT/socket 검사를 읽었다.
- I 보고서의 wheel install/site build/시각화·8개 캡처·native pinned upstream/row 계약 및 skip 80개의 범위는 그 보고서의 기존 결과로 인용한다. 모든 원시 산출물을 독립 재실행·재채점하지 않았다.
- 실제 native/API/Docker·EDA/cleanup·Ubuntu x86_64·OS browser/SSH는 **이번에도 `not_run`**이다. R16을 성공으로 승격하거나 과거 legacy 결과를 대신 쓰지 않았다.

### 이번 신규 확인

공유 Python `/Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python`을 실행만 사용했다. CWD는 지정 worktree, `env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1`, 고유 절대 `AGENT_OPT_HOME=$TMP/final-mvp-final-review-home`이었다(`$TMP`는 위 승인된 `/T/opencode`).

1. M1 argv를 `cli.main`에 전달하고 stdout/stderr를 메모리에 캡처: 반환 **2**, stdout `""`, 필수 name 오류. 파일 생성 전 분기다.
2. M2 probe: `-B`로 검토 코드를 로딩한 뒤 해당 호출 구간만 `sys.dont_write_bytecode=False`, `SourceFileLoader.get_data`의 `.pyc` cache miss와 `set_data`의 메모리 기록을 patch. 실제 `main(['plan','examples/minimal/experiment.toml'])` 반환 **0**, JSON 출력 2032자, bytecode 쓰기 대상 **13개** 관측. `set_data`는 디스크에 쓰지 않았다. 실제 모델/evaluator를 mock 성공으로 바꾼 검사가 아니다.

전체 테스트/사이트/wheel/HTTP의 불필요한 재실행 없이 두 경미 사항의 정확한 실패·부작용 경계를 확인했다.

## 8. 최종 인계

- **필수 차단 수정: 없음(Critical/Important 0).** 경미 보완은 I 안내의 필수 name와 plan bytecode 억제/사용자 기본 환경 covering이다.
- I의 제품 결함 두 건 수정·기존 전체 테스트 결과는 수용한다. I가 적은 “29 완료·1 부분”을 무조건적인 제품 전체 무변경/실환경 완료 승인으로 재사용하지 않는다. 이 리뷰에서는 **R14의 경미 보완과 R16 live 부분**을 명시적으로 남긴다.
- 상대 Home 정책·A~E 병렬 결정·MVP 경계·고정 SHA·private/evaluator·기존 legacy 의미를 변경하라는 요구는 없다.
- 제품/테스트·기존 검증 보고서를 수정하지 않았다. 후속 담당자는 M1/M2만 좁게 처리하고 기존 검증의 fixture/mock/live 구분을 유지하면 된다.
