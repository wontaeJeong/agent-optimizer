# 제품 배경과 결정

요구사항의 출처는 사용자가 제공한 `agent-optimizer-v0.3.0.zip` 인수인계다.
제품은 **범용 Agent Optimizer**이며 RTL 디버깅은 첫 적용 분야다. 실제 대상 Agent의 내부 구조는
미확정이므로 OpenCode/sub-agent 등 특정 구조를 전제하지 않는다. ACE 데모 성공도 다른 팀 Agent 개선의 증거가 아니다.
처음 개발할 때는 [빠른 시작](../README.md#개발환경-빠른-시작) → [담당 템플릿](../experiments/README.md) →
[관련 계약](adding-components.md)만 따라가면 된다.

## 확정 요구사항

- Mac/Ubuntu의 Python CLI·대화형 TUI와 독립 HTML 보고서. 웹/분산 서버는 현재 요구사항이 아니다.
- 실제 Agent 개발자는 데이터셋을 직접 고른 뒤 검증된 준비 경로와 CLI/TUI로 Optimizer를 실행한다.
  팀별 데이터셋·하네스·Optimizer를 계속 추가하므로 중앙 registry/CLI 선택지 수정 없이 목록이 확장되어야 한다.
- 알고리즘·Agent/Harness·평가 담당이 `contracts.py`로 통합한다. 같은 기능에 추상 계층을 늘리지 않는다.
- 프롬프트뿐 아니라 설정·코드·역할·실행 흐름도 대상 Agent가 허용하는 범위에서 변경할 수 있어야 한다.
- 실제 Agent는 별도 repo의 고정 commit 또는 준비한 local 소스. 후보는 스냅샷에서 만들고
  원본·평가 기준·테스트는 수정하지 않는다. Agent 구성과 생성 RTL 등 과제 산출물은 별개다.
- 여러 팀의 독립 Agent와 한 Agent 내부 sub-agent는 다르다. 소스 버전·계보·결과를 그룹별로 식별한다.
- 실험별 Harness·Optimizer·평가·모델·지표·예산을 지정한다. 동일 조건 baseline/후보 비교,
  validation 선택, 선택 고정 후 test를 유지한다. 미수집 지표는 None, Agent/Optimizer 사용량은 분리한다.
- 미구현은 명시적으로 실패한다. 슬롯·등록·합성 점수로 실제 지원이나 성능을 주장하지 않는다.

## 2026-09-24 CLI/TUI·연구 검색 확장 선택

- `agent-opt init`/`tui`에서 CVDP·Verilog-Eval 또는 사용자 JSON 데이터셋을 **명시적으로 선택**한다.
  준비만 자동으로 수행하며 데이터셋을 자동 추천하거나 채점기를 추측하지 않는다.
- 내장 GEPA(반성·minibatch·validation Pareto/merge), Meta-Harness(코드 하네스 후보 탐색),
  Ecdysis(과제 간 반복 실패 그룹·다단계 검토·train 점수 엄격 개선)를 독립 stage로 구현한다.
  `.references`의 고정 자료를 참고한 **자체 메서드 구현**이며 원본/논문 재현으로 단정하지 않는다.
- Agent 실행 argv·실제 editable 경로·커스텀 evaluator는 사용자 또는 팀이 제공한다.
  준비된 데이터셋은 고정 버전/해시와 split을 기록하고, Verilog-Eval private test/ref는 Agent 밖에 둔다.
- 시간·iteration·dataset/과제 이벤트를 CLI/TUI와 HTML에서 같은 기록으로 확인한다.
  복수 dataset session은 독립 run과 보고서를 연결하고 서로 다른 평가 지표를 직접 순위화하지 않는다.
- 팀 등록은 `experiments/<team>/extensions.toml`의 Dataset/Harness/Optimizer/Evaluator 파일 경로다.
  기존 개별 experiment `[plugins.*]`도 그대로 사용한다.

## 현재 MVP 선택 (2026-09-22)

- 코어 setup/doctor와 API-free fixture부터 시작하고 팀 파일 플러그인 하나를 연결한다.
  `experiments/<team>/`가 소유권 경계이며 registry 수정/설치 entry point가 필요 없다.
- 여러 Agent × 호환 Harness 전체 조합 및 여러 독립 Optimizer를 순차 실행한다. 모든 stage는
  baseline에서 시작하며 stage-local train history와 공통 baseline cache를 사용한다.
  기본 최종 비교는 모든 stage winner, 선택은 lexicographic keep=1·mean/sum이다.
- 현재 변경 API는 텍스트 생성/교체다. 임의 pair matrix·삭제·바이너리 패치는 지원하지 않는다.
- 최소 데모는 두 합성 Agent·한 repair stage·7 trial이다. `baseline`/`file_variants`는 계약 예제이지 연구 알고리즘이 아니다.
- ACE는 선택적 OpenCode **스킬 프로필** 데모다. 기본 3회 단순 LLM train 피드백 뒤 validation 선택을 한다.
  native ACE runner나 논문 재현과 동일하지 않으며 이 프로필을 모든 Agent의 확정 요구사항으로 승격하지 않는다.
- ACE/CVDP/시뮬레이터 자산은 examples에 두고 공식 OSS 평가 환경을 재사용한다. 상용 EDA는 제외한다.
  로컬/외부 소스의 인증정보는 제외하고 키는 환경/credential store로 전달한다.

## 남은 결정

1. 실제 외부 Agent의 소스 접근·실행/평가법·editable·Harness/sub-agent 구조.
2. 실제 모델/Agent 조합의 반복 실험 및 세 자체 구현과 각 논문 방법·예제의 차이 검증.
3. 비교할 모델·예산·지표 우선순위·family 분리 데이터·전체 사용량 수집.
4. 향후 native ACE 대표 프로필과 원본 평가 루프/외부 evaluator의 책임 분담.

현재 기능은 [status](status.md), 후속 순서는 [NEXT_STEPS](NEXT_STEPS.md), 보류 기능/복원 위치는
[FUTURE](FUTURE.md), 외부 사실/고정 출처는 [SOURCES](SOURCES.md)다.
[날짜별 검증](verification.md)은 당시 환경의 증거이며 첫 실행 필수 읽기 목록이 아니다.
