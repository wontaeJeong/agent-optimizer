# 사람용 MkDocs 가이드 사이트 설계

## 목적과 독자

GitHub Pages에 Agent Optimizer의 사람용 사용 가이드와 팀 확장 개발 가이드를 게시한다.
기존 `README.md`, `docs/`, `experiments/`, `CONTRIBUTING.md`는 사실 확인과 명령 대조에 참고하되,
사이트 본문을 그대로 복사하거나 기존 설계·검증 기록 전체를 공개 메뉴에 올리지 않는다.
가이드는 한국어로 작성한다. 코드 식별자, 명령, 경로는 실제 구현과 동일하게 표기한다.

- 사용자: 코어 환경을 준비하고 데이터셋을 직접 선택한 뒤 CLI/TUI로 실험을 실행하고 보고서를 읽는 사람.
- 팀 개발자: 자신의 Agent, Dataset, Harness, Optimizer, Evaluator를 연결하는 사람.

## 사이트 구성

`mkdocs.yml`에서 `docs_dir: website`를 지정하고 명시적인 `nav`로 게시 범위를 제한한다.
사이트 전용 원고와 이미지 파일은 `website/`에 둔다. 기존 `docs/`는 사이트의 문서 소스가 아니다.

| 구역 | 페이지 | 독자가 확인할 내용 |
|---|---|---|
| 시작 | `website/index.md` | 제품의 범용 실험 흐름, 두 독자 경로, 합성 데모와 실제 성능 검증의 구분 |
| 사용자 | `website/user/getting-started.md` | `make setup ARGS="--core"`, CLI/TUI 시작, 모델·Docker가 필요 없는 첫 확인 |
| 사용자 | `website/user/experiment.md` | 소스·argv·editable·데이터셋·평가기·Optimizer를 명시적으로 선택, doctor → run |
| 사용자 | `website/user/results.md` | `report.html`의 집계·선택·실패·사용량 확인, 합성 fixture의 결과 해석 |
| 개발자 | `website/developer/overview.md` | 계약별 역할, 스냅샷/평가 분리와 train → validation → test 흐름 |
| 개발자 | `website/developer/components.md` | `experiments/<team>/` 템플릿 선택, 공통 계약, registry 등록, 컴포넌트별 시작점 |
| 개발자 | `website/developer/validation.md` | 작은 fixture·plan 진단·관련 계약 검사, 실제 외부 Agent/모델 검증의 별도 기준 |

사람용 페이지는 순서대로 따라 할 수 있는 짧은 설명, 실행 가능한 명령, 기대 결과,
실패 시 점검 위치를 제공한다. 실제 모델 키·엔드포인트는 예시 값만 쓰고 인증정보를 저장하지 않는다.
데이터셋 자동 추천, 모든 Agent 자동 호환, 연구 알고리즘의 upstream 재현, 합성 점수의 실제 성능 주장 등은 하지 않는다.

## 화면과 시각 자료

Material for MkDocs의 탐색 탭·검색·코드 복사·안내 박스·반응형 레이아웃을 사용한다.
불필요한 테마 재구현이나 별도 JavaScript 프레임워크는 도입하지 않는다.

- Mermaid 흐름도 1: Agent/데이터셋/하네스/Optimizer/평가기 및 보고서의 연결.
- Mermaid 흐름도 2: baseline → train 탐색 → validation 선택 → 고정 후 test.
- 결과 페이지에 실제 보존된 `docs/superpowers/report-after-1440.png`의 복사본을 게시한다.
  이미지 설명·캡션에서 **합성 fixture 예시**이며 모델 성능의 증거가 아님을 명시한다.
  이미지의 출처와 사이트 원본의 관계를 문서에 기록한다.

Mermaid가 브라우저에서 표시되지 않아도 도식 옆 텍스트와 대체 설명으로 흐름을 이해할 수 있어야 한다.
모바일 폭에서 코드 블록, 이미지, 메뉴가 가로로 잘리지 않도록 기본 Material 동작으로 확인한다.

## 빌드·배포 흐름

문서 도구는 애플리케이션 런타임 의존성과 분리된 `requirements-docs.txt`에 고정한다.
MkDocs + Material과 필요한 Markdown 확장만 사용하고, `mkdocs build --strict`로
페이지·이미지·내부 링크/앵커 오류를 검사한다. `site/` 빌드 결과는 Git에 넣지 않는다.
로컬 미리보기 명령과 사이트 주소를 `README.md`에 짧게 안내한다.

`.github/workflows/pages.yml`에서 PR마다 동일한 문서 빌드를 확인한다. `main` push는
빌드가 성공하면 `actions/upload-pages-artifact`와 `actions/deploy-pages`로 정적 파일을 게시한다.
배포 단계에는 `pages: write`, `id-token: write` 권한과 `github-pages` 환경을 사용한다.
프로젝트 사이트의 기본 경로는 `https://wontaeJeong.github.io/agent-optimizer/`로 설정한다.
GitHub 저장소의 Pages 설정은 **GitHub Actions**를 게시 소스로 선택해야 하며, 실제 게시 성공은
`main` 반영 후 Actions 로그와 접속 URL을 확인해 판단한다. PR 빌드 통과를 게시 성공으로 표현하지 않는다.

## 검증과 변경 범위

문서에 제시한 명령·계약은 현재 README, 템플릿, `contracts.py`, CLI와 대조한다.
별도 환경에 문서 의존성을 설치해 `mkdocs build --strict`를 실행하고, 생성된 사이트의
메뉴·도식·검색·이미지·모바일 폭을 로컬 미리보기로 확인한다. PR 본문에는 사이트 변경 후 화면과
재현 명령을 포함한다. 링크/이미지가 깨지면 빌드를 실패시키고, Pages 배포는 성공한 빌드에만 진행한다.
문구를 그대로 검사하는 중복 테스트는 만들지 않는다. 기존 앱의 실행 의미와 코어 의존성은 변경하지 않는다.
