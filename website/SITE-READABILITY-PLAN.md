# 문서 사이트 가독성 개선 구현 계획

> 실행 시 `executing-plans` 스킬을 사용하고 아래 항목을 순서대로 검증한다.

**목표:** 세 작업별 시작 경로를 명확히 하고 합성 실험, 결과 화면, 구조도를 처음부터 읽을 수 있게 한다.

**구성:** 기존 페이지 경로·앵커와 Starlight 기본 UI는 유지한다. 문서 구조·원고를 먼저 다듬고, 클라이언트 Mermaid 통합을 제거한 뒤 정적 SVG를 원고에 직접 삽입한다. CSS는 본문 읽기와 개별 스크롤 영역에만 한정한다.

**도구:** Astro 7, Starlight 0.42, MD/MDX, SVG, CSS, Node 22.12+.

**설계:** `website/SITE-READABILITY-DESIGN.md`

## 공통 제약

- 범위는 `website/`의 문서 사이트·콘텐츠이며 실행 엔진과 보고서 생성 로직을 수정하지 않는다.
- 기존 7개 하위 URL과 공개 앵커를 유지한다.
- 7-trial 최소 데모와 2-trial `guide-fixture`, 선택형 ACE/CVDP의 전제 조건과 증거 수준을 구분한다.
- 합성 fixture·정적 doctor·실제 외부 Agent 평가를 성공 근거로 혼동하지 않는다.
- `website/`에서 `npm ci`, `npm run build` 및 내부 링크/앵커 검사를 통과한다.

## 파일 역할

- `astro.config.mjs`: 3개 그룹의 사이드바와 Mermaid 통합 제거.
- `src/content/docs/index.mdx`: 세 역할별 시작 카드.
- `src/content/docs/getting-started/{first-run,results}.md`: 기본 경로 및 결과·원본 기록 설명.
- `src/content/docs/guides/experiment.md`, `src/content/docs/developer/*.md`: 사용자/팀 개발 경로.
- `src/content/docs/concepts/overview.md`: 네 구조도와 단계 설명.
- `src/assets/diagram-*.svg`: 네 구조도 및 개발자 독립 stage 그림, 각 그림에 title/desc.
- `src/styles/site.css`: 기존 Mermaid 전용 파일을 사이트 읽기 스타일로 교체.

### 작업 1: 경로와 첫 실행

**Files:** `website/astro.config.mjs`, `website/src/content/docs/index.mdx`, `website/src/content/docs/getting-started/first-run.md`, `website/src/content/docs/guides/experiment.md`

**Interfaces:** 기존 `/agent-optimizer/` 기준의 하위 URL과 앵커를 그대로 제공한다.

- [ ] **Step 1: 원고와 실행 상태 대조.** `README.md` 5–50행, `docs/status.md` 19–36행, `website/src/content/docs/getting-started/first-run.md`를 비교하여 `make setup-core`가 자동 7 trial을 만들고 직접 만든 `guide-fixture`는 2 trial임을 확인한다.
- [ ] **Step 2: 사이드바·홈 수정.** `sidebar`를 시작하기(첫 실행/결과), 실험하기(실험 구성/동작 원리), 팀 컴포넌트 개발(컴포넌트 연결/구조와 경계/검증 순서)로 바꾸고 홈 카드를 각각 `/getting-started/first-run/`, `/guides/experiment/`, `/developer/components/`로 바로 연결한다. 카드 문구에는 전제 조건과 다음 페이지를 명시한다.
- [ ] **Step 3: 단일 기본 경로 작성.** `make setup-core` → `make doctor-core` → `.venv/bin/agent-opt doctor --plan examples/minimal/experiment.toml --json` → `.venv/bin/agent-opt run examples/minimal/experiment.toml`을 붙여 넣는 블록과 `run_dir`/`status`/`trials_used: 7` 확인, `report.html` 여는 법을 함께 배치한다. 앞선 setup 자체가 데모 하나를 만든다고 명시한다. 선택형 2-trial 설정 명령과 ACE/CVDP를 독립 절로 둔다.
- [ ] **Step 4: 사용자 실험 구성 편집.** 사용자 Agent 입력·명시 데이터셋·평가기·자격증명·정적 plan을 짧은 절로 정리하고, 독립 실행 가능한 fixture 명령만 실제 명령으로 남긴다.
- [ ] **Step 5: 빌드로 검증.** `npm run build`에서 링크·앵커 검사 성공 확인 후 `git diff --check`를 실행한다.

### 작업 2: 즉시 읽히는 구조도

**Files:** `website/astro.config.mjs`, `website/package.json`, `website/package-lock.json`, `website/src/content/docs/concepts/overview.md`, `website/src/content/docs/developer/overview.md`, `website/src/assets/diagram-architecture.svg`, `website/src/assets/diagram-stages.svg`, `website/src/assets/diagram-iteration.svg`, `website/src/assets/diagram-boundaries.svg`, `website/src/assets/diagram-stage-isolation.svg`, `website/src/styles/site.css`

**Interfaces:** 개념 페이지의 `#전체-구조`, `#실험-단계`, `#최적화-반복`, `#컴포넌트-경계`를 유지한다. 각 SVG는 `<title>`과 `<desc>`를 제공하고 각 Markdown 이미지에는 별도의 간결한 alt를 준다.

- [ ] **Step 1: 기준 원인 확인.** 기존 빌드 `dist/concepts/overview/index.html`에서 `<pre class="mermaid">flowchart`가 초기 HTML에 있는지 확인한다.
- [ ] **Step 2: 정적 도식 작성.** 구조도는 원본→스냅샷→Harness→Evaluator→Trial→Report의 읽기 방향과 Dataset의 공개/분리 평가 경로, Optimizer의 editable 되먹임을 분리해 그린다. 단계 도식은 설정·준비·doctor/실행·baseline/반복 train/validation/선택 고정·선택적 test/보고로 배치한다. 나머지 반복·팀 경계·독립 stage도 같은 의미를 SVG에서 유지한다. SVG `viewBox`와 노드·화살표의 채우기/선 대비를 확인한다.
- [ ] **Step 3: HTML에 SVG 직출력.** 문서의 Mermaid 코드 펜스를 SVG 이미지로 바꾸고 `mermaid()` 통합과 런타임 패키지를 제거한다. SVG 문법은 본문 검색 색인에 들어가지 않게 한다. 설명 문단에 `Evaluator`, `평가기` 등 검색 가능한 실제 용어를 남긴다.
- [ ] **Step 4: 좁은 화면 읽기.** 도식마다 래퍼를 추가하고 도식의 최소 읽기 폭·독립 가로 스크롤·조작 안내를 스타일에 넣는다. 확대 없이 글자를 구분할 수 있어야 한다.
- [ ] **Step 5: 빌드·색인 검증.** `npm ci && npm run build`를 실행하고 `dist/concepts/overview/index.html`에 Mermaid `pre`가 없는지, Pagefind 검색에 `flowchart`가 없는지 확인한다.

### 작업 3: 결과·팀 가이드·화면 조정

**Files:** `website/src/content/docs/getting-started/results.md` (읽기 흐름에 따라 `.mdx`로 이동 가능), `website/src/content/docs/developer/{components,overview,validation}.md`, `website/src/styles/site.css`, `website/astro.config.mjs`

**Interfaces:** 결과 파일은 `src/assets/report-fixture.png`의 1440×900 7-trial 합성 캡처를 재사용한다. 링크·이미지 접근성 및 원본 크기 열기를 제공한다.

- [ ] **Step 1: 결과 설명 정리.** 이미지 캡션에 7-trial과 2-trial의 차이를 명시하고, 상태/예산과 validation 비교를 읽기 쉬운 크기로 두 발췌 영역에 배치한다. 원본 이미지 링크를 새 탭에서 열 수 있게 한다. `report.html`/`report.md`/`report.json`은 파생, `summary.json`/`events.jsonl`/`manifest.json`은 실행 기록이라고 표로 구별한다.
- [ ] **Step 2: 팀 경로 구획.** `components.md`의 코드가 의사코드임을 표기하고, 템플릿·계약·등록·검증 파일의 GitHub 링크를 달며 `overview.md`, `validation.md`의 앞뒤 경로와 전제/결과/주의점을 분리한다. 템플릿을 복사해 바꿔야 하는 `experiments/my-team/` 경로는 예시라고 명시한다.
- [ ] **Step 3: 읽기 스타일 조정.** `--sl-content-width`를 데스크톱에서 읽기 좋은 범위로 소폭 넓히고 카드 문구·문단 간격, 표/코드의 스크롤 영역만 조정한다. Starlight 기본 메뉴/테마/복사는 건드리지 않는다.
- [ ] **Step 4: 실제 브라우저 검증.** 로컬 `npm run dev -- --host 127.0.0.1` 또는 `npm run preview -- --host 127.0.0.1`에서 360/390/768/1440px 및 명/암 테마에 경로 3개, 검색어 `evaluator`/`평가기`/`첫 실행`, 초기 그림·스크롤·표·코드 복사·원본 이미지·키보드를 확인한다. 실패하면 관련 콘텐츠/스타일만 고치고 다시 확인한다.
- [ ] **Step 5: 최종 빌드·PR.** `npm ci && npm run build`, `git diff --check`, `git status --short --branch`, `git worktree list`를 확인한다. 전후 캡처를 PR 본문에 게시하고 재현 절차와 Mermaid 원인·정적 SVG 선택 이유, 검증 결과를 적는다.
