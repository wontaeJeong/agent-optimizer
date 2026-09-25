# ACE 예제 lifecycle의 독립 실행 구현 계획

> **실행 담당:** REQUIRED SUB-SKILL: `superpowers:executing-plans`. 각 체크박스는 실패 회귀 → 최소 구현 → 성공 검증 → 커밋 순으로 실행한다.

**목표:** 첫 PR에서 ACE 예제의 준비·진단·실행을 설치된 코어가 직접 호출할 수 있는 Python 함수로 분리한다.

**구조:** ACE/CVDP 특화 로직은 `examples/ace-rtl/environment/`에 남긴다. 별도 Python 패키지 설치 없이 그 폴더를 버전 고정 연동 스냅샷에 복사해도 함수가 동작하도록 소스 위치를 기준으로 root를 구한다. CLI의 선택형 다운로드와 개발용 `scripts/dev.py` 호출 통일은 **머지 commit이 확정된 뒤** 두 번째 PR에서 연결한다.

**기술:** Python 3.11+, 기존 `setup.py`·`prepare.py`·`checks.py`, unittest, Docker 선택 검증.

**설계:** `docs/superpowers/specs/2026-09-25-standalone-cli-selected-integrations-design.md` 중 ACE lifecycle과 선택형 연동 스냅샷의 준비 계약.

## 전체 제약

- ACE-RTL은 OpenCode 스킬 프로필이고 native runner 실행·논문 재현이 아니다.
- source/data pin·공식 CVDP 평가·private 자료 분리·환경 lock·이미지 ID 검사는 기존 로직을 재사용한다.
- 설정/원본/테스트·평가기 수정 금지, 실패 시 baseline/합성 평가 대체 금지.
- 모델 API 키는 환경/credential store만 사용하고 실제 호출은 `run` 또는 명시적 모델 probe 때만 한다.
- 실행 argv 배열과 `shell=False`; 설치된 코어에서 개발용 `scripts/bootstrap.sh`를 필수로 호출하지 않는다.

## 파일별 책임

- 새 `examples/ace-rtl/environment/lifecycle.py`: `prepare(root, offline=False, platform=None)`, `inspect(root, platform=None)`, `run(root, iterations=None, platform=None)`의 예제 전용 함수. 기존 파일을 동적으로 불러와 같은 고정 자산을 사용한다.
- `examples/ace-rtl/adapter.py`: 정확한 ACE 고정 실험만 선택한 후 lifecycle로 직접 위임.
- `src/agent_optimizer/readiness.py`, `scripts/dev_doctor.py`, `examples/ace-rtl/environment/diagnostics.py`: 기존 공통 읽기 전용 probe를 코어로 옮겨 예제가 개발용 `scripts/` 없이 독립 진단하게 한다.
- `tests/test_cli_experience.py`, `tests/test_ace_demo.py`, `tests/test_dev_environment.py`: shell bounce 배제, source 복사 위치, 모의 계약과 평가환경 결과 구분.
- `examples/ace-rtl/README.md`, `docs/status.md`, `docs/verification.md`: 현 PR의 실제 검증 범위를 표시.

---

### 작업 1: 선택형 예제 자산 준비 함수

**파일:** 새 `examples/ace-rtl/environment/lifecycle.py`, 수정 `tests/test_ace_demo.py`.

**입력:** `root: Path`, `offline: bool`, `platform: str | None`. **출력:** 준비된 `root/datasets/ace-demo/tasks.json`과 환경 lock. 준비하지 않은 소스/driver/이미지 자동 대체 없음.

- [ ] **1. RED:** 임시 루트에 필요한 `examples/ace-rtl/environment/setup.py`와 `prepare.py`, `demo.py`의 테스트 복사본을 배치한다. `lifecycle.prepare(root, offline=True, platform="linux/arm64")`가 `setup.prepare_environment`를 호출한 뒤 고정 과제 manifest를 쓰는지 검증한다. Python `mock.patch`는 외부 Docker·다운로드만 교체하고 manifest 쓰기 및 순서는 실제로 검사한다.
  ```python
  output = root / "datasets/ace-demo/tasks.json"
  prepared = lifecycle.prepare(root, offline=True, platform="linux/arm64")
  self.assertEqual(prepared, output)
  self.assertTrue(output.is_file())
  self.assertEqual([row["split"] for row in json.loads(output.read_text())["tasks"]],
                   ["train", "validation"])
  ```
- [ ] **2. RED 확인:** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_ace_demo.py -k test_lifecycle_prepares_fixed_demo -v`에서 새 진입 함수 누락을 확인한다.
- [ ] **3. 최소 구현:** `load_example(root: Path, relative: str, name: str)`는 `importlib.util.spec_from_file_location`으로 root 내부의 승인된 파일만 불러온다. `prepare()`는 `setup.prepare_environment(offline=offline, platform=platform)` → `prepare.prepare_dataset(dataset, root / "datasets/ace-demo/all-tasks.json", lock)` → `demo.select_tasks(manifest)` → `write_json(root / "datasets/ace-demo/tasks.json", selected)` 순으로 호출하고 결과 경로를 반환한다.
  ```python
  def prepare(root: Path, *, offline: bool = False, platform: str | None = None) -> Path:
      setup = load_example(root, "examples/ace-rtl/environment/setup.py", "ace_setup")
      source = load_example(root, "examples/ace-rtl/prepare.py", "ace_prepare")
      demo = load_example(root, "examples/ace-rtl/environment/demo.py", "ace_demo")
      dataset, lock = setup.prepare_environment(offline=offline, platform=platform)
      target = root / "datasets/ace-demo/tasks.json"
      selected = demo.select_tasks(source.prepare_dataset(dataset, target.with_name("all-tasks.json"), lock))
      write_json(target, selected)
      return target
  ```
- [ ] **4. GREEN:** 관련 테스트·`make lint`를 확인한다.
- [ ] **5. 커밋:** 예제 코드·회귀만 한국어 메시지로 커밋한다.

### 작업 2: 개발용 스크립트 없이 진단할 수 있는 예제

**파일:** `src/agent_optimizer/readiness.py`, `scripts/dev_doctor.py`, `examples/ace-rtl/environment/diagnostics.py`, `tests/test_dev_onboarding.py`, `tests/test_ace_demo.py`.

**입력:** `examples/ace-rtl/environment`만 복사된 작업공간. **출력:** `diagnostics.collect_checks(root, environment={"PATH": ""})`가 `scripts/dev_doctor.py` 없이 읽기 전용 오류 체크를 반환.

- [ ] **1. RED:** `setup.py`·`diagnostics.py`가 있는 임시 `examples/ace-rtl/environment/`와 빈 `scripts/` 디렉터리를 만들고, 동적으로 불러온 `diagnostics.collect_checks()`가 `environment.lock=error`, `source.ACE-RTL=error`를 반환하며 파일을 쓰지 않는지 검사한다.
  ```python
  spec = importlib.util.spec_from_file_location("isolated_ace_diagnostics", selected)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  rows = module.collect_checks(root, environment={"PATH": ""})
  self.assertEqual({row["id"]: row["status"] for row in rows}["environment.lock"], "error")
  self.assertFalse((root / "external").exists())
  ```
- [ ] **2. RED 확인:** `test_ace_demo.py -k test_ace_diagnostics_without_developer_scripts -v`에서 `scripts/dev_doctor.py` 누락 오류를 확인한다.
- [ ] **3. 최소 구현:** `dev_doctor.Runner`의 `add`, `ok`, `run`, `probe`를 같은 시그니처로 `agent_optimizer.readiness.Runner`로 옮기고 개발용 스크립트는 이 클래스를 import한다. ACE `diagnostics.py`도 같은 Runner를 import하며 옆에 둔 `setup.py`를 `ModuleType`/`compile`로 읽기 전용 로드한다. ACE용 `SETUP` 복구 안내는 기존 사용자 명령을 보존한다.
  ```python
  from agent_optimizer.readiness import Runner
  setup_path = Path(__file__).with_name("setup.py")
  setup = ModuleType("ace_diagnostic_inputs")
  setup.__file__ = str(setup_path)
  exec(compile(setup_path.read_bytes(), str(setup_path), "exec"), setup.__dict__)
  ```
- [ ] **4. GREEN:** `test_ace_demo.py`, `test_dev_onboarding.py`, `make lint`를 확인한다.
- [ ] **5. 커밋:** 공통 Runner 이동과 예제 진단 테스트만 한국어 메시지로 커밋한다.

### 작업 3: 읽기 전용 진단과 실모델 전 실행 보호

**파일:** `examples/ace-rtl/environment/lifecycle.py`, `tests/test_ace_demo.py`, `tests/test_cli_experience.py`.

**입력:** 준비된 환경 lock·`root`·선택 플랫폼. **출력:** `inspect()`는 모델 호출/다운로드 없이 driver/이미지/도구 체크 결과, `run()`은 기존 `checks.live(lock, iterations=...)` 종료 코드를 유지.

- [ ] **1. RED:** lock 누락·플랫폼 불일치·손상된 lock은 원본 파일을 보존하고 `UnavailableError` 또는 `ConfigurationError`로 중단하는 회귀를 작성한다. 모델 설정이 없으면 `run()`이 `setup.validate_platform`·Docker/데이터 probe보다 먼저 `blocked_auth`를 보고하는 순서를 검사한다. 준비된 fake lock의 `inspect()`는 도구 실패를 `ready=false`로 반환하고 모델 함수를 호출하지 않는다.
  ```python
  with patch.object(setup, "validate_platform", side_effect=AssertionError("Docker called")):
      with self.assertRaisesRegex(UnavailableError, "blocked_auth"):
          lifecycle.run(root)
  self.assertEqual((root / "external/environment-lock.json").read_bytes(), before)
  ```
- [ ] **2. RED 확인:** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_ace_demo.py -k test_lifecycle -v`에서 누락 함수를 확인한다.
- [ ] **3. 최소 구현:** `inspect(root, platform=None) -> dict`는 `setup.read_environment_lock()` → 플랫폼/CA/driver와 고정 source/data 확인 → `setup.verified_sim_image()` → `setup.doctor()` 순으로 검사한다. `run()`은 먼저 `setup.validate_live()`로 API URL·키를 검사한 뒤 `inspect()`를 수행하고, `DOCKER_DEFAULT_PLATFORM`·`OSS_SIM_IMAGE`를 실행 동안만 설정한다. `checks.live(lock, iterations)`가 기존 고정 프로필·예산·보고서를 유지하며 종료 코드를 반환한다.
  ```python
  def run(root: Path, *, iterations: int | None = None, platform: str | None = None) -> int:
      setup = load_example(root, "examples/ace-rtl/environment/setup.py", "ace_run_setup")
      setup.validate_live()
      report = inspect(root, platform=platform)
      if not report["ready"]:
          raise UnavailableError("ACE 평가 실행환경을 준비하고 다시 진단하세요")
      checks = load_example(root, "examples/ace-rtl/environment/checks.py", "ace_run_checks")
      return checks.live(report["lock"], iterations=iterations)
  ```
- [ ] **4. GREEN:** 위 회귀와 기존 `test_dev_onboarding.py`·`test_progress.py`를 확인한다. 모의 검사와 실제 Docker smoke는 별도 결과다.
- [ ] **5. 커밋:** lifecycle과 회귀를 한국어 메시지로 커밋한다.

### 작업 4: 앱 CLI의 shell-free ACE 위임

**파일:** `examples/ace-rtl/adapter.py`, `tests/test_cli_experience.py`, `tests/test_ace_demo.py`.

**입력:** 정확히 `examples/ace-rtl/experiment.toml`을 선택한 `agent-opt run`/TUI. **출력:** 설치된 코어와 예제 lifecycle 함수만으로 실행, 스크립트 shell 호출 없음.

- [ ] **1. RED:** `test_ace_existing_profile_uses_its_live_bootstrap_for_tui_and_run`을 실제 계약에 맞춰 바꾼다. 임시 프로젝트의 예제 `lifecycle.py`가 `run(root)` 호출을 파일 마커에 남기도록 하고 `scripts/bootstrap.sh`를 생성하지 않는다. TUI·CLI 두 진입점이 marker를 남기고 실패 종료 코드를 유지하며 다른 실험은 일반 runner를 사용해야 한다.
  ```python
  (root / "examples/ace-rtl/environment/lifecycle.py").write_text(
      'def run(root, *, iterations=None, platform=None):\n'
      '    (root / "launch.marker").write_text("direct lifecycle")\n    return 3\n')
  self.assertEqual(main(["run", str(root / "examples/ace-rtl/experiment.toml")]), 3)
  self.assertEqual((root / "launch.marker").read_text(), "direct lifecycle")
  ```
- [ ] **2. RED 확인:** CLI 테스트에서 기존 `launch_existing()`가 bootstrap 파일을 호출해 직접 위임 마커를 만들지 못함을 확인한다.
- [ ] **3. 최소 구현:** `ACEOpenCode.launch_existing(spec) -> int`의 정확한 경로 guard는 유지하고, `subprocess.run(["sh", ...])` 대신 `examples/ace-rtl/environment/lifecycle.py`를 `importlib`로 불러 `run(root)`을 호출한다. 직접 `checks.live` 우회/합성 대체 없이 exit code를 전달한다.
  ```python
  path = root / "examples/ace-rtl/environment/lifecycle.py"
  module = load_example(root, path.relative_to(root).as_posix(), "ace_cli_lifecycle")
  return module.run(root)
  ```
- [ ] **4. GREEN:** CLI 경계 테스트·`make lint`·`make test`를 실행한다. 모델 설정 없이 실제 Docker 성공이라고 표시하지 않는다.
- [ ] **5. 커밋:** 예제 adapter·회귀만 한국어 메시지로 커밋한다.

## 첫 PR의 완료 및 다음 PR 전제

- [ ] 첫 PR에서 `make test`, `make lint`, 격리 wheel의 사용자 custom 실험, 기존 `make doctor-core`를 확인한다. Docker 고정 자산이 있으면 기존 `make smoke`도 별도로 실행하고 근거를 기록한다.
- [ ] 설계·테스트·미검증 영역을 문서화하고 PR을 생성한다. 머지 여부는 사용자에게 묻는다.
- [ ] 첫 PR이 실제 머지되어 불변 commit이 확정된 뒤, 그 commit을 pin으로 넣는 두 번째 계획을 작성한다. 머지 전 임의 HEAD/tag를 사용자 wheel의 고정 출처로 사용하지 않는다.
