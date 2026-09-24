# User Configuration Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `agent-opt init` reliably generate runnable experiments for structured optimizer options and permit retry after generation fails.

**Architecture:** Keep the current CLI and TOML writer. Recursively serialize JSON-compatible values as TOML literals, validate through `load_experiment`, and remove only a newly created config directory on an exception. Keep prepared datasets and preexisting configurations untouched.

**Tech Stack:** Python 3.11+, stdlib `tomllib`/`unittest`, existing `agent_optimizer` CLI and synthetic fixture.

**Spec:** `docs/superpowers/specs/2026-09-25-readiness-followup-design.md`

## Global Constraints

- Preserve the existing CLI/TUI, explicit dataset choice, common contracts and pinned source/data identities.
- Use the existing worktree and project `.venv`; do not write to the default checkout.
- Synthetic fixture results are wiring evidence, not real Agent performance.
- Do not store credentials or private endpoint details in generated configuration.

---

## File map

- `src/agent_optimizer/setup_wizard.py`: TOML literal writer and ownership of generated config directory.
- `tests/test_cli_experience.py`: user-facing generation/doctor/run/rollback regression tests.

### Task 1: Serialize nested optimizer options

**Files:**
- Modify: `src/agent_optimizer/setup_wizard.py:58-68`
- Test: `tests/test_cli_experience.py` (`CLIExperienceTests`)

**Interfaces:**
- Consumes: `main(["init", ..., "--optimizer-config", JSON, "--yes"])` and `_section(name, mapping)`.
- Produces: `_literal(value) -> str` returning TOML literals for strings, booleans, finite numbers, arrays and string-keyed inline tables; unsupported values raise `ConfigurationError`.

- [ ] **Step 1: Write a failing end-to-end regression.** In `CLIExperienceTests`, create a command with the usual `self.root`, `self.agent`, `self.data`, command JSON, `--optimizer file_variants`, and:

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
  with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
      self.assertEqual(main(["doctor", "--plan", str(plan), "--json"]), 0)
      self.assertEqual(main(["run", str(plan)]), 0)
  ```

  Use `--name structured-options`, `--agent str(self.agent)`, `--dataset str(self.data)`, `--evaluator examples/minimal/evaluator.py:TextFixtureEvaluator`, `--editable configs/strategy.json`, and `--command-json '["{python}","{agent_dir}/src/fixture_agent.py","{task_dir}"]'` as in existing nearby tests. Inspect the resulting summary to assert synthetic=true, completed, and baseline 0 versus selected 1 on validation; assert `report.html` exists.

- [ ] **Step 2: Run only the new test; expect the TOML parser to reject the colon in the array of objects.** Run `PYTHONPATH=src:tests .venv/bin/python -m unittest test_cli_experience.CLIExperienceTests.test_structured_optimizer_options_complete_user_flow -v`.
- [ ] **Step 3: Implement recursive `_literal`.** Preserve the existing scalar output; handle `list`/`tuple` with `"[" + ", ".join(_literal(item) ...) + "]"`, `dict` with quoted string keys and `" = "` inside `{ ... }`, and reject `None`, non-finite floats, and non-string dict keys with `ConfigurationError`. Validate using the existing `load_experiment` call, not a separate format parser.
- [ ] **Step 4: Run the targeted test plus existing scalar settings tests.** Run `PYTHONPATH=src:tests .venv/bin/python -m unittest test_cli_experience.CLIExperienceTests.test_structured_optimizer_options_complete_user_flow test_cli_experience.CLIExperienceTests.test_gepa_trial_allowance_tracks_requested_iterations_and_merge -v`; expect both to pass.
- [ ] **Step 5: Commit only the writer and test.** Use a concise message consistent with recent history, e.g. `Fix structured optimizer config generation`.

### Task 2: Roll back a failed generated config

**Files:**
- Modify: `src/agent_optimizer/setup_wizard.py:116-209`
- Test: `tests/test_cli_experience.py` (`CLIExperienceTests`)

**Interfaces:**
- Consumes: `write_experiment(config_root, ..., stages, ...) -> Path`, its existing early `config_root.exists()` guard, `_literal` from Task 1 and `load_experiment`.
- Produces: same signature and output on success; on failure after `mkdir`, removes only its newly created directory and re-raises the original error.

- [ ] **Step 1: Write a failing retry regression.** Call `main(init_args)` with `--name invalid-once`, `--optimizer baseline`, and `--optimizer-config '{"baseline":{"unsupported":null}}'`; assert exit 2 and `not (self.root / "runs/configs/invalid-once").exists()`. Then call the same init command with the invalid config removed and assert exit 0. In a separate assertion create `runs/configs/existing` with a `sentinel` file, call `main` for `--name existing`, and verify exit 2 plus unchanged sentinel bytes.
- [ ] **Step 2: Run only the new rollback test; expect the folder left by the failed serializer.** Run `PYTHONPATH=src:tests .venv/bin/python -m unittest test_cli_experience.CLIExperienceTests.test_failed_generation_can_retry_without_removing_existing_directory -v`.
- [ ] **Step 3: Implement rollback at the creation boundary.** Keep all pre-creation checks outside the `try`. After `config_root.mkdir(parents=True)`, place the current writes and `load_experiment(target)` in `try`; in `except Exception` call `shutil.rmtree(config_root)` and re-raise. Import `shutil`. Do not clean `external/datasets`, `runs/` or a preexisting config folder.
- [ ] **Step 4: Run the new and related generation tests.** Run `PYTHONPATH=src:tests .venv/bin/python -m unittest test_cli_experience.CLIExperienceTests.test_failed_generation_can_retry_without_removing_existing_directory test_cli_experience.CLIExperienceTests.test_insufficient_trial_limit_does_not_publish_partial_experiment test_cli_experience.CLIExperienceTests.test_structured_optimizer_options_complete_user_flow -v`; expect pass.
- [ ] **Step 5: Commit only the rollback and test.** Example message: `Clean up failed generated experiment configs`.

## Handoff verification

After Task 2, run `make lint`, `make test`, `make doctor ARGS="--core --json"`, and an explicit `agent-opt init`/doctor/run/report for the synthetic file-variants configuration. Read the actual `summary.json`, `report.html`, exit codes and skip counts before reporting success. The transport/CI work is planned separately in `docs/superpowers/plans/2026-09-25-portable-environment-readiness.md`.
