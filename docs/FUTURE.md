# 보류 기능과 복원 조건

현재 MVP는 여러 Agent × 호환 Harness와 여러 **독립 파일 Optimizer**를 지원한다.
baseline-only stage, stage-local train history, 모든 stage winner의 기본 비교,
lexicographic keep=1·mean/sum을 먼저 검증한다. 아래 기능을 켜는 experimental flag는 없다.

## 활성 표면에서 이동한 기능

stage chaining/validation gate, **공통 objective의** weighted/Pareto·constraints·복수 winner·max/p95,
stored-result rerank, 설치 entry-point 자동 발견은 보류했다.
**원본 코드·테스트·예제별 복원 위치와 조건은 [deferred/README.md](../deferred/README.md)**에 있다.
기준 revision은 `9afcabe`; `.txt` snapshot은 실행 프로필이 아니다.
명시적인 팀 요구와 경계/partial/null 회귀를 확보한 뒤 검토하며 과거 acceptance test를 현재 지원으로 해석하지 않는다.
과거 GEPA/Meta-Harness/Ecdysis 오류 슬롯 snapshot은 이력이며, 현재 내장 메서드 구현과 동일한 코드가 아니다.
새 연구 이름은 팀 파일 플러그인으로 계속 추가할 수 있다.

## 아직 구현하지 않은 확장

- **전체 화면 실행 이력 탐색:** 현재 `agent-opt tui`는 설정 wizard와 실시간 단계/시간 화면이며
  복수 과거 실행을 탐색하는 화면은 제공하지 않는다.
- **병렬 scheduler / resume:** 현재 순차 실행. checkpoint/결과 보존은 재시작이나 동시 실행 보장이 아니다.
- **native ACE:** 현재 OpenCode 스킬 프로필과 별도다. 원본 runner/wrapper·의존성·모델/내부 반복 예산,
  private 평가와 피드백 책임, timeout/정리/사용량 및 실제 역할 호출 증거가 필요하다.
- **새 전용 Harness / 연구 알고리즘:** 정확한 대상·고정 버전·공통 계약·실환경 증거를 확보한 팀이 구현한다.
- **엄격한 비용/호출 상한, 임의 Agent/Harness pair matrix, 삭제/바이너리 변경:** 구체적 요구가 생긴 뒤 설계한다.

당장 할 일은 [NEXT_STEPS](NEXT_STEPS.md)의 코어 fixture → 팀 플러그인 경로다.
