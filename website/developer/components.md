# 컴포넌트 연결

**역할에 맞는 템플릿 하나를 골라** `experiments/<team>/`으로 복사합니다. 팀 구현은 공통 계약으로 Runner와 연결되며 알고리즘끼리 직접 호출하지 않습니다.

| 담당 | 시작 파일 | 먼저 확인할 것 |
|---|---|---|
| Optimizer | `experiments/optimizer-template/` | `optimize`, `context.propose`와 train 평가 |
| Harness | `experiments/harness-template/` | Agent/프로필/실험 배선과 `run` |
| Dataset | `experiments/dataset-template/` | 공개 과제 준비·읽기 전용 진단·별도 Evaluator |
| 외부 Agent | `experiments/customer-template/` | 소스/실행 argv/editable/평가 연결 |

복사 후 템플릿 내부의 `experiments/<원본 템플릿>/` 참조와 실험 이름을 팀 경로로 바꾸세요. 그대로인 템플릿 stub은 구현 전 **명시적으로 실패**하도록 설계되어 있습니다.

## 계약을 구현합니다

`src/agent_optimizer/contracts.py`에서 사용하는 최소 메서드는 다음과 같습니다.

```python
class Optimizer:
    def optimize(self, context, seeds, config):
        # OptimizationResult(candidates, checkpoint)를 반환
        ...

class Harness:
    def run(self, request):
        # ExecutionResult를 반환
        ...

class Evaluator:
    def evaluate(self, task, output_dir, timeout_seconds):
        # Evaluation을 반환
        ...

class Provider:
    def describe(self): ...
    def prepare(self, cache, *, offline=False): ...
    def doctor(self, cache): ...  # 읽기 전용
```

- Optimizer는 `context.propose(parent, {"configs/strategy.json": "..."}, producer)`로 **editable 안의 텍스트만** 제안합니다. `evaluate`/`evaluate_batch`는 train용이며 `history()`에는 자기 stage의 train만 들어갑니다. validation 수치 선택과 최종 test 실행은 Runner의 경계를 따릅니다.
- Harness의 `request.agent_dir`는 후보 Agent, `task_dir`는 공개 입력과 산출물입니다. 셸을 통한 명령 조합 대신 argv 배열을 사용하고 실행 실패/timeout을 그대로 반환하세요.
- Evaluator는 Agent 자기보고가 아닌 실제 산출물을 판정합니다. 환경 오류에는 `passed=None`, 미수집 사용량에는 `None`을 사용하며 일부만 관측한 사용량은 partial로 표기합니다.
- Dataset provider는 공개 과제와 채점 자산을 분리하고, `prepare`의 출처·버전·해시와 등록 Evaluator ID를 연결합니다. `doctor`는 다운로드/설치 없이 준비 상태만 읽습니다.

## 팀 ID를 등록합니다

`src/agent_optimizer/registry.py`의 **기존 항목은 유지**하면서 `PROJECT_COMPONENTS`의 해당 mapping에 팀 ID를 추가합니다:

```python
"datasets": {"team_dataset": "experiments/my-team/provider.py:Provider"},
"evaluators": {"team_evaluator": "experiments/my-team/evaluator.py:Evaluator"},
"harnesses": {"team_harness": "experiments/my-team/adapter.py:Harness"},
"optimizers": {"team_optimizer": "experiments/my-team/optimizer.py:Optimizer"},
```

이 줄들은 각 mapping에 **추가할 예시 항목**이지 `PROJECT_COMPONENTS` 전체를 대체하는 코드가 아닙니다. 공유 helper는 `PROJECT_DEPENDENCIES`에 `"datasets/team_dataset": ["experiments/my-team/importer.py"]`처럼 선언합니다. 이는 재현용 파일 hash 기록이며 Python 패키지 설치를 대신하지 않습니다. 한 실험에서만 쓰는 플러그인은 실험 TOML의 `[plugins.*]` 파일 참조를 사용할 수 있습니다. CLI 선택지나 설치 entry point는 수정하지 않습니다.

소스가 외부 Git이면 전체 commit SHA를 고정하고, 원본·평가 기준·테스트와 실제 editable 권한을 구분하세요. 시작이 됐다면 [검증 순서](validation.md)로 배선을 확인합니다.
