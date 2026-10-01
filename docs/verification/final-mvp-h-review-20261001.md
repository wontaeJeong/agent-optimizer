# H 독립 범위 리뷰 — 문서·Starlight·실행 안내

확인일: 2026-10-01. 대상 HEAD: `a0a8756cf5ff5cca9bfd41c0dd063c4fcda49dc3`.
기준: `H_DOCS_STARLIGHT_HOWTO.md`, 제공된 `final-mvp-review-h.diff`, H 검증 보고서와 실제 구현.
지정 `final-mvp-20261001` 워크트리에서 직접 검토했다. 하위 에이전트·기능코드 수정·커밋·설치·모델 호출·테스트/빌드 재실행은 수행하지 않았다.

## 판정

- **명세 적합성: 수정 필요.** native prepare의 검사 범위를 과장한 P2 1건이 남았다. 나머지 H 요구사항은 아래 대조 범위에서 충족한다.
- **코드/문서 품질: 수정 필요.** 기존 구조·Starlight·공통 계약과 일관된 문서/자산 변경이지만, 핵심 준비 안내가 구현과 다른 상태로 반복된다. 이 문구를 정정한 뒤 승인할 수 있다. H diff에 기능코드 변경은 없으며 소유 밖 구현 전체의 독립 승인으로 확장하지 않는다.
- P0/P1: 0건. P2: 1건. 추가 차단 발견 사항 없음.

## 발견 사항

### H-R1 — [P2] native `prepare --offline`이 모델 등 전체 실행 환경의 누락을 거부한다고 설명한다

**대표 위치:** `examples/ace-rtl/NATIVE.md:45`, `README.md:37`, `website/src/content/docs/getting-started/presets.md:24`.

동일 안내는 `docs/development.md:11`, `docs/status.md:11`, `docs/NEXT_STEPS.md:5`, `website/src/content/docs/developer/validation.md:46`에도 반복된다. 특히 대표 세 위치는 누락된 **interpreter/driver/image/모델 환경**을 prepare가 명시 오류로 끝낸다고 적는다.

**실제 구현 근거:**

- `src/agent_optimizer/integrations.py:298-314`의 native prepare는 선택 데이터/descriptor 검증 → native source/interpreter readiness → **outer evaluator**의 `validate_benchmark`만 호출한 뒤 `ready=True`를 반환한다. 모델 설정 검사나 전체 doctor 호출이 없다. native 분기에서 `offline`은 추가 검사를 활성화하지 않는다.
- `examples/ace-rtl/native_prepare.py:80-91`의 readiness는 source pin/asset/lock과 native Python 3.12·yaml·pydantic_settings만 검사한다.
- `examples/ace-rtl/native_evaluator.py:25-31` 및 `examples/ace-rtl/evaluator.py:43-63`의 benchmark 검사는 outer repo entrypoint/driver 파일과, **identity가 선언된 경우** image inspect 및 task 형태를 검사한다. driver 패키지 import·모델 URL/ID/key·독립 inner evaluator 환경 전체를 확인하지 않는다.
- 전체 준비 진단은 `examples/ace-rtl/native_selection.py:78-126`의 pair별 source/inner·outer driver/image 검사와 `src/agent_optimizer/readiness.py:604-632`의 모델 설정 검사에서 수행한다. 실제 연결은 별도 `--model` probe(`readiness.py:633-641`)다.

**영향:** native source/interpreter와 outer benchmark 검사만 통과하면 Agent 모델 환경이 없어도 prepare는 성공할 수 있다. 사용자는 prepare 실패/성공이 모든 필수 환경의 누락을 검증한다고 오해하고, 명령별 실패 원인과 준비 완료의 의미를 잘못 해석할 수 있다. 가이드에 다음 doctor가 있어 실행을 곧바로 성공으로 주장하는 문제는 아니지만, H의 실제 동작 대조 요구에는 어긋난다.

**요청:** 문서에서 native init의 로컬 export/선택 검증, prepare의 제한된 검증, `doctor --plan`의 전체 정적 준비 진단, `--model`의 실제 API probe를 구분한다. “누락 환경을 자동 설치/온라인 보완하지 않는다”는 설명은 유지하되, **모든 모델/driver/inner 환경 누락이 prepare에서 반드시 실패한다**는 표현은 제거한다. G/H의 여러 미준비 조건이 함께 있던 종료 2 사례를 각 조건의 독립 prepare 검증 증거로 일반화하지 않는다. 기능코드 변경 요구는 아니다.

## 요구사항·구현 대조

| 검토 항목 | 근거와 판단 |
|---|---|
| README 진입 순서·fixture | 목적→fixture→TUI/CLI→native 조건→내 Agent→Home/History/report→개발 링크 순서를 확인했다. 기존 minimal의 명시 `output_dir="runs"`와 새 init UUID를 구분한다. H §2 및 기존 `minimal-run.stdout`에서 completed·7 trial·실제 output 부모를 확인했다. 합성 표시를 native 성공으로 바꾸지 않는다. |
| 실제 CLI/help·명령 | `cli.py:166-331,392-425,734-776`와 H의 저장된 init/report help를 대조했다. native flags, 반복 CID·rows JSON, output, doctor model, report serve/no-open/port/json/csv는 존재한다. 별도 serve 명령을 안내하지 않는다. placeholder CONFIG/RUN·경로/image 값은 실제 출력으로 교체하도록 명시한다. |
| native/legacy·API·표면 | NATIVE의 adapter/profile/evaluator와 `native_selection.py:187-225,289-392`의 생성 정책이 맞는다. `prepare_source`, `prepare_dataset`, `readiness` API는 `native_prepare.py:27-127`과 맞는다. GEPA guidance·Meta orchestration은 `native_bridge.py:57-83`에서 실제 소비한다. legacy setup/smoke/live와 native를 분리한다. 단, prepare 범위는 H-R1 정정 필요다. |
| App Home·provenance·output·migration | `app_paths.py:12-52`, `config.py:195-211,254`, CLI 생성 경로와 `native_selection.py:367-387`을 대조했다. 절대 Home override·6개 하위 경계·UUID·config/project/local source 기준·CLI>TOML>Home 부모 의미가 맞는다. `history.py:306-329`의 Home/legacy/explicit 부모 조회와 문서가 맞고 자동 migration을 약속하지 않는다. |
| TUI 상태·모델 입력 | `tui.py`의 Native/Rows/Split·Review/Preparing/Doctor 흐름과 `:503-638`의 secret 판정·환경/세션/기본/preset/Custom을 대조했다. Endpoint/ID 평문과 key masking, 명시 제공 preset만 소비하는 설명이 맞는다. highlight·준비·실행 action을 구분한다. |
| CID 실제 지원 | NATIVE `:66-75`·사이트 presets `:76-85`는 C 보고서 `:51-79`의 94/94·55/55·40/13·35/35, 197 eligible/27 제외, PNR/상용 사유와 8개 중복을 그대로 반영한다. 정적 eligibility를 정답률/전체 CVDP 지원으로 표현하지 않는다. |
| inner/outer·private 도식 | product-flow/native-loop/app-home SVG와 기존 architecture의 train-only label을 확인했다. private 자료는 evaluator로만 향하며 모델 쪽 반환은 binary 상태/집계다. `native_bridge.py:197-262`의 public processor·private helper 차단·run_attempt와 일치한다. outer 재평가와 inner pass를 구분하고 local Python의 OS sandbox를 주장하지 않는다. |
| report·History·서버 | `results.py:305-312`의 단일 normalized model, `report_model.py:338-418`의 기록 기반 algorithm trail/validation 비교, `history.py:332-349` 및 `report_server.py:156-175,209-249`의 재검증·HTML-only/loopback·포트 오류와 대조했다. nullable/partial·frozen selection 보존·evidence warning과 session child 별도 선택을 안내한다. |
| 개발 명령·기존 환경 | development의 setup-core/doctor-core와 legacy full setup/smoke/live 범위 구분이 유지된다. `scripts/dev.py:31-56`의 절대 AGENT_OPT_CORE_PYTHON·venv identity·현재 checkout PYTHONPATH와 안내가 맞는다. offline/cache·CA/proxy 복구를 실제 명령 범위별로 설명한다. |
| SOURCE SHA·과거 기록 | `git diff 28b5367 a0a8756`에서 SOURCES의 설명만 추가되고 기존 SHA가 유지된다. source/native manifest·driver lock·pyproject/uv lock·사이트 package/lock/config는 H에서 변경되지 않았다. verification.md는 새 절만 추가했다. 과거 OpenCode/Claude/evaluator-only 성공과 새 native not_run을 분리하며 개인 비공개 메모의 신규 전재를 발견하지 않았다. |
| 사이트 경로·scripts·근거 | package.json `:5-9`는 dev/build/preview/check:links이며 check:links=astro build, astro.config `:9-10,36`은 기존 site/base 및 link validator다. 9개 원고의 /agent-optimizer 내부 링크와 상대 asset 경로, 기존 반응형 SVG/CSS를 확인했다. 재마이그레이션·새 UI library/CSS·package script 변경은 없다. |

## 검증 증거의 범위

- **이번 리뷰:** 소스·문서·제공 diff 및 `28b5367..a0a8756` Git diff를 읽어 대조했다. 기존 H 저장 help/fixture stdout·preview 로그와 전후/도식 캡처 파일의 존재를 확인했다. 테스트·빌드·브라우저 검사는 재실행하지 않았다.
- **H가 기록한 기존 결과:** `final-mvp-h-20261001.md:39-65`의 help 11개·합성 7/2 trial·HTML-only HTTP/종료·관련 계약 31개와 lint, `:69-94`의 build/check:links 종료 0·10 pages·18 viewport 검사·전후 캡처를 기존 증거로 소비했다. 이번 독립 실행 결과로 주장하지 않는다.
- **G가 기록한 기존 결과:** `final-mvp-g-20261001.md:180-213`의 전체 1155개 중 1075 통과/80 skip, Ruff·실제 source-free wheel build/install·합성/HTTP/native helper 진단 근거를 대조했다. 새 native live·실 Docker cleanup·Ubuntu native loop 성공으로 확장하지 않는다.
- 실모델/native 전체 loop·실 EDA/cleanup·실 OS browser/SSH는 H가 명시한 미검증 범위를 유지한다. 기존 Astro directive/404 경고는 H 보고서상 변경 전부터 존재하며 이번 리뷰에서 새 결함으로 단정하지 않는다.

## 인계

H-R1의 안내와 복제 문구를 실제 prepare/doctor 책임에 맞춰 정정한 뒤 재리뷰한다. 이 리뷰는 위 발견 사항 외 기능 추가·pin 갱신·live 실행을 요구하지 않는다. 기록 파일은 `docs/verification/final-mvp-h-review-20261001.md` 하나이며 기존 기본 저장소 main·사용자 변경과 다른 워크트리를 보존한다.
