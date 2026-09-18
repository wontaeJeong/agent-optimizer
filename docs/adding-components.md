# Agent / Harness / Optimizer / 평가 연결

`experiments/customer-template/`를 복사해서 시작하세요. 코어 수정 없이 TOML에서 플러그인을 등록합니다.

```toml
[plugins.optimizers]
my_optimizer = "experiments/my-team/optimizer.py:Optimizer"
[plugins.harnesses]
my_harness = "experiments/my-team/adapter.py:Harness"
[plugins.evaluators]
my_evaluator = "experiments/my-team/evaluator.py:Evaluator"
```

각 파일은 독립 모듈로 로딩합니다. 파일 간 import가 많아지면 팀 코드를 Python package로 설치하고
`agent_optimizer.optimizers`, `.harnesses`, `.evaluators` entry point를 사용하세요.
미구현 슬롯을 구현해도 자동 활성화되지 않습니다. 위 등록으로 명시적으로 연결합니다.
`plan`도 플러그인 Python 코드를 로딩하므로 신뢰한 파일만 사용하세요.

## Agent 소스

Agent manifest schema_version은 2, experiment/benchmark schema_version은 1입니다.
`source.path`는 Agent manifest 기준, experiment의 agents/harnesses/benchmark/plugins 경로는
`project_root` 기준입니다. 모든 CLI 예제는 프로젝트 루트 실행을 전제로 합니다.

```toml
schema_version = 2
id = "team-agent"
description = "Team-owned agent"
supported_harnesses = ["command"]
prompt_file = "prompts/system.md"
editable = ["prompts/**", "src/**", "workflow/**"]
[source]
kind = "git"
url = "ssh://git@example.org/team/agent.git"
revision = "<실제 전체 commit SHA>"
```

로컬 checkout은 `[source] kind="local", path="/path/to/agent"`로 연결합니다.
`include`/`exclude`로 필요한 파일만 가져올 수 있습니다. Git submodule/symlink/LFS는 자동 처리하지 않습니다.
이미 준비한 regular-file 소스를 local로 연결하세요. 설치 의존성이 필요하면 Harness 이미지에 준비하거나
manifest `build` argv로 trial 환경 내에서 실행합니다.

## Harness

`run(request: RunRequest) -> ExecutionResult`. `request.agent_dir`는 후보 Agent,
`request.task_dir`는 공개 입력/산출물입니다. 평가 자산은 전달하지 않습니다.
command 어댑터 argv placeholder: `{python}`, `{agent_dir}`, `{task_dir}`, `{request_file}`, `{seed}`.
작업 디렉터리는 trial workspace. Docker 내부 경로로 자동 변환합니다.
미등록 placeholder는 치환하지 않으므로 자체 shell interpolation을 기대하지 마세요.
OpenCode 이외 CLI도 command wrapper로 먼저 연결한 후 필요한 trace parsing을 추가할 수 있습니다.

## Optimizer

`optimize(context, seeds, config) -> OptimizationResult`.
- `context.propose(parent, {"relative/file": "new content"}, producer)`로 후보 생성.
- `context.evaluate(candidate)`는 train split만 사용. train이 없는 실험에서 호출하면 실패.
- `context.history()`는 train 기록만 반환.
- `context.record_usage(input_tokens, output_tokens, cost_usd)`는 Optimizer 자체 사용량 기록.
- `OptimizationResult(candidates=[...], checkpoint={...})` 반환. runner가 validation 평가/선택.

stage `inputs`로 이전 stage를 조합합니다. stage 순서는 TOML 순서이며 forward reference/순환은 금지합니다.
`when`으로 validation metric에 따른 stage 실행 조건을 지정할 수 있습니다.
현재 후보 변경은 텍스트 파일 생성/교체이며 삭제·바이너리 패치 API는 없습니다.

## Evaluator

constructor(config) 후 `evaluate(task, output_dir, timeout_seconds) -> Evaluation`.
성공/실패는 실제 테스트 근거로 판단합니다. 환경 오류는 `infrastructure_error`, passed=None으로 반환합니다.
Agent가 작성한 success.json 같은 자기보고만으로 성공 판정하지 않습니다.
추가 지표는 Evaluation.metrics에 넣고 objective.metrics의 source로 참조합니다.

## 지표·예산

objective: lexicographic / weighted / pareto. metric: maximize/minimize, mean/sum/max/p95.
constraints와 keep으로 후보 선택을 제어합니다. 비용/시간 조건은 **평가 후 선택 제약**이며 실행 중 비용
차단 기능이 아닙니다. 실행 budget은 max_trials, max_wall_time_seconds, trial_timeout_seconds만 지원합니다.
`rerank`는 이미 집계된 validation 결과의 우선순위/가중치만 바꿉니다. 새 지표/집계 변경은 재실행 필요.
