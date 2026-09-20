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

### 소스 선택과 숨김 런타임 자산

기본 `include = ["*"]`는 `.claude/`, `.codex/`, `.cursor/`, `.opencode/` 개발자 디렉터리를
제외합니다. 검토한 Agent 런타임 파일이 필요하면 해당 디렉터리까지 리터럴 경로로 명시하세요.
예를 들어 아래 설정은 일반 소스와 `.opencode/agents/` 파일만 포함하고, 같은 디렉터리의
개인 플러그인 등은 기본 제외 상태로 둡니다.

```toml
[source]
kind = "local"
path = "/path/to/agent"
include = ["*", ".opencode/agents/**"]
```

`*`, `**/*.md`, `.*/**` 같은 포괄 패턴은 개발자 디렉터리 제외를 해제하지 않습니다.
중첩 디렉터리도 `vendor/.opencode/agents/**`처럼 해당 경로를 명시해야 하며, `exclude`가 항상 우선합니다.
이 선택 규칙은 로컬 소스와 고정 Git 소스에 동일하게 적용됩니다.

다음 항목은 명시적 `include`나 `exclude = []`로도 포함할 수 없습니다.

- `.git`, `.venv`, `__pycache__`, `.pytest_cache`, `.vscode`, `.idea` 경로 요소와 `*.pyc` 파일.
- 모든 깊이의 `.env*` 경로 요소 (`.env.example`, `.envrc` 포함).
- 알려진 인증 파일명: `auth.json`, `auth.jsonc`, `credentials`, `credentials.json`,
  `.credentials.json`, `.netrc`, `_netrc`, `.git-credentials`.

이는 경로/파일명 기반 제외이며 임의 파일에 담긴 비밀정보를 탐지하는 기능이 아닙니다.
포함할 런타임 자산은 직접 검토하고, 인증 값은 환경변수나 credential store로 전달하세요.
소스 루트와 선택한 경로의 symlink 및 특수 파일은 거부합니다. 산출물 수집도 실제 디렉터리 루트와
regular file만 허용하며, 내부를 가리키는 symlink도 허용하지 않습니다.

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
후보와 부모는 해당 그룹의 `CandidateStore`가 성공적으로 발급한 값이어야 합니다.
ID·Agent ID·경로·hash·부모·producer를 바꾸거나 스냅샷 파일을 직접 수정하면 거부됩니다.
검증은 캐시된 평가를 반환하기 전에도 수행합니다. 변경은 항상 `context.propose`로 새 후보를 만드세요.

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
