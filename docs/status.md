# 현재 구현·검증 상태

**2026-09-22 MVP:** 코어 setup/doctor → API-free fixture → 팀 파일 플러그인 하나가 기본 경로다.
시작은 [README](../README.md#개발환경-빠른-시작)와 [역할별 템플릿](../experiments/README.md).
번호 메뉴는 제공하며 1/2는 core, 7은 선택적 ACE 전체 준비다. 옵션 없는 setup/doctor의 전체 경로도 유지한다.
rich TUI·병렬 scheduler·resume·native ACE는 [보류](FUTURE.md) 상태다.

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

현재 실행 근거는 [MVP 검증](verification.md#2026-09-22-mvp-team-templates), 후속 작업은
[NEXT_STEPS](NEXT_STEPS.md). 보류한 chaining/gates/weighted/Pareto/constraints/rerank/설치 entry point/연구 슬롯은
[FUTURE](FUTURE.md)와 [복원 지도](../deferred/README.md)에 구분했다. 연구 알고리즘은 구현 완료가 아니다.

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
- **미검증:** 실제 배포 모델→ACE→CVDP 최적화/성능 개선, native ACE, 전체 sub-agent 사용량.
  새로운 팀 CLI나 연구 구현은 각각 별도 증거가 필요하다. plan은 설정/등록 수준의 검사다.
