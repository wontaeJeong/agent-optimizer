# Harness 담당: 복사 가능한 전체 배선

`adapter.py:Harness`는 `run(RunRequest) -> ExecutionResult`의 **미구현 stub**입니다.
Agent/프로필/실험 TOML과 기존 public fixture를 함께 연결해 두었습니다. `plan`은 등록 검사만 통과하며
구현 전 `run`은 **exit 2 / Team Harness is not implemented**, summary는 error입니다.

프로젝트 루트에서:

```bash
cp -R experiments/harness-template experiments/my-team
# 아래 세 참조를 편집한 뒤:
PYTHONPATH=src python3 -m agent_optimizer plan experiments/my-team/experiment.toml
PYTHONPATH=src python3 -m unittest discover -s tests -p test_plugin_contracts.py -v
```

## 복사 후 바꿀 것

1. `experiment.toml`의 `agents`, `harnesses`, `[plugins.harnesses].team_harness` 세 경로에서
   `experiments/harness-template/`를 **`experiments/my-team/`**으로 바꿉니다. 실험 name도 지정합니다.
2. 같은 깊이의 복사라면 `project_root="../.."`와 Agent의
   `source.path="../../examples/minimal/agents/solo"`는 유지합니다. benchmark/evaluator도 기존 fixture입니다.
3. 등록 이름을 바꾸면 `harness.toml`의 `adapter`와 `agent.toml`의 `supported_harnesses`를 함께 바꿉니다.
   프로필 `id`는 결과 식별자이고 adapter 등록 이름과 다릅니다.
4. 복사한 `adapter.py`를 구현합니다. helper는 `[plugin_dependencies]`의
   `"harnesses/team_harness" = ["experiments/my-team/helper.py"]`로 기록합니다.

회귀 테스트는 실제 디렉터리를 복사하고 **복사본만** synthetic `FixtureHarness` 기반 구현으로 바꿉니다.
`plan` 후 실제 fixture subprocess/evaluator를 실행하여 completed, `team-copy` 지표, 복사본 파일 hash와
원본 보존을 확인합니다. 임시 결과는 삭제됩니다. 원본 stub의 명시적 실패도 별도로 검사합니다.
이는 실제 외부 CLI/모델 지원 증거가 아닙니다.

## 구현·실행 계약

- `request.agent_dir`는 후보, `task_dir`는 공개 입력/산출물, `prompt`는 실행 지침입니다.
  private 평가 자산에 접근하지 않습니다. 실제 산출물을 `task_dir`에 남깁니다.
- 단순 CLI는 기존 `CommandHarness`와 argv를 먼저 사용하세요. `process.execute`로 timeout/종료를
  처리하고 shell interpolation에 의존하지 않습니다. CLI별 인증/모델은 환경 또는 credential store로 전달합니다.
- 관측된 지표만 `ExecutionResult.metrics`에 반환합니다. 전체가 아니면 partial 이름, 미수집은 None입니다.
  CLI/환경 실패를 성공이나 합성 결과로 대체하지 않습니다.
- 구현 후 `PYTHONPATH=src python3 -m agent_optimizer run experiments/my-team/experiment.toml`로
  작은 실행을 검증하세요. 실제 CLI로 바꾸면 해당 Agent 소스·명령·runtime·평가 연결도 함께 교체합니다.

Claude Code/Codex 등은 별도 어댑터 구현이 필요합니다. 공통 계약은
[adding-components](../../docs/adding-components.md#harness)와 `src/agent_optimizer/contracts.py`를 따릅니다.
