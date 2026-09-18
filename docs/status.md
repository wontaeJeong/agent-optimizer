# 구현·검증 상태 (v0.3.0)

| 항목 | 상태 |
|---|---|
| 범용 코어/외부 소스/복수 Agent/실험 단계/지표 | 구현, 오프라인 테스트 |
| baseline / file_variants | 구현, 합성 데모 검증 |
| GEPA / Meta-Harness / Ecdysis | 팀원 구현 슬롯, 호출 시 미지원 오류 |
| command / OpenCode / Docker 프로세스 | 구현, 계약·timeout 테스트; 실제 OpenCode/Docker 미실행 |
| Claude Code / Codex / OpenAgent | 확장 규약, 전용 어댑터 미구현 |
| 작은 RTL 예제/Icarus | 구현, 모의 계약 테스트; 실제 Icarus 미설치로 smoke 생략 |
| ACE OpenCode skill / CVDP Docker | 예제 연결 코드·설치·과제 변환 포함; 실환경 통합 미검증 |
| ACE 원본 native runner | 자동 최적화 경로로 연결하지 않음, upstream 링크 제공 |
| CVDP 전체 문제 유형 | 미지원. 초기 cid003 RTL 기능 검증 문제만 허용 |
| CVDP 상용 의존성 | 제외 보고서 기록. 공식 OSS 이미지 외 환경은 초기 예제에서 거부 |
| 토큰/비용 | 미수집은 null; OpenCode root 이벤트 partial 지표만 별도 제공 |
| 엄격한 비용/호출 상한, 병렬 실행, resume | 미구현 |
| test 평가 | 일반 코어 지원; ACE 한 문제 smoke는 validation-only |

실제 모델 성능 개선이나 ACE 논문 결과 재현을 주장하지 않습니다.
ACE 역할 코드의 수정 효과는 선택한 실행 프로필이 실제 그 코드를 사용하는지 확인해야 합니다.
현재 스킬 프로필은 OpenCode가 참조·활용하는 방식이며 모든 Python 역할 코드 실행을 강제하지 않습니다.
API 키·Docker daemon·모델 endpoint가 준비된 개인 서버에서 첫 실환경 검증을 수행하세요.
