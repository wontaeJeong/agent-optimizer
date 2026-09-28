---
title: 컴포넌트 연결
description: 팀 템플릿을 골라 공통 계약을 구현하고 Dataset·Harness·Optimizer·Evaluator ID를 등록합니다.
---

**시작 조건:** [README의 코어 빠른 시작](https://github.com/wontaeJeong/agent-optimizer#개발환경-빠른-시작)을 마친 뒤 [담당별 템플릿 목록](https://github.com/wontaeJeong/agent-optimizer/blob/main/experiments/README.md)에서 **자신의 역할 하나**를 고릅니다. 팀 구현은 `experiments/<team>/`에 두고, [확장 계약](https://github.com/wontaeJeong/agent-optimizer/blob/main/docs/adding-components.md) 중 필요한 역할만 확인하세요.

## 1. 담당 템플릿 복사

| 담당 | 시작 파일 | 첫 확인 지점 |
|---|---|---|
| Optimizer | [optimizer-template](https://github.com/wontaeJeong/agent-optimizer/tree/main/experiments/optimizer-template) | `optimize`, `context.propose`, train 평가 |
| Harness | [harness-template](https://github.com/wontaeJeong/agent-optimizer/tree/main/experiments/harness-template) | Agent/프로필/실험 연결과 `run` |
| Dataset | [dataset-template](https://github.com/wontaeJeong/agent-optimizer/tree/main/experiments/dataset-template) | 공개 과제 준비, 읽기 전용 진단, 분리 평가 |
| 외부 Agent | [customer-template](https://github.com/wontaeJeong/agent-optimizer/tree/main/experiments/customer-template) | 소스·실행 argv·editable·평가 연결 |

**복사 후:** 템플릿 내부의 `experiments/<원본 템플릿>/` 참조와 실험 이름을 실제 팀 경로로 변경합니다. `experiments/my-team/`은 **설명용 예시 경로**로, 복사·수정 전에는 존재하지 않습니다. 원본 stub은 구현 전 의도적으로 실패합니다.

## 2. 관련 계약 구현

공통 타입과 실제 메서드 선언은 [contracts.py](https://github.com/wontaeJeong/agent-optimizer/blob/main/src/agent_optimizer/contracts.py)에 있습니다. 아래 표는 **계약 요약**이며 실행용 Python 예제가 아닙니다.

| 역할 | 필요한 메서드 | 결과·주의점 |
|---|---|---|
| `Optimizer` | `optimize(context, seeds, config)` | `OptimizationResult`; `context.propose`로 editable 안의 텍스트만 제안 |
| `HarnessAdapter` | `run(request)` | `ExecutionResult`; `request.agent_dir`의 후보를 공개 `task_dir`에서 실행 |
| `Evaluator` | `evaluate(task, output_dir, timeout_seconds)` | `Evaluation`; Agent 자기보고 대신 실제 산출물 채점 |
| `DatasetProvider` | `describe()`, `prepare(cache, offline=False)`, `doctor(cache)` | 공개 과제·분리 평가 자산·출처를 준비하고 `doctor`는 읽기 전용 |

Optimizer의 `evaluate`/`evaluate_batch`와 `history()`는 baseline과 **자기 stage의 train**만 수정 근거로 사용합니다. 일부 방법의 내부 선택에는 validation **수치**가 쓰일 수 있지만 private 자료나 test 결과는 전달되지 않습니다. Harness는 argv 배열로 실행하며 실패·timeout을 숨기지 않습니다. 환경 오류의 `passed=None`, 미수집 사용량의 `None`, 부분 관측의 partial 표기를 유지하세요. [구조와 경계](/agent-optimizer/developer/overview/)에서 정보 흐름을 확인할 수 있습니다.

## 3. 팀 ID 등록

[registry.py](https://github.com/wontaeJeong/agent-optimizer/blob/main/src/agent_optimizer/registry.py)의 `PROJECT_COMPONENTS`에서 **기존 항목을 보존한 채** 해당 mapping에만 팀 항목을 추가합니다. 아래는 **추가 항목을 보여 주는 설명용 코드 조각**으로 그대로 붙여 넣어 실행하거나 전체 mapping을 덮어쓰는 예제가 아닙니다.

```python
"datasets": {"team_dataset": "experiments/my-team/provider.py:Provider"},
"evaluators": {"team_evaluator": "experiments/my-team/evaluator.py:Evaluator"},
"harnesses": {"team_harness": "experiments/my-team/adapter.py:Harness"},
"optimizers": {"team_optimizer": "experiments/my-team/optimizer.py:Optimizer"},
```

공유 helper는 `PROJECT_DEPENDENCIES`에 `"datasets/team_dataset": ["experiments/my-team/importer.py"]`처럼 기록합니다. 이는 파일 hash/재현 정보이지 Python 패키지 설치가 아닙니다. 한 실험 전용 파일 플러그인은 TOML의 `[plugins.*]`로 연결할 수 있습니다. CLI 선택지와 설치 entry point는 수정하지 않습니다.

`catalog list/show`는 등록 ID의 설명과 `ready`/`reason`을 **읽기 전용**으로 노출합니다. 소스 checkout에서는 `examples/*/source.toml` 또는 `agent.toml`의 Agent 설명·`supported_harnesses`, `examples/*/harness*.toml`의 프로필 ID·adapter/runtime도 읽습니다. 예를 들어 `model-rtl-agent`/`model-rtl-command`는 별도 연구 예제로 목록에 나오지만 wheel 설치·모델·도구 준비나 TUI **5번의 ACE 조합**과의 호환을 보장하지 않습니다. Harness adapter를 등록한 뒤 실제 실행 profile/argv와 Agent 지원 관계, Dataset provider와 별도 evaluator를 연결해야 합니다. 미지원 조합은 비활성 이유를 확인하고 고급 설정/기존 실험을 사용하세요. [프리셋과 직접 구성의 차이](/agent-optimizer/guides/experiment/#프리셋-조회와-직접-구성의-차이)를 참고하세요.

**다음 단계:** [검증 순서](/agent-optimizer/developer/validation/)에서 코어 fixture → 팀 파일·정적 계획 → 실제 실행의 증거를 구분해 확인하세요. 외부 Git Agent는 전체 commit SHA를 고정하고 원본·채점 기준·테스트와 editable 권한을 분리합니다.
