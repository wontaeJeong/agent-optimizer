---
title: 동작 원리
description: Agent Optimizer의 구성, 실행 순서, 최적화 반복과 팀 컴포넌트의 경계를 한눈에 봅니다.
---

Agent Optimizer는 **Agent를 실행하고, 결과를 채점하고, 허용된 파일을 바꾼 후보를 비교**하는 도구입니다. 아래 그림의 화살표는 정보가 이동하는 방향을 보여 줍니다. 자세한 실행 명령은 [첫 실행](/agent-optimizer/getting-started/first-run/)에 있습니다.

## 전체 구조

```mermaid
flowchart TB
  A[Agent 원본] --> S[원본 보존 스냅샷]
  S --> H[Harness: 후보 Agent 실행]
  D[사용자가 고른 Dataset] -->|공개 과제| H
  H -->|산출물| E[Evaluator: 별도 채점]
  D -->|평가 자료는 Agent 밖에 보관| E
  E --> T[Trial: 실행과 채점 기록]
  T --> O[Optimizer: 후보 제안]
  O -->|editable 파일만 변경| S
  T --> R[실험별 Report]
```

**Agent**는 최적화할 대상, **Harness**는 이를 실행하는 방법, **Dataset**은 과제 모음, **Evaluator**는 실행 결과를 채점하는 컴포넌트입니다. Optimizer는 원본을 고치지 않고 허용된 파일만 바꾼 스냅샷을 만듭니다. 채점 전용 자료는 Agent 실행 공간으로 전달하지 않습니다. [역할별 상세 설명](/agent-optimizer/developer/overview/)도 참고하세요.

## 실험 단계

```mermaid
flowchart TB
  C[Configure: Agent·과제·수정 범위 선택] --> P[Prepare: 선택 자산 준비]
  P --> D[Doctor: 설정과 준비 상태 진단]
  D --> R[Run: 실험 시작]
  R --> B[baseline의 validation 점수]
  B --> T[train에서 후보 탐색]
  T --> V[validation으로 후보 선택]
  V --> F[선택 고정]
  F --> Q{final_test 설정?}
  Q -->|예| X[고정 후보와 baseline의 test]
  Q -->|아니요| O[Report 생성]
  X --> O
```

사용자가 데이터셋을 직접 선택합니다. `doctor --plan`은 **준비 전에도** 실행할 수 있지만, 그때는 부족한 자산을 표시할 수 있습니다. 준비 뒤 다시 확인해도 실제 모델 호출이나 채점 성공을 보증하지 않습니다. `run`은 부족한 자산을 자동 설치하지 않으며, 최종 test는 선택을 고정한 뒤에만 실행합니다.

## 최적화 반복

```mermaid
flowchart LR
  B[공통 baseline] --> E[train 과제 실행]
  E --> V[Evaluator의 train 결과]
  V --> O[선택한 Optimizer]
  O -->|허용 파일 변경| C[후보 Agent]
  C --> E
  C --> S[validation 수치로 후보 비교]
  S --> W[stage별 승자와 최종 후보 선택]
```

각 Optimizer stage는 공통 baseline에서 **독립적으로** 시작합니다. 수정 근거와 이력에는 baseline과 자기 stage의 train 결과만 들어갑니다. 일부 방법은 validation **수치**를 내부 후보 선택에 사용할 수 있지만, 비공개 채점 자료나 test 결과를 수정 근거로 받지 않습니다. [결과 읽기](/agent-optimizer/getting-started/results/)에서 선택된 후보와 실패 근거를 확인하세요.

## 컴포넌트 경계

```mermaid
flowchart LR
  Team[팀 코드: Dataset·Harness·Optimizer·Evaluator] --> Contract[contracts.py: 공통 계약]
  Team --> Registry[registry.py: ID와 구현 파일 등록]
  Contract --> Runner[Runner: 실험 실행과 기록]
  Registry --> Runner
  Runner -->|공개 입력| Agent[Agent 작업공간]
  Runner -->|분리된 채점| Evaluator[Evaluator 작업공간]
```

팀 구현은 `experiments/<team>/`에서 관리하고 중앙 `registry.py`에 ID를 등록합니다. Runner가 공통 계약을 통해 컴포넌트를 호출하므로 알고리즘끼리 직접 연결하지 않습니다. 로컬 팀 플러그인에는 자동 OS 격리가 없으므로 신뢰한 코드를 연결합니다. [컴포넌트 연결](/agent-optimizer/developer/components/)에서 실제 파일과 메서드를 확인하세요.
