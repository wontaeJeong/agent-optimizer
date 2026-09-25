# MVP 기본 경로와 연구 경계 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 암묵적 연구 실행과 GEPA 병합을 비활성화하고 독립 stage 후보의 평가·변경 경계를 통일한다.

**Architecture:** `cli.py`의 설정 생성 사전 검사, `gepa.py`의 선택형 병합 진입 검사, `runner.py`의 stage 후보 검사만 바꾼다. 구현·등록·보고서 코드는 보존하고 활성 경로를 문서와 맞춘다.

**Tech Stack:** Python 3.11+, Typer CLI, unittest, TOML

**Spec:** `docs/superpowers/specs/2026-09-26-mvp-design-simplification-design.md`

## Global Constraints

- `merge` 구현을 삭제하지 않는다. `merge=true`만 평가/모델 호출 전에 명시적으로 거부한다.
- `--optimizer` 검사는 데이터셋 준비 전에 하고 기존 명시적 Optimizer와 대화형 wizard는 유지한다.
- stage가 소유하는 후보와 공통 baseline만 수정·평가하며 최종 validation 선택과 공유 baseline cache는 유지한다.
- 문서와 사용자 안내는 한국어로 작성하고 역사적 검증·설계 문서는 소급 수정하지 않는다.
- 작업 디렉토리는 `.worktrees/mvp-design-review`, 초기 기준은 `origin/main`이다.

## 파일 책임

- `src/agent_optimizer/cli.py`와 `tests/test_cli_experience.py`: 비대화형 설정 생성의 명시적 Optimizer 선택.
- `src/agent_optimizer/optimizers/gepa.py`와 `tests/test_research.py`: GEPA 병합의 미지원 경계.
- `src/agent_optimizer/runner.py`와 `tests/test_progress.py`: stage별 후보 소유권.
- `README.md`, `docs/status.md`, `docs/adding-components.md`, `docs/FUTURE.md`: 현재 활성 표면과 복원 조건.

---

### Task 1: 비대화형 init의 암묵적 GEPA 선택 비활성화

**Files:** Modify `src/agent_optimizer/cli.py:186,321-358`; Test `tests/test_cli_experience.py:782-818`; Modify `README.md:109-129`.

**Interfaces:** Consumes `main(argv)` and `_dispatch(SimpleNamespace(...))`; produces an actionable `ConfigurationError` for missing `--optimizer` before `prepare_selection`, preserving explicitly selected IDs.

- [ ] **Step 1: Write the failing test.** In `CLIExperienceTests` (use the class containing `test_noninteractive_init_requires_explicit_dataset_without_creating_files`), call `main(["init", "--project-root", str(self.root), "--agent", str(self.agent), "--name", "no-optimizer", "--dataset", "sample_text", "--editable", "configs/strategy.json", "--command-json", '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]', "--yes"])` with `patch("agent_optimizer.cli.prepare_selection", side_effect=AssertionError("준비가 먼저 실행됨"))`, captured stderr/stdout; assert exit 2, stderr includes `--optimizer`, and `self.root / "runs/configs/no-optimizer"` does not exist. Existing explicit baseline generation/run test remains the success regression.

  ```python
  def test_init_no_optimizer_fails_before_dataset_preparation(self):
      args = ["init", "--project-root", str(self.root), "--agent", str(self.agent),
              "--name", "no-optimizer", "--dataset", "sample_text",
              "--editable", "configs/strategy.json", "--command-json",
              '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]', "--yes"]
      errors = io.StringIO()
      with patch("agent_optimizer.cli.prepare_selection",
                 side_effect=AssertionError("준비가 먼저 실행됨")), \
              contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
          code = main(args)
      self.assertEqual(code, 2)
      self.assertIn("--optimizer", errors.getvalue())
      self.assertFalse((self.root / "runs/configs/no-optimizer").exists())
  ```
- [ ] **Step 2: Verify red.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -k no_optimizer -v` must fail because `prepare_selection` is called before any missing-optimizer error.
- [ ] **Step 3: Implement minimal change.** In `_dispatch`'s `init` branch, add `if not args.optimizer: raise ConfigurationError("Optimizer를 --optimizer ID로 명시하세요 (예: --optimizer baseline)")` before `component_inventory` and `prepare_selection`; change `chosen = args.optimizer or ["gepa"]` to `chosen = args.optimizer`. Update Typer `--optimizer` help to describe the required explicit selection. In README's CLI `init` explanation, state `--optimizer baseline` for the model-free check and explicit choice for research runs.

  ```python
  if not args.optimizer:
      raise ConfigurationError("Optimizer를 --optimizer ID로 명시하세요 (예: --optimizer baseline)")
  # 기존 인자 및 실행 명령 검사 후, 데이터셋 준비 전:
  chosen = args.optimizer
  ```
- [ ] **Step 4: Verify green.** Run the focused command from Step 2 and `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -k custom_scored_dataset -v`.
- [ ] **Step 5: Commit.** Stage only these three files, review staged diff, and commit with Korean message `init에서 Optimizer 명시 선택 요구`.

### Task 2: GEPA 병합의 validation-to-mutation 경로 비활성화

**Files:** Modify `src/agent_optimizer/optimizers/gepa.py:29-52`; Test `tests/test_research.py:102-163`; Modify `README.md:259-269`, `docs/status.md:32-35`, `docs/adding-components.md:83-91`, `docs/FUTURE.md:18-27`.

**Interfaces:** Consumes `GEPAOptimizer.optimize(context, seeds, config)`; produces `UnavailableError` before any `context.evaluate`/`evaluate_validation`/`propose`/model request for non-false `merge`, preserving default and `merge=false` search.

- [ ] **Step 1: Write failing tests.** Add a focused unittest: `context = Mock(); seed = Candidate("seed", "fixture", self.root, "hash"); self.assertRaisesRegex(UnavailableError, "GEPA merge.*보류")` around `GEPAOptimizer().optimize(context, [seed], {"file": "prompt.md", "iterations": 1, "merge": True})`; assert `context.evaluate.assert_not_called()` and `context.propose.assert_not_called()`. In the existing frontier/merge fixture, change its configuration to `{"file": "prompt.md", "iterations": 2, "merge": False}` and assert frontier `['c1', 'c2']` and `checkpoint['merges'] == []`; keep all production merge code intact.

  ```python
  from unittest.mock import Mock
  from agent_optimizer.optimizers.gepa import GEPAOptimizer

  def test_gepa_merge_rejected_before_evaluation(self):
      context = Mock()
      seed = Candidate("seed", "fixture", self.root, "hash")
      with self.assertRaisesRegex(UnavailableError, "GEPA merge.*보류"):
          GEPAOptimizer().optimize(context, [seed],
                                   {"file": "prompt.md", "iterations": 1, "merge": True})
      context.evaluate.assert_not_called()
      context.propose.assert_not_called()
  # 기존 frontier fixture는 merge=False로 실행하고 후보 ['c1', 'c2'], merges=[]를 확인.
  ```
- [ ] **Step 2: Verify red.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_research.py -k merge -v` must fail on the new early-rejection test.
- [ ] **Step 3: Implement minimal change.** Immediately after `only_keys(...)` in `GEPAOptimizer.optimize`, add `if config.get("merge", False) is not False: raise UnavailableError("GEPA merge는 보류 중입니다: validation 수치를 모델 수정 근거로 전달하지 않도록 재설계가 필요합니다")`. Leave the later `if config.get("merge", False) ...` branch unmodified. README/status/extension/FUTURE state that Pareto selection remains active, merge is blocked, and re-enabling requires train-only mutation evidence and a boundary test.

  ```python
  if config.get("merge", False) is not False:
      raise UnavailableError(
          "GEPA merge는 보류 중입니다: validation 수치를 모델 수정 근거로 전달하지 않도록 재설계가 필요합니다")
  ```
- [ ] **Step 4: Verify green.** Run the Step 2 command and `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_research.py -v`.
- [ ] **Step 5: Commit.** Stage only these six files, review staged diff, and commit with Korean message `GEPA 병합을 보류하고 연구 경계 명시`.

### Task 3: 독립 stage의 후보 수정·평가 경계 통일

**Files:** Modify `src/agent_optimizer/runner.py:61-81`; Test `tests/test_progress.py:257-280`.

**Interfaces:** `Context.propose(parent: Candidate, files: dict[str, str], producer: str)` and `Context.evaluate(candidate: Candidate)` accept baseline or own-stage candidate, reject other issued candidates with `ConfigurationError`; `Context.evaluate_batch` and `Context.evaluate_validation` retain their own guards.

- [ ] **Step 1: Write failing test.** In `ProgressTests`, register two in-memory classes under `registry.factories['optimizers']` and configure stages `first` and `second`. First saves `context.propose(seeds[0], {'configs/strategy.json': '{"repair": true}'}, 'first')` to a shared closure and returns `OptimizationResult([child])`. Second tries `context.evaluate(shared['child'])` and `context.propose(shared['child'], {'configs/strategy.json': '{"repair": false}'}, 'second')`, catches `ConfigurationError` for each and stores booleans in checkpoint; then `context.evaluate(seeds[0])`, creates/evaluates its own child and returns `OptimizationResult([child], checkpoint)`. Assert both denials, second stage completion, and both baseline/own train evaluations succeed. Set stage max_trials=5 and spec budget max_trials=20, final_stages=['second'].

  ```python
  from agent_optimizer.contracts import OptimizationResult

  def test_cross_stage_candidate_cannot_be_evaluated_or_proposed(self):
      shared = {}
      class First:
          def optimize(self, context, seeds, config):
              child = context.propose(seeds[0], {"configs/strategy.json": '{"repair": true}'}, "first")
              shared["child"] = child
              return OptimizationResult([child])
      class Second:
          def optimize(self, context, seeds, config):
              denied = {}
              for action in ("evaluate", "propose"):
                  try:
                      if action == "evaluate":
                          context.evaluate(shared["child"])
                      else:
                          context.propose(shared["child"],
                                          {"configs/strategy.json": '{"repair": false}'}, "second")
                  except ConfigurationError:
                      denied[action] = True
                  else:
                      denied[action] = False
              baseline = context.evaluate(seeds[0])
              child = context.propose(seeds[0],
                                      {"configs/strategy.json": '{"repair": true}'}, "second")
              own = context.evaluate(child)
              return OptimizationResult([child], {**denied, "baseline": baseline["valid"],
                                                  "own": own["valid"]})
      registry = Registry()
      registry.factories["optimizers"].update(first=First, second=Second)
      self.spec.update(stages=[{"id": "first", "optimizer": "first", "max_trials": 5},
                               {"id": "second", "optimizer": "second", "max_trials": 5}],
                       final_stages=["second"])
      self.spec["budget"]["max_trials"] = 20
      _, summary = run_experiment(self.spec, registry, self.root / "runs")
      stage = summary["groups"][0]["stages"][1]
      self.assertEqual(stage["status"], "completed")
      self.assertEqual(stage["checkpoint"], {"evaluate": True, "propose": True,
                                             "baseline": True, "own": True})
  ```
- [ ] **Step 2: Verify red.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_progress.py -k cross_stage_candidate -v` must fail because the second stage can evaluate/propose using the first stage's issued candidate.
- [ ] **Step 3: Implement minimal change.** At the start of `Context.propose`, before budget/candidate verification, add `if parent.id not in self._candidate_ids: raise ConfigurationError("Cannot propose from another stage's candidate")`; at the start of `Context.evaluate`, add `if candidate.id not in self._candidate_ids: raise ConfigurationError("Cannot evaluate another stage's candidate")`. CandidateStore's existing full identity/hash verification still applies after ownership checks.

  ```python
  if parent.id not in self._candidate_ids:
      raise ConfigurationError("Cannot propose from another stage's candidate")
  # 이 검사를 Context.propose의 기존 self._group.budget.remaining() 앞에 배치한다.

  if candidate.id not in self._candidate_ids:
      raise ConfigurationError("Cannot evaluate another stage's candidate")
  # 이 검사를 Context.evaluate의 기존 return self._group.evaluate(...) 앞에 배치한다.
  ```
- [ ] **Step 4: Verify green.** Run Step 2 and `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_plugin_contracts.py -v`.
- [ ] **Step 5: Commit.** Stage only runner and test file, review staged diff, and commit with Korean message `독립 stage 후보 수정과 평가 경계 통일`.

### Task 4: 전체 검증과 PR

**Files:** No source modifications unless verification finds a regression.

**Interfaces:** Consumes tasks 1-3; produces a clean worktree and a PR with actual verification evidence.

- [ ] **Step 1: Run full checks.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`, `PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml`, and `make lint`. Record test count/skips and demo `status`/`trials_used`.
- [ ] **Step 2: Inspect branch.** Check `git status --short --branch`, `git diff origin/main...HEAD`, and `git log --oneline -10`; confirm only intended commits and that the base directory remains on `main`.
- [ ] **Step 3: Publish.** Push `audit/mvp-design-review` to origin, create a Korean PR with scope and exact check results, and return its URL. Ask user whether to merge; do not merge without approval.
