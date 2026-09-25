# 현재 구현·검증 상태

**2026-09-24 확장:** 코어 setup/doctor → 명시적 데이터셋 선택/준비 → CLI/TUI 최적화 → HTML 보고서.
팀 개발의 API-free fixture → 파일 플러그인 경로도 유지한다.
시작은 [README](../README.md#개발환경-빠른-시작)와 [역할별 템플릿](../experiments/README.md).
번호 메뉴는 제공하며 1/2는 core, 7은 선택적 ACE 전체 준비, 8은 일반 Agent TUI다.
옵션 없는 setup/doctor의 전체 ACE 경로와 `--dataset ID`의 선택 데이터셋 경로는 별개다.
`agent-opt tui`는 기존 실험의 계획 진단·확인·실행과 새 실험 생성·실행을 선택할 수 있고,
`agent-opt init`은 TTY에서 새 설정만 만들 수 있다. 병렬 scheduler·resume·native ACE는 [보류](FUTURE.md)다.
고정 `examples/ace-rtl/experiment.toml`을 TUI/`agent-opt run`에서 선택하면 예제 어댑터가
기존 `live` 준비·실행에 위임한다. 이는 OpenCode 스킬 프로필 + 공식 CVDP 평가이며 native ACE는 아니다.

## 현재 기능

| 기능 | 현재 범위 / 근거 |
|---|---|
| 복수 Agent × Harness | 모든 호환 조합 순차 실행, 그룹별 버전·계보·결과. 임의 pair matrix/내부 sub-agent 자동 관리는 없음 |
| 복수 독립 Optimizer | 명시적 파일 등록, stage마다 baseline 시작. stage-local train history, 공유 baseline cache. 기본 최종 비교는 모든 stage winner |
| 평가·선택 | train-only 탐색, validation 선택 고정 후 test. lexicographic keep=1, mean/sum, custom evaluator metrics |
| 원본·평가 경계 | 고정 Git/local snapshot, editable·후보 변조 검사, private 평가 분리. local/in-process plugin은 OS 격리 아님 |
| 결과·사용량 | manifest/hash/diff/lineage, trial/event/checkpoint/frozen selection/summary/report. Optimizer usage는 stage와 optimizer 이름 포함; nullable/partial 유지 |
| baseline/file_variants | API-free 실행 가능. 최소 데모는 두 Agent·한 repair stage·7 trial(solo 4/team 3), 합성 점수 |
| 팀 템플릿 | Optimizer·Harness·외부 Agent 복사 경로. Harness는 Agent/프로필/experiment 전체 배선; stub 실행은 명시적 UnavailableError |
| 단순 LLM 피드백 | 파일 플러그인, 기본 3회 train 수정/재평가. 로컬 fixture 회귀와 실제 배포 모델 실행은 별개 |
| command/OpenCode/Docker | argv·timeout·오류/이벤트 계약. 실환경 통합 근거는 아래 날짜별 기록을 따름 |
| core 준비/진단 | Docker/ACE/모델 없이 준비·진단·fixture. 첫 의존성 준비에는 다운로드가 필요할 수 있음 |
| 사용자 CLI/TUI | 데이터셋 명시적 선택·자동 준비, argv/editable 검증, 중앙 Python 등록 팀 목록, 읽기 전용 `doctor --dataset/--plan`, 과제·iteration 실시간 경과 |
| Dataset | CVDP reviewed no-commercial importer/공식 평가기, 고정 Verilog-Eval v2 + 별도 Icarus v12 private 평가기, 사용자 tasks.json + 지정 evaluator |
| GEPA/Meta-Harness/Ecdysis | 원본을 복제하지 않은 자체 메서드 구현: train 반성·Pareto/merge, scaffold 탐색, 반복 실패/협업 검토/strict train 개선. 실제 배포 모델 검증과 분리 |
| 결과 UX | 항상 `report.html`/summary/events/Markdown, dataset session별 독립 보고서 연결. `report.json` v2는 기록된 validation 집계·trial·과제 비교를 시각화용으로 정규화하며, HTML은 그룹별 개선 추이·기준 대비 선택·탐색 계보·과제·시간/실패를 독립 SVG/CSS로 표시. 없는 비용/집계는 추정하지 않음 |

코어/연구 구현 근거는 [2026-09-24 검증](verification.md#2026-09-24-cli-tui-and-research-method-integration), 후속 작업은
[NEXT_STEPS](NEXT_STEPS.md). 보류한 chaining/gates/공통 objective의 weighted/Pareto/constraints/rerank/설치 entry point는
[FUTURE](FUTURE.md)와 [복원 지도](../deferred/README.md)에 구분했다. 이전 슬롯은 현재 세 자체 구현의 근거가 아니다.

## ACE-RTL 실행 프로필

현재는 `source.toml` → runner가 SKILL.md 읽기 → `adapter.py:ACEOpenCode` 제한 지침 추가
→ OpenCode 호출 → 종료 후 외부 CVDP 평가다. `simple_feedback`이 바꾼 role-guidance.md는 prompt에 포함한다.
native `ace_agent_runner.py`/`ace_cvdp_native_runner.py`의 자체 역할·반복·평가 루프 실행과 동일하지 않다.
역할 Python 파일이 editable이어도 실제 호출되었다는 증거 없이는 native 코드 최적화를 주장할 수 없다.
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

- **현재 로컬 계약 검증:** copied Harness의 실제 fixture 실행과 파일 fingerprint, 원본 stub 실패,
  여러 독립 Optimizer/Agent의 history·선택·usage를 검사한다. API-free 회귀는 외부 CLI/모델 성공이 아니다.
- **과거 실환경 근거:** `10baa46`의 native Ubuntu 공식 통합, `ed4fea4`의 Python 3.11/3.12 및
  공식 Docker/SSE-tool fixture, 온보딩 검증을 [날짜별 기록](verification.md)에 유지한다.
  그 당시 9-trial minimal 기록은 당시 결과이며 현재 7-trial 경로로 소급 수정하지 않는다.
- **이번 실제 연결 검증:** DeepSeek `deepseek-flash` → ACE OpenCode 스킬 프로필 → 공식 CVDP의 두 과제·4 trial이 Mac ARM64에서 실행되었다. 두 validation 후보가 1.0으로 동점이라 시간 기준으로 baseline이 선택되었다. [2026-09-25 기록](verification.md#2026-09-25-ace-rtl-스킬-프로필-실제-모델-e2e).
- **미검증:** 실제 배포 모델→실 Agent에 세 연구 알고리즘을 적용한 성능 향상, native ACE,
  Verilog-Eval의 전체 과제/Ubuntu x86_64 실행, 전체 sub-agent 사용량. 새 팀 컴포넌트도
  복사/fixture 검증과 실제 환경 실행을 각각 구분한다. plan doctor는 설정/등록·로컬 자산 수준 검사다.
