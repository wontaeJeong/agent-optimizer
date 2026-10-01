---
title: 검증 순서
description: 코어 합성 fixture, 팀 파일과 정적 계획, 실제 Agent·평가기 연결을 단계별로 검증합니다.
---

**전제 조건:** [README의 개발환경 빠른 시작](https://github.com/wontaeJeong/agent-optimizer#개발환경-빠른-시작)과 [담당 템플릿 선택](https://github.com/wontaeJeong/agent-optimizer/blob/main/experiments/README.md)을 마치고 [컴포넌트 연결](/agent-optimizer/developer/components/)에서 담당 계약을 확인하세요. 아래 명령은 저장소 **루트**에서 실행합니다. 코어 배선 → 팀 fixture → 실제 Agent/평가 환경 순으로 근거를 넓힙니다.

## 1. 코어와 계약

```bash
make setup-core
make doctor-core
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_plugin_contracts.py -v
PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml
```

**예상 결과:** 계약 테스트는 원본 보존·후보 범위·그룹별 독립 실행·선택 경계를 API-free fixture로 검증합니다. 최소 예제의 7 trial은 실제 모델·외부 채점 환경이 아닌 **합성 결과**이며 `run_dir/report.html`에 기록됩니다.

## 2. 팀 파일과 선언

**사전 작업:** [팀 템플릿](https://github.com/wontaeJeong/agent-optimizer/blob/main/experiments/README.md)을 `experiments/my-team/`에 **직접 복사·수정**하고 [registry.py](https://github.com/wontaeJeong/agent-optimizer/blob/main/src/agent_optimizer/registry.py)에 필요한 ID를 등록합니다. `experiments/my-team/experiment.toml`은 **설명용 경로**로 복사 전에는 존재하지 않습니다. 팀 파일과 선언이 준비된 후에만 아래를 실행하세요.

```bash
PYTHONPATH=src .venv/bin/python -m agent_optimizer plan experiments/my-team/experiment.toml
.venv/bin/agent-opt datasets list
.venv/bin/agent-opt doctor --plan experiments/my-team/experiment.toml --json
```

**예상 결과:** 템플릿마다 필요한 자산·provider 등록 조건이 다릅니다. `plan`/`doctor --plan`은 선언·플러그인 파일·선택 자산의 **정적 점검**입니다. `"ready": true`여도 모델 실행이나 채점 성공은 아닙니다. 원본 stub의 의도된 실패·환경 누락은 팀 구현으로 해결하며 baseline/합성 평가로 대체하지 않습니다. 메서드 입력·출력은 [공통 계약](https://github.com/wontaeJeong/agent-optimizer/blob/main/src/agent_optimizer/contracts.py)에 맞춥니다.

## 3. 선택한 자산과 실제 실행

새 Dataset을 등록했다면 사용자 선택 후 `.venv/bin/agent-opt doctor --dataset team_dataset --json`으로 준비 상태를 **읽기 전용** 진단합니다. 통과한 뒤 작은 공개 train/validation 과제로 팀의 `run`을 실행하고 실제 Agent 산출물·Evaluator 근거·`runs/<run-id>/report.html`의 상태/사용량을 함께 확인하세요. `<run-id>`는 실제 출력으로 바꿉니다.

```bash
PYTHONPATH=src .venv/bin/python -m agent_optimizer run experiments/my-team/experiment.toml
make lint
make test
git diff --check
```

**예상 결과:** 팀 `run`의 완료 상태만으로 외부 평가 성공이라고 결론 내리지 말고 과제별 산출물·채점 결과를 확인합니다. 실제 외부 모델·Harness·평가기에는 별도 자격증명·평가 환경이 필요합니다. 실패한 도구 실행은 성공으로 대체하지 않고 사용한 소스 commit·데이터셋 버전·모델·예산·평가기를 기록하세요. [구조와 경계](/agent-optimizer/developer/overview/)의 train 피드백과 선택 후 test도 확인합니다.

## 4. ACE/CVDP 실행환경과 모델 검증

**현재 native 경로는 [프리셋 가이드](/agent-optimizer/getting-started/presets/)**의 사용자 선택 고정 로컬 source/data·명시 CID/row/split·별도 Python 3.12/native extra(PyYAML)·평가 driver·Docker/image identity·API 조건부터 확인합니다. init은 로컬 export/선택 검증·설정 생성, prepare는 고정 선택 자료/descriptor·source pin/asset/lock·native Python 3.12/yaml/pydantic_settings·outer benchmark 제한 검사입니다. outer repo entrypoint/driver 파일·task 형태와 **identity 선언 시에만** image inspect를 확인하며 모델·driver imports·독립 inner 환경 전체는 검사하지 않습니다. `--offline`은 범위 확대/자동 설치/다운로드/온라인 보완을 하지 않습니다.

**전체 정적 환경 검증은 `doctor --plan CONFIG --json`**, 실제 API 연결은 `doctor --plan CONFIG --model --json`입니다. prepare는 모델 환경이 없어도 성공할 수 있으므로 준비 완료의 정본으로 사용하지 않습니다. doctor의 pair별 source·inner/outer driver/image·모델 URL/ID/key·TLS 등 checks를 확인한 뒤 작은 row Baseline smoke·독립 연구 설정으로 넓힙니다. native live·실 cleanup·Ubuntu loop는 not_run입니다. 아래 make 명령은 **기존 coding 전체 경로**입니다.

**선택형 실환경 경로:** 코어 계약 테스트와 별도로 실제 Docker 자산·공식 채점기를 준비합니다. 저장소의 수동
`official_cvdp=true` CI는 모델 자격증명 없이 공식 정답/오답과 ACE CLI의 인증 실패 경로를
확인하며, 모델을 사용하는 live 성공은 뜻하지 않습니다.
옵션 없는 개발 명령 `make setup`·`make doctor`는 **ACE 전체 범위**이며 `make smoke`도
실제 평가 도구를 실행합니다. 코어는 위의 `-core` 명령을 사용하세요.

```bash
make setup
make doctor
make smoke
# 모델 키와 AGENT_OPT_MODEL_BASE_URL을 환경에서 지정한 뒤:
.venv/bin/agent-opt run examples/ace-rtl/experiment.toml
# 필요하면 호스트 API·컨테이너 도구 연결만 개발 진단:
sh scripts/bootstrap.sh doctor --model
```

**실제 확인:** `agent-opt run`은 ACE 스킬 프로필을 기존 `live` 경로로 실행합니다. 같은 고정 프로필은
`.venv/bin/agent-opt tui`의 **기존 실험 실행**에서도 고를 수 있습니다. 공식 raw 결과와
`runs/dev-live/<run-id>/summary.json`·`report.html`을 확인하고 미실행/차단을 따로 기록하세요.
개발자용 `doctor --model`은 실제 API·컨테이너 도구를 호출하며, `agent-opt doctor --plan`의 정적 진단과 다릅니다.
이 고정 `simple_feedback` 경로는 TUI Home의 **New Optimization** 또는 선택형 CLI의 [GEPA·Meta-Harness 프리셋](/agent-optimizer/getting-started/presets/)과 별개입니다. 2026-09-28 [source checkout 실환경 후속 기록](https://github.com/wontaeJeong/agent-optimizer/blob/main/docs/verification.md#2026-09-28-선택형-gepameta-harness-실모델공식-cvdp-후속-검증)에는 GEPA/Meta를 각각 **1 iteration, 실제 4/최대 5 trial**로 실행해 후보 사용과 공식 CVDP raw 각 4건을 확인한 근거가 있습니다. 둘 다 validation 동점으로 baseline을 선택했고 `final_test=[]`입니다. 기본 3회/최대 9 trial, 설치형 wheel의 GPT-5 plugin 후속 변경, 일반 성능 개선까지 검증한 것은 아닙니다.

명령별 준비 조건과 부작용은 [개발 명령 기준](https://github.com/wontaeJeong/agent-optimizer/blob/main/docs/development.md)을 참고하고, 현재 검증된 범위와 미검증 항목은 [상태 문서](https://github.com/wontaeJeong/agent-optimizer/blob/main/docs/status.md)와 대조하세요.

## 5. 배포·문서 검증

[G 최종 §7](https://github.com/wontaeJeong/agent-optimizer/blob/main/docs/verification/final-mvp-g-20261001.md)은 전체 1155개 중 실행 1075 통과·기존 skip 80, Ruff·실제 source-free wheel build/install·합성 CLI/native helper/정적 진단·HTTP 근거입니다. 실모델/EDA 성공은 아닙니다. 기존 코어 환경 실행만 필요하면 `AGENT_OPT_CORE_PYTHON=/절대/기존-venv/bin/python make lint`로 현재 checkout을 검사합니다. setup 대상 변경은 아닙니다.

사이트는 기존 Starlight를 사용합니다. Node 22.12+·website에서 `npm ci`, `npm run dev`, `npm run build`, `npm run check:links`를 사용합니다. 실제 check:links script는 astro build이며 내부 링크 validator를 포함합니다. `/agent-optimizer` base path·SVG/이미지·한글 anchor·code fence·360px/desktop을 확인하고 [H 증거](https://github.com/wontaeJeong/agent-optimizer/blob/main/docs/verification/final-mvp-h-20261001.md)를 남깁니다. 과거 날짜별 증거는 보존합니다.
