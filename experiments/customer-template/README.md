# 외부 Agent 담당

프로젝트 루트에서 `cp -R experiments/customer-template experiments/my-team`으로 시작합니다.
실제 Agent 소스는 별도 repo이며 코어에 고객별 분기를 추가하지 않습니다.

| 파일 | 복사 후 반드시 바꿀 참조 |
|---|---|
| `experiment.toml` | `agents`, `harnesses`, `[plugins.evaluators].customer`의 `experiments/customer-template/`를 `experiments/my-team/`으로 변경. name과 benchmark를 팀 과제 JSON으로 지정 |
| `agent.toml` | id, source, prompt_file, editable. local path는 **이 manifest 기준**; Git은 URL과 전체 고정 commit revision 지정 |
| `harness.toml` | command argv, runtime, id. adapter를 바꾸면 Agent supported_harnesses도 일치시킴 |
| `evaluator.py` | 실제 평가 구현. 공개 입력과 private 평가 자산을 분리하고 환경 오류/미수집 지표를 정직하게 반환 |

같은 깊이에서 `project_root="../.."`는 유지합니다. experiment 내부 파일 참조는 project_root 기준입니다.
등록 이름 customer를 바꾸면 evaluator도 함께 바꾸세요. helper hash는
`[plugin_dependencies] "evaluators/customer" = ["experiments/my-team/helper.py"]`로 선언합니다.

위 입력을 준비한 뒤:

```bash
PYTHONPATH=src python3 -m agent_optimizer plan experiments/my-team/experiment.toml
PYTHONPATH=src python3 -m agent_optimizer run experiments/my-team/experiment.toml
```

그대로인 템플릿은 의도적으로 존재하지 않는 소스/benchmark와 미구현 evaluator를 사용하므로 실패합니다.
API-free 시작점은 [minimal](../../examples/minimal/experiment.toml); 새 CLI 배선은
[Harness 템플릿](../harness-template/README.md)입니다. 작은 baseline부터 확인한 뒤 Optimizer를 연결하세요.
소스가 수정 불가라면 허용된 프롬프트·설정 bundle만 대상으로 삼습니다. 소스/평가 수정 권한과
숨김 런타임 자산·인증 제외 규칙은 [공통 계약](../../docs/adding-components.md#agent-소스)을 따릅니다.
