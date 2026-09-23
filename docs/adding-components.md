# 담당별 확장 계약

먼저 [팀 템플릿 선택](../experiments/README.md) 후 필요한 절만 읽으세요.
팀 소유 파일은 `experiments/<team>/`, 공통 타입은 `src/agent_optimizer/contracts.py`입니다.
프로젝트 루트에서 CLI를 실행하며 registry 수정/설치 entry point 없이 명시적으로 등록합니다:

```toml
[plugins.optimizers]
team_optimizer = "experiments/my-team/optimizer.py:Optimizer"
[plugins.harnesses]
team_harness = "experiments/my-team/adapter.py:Harness"
[plugins.evaluators]
team_evaluator = "experiments/my-team/evaluator.py:Evaluator"
[plugins.datasets]
team_dataset = "experiments/my-team/provider.py:Provider"
```

필요한 종류만 등록하세요. `plan`도 Python 파일을 로딩하므로 신뢰한 코드만 사용합니다.
등록 성공은 실제 구현·외부 실행 성공이 아니며 stub은 구현 전 명시적으로 실패합니다.

## Dataset provider / 팀 확장 목록

[`experiments/dataset-template/`](../experiments/dataset-template/README.md)을 팀 폴더로 복사하여
`extensions.toml`에 팀 Dataset/Harness/Optimizer/Evaluator 파일을 명시적으로 등록합니다.
`load_extensions(path, project_root)`는 schema_version=1과 등록 파일·helper 경로를
플러그인 코드 실행 전에 검사합니다. 등록 경로는 기존 실험 설정과 동일하게 project_root 기준입니다.
Dataset provider의 `describe()`는 이름·과제 형태·평가기를 기술하고,
`prepare(cache, offline=False)`는 준비된 공개 benchmark 경로·평가기·출처/해시를 반환합니다.
private 채점 자료는 Agent workspace나 공개 과제 파일에 넣지 않습니다.

## Optimizer

**[API-free 회귀와 최소 propose/evaluate 예제](../experiments/optimizer-template/README.md)**부터 실행하세요.
테스트는 임시 결과를 정리하며 minimal demo는 `runs/<run-id>/` 보고서를 보존합니다.
선택적 모델 반복은 [simple-feedback](../experiments/simple-feedback/README.md)입니다.

`optimize(context, seeds, config) -> OptimizationResult`:

| API | 계약 |
|---|---|
| `propose(parent, {"relative/file": "content"}, producer)` | editable 안의 텍스트 생성/교체. 원본/후보 직접 수정 금지 |
| `evaluate(candidate)` | train 집계만 반환. train 없으면 오류. split 인자 없음 |
| `history()` | baseline과 자기 stage 후보의 train trial/feedback만 반환 |
| `record_usage(input_tokens, output_tokens, cost_usd)` | Optimizer 자체 관측값; 미수집 None. Agent/Harness/stage/optimizer 식별자와 즉시 저장 |
| `OptimizationResult(candidates, checkpoint)` | runner가 validation 평가/선택. checkpoint는 JSON 메타데이터이며 resume 아님 |

각 stage의 seed는 같은 그룹 baseline입니다. baseline train cache는 공유하되 다른 stage의 후보 이력은
공유하지 않습니다. 기본 최종 비교는 모든 stage winner이고 `final_stages`로 명시적 subset을 정할 수 있습니다.
`inputs`는 생략 또는 `["baseline"]`만 지원합니다. 후보/부모는 context가 발급한 정상 값이어야 하며
metadata·경로·hash·스냅샷 변조는 cache 반환 전에도 거부합니다. 삭제/바이너리 패치 API는 없습니다.
선택적 runtime `remaining_seconds()`로 외부 요청 timeout을 남은 예산에 맞출 수 있습니다.

## Harness

[전체 복사 배선](../experiments/harness-template/README.md)은 Agent/프로필/experiment와 public fixture를 포함합니다.
`run(request: RunRequest) -> ExecutionResult`: `agent_dir`는 후보, `task_dir`는 공개 입력/산출물입니다.
private 평가 자산은 전달하지 않습니다. 실제 산출물을 task_dir에 쓰고 관측 지표를 반환하세요.
단순 CLI는 command adapter의 argv를 사용합니다: `{python}`, `{agent_dir}`, `{task_dir}`, `{request_file}`, `{seed}`.
trial workspace가 cwd이며 Docker 경로는 변환합니다. 임의 shell interpolation은 지원하지 않습니다.
인증은 환경/credential store, timeout/프로세스 처리는 `process.execute` 계약을 따릅니다.
전체가 아닌 사용량은 partial 이름으로, 미수집은 None으로 반환하고 CLI 실패를 성공으로 대체하지 않습니다.

## Agent 소스

[외부 Agent 템플릿](../experiments/customer-template/README.md)의 placeholder를 실제 값으로 교체하세요.
Agent schema_version=2, experiment/benchmark=1입니다. Agent `source.path`는 **manifest 기준**,
experiment의 agents/harnesses/benchmark/plugins는 **project_root 기준**입니다.
`supported_harnesses`는 사용하는 프로필의 adapter 등록 이름과 맞춥니다.

```toml
[source]
kind = "git"
url = "ssh://git@example.org/team/agent.git"
revision = "<실제 전체 commit SHA>"
```

local은 `kind="local"`, `path="/path/to/agent"`를 사용합니다. prompt_file/editable은 소스 내부 경로입니다.
소스는 원본 수정 없이 확보합니다. submodule/symlink/LFS는 자동 처리하지 않으며 준비한 regular-file
소스를 연결해야 합니다. 의존성은 Harness 환경 또는 Agent build argv로 준비합니다.

`include`/`exclude`로 자산을 선택합니다. 기본 include `*`는 `.claude/.codex/.cursor/.opencode`를 제외합니다.
검토한 런타임 자산만 `include=["*", ".opencode/agents/**"]`처럼 리터럴 prefix로 허용하세요.
포괄 패턴(`**/*.md`, `.*/**`)은 제외를 해제하지 않으며 중첩 경로도 명시해야 합니다. exclude가 우선합니다.
Git/local 공통으로 아래는 명시적 include로도 가져올 수 없습니다:

- `.git`, `.venv`, `__pycache__`, `.pytest_cache`, `.vscode`, `.idea`, `*.pyc`.
- 모든 깊이의 `.env*` (`.env.example`, `.envrc` 포함).
- `auth.json`, `auth.jsonc`, `credentials`, `credentials.json`, `.credentials.json`, `.netrc`, `_netrc`, `.git-credentials`.

경로 기반 필터가 임의 파일의 비밀정보까지 탐지하지는 않습니다. 직접 검토하고 인증은 별도 전달하세요.
소스/산출물의 symlink·특수 파일은 내부를 가리키더라도 거부합니다.

## Evaluator와 선택

constructor(config), `evaluate(task, output_dir, timeout_seconds) -> Evaluation`.
실제 평가 근거로 passed를 정하며 Agent 자기보고는 성공 근거가 아닙니다.
환경 오류는 infrastructure_error/passed=None, 사용자 정의 지표는 `Evaluation.metrics`로 반환합니다.
objective.metrics의 source로 참조하고 direction=maximize/minimize, aggregate=mean/sum을 지정합니다.
선택은 **lexicographic, keep=1**만 지원합니다. validation으로 선택을 고정한 뒤 test를 실행합니다.
budget은 max_trials/max_wall_time_seconds/trial_timeout_seconds이며 비용·호출 차단 장치가 아닙니다.
invalid/partial split은 선택에서 제외합니다. [부분 결과](architecture.md#실행-종료와-부분-결과)를 참고하세요.

## 파일 의존성 기록

```toml
[plugin_dependencies]
"optimizers/team_optimizer" = ["experiments/my-team/helpers.py"]
```

키는 등록한 kind/name, 경로는 project_root 기준 regular file입니다. harnesses/evaluators도 같습니다.
누락·절대/이탈 경로·symlink·잘못된 선언은 plugin 로딩 전 거부합니다. manifest의 plugin_sha256에
직접 등록은 file.py:Symbol 키, helper는 상대 경로 키로 기록합니다. 중복 helper hash는 한 번 저장하고
관계는 experiment.plugin_dependencies에 남깁니다. hash 키 충돌은 거부합니다.
자동 import 탐색/설치 기능이 아니므로 helper와 외부 의존성·모델 버전은 담당자가 선언/고정해야 합니다.

고급 선택/조합·설치 entry point·연구 슬롯의 복원 정보는 [FUTURE](FUTURE.md)에 있습니다.
