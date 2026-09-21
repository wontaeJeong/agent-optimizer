# Harness 추가

Claude Code, Codex, 자체 CLI 등은 같은 `RunRequest -> ExecutionResult` 계약으로 연결합니다.
이 템플릿은 연결 지점이며 실제 CLI 지원 구현이 아닙니다. OpenAI 호환 endpoint가 있다고 해서
모든 Harness의 인증·모델 프로토콜까지 호환되는 것은 아닙니다.

1. `adapter.py`를 팀 디렉터리에 복사하고 `Harness.run`을 구현합니다. 단순 CLI는 기존
   `CommandHarness`를 재사용하고 trace parsing이 필요할 때만 확장합니다.
2. experiment에 `[plugins.harnesses] team_harness = "experiments/my-team/adapter.py:Harness"`를
   등록합니다. helper 파일은 `[plugin_dependencies]`의 `"harnesses/team_harness"`에 선언합니다.
3. Harness TOML에 `adapter = "team_harness"`, runtime과 필요한 환경변수 **이름**을 지정합니다.
   Agent manifest의 `supported_harnesses`에도 등록한 이름을 추가합니다.
4. 아래 계약을 fixture로 검증하고 실제 CLI/모델 smoke를 수행한 뒤 지원 상태를 갱신합니다.

| 연결 항목 | 계약 |
|---|---|
| 입력 | `request.prompt`, 후보 `agent_dir`, 공개 `task_dir`만 사용 |
| 실행 | argv 배열, `process.execute`, timeout과 종료/중단 처리 |
| 인증·모델 | CLI별 protocol/auth를 확인하고 환경 또는 credential store 사용 |
| 산출물 | `task_dir`에 실제 결과를 작성; private 평가 데이터 접근 금지 |
| 오류 | CLI 오류를 성공으로 처리하지 않음; 환경 문제는 `infrastructure_error` |
| 지표 | 관측 값만 기록; 전체 사용량이 아니면 partial 이름 사용, 누락은 None |

ACE 예제의 `adapter.py:with_ace_guidance`는 Harness 독립적인 prompt 준비 함수입니다.
필요하면 같은 지침을 새 adapter에 적용하고 helper fingerprint를 선언하세요.
Optimizer는 Harness별 구현을 호출하지 않고 항상 공통 context를 사용합니다.
