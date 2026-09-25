# 사람용 MkDocs 가이드 사이트 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 이 작업은 위임 지시가 없어 현재 세션에서 직접 구현한다.

**목표:** 사람용 사용자·팀 개발자 가이드를 Material 기반 GitHub Pages에 자동 게시한다.

**구조:** `website/`만 정적 문서 소스로 사용하고 기존 `docs/`는 참고 자료로 유지한다. 독립 문서 의존성으로 로컬/CI 빌드를 실행하며 PR에서는 검증, `main`에서는 검증 후 Pages에 배포한다.

**기술:** MkDocs 1.6.1, Material for MkDocs 9.6.20, Mermaid, GitHub Actions Pages.

**설계:** `docs/superpowers/specs/2026-09-25-mkdocs-guides-design.md`

## 공통 제약

- 가이드는 한국어로 작성한다. 코드 식별자·명령·경로는 실제 구현과 일치시킨다.
- 사이트 소스는 `website/`이며, 기존 `docs/` 원문이나 설계·검증 기록 전체를 메뉴에 게시하지 않는다.
- 실제 모델 키·엔드포인트는 저장하지 않는다. 합성 fixture 점수는 실제 모델 성능으로 설명하지 않는다.
- 앱 런타임 의존성 및 CLI 동작을 변경하지 않는다. 문구 반복 검사용 단위 테스트는 만들지 않는다.
- PR마다 문서 빌드를 검사하고 `main` 반영 후에만 Pages를 게시한다.

## 파일 지도

- `mkdocs.yml`: 명시적 메뉴, Material 옵션, Markdown 확장, 링크 검사 설정.
- `requirements-docs.txt`: 문서용 고정 의존성.
- `website/index.md`: 독자별 시작 경로와 범용 제품 설명.
- `website/user/{getting-started,experiment,results}.md`: 설치/데모, 실험 선언, 결과 해석.
- `website/developer/{overview,components,validation}.md`: 아키텍처, 팀 계약/등록, 검증 절차.
- `website/assets/report-fixture.png`: 실제 보존된 합성 보고서 화면의 복사본.
- `.gitignore`, `README.md`: 빌드 산출물 제외, 로컬 미리보기 안내.
- `.github/workflows/pages.yml`: PR 빌드와 main 게시.

### 작업 1: 사이트 기반과 사용자 가이드

**파일:** `mkdocs.yml`, `requirements-docs.txt`, `.gitignore`, `website/index.md`, `website/user/*.md`, `website/assets/report-fixture.png`

**입력:** `README.md`의 최신 CLI 명령, `docs/architecture.md`의 실행/결과 경계, `docs/superpowers/report-after-1440.png`의 실제 합성 화면.
**산출:** 페이지 제목과 상대 링크가 정의된 MkDocs 사이트; 작업 2는 이 메뉴 구조를 사용한다.

- [ ] 1. 빌드가 아직 불가능한 상태를 확인한다: `python3 -m mkdocs build --strict`는 `No module named mkdocs`이거나 `mkdocs.yml` 부재로 실패해야 한다.
- [ ] 2. `requirements-docs.txt`에 `mkdocs==1.6.1`과 `mkdocs-material==9.6.20`을 작성하고 별도 문서 환경에 설치한다.
- [ ] 3. `mkdocs.yml`에 `docs_dir: website`, 프로젝트 사이트 `site_url`, `theme: material`(한국어·명/암 모드·탭·검색·코드 복사), 명시적 `nav`, 검색, admonition/details, Mermaid용 `pymdownx.superfences`, 링크/앵커 경고 설정을 작성한다. 예시:

  ```yaml
  site_url: https://wontaeJeong.github.io/agent-optimizer/
  docs_dir: website
  theme:
    name: material
    language: ko
    features:
      - navigation.tabs
      - content.code.copy
  plugins:
    - search
  markdown_extensions:
    - admonition
    - pymdownx.details
    - pymdownx.superfences:
        custom_fences:
          - name: mermaid
            class: mermaid
            format: !!python/name:pymdownx.superfences.fence_code_format
  validation:
    links:
      not_found: warn
      anchors: warn
  ```

- [ ] 4. `website/index.md`, `website/user/getting-started.md`, `experiment.md`, `results.md`를 작성한다. 빠른 시작은 `make setup ARGS="--core"` → `.venv/bin/agent-opt tui` 또는 API-free `init` → `doctor --plan` → `run` → `report.html`로 연결한다. `experiment.md`는 `--command-json`, `--editable`, 명시적인 `--dataset`, custom `--evaluator`, 모델 설정의 선택 경로를 설명한다. `results.md`는 null/partial, validation/test, 데이터셋별 독립 비교를 설명한다.
- [ ] 5. 기존 `docs/superpowers/report-after-1440.png`를 `website/assets/report-fixture.png`로 복사하고 정확한 합성 fixture 설명 및 출처를 결과 페이지에 표기한다. `.gitignore`에 `/site/`를 추가한다.
- [ ] 6. `mkdocs build --strict`를 실행해 아직 작성되지 않은 개발자 페이지 외의 링크·이미지가 유효함을 확인한다. 개발자 nav 항목이 먼저 작성되어 엄격한 빌드가 실패하면 작업 2의 개발자 페이지를 작성한 뒤 재검증한다. `git diff --check` 후 변경 파일만 커밋한다.

### 작업 2: 팀 개발자 가이드

**파일:** `website/developer/overview.md`, `website/developer/components.md`, `website/developer/validation.md`

**입력:** `src/agent_optimizer/contracts.py`, `src/agent_optimizer/registry.py`, `docs/adding-components.md`, `experiments/README.md`, `CONTRIBUTING.md`.
**산출:** 독립된 사람용 팀 개발자 경로. 코어 내부 설계 원문을 그대로 게시하지 않는다.

- [ ] 1. `overview.md`에 두 번째 Mermaid 도식으로 baseline → train 후보 탐색 → validation 선택 → 고정 후 test를 그리고 첫 도식의 Agent/데이터셋/하네스/평가기/Optimizer 역할을 설명한다. 도식 주변에 대체 텍스트를 둔다.
- [ ] 2. `components.md`에 역할별 템플릿, `PROJECT_COMPONENTS`의 실제 ID→`file.py:Symbol` 등록 예제, 공통 계약 `Optimizer.optimize`/`HarnessAdapter.run`/`Evaluator.evaluate`/`DatasetProvider.prepare`, 스냅샷·editable·private 평가 경계를 적는다.
- [ ] 3. `validation.md`에 코어 준비 → fixture/plan → 계약 테스트 → 실제 팀 환경 확인의 순서와 미구현 stub 실패/실환경 검증 구분을 적는다.
- [ ] 4. `mkdocs build --strict`와 `git diff --check`를 실행하고 링크·앵커·이미지 오류가 없으면 변경 파일만 커밋한다.

### 작업 3: 자동 빌드·배포와 사용 안내

**파일:** `.github/workflows/pages.yml`, `README.md`

**입력:** 작업 1~2의 문서 사이트; 기존 `.github/workflows/ci.yml`의 CI 스타일.
**산출:** PR에서 검증되고 `main`에서만 업로드/배포되는 정적 사이트.

- [ ] 1. 워크플로를 다음 구조로 작성한다. 설치 명령과 빌드 명령은 로컬 검증 명령과 동일하게 한다.

  ```yaml
  name: guides-pages
  on:
    pull_request:
    push:
      branches: [main]
    workflow_dispatch:
  permissions:
    contents: read
  jobs:
    build:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with:
            python-version: '3.12'
        - run: python -m pip install -r requirements-docs.txt
        - run: mkdocs build --strict
        - if: github.event_name == 'push' && github.ref == 'refs/heads/main'
          uses: actions/upload-pages-artifact@v3
          with:
            path: site
    deploy:
      if: github.event_name == 'push' && github.ref == 'refs/heads/main'
      needs: build
      runs-on: ubuntu-latest
      permissions:
        pages: write
        id-token: write
      environment:
        name: github-pages
        url: ${{ steps.deployment.outputs.page_url }}
      steps:
        - id: deployment
          uses: actions/deploy-pages@v4
  ```

- [ ] 2. `README.md`에 문서 주소, 독립 문서 환경 설치·`mkdocs serve`·`mkdocs build --strict`, Pages 게시 소스를 GitHub Actions로 선택하는 방법을 짧게 안내한다.
- [ ] 3. 새 문서 환경에서 `mkdocs build --strict`, 기존 코어 환경이 준비되면 `make lint`, `git diff --check`를 실행한다. 로컬 브라우저에서 데스크톱/모바일 메뉴·검색·Mermaid·이미지 로딩을 확인하고 사이트 화면을 캡처한다.
- [ ] 4. `git status`, `git diff`, 최근 로그를 확인하고 의도한 변경만 커밋한다. 브랜치를 푸시하고 PR에 신규 사이트라 변경 전 화면이 없다는 이유, 사이트 변경 후 캡처·재현 명령·실제 검증 결과를 기록한다. Pages 실제 게시 여부는 `main` 반영 후 별도 확인 대상으로 분리한다.
