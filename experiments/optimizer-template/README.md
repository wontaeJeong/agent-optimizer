# Optimizer 담당: API 없이 계약부터

준비된 코어 환경에서 프로젝트 루트 기준으로 실행하세요:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_plugin_contracts.py -v
PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml
```

첫 명령은 **실제 runner를 쓰는 API-free 계약 회귀**입니다. train 피드백·원본 보존·usage·선택 후 test,
복수 Agent의 독립 파일 Optimizer 비교를 검사합니다. 테스트의 임시 결과는 종료 시 삭제됩니다.
두 번째 명령은 두 합성 Agent·단일 repair stage·**7 trial(solo 4/team 3)** 데모이며
`runs/<run-id>/{report.md,summary.json,events.jsonl}`을 보존합니다. 모델 성능 증거가 아닙니다.

## 복사 후 바꿀 것

```bash
cp -R experiments/optimizer-template experiments/my-team
# 아래 등록 경로를 편집한 뒤:
PYTHONPATH=src .venv/bin/python -m agent_optimizer plan experiments/my-team/experiment.toml
```

- `experiment.toml`: `[plugins.optimizers].team_optimizer`를
  `experiments/my-team/optimizer.py:Optimizer`로 변경. 실험 `name`도 팀 이름으로 지정합니다.
- 등록 이름을 바꾸면 `stages.optimizer`도 같이 변경합니다. `project_root="../.."`는 같은 깊이에서 유지합니다.
- 초기 `agents`, `harnesses`, `benchmark`, `text_fixture`는 기존 public fixture를 그대로 사용합니다.
  실제 대상으로 전환할 때만 교체하세요. stage를 더하면 모두 baseline에서 독립 실행됩니다.
- helper를 쓰면 `[plugin_dependencies]`의 `"optimizers/team_optimizer"`에
  `["experiments/my-team/helpers.py"]`를 선언합니다. hash 기록용이며 import 경로 설정 기능은 아닙니다.

`plan`의 valid/integrations_ready는 설정·등록 검사입니다. 그대로인 stub을 `run`하면
**exit 2 / UnavailableError**, summary의 status=error이고 선택/test는 없습니다.
예약 연구 슬롯은 없습니다. 원하는 팀 이름으로 파일을 명시적으로 등록하세요.

## 최소 propose/evaluate 구현

복사한 `optimizer.py`의 클래스를 아래로 바꾸면 기존 fixture로 실행할 수 있습니다:

```python
from agent_optimizer.contracts import OptimizationResult

class Optimizer:
    def optimize(self, context, seeds, config):
        baseline, = seeds
        context.evaluate(baseline)  # train only; cached baseline may be shared
        candidate = context.propose(
            baseline, {"configs/strategy.json": '{"repair": true}'}, "my-team")
        context.evaluate(candidate)
        return OptimizationResult([candidate], {"iteration": 1})
```

```bash
PYTHONPATH=src .venv/bin/python -m agent_optimizer run experiments/my-team/experiment.toml
```

`context.history()`는 baseline과 **자기 stage의 train**만 반환합니다. validation/test 선택은 runner가
소유하며 기본 최종 비교는 모든 stage winner입니다. 원본/스냅샷 직접 수정 대신 `propose`를 사용하세요.
모델을 호출하는 구현은 호출마다 `record_usage(input_tokens, output_tokens, cost_usd)`를 사용합니다.
미수집은 `None`; 기록은 Agent/Harness/stage/Optimizer 식별자를 포함하며 checkpoint는 resume가 아닙니다.
계약 상세는 [adding-components](../../docs/adding-components.md#optimizer), 선택적 모델 예제는
[simple-feedback](../simple-feedback/README.md). 연구 구현 채택 시에만 [출처](../../docs/SOURCES.md)를 대조합니다.
