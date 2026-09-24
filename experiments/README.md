# 담당별 시작점

팀 구현은 **`experiments/<team>/`**에서 소유하고 Dataset/Harness/Optimizer/Evaluator ID를
`src/agent_optimizer/registry.py`의 `PROJECT_COMPONENTS`에 등록하면 CLI/TUI·doctor 목록에서 탐색할 수 있습니다.
프로젝트 루트에서 복사하고 선택한 README의 post-copy 경로를 바꾼 뒤 `plan`으로 배선을 확인하세요.
필요한 helper 경로는 `PROJECT_DEPENDENCIES`에 선언하고 CLI 선택지·entry-point 패키지 설치는 바꾸지 않습니다.

| 담당 | 복사할 템플릿 | 첫 완료 조건 |
|---|---|---|
| Optimizer | [optimizer-template](optimizer-template/README.md) | API-free 계약 테스트 → propose/evaluate 구현 → validation 선택 |
| Harness | [harness-template](harness-template/README.md) | Agent/프로필/등록 경로 연결 → 실제 CLI 실행·오류/사용량 검증 |
| Dataset | [dataset-template](dataset-template/README.md) | 공개 task/분할·private 평가 자료·검증된 출처/해시·평가기 연결 |
| 외부 Agent | [customer-template](customer-template/README.md) | 고정 소스·editable·명령·과제·평가 연결 → 작은 baseline |

먼저 [코어 개발환경](../README.md#개발환경-빠른-시작)을 준비하세요.
공통 규칙은 [확장 계약](../docs/adding-components.md), 선택적 모델 예제는
[simple-feedback](simple-feedback/README.md)입니다. 템플릿 stub은 구현 전 명시적으로 실패합니다.
