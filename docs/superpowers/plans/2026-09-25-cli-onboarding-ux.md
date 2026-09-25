# 개발 명령과 Agent CLI 시작 흐름 구현 계획

> **실행 담당:** REQUIRED SUB-SKILL: `superpowers:executing-plans`로 체크박스(`- [ ]`)를 순서대로 실행한다. 각 작업은 작은 회귀 테스트 작성 → 실패 확인 → 최소 구현 → 통과 확인 → 커밋 순서다. 작업 브랜치는 `chore/setup-cli-syntax`다.

**목표:** 개발 환경 명령의 장황한 `ARGS` 입력을 줄이고, 기존 Agent 실험 실행과 신규 Agent 등록을 구분하는 CLI/TUI를 제공한다.

**구조:** Make 별칭은 기존 POSIX bootstrap에 위임한다. CLI는 기존 Typer `init`/`tui`에 분기를 추가하고 기존 wizard의 입력·확인 로직을 공유한다. 실행 명령은 명령 하네스에서만 argv로 저장하며 ACE 프로필은 기존 실험 파일을 그대로 사용한다.

**기술:** GNU/BSD make, POSIX sh, Python 3.11+, Typer, unittest.

**설계:** `docs/superpowers/specs/2026-09-25-cli-onboarding-ux-design.md`.

## 전체 제약

- Python CLI/TUI와 평평한 모듈 구조를 유지하고 새 명령 프레임워크를 추가하지 않는다.
- 데이터셋·Agent 실행 방법·하네스 전용 설정·채점기를 임의로 추측하지 않는다.
- Agent 실행은 argv 배열 및 `shell=False`; shell 문법 실행·자격증명 저장은 금지한다.
- ACE-RTL 예제는 OpenCode 스킬 프로필이며 native ACE 실행으로 표시하지 않는다.
- 기존 `ARGS=...`, `--command-json`, `init` JSON stdout, `run`/`doctor` 호출은 호환한다.
- 사람에게 보이는 신규 문구는 한국어로 작성한다.

## 파일별 책임

- `Makefile`: 일반적인 코어 준비/진단 별칭만 제공하고 기존 bootstrap 위임 유지.
- `scripts/bootstrap.sh`: CLI 도움말의 대표 명령 변경.
- `src/agent_optimizer/setup_wizard.py`: 대화형 Agent/데이터셋/하네스 입력과 재사용 가능한 인수 작성. 명령이 필요한 하네스만 질문.
- `src/agent_optimizer/cli.py`: 비대화형 인수 검증·대화형 `init`/`tui` 분기·기존 계획 진단/확인/실행.
- `examples/ace-rtl/adapter.py`: 준비된 고정 ACE 스킬 프로필을 기존 `live` 명령으로 위임하는 예제 전용 메서드.
- `tests/test_dev_onboarding.py`, `tests/test_cli_experience.py`: 실제 진입점과 계약 경계를 회귀 검증.
- `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `docs/development.md`, `docs/adding-components.md`, `docs/NEXT_STEPS.md`, `website/user/getting-started.md`, `website/developer/validation.md`: 사용자 시작 예시와 의미를 일치시킴.

### 작업 1: Make 코어 명령 별칭

**파일:** `Makefile`, `scripts/bootstrap.sh`, `tests/test_dev_onboarding.py`.

**입력:** 기존 `sh scripts/bootstrap.sh setup|doctor --core`. **출력:** 같은 argv를 전달하는 `make setup-core|doctor-core`.

- [ ] **1. 실패 테스트:** `BootstrapTests`에서 `make -f <복사된 Makefile> setup-core`와 `doctor-core`가 각각 `arg:setup/doctor`, `arg:--core`를 Python stub에 전달하는지 검사한다. `doctor`는 기존 fake `python3`을, `setup`은 기존 fake `git`/`uv`를 사용한다. 기존 `ARGS` 전달 테스트도 유지한다.
  ```python
  def test_core_make_aliases_forward_core_flag(self):
      self.tool("python3", 'case "$1" in -I) exit 0;; esac\nprintf "arg:%s\\n" "$@" >> "$TRACE"\n')
      result = self.invoke("doctor-core", make=True)
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertIn("arg:doctor\narg:--core\n", self.trace_text())
  ```
- [ ] **2. RED 확인:** `PYTHONPATH=src /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_dev_onboarding.py -q`; `No rule to make target 'doctor-core'`를 확인한다.
- [ ] **3. 최소 구현:** `Makefile`에 두 PHONY 타깃을 두고 기존 makefile 경로 해석과 동일한 방식으로 `sh .../scripts/bootstrap.sh $(@:-core=) --core`에 해당하는 POSIX 명령을 전달한다. `scripts/bootstrap.sh`의 `help()`에서 두 명령을 대표 예시로 사용한다.
  ```make
  .PHONY: setup-core doctor-core
  setup-core doctor-core:
	@makefile='$(subst ','"'"',$(MAKEFILE_LIST))'; makefile=$${makefile# }; \
	sh "$$(dirname "$$makefile")/scripts/bootstrap.sh" $(patsubst %-core,%,$@) --core
  ```
- [ ] **4. GREEN 확인:** 위 테스트와 `make help` 출력에서 두 명령 안내 및 기존 `make doctor ARGS="--core"`가 유지되는지 검사한다.
- [ ] **5. 커밋:** `Makefile`, `scripts/bootstrap.sh`, 테스트만 스테이징해 한국어 메시지로 커밋한다.

### 작업 2: 명령형 하네스에 한정한 CLI 실행 argv

**파일:** `src/agent_optimizer/cli.py`, `src/agent_optimizer/setup_wizard.py`, `tests/test_cli_experience.py`.

**입력:** 선택된 등록 하네스 및 `--command` 또는 `--command-json`. **출력:** 명령형 하네스는 비어 있지 않은 argv, `opencode`는 명령 키 없는 프로필. 팀 커스텀 하네스는 전용 프로필을 요구한다.

- [ ] **1. 실패 테스트:** 기존 로컬 fixture `init`에 `--command '{python} {agent_dir}/src/fixture_agent.py --input {task_dir}'`를 주어 생성된 `harness.toml`의 `command` 배열을 확인한다. `--harness opencode`에서는 명령 옵션 없이 생성하고 `command` 필드가 없는지 확인한다. 양쪽 명령 옵션 동시 사용·비명령 하네스에 명령 입력·빈/미완성 인용은 준비 전에 오류가 나며 새 runs/configs 폴더가 없음을 검사한다.
  ```python
  args = ["init", "--project-root", str(self.root), "--agent", str(self.agent),
          "--dataset", str(self.data), "--editable", "configs/strategy.json",
          "--optimizer", "baseline", "--command",
          "{python} {agent_dir}/src/fixture_agent.py --input {task_dir}", "--yes"]
  self.assertEqual(main(args), 0)
  self.assertEqual(load_experiment(self.root / "runs/configs/solo/experiment.toml")
                   ["_profiles"][0]["command"][-2:], ["--input", "{task_dir}"])
  ```
- [ ] **2. RED 확인:** `PYTHONPATH=src /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -q`에서 `--command` 미지원과 `opencode` 명령 강제 오류를 확인한다.
- [ ] **3. 최소 구현:** `init_command`에 `command: str | None = typer.Option(None, "--command", ...)`를 추가하고 `_dispatch`의 dataset 준비보다 먼저 두 인자 중복/빈 값/인용 오류를 검사한다. `shlex.split`은 argv 파싱에만 사용한다. `CommandHarness.argv`를 그대로 상속한 등록 어댑터는 명령을 요구하고, 내장 `opencode`·`fixture`는 요구하지 않는다. 그 밖의 사용자 전용 하네스 자동 생성은 프로필 구성 안내와 함께 오류 처리한다. `write_experiment`는 명령이 선택되지 않으면 `harness.command`를 쓰지 않는다.
  ```python
  if command_text is not None:
      try:
          command_argv = shlex.split(command_text)
      except ValueError as exc:
          raise ConfigurationError(f"잘못된 Agent 실행 명령: {exc}") from exc
  ```
- [ ] **4. GREEN 확인:** CLI 파일 회귀와 `PYTHONPATH=src /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m agent_optimizer --help`를 확인한다.
- [ ] **5. 커밋:** CLI·wizard·테스트만 스테이징해 한국어 메시지로 커밋한다.

### 작업 3: 대화형 `init`과 기존 실험 TUI 선택

**파일:** `src/agent_optimizer/cli.py`, `src/agent_optimizer/setup_wizard.py`, `tests/test_cli_experience.py`.

**입력:** TTY의 `agent-opt init` 또는 `agent-opt tui`. **출력:** 전자는 새 설정 생성만, 후자는 기존 계획 확인 후 실행 또는 새 설정 생성 후 실행.

- [ ] **1. 실패 테스트:** 입력을 제공하는 `isatty() == True` 스트림으로 `main(["init", ...])`에 응답해 JSON 설정 출력과 실행 없음, `main(["tui", ...])`에 `1`, ACE 파일 경로, `n`을 응답해 `collect_plan()`은 호출되고 `run_experiment()`는 호출되지 않는 것을 확인한다. `doctor --plan`이 `ready=false`를 반환하는 경우와 EOF도 실행/설치하지 않는지 확인한다. 기존 TUI 새 실험 선택의 인수 배열은 기존 wizard 테스트를 재사용한다.
  ```python
  class TerminalInput(io.StringIO):
      def isatty(self):
          return True

  with patch("agent_optimizer.cli.sys.stdin", TerminalInput("1\nexamples/ace-rtl/experiment.toml\nn\n")), \
       patch("agent_optimizer.cli.collect_plan", return_value={"scope": "plan", "ready": True, "checks": []}) as probe, \
       patch("agent_optimizer.cli.run_experiment") as run:
      self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
      probe.assert_called_once()
      run.assert_not_called()
  ```
- [ ] **2. RED 확인:** CLI 회귀에서 새 TUI 선택이 없거나 `init`이 플래그를 요구하는 실패를 확인한다.
- [ ] **3. 최소 구현:** `wizard_arguments(project_root)`는 새 설정 공통 질문을 만들되 `init`에서 최종 문구를 '설정 생성'으로 사용한다. `tui`는 먼저 기존/신규를 선택한다. 기존 경로는 명시된 설정 경로를 `collect_plan`으로 정적 점검하고 요약·확인을 stderr에 표시한 뒤 `load_experiment` → `run_experiment`를 기존 `ProgressDisplay`로 호출한다. 실패·거절은 종료 코드 2, Ctrl-C는 130, 성공은 0. `init`은 TTY에서 아무 선택 옵션이 없을 때에만 wizard → 기존 `_dispatch(init)` 흐름을 재사용하고 stdout에는 JSON만 출력한다.
  ```python
  if args.command == "init" and not args.agent and not args.dataset and sys.stdin.isatty():
      return main(wizard_arguments(args.project_root.absolute()))
  ```
- [ ] **4. GREEN 확인:** 전체 CLI 회귀 및 `PYTHONPATH=src /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest discover -s tests -v`를 확인한다.
- [ ] **5. 커밋:** 두 Python 파일과 테스트만 스테이징해 한국어 메시지로 커밋한다.

### 작업 4: ACE 실사용 프로필의 실행 위임과 환경 검증 경계

**파일:** `src/agent_optimizer/cli.py`, `examples/ace-rtl/adapter.py`, `examples/ace-rtl/experiment.toml`, `tests/test_cli_experience.py`, `docs/verification.md`.

**입력:** ACE 고정 `experiment.toml`의 이미 확인된 선택 및 등록된 `ACEOpenCode` 어댑터. **출력:** 실제 `live` 명령과 동일한 사전 검사·모델·Docker/공식 CVDP 실행 및 자식 종료 코드. 일반 하네스는 기존 runner 사용.

- [ ] **1. RED:** 임시 프로젝트에 `examples/ace-rtl/experiment.toml`과 출력 마커를 기록하는 가짜 `scripts/bootstrap.sh`를 두고 TUI의 기존 실험 선택 및 `agent-opt run`이 `sh scripts/bootstrap.sh live`를 `cwd=project_root`에서 정확히 한 번 실행하는지 검사한다. 가짜 script의 종료 2/3은 그대로 전달하고 일반 최소 fixture는 직접 runner로 완료한다. `collect_plan`은 ACE 자산이 없는 fixture에서만 `ready=true`로 교체하고 실제 자식 프로세스·파일 마커는 교체하지 않는다.
  ```python
  (self.root / "scripts").mkdir()
  (self.root / "scripts/bootstrap.sh").write_text(
      '#!/bin/sh\nprintf "%s:%s\\n" "$PWD" "$1" > "$PWD/launch.marker"\nexit 3\n')
  # TUI에서 ACE 경로를 선택/승인하거나 main(["run", str(ace_experiment)]) 후:
  self.assertEqual((self.root / "launch.marker").read_text().strip(), f"{self.root.resolve()}:live")
  ```
- [ ] **2. RED 실행:** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -k ace -v`에서 기존 TUI가 일반 runner를 호출하는 실패를 확인한다.
- [ ] **3. 최소 구현:** `ACEOpenCode.launch_existing(spec: dict) -> int`는 `_source`가 예제의 정확한 실험 파일인지 확인하고 `subprocess.run(["sh", str(root / "scripts/bootstrap.sh"), "live"], cwd=root, shell=False).returncode`를 반환한다. `cli.py`의 공유 실행 경로는 선택된 등록 하네스 구현에 이 메서드가 있는 경우에만 호출한다. 다중 Agent/하네스와 다른 파일을 ACE 고정 경로로 넘기지 않는다. `--output`은 예제 `live`에 전달되지 않으므로 조용히 무시하지 않고 오류로 거절한다. `live`가 가진 모델/lock·플랫폼·driver·이미지 진단을 CLI에 복사하지 않는다.
  ```python
  adapter = registry.resolve("harnesses", spec["_profiles"][0]["adapter"])
  launcher = getattr(adapter, "launch_existing", None)
  if launcher is not None:
      return launcher(spec)
  return run_experiment(spec, registry, on_event=progress)
  ```
- [ ] **4. 중앙 평가기 재사용:** `doctor --plan examples/ace-rtl/experiment.toml --json`에서 `evaluator.registration`이 정상이어야 한다. 현재 중복된 `[plugins.evaluators] cvdp`와 대응 helper 선언을 지우고 중앙 `PROJECT_COMPONENTS`·`PROJECT_DEPENDENCIES`를 사용한다. 변경 전 실패와 변경 후 성공을 회귀로 검증한다.
- [ ] **5. GREEN/환경 분리:** CLI/어댑터 경계 테스트와 `make lint`를 통과시킨다. 현재 작업 워크트리의 `make doctor-core`와 Docker/ACE 준비 자산의 유무를 확인한다. `make setup` → `make doctor` → `make smoke`를 실제 실행하고 모델 키가 있을 때만 `sh scripts/bootstrap.sh doctor --model` → TUI/CLI 실제 ACE 실행으로 확대한다. 없다면 실제 모델 완료를 기록하지 않는다.
- [ ] **6. 커밋:** CLI·ACE 예제·계약 테스트를 한국어 메시지로 커밋한다.

### 작업 5: 시작 가이드와 최종 UX 검증

**파일:** `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `docs/development.md`, `docs/adding-components.md`, `docs/NEXT_STEPS.md`, `docs/verification.md`, `website/user/getting-started.md`, `website/user/experiment.md`, `website/developer/validation.md`, `examples/minimal/README.md`, `src/agent_optimizer/cli.py`(도움말 문구), `.github/workflows/ci.yml`(실행환경 검사 구분 필요 시).

**입력:** 새 Make 별칭과 명령/기존 계획 분리. **출력:** 복사 가능한 명령과 ACE 예제 경계 안내.

- [ ] **1. 실패 검사:** README/가이드의 첫 설치와 `agent-opt --help`에서 여전히 `ARGS="--core"`를 권장하는 위치를 확인하고, `sh scripts/bootstrap.sh setup --core`·기존 ARGS 경로를 사용하는 자동화는 유지할 목록을 만든다.
- [ ] **2. 문서·도움말 갱신:** 첫 시작은 `make setup-core` → `make doctor-core` → `agent-opt tui`(기존 ACE 선택) 또는 `agent-opt init`(새 Agent) → `doctor --plan` → `run` 순서로 적는다. ACE는 `make setup`·`make doctor`로 고정 자산을 준비하고 `examples/ace-rtl/experiment.toml`을 명시적으로 선택해 같은 `live` 경로에서 실제 실행하게 한다. 코어 검사/공식 평가 smoke/모델 live를 별개 증거로 표기한다. 인수 조합 예시는 직접 bootstrap 구문, JSON argv는 호환 예시, 새 `--command`는 명령형 하네스에만 사용한다고 적는다. 참조된 기타 온보딩 문서도 동일한 대표 명령으로 맞춘다.
  ```text
  make setup-core
  make doctor-core
  .venv/bin/agent-opt tui
  # 준비된 ACE 프로필: examples/ace-rtl/experiment.toml
  ```
- [ ] **3. 검사:** 관련 unittest, 전체 unittest, `PYTHONPATH=src /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml`, `make lint`, `git diff --check`를 실행하고 실제 통과 범위를 기록한다. `make setup`/외부 모델·Docker는 UX 변경 자체의 회귀 증거로 사용하지 않는다.
- [ ] **4. 화면 캡처·커밋:** 이전/변경 후 도움말 또는 TTY 화면을 캡처하고 PR에 재현 명령을 기록한다. 캡처할 수 없으면 그 이유를 기록한다. 문서·도움말만 스테이징해 한국어 메시지로 커밋한다.

## 완료 절차

- [ ] 작업 브랜치의 전체 변경·커밋·검증 결과를 확인한다.
- [ ] 브랜치를 푸시하고 기존 PR이 있으면 반영, 없으면 PR을 생성한다. CLI/TUI 변경 전후 캡처와 재현 방법을 본문에 포함한다.
- [ ] 기본 디렉터리가 `main`인지 `git status --short --branch`와 `git worktree list`로 확인하고 PR URL을 보고한다. 병합은 사용자 승인 후에만 한다.
