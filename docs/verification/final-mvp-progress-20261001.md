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
- A: 완료. b665efe..3cb8424, 리뷰 중요 3건·경미 1건 수정 후 재리뷰 승인.
- B: 완료. 520f4a7..7c7aeed, 리뷰 중요 5건 수정 후 재리뷰 승인.
- C: 완료. 4fd8af1..d405b87, 리뷰 중요 2건·경미 2건 수정 후 재리뷰 승인. live는 not_run.
- D: 완료. cb63f69..7021723, 리뷰 중요 2건·경미 1건 수정 후 재리뷰 승인.
- E: 완료. 4c54c05, 독립 리뷰 중요 finding 없음. 리뷰 문서는 E worktree에 보존.
- 통합: ff0d6dc까지 충돌 없이 cherry-pick 완료. 각 작업 보고서에 검증 명령·결과 기록.
- F: 완료. be41046까지 독립 리뷰 수정 승인·최종 계약 인계 완료. native 정책은 examples 소유 thin hook이며 관련 211개 검증은 final-mvp-f-20261001.md §6~§8에 기록.
- G: 완료. 28b5367까지 독립 리뷰 수정·재리뷰 승인. 전체 1155개 중 실행 1075개 통과·기존 skip 80개, lint·실제 wheel build/install smoke 통과. native live는 not_run. 최종 근거는 final-mvp-g-20261001.md §7.
- H: 완료. 51b905d까지 독립 리뷰/fix 승인 인계를 소비했다. 실제 help·fixture·History/HTTP·계약·lint·Starlight build/link·캡처 및 prepare/doctor 책임 정정은 final-mvp-h-20261001.md의 최신 append가 정본이다. native live not_run.
- I: 완료. 17d3501에서 일반 prepare 오분기·native source.subdir 및 make 테스트 환경 격리를 보완했다. 실제 make test 1157개 중 실행 1077 통과·기존 skip 80, lint/demo·새 wheel install·source/wheel CLI/PTY·TUI·실제 HTTP/종료·local/Git command·사이트 build/link 검증. R01~R30 완료 29·부분 1(R16)·차단 0, native live not_run. exact 명령·경로·미검증·최종 문서 커밋 관계는 [I 보고서](final-mvp-i-20261001.md)에 기록한다. 하위 에이전트·push/PR 없음.
- 최종 whole-branch 리뷰/fix: cb7fbdf 대상 [독립 리뷰](final-mvp-final-review-20261001.md)는 Critical 0·Important 0·Minor 2. 단일 후속 wave에서 M1 필수 name 사용법을 실제 실행하고 M2 plan startup/main/callback import를 기존 no-bytecode 보호에 연결했다. no-`-B`/no-env actual disk regression·이전 값 복구·scope 밖 실제 pyc negative control, source-free wheel module/console smoke·covering 53개·실제 make 1160개 중 실행 1080 통과·기존 skip 80·lint를 완료했다. 최신 증거는 [I §8](final-mvp-i-20261001.md). R14 사용자 호출 증거 보완·R16 live 부분 유지, 하위 에이전트·push/PR 없음. 새 독립 재리뷰 승인을 대신 주장하지 않는다.
- 최종 독립 재리뷰: e42a06f의 단일 수정 wave에서 M1·M2 모두 해소, 새 Critical/Important/Minor 0건으로 승인받았다. 총괄은 같은 코드에서 아래 명령을 직접 실행해 `Ran 1160 tests in 173.140s`, `OK (skipped=80)` 및 lint 통과를 확인했다. 원본 로그는 `/Users/wt.jeong/.local/share/opencode/tool-output/tool_0f57b7670001aAPlZ0RZyL602t`다. 기본 디렉터리는 main이며 사용자 변경·다른 worktree를 보존했고 통합 worktree는 clean이었다. 자동 push 금지에 따라 브랜치·worktree를 로컬 보존한다.

```bash
env -i PATH=/Users/wt.jeong/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-i/home AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-i/controller-final-home TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-i/tmp PYTHONDONTWRITEBYTECODE=1 AGENT_OPT_CORE_PYTHON=/Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never make test
env AGENT_OPT_CORE_PYTHON=/Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python PYTHONDONTWRITEBYTECODE=1 make lint
git diff --check origin/main...HEAD
git status --short --branch
git worktree list
```
