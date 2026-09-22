# 담당별 시작점

팀 코드는 **`experiments/<team>/` 파일 플러그인**으로 소유합니다. 프로젝트 루트에서 복사하고,
선택한 README의 post-copy 경로를 바꾼 뒤 `plan`으로 배선을 확인하세요. registry 수정이나
entry-point 패키지 설치는 필요 없습니다.

| 담당 | 복사할 템플릿 | 첫 완료 조건 |
|---|---|---|
| Optimizer | [optimizer-template](optimizer-template/README.md) | API-free 계약 테스트 → propose/evaluate 구현 → validation 선택 |
| Harness | [harness-template](harness-template/README.md) | Agent/프로필/등록 경로 연결 → 실제 CLI 실행·오류/사용량 검증 |
| 외부 Agent | [customer-template](customer-template/README.md) | 고정 소스·editable·명령·과제·평가 연결 → 작은 baseline |

먼저 [코어 개발환경](../README.md#개발환경-빠른-시작)을 준비하세요.
공통 규칙은 [확장 계약](../docs/adding-components.md), 선택적 모델 예제는
[simple-feedback](simple-feedback/README.md)입니다. 템플릿 stub은 구현 전 명시적으로 실패합니다.
