# 최종 MVP H — 문서·Starlight 동기화 및 I 인계

확인일: 2026-10-01. **H 문서·사이트 동기화/검증 완료, native live는 `not_run`이다.** 기준 HEAD `28b5367f29f202b85bd1939d0d52c1f79d31d5ad`, 지정 통합 워크트리·브랜치를 재사용한다.

## 작업 계획

목표: 실제 help·A~G 승인 근거에 맞춰 처음 사용하는 개발자의 fixture → native 조건 → 내 Agent → 결과 → 개발 여정을 동기화한다.
구조: README는 진입, `examples/ace-rtl/NATIVE.md`는 native 실행 계약, docs는 개발/경계, 기존 Starlight는 사용자 여정이다. 기능코드·pin은 수정하지 않는다.
기술: Python CLI·Textual의 실제 계약, 기존 Astro/Starlight Markdown·SVG. 하위 에이전트 없이 직접 수행한다.

- [x] A~G 검증 보고서·AGENTS·실제 help와 `website/package.json` scripts를 대조했다.
- [x] README·native/legacy 가이드·현재 docs·experiments·사이트와 경계/inner loop/Home 세 SVG를 동기화했다.
- [x] 격리 Home/output fixture와 사이트 build/link/base path/assets/한글 anchors/360px·desktop을 검증했다.
- [x] 결과·전후 캡처·live 조건과 I 체크리스트를 기록했다. intended diff·status/log 검토 후 한국어 로컬 커밋으로 인계한다.

## 경계

공유 코어 Python은 실행에만 사용한다. 개인 Home/키/온라인 모델은 사용하지 않는다. 임시 결과는 `/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-h`에만 둔다. 사이트 의존성은 지정 격리 워크트리의 `npm ci`만 허용한다. 과거 날짜별 증거를 보존하고 과거 OpenCode 성공을 native 성공으로 바꾸지 않는다. 소유 밖 결함은 I에 인계한다. push/PR/main 수정 없음.

## 1. 소비 근거·변경 문서

`H_DOCS_STARLIGHT_HOWTO.md`를 먼저 읽고 AGENTS와 A~G 검증 보고서를 소비했다. A §2/§7의 절대 Home/output 부모·mixed History, B §7의 평문 Endpoint/secret draft·selector/preset, C §2/§8의 CID 지원표/실패 partial·cleanup, D §8 normalized/native/validation, E HTML-only/close, **F §6~§8 native flags·예제 정책·workspace 출처**, **G §7 최종 1155개/실제 wheel build/install·복수 pair·독립 inner/outer 진단**을 대조했다. progress의 A~G 승인 상태는 보존했다. 인덱스가 없어 CodeGraph를 생성하지 않았다.

변경: README, AGENTS/CONTRIBUTING, docs의 CONTEXT/status/NEXT_STEPS/FUTURE/SOURCES/development/architecture/adding-components/report-schema/verification 및 이 H/progress, examples/ace-rtl README/NATIVE, experiments README, 기존 Starlight **9개 원고**. 신규 SVG 3개(`diagram-product-flow`, `diagram-native-loop`, `diagram-app-home`)와 기존 architecture SVG의 train-only label을 정리했다. CSS/새 UI library/사이트 프레임워크·package scripts/lock·기능코드 변경 없음.

README 순서는 목적 → fixture → TUI/CLI → native 조건 → 내 Agent → Home/History/report → 개발 링크다. native와 legacy active surfaces·inner/outer·row eligibility와 실도구 정답을 구분한다. 날짜별 `docs/verification.md`는 새 절만 추가했고 **기존 본문 바이트를 보존**했음을 검사했다. 기존 upstream/HF/driver/first-party pin은 변경하지 않았다. 사용자 개인 메모는 문서에 옮기지 않았다.

## 2. 실제 명령·결과

아래 `H`/`PY`는 실제 실행 절대경로 약기이며 CWD는 지정 통합 워크트리다. macOS `/var`와 `/private/var`는 같은 임시 경계다. 모든 Python 제품 subprocess는 `env -i`와 명시 HOME/App Home/TMPDIR·PYTHONDONTWRITEBYTECODE를 사용했다.

```bash
H=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-h
PY=/Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "$PY" "$H/verify_commands.py"
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "$PY" "$H/fixture_commands.py"
```

두 script 모두 종료 0. `verify_commands.py`는 실제 `agent-opt` module entrypoint의 **최상위·catalog·catalog list/show·init·prepare·doctor·plan·run·report·tui --help 총 11개**를 실행했다. COLUMNS=200으로 전체 flag 이름을 읽었다. stdout/stderr는 `H/{명령}-help.txt`; help 조회 후 새 `H/app`은 생성되지 않았다. `--cid/--rows/--native-dataset/source/upstream/python/evaluator`, `--max-wall-time-seconds/--trial-timeout-seconds`, report `--serve/--no-open/--port/--json/--csv/--html`, doctor `--model`은 실제 help에 있다. 별도 serve 명령은 없다. native flags를 legacy 전체 setup과 섞지 않았다.

`fixture_commands.py`의 실제 argv는 `H/commands.jsonl`, 명령별 stdout/stderr는 `H/{name}.{stdout,stderr}`다. prefix는 `"$PY" -m agent_optimizer`이며 실제 실행 인수/결과:

| argv(공통 prefix 이후) | 결과 |
|---|---|
| `catalog show harness ace_native --json`, `catalog show optimizer gepa --json` | 각각 0·단일 JSON, Home 무생성 |
| `doctor --plan examples/minimal/experiment.toml --json` | 0·정적 ready |
| `run examples/minimal/experiment.toml --output "$H/output/minimal"` | 0·completed·7 trial·summary synthetic=true, explicit output 부모 소비 |
| `init --name my-fixture --agent examples/minimal/agents/solo --command '{python} {agent_dir}/src/fixture_agent.py {task_dir}' --editable configs/strategy.json --dataset examples/minimal/tasks.json --evaluator examples/minimal/evaluator.py:TextFixtureEvaluator --optimizer baseline --yes` | 0·Home UUID 설정 생성 |
| `doctor --plan "$CONFIG" --json`, `plan "$CONFIG"`, `run "$CONFIG"` | 각각 0, 2-trial completed·기본 Home/runs |
| `report "$RUN" --json`, `report "$RUN" --html` | 각각 0, 원본 summary/events/frozen selection 바이트 보존 |
| `report "$RUN" --json --serve` | 예상 종료 2·충돌 명시 거부 |
| `report "$RUN" --serve --no-open --port 18769` | 실제 GET report.html=200·summary.json=404·SIGINT 종료 130, stdout 비움·URL/안내 stderr |

실제 CONFIG는 `H/fixture-app/experiments/my-fixture-ad47633733c0/experiment.toml`, RUN은 `H/fixture-app/runs/20261001T013716Z-441ae029`다. minimal은 `H/output/minimal/20261001T013716Z-8debdafb`. 원본/inode History API에서 fixture row 조회도 확인했다. fixture Agent/평가기는 실제 로컬 **합성** 실행이며 native 성공이 아니다. README minimal에는 기존 TOML의 명시 output_dir=runs를 정확히 설명했으며 H 검증은 사용자 지시대로 `--output`을 추가해 임시 경계에 저장했다. setup-core/install은 공유 환경 보호를 위해 H에서 실행하지 않았고 G의 기존 증거를 소비했다.

### 관련 계약·lint·문서 링크

```bash
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests HOME="$H/home" AGENT_OPT_HOME="$H/test-app" TMPDIR="$H/tmp" "$PY" -m unittest test_plugin_contracts test_research -v
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin HOME="$H/home" AGENT_OPT_HOME="$H/lint-app" TMPDIR="$H/tmp" AGENT_OPT_CORE_PYTHON="$PY" PYTHONDONTWRITEBYTECODE=1 make lint
env PYTHONDONTWRITEBYTECODE=1 "$PY" "$H/check_docs.py"
git diff --check
```

**31개/5.384초 OK**, 실패/skip 없음. 기존 plugin 18 + research 13이며 문구를 반복하는 새 제품 테스트를 추가하지 않았다. Ruff `All checks passed!`, diff 종료 0. 최종 로컬 링크/heading/code fence **185개 오류 0**, 과거 verification 본문 보존 OK. 전체 1155개·wheel은 **G §7의 실제 결과**이며 H에서 전체/wheel을 새로 실행했다고 주장하지 않는다.

## 3. 실제 사이트 build·브라우저·캡처

Node **25.7.0**, npm **11.10.1**. package.json 실제 scripts는 dev=`astro dev`, build=`astro build`, preview=`astro preview`, check:links=`astro build`다. 기존 astro.config의 site/base=`/agent-optimizer`, Starlight 내부 링크 validator를 유지했다. CWD=`지정 워크트리/website`:

```bash
npm ci --cache "$H/npm-cache"
npm run build
npm run check:links
npm run preview -- --host 127.0.0.1 --port 18768 > "$H/preview.log" 2>&1 &
```

ci 종료 0, 332 packages·0 vulnerabilities. 변경 전 build와 최종 두 scripts 모두 종료 0, **10 pages(404 포함)**·Pagefind/sitemap·8 SVG 최적화, **All internal links are valid.** 최종 build 1.09초·check:links 0.834초. 기존 Vite `use astro:head-inject` 2건·404 content entry 경고는 변경 전에도 같았으며 기능 실패/새 결함으로 숨기지 않는다. scripts/lock/pins는 유지했다.

Playwright `browser_run_code_unsafe`에서 loopback preview를 사용했다(제품 report 서버 검증과 별도). `setViewportSize` **1440×1000 / 360×800**, `goto` 후 각 lazy img를 `scrollIntoViewIfNeeded`·`decode`하고 networkidle 뒤 확인했다. 9개 route(`index`, first-run, presets, results, experiment, concepts/overview, developer/components/overview/validation) × 두 크기 **18개 모두 scrollWidth=viewport**, 이미지 loaded=true, 깨진 페이지 내 anchor=[], stylesheet/script src는 `/agent-optimizer/` base, asset HTTP 오류=[]였다. code fence는 first-run 2/presets 2/results 1/experiment 1/components 1/validation 4개로 실제 렌더링됐다. 한글 anchor는 build validator와 DOM id 대조로 확인했다.

최초 이미지 검사 1회는 화면 밖 **lazy 이미지 미로딩**을 제품 결함으로 오인하는 검사 오류였다. 같은 DOM의 src/loading/rect를 확인하고 scroll/decode 후 위 18개를 완료했다. 이후 SVG 화살표 표시를 파일 내 개별 path로 정리하고 최종 build·presets/overview **4개** 반응형 검사를 다시 수행했다. 세 SVG 원본/캡처를 직접 읽어 private→모델 화살표 없음과 텍스트/방향을 확인했다. 새 custom CSS/animation은 없다.

캡처 루트 `H/captures/`(로컬 검증 자료이며 커밋/외부 배포하지 않음):

| 변경 전(HEAD 28b5367 사이트) | 변경 후 | 크기/내용 |
|---|---|---|
| `before-desktop.png` | `after-presets-1440.png` | 동일 presets 페이지 1440×1000, fullPage |
| `before-360.png` | `after-presets-360.png` | 동일 presets 페이지 360×800, fullPage |
| 해당 없음 | `after-home-1440.png`, `after-home-360.png` | 첫 경로/조건 카드 |
| 해당 없음 | `after-overview-1440.png`, `after-overview-360.png` | 세 경계 도식/설명 |
| 해당 없음 | `product-flow.png`, `native-loop.png`, `app-home.png` | 최종 SVG 단독 캡처 |

재현: preview base `http://127.0.0.1:18768/agent-optimizer/`에 `getting-started/presets/`, `concepts/overview/`, 빈 route를 붙여 위 viewport로 `page.screenshot({path:절대캡처경로,fullPage:true})`. 단독 SVG는 overview의 `img[src*="diagram-이름"]`를 scroll/decode 후 locator.screenshot했다. 종료 시 `lsof -iTCP:18768 -sTCP:LISTEN -n -P`·`ps -p 28516 -o pid=,command=`로 지정 website의 Astro preview PID **28516**임을 확인하고 `kill 28516`으로 종료한다. 실 OS 브라우저 자동 열기·SSH 성공은 미검증이다.

## 4. I 인계·live 조건·잔여 사항

- [x] README fixture→TUI/CLI→native 조건→내 Agent→History/report→개발 여정, init experiment/run_dir 정본·실제 help/script 대조.
- [x] 절대 Home override·6개 경계·project/config/source provenance·explicit output 부모·legacy 보존·자동 migration 없음.
- [x] native/legacy ID와 실제 GEPA/Meta 표면·outer trial/inner attempt/iteration·trusted 재평가·private/train/validation/test 화살표 검토.
- [x] C의 CID002 94/94·004 55/55·007 40/13·016 35/35 정적 지원표, CID007 27 제외/사유/8중복·전체 지원/정답률 아님.
- [x] TUI 상태·Endpoint/ID 평문·key secret·명시 preset/Custom·Review row/split/final_test·무효화/준비/doctor/명시 실행·Result/History 설명.
- [x] normalized JSON/MD/HTML·nullable/partial·algorithm trail·frozen selection·warning·loopback HTML-only/충돌/URL/cleanup 설명 및 실제 합성 HTTP 검증.
- [x] 사이트 build/link·base/assets·한글 anchor/code fence·360px/desktop 전후 캡처와 세 SVG.
- [ ] **native live 조건부 검증:** 실제 선택 고정 source/HF 파일·별도 Python 3.12/native extra PyYAML·고정 CVDP driver lock/repo·Docker/Compose/ps·검토 OSS image tag/identity·Agent URL/ID/key(연구 Optimizer 요구 별도)를 갖춘 뒤 명시 row Baseline smoke→독립 연구 설정을 실행한다. 지금은 `not_run`; online 모델/키를 사용하지 않았다.
- [ ] 실 Docker/network cleanup·native OS process/Agent/EDA 전체·Ubuntu x86_64·OS browser/SSH는 별도 실환경 결과가 필요하다. G wheel·C fixture·과거 coding 성공으로 대체하지 않는다.
- [ ] I 최종 전체 회귀/배포와 사용자 여정을 재확인한다. H 소유 밖 **새 기능 결함은 발견하지 않았다**. 기존 Astro directive/404 경고는 비차단 잔여이며 정리 여부는 I가 판단한다.

verification-before-completion과 requesting-code-review 항목을 실제 명령·diff·소유권·요구사항으로 직접 검토했다. 사용자 지시로 하위 reviewer를 생성하지 않았다. 독립 H 재리뷰 승인 자체를 주장하지 않는다. 기능코드·source pins·개인 Home/키·공유 `.venv`는 변경하지 않았고 main과 기존 사용자 변경을 보존한다. 한국어 로컬 커밋만 남기며 push/PR은 하지 않는다.
