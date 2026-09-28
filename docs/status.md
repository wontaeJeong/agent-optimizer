# 현재 구현·검증 상태

**2026-09-28 CLI 선택형 경로:** `catalog list/show`는 등록 항목의 설명을 읽기 전용으로
조회하고, `init --agent-preset ace-rtl --harness-profile ace-opencode --optimizer gepa|meta_harness
--dataset cvdp --yes`는 독립된 run-owned 설정을 생성합니다. `tui` 첫 화면도 네 항목을 순서대로
선택하고 같은 설정 생성 함수를 사용합니다. `init --yes`는 선택 데이터셋과 ACE 고정 자산을 준비하고
`prepare EXPERIMENT`는 준비된 자산을 검증·재사용합니다. GEPA의 후보 role-guidance는
기존 ACE adapter의 prompt에, Meta-Harness의 후보 `.py`는 각 trial의 공개 과제
`build`에 연결합니다. 새 설정은 원래 고정 simple_feedback 실험을 대체하지 않습니다.
코어/합성·설치형·Docker/모델/공식 평가의 새 검증 수준은 [날짜별 기록](verification.md)을
따르며 준비 여부만으로 점수나 개선을 주장하지 않습니다.

**2026-09-27 확장:** 코어 setup/doctor → 명시적 데이터셋·ACE 프로필 선택/준비 → CLI/TUI 최적화 → HTML 보고서.
팀 개발의 API-free fixture → 파일 플러그인 경로도 유지한다.
시작은 [README](../README.md#개발환경-빠른-시작)와 [역할별 템플릿](../experiments/README.md).
번호 메뉴는 제공하며 1/2는 core, 7은 선택적 ACE 전체 준비, 8은 일반 Agent TUI다.
옵션 없는 setup/doctor의 전체 ACE 경로와 `--dataset ID`의 선택 데이터셋 경로는 별개다.
`agent-opt tui`는 기존 실험, 새 실험, ACE-RTL + CVDP 예제의 별도 선택·준비·실행을 지원한다.
5번 선택형 새 최적화는 ACE-RTL/OpenCode/GEPA·Meta-Harness/CVDP 및 합성 Agent/Fixture/Baseline·FileVariants/sample_text를 각각 명시적으로 선택한다. 초점 이동은 읽기 전용이며 마지막 확인 이후에만 자산을 준비한다.
1번 기존 실험은 `runs/configs/`의 최근 생성 설정 최대 5개를 번호로 선택하거나 직접 경로를 입력한다.
4번 이전 실행 보기는 현재 작업공간의 `runs/<run-id>`와 `runs/dev-live/<run-id>`에서 요약과
HTML이 있는 실행을 run ID의 UTC 생성 시각순 최근 10개까지 읽기 전용으로 나열하고,
선택한 보고서의 절대경로만 표시한다.
symlink·손상된 요약은 제외하며 보고서를 생성하거나 브라우저를 열지 않는다.
`agent-opt init`은 TTY에서 새 설정만 만들 수 있다. 복수 데이터셋 session은 독립 프로세스로
기본 2개를 병렬 실행하며 `--jobs`로 동시 실행 수를 제한한다. 단일 실험 내부 병렬화·resume·native ACE는 [보류](FUTURE.md)다.
고정 `examples/ace-rtl/experiment.toml`을 TUI/`agent-opt run`에서 선택하면 예제 어댑터가
기존 `live` 준비·실행에 위임한다. 이는 OpenCode 스킬 프로필 + 공식 CVDP 평가이며 native ACE는 아니다.
wheel 단독 설치에서 로컬 Agent·사용자 데이터셋/명시적 evaluator 실험과
`init --profile ace-rtl` → `prepare` → `doctor --plan` → `run`을 소스 저장소 없이
선택할 수 있다. CVDP·Verilog-Eval도 선택 시에만 고정 출처의 코드를 가져온다.
준비 완료 marker와 자산 해시가 없으면 실행하지 않는다. 개발 checkout의 full ACE
`setup`/`smoke`/`live`는 같은 예제 lifecycle을 재사용한다.

## 현재 기능

| 기능 | 현재 범위 / 근거 |
|---|---|
| 복수 Agent × Harness | `[[pairs]]` 생략 시 Agent 우선 전체 곱, 명시 시 선언 순서대로 선택한 쌍만 순차 실행. 알 수 없는 ID·중복·미지원·미사용 선언 거부, 그룹별 버전·계보·결과. 내부 sub-agent 자동 관리는 없음 |
| 복수 독립 Optimizer | 명시적 파일 등록, stage마다 baseline 시작. stage-local train history, 공유 baseline cache. 기본 최종 비교는 모든 stage winner |
| 평가·선택 | train-only 탐색, validation 선택 고정 후 test. lexicographic keep=1, mean/sum, custom evaluator metrics |
| 원본·평가 경계 | 고정 Git/local snapshot, editable·후보 변조 검사, private 평가 분리. local/in-process plugin은 OS 격리 아님 |
| 결과·사용량 | manifest/hash/diff/lineage, trial/event/checkpoint/frozen selection/summary/report. Optimizer usage는 stage와 optimizer 이름 포함; nullable/partial 유지 |
| baseline/file_variants | API-free 실행 가능. 최소 데모는 두 Agent·한 repair stage·7 trial(solo 4/team 3), 합성 점수 |
| 팀 템플릿 | Optimizer·Harness·외부 Agent 복사 경로. Harness는 Agent/프로필/experiment 전체 배선; stub 실행은 명시적 UnavailableError |
| 단순 LLM 피드백 | 파일 플러그인, 기본 3회 train 수정/재평가. 로컬 fixture 회귀와 실제 배포 모델 실행은 별개 |
| command/OpenCode/Docker | argv·timeout·오류/이벤트 계약. 실환경 통합 근거는 아래 날짜별 기록을 따름 |
| core 준비/진단 | Docker/ACE/모델 없이 준비·진단·fixture. 첫 의존성 준비에는 다운로드가 필요할 수 있음 |
| 사용자 CLI/TUI | 데이터셋·비대화형 `init` Optimizer 명시적 선택, 선택 데이터셋 자동 준비, argv/editable 검증, 중앙 Python 등록 팀 목록, 읽기 전용 `doctor --dataset/--plan`, 과제·iteration 실시간 경과, 복수 데이터셋 병렬 session 상태 행 |
| Dataset | CVDP reviewed no-commercial importer/공식 평가기, 고정 Verilog-Eval v2 + 별도 Icarus v12 private 평가기, 사용자 tasks.json + 지정 evaluator |
| GEPA/Meta-Harness/Ecdysis | 원본을 복제하지 않은 자체 메서드 구현: train 반성·validation Pareto, scaffold 탐색, 반복 실패/협업 검토/strict train 개선. GEPA 병합은 비활성화; 실제 배포 모델 검증과 분리 |
| 결과 UX | 항상 `report.html`/summary/events/Markdown, dataset session별 독립 보고서 연결. `report.json` v3는 기록된 validation 집계·trial·과제 비교와 근거 완전성/불일치를 시각화용으로 정규화하며, HTML은 그룹별 개선 추이·기준 대비 선택·탐색 계보·과제·시간/실패를 독립 SVG/CSS로 표시. 없는 비용/집계는 추정하지 않음 |

코어/연구 구현 근거는 [2026-09-24 검증](verification.md#2026-09-24-cli-tui-and-research-method-integration), 후속 작업은
[NEXT_STEPS](NEXT_STEPS.md). 보류한 chaining/gates/공통 objective의 weighted/Pareto/constraints/rerank/설치 entry point는
[FUTURE](FUTURE.md)와 [복원 지도](../deferred/README.md)에 구분했다. 이전 슬롯은 현재 세 자체 구현의 근거가 아니다.

## ACE-RTL 실행 프로필

기본 `simple_feedback` 예제는 `source.toml` → runner가 SKILL.md 읽기 → `adapter.py:ACEOpenCode` 제한 지침 추가
→ OpenCode 호출 → 종료 후 외부 CVDP 평가다. `simple_feedback`이 바꾼 role-guidance.md는 prompt에 포함한다.
native `ace_agent_runner.py`/`ace_cvdp_native_runner.py`의 자체 역할·반복·평가 루프 실행과 동일하지 않다.
역할 Python 파일이 editable이어도 실제 호출되었다는 증거 없이는 native 코드 최적화를 주장할 수 없다.
새 선택형 GEPA는 후보 role-guidance의 prompt 반영을 유지한다. 새 선택형 Meta-Harness는 별도로 추가한
`agent_opt_scaffold.py`의 `prepare_task`를 후보 복사본에서 공개 과제에 실행해 파일 해시/결과를 기록한다.
이는 upstream ACE 역할 Python/native runner의 실행이 아니라 OpenCode 전 단계의 자체 scaffold다.
실환경 실행 후에도 주장 범위는 **선택한 데이터/모델/예산에서 이 스킬 프로필의 안내 변경 효과**다.

- setup의 고정 HF 입력은 302개 중 지원 형태 71개, 제외 231개다. 전체 시뮬레이션 통과 수가 아니다.
  live는 priority encoder train/QAM16 validation, final_test=false; evaluator smoke는 별도 LFSR이다.
- importer는 검토한 cid003/rtl 출력/OSS Compose 형태에 한정하며 제외 사유를 기록한다.
  상용 문자열 검사는 전체 의존성 분석이 아니므로 신규 과제의 실제 실행·채점을 별도 검토해야 한다.
- 후보 output.context를 공식 driver에 넘기며 비어 있지 않은 integer tests가 모두 0일 때 binary 통과다.
  공식 score-based 전체 집계 대체가 아니다. private 자산은 공개 입력에서 분리한다.
- 환경 오류/unsupported 포함 split은 모든 집계가 null이다. 공식 result=1도 private log의
  Docker build/launch 오류면 환경 실패다. 정상 HDL 오답은 passed=0을 유지한다.
- OpenCode root 이벤트의 harness_reported 사용량은 partial이며 전체 Agent 사용량은 null이다.
  작은 RTL evaluator도 합성만으로 정화하지 않으며 입력 제한·private 검사 완료가 필요하다.

## 검증 수준

- **2026-09-28 후속 실환경 검사:** 고정 소스·driver·이미지를 준비한 Mac ARM64에서 호스트 모델 도구 호출과 Docker OpenCode 도구 호출, 공식 CVDP smoke 정답/오답이 통과했다. GEPA·Meta-Harness **각 1 iteration, 실제 4/최대 5 trial**에서 후보 파일 변경·실제 Harness 입력/실행·공식 raw 채점(각 test 1건 `result=0`)이 연결됐다. 두 validation은 baseline/후보가 1.0 동점이어서 baseline을 선택했고 최종 test는 없다. **성능 향상·기본 3회 반복·설치형 wheel의 해당 모델 연동** 검증은 아니다. [별도 실환경 근거](verification.md#2026-09-28-선택형-gepameta-harness-실모델공식-cvdp-후속-검증).
- **2026-09-28 선택형 TUI 계약:** 최신 main 반영 후 `make test` 781건 중 766 통과·15 skip, Ruff·합성 데모·독립 wheel TUI·사이트 빌드 통과. `make doctor`는 이 워크트리의 ACE 자산/환경 lock 누락으로 exit 2였으므로 두 선택형 알고리즘의 **실모델/OpenCode·공식 CVDP 결과는 미검증**이다. [날짜별 근거](verification.md#2026-09-28-선택형-tuiace-후보-연결-계약-검증).
- **2026-09-27 첫 실행 UX 검증:** Mac ARM64의 `make lint/test/demo`, 독립 wheel 사용자 CLI,
  Astro 사이트 빌드가 통과했다(최신 main 반영 후 734개 중 719 통과·15 skip, 합성 7 trial). 새 워크트리의
  ACE/CVDP 자산은 미준비로 `make smoke`가 차단되었으며 공식 평가/외부 모델은 실행하지 않았다.
  [명령별 근거](verification.md).
- **현재 로컬 계약 검증:** copied Harness의 실제 fixture 실행과 파일 fingerprint, 원본 stub 실패,
  여러 독립 Optimizer/Agent의 history·선택·usage를 검사한다. API-free 회귀는 외부 CLI/모델 성공이 아니다.
- **2026-09-27 선택 쌍 계약 검증:** 두 Agent×두 fixture 프로필에서 생략 시 4그룹, 명시 시 2그룹의
  plan/doctor 예산·실행 그룹·원본 manifest를 대조했다. 새 fixture 프로필은 테스트 임시 프로젝트에서
  생성했으며 API-free 계약 결과는 실제 외부 Agent/모델 성능 근거가 아니다.
- **과거 실환경 근거:** `10baa46`의 native Ubuntu 공식 통합, `ed4fea4`의 Python 3.11/3.12 및
  공식 Docker/SSE-tool fixture, 온보딩 검증을 [날짜별 기록](verification.md)에 유지한다.
  그 당시 9-trial minimal 기록은 당시 결과이며 현재 7-trial 경로로 소급 수정하지 않는다.
- **이번 실제 연결 검증:** DeepSeek `deepseek-flash` → ACE OpenCode 스킬 프로필 → 공식 CVDP의 두 과제·4 trial이 Mac ARM64에서 실행되었다. 두 validation 후보가 1.0으로 동점이라 시간 기준으로 baseline이 선택되었다. [2026-09-25 기록](verification.md#2026-09-25-ace-rtl-스킬-프로필-실제-모델-e2e).
- **Claude Code 첫 실실행은 차단:** Mac ARM64의 Claude Code 2.1.261·DeepSeek Anthropic 호환 endpoint에서 당시 baseline 2/4 trial이 `error_max_turns`로 종료됐다. 그 당시 train/validation 공식 raw 결과·후보 선택은 없었다. [첫 기록](verification.md#2026-09-27-claude-codedeepseekcvdp-첫-실실행-차단)은 보존한다.
- **별도 승인 후 추가 4-trial 실실행:** DeepSeek `deepseek-flash` Agent와 명시적 OpenAI Optimizer 모델 1회 제안으로 두 train·후보 validation 3건의 공식 raw test가 통과했다. baseline validation은 `agent_incomplete`/무효/null이고 공식 raw가 없다. 유효한 `c0002`가 선택됐지만 baseline 대비 개선률은 비교 불가다. [추가 실행 근거](verification.md#2026-09-27-claude-code-추가-4-trial-공식-cvdp-부분-성공).
- **현재 Claude Code 도구 설정:** 첫 실행은 MCP 도구 목록 노출만 확인됐고 호출은 확인되지 않았다. 둘째 실행에는 등록된 codegraph/Playwright MCP 도구 시도·권한 거부가 있었다. 두 실행 모두 `--strict-mcp-config`가 없었다. flag 추가 직후에는 argv 회귀만 통과했다. [당시 계약](verification.md#2026-09-27-claude-code-암묵적-mcp-설정-차단-계약-실모델-미검증).
- **strict MCP 세 번째 독립 실실행:** 4/4 trial에서 네 CLI 초기 도구 목록과 tool-use 모두 MCP 0건. baseline train 공식 raw 1/1 통과, 후보 train은 RTL 출력 누락으로 0점·공식 raw 없음, 두 validation은 `agent_incomplete`/raw 없음. `no_eligible_candidate`/선택 없음이며 개선 비교 불가. [실행 근거](verification.md#2026-09-27-strict-mcp-적용-후-세-번째-독립-4-trial-선택-없음).
- **공개 RTL target 경로 안내 후 네 번째 독립 실실행:** DeepSeek Agent + 명시적 OpenAI Optimizer 한 번, 4/4 trial 모두 공식 raw 채점. baseline train/validation 및 후보 train은 1/1, 후보 validation은 기능 불일치로 0/1(모두 `valid=true`). `completed`지만 `c0001` baseline이 선택되어 성능 개선 근거는 없다. [새 실행 근거](verification.md#2026-09-27-공개-rtl-target-안내-후-네-번째-독립-실실행).
- **연구 예제의 새 실모델 부분 검증:** [model-rtl-agent](../examples/model-rtl-agent/README.md)를 선택 CVDP의 공개 두 train family·별도 validation family와 DeepSeek Agent / OpenAI Optimizer로 한 번 실행했다. Mac ARM64의 공식 평가 raw 6건(정답 5·오답 1), **9/16 trial 뒤 `error`**. QAM16 train의 60초 Agent 요청 두 건이 `infrastructure_error`/raw 없음으로 끝나 baseline train 집계가 `null`이고, Ecdysis는 이를 거부했다. GEPA·Meta의 stage validation 각 1/1은 **전체 winner/선택 고정이 아니다**. Meta 후보의 fallback QAM16 train도 출력 누락 0점/raw 없음이다. [명령·trial별 근거](verification.md#2026-09-27-연구-optimizer-선택-cvdp-한정-실모델-실행-중단).
- **두 번째 독립 CVDP 실행:** Agent 요청만 120초로 조정한 별도 승인 run은 Mac ARM64에서 **11/16 trial `completed`**, 공개 과제 공식 raw **11건(통과 8·실패 3)**. 실패 3건은 모델 응답의 Markdown 코드 펜스가 RTL에 남아 발생한 Icarus 컴파일 구문 오류이며 기능 불일치 근거는 아니다. GEPA·Meta·Ecdysis 모두 완료했지만 세 stage의 선택과 전체 고정 선택은 validation 1.0인 baseline `c0001`이다. Meta의 변경된 실행 Python 후보는 train 2/2·validation 1/1 통과했으나 동점이라 선택되지 않았고, Ecdysis 변경 Python 후보는 train 엄격 개선이 없어 validation을 실행하지 않았다. `final_test=false`, 일반적 성능 향상 근거는 없다. [독립 실행 원시 근거](verification.md#2026-09-28-연구-optimizer-선택-cvdp-두-번째-독립-실모델-실행).
- **연구 예제 실행 경계:** 두 실행은 신뢰한 로컬 Python 후보 코드에서만 적용한다. `runtime.kind="local"` 후보는 호스트의 동일 사용자 권한으로 실행되며 공개 workspace/private 평가의 논리적 파일 분리는 OS 격리가 아니다. 후보는 동일 사용자의 private 자산·Optimizer API 키에 접근할 수 있다. `model_unavailable` stdout/exit 2에 따른 `infrastructure_error`는 후보 자기보고 오류 분류이지 신뢰된 인프라 인증 장애의 증명이 아니다. 위 첫 run의 무효/null은 좋은 점수나 공식 raw로 바뀌지 않는다.
- **선택형 wheel의 새 검증:** Mac ARM64에서 소스 밖 wheel 설치·사용자 Agent 합성 실행, 선택형 ACE 고정 Git/driver/이미지 준비와 읽기 전용 계획 진단, Docker 공식 LFSR 정답·오답을 확인했다. 모델 키 없는 `run`은 `blocked_auth`로 차단된다. [같은 날짜의 별도 기록](verification.md#2026-09-25-선택형-wheel-연동-검증).
- **미검증:** 세 연구 알고리즘의 일반화된 성능 향상·후보별 최종 test, native ACE,
  Verilog-Eval의 전체 과제/Ubuntu x86_64 실행, 전체 sub-agent 사용량. 새 팀 컴포넌트도
  복사/fixture 검증과 실제 환경 실행을 각각 구분한다. plan doctor는 설정/등록·로컬 자산 수준 검사다.
