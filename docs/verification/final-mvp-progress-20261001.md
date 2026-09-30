# 최종 MVP 실행 기록 — 계획: agent-optimizer-final-prompts-20261001/00_README.md

## 지침 대조 및 결정

- 기본 저장소 main과 사용자 .gitignore·zip을 보존한다. 동일 작업용 깨끗한 feat/final-mvp-20261001 worktree를 재사용한다.
- 작업지시의 자동 push 금지를 적용한다. 검증된 작업의 로컬 커밋·통합만 수행하고 원격 push·PR은 하지 않는다.
- 결정: P0의 상대 AGENT_OPT_HOME 허용 제안은 A의 명시 요구와 충돌하므로 상대값을 configuration error로 거부한다. 잘못 판단했다면 상대 환경 경로 사용자에 대한 정책 재조정이 필요하다.
- 결정: A~E 병렬은 사용자 실행지시가 스킬의 순차 구현 기본값보다 우선한다. 독립 worktree와 파일 소유권으로 충돌을 방지한다. 잘못 판단했다면 통합 시 재작업이 필요하다.
- .venv 경로 의존 baseline 오류는 G에서 실제 원인을 수정한다. 새로운 기능 실패와 구별하고 skip으로 숨기지 않는다.

## 계획 자체 및 공유 인터페이스 대조

| 작업/연결 | 생산·소비 계약 및 자체 요구 대조 | 결과 |
|---|---|---|
| P0 | 기존 기반 재사용·현재 변경 보호·baseline | 문서 완료, 경로 환경 오류 기록 |
| A | 순수 resolver·명시 output·legacy·lifecycle | 상대 Home 허용 P0 제안을 거부하도록 확정 |
| B | stable ChoiceRow·평문 Endpoint·credential 거부 | 표시와 생성 함수 소유권 분리 |
| C | native upstream loop·trusted 평가·세 역할·CID | live 미실행과 fixture 증거 구별 필수 |
| D | normalized v3·optional native payload | raw summary/events를 변경하지 않음 |
| E | loopback·HTML allowlist·close | P0의 report_path 입력 signature 사용 |
| A↔F | app_paths/history/config_root → CLI/TUI writer | F가 생성·조회 소비; 병렬 CLI 수정 없음 |
| A↔C | source/config 경로 ↔ native profile | 후보 snapshot과 private 경계 보존 |
| B↔F | ChoiceRow/model/action → 생성·실행 연결 | F는 B 통합 뒤 같은 파일 수정 |
| C↔D↔F | native sidecar → runner event → report | C는 sidecar, F producer, D 소비 |
| D↔E↔F | self-contained HTML → 서버 → 열람 | HTML만 공개; raw evidence 미공개 |
| F | A~E 완료 뒤 제품 연결 | 공통 registry/CLI/TUI 소유 |
| F↔G | 신규 오류/locale 요구 → 진단·공유 파일 | G는 F 완료 뒤 수행 |
| G | 개발환경·offline/CA/proxy·baseline | mock/live 분리 및 환경 경로 오류 해소 |
| H | 실제 help/구현 → 문서 | 과거 native 보류 결정만 갱신 |
| I | 전체 통합·보안·wheel·E2E | 발견 결함 최소 수정; 미검증 명시 |

## 진행

- P0: 완료. final-mvp-p0-20261001.md에 정확한 baseline·공통 계약·R01~R30 기록.
- A~E: 전용 worktree 생성 완료. 독립 구현·검증 시작.
- F/G/H/I: 대기.
