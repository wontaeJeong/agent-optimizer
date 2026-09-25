# 독립 설치 코어 CLI 구현 계획

> **실행 담당:** REQUIRED SUB-SKILL: `superpowers:executing-plans`. 체크박스를 순서대로 실행하고 각 코드 변경은 실패 회귀 → 최소 구현 → 성공 검증 → 커밋으로 마친다.

**목표:** wheel만 설치한 사용자도 저장소 밖에서 CLI/TUI 목록과 사용자 Agent·명시적 evaluator 실험을 실행한다.

**구조:** 프로젝트 전용 Python 파일 등록은 명시적인 소스 checkout에서만 로드하고, 설치 패키지의 조회용 데이터셋 항목은 import가 없는 카탈로그로 제공한다. 범용 실행기·계약은 그대로 사용한다. 이후 ACE/CVDP 선택형 연동은 별도 구현 계획에서 이 기반에 연결한다.

**기술:** Python 3.11+, Typer, setuptools wheel, unittest, `venv`.

**설계:** `docs/superpowers/specs/2026-09-25-standalone-cli-selected-integrations-design.md` 중 설치 패키지 독립성과 사용자 정의 Agent/데이터셋 경계.

## 전체 제약

- 제품은 범용 Agent Optimizer이며 ACE-RTL/CVDP 의존성은 `examples/`에 둔다.
- 알고리즘 간 직접 호출·자동 데이터셋 추천·없는 기능의 baseline 대체를 하지 않는다.
- Agent 실행은 argv 배열과 `shell=False`; 자격증명은 환경/credential store에만 둔다.
- wheel의 기능 검사는 저장소 밖에서 `PYTHONPATH` 없이 수행하고 실제 `init`·`run`·`report`까지 확인한다.
- 기존 소스 checkout의 `experiments/<team>/` → `PROJECT_COMPONENTS` 등록과 문서화된 `--project-root` 사용은 유지한다.
- 사람에게 보이는 문구는 한국어로 쓴다.

## 파일별 책임

- 새 `src/agent_optimizer/catalog.py`: 선택 가능한 첫 데이터셋의 이름·설명·준비 필요 여부만 보유. 조회 시 플러그인 실행 금지.
- `src/agent_optimizer/registry.py`: 소스 checkout의 파일 등록과 설치된 기본 알고리즘/하네스를 분리.
- `src/agent_optimizer/cli.py`, `src/agent_optimizer/setup_wizard.py`: 외부 작업공간에서 목록·사용자 데이터셋·Agent 흐름 유지.
- `src/agent_optimizer/readiness.py`: 프로젝트 등록 확인을 명시적으로 선택한 파일에만 적용.
- `tests/support.py`, `tests/test_cli_experience.py`, 새 `tests/test_installed_cli.py`: checkout fixture와 bare 프로젝트의 행동 구분.
- `.github/workflows/ci.yml`: 기존 wheel 설치 단계 다음에 소스 밖 기능 smoke 실행.

---

### 작업 1: 저장소 없는 Registry와 목록 조회

**파일:** 새 `src/agent_optimizer/catalog.py`, 수정 `src/agent_optimizer/registry.py`, `src/agent_optimizer/cli.py`, `tests/support.py`, `tests/test_cli_experience.py`.

**입력:** `Registry.load_project(root: Path)`와 `agent-opt datasets list --project-root PATH`. **출력:** 빈 프로젝트에서 저장소 파일 조회 없이 내장 하네스/Optimizer와 준비 전 선택형 데이터셋 목록. 실제 source checkout에서는 `PROJECT_COMPONENTS` 등록을 유지.

- [ ] **1. RED:** 일반 임시 디렉터리에서 `main(["datasets", "list", "--project-root", path])`가 ACE/CVDP·Verilog-Eval 선택형 ID를 출력하고 디렉터리에 파일을 만들지 않는 회귀를 작성한다. 기존 `test_project()` fixture는 실제 소스 checkout을 표시하도록 `pyproject.toml`을 복사한다. 누락된 선택형 구현은 목록 출력만 허용한다.
  ```python
  with tempfile.TemporaryDirectory() as directory:
      output = io.StringIO()
      with contextlib.redirect_stdout(output):
          self.assertEqual(main(["datasets", "list", "--project-root", directory]), 0)
      self.assertEqual({row["name"] for row in json.loads(output.getvalue())},
                       {"cvdp", "verilog-spec", "verilog-completion"})
      self.assertEqual(list(Path(directory).iterdir()), [])
  ```
- [ ] **2. RED 확인:** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -k test_wheel_catalog_without_repository -v`; 현재 `plugin_files`가 `examples/` 누락으로 실패해야 한다.
- [ ] **3. 최소 구현:** `catalog.py`의 `DATASETS`는 선택형 이름과 `task_form`·`evaluator`·`requires_preparation=True`만 가진다. `registry.py`에 `is_source_checkout(root: Path) -> bool`을 두어 `pyproject.toml`의 `[project].name == "agent-optimizer"`일 때만 `PROJECT_COMPONENTS` 파일을 로드한다. `cli.py`의 목록은 실제 provider 결과와 카탈로그를 ID 기준으로 합치되 중복을 조용히 덮지 않는다.
  ```python
  def is_source_checkout(root: Path) -> bool:
      marker = root / "pyproject.toml"
      try:
          return marker.is_file() and read_toml(marker).get("project", {}).get("name") == "agent-optimizer"
      except (OSError, ValueError, TypeError, AttributeError):
          return False

  def load_project(self, root: Path) -> None:
      if not is_source_checkout(root):
          return
      plugin_files(root, PROJECT_COMPONENTS, PROJECT_DEPENDENCIES)
      self.load_plugins(root, PROJECT_COMPONENTS)
  ```
- [ ] **4. GREEN:** CLI 회귀와 `make lint`를 실행한다. `test_project()`가 여전히 `sample_text`·`sample_command`를 목록/실험에서 노출하는지 확인한다.
- [ ] **5. 커밋:** 변경한 코드·회귀만 스테이징하여 한국어 메시지로 커밋한다.

### 작업 2: 사용자 로컬 Agent·데이터셋의 설치형 실행

**파일:** `src/agent_optimizer/registry.py`, `src/agent_optimizer/readiness.py`, `src/agent_optimizer/setup_wizard.py`, `tests/test_cli_experience.py`.

**입력:** 저장소 마커가 없는 작업공간의 로컬 Agent, tasks.json, `--evaluator evaluator.py:TextFixtureEvaluator`. **출력:** `init`의 유효한 설정, 읽기 전용 `doctor --plan`, baseline `run`, HTML 보고서.

- [ ] **1. RED:** 임시 작업공간으로 `examples/minimal/agents/solo`, `examples/minimal/tasks.json`, `examples/minimal/evaluator.py`의 실제 fixture 파일을 복사한 뒤 `main(["init", "--project-root", root, "--agent", "agents/solo", "--dataset", "tasks.json", "--evaluator", "evaluator.py:TextFixtureEvaluator", "--editable", "configs/strategy.json", "--optimizer", "baseline", "--command", "{python} {agent_dir}/src/fixture_agent.py {task_dir}", "--yes"])` → `doctor --plan --json` → `run`을 검사한다. 원본 Agent 파일은 바뀌지 않아야 한다.
  ```python
  temporary = tempfile.TemporaryDirectory()
  self.addCleanup(temporary.cleanup)
  root = Path(temporary.name)
  arguments = ["init", "--project-root", str(root), "--agent", "agents/solo",
               "--dataset", "tasks.json", "--evaluator", "evaluator.py:TextFixtureEvaluator",
               "--editable", "configs/strategy.json", "--optimizer", "baseline",
               "--command", "{python} {agent_dir}/src/fixture_agent.py {task_dir}", "--yes"]
  output = io.StringIO()
  with contextlib.redirect_stdout(output):
      self.assertEqual(main(arguments), 0)
  plan = Path(json.loads(output.getvalue())["experiment"])
  self.assertEqual(main(["doctor", "--plan", str(plan), "--json"]), 0)
  self.assertEqual(main(["run", str(plan)]), 0)
  ```
- [ ] **2. RED 확인:** 위 테스트를 `-k test_bare_workspace_custom_agent_and_evaluator -v`로 실행하여 `Registry` 또는 `plugin_files`의 소스 저장소 가정으로 실패하는 지점을 확인한다.
- [ ] **3. 최소 구현:** `Registry.selected_files()`는 소스 checkout에서만 `PROJECT_COMPONENTS`와 해당 helper를 선택하고, 그 외에는 실험 선언의 `[plugins.*]`/`plugin_dependencies`만 검증한다. `prepare_selection()`의 상대적인 사용자 `tasks.json`은 현재 shell cwd가 아니라 선택한 `project_root` 기준으로 해석한다. `readiness.collect_plan()`과 `_registered()`는 같은 소스 checkout 판단을 사용하고, 선택하지 않은 저장소 예제 누락을 오류로 보고하지 않는다. 등록되지 않은 평가기/필수 채점기 누락은 기존 오류를 유지한다.
  ```python
  requested = {
      "datasets": [spec.get("_benchmark_metadata", {}).get("dataset_provider")],
      "evaluators": [spec.get("evaluator")],
      "harnesses": [profile["adapter"] for profile in spec.get("_profiles", [])],
      "optimizers": [stage["optimizer"] for stage in spec.get("stages", [])],
  }
  selected = {kind: {} for kind in PROJECT_COMPONENTS}
  if is_source_checkout(root):
      for kind, names in requested.items():
          selected[kind] = {name: PROJECT_COMPONENTS[kind][name]
                            for name in names if name in PROJECT_COMPONENTS[kind]}
  selected_dependencies = {key: paths for key, paths in PROJECT_DEPENDENCIES.items()
                           if key.split("/", 1)[1] in selected.get(key.split("/", 1)[0], {})}
  files = plugin_files(root, selected, selected_dependencies)
  files.update(plugin_files(root, spec.get("plugins", {}), spec.get("plugin_dependencies", {})))
  ```
- [ ] **4. GREEN:** bare workspace 테스트, 기존 `test_plugin_contracts.py`와 `test_cli_experience.py`, `make lint`를 실행한다.
- [ ] **5. 커밋:** 코어 코드·회귀만 스테이징해 한국어 메시지로 커밋한다.

### 작업 3: 격리 wheel의 기능 검증

**파일:** 새 `tests/test_installed_cli.py`, 수정 `.github/workflows/ci.yml`, `CONTRIBUTING.md`.

**입력:** `dist/agent_optimizer-*.whl`과 Python 3.11/3.12. **출력:** 소스 트리 밖 설치된 명령의 선택형 목록·custom init/doctor/run/report와 원본 파일 불변의 실제 실행 증거.

- [ ] **1. 검증 스크립트 RED:** CLI용 `tests/test_installed_cli.py`에 wheel 경로를 받는 `main(wheel: Path) -> int`를 작성한다. 임시 `venv`를 만들고 `python -m pip install <wheel>`로 격리 설치한 뒤 작업공간에 최소 fixture의 Agent/tasks/evaluator만 복사한다. `PYTHONPATH`·설치 소스 cwd는 비우고 `agent-opt datasets list`, `init`, `doctor --plan --json`, `run`, 보고서 존재를 자식 exit/status로 검사한다.
  ```python
  env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
  subprocess.run([str(venv_python), "-m", "pip", "install", str(wheel)],
                 check=True, cwd=outside, env=env)
  proc = subprocess.run([str(venv_scripts / "agent-opt"), "datasets", "list"],
                        cwd=outside, env=env, capture_output=True, text=True, check=True)
  assert "cvdp" in {row["name"] for row in json.loads(proc.stdout)}
  ```
- [ ] **2. RED 확인:** `.venv/bin/python -m build` 후 `.venv/bin/python tests/test_installed_cli.py dist/agent_optimizer-0.3.0-py3-none-any.whl`로 현재 설치형 CLI의 누락을 확인한다. pip의 의존성은 네트워크/캐시를 이용하지만 Agent·모델·Docker 호출은 없다.
- [ ] **3. CI 추가:** 기존 wheel 외부 설치 검증 직후 `python tests/test_installed_cli.py dist/agent_optimizer-0.3.0-py3-none-any.whl`을 실행한다. `CONTRIBUTING.md`에서 `--help` 전용 계약과 실제 기능 계약을 구분한다.
- [ ] **4. GREEN:** 설치형 smoke와 `make test`, `make lint`, `actionlint`, `git diff --check`를 확인한다.
- [ ] **5. 커밋:** 설치형 smoke·워크플로·문서만 스테이징해 한국어 메시지로 커밋한다.

## 두 번째 구현 계획으로 연결

`docs/superpowers/specs/2026-09-25-standalone-cli-selected-integrations-design.md`의 선택형
연동 스냅샷·미준비 선언·ACE lifecycle은 이 코어 작업의 준비된 인터페이스를 소비한다.
첫 단계 검증 후 해당 코드를 `docs/superpowers/plans/2026-09-25-selected-integrations.md`로
구체화해 TDD·별도 커밋으로 구현한다. 첫 단계의 CLI 목록은 실제 제공 여부를 `requires_preparation`
필드로 명시하고, 준비되지 않은 ID를 성공 가능한 평가기로 가장하지 않는다.
