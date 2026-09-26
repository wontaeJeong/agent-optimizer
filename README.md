# Agent Optimizer — Agent 개발자를 위한 CLI/TUI

범용 Agent 최적화 실험용 Python CLI·대화형 TUI입니다. **ACE-RTL은 데모 대상이며 제품 코어가 아닙니다.**
다른 팀 Agent의 repo·실행 방식·평가 방법·수정 허용 범위를 연결해 같은 실험 흐름을 사용합니다.
실제 Agent는 별도 repo, 작은 개발용 Agent는 `examples/`에 포함합니다.
대상에 따라 실행·평가 어댑터 개발이 필요하며, 모든 Agent를 설정만으로 자동 지원하지는 않습니다.

## 사람용 가이드 사이트

[사용자·팀 개발자 가이드](https://wontaeJeong.github.io/agent-optimizer/)는 `website/` 원고를
Material for MkDocs로 빌드합니다. 로컬 미리보기와 링크 검사는 앱 환경과 분리해 실행합니다:

```bash
python3.12 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r requirements-docs.txt
.venv-docs/bin/mkdocs serve
# 별도 터미널에서 배포 전 검사: .venv-docs/bin/mkdocs build --strict
```

로컬 주소는 `http://127.0.0.1:8000/agent-optimizer/`입니다. PR에서는 엄격한 문서 빌드를 검사하고
`main`에 반영되면 GitHub Actions가 게시합니다. 이 저장소는 Pages 게시 소스를 **GitHub Actions**로
설정했습니다. 다른 저장소에 옮길 때는 **Settings → Pages → Build and deployment**에서 선택하세요.
실제 공개 여부는 배포 작업과 접속 주소로 확인하세요.

## Agent 개발자가 사용하는 경로

wheel만 설치해도 저장소 clone 없이 `agent-opt datasets list`와 사용자 로컬/고정 Git
Agent·명시적 evaluator 실험의 `init` → `doctor --plan` → `run` → `report`가 동작합니다.
`cvdp`·Verilog-Eval은 **직접 선택한 뒤에만** 검증된 고정 버전 코드·데이터·평가 환경을
준비합니다. 목록 노출은 자산 준비나 모델 연결 성공을 뜻하지 않습니다.

저장소 개발자는 먼저 `make setup-core`로 CLI를 준비합니다. `.venv/bin/agent-opt tui`에서 **기존 실험 실행**을
선택하면 `experiment.toml`의 계획 진단·확인 뒤 실행하고, **새 실험 만들고 실행**에서는
Agent·editable 파일·Optimizer·**직접 선택하는 데이터셋**을 묻습니다. 새 `command` 하네스에서만
Agent 실행 명령을 묻습니다. **3번 ACE-RTL + CVDP 예제**에서는 작업공간과 준비 작업을
확인한 뒤 선택형 연동을 준비합니다. 모델 값이 없으면 이 세션에서만 URL·모델 ID·숨김 키를 묻고,
계획 진단 뒤 실행을 다시 확인합니다. 설정만 만들려면
`.venv/bin/agent-opt init`을 대화형으로 실행합니다.
데이터셋을 자동 추천하지 않으며, 선택한 CVDP/Verilog-Eval은 고정 버전 소스·데이터·OSS 평가 환경을
자동 준비합니다(첫 실행에는 다운로드·Docker 빌드가 걸릴 수 있습니다). 사용자 데이터셋도 별도의
채점기를 지정해 사용할 수 있습니다.

### 저장소 없이 wheel에서 ACE 예제 선택

Python 3.11+, Git, uv, Docker Engine/Compose가 필요합니다. 제공받은 wheel을 가상환경에
설치한 뒤 **새 작업공간**을 지정하세요. macOS Docker Desktop은 해당 작업공간을 컨테이너에
공유할 수 있어야 하므로 홈 디렉터리처럼 공유된 경로를 사용합니다.

```bash
python3 -m venv "$HOME/agent-opt-env"
"$HOME/agent-opt-env/bin/python" -m pip install /path/to/agent_optimizer-0.3.0-py3-none-any.whl
"$HOME/agent-opt-env/bin/agent-opt" tui  # 3번 ACE-RTL + CVDP 선택: 준비 → 모델 입력 → 실행
```

TTY 없는 자동화에는 다음 앱 명령을 사용합니다. 모델 키·기본 URL은 실행 환경/credential store에 설정하세요.

```bash
"$HOME/agent-opt-env/bin/agent-opt" init --profile ace-rtl --workspace "$HOME/agent-opt-ace"
"$HOME/agent-opt-env/bin/agent-opt" prepare "$HOME/agent-opt-ace/experiment.toml"
"$HOME/agent-opt-env/bin/agent-opt" run "$HOME/agent-opt-ace/experiment.toml"
```

선택적 `doctor --plan "$HOME/agent-opt-ace/experiment.toml" --json`은 준비 전
`integration.prepare=blocked`, 준비 뒤에는 정적 계획 검사가 `ready=true`로 바뀝니다.
`prepare`는 고정 Git 소스·CVDP 데이터·별도 Python driver·Docker
이미지를 준비하고 실제 도구를 검사합니다. 검증한 캐시만 재사용하려면 `prepare ... --offline`을
사용하세요. `run`은 준비되지 않은 자산을 자동 설치하지 않으며, 모델 키가 없으면 명시적으로
실패합니다. TUI에서는 필요한 모델 값을 세션에만 입력하며 자동 설치·성공 대체는 하지 않습니다.
다른 Agent의 CVDP만 사용하려면 사용자 `--agent`와 `--dataset cvdp`를 지정하고,
사용자 `tasks.json`에는 `--evaluator file.py:Symbol`을 따로 지정합니다. 서로 다른
평가기 점수를 직접 합산하지 않습니다.

### 모델·Docker 없이 기본 동작 확인

프로젝트 루트에서 다음 **합성 fixture**를 실행하면 설치부터 보고서까지 확인할 수 있습니다.
첫 `setup --core`는 자체적으로 코어 doctor와 7-trial 최소 데모도 실행합니다.

```bash
make setup-core
make help                         # 개발환경 명령
.venv/bin/agent-opt --help        # 실제 사용자 명령
.venv/bin/agent-opt datasets list
.venv/bin/agent-opt init --name my-fixture \
  --agent examples/minimal/agents/solo \
  --command '{python} {agent_dir}/src/fixture_agent.py {task_dir}' \
  --editable configs/strategy.json \
  --dataset examples/minimal/tasks.json \
  --evaluator examples/minimal/evaluator.py:TextFixtureEvaluator \
  --optimizer baseline --yes
.venv/bin/agent-opt doctor --plan runs/configs/my-fixture/experiment.toml --json
.venv/bin/agent-opt run runs/configs/my-fixture/experiment.toml
# 위 run 출력의 run_dir 값으로 <run-id>를 대체해 HTML을 재생성하려면:
.venv/bin/agent-opt report "runs/<run-id>" --html
```

`datasets list`에는 준비된 합성 `sample_text`도 보입니다. `doctor --plan`의 JSON에
`"scope": "plan", "ready": true`가 표시되고, `run`은 진행 상황과 함께
`"status": "completed", "trials_used": 2` 및 `run_dir`을 출력해야 합니다.
`run_dir/report.html`은 **run이 이미 생성**하므로 마지막 `report --html`은 재생성이 필요할 때만
실행합니다. 이 결과는 코어 경로의 연결 검사이며 모델 최적화 성능을 뜻하지 않습니다.
같은 절차를 다시 따라 할 때는 `--name`과 이후의 `runs/configs/<name>/experiment.toml`을
새 이름으로 바꾸세요. 이미 생성된 설정은 덮어쓰지 않습니다.
대화형 경로는 TTY에서 `.venv/bin/agent-opt tui`(기존 실험 또는 새 실험)나
`.venv/bin/agent-opt init`(새 설정만 생성)으로 열 수 있습니다.

실제 Agent는 `--agent <로컬 소스>` 또는 `--agent <Git URL> --revision <전체 commit>`과
선택한 하네스의 실행 방법, 사용 중인 `--prompt-file`, 수정 허용 `--editable` 범위를 연결합니다.
`command` 하네스에만 실행 argv가 필요합니다. Agent 명령에 `--input` 옵션이 있으면
`--command 'python3 agent.py --input {task_dir}'`를 사용할 수 있습니다. 인용은 argv로 분리하되
셸 확장·파이프·리다이렉션을 실행하지 않습니다.
OpenCode·ACE처럼 실행을 하네스가 정의한 경우 명령을 지정하지 않으며, ACE의 Docker·플러그인
프로필은 `examples/ace-rtl/experiment.toml`에서 재사용합니다. 이 고정 프로필은 TUI와
`agent-opt run`에서 예제의 `live` 준비·검사를 거쳐 공식 CVDP 평가까지 실행합니다.
`--optimizer gepa --optimizer meta_harness --optimizer ecdysis`처럼 반복해 독립 stage를 지정할 수 있습니다.
비대화형 `init`에는 `--optimizer`를 명시해야 합니다. 모델 없는 연결 검사에는
`--optimizer baseline`을, 연구 탐색에는 사용할 Optimizer를 직접 선택하세요.
코드 하네스 방식은 실제 실행되는 `.py` 파일이 필요하고, 여러 파일이 일치하면
`--scaffold-file`(GEPA는 `--target-file`)을 지정합니다. 모델 제안에는 `AGENT_OPT_MODEL_BASE_URL`과
`AGENT_OPT_MODEL_API_KEY`를 환경에 설정합니다. 앱 TUI는 값이 없으면 숨김 입력을 받습니다.
`AGENT_OPT_MODEL_ID`는 선택 사항이며 생략하면 `glm5.3-flash`를 사용합니다. OpenCode 하네스의
`AGENT_OPT_MODEL` 선택자는 이 모델 API 설정과 별도입니다.
로컬 `.env`를 사용하는 개발자는 프로젝트 루트에서 `set -a; source .env; set +a`로 현재 셸에
내보낸 뒤 앱 CLI를 실행하세요. 앱은 `.env`를 자동으로 찾거나 키를 실험 파일에 저장하지 않습니다.
기존 `MODEL_*` 변수와 `init --argv`는 더 이상 사용하지 않습니다. Agent 명령은
`--command`에 인용 가능한 명령 문자열로 입력합니다.
자격증명은 생성 설정에 저장하지 않습니다.

`--dataset cvdp`, `--dataset verilog-spec`, `--dataset verilog-completion`이나
`--dataset <내 tasks.json> --evaluator <file.py:Symbol>`을 지정합니다.
사용자 evaluator가 `passed` 외 지표를 보고할 때는 `--metric <지표 이름>`과
`--direction maximize|minimize`를 지정합니다. 기본 9개 과제를 train/validation/test로 고르게
샘플링하며 `--max-tasks`, `--max-trials`, `--max-wall-time-seconds`,
`--trial-timeout-seconds`로 범위를 조절할 수 있습니다.
여러 `--dataset`이면 각 데이터셋의 독립 실험을 만들어
`agent-opt run-session "runs/configs/<name>/session.json"`으로 실행합니다.
데이터셋별 독립 프로세스가 기본 최대 2개까지 동시에 실행되고, `run-session --jobs 1`은 순차 실행,
`--jobs N`은 동시 실행 상한을 조절합니다. TUI의 복수 데이터셋 실행도 기본 2개를 사용합니다.
TTY에서는 데이터셋마다 대기·실행·완료 상태와 현재 과제·경과 시간을 한 화면에 표시하고,
리다이렉트 시에는 데이터셋 번호가 붙은 진행 기록을 stderr에 남깁니다. 완료 후 각 데이터셋의
독립 `report.html`이 세션 index에 연결되며,
서로 다른 채점기의 점수를 직접 한 순위로 합치지 않습니다. 팀의 새 데이터셋/하네스/Optimizer는
`experiments/<team>/`에서 구현하고 `src/agent_optimizer/registry.py`에 ID→구현 파일을 등록합니다.
CLI 선택지·설치 entry point 변경은 필요 없습니다.
세 연구 알고리즘은 이 저장소의 **자체 메서드 구현**으로, upstream 논문 실험 재현과 구분합니다.

## 개발환경 빠른 시작

Mac/Ubuntu와 **Git**부터 준비하고 프로젝트 루트에서 실행하세요. 코어 개발에는 Docker·Compose·Buildx나
모델 키가 필요 없습니다. uv가 없으면 installer 다운로드용 curl 또는 wget이 필요합니다.
프록시·추가 CA가 필요한 환경은 먼저 [네트워크 설정](docs/network.md)을 적용하세요.

```bash
make help                         # 설치 없이 개발 명령 확인
make setup-core                   # frozen 개발 도구 + 코어 진단 + 첫 최소 데모
make doctor-core                  # 코어만 읽기 전용 진단
make menu                        # 1/2번: 코어 설치/진단, 3번: fixture 테스트
make demo                        # 비대화형 최소 데모
# make/Python이 없으면 시작 명령 대신:
sh scripts/bootstrap.sh setup --core
```

CLI·TUI·`make`의 안내/진단은 터미널에서 상태별 색상으로 강조합니다. 출력을 리다이렉트하거나
`NO_COLOR=1`을 설정하면 색상이 꺼지며, JSON 출력에는 색상 코드를 넣지 않습니다.

개발 명령(`make`)과 사용자 CLI/TUI·리포트는 **한국어가 기본**입니다. 영어 문구가 필요하면
`AGENT_OPT_LANG=en make help`, `AGENT_OPT_LANG=en .venv/bin/agent-opt tui`처럼 실행하세요.
실행 언어는 `summary.json`의 `report_language`에 기록되어 `report.md`·`report.html`을 재생성해도
유지됩니다. 기존 실행을 포함해 한 번만 다른 언어로 다시 만들 때는
`AGENT_OPT_LANG=en .venv/bin/agent-opt report "runs/<run-id>" --html`을 사용합니다.
명령·옵션·컴포넌트 ID와 `--json` 필드·상태 값, 외부 도구/Agent 원본 로그는 영어로 유지합니다.

`setup --core` 출력의 `"status": "ready", "scope": "core"`와
`make doctor-core`의 `코어 개발 환경: 준비됨`을 확인합니다.
`make demo` 출력의 `"status": "completed", "trials_used": 7`과 `run_dir`을 확인하고
해당 `run_dir/report.html`을 열면 기본 실행까지 검증할 수 있습니다.
`setup --core`는 기존 uv 설치 경로를 사용해, uv가 없으면 0.10.7을 로컬에 설치하고
Python 3.12·frozen 개발 의존성을 `.venv`에 준비합니다. **최초 준비에는 의존성 다운로드가 필요할 수 있지만,
최소 데모와 로컬 HTTP fixture 실행은 외부 모델·Docker를 사용하지 않습니다.**
코어 준비는 ACE/CVDP 소스·데이터·이미지를 준비하지 않으며 모델/평가 환경의 준비 완료를 뜻하지 않습니다.
데이터셋은 직접 선택하여 `sh scripts/bootstrap.sh setup --dataset verilog-spec` 또는
`.venv/bin/agent-opt datasets prepare verilog-spec`으로 별도 준비하고
`sh scripts/bootstrap.sh doctor --dataset verilog-spec --json`으로 진단합니다.
`agent-opt doctor --dataset ID --json`도 같은 선택 자산을 읽기 전용으로 점검합니다.
`--core`와 `--dataset`은 함께 쓸 수 없습니다. 아무 옵션 없는 setup/doctor는 기존 **ACE 전체** 경로입니다.
설치 로그는 `external/setup-logs/`에 보존합니다. 완료 시 출력된
`runs/<run-id>/report.html`, `report.md`, `summary.json`을 확인하세요. 최소 데모는 두 합성 Agent·한 repair stage·7 trial(solo 4/team 3)의
연결 검증이며 실제 모델 성능 수치가 아닙니다. API 키는 **live 및 명시적 모델 연결 검사**에 필요합니다.

메뉴는 Python 3.11+와 TTY가 필요하며 모델 토큰은 숨김 입력, 설정은 세션에만 유지됩니다.
**7번은 선택적 ACE 전체 환경 준비**이며 4/5번의 실제 모델·평가 실행 전에 사용합니다.
**8번은 일반 Agent 최적화 TUI**로 `.venv/bin/agent-opt tui`를 열고 기존 실험과 새 실험 중 선택합니다.
[메뉴·OS별 설치 안내](docs/development.md#번호-메뉴)

| 명령 | 용도 |
|---|---|
| `make` / `make help` | 설치·Docker 조회 없는 도움말 |
| `make setup-core` | 코어 준비·진단·합성 데모 |
| `make doctor-core` / `sh scripts/bootstrap.sh doctor --core --json` | 코어만 읽기 전용 진단 / `scope=core` 단일 JSON |
| `sh scripts/bootstrap.sh setup --core --offline` | 준비한 uv/Python/패키지 cache만 재사용 |
| `sh scripts/bootstrap.sh setup --dataset cvdp --offline` | 검증된 선택 CVDP 평가 자산만 재사용; ACE Agent 이미지 준비는 별개 |
| `sh scripts/bootstrap.sh doctor --dataset verilog-spec --json` | 선택 데이터셋 준비 상태 읽기 전용 진단; Docker/고정 이미지 누락도 실패로 보고 |
| `.venv/bin/agent-opt doctor --plan PATH --json` | Agent/컴포넌트 선언·선택 자산·예산·필요한 모델 설정의 정적 점검 |
| `make setup` / `make doctor` | 선택적 ACE 전체 준비 / 전체 진단 (`--json` 지원) |
| `make lint` / `make test` / `make demo` | `.venv`에서 일상 개발 검사·데모 |
| `sh scripts/bootstrap.sh setup --offline` | ACE 전체 자산·캐시 검증 및 재사용 |
| `make smoke` | 모델 호출 없는 실제 RTL/CVDP 정답·오답 검사 |
| `make live` | 설정한 OpenAI 호환 모델로 ACE 지침 최적화 반복 |

`live`는 실행 중인 데이터셋·단계·과제·경과 시간을, `smoke`는 실제 도구·toy·공식 평가의
검사별 경과 시간을 stderr에 표시합니다. `setup`·선택 데이터셋 준비·모델 진단과 보고서 재생성도
오래 걸리는 단계의 상태를 표시합니다. TTY에서는 갱신되는 상태 화면, 리다이렉트할 때는 단계별
시작·종료 줄을 남기며 JSON stdout은 그대로 파싱할 수 있습니다.
이미 시작한 실행에는 새 표시가 적용되지 않습니다.

make가 없으면 모든 명령을 `sh scripts/bootstrap.sh <명령> [옵션]`으로 실행합니다.
가상환경 활성화·PATH·offline 복구는 [개발환경 가이드](docs/development.md), 일상 작업과
담당 영역은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

## 담당별 시작

위 빠른 시작 → [Optimizer / Harness / 외부 Agent 템플릿](experiments/README.md) →
[관련 공통 계약](docs/adding-components.md) 순서로 시작하세요. 팀 코드는 `experiments/<team>/`에 둡니다.
외부 연동 변경 시 [SOURCES](docs/SOURCES.md)를 대조하며 [날짜별 검증](docs/verification.md)은 과거 증거입니다.
현재 상태·후속 순서는 [status](docs/status.md) / [NEXT_STEPS](docs/NEXT_STEPS.md), 개발 규칙은 [AGENTS](AGENTS.md)입니다.

도메인 코드는 `examples/`에 두고, 슬롯·미검증 통합을 완료로 표현하지 않습니다.
외부 기술 판단은 고정 출처와 실제 설정을 대조하며 문서 정리를 이유로 upstream 버전을 자동 갱신하지 않습니다.

## 코어만 실행: API·Docker 없는 최소 데모

Python 3.11+ / Mac·Linux 기준, 프로젝트 루트에서 실행합니다.

프록시·추가 CA가 필요한 환경은 먼저 [선택적 네트워크 설정](docs/network.md)을 적용하세요.
설정하지 않으면 기존 직접 연결 방식을 사용합니다.

```bash
make setup-core
make doctor-core
make demo
```

uv 없이 실행하려면 Python 3.11+ 가상환경에 `python -m pip install -e .`로
`pyproject.toml`의 런타임 의존성을 먼저 설치하세요. 아래 `python3`는 해당 환경의 Python입니다.
`setup --core`로 준비한 뒤에는 부모 shell이 자동 활성화되지 않으므로 `.venv/bin/python`을 사용하세요.

```bash
PYTHONPATH=src python3 -m agent_optimizer run examples/minimal/experiment.toml
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

`runs/<run-id>/report.html`, `report.md`, `summary.json`, `events.jsonl`을 확인하세요.
최소 데모는 두 개의 독립적인 합성 Agent를 실행합니다. 첫 Agent는 설정 변경 후 검증 점수가
0 → 1로 바뀝니다. 이는 연결 검증을 위한 **의도적으로 만든 결과**이며 RTL/LLM 성능 개선 증거가 아닙니다.

## 폴더

```text
src/agent_optimizer/       공통 계약·실험 실행·소스 스냅샷·결과
  optimizers/             내장 baseline / file_variants / GEPA / Meta-Harness / Ecdysis
  harnesses/              command / OpenCode
examples/
  minimal/                즉시 실행하는 합성 데모, 두 Agent
  rtl-debugger/           작은 RTL Agent + OpenCode + Yosys/Icarus 평가
  ace-rtl/                외부 ACE-RTL + OpenCode 스킬 + 공식 CVDP 평가
  benchmarks/             선택형 CVDP·Verilog-Eval Dataset/Evaluator와 고정 평가 환경
experiments/              팀별 Dataset / Optimizer / Harness / 외부 Agent 파일 플러그인
  dataset-template/       팀 Dataset provider와 중앙 등록 안내
scripts/                  setup / doctor / smoke / live 및 최소 데모 명령
docs/                     설계·확장·구현 상태
tests/                    의미 있는 경계·실험 검증
external/ datasets/ runs/ 다운로드·데이터·결과, Git 제외
```

## 구현 범위

- 실행 가능: 외부 Git 고정 커밋/로컬 소스 스냅샷, 복수 Agent × Harness 실험, baseline,
  여러 독립 파일 Optimizer 비교, 단순 LLM 피드백 반복, validation 선택 후 test 평가.
- 모든 stage는 baseline에서 시작하며 train 이력은 baseline과 자기 stage만 포함합니다.
  기본 최종 비교는 모든 stage winner, 선택은 lexicographic keep=1·mean/sum입니다.
- OpenCode 및 Docker 실행 어댑터와 예제 전용 Icarus/CVDP 연결 코드를 포함합니다.
- GEPA/Meta-Harness/Ecdysis의 독립 검색 루프와 팀 파일 플러그인을 제공합니다.
  GEPA의 validation Pareto 선택은 유지하며, 병합(`merge=true`)은 train 전용 수정 근거를
  보장할 때까지 명시적으로 실패합니다. 미구현 템플릿과 고급 조합/선택은 [FUTURE](docs/FUTURE.md)에 있습니다.
- Claude Code / Codex / OpenAgent는 확장 규약만 제공합니다. 별도 구현 완료로 표시하지 않습니다.
- Mac Docker ARM64와 native Ubuntu x86_64에서 공식 CVDP 정답·오답과 host-Docker toy 평가를 실행했습니다.
  실제 도구 테스트 9개와 전체 smoke가 통과했습니다. 입력 제한은 필수이며 합성만으로 임의 RTL을
  정화하지 않습니다. `deepseek-flash` 모델과 ACE/OpenCode 스킬 프로필의 두 과제·4 trial 연결은
  Mac ARM64에서 실행했으며 실제 성능 향상이나 native ACE 검증은 아닙니다. [검증 기록](docs/verification.md)

## 선택적 ACE 전체 준비와 실제 데모

[ACE-RTL 예제](examples/ace-rtl/README.md)는 기본 3회 **train 평가 → ACE 지침 수정 → 재평가** 후
별도 validation으로 후보를 선택합니다. 기본 모델은 `glm5.3-flash`이며 설정으로 교체합니다.
Python 3.11+, uv, Git, Docker Engine/Compose가 필요합니다. Ubuntu 시스템 CA 사용 시 Buildx도 필요합니다.
호스트에 OpenCode·시뮬레이터를 별도로 설치하지 않습니다.
기본 `setup`/`doctor`는 기존 전체 경로입니다. 첫 이미지 컴파일은 수십 분 걸릴 수 있습니다.
`--core`는 setup/doctor에서만 지원하며 `--platform` 또는 `doctor --model`과 함께 사용할 수 없습니다.

```bash
# 개발용 비대화형 명령에서는 실제 기본 주소·토큰을 셸/credential store에서 설정
export AGENT_OPT_MODEL_BASE_URL=https://model.example/v1
export AGENT_OPT_MODEL_ID=glm5.3-flash
# AGENT_OPT_MODEL_API_KEY도 export. .env는 자동 로딩하지 않음.
make setup                         # Python 환경·소스·데이터·두 이미지 일괄 준비
make doctor                        # 준비 상태와 실패 조치; 모델 호출 없음
make smoke                         # 모델 키 없이 실제 RTL/CVDP 정답·오답 검증
# 앱에서 같은 ACE 예제를 실행하려면:
.venv/bin/agent-opt tui            # 1번 기존 실험 → examples/ace-rtl/experiment.toml
.venv/bin/agent-opt run examples/ace-rtl/experiment.toml
# 개발 중 실제 모델/컨테이너 연결만 분리 진단하려면:
sh scripts/bootstrap.sh doctor --model
```

ACE 프로필을 선택한 두 `agent-opt` 경로는 예제의 `live` 진단·환경 연결·공식 평가를 그대로
실행합니다. `doctor --plan`은 정적 검사이므로 모델 연결이나 공식 평가 성공을 보증하지 않습니다.
`make setup-core`·`make demo`는 개발환경/합성 검사, `make setup`·`make doctor`·`make smoke`는
모델 없는 ACE 평가 실행환경 검사, `doctor --model`과 ACE `live`는 실제 모델을 사용하는
단계입니다. 자격증명·고정 자산이 없으면 실행은 실패하며 다른 경로의 성공으로 대체하지 않습니다.

Ubuntu에서는 기존 proxy 환경과 `/etc/ssl/certs/ca-certificates.crt`를 사용합니다.
명시적 `AGENT_OPT_CA_BUNDLE`이 우선합니다. [proxy/CA 안내](docs/network.md)를 확인하세요.
`doctor --json`은 개발 진단용 결과와 실패 종료 코드 2를 제공합니다.
`agent-opt doctor --dataset ID`와 `--plan PATH`는 각각 선택 데이터셋과
실험 선언의 읽기 전용 준비 점검입니다. `--plan`은 실제 Agent 산출물·평가기/모델 성공을 보증하지 않습니다.
실제 모델 연결은 명시적 `--model`에서만 호출합니다. **ACE 전체 준비 검사는 위 `make doctor`**를 사용합니다.
uv/Python이 없으면 `sh scripts/bootstrap.sh setup`이 프로젝트 전용 환경을 준비합니다.

`--platform`을 생략하면 빌드 전에 Docker daemon의 native `linux/amd64` 또는 `linux/arm64`를
선택해 기록합니다. 명시적 `--platform`은 그대로 사용하며 미지원 architecture는 오류입니다.
빌드 실패 후 다른 architecture로 자동 재시도하지 않습니다. 예: `sh scripts/bootstrap.sh setup --platform linux/arm64`.
`sh scripts/bootstrap.sh setup --offline`은 검증된 cache만 재사용합니다.
Python 3.12 CVDP driver는 예제의 [전이 의존성 lock](examples/ace-rtl/environment/requirements-cvdp-py312.txt)으로
동기화하며 lock hash와 실제 설치 목록을 기록합니다. 이전 환경은 한 번 online setup으로 갱신하세요.
상용 EDA 도구·라이선스 설정은 제공하지 않습니다. 플랫폼별 검증/차단 결과는 [검증 기록](docs/verification.md)을 따릅니다.

PR CI는 Python 3.11/3.12와 Ubuntu native Yosys/Icarus로 코어·실제 RTL·패키징을 검사합니다.
공식 Docker 통합은 기존 `ci.yml`의 수동 `official_cvdp` 입력으로 실행합니다. 두 경로 모두 모델 호출은 없습니다.
`10baa46`의 Ubuntu 코어 CI와 공식 setup/offline/smoke·provider config 검사가 통과했습니다.
첫 공식 smoke의 FROM 참조 실패와 수정 후 native 정답·오답 근거는
[최종 재검증 기록](docs/verification.md#2026-09-20-native-ubuntu-repeat--passed)에 보존합니다.
브랜치 실행 명령과 준비 조건은 [CONTRIBUTING.md](CONTRIBUTING.md#ci와-pr-병합)를 참고하세요.

## 다른 팀에 적용

1. `experiments/customer-template/` 복사.
2. Agent 소스 repo/고정 커밋과 editable 범위 설정.
3. Harness 명령 또는 어댑터, 평가 함수 연결.
4. 작은 baseline을 확인한 후 담당 Optimizer 연결.
5. 동일 데이터·모델·예산으로 비교하고 diff와 지표 공유.

[확장 가이드](docs/adding-components.md) · [구조](docs/architecture.md) · [팀 개발](CONTRIBUTING.md)
알고리즘 담당자는 [API-free 회귀·최소 구현](experiments/optimizer-template/README.md)부터 확인하세요.
[단순 LLM Optimizer](experiments/simple-feedback/README.md)는 모델 준비 후 선택적으로 연결합니다.
새 CLI 연결은 [Harness 템플릿](experiments/harness-template/README.md)을 사용합니다.

## 결과와 제한

미수집 토큰/비용은 `null`입니다. OpenCode root 이벤트에서 관측된 사용량은 별도 partial 지표이며
sub-agent까지 합산된 Agent 전체 사용량으로 표시하지 않습니다.
실험 trial 수·벽시계·trial timeout을 제한합니다. 엄격한 API 비용 상한/호출 수 제한, 재시작 resume,
단일 실험 안의 과제·stage 병렬 실행은 아직 없습니다. 비용 상한은 사용하는 provider/proxy에서도 설정하세요.

코어 플러그인은 신뢰한 팀 코드로 실행합니다. local 모드는 OS 격리가 없으며 개발용입니다.
Docker Agent는 해당 trial workspace와 설정한 경우 읽기 전용 CA bundle만 마운트하고,
평가 데이터나 Docker socket을 전달받지 않습니다.
평가 데이터는 Agent workspace와 분리합니다. 공식 Docker 평가기는 호스트가 실행합니다.
