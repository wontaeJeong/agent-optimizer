# 개발 명령과 Agent CLI의 시작 흐름 개선

## 배경과 선택

`make setup ARGS="--core"`는 짧은 개발 명령에도 변수를 써야 한다. `agent-opt init`은
`--command-json`을 모든 하네스에 요구하고, `agent-opt tui`는 항상 새 실험을 만들어 즉시 실행한다.
그러나 `examples/ace-rtl/experiment.toml`은 Git Agent 소스, `ace_opencode` 파일 플러그인,
Docker 프로필과 평가기를 이미 함께 선언한다. 해당 하네스는 OpenCode 실행 argv를 직접 구성하며
`harness.command`를 사용하지 않는다. 현재 `init`의 로컬 하네스 생성 경로로 이 프로필을 재현할 수 없다.

선택지는 (1) 모든 Agent에 명령 문자열을 요구하는 기존 `init` 단축, (2) 실행 명령을 자동 추측하는
진입점 탐지, (3) 준비된 실험을 재사용하고 새 Agent만 하네스별로 안내하는 흐름이다.
(1)은 ACE 사례를 해결하지 못하고 (2)는 임의 Agent의 실행·평가 계약을 추측한다. (3)을 채택한다.
ACE 예제는 OpenCode **스킬 프로필**이지 native ACE runner가 아니며, 이 UX 변경으로 지원 범위가
확장된 것처럼 표현하지 않는다.

## 사용자 흐름

1. `make setup-core`, `make doctor-core`를 일반적인 첫 개발 명령으로 제공한다. 기존
   `make setup`, `make doctor`, `ARGS=...` 경로와 직접 `sh scripts/bootstrap.sh <명령> [옵션]`은
   유지한다. `--dataset`, `--offline`, `--model`, `--platform`처럼 조합이 다양한 옵션은 직접
   bootstrap 명령을 예시로 제시한다. `make setup --core`처럼 Make 옵션으로 해석되는 문법은 약속하지 않는다.
2. `agent-opt tui` 첫 화면에서 **기존 실험 실행** 또는 **새 실험 만들고 실행**을 사용자가 선택한다.
   기존 경로에서는 사용자가 `experiment.toml` 경로를 입력한다. 해당 파일의 읽기 전용
   `doctor --plan` 결과와 실행 대상을 보여준 다음 실행 여부를 확인한다. 거절하거나 준비가
   부족하면 실행하지 않으며, 파일·데이터셋·모델을 임의로 교체하거나 자동 설치하지 않는다.
   계획 진단 통과는 실제 모델·Agent·공식 평가 실행 성공을 뜻하지 않는다.
   준비된 예제는 명시적으로 `examples/ace-rtl/experiment.toml`을 지정한다. 스크립트는 기존
   `agent-opt run <experiment.toml>`을 계속 사용할 수 있다.
3. `agent-opt init`을 인수 없이 TTY에서 호출하면 안내에 따라 **새 설정만** 만든다. 데이터셋,
   Agent 소스, editable 경로, 하네스와 Optimizer는 사용자가 명시적으로 선택하며, 확인 전에는
   데이터셋 준비·설정 쓰기·Agent 실행이 없다. 완료 후 생성한 설정 경로와 `doctor --plan`, `run`
   후속 명령을 stderr에 표시하고 stdout의 기존 JSON 결과는 유지한다. `agent-opt tui`의 새 실험
   경로도 동일한 질문/검증을 사용하되 확인 후 생성·실행까지 이어진다. TTY가 없는 `init`은
   기존 명시적 옵션과 `--yes`를 요구한다.
4. 대화형 질문에서 Agent 실행 명령은 선택한 하네스가 `CommandHarness.argv`를 그대로 쓰는
   경우에만 요구한다. 기본 `opencode`는 명령을 묻거나 가짜 명령을 설정에 저장하지 않는다.
   고유 실행 프로필·플러그인 설정을 필요로 하는 하네스는 기존 `experiment.toml` 경로를
   안내하며, 지원하지 않는 자동 설정 생성을 성공으로 처리하지 않는다.

## 비대화형 입력과 계약

- `init --command 'python agent.py --input {task_dir}'`를 `command` 계열 하네스의 간편 입력으로
  추가한다. 따옴표로 묶은 명령 문자열을 argv로 분리해 기존 `harness.command` 배열에 저장하고,
  실행 시에는 기존처럼 `shell=False`를 유지한다. 셸 변수 확장·파이프·리다이렉션은 지원하지
  않는다고 도움말에 적는다. 빈 명령, 잘못된 인용, `--command`와 `--command-json` 동시 지정은
  준비 전에 명확히 거절한다. 대시로 시작하는 Agent 인자는 문자열 안에서 argv 요소로 보존한다.
- 기존 `--command-json`과 인수 있는 `init`의 JSON 출력/종료 코드, 반복 `--dataset`·`--optimizer`,
  `run`·`doctor` 입력/출력은 유지한다. 비명령 하네스에 실행 명령을 강요하지 않되, 그 하네스에
  명령 옵션을 주면 조용히 버리지 않고 거절한다. 명령 필요 여부는 명시된 하네스 구현을 기준으로
  판단한다. 알 수 없는 팀 하네스의 실행 방법은 추측하지 않는다.
- 기존 ACE 프로필의 Docker·플러그인·고정 소스·공식 평가 구성은 `init`에서 재구성하지 않는다.
  새 Agent의 일반 설정 경로와 기존 실험의 실행 경로를 구분한다. 데이터셋 자동 추천, 원본 수정,
  private 평가 자료 노출, 모델 자격증명 저장은 하지 않는다.

## 변경 지점과 검증

- `Makefile`, `scripts/bootstrap.sh` 도움말과 README/개발·사용자 가이드의 첫 실행 명령을
  수정한다. `AGENTS.md`의 코어 시작 명령도 새 별칭으로 맞춘다.
- `src/agent_optimizer/cli.py`의 `tui`/`init` 분기와
  `src/agent_optimizer/setup_wizard.py`의 공통 질문·생성 경계를 정리한다. 새 명령 체계나
  별도 프레임워크를 만들지 않는다.
- `tests/test_dev_onboarding.py`에서 새 Make 별칭의 실제 인수 전달과 기존 경로 호환을,
  `tests/test_cli_experience.py`에서 대화형 두 경로, ACE 설정 선택 시 명령 미요구,
  비대화형 command/opencode 입력과 실패 시 무부작용을 검증한다. 코어 회귀·`make lint`·
  최소 데모와 `git diff --check`를 실행한다. 외부 모델/공식 평가 실행 증거와 구분한다.
- CLI/TUI UX PR에는 기존/변경 후 터미널 화면 캡처와 재현 명령을 포함한다. 캡처가 불가능한
  환경이면 그 이유를 PR에 적는다.
