# 구조와 경계

팀 확장은 **`experiments/<team>/`에 구현하고 `src/agent_optimizer/registry.py`에 등록**합니다. 코어는 실험 선언, 원본 스냅샷, 실행·평가와 결과 기록을 담당합니다. 제품은 범용 Agent Optimizer이며 특정 RTL Agent나 벤치마크가 필수 조건은 아닙니다.

## 누가 무엇을 맡나요?

| 구성 | 책임 | 입력과 출력 |
|---|---|---|
| Agent 소스 | 최적화할 실행 대상 | 로컬 소스 또는 전체 commit으로 고정한 Git 소스 |
| Dataset provider | 사용자가 선택한 과제 준비 | 공개 과제·split·버전/출처 및 분리된 평가 자산 |
| Harness | 후보 Agent 실행 | `RunRequest` → `ExecutionResult`, 공개 과제 입력·산출물 |
| Evaluator | 실제 결과 채점 | `Task`와 산출물 → `Evaluation` |
| Optimizer | 허용된 변경으로 후보 제안 | `OptimizationContext` → `OptimizationResult` |
| Runner | 예산·분할·선택·기록 | 독립 stage, 그룹별 보고서와 이벤트 |

[첫 화면의 연결도](../index.md#workflow)는 구성 간 데이터 흐름을 보여줍니다. 원본은 보존하고 후보는 editable 파일의 스냅샷에서 만듭니다. 공개 과제만 Agent 실행 공간으로 전달하며 private 채점 자료는 Evaluator가 관리합니다. 신뢰한 팀 Python 플러그인이나 로컬 Harness에는 OS 격리가 자동으로 생기지 않습니다.

## 선택과 정보 경계

```mermaid
flowchart LR
  B[공통 baseline] --> T1[stage A: train 후보 탐색]
  B --> T2[stage B: train 후보 탐색]
  T1 --> V[각 stage validation 평가]
  T2 --> V
  V --> W[후보 선택 고정]
  W --> X[선택적 test]
  X --> R[독립 실험 보고서]
```

도식의 순서: 모든 Optimizer stage가 공통 baseline에서 독립적으로 시작하고 **자기 stage와 baseline의 train 이력**만 사용합니다. validation의 수치로 후보를 선택할 수 있지만 private 평가 자료와 test 결과는 수정 근거로 노출되지 않습니다. 최종 선택을 고정한 뒤에만 test를 실행합니다.

기본 최종 비교는 모든 stage winner를 대상으로 하며 선택은 lexicographic `keep=1`, 지표 집계는 `mean`/`sum`입니다. 서로 다른 데이터셋의 평가 점수를 하나로 합쳐 순위를 매기지 않습니다. [컴포넌트 연결](components.md)에서 팀 확장 경로를 확인하세요.
