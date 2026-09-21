# Simple feedback Optimizer

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

`MODEL_ENDPOINT`(완전한 completion URL) 또는 `MODEL_BASE_URL` 중 하나, `MODEL_API_KEY`, 선택적
`MODEL_ID`(기본 `glm5.3-flash`)를 환경에 설정합니다. 설정 파일에 인증 값을 넣지 마세요.
모델 응답은 `{"content":"전체 파일 내용"}`이어야 합니다. 잘못된 응답·환경 실패는 중단합니다.
미수집 usage는 null입니다. 이번 예제는 seed 하나·파일 하나·1~20회 반복을 지원합니다.

팀 구현은 이 파일을 복사하거나 `../optimizer-template/`에서 시작해 다른 플러그인 이름으로
등록하면 됩니다. 코어 registry 수정이나 다른 알고리즘 호출은 필요하지 않습니다.
`context.evaluate/history`는 train 전용, `propose`는 editable 스냅샷 전용입니다.
`record_usage(None, None, None)`도 호출 사실을 보존합니다. 런타임 context의 선택적
`remaining_seconds()`로 외부 요청 timeout을 남은 예산 이하로 줄일 수 있습니다.
