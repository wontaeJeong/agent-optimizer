# 사람용 문서 사이트의 Starlight 전환 설계

## 목적과 범위

기존 MkDocs 사이트의 한국어 가이드 7쪽과 합성 결과 이미지를 보존하면서,
`website/`만 독립 Astro + Starlight 정적 사이트로 전환한다. 처음 온 개발자가
프로젝트 목적 → 구조 → 실행 흐름 → 구성 요소 → 사용법을 따라갈 수 있게 한다.
`docs/`는 연구·개발 근거로 남기고, 애플리케이션·실험·Optimizer 코드는 수정하지 않는다.
사이트는 웹 애플리케이션이 아니라 GitHub Pages에 게시하는 정적 안내문이다.

## 문서와 탐색

Starlight의 표준 `website/src/content/docs/` 컬렉션에 기존 원고를 옮긴다.
내용은 유지하고 필수 frontmatter, 기존 MkDocs 안내 상자·내부 링크·그림 경로만 변환한다.
새 설명은 용어를 짧게 풀고 실제 코드와 CLI의 동작을 확인한 뒤 작성한다.

| 기존 원고 | 전환 위치 | 탐색 |
|---|---|---|
| `website/index.md` | `index.mdx` | Overview; Starlight 카드로 학습 경로 안내 |
| `website/user/getting-started.md` | `getting-started/first-run.md` | Getting Started / 첫 실행·첫 Experiment |
| `website/user/results.md` | `getting-started/results.md` | Getting Started / 결과 읽기 |
| `website/user/experiment.md` | `guides/experiment.md` | Guides / Experiment 구성·실제 Agent 연결 |
| `website/developer/overview.md` | `developer/overview.md` | Developer / 구조와 경계 |
| `website/developer/components.md` | `developer/components.md` | Components / Component 연결 |
| `website/developer/validation.md` | `developer/validation.md` | Developer / Validation |
| 없음 | `concepts/overview.md` | Concepts / 구조·단계·반복·경계 |

빈 하위 문서나 내용 없는 Reference는 만들지 않는다. 사용자가 기존 URL 유지가
필수는 아니라고 확인했으므로 새 문서 경로를 적용하고, 새 경로의 내부 링크를
모두 점검한다. `website/assets/report-fixture.png`는 문서 폴더에서 상대 경로로
가져오며, 기존의 합성 fixture 결과라는 설명을 유지한다.

Starlight 기본 한국어 UI(`root` locale `ko`), 사이드바, Pagefind 검색,
명/암 테마, 코드 블록 복사, GitHub 링크를 사용한다. 첫 화면에 CardGrid로
독자의 경로를 보여 주고, 실행 절차에는 필요할 때만 단계형 UI/안내 상자를 쓴다.
별도 디자인 시스템, 앱 프레임워크, 장식용 CSS는 도입하지 않는다.

## 시각화와 사실 경계

`concepts/overview.md`에 네 가지 Mermaid 도식을 짧은 텍스트와 함께 둔다.

1. **전체 구조:** 원본 Agent → 후보 스냅샷 → Harness 실행(선택 Dataset의 공개 과제)
   → 분리된 Evaluator 채점 → Optimizer의 허용 파일 후보 제안 → 그룹별 결과.
   Dataset과 Evaluator를 같은 실행 과정이나 같은 권한으로 합치지 않는다.
2. **실험 단계:** 설정 → 선택 자산 준비/읽기 전용 `doctor --plan` 진단
   → 실행 → train 평가/후보 탐색 → validation 선택 → 선택 고정 후 test(설정 시)
   → 보고서. `doctor`는 정적 진단이고 모델/실평가 성공을 보증하지 않는다.
3. **최적화 반복:** baseline에서 시작해 train의 실행·평가·후보 제안을 반복;
   각 stage는 독립적인 train 이력만 사용하고 최종 후보는 validation으로 선택한다.
4. **컴포넌트 경계:** 사용자/팀 Dataset·Harness·Optimizer·Evaluator 구현
   (`experiments/<team>/`) → 공통 계약(`contracts.py`) → 명시 등록(`registry.py`)
   → Runner. private 평가 자료는 Agent 실행 공간으로 보내지 않는다.

그림 아래 텍스트만으로도 흐름을 이해할 수 있게 하고, 코드에 없는 자동 추천·
병렬 stage 탐색·성능 개선·상용 도구 지원을 그림이 암시하지 않게 한다.

## 빌드·플러그인·배포

`website/package.json`과 `package-lock.json`으로 문서 도구를 분리하고
Node 22 이상, Astro와 Starlight의 호환 버전을 사용한다. `astro.config.mjs`에
사이트 주소 `https://wontaeJeong.github.io`와 Pages 프로젝트 경로
`/agent-optimizer`를 설정한다. 문서 내부 URL과 정적 자산은 이 경로를 포함하도록
작성하고, 로컬 preview에서도 같은 경로를 확인한다.

필요한 통합은 Mermaid fenced code 렌더링(`astro-mermaid` + 호환 Mermaid),
내부 문서/앵커 검증(`starlight-links-validator`), `llms.txt` 생성
(`starlight-llms-txt`)으로 제한한다. `starlight-dot-md`는 원문 노출을 위해
참고하되 마지막 게시가 다른 후보보다 오래된 만큼 현재 Astro/Starlight에서
호환성·정적 출력·URL을 확인한 경우에만 추가한다. 실패하면 별도 raw Markdown
플러그인 없이 `llms-full.txt`와 GitHub의 원고 링크를 제공한다.

기존 `.github/workflows/pages.yml`의 PR 빌드, `main` push 배포 조건과
Pages 권한·환경을 유지한다. 빌드 단계만 `npm ci` → Astro 정적 빌드 및
내부 링크 검사 → `website/dist` 업로드로 바꾸고, 성공한 artifact만
`actions/deploy-pages`에 전달한다. `mkdocs.yml`, `requirements-docs.txt`,
옛 빌드 ignore 항목을 제거하고 README에 `website/`의 설치·미리보기·검증
명령을 적는다. 역사적 설계·검증 근거인 `docs/`의 이전 MkDocs 언급은
과거 기록으로 두고 변경하지 않는다.

## 검증과 완료 기준

- `website/`에서 lockfile 기반 클린 설치, production build, 링크·앵커 검사,
  프리뷰를 실행한다. 내부 링크 오류·누락 페이지는 빌드 실패로 처리한다.
- 생성된 HTML의 한국어·메뉴·검색 인덱스·GitHub 링크·코드 블록·그림·이미지와
  Pages 하위 경로를 확인한다. 데스크톱/모바일에서 탐색과 명/암 모드도 확인한다.
- 생성된 `llms.txt`와 `llms-full.txt`, 채택한 경우 페이지별 `.md` 원문을
  확인한다. 원문 URL과 HTML 링크가 서로 섞이지 않았는지도 검사한다.
- 워크플로 문법과 Pages artifact 경로를 확인하고 PR에서 빌드 체크 결과를
  확인한다. 실제 공개 Pages 갱신은 `main` 반영 뒤의 배포 결과로만 판정한다.
- 문서 UI 변경 전·후 캡처와 재현 방법을 PR에 기록한다. 앱 코드나 `docs/`의
  변경이 없고, 구 MkDocs 실행 설정·의존성이 남지 않아야 한다.
