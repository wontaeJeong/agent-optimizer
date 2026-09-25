# 선택형 ACE/CVDP 연동 구현 계획

> **실행 담당:** REQUIRED SUB-SKILL: `superpowers:executing-plans`. 각 작업은 실패 회귀 → 최소 구현 → 성공 검증 → 커밋 순서다.

**목표:** wheel만 설치한 사용자가 저장소 clone 없이 ACE/CVDP를 명시적으로 골라 준비·진단·실행하되 다른 Agent/데이터셋 계약을 유지한다.

**구조:** 카탈로그는 첫 PR이 rebase 머지된 불변 commit `ae0874fb94d94284a07a17d84ef60058ed9a97b6`을 가리킨다. 선택 후 검증된 `examples/`, `experiments/` 등 **필요 파일만 사용자 작업공간의 원래 상대 경로**에 게시한다. 고정된 ACE adapter와 lifecycle은 파일 위치·호출 방식을 바꾸지 않고 사용한다. 준비 완료 marker는 모든 파일/환경 검사 뒤에만 기록한다.

**기술:** Python 3.11+, Typer, Git, uv 0.10.7, Docker/Compose, 기존 CVDP driver.

**설계:** `docs/superpowers/specs/2026-09-25-standalone-cli-selected-integrations-design.md`.

## 전체 제약

- CLI wheel은 저장소 없이 시작하며 선택 전 Git/Docker 다운로드·모델 호출은 없다.
- Git pin과 upstream ACE/CVDP/Verilog-Eval 버전/해시는 자동 갱신하지 않는다.
- 사용자 Agent는 로컬/고정 Git 소스, 사용자 dataset은 분리된 evaluator를 명시한다.
- `doctor --plan`은 읽기 전용, `run`은 다운로드·설치 없이 준비 부족 시 명시적 오류다.
- 완성 전 marker가 없으면 자산 일부가 있어도 실행 불가; 기존 사용자 파일·원본 Agent·평가기 수정 금지.
- 외부 명령은 argv와 `shell=False`, 모델 키는 환경/credential store만 사용한다.

## 파일별 책임

- `src/agent_optimizer/catalog.py`: 선택형 코드의 첫-party URL/불변 commit과 기존 데이터셋 metadata.
- 새 `src/agent_optimizer/integrations.py`: cache 검증·허용 파일 배치·pending pointer·준비 marker·readiness.
- `src/agent_optimizer/cli.py`, `src/agent_optimizer/setup_wizard.py`: `init --profile`, `prepare`, TUI 명시적 ACE 선택과 다른 Agent/CVDP 입력.
- `src/agent_optimizer/config.py`, `src/agent_optimizer/readiness.py`: 준비 전/후 pointer를 올바르게 판정하고 동일 runner로 연결.
- `tests/test_cli_experience.py`, `tests/test_installed_cli.py`: 실제 Git fixture·wheel 밖 bare 작업공간 및 선택 승인/거절.
- `README.md`, `website/user/getting-started.md`, `docs/verification.md`, `CONTRIBUTING.md`: 준비 조건·실제 실행 근거.

---

### 작업 1: 고정 Git 출처와 선택 전 조회

**파일:** `src/agent_optimizer/catalog.py`, `tests/test_cli_experience.py`.

**인터페이스:** `INTEGRATIONS["ace-rtl"] = {"url": str, "revision": str, "contract": 1}`. CVDP/Verilog-Eval 코드도 동일한 고정 첫-party commit을 사용하지만 데이터셋 고유 pin은 `DATASETS` 그대로 둔다.

- [ ] **1. RED:** bare 작업공간에서 `INTEGRATIONS["ace-rtl"]`의 URL·전체 commit을 확인하고 `datasets list`가 파일·네트워크·Docker 호출 없이 동작하는 테스트를 작성한다.
  ```python
  self.assertEqual(INTEGRATIONS["ace-rtl"]["revision"],
                   "ae0874fb94d94284a07a17d84ef60058ed9a97b6")
  self.assertFalse((project / "examples").exists())
  ```
- [ ] **2. RED 확인:** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -k test_optional_integration_catalog -v`에서 항목 부재로 실패한다.
- [ ] **3. 최소 구현:** ID→고정 URL/SHA/계약 버전만 `catalog.py`에 정적으로 기록한다. `DATASETS`의 upstream revision이나 평가 SHA는 바꾸지 않는다.
  ```python
  INTEGRATIONS = {"ace-rtl": {"url": "https://github.com/wontaeJeong/agent-optimizer.git",
                              "revision": "ae0874fb94d94284a07a17d84ef60058ed9a97b6", "contract": 1}}
  ```
- [ ] **4. GREEN:** 해당 테스트·`make lint` 실행.
- [ ] **5. 커밋:** 카탈로그/회귀만 한국어 커밋.

### 작업 2: 검증된 연동 파일을 작업공간에 게시

**파일:** 새 `src/agent_optimizer/integrations.py`, `tests/test_cli_experience.py`.

**인터페이스:** `acquire_integration(workspace: Path, integration_id: str, *, offline=False, source_url=None, revision=None) -> dict`. source override는 개발용 Python fixture에서만 호출하며 사용자 명령은 카탈로그 pin만 사용한다.

- [ ] **1. RED:** 임시 로컬 Git에 `examples/ace-rtl/{adapter.py,environment/lifecycle.py}`·`examples/rtl-debugger/Dockerfile`·`examples/benchmarks/cvdp.py`·`experiments/simple-feedback/optimizer.py`·`src/agent_optimizer/models.py`를 둔다. 고정 SHA 온라인/오프라인 획득의 파일 해시 일치와 다른 SHA, 누락 cache, symlink, 기존 사용자 파일 충돌 시 `ready` marker 및 원본 변경이 없는지 검사한다.
  ```python
  result = acquire_integration(workspace, "ace-rtl", source_url=fixture_url,
                               revision=revision)
  self.assertEqual(result["revision"], revision)
  self.assertTrue((workspace / "examples/ace-rtl/adapter.py").is_file())
  self.assertFalse((workspace / ".agent-opt/integration-ready.json").exists())
  ```
- [ ] **2. RED 확인:** `test_cli_experience.py -k test_acquire_optional_integration -v`에서 함수 부재를 확인한다.
- [ ] **3. 최소 구현:** `datasets.acquire_pinned_git()`으로 `~/.cache/agent-optimizer/integrations/ae0874fb94d94284a07a17d84ef60058ed9a97b6`를 검증한다. `ace-rtl`은 `examples/ace-rtl`, `examples/rtl-debugger`, `examples/benchmarks`, `experiments/simple-feedback`, `src/agent_optimizer/models.py`를 대상으로 한다. 단독 CVDP/Verilog-Eval은 선택한 provider/평가기와 그 helper만 가져오며 ACE Agent/Optimizer 파일은 제외한다. `selected_files(source: Path, integration_id: str) -> list[Path]`는 허용 목록의 regular 파일만 열거하고 symlink·이탈 경로를 거부한다. 전부 검증해 임시 staging에 복사한 뒤 작업공간에 **없는** 파일만 임시 파일 → `replace()`로 게시한다. 기존 파일 내용이 다르면 거부하고 준비 완료 marker는 여기서 쓰지 않는다. 성공 시 `{"revision": revision, "paths": [상대 파일 목록]}`을 반환한다.
  ```python
  source = acquire_pinned_git(cache / revision, url, revision, offline=offline)
  staged = workspace / ".agent-opt" / ("staging-" + uuid.uuid4().hex)
  for original in selected_files(source, integration_id):
      relative = original.relative_to(source)
      destination = safe_path(workspace, relative.as_posix())
      if destination.exists() and destination.read_bytes() != original.read_bytes():
          raise ConfigurationError(f"연동 파일 충돌: {relative}")
      target = staged / relative
      target.parent.mkdir(parents=True, exist_ok=True)
      shutil.copyfile(original, target)
  for staged_file in sorted(staged.rglob("*")):
      if not staged_file.is_file():
          continue
      relative = staged_file.relative_to(staged)
      destination = safe_path(workspace, relative.as_posix())
      if not destination.exists():
          destination.parent.mkdir(parents=True, exist_ok=True)
          temporary = destination.with_name(destination.name + ".pending")
          shutil.copyfile(staged_file, temporary)
          temporary.replace(destination)
  ```
- [ ] **4. GREEN:** 재시도·offline·pin 변경·symlink·파일 충돌 회귀와 `make lint` 실행.
- [ ] **5. 커밋:** 획득/검증 코드와 테스트만 커밋.

### 작업 3: 단일 pointer 실험과 명시적 준비

**파일:** `src/agent_optimizer/integrations.py`, `src/agent_optimizer/cli.py`, `src/agent_optimizer/config.py`, `src/agent_optimizer/readiness.py`, `tests/test_cli_experience.py`.

**인터페이스:** `agent-opt init --profile ace-rtl --workspace PATH`는 `PATH/experiment.toml`이라는 **pending pointer**만 생성한다. `agent-opt prepare PATH/experiment.toml [--offline]`은 pin을 확인한 뒤 같은 작업공간에 예제 파일과 평가 환경을 준비한다. 완료 후 `load_experiment(pointer)`는 검증된 `PATH/examples/ace-rtl/experiment.toml`을 반환한다.

- [ ] **1. RED:** init 뒤 작업공간에 pointer 파일만 있고 `doctor --plan`은 `integration.prepare=blocked`, `run`은 2, 네트워크/작업공간 복사는 없다. 잘못된 pin/다른 integration ID 및 `init --profile`과 `--agent` 동시 지정은 쓰기 전에 거부한다. 준비한 marker를 변조하면 `run`이 다른 프로필로 대체하지 않고 실패한다.
  ```python
  output = io.StringIO()
  with contextlib.redirect_stdout(output):
      self.assertEqual(main(["init", "--profile", "ace-rtl", "--workspace", str(workspace)]), 0)
  pointer = Path(json.loads(output.getvalue())["experiment"])
  self.assertEqual(pointer, workspace / "experiment.toml")
  self.assertEqual(main(["doctor", "--plan", str(pointer)]), 2)
  ```
- [ ] **2. RED 확인:** `test_cli_experience.py -k test_ace_pending_pointer_before_preparation -v`에서 `--profile` 미지원 확인.
- [ ] **3. 최소 구현:** pointer는 `schema_version=1`, `[integration] id="ace-rtl", revision="ae0874fb94d94284a07a17d84ef60058ed9a97b6", config="examples/ace-rtl/experiment.toml"`만 적는다. `read_toml`로 이 선언을 엄격 검증하고 marker가 없으면 `doctor --plan`은 읽기 전용 `blocked/prepare` 안내를 반환한다. `prepare`는 pin된 예제 파일을 **수정 없이** 복사한 뒤 `lifecycle.prepare(workspace)`와 `lifecycle.inspect(workspace)`가 성공할 때만 `.agent-opt/integration-ready.json`을 원자적으로 기록한다. `config.load_experiment(pointer)`는 marker의 pin/파일 해시를 확인하고 `safe_path(workspace, config)`로만 위임한다. `Registry.load_project(workspace)`는 source checkout marker 대신 이 검증된 integration marker가 있는 경우에만 카탈로그의 **선택된 evaluator/provider/helper**를 등록한다. 따라서 원본 `experiment.toml`을 변형하지 않는다.
  ```toml
  schema_version = 1
  [integration]
  id = "ace-rtl"
  revision = "ae0874fb94d94284a07a17d84ef60058ed9a97b6"
  config = "examples/ace-rtl/experiment.toml"
  ```
- [ ] **4. GREEN:** init/doctor/readiness/prepare/변조·rollback 회귀와 `make lint` 확인.
- [ ] **5. 커밋:** 설정·준비 경계와 회귀만 커밋.

### 작업 4: 고정된 ACE runner와 다른 데이터셋 연결

**파일:** `src/agent_optimizer/cli.py`, `src/agent_optimizer/setup_wizard.py`, `src/agent_optimizer/readiness.py`, `src/agent_optimizer/integrations.py`, `tests/test_cli_experience.py`.

**인터페이스:** `agent-opt run PATH/experiment.toml`은 pin을 검증한 inner spec을 ACE adapter로 전달한다. 준비하지 않은 `cvdp`·`verilog-spec`·`verilog-completion`을 다른 Agent가 선택하면 동일한 pin 획득 뒤 등록된 평가기/provider 계약을 사용한다.

- [ ] **1. RED:** 준비된 pointer의 `run`은 pinned `ACEOpenCode.launch_existing`가 정확한 `workspace/examples/ace-rtl/experiment.toml`만 받아 기존 `lifecycle.run(root)`을 호출하는지 격리 Git fixture에서 검사한다. custom Agent+`--dataset cvdp` 및 Verilog-Eval은 evaluator/소스 pin을 명시한 경우에만 준비하고, 사용자 tasks.json/evaluator는 다운로드하지 않는지 확인한다.
- [ ] **2. RED 확인:** `test_cli_experience.py -k test_installed_ace_pointer_uses_pinned_adapter -v`에서 pointer 해석·실행 부재 확인.
- [ ] **3. 최소 구현:** `_dispatch(run)`/TUI는 `load_experiment(pointer)`가 돌려준 inner spec을 기존 `_launch_existing()`에 전달한다. `readiness._registered()`는 준비 marker가 검증된 경우에만 해당 첫-party 등록 ID를 허용하고 소스 marker 없는 workspace의 잘못된 중복 등록을 거부한다. `prepare_selection()`은 명시적으로 고른 첫-party dataset에만 연동 파일 획득 및 **임시 provider/evaluator 등록**을 적용하고, 준비 후에는 marker에 기록한 provider ID를 등록한다. `integrations.selected_dataset_plugins(selected_id: str) -> dict`는 `cvdp`→`examples/benchmarks/cvdp.py:Provider`·`examples/ace-rtl/evaluator.py:CVDPEvaluator`, `verilog-spec`/`verilog-completion`→기존 `verilog_eval.py`·`verilog_evaluator.py`의 파일 ID를 반환한다. 선택하지 않은 plugin은 import/설치하지 않는다.
  ```python
  if selected_id in CATALOG_DATASETS and selected_id not in registry.factories["datasets"]:
      acquire_integration(project_root, "ace-rtl", offline=offline)
      registry.load_plugins(project_root, selected_dataset_plugins(selected_id))
  ```
- [ ] **4. GREEN:** 기존 `test_plugin_contracts.py`, CLI 회귀와 모의 pin fixture 재실행. Docker/모델 결과를 모의 테스트 성공으로 표시하지 않는다.
- [ ] **5. 커밋:** ACE 포인터 및 선택형 dataset 경로와 회귀만 커밋.

### 작업 5: 개발 명령도 같은 ACE lifecycle 재사용

**파일:** `scripts/dev.py`, `tests/test_dev_onboarding.py`, `tests/test_progress.py`.

- [ ] **1. RED:** 기존 `sh scripts/bootstrap.sh setup`, `smoke`, `live`의 종료 코드/진단·데모 순서는 유지하면서 full setup 자산 준비가 `lifecycle.prepare(root, offline, platform)`, live가 `lifecycle.run(root, iterations, platform)`으로 이동하는 테스트를 작성한다.
  ```python
  with patch.object(lifecycle, "prepare", return_value=root / "datasets/ace-demo/tasks.json") as prepare:
      self.assertEqual(dev.main(["setup", "--offline", "--platform", "linux/arm64"]), 0)
      prepare.assert_called_once_with(root, offline=True, platform="linux/arm64")
  ```
- [ ] **2. RED 확인:** `test_dev_onboarding.py -k test_dev_ace_commands_share_lifecycle -v`에서 dev.py가 기존 별도 코드를 호출하는 실패를 확인한다.
- [ ] **3. 최소 구현:** `scripts/dev.py.load("ace_lifecycle", "examples/ace-rtl/environment/lifecycle.py")`를 전체 setup 및 live/smoke에서 사용한다. setup은 `lifecycle.prepare()` 뒤 기존 최종 doctor와 합성 데모를, live는 `lifecycle.run()`의 종료 코드를, smoke는 `lifecycle.inspect()`의 검증된 lock을 `checks.smoke(lock)`에 전달한다. 코어 `--core`와 단일 데이터셋 준비 분기는 유지한다.
  ```python
  lifecycle = load("ace_lifecycle", "examples/ace-rtl/environment/lifecycle.py")
  if args.command == "live":
      return lifecycle.run(ROOT, iterations=args.iterations, platform=args.platform)
  if args.command == "smoke":
      report = lifecycle.inspect(ROOT, platform=args.platform)
      if not report["ready"]:
          raise UnavailableError("ACE 평가 환경이 준비되지 않았습니다")
      return load("ace_dev_checks", "examples/ace-rtl/environment/checks.py").smoke(report["lock"])
  ```
- [ ] **4. GREEN:** `test_dev_onboarding.py`, `test_dev_environment.py`, `make lint`, 코어 진단, 준비된 Docker의 `make smoke`와 이전 종료 코드/결과를 확인한다.
- [ ] **5. 커밋:** 개발 호환 진입점과 회귀를 커밋.

### 작업 6: TUI 확인·wheel 사용자 검증·실환경 기록

**파일:** `src/agent_optimizer/cli.py`, `tests/test_cli_experience.py`, `tests/test_installed_cli.py`, `README.md`, `website/user/getting-started.md`, `docs/status.md`, `docs/verification.md`, `.github/workflows/ci.yml`(필요 시).

- [ ] **1. RED:** 새 wheel의 TUI 첫 화면에서 ACE 선택 → workspace 지정 → Git clone/driver/Docker 빌드 요약, 거절 시 cache/workspace 미생성, 승인 시 `prepare(pointer)`와 동일 경로. 완료 뒤 정적 doctor/실도구 readiness/최종 실행 확인을 분리한다. 모델 키 없이 실행하면 `blocked_auth`, 합성 대체가 없음을 본다.
- [ ] **2. RED 확인:** `test_cli_experience.py -k test_tui_optional_ace_preparation -v`에서 선택지 부재 확인.
- [ ] **3. 최소 구현:** 기존 TUI 메뉴에 `ACE-RTL + CVDP 예제`를 명시적 선택지로 추가한다. `init --profile` → 작업공간과 외부 작업 요약 → 확인 후 `prepare` → `doctor --plan` → `lifecycle.inspect` → 실행 여부 확인 순서를 사용한다. 최종 `run`은 다운로드/설치를 하지 않고 모델 연결은 명시적 probe 또는 실제 run에서만 호출한다.
- [ ] **4. 통합 검증:** `make test`, `make lint`, `.venv/bin/python -m build`, 저장소 밖 wheel의 custom 데이터와 ACE pointer init/prepare/doctor/키 없는 run, `actionlint`, `git diff --check`. 준비한 Mac/Docker에서 실제 ACE workspace `prepare` → `make smoke`와 동일 공식 평가 정답/오답을 실행하고, 모델 키가 없으면 실모델 E2E 미검증을 기록한다.
- [ ] **5. 커밋·PR:** 변경·검증 문서와 코드를 커밋, 푸시, PR 생성. TUI 전후 캡처/재현 방법 또는 이미지 캡처 불가 이유를 본문에 포함한다. 자동 머지는 하지 않는다.
