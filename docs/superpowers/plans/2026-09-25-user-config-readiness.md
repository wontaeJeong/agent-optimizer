# 사용자 설정 준비 구현 계획

> **구현 시 필수 스킬:** 작업별로 superpowers:subagent-driven-development 또는 superpowers:executing-plans를 적용한다. 단계는 체크박스로 추적한다.

**목표:** `agent-opt init`에서 중첩 Optimizer 설정을 실행 가능한 실험으로 만들고 실패 시 재시도를 허용한다.

**구조:** 기존 CLI·TOML 작성기를 유지한다. JSON 호환 값을 TOML literal로 재귀 직렬화하고
`load_experiment`로 검증한다. 예외가 나면 이번에 생성한 설정 디렉터리만 정리하며, 기존
설정과 준비된 데이터셋은 보존한다.

**기술:** Python 3.11+, 표준 라이브러리 `tomllib`/`unittest`, 기존 `agent_optimizer` CLI와 합성 fixture.

**설계:** `docs/superpowers/specs/2026-09-25-readiness-followup-design.md`

## 공통 제약

- 기존 CLI/TUI, 명시적 데이터셋 선택, 공통 계약과 source/data pin을 유지한다.
- 격리된 작업 워크트리와 프로젝트 `.venv`를 사용하고 기본 checkout은 수정하지 않는다.
- 합성 fixture 수치를 실제 Agent 성능으로 표현하지 않는다.
- 생성 설정에 자격증명이나 비공개 endpoint 정보를 저장하지 않는다.

---

## 파일 책임

- `src/agent_optimizer/setup_wizard.py`: TOML literal 및 생성 설정 디렉터리의 소유권.
- `tests/test_cli_experience.py`: 생성/doctor/run/실패 정리 회귀.

### 작업 1: 중첩 Optimizer 옵션 직렬화

**파일:** `src/agent_optimizer/setup_wizard.py:58-68`, `tests/test_cli_experience.py`

**입력/출력:** `main(["init", ..., "--optimizer-config", JSON, "--yes"])`와
`_section(name, mapping)`을 사용한다. `_literal(value) -> str`은 문자열, 불리언, 유한 수,
배열, 문자열 키의 inline table을 TOML로 반환하고 미지원 값에는 `ConfigurationError`를 낸다.

- [ ] **1. 실패할 사용자 흐름 회귀 작성.** `CLIExperienceTests`에서 기존 `self.root`,
  `self.agent`, `self.data`, command JSON을 사용한다. `--optimizer file_variants`와 다음 옵션을 넣는다.

  ```python
  options = {"file_variants": {"include_seeds": True, "variants": [
      {"name": "enable-repair", "files": {"configs/strategy.json": '{"repair": true}'}}
  ]}}
  args += ["--optimizer-config", json.dumps(options), "--yes"]
  with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
      self.assertEqual(main(args), 0)
  plan = self.root / "runs/configs/structured-options/experiment.toml"
  spec = load_experiment(plan)
  self.assertEqual(spec["stages"][0]["config"]["variants"], options["file_variants"]["variants"])
  ```

  `--name structured-options`, `--agent str(self.agent)`, `--dataset str(self.data)`,
  `--evaluator examples/minimal/evaluator.py:TextFixtureEvaluator`,
  `--editable configs/strategy.json`, `--command-json`에 기존 fixture argv를 지정한다.
  `doctor --plan`, `run`까지 호출하고 `summary.json`의 synthetic=true·completed,
  validation baseline 0→selected 1과 `report.html` 존재 여부를 확인한다.

- [ ] **2. 실패 확인.** `PYTHONPATH=src:tests .venv/bin/python -m unittest test_cli_experience.CLIExperienceTests.test_structured_optimizer_options_complete_user_flow -v`를 실행한다. 배열 속 JSON 객체의 `:` 때문에 TOML 파싱이 실패해야 한다.
- [ ] **3. 최소 구현.** `_literal`에서 기존 scalar 표현을 유지하고 list/tuple은 `"[" + ", ".join(_literal(item) ...) + "]"`, dict는 따옴표로 감싼 키·`" = "`를 사용하는 `{ ... }`로 만든다. `None`, 유한하지 않은 float, 문자열이 아닌 키는 `ConfigurationError`로 거부한다. 별도 파서 대신 기존 `load_experiment`로 검사한다.
- [ ] **4. 대상 검사.** 새 테스트와 `test_gepa_trial_allowance_tracks_requested_iterations_and_merge`를 실행해 둘 다 통과하는지 확인한다.
- [ ] **5. 변경 파일만 커밋.** 예: `중첩 Optimizer 설정 생성을 수정`.

### 작업 2: 실패한 설정 디렉터리 정리

**파일:** `src/agent_optimizer/setup_wizard.py:116-209`, `tests/test_cli_experience.py`

**입력/출력:** `write_experiment(config_root, ..., stages, ...) -> Path`의 서명과 성공 결과는
유지한다. `mkdir` 이후 실패하면 새로 만든 디렉터리만 지우고 원래 예외를 다시 낸다.

- [ ] **1. 실패할 재시도 회귀 작성.** `--name invalid-once`, `--optimizer baseline`,
  `--optimizer-config '{"baseline":{"unsupported":null}}'`로 `main(init_args)`가 종료 코드 2를
  반환하고 `runs/configs/invalid-once`가 남지 않아야 한다. 잘못된 설정을 제거해 같은 이름으로
  재실행하면 코드 0이어야 한다. 별도로 기존 `runs/configs/existing/sentinel`을 만든 뒤
  같은 이름으로 init 실패 시 sentinel의 바이트가 유지되는지도 검사한다.
- [ ] **2. 실패 확인.** `PYTHONPATH=src:tests .venv/bin/python -m unittest test_cli_experience.CLIExperienceTests.test_failed_generation_can_retry_without_removing_existing_directory -v`로 실패한 폴더가 남는 현상을 확인한다.
- [ ] **3. 최소 구현.** `config_root.mkdir(parents=True)` 이전 검사들은 유지한다. 그 다음 쓰기와
  `load_experiment(target)`를 `try` 안에 넣고 `except Exception`에서
  `shutil.rmtree(config_root)` 후 재발생시킨다. `shutil`을 import한다. `external/datasets`,
  `runs/`, 기존 설정은 정리하지 않는다.
- [ ] **4. 대상 검사.** 새 테스트와 `test_insufficient_trial_limit_does_not_publish_partial_experiment`,
  `test_structured_optimizer_options_complete_user_flow`를 실행한다.
- [ ] **5. 변경 파일만 커밋.** 예: `실패한 실험 설정 디렉터리를 정리`.

### 리뷰 후속: 복수 데이터셋과 session 실패

**파일:** `src/agent_optimizer/cli.py`, `src/agent_optimizer/setup_wizard.py`,
`tests/test_cli_experience.py`

- [ ] **1. 복수 데이터셋 재시도 회귀.** 두 번째 데이터셋 준비가 실패할 때 첫 번째
  `experiment.toml`을 남기지 않고 기존 sentinel은 보존하는지 검사한다. 두 번째 입력을
  고친 뒤 같은 이름으로 다시 init 하면 두 실험과 `session.json`이 생성돼야 한다.
- [ ] **2. 생성 후 출력 실패 회귀.** 정상 데이터셋 둘로 설정을 만들되 출력 stream의
  `write`가 `OSError`를 내게 하여 새 `session.json`·실험 폴더가 모두 정리되는지 검사한다.
  이전 `session.json`이 있는 경우에는 바이트가 유지되어야 한다.
- [ ] **3. 문자열 경계 회귀.** Optimizer 설정의 DEL(`\x7f`) 문자가 TOML로 왕복되는지
  확인한다. `test_multi_dataset_generation_failure_can_retry_without_leaving_first_plan`,
  `test_multi_dataset_output_failure_does_not_leave_dangling_session`,
  `test_generated_optimizer_strings_round_trip_del_character`를 실행한다.

## 인계 검증

작업 2 후 `make lint`, `make test`, `make doctor ARGS="--core --json"`와 합성
file-variants의 명시적 init/doctor/run/report를 실행한다. 성공 주장 전에 실제
`summary.json`, `report.html`, 종료 코드와 skip 수를 읽는다. 전송·CI 작업은
`docs/superpowers/plans/2026-09-25-portable-environment-readiness.md`에 별도로 정리한다.
