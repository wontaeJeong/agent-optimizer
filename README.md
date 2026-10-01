# Agent Optimizer — Agent 개발자를 위한 CLI/TUI

로컬 또는 고정 Git commit의 Agent 소스에 실행 Harness·데이터셋·별도 Evaluator·Optimizer를 연결하여 **후보 생성 → 평가 → 선택 → 보고**를 반복하는 범용 Python 도구입니다. 원본과 평가 기준을 보존하며 ACE-RTL은 `examples/`의 선택적 연동입니다.

## 개발환경 빠른 시작

저장소 루트에서 Mac/Linux·Git·Python 3.11+로 시작합니다. `make setup-core`는 uv와 신규 Python 3.12·고정 개발 의존성을 `.venv`에 준비하고 합성 데모도 한 번 실행합니다. 첫 설치에 다운로드가 필요할 수 있으나 **fixture 실행은 모델·Docker가 필요 없습니다.** make가 없으면 `sh scripts/bootstrap.sh setup --core`를 사용하세요.

```bash
make setup-core
make doctor-core
.venv/bin/agent-opt doctor --plan examples/minimal/experiment.toml --json
.venv/bin/agent-opt run examples/minimal/experiment.toml
```

마지막 명령은 새 실행을 만듭니다. 예상값은 `status=completed`, `trials_used=7`, `synthetic=true`입니다. 두 합성 Agent·`fixture`·`file_variants`의 배선 검사이며 실제 모델/RTL 개선이 아닙니다. 이 **기존 TOML은 명시 `output_dir="runs"`**여서 프로젝트 `runs/<run-id>`에 저장합니다. 후속 명령에는 JSON이 출력한 `run_dir`·`report_html`을 사용하세요.

## TUI 또는 CLI로 선택하기

```bash
.venv/bin/agent-opt --help
.venv/bin/agent-opt tui
.venv/bin/agent-opt catalog list --kind harness
.venv/bin/agent-opt catalog show optimizer gepa --json
```

무인자 `agent-opt`는 정상 TTY에서 TUI를 열고 pipe/CI/dumb 터미널에서는 help와 종료 2를 반환합니다. Home의 **새 최적화 / 기존 실험 / 실행 이력 / 고급 설정 / 종료**에서 선택합니다. 새 흐름은 **Agent → Harness → Optimizer → Dataset → (native CID·row·split) → Model → Review → Preparing → Doctor → Running → Result/History**입니다. `↑/↓`, `Enter`, `Esc`를 사용하며 highlight는 조회만 합니다. 준비 완료 후 Doctor로, 진단 통과 후 실행으로 각각 명시적으로 계속해야 합니다.

Planned는 미구현·비활성, 미준비는 자산/환경 부족, 비호환은 선택 불가, 미검증은 실환경 성공 근거 부재입니다. **Endpoint와 Model ID는 평문, API key만 숨김 입력**입니다. 현재 환경·세션·기본값·명시 제공 named preset·Custom을 구분하며 preset은 URL/ID만 저장합니다. 자격증명 포함 URL은 거부하고 키는 세션/환경에만 둡니다. `.env` 자동 로딩은 없습니다. 상세는 [프리셋 가이드](https://wontaeJeong.github.io/agent-optimizer/getting-started/presets/)를 확인하세요.

`catalog`는 읽기 전용 설명 조회, `init --yes`·`prepare`는 선택 자산 준비, `doctor --plan`·`plan`은 정적 검사, `run`은 실제 외부 실행이 가능한 명령입니다. `doctor --plan CONFIG --model`만 명시 모델 API probe를 추가하며 성공해도 전체 Agent/평가 성공은 아닙니다. 기계용 stdout JSON과 진행 stderr를 구분하세요. 별도 `serve` 명령은 없고 **`report --serve`**를 사용합니다.

## 실제 ACE native 데모 조건

ACE-RTL의 첫 Harness는 **Python native**입니다. CLI 선택은 `--harness-profile ace_native`(별칭 `ace-native`), Agent ID `ace-rtl-native`, adapter `ace_native`, profile `ace-native`, evaluator `cvdp_native`입니다. 고정 **로컬** ACE checkout/export·HF JSONL, 별도 Python **3.12 + native extra(PyYAML)**, 고정 CVDP driver/repo·검토한 OSS simulator image tag/identity·Docker·`ps`, Agent API URL/ID/key가 필요합니다. Baseline도 native Agent API를 요구하며 Optimizer API 필요 여부는 별도입니다.

사용자가 `cid002/cid004/cid007/cid016`과 **실제 row ID→train/validation/test**를 고릅니다. 자동 추천·전체 CVDP 지원·자동 held-out 분할은 없습니다. CID007은 40개 중 13개만 정적 eligible이며 PNR/상용 helper 27개를 제외합니다. native `init`/`prepare`는 사용자가 고른 고정 로컬 소스·데이터를 검증/준비하는 경로입니다. **`prepare --offline`은 누락 interpreter/driver/image/모델 환경을 설치하거나 online으로 보완하지 않고 명시 오류로 끝납니다.**

[native 실행 가이드](examples/ace-rtl/NATIVE.md)에 준비 → doctor → 작은 smoke → 선택 CID → 결과의 복사 가능한 명령과 지원표가 있습니다. GEPA는 `native/guidance.md`, Meta-Harness는 실제 import되는 `native/orchestration.py:guidance`를 수정합니다. outer Optimizer trial과 inner ACE attempt/iteration·trusted 최종 평가를 구분합니다. native live는 현재 **`not_run`**입니다.

기존 **OpenCode/Claude Code coding 프로필**은 별도 선택입니다. `ace-opencode`의 GEPA `role-guidance.md`/Meta `agent_opt_scaffold.py:prepare_task`는 native 표면이 아닙니다. `init --profile ace-rtl --workspace PATH`와 옵션 없는 `make setup/doctor`, `make smoke/live`는 **기존 ACE 전체 coding 경로**입니다. 코어/native 전체 준비로 재해석하지 마세요. [legacy 안내](examples/ace-rtl/README.md)와 [과거 실제 OpenCode 기록](docs/verification.md#2026-09-28-선택형-gepameta-harness-실모델공식-cvdp-후속-검증)은 native 성공 증거가 아닙니다.

## 내 Agent 연결하기

코어 준비 후 저장소 루트에서 아래 합성 2-trial 설정을 만들 수 있습니다.

```bash
.venv/bin/agent-opt init --name my-fixture \
  --agent examples/minimal/agents/solo \
  --command '{python} {agent_dir}/src/fixture_agent.py {task_dir}' \
  --editable configs/strategy.json \
  --dataset examples/minimal/tasks.json \
  --evaluator examples/minimal/evaluator.py:TextFixtureEvaluator \
  --optimizer baseline --yes
# init JSON의 experiment 절대경로를 그대로 복사:
CONFIG='/실제/init/출력/experiment.toml'
.venv/bin/agent-opt doctor --plan "$CONFIG" --json
.venv/bin/agent-opt plan "$CONFIG"
.venv/bin/agent-opt run "$CONFIG"
```

`CONFIG`는 설명용 값이며 실제 `init` 출력으로 바꿉니다. 새 설정은 **App Home/experiments/<이름>-<uuid12>/experiment.toml**이며 같은 이름도 독립 생성합니다. 고정 `runs/configs/<name>` 경로를 추측하지 마세요. 실제 Agent는 `--agent LOCAL` 또는 `--agent GIT_URL --revision FULL_SHA`를 연결하고 editable·Harness·데이터·평가기를 직접 지정합니다. `--command`는 argv 인용만 분리하며 셸 확장/파이프를 실행하지 않습니다. [실험 구성](https://wontaeJeong.github.io/agent-optimizer/guides/experiment/)을 참고하세요.

### App Home과 프로젝트

기본 **`~/.agent-optimizer`**, `AGENT_OPT_HOME`은 `~` 확장 후 **절대경로만** 허용합니다(없거나 빈 값이면 기본). 상대값·unsafe 경로/권한을 조용히 fallback하지 않습니다.

```text
~/.agent-optimizer/
  experiments/  # 생성 설정·Agent/Harness/tasks 선언
  runs/         # 새 설정의 기본 run 부모 → UTC run-id
  sessions/     # 복수 dataset 독립 run-session 부모
  assets/       # 선택 연동 helper·고정 native export
  cache/        # datasets 및 integrations의 검증 캐시
  logs/         # 앱 로그 경계(항상 생성되는 폴더는 아님)
```

프로젝트는 개발 소스/플러그인의 기준, Home은 실행 저장소입니다. 새 설정의 `project_root`는 원본 절대 provenance, `config_root="."`는 설정 파일 부모입니다. agents/harnesses/benchmark는 config_root, 원본 플러그인은 project_root, local source는 Agent manifest 기준을 보존합니다. **output 우선순위: CLI `--output` > 명시 TOML `output_dir` > Home/runs**. 모두 run-id를 담는 **부모**이며 상대 CLI output은 호출 CWD, 상대 TOML output은 project_root 기준입니다. session explicit output도 부모 의미입니다. 옛 프로젝트 runs/sessions·명시 output 이력은 선택한 경계에서 조회하며 XDG/cache/실행 자료를 **자동 migration·이동·삭제하지 않습니다**.

## History와 보고서 보기

TUI 실행 이력은 성공·실패·중단·보고서 없음·session과 실제 child를 읽기 전용으로 보여줍니다. HTML 없음은 실행 없음이 아닙니다. 종료 근거 없는 running은 `stale`, 불충분한 기록은 `unknown`; 선택한 기존 실험의 explicit output 부모도 조회합니다.

```bash
RUN='/실제/run/출력/run_dir'
.venv/bin/agent-opt report "$RUN" --json
.venv/bin/agent-opt report "$RUN" --html
.venv/bin/agent-opt report "$RUN" --serve --no-open --port 0
```

`report.html`, `report.md`, `report.json` v3는 **같은 normalized model**을 사용합니다. `summary.json`·events·manifest·후보 diff·`frozen_selection.json`은 원본 근거입니다. 기록된 validation만 비교하며 stage별 algorithm trail·inner/native 요청과 outer 평가·최종 test를 분리합니다. 미수집은 null, partial은 전체 사용량이 아니며 누락/손상/불일치는 evidence warning으로 표시합니다. `--html`은 저장된 결과로 재생성할 뿐 재평가/재선택하지 않습니다.

`--serve`는 **127.0.0.1의 선택 HTML 한 파일만** 공개합니다. JSON/MD/로그/후보/private와 session child 링크는 allowlist 밖입니다. child 보고서는 별도로 선택하세요. `--html --serve`는 재생성 후 열람, `--no-open`은 자동 브라우저 생략, `--port 0`은 자동 포트, Ctrl+C는 130입니다. 명시 포트 충돌은 오류와 retry를 제공하고 브라우저 실패는 URL을 남기며 run 성적을 바꾸지 않습니다. SSH에서는 서버가 살아 있는 동안 표시 포트로 포워딩하세요. `--json/--csv`와 serve 충돌은 종료 2입니다.

![합성 최소 실행의 HTML 보고서(과거 캡처, 실제 native 성능 근거 아님)](website/src/assets/report-minimal-current.png)

## 개발 문서와 검증 범위

**README 빠른 시작 → [담당 템플릿](experiments/README.md) → [확장 계약](docs/adding-components.md)·[contracts.py](src/agent_optimizer/contracts.py)** 순서로 진행합니다. 팀 구현은 `experiments/<team>/`, ID→파일 등록은 `registry.py`입니다. 여러 Agent/Harness·독립 stage는 baseline에서 시작하고 수정 근거는 stage-local train, 선택은 validation, test는 선택 고정 이후입니다. 연구 이름의 자체 구현은 upstream/논문 재현이 아닙니다. Planned/미지원은 명시 실패하며 합성 fallback하지 않습니다.

- [구조/세 경계 도식](docs/architecture.md), [현재 상태](docs/status.md), [다음 작업](docs/NEXT_STEPS.md), [보류](docs/FUTURE.md)
- [개발 명령·offline/CA/proxy](docs/development.md), [기여/검증](CONTRIBUTING.md), [고정 출처](docs/SOURCES.md), [날짜별 증거](docs/verification.md)
- [G 최종 §7](docs/verification/final-mvp-g-20261001.md#7-수정-라운드-1--독립-리뷰-r1r4-대응): 전체 1155개 중 실행 1075개 통과·기존 skip 80개, lint·실제 source-free wheel build/install/합성/HTTP smoke 통과. **native 실모델·실 Docker/EDA·Ubuntu native loop는 not_run**입니다.

기존 코어 검사에는 `make test/lint/demo`를 사용합니다. 다른 격리 checkout에서 기존 환경 실행만 필요하면 `AGENT_OPT_CORE_PYTHON=/절대/기존-venv/bin/python make lint`처럼 지정합니다. 사이트는 기존 Astro Starlight를 유지합니다. Node.js 22.12+로 `website/`에서 `npm ci`, `npm run dev`, `npm run build`, `npm run check:links`(실제 script는 build)를 실행하세요. `/agent-optimizer` base path이며 앱 환경과 별개입니다.
