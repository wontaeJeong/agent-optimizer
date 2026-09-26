# Simple feedback Optimizer

첫 팀 구현은 [API-free 계약 회귀와 최소 propose/evaluate](../optimizer-template/README.md)부터 시작하세요.
이 예제는 **모델 설정 후 선택적으로** 실행합니다. 테스트 임시 결과와 `runs/`의 지속 데모 보고서를 구별하세요.

작은 LLM 피드백 예제이며 Meta-Harness/GEPA 구현이 아닙니다. seed의 train 평가 → 지정 파일 수정 →
train 재평가를 기본 3회 수행합니다. 모든 후보와 seed를 runner에 반환하여 validation으로 선택합니다.
test는 선택 후에만 실행합니다. 점수 개선은 보장하지 않습니다.

```toml
[plugins.optimizers]
simple_feedback = "experiments/simple-feedback/optimizer.py:Optimizer"
[plugin_dependencies]
"optimizers/simple_feedback" = ["src/agent_optimizer/models.py"]
[[stages]]
id = "feedback"
optimizer = "simple_feedback"
inputs = ["baseline"]
[stages.config]
file = "skills/ace-rtl/references/role-guidance.md"
iterations = 3
request_timeout_seconds = 60
```

`AGENT_OPT_MODEL_BASE_URL`(`/chat/completions`를 제외한 기본 URL),
`AGENT_OPT_MODEL_API_KEY`, 선택적 `AGENT_OPT_MODEL_ID`(기본 `glm5.3-flash`)를 환경에 설정합니다.
설정 파일에 인증 값을 넣지 마세요.
모델 응답은 `{"content":"전체 파일 내용"}`이어야 합니다. 잘못된 응답·환경 실패는 중단합니다.
미수집 usage는 null입니다. 이번 예제는 seed 하나·파일 하나·1~20회 반복을 지원합니다.

## 팀 복사

`cp -R experiments/simple-feedback experiments/my-team` 후 위 TOML 블록을 팀 experiment에 넣습니다.
`[plugins.optimizers]`의 파일 경로를 `experiments/my-team/optimizer.py:Optimizer`로 바꾸세요.
등록 이름을 바꾸면 `stages.optimizer`와 `plugin_dependencies` 키도 함께 바꿉니다.
`src/agent_optimizer/models.py` helper 경로는 유지하며 `stages.config.file`은 대상 Agent의 editable 파일로
지정합니다. 별도 experiment가 필요하면 [Optimizer 템플릿](../optimizer-template/experiment.toml)의
fixture 배선을 사용하고 file을 `configs/strategy.json` 등 대상에 맞게 설정합니다.
`plan`으로 등록 검사 후, 준비한 모델로 `run`을 실행하세요. registry 수정/설치 entry point는 필요 없습니다.

여러 stage를 등록해도 각각 baseline에서 시작합니다. 기본 최종 비교는 모든 stage winner입니다.
`context.evaluate/history`는 train 전용, `propose`는 editable 스냅샷 전용입니다.
`record_usage(None, None, None)`도 호출 사실을 보존합니다. 런타임 context의 선택적
`remaining_seconds()`로 외부 요청 timeout을 남은 예산 이하로 줄일 수 있습니다.
