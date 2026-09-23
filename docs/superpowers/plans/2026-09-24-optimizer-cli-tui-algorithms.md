# Optimizer CLI/TUI and Research Integrations Implementation Plan

**Execution note:** 구현·로컬 검증 명령과 미검증 범위는 `docs/verification.md#2026-09-24-cli-tui-and-research-method-integration`에 기록한다. 아래는 작업 당시 계획이며 실제 CLI 표면은 README를 따른다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This repository's agent instructions select inline execution; do not dispatch agents without explicit user request.

**Goal:** Deliver extensible end-user CLI/TUI with automatic preparation of explicitly selected CVDP, Verilog-Eval or user datasets, three real research optimization loops, progress and an HTML report.

**Architecture:** Extend the current runner/contracts instead of adding an orchestration framework. A team-owned extension manifest supplies file plugin registrations; dataset providers prepare inputs and evaluator references, while the existing runner owns trials and selection. Versioned events drive both live terminal display and an offline HTML report.

**Tech Stack:** Python >=3.11, stdlib argparse/JSON/TOML/unittest/HTML; existing OpenAI-compatible model transport; pinned benchmark sources and OSS simulators. Use isolated Docker only for benchmark evaluators requiring it.

**Spec:** `docs/superpowers/specs/2026-09-24-optimizer-cli-tui-algorithms-design.md`

## Global Constraints

- Team extensions live in `experiments/<team>/`; adding a dataset, harness or optimizer requires no edits to built-in registry or CLI menu code.
- User selects a dataset explicitly; selected supported built-ins download and validate assets automatically. Never install or run from ignored `.references/` at runtime.
- CVDP source SHA `8e894cf74414ab1eaea1e2b4e80a02f123df07b6`; Verilog-Eval source SHA `c498220d0a52248f8e3fdffe279075215bde2da6`.
- Verilog-Eval v2 requires Icarus v12; do not reuse the CVDP v13 evaluation image. Keep benchmark tests/references private.
- Preserve candidate snapshot/editable checking, independent stages, `test` only after frozen selection, nullable/partial usage, existing CLI and schema compatibility.
- Project core is domain-independent, argv execution has `shell=False`, credentials are environment-only, errors never fall back to synthetic success.

## File ownership map

| Unit | Files | Responsibility |
|---|---|---|
| Extensions | `src/agent_optimizer/catalog.py`, `contracts.py`, `registry.py`, `config.py`, `experiments/dataset-template/*` | Load explicit versioned manifests; dataset provider contract; validate and fingerprint all team files; list new components dynamically. |
| Dataset integration | `src/agent_optimizer/datasets.py`, `examples/benchmarks/cvdp.py`, `examples/benchmarks/verilog_eval.py`, `examples/benchmarks/verilog_evaluator.py` | Explicit choice; pinned/cache-aware preparation; separated public tasks/private scoring; custom dataset conversion. |
| Run and event stream | `src/agent_optimizer/runner.py`, `results.py`, `contracts.py` | Per-stage budgets, train/validation API, phase timing, durable progress events and incomplete-run persistence. |
| Research search | `src/agent_optimizer/optimizers/{research,gepa,meta_harness,ecdysis}.py`, `registry.py` | Bounded model proposals, distinct method loops, durable usage and iteration events. |
| End-user UX | `src/agent_optimizer/{cli,setup_wizard,terminal_report,html_report}.py` | Interactive/noninteractive config generation, live status, and standalone report. |
| Evidence and guidance | `tests/test_{catalog,datasets,research,progress,html_report}.py`, existing focused regression files, README/docs/experiments | Assertions about boundaries and extensibility; match documentation to verified features. |

---

### Task 1: Team component discovery and dataset provider contract

**Files:** Create `src/agent_optimizer/catalog.py`, `experiments/dataset-template/{extensions.toml,provider.py,README.md}`, `tests/test_catalog.py`; modify `src/agent_optimizer/{contracts,registry,config}.py`, `docs/adding-components.md`.

**Interfaces:** `DatasetProvider.describe() -> dict`, `DatasetProvider.prepare(cache: Path, *, offline: bool) -> dict` returning a `benchmark` path, an `evaluator` file reference, and `provenance`. `load_extensions(path: Path, project_root: Path) -> dict` validates `[plugins.optimizers]`, `[plugins.harnesses]`, `[plugins.evaluators]`, `[plugins.datasets]` and `[plugin_dependencies]`; all file references are relative to project root, just as for existing experiment plugins. `Registry.load_plugins(root, mapping)` resolves registered providers without hardcoded team names. Existing experiment manifests remain valid.

- [ ] **Step 1: Write failing fixture tests.** In `tests/test_catalog.py`, create a temporary extension manifest and file plugins with `tempfile.TemporaryDirectory`; assert its dataset/harness/optimizer names are listed, their code runs in one small experiment, and invalid/duplicate/missing registrations fail before any plugin side effects. Assert `registry.py` and CLI don't mention the fixture names.
  ```python
  # In a TemporaryDirectory after writing extensions.toml and dataset.py:Provider:
  inventory = load_extensions(root / "experiments/team/extensions.toml", root)
  self.assertEqual(inventory["plugins"]["datasets"]["team_set"], "dataset.py:Provider")
  self.assertIn("team_set", inventory["plugins"]["datasets"])
  ```
- [ ] **Step 2: Run red.** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_catalog.py -v` must fail for absent `load_extensions`.
- [ ] **Step 3: Implement contract and loader.** Use `tomllib` and existing `plugin_files(root, plugins, dependencies)` for validated `file.py:Symbol` paths; extend permitted kind to `datasets` and `Registry.factories` with an empty built-in dataset map. Return metadata via `describe()` only after loading a trusted explicit file. Make `load_experiment` retain the extension manifest fingerprint and preflight verify the chosen provider matches the evaluator.
  ```python
  def load_extensions(path: Path, project_root: Path) -> dict:
      with path.open("rb") as stream:
          value = tomllib.load(stream)
      if value.get("schema_version") != 1:
          raise ConfigurationError("Extension schema_version must be 1")
      plugin_files(project_root, value.get("plugins", {}), value.get("plugin_dependencies", {}))
      return value
  ```
- [ ] **Step 4: Run green and regression.** Run focused test above plus `PYTHONPATH=src python3 -m unittest discover -s tests -p test_plugin_contracts.py -v`; reject altered helper dependencies before execution.
- [ ] **Step 5: Commit.** Stage only these task files and `git commit -m "Add team-owned dataset and integration catalog"`.

### Task 2: Runner feedback, fair budgets and progress events

**Files:** Modify `src/agent_optimizer/{contracts,runner,results,config}.py`; create `tests/test_progress.py`; update `tests/test_run_lifecycle.py`.

**Interfaces:** `OptimizationContext.evaluate_validation(candidate: Candidate) -> dict` exposes per-task numeric scores with no private evaluator artifacts; `OptimizationContext.emit(event: str, **fields) -> None` records algorithm iteration events. `EventStore.append` persists a `schema_version=1`, ISO timestamp and stage/group/task identity; task start, Agent start/end and evaluation start/end events precede completion. `Budget` includes explicit stage allowances and a reserved final selection/test allowance.

- [ ] **Step 1: Write red tests.** Fixture runner tests assert `trial_started` precedes `trial_completed`, all events have timestamps, a deliberately slow evaluator has an `evaluation_started` entry before it returns, per-task validation scores are visible but private task data is absent, stage A exhaustion does not consume stage B's reserved trials, and test remains after `frozen_selection.json`.
  ```python
  events = [json.loads(s) for s in (root / "events.jsonl").read_text().splitlines()]
  self.assertLess(next(i for i, e in enumerate(events) if e["event"] == "trial_started"),
                  next(i for i, e in enumerate(events) if e["event"] == "trial_completed"))
  self.assertTrue(all("timestamp" in e for e in events))
  ```
- [ ] **Step 2: Run red.** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_progress.py -v` fails on missing event/validation methods.
- [ ] **Step 3: Add the minimum runner changes.** Filter validation records to `task_id`, `status`, `valid`, numeric metrics; keep `history()` train-only. Emit start/end events at the existing `GroupRunner.trial` phase boundaries. Allocate per-stage limits up front from `budget.max_trials`, leaving baseline/final trial reservations; preflight rejects insufficient budgets rather than launching a partial comparison. In `finally`, keep existing summary/report writes.
  ```python
  def evaluate_validation(self, candidate):
      self._group.evaluate(candidate, "validation")
      return {"tasks": [{"task_id": r["task_id"], "metrics": r["metrics"], "valid": r["valid"]}
                        for r in self._group.records if r["candidate_id"] == candidate.id
                        and r["split"] == "validation"]}
  ```
- [ ] **Step 4: Run green and lifecycle regression.** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_progress.py -v` and `PYTHONPATH=src python3 -m unittest discover -s tests -p test_run_lifecycle.py -v` pass.
- [ ] **Step 5: Commit.** `git commit -m "Record timed run phases and protect stage budgets"` after staging related files.

### Task 3: Explicit datasets and pinned benchmark preparation

**Files:** Create `src/agent_optimizer/datasets.py`, `examples/benchmarks/{cvdp,verilog_eval,verilog_evaluator}.py`, `tests/test_datasets.py`; reuse `examples/ace-rtl/{prepare,evaluator}.py` and `examples/ace-rtl/environment/setup.py` without altering the locked SHA.

**Interfaces:** `prepare_dataset(name: str, cache: Path, *, offline: bool) -> dict` returns a versioned benchmark path, evaluator file reference and asset hashes. `import_verilog_eval(tree: Path, mode: str) -> dict` builds the public task manifest. `cvdp` delegates to the current reviewed no-commercial downloader/importer; `verilog-eval` fetches the pinned Git tree and imports either v2 task mode, keeping tests outside `Task.files`. `custom` accepts existing tasks JSON and explicit evaluator registration; an unpartitioned custom dataset is grouped by `family` and deterministically assigned to splits.

- [ ] **Step 1: Write red fixture tests.** Stub the downloader with a local verified fixture; assert bad hash and offline missing fail without publishing partial files. Use two related Verilog problem IDs from both modes and assert neither `_test.sv` nor `_ref.sv` appears in public task files/optimizer feedback and both share a split. Assert an unsupported simulator version or missing evaluator is `UnavailableError`, not `passed=0`.
  ```python
  manifest = import_verilog_eval(tree, mode="spec-to-rtl")
  for task in manifest["tasks"]:
      self.assertFalse(any(name.endswith(("_test.sv", "_ref.sv")) for name in task["files"]))
  ```
- [ ] **Step 2: Run red.** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_datasets.py -v` fails on missing provider.
- [ ] **Step 3: Implement one provider at a time.** First wrap the reviewed CVDP helper without importing ACE agent behavior, then add pinned Verilog tree validation, v2 prompt/task import and private evaluation using a separately verified Icarus v12 runtime. Run a known correct and deliberately wrong local candidate through exactly the proposed scoring command; record provenance and source hashes. Implement custom schema validation and family-isolated split after the two built-ins.
  ```python
  for prompt_path in sorted(dataset_dir.glob("*_prompt.txt")):
      stem = prompt_path.name.removesuffix("_prompt.txt")
      public = {"prompt.txt": prompt_path.read_text(encoding="utf-8"), "solution.sv": ""}
      tasks.append({"id": stem, "split": splits[stem], "family": stem, "files": public,
                    "evaluation": {"problem_id": stem}, "prompt": public["prompt.txt"]})
  # Keep `_test.sv`/`_ref.sv` exclusively in the evaluator's separately locked tree.
  ```
- [ ] **Step 4: Run focused tests and actual tool probe.** Run the focused test above and existing `test_ace_demo.py`/`test_integrations.py`. Run the Verilog positive/negative fixture only when v12 is actually installed/prepared; record exact command/output and block live use when not available.
- [ ] **Step 5: Commit.** `git commit -m "Prepare selected benchmark datasets with private scoring"` after staging related files.

### Task 4: Shared bounded proposer and GEPA search

**Files:** Create `src/agent_optimizer/optimizers/{research,gepa}.py`, `tests/test_research.py`; modify `src/agent_optimizer/registry.py`.

**Interfaces:** `research.propose_text(context, parent, filename, evidence, instruction, timeout) -> Candidate` uses `ModelSettings.from_env`, `complete`, strict JSON content parsing, `context.record_usage` (None for unknown), and `context.propose`. `GEPAOptimizer.optimize` uses train per-task minibatches, reflection and bounded mutation, per-task validation scores and a Pareto frontier, with optional merge and iteration checkpoints.

- [ ] **Step 1: Write red deterministic model tests.** Patch `complete` to return different text for two trials; assert the stronger candidate is kept, unequal per-task scores produce a nontrivial Pareto frontier and merged candidate has two traceable parents (or explicit merge metadata when snapshot parentage supports one parent). Assert no `test` event until freeze and no private feedback enters model messages.
  ```python
  sent = []
  def reply(messages, **kwargs):
      sent.append(messages)
      return {"choices": [{"message": {"content": '{"content":"better"}'}}]}
  with patch("agent_optimizer.optimizers.research.complete", side_effect=reply):
      result = GEPAOptimizer().optimize(context, [seed], {"file": "prompt.md", "iterations": 1})
  self.assertGreaterEqual(len(result.candidates), 1)
  self.assertNotIn("secret_testbench", json.dumps(sent))
  ```
- [ ] **Step 2: Run red.** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_research.py -v` fails on missing GEPA registration.
- [ ] **Step 3: Implement proposal/parser and frontier logic.** Accept finite non-null scores only; prefer nondominated vectors, bound pool and merges by configured max iterations/trials, checkpoint seed/parent/frontier per iteration. Reject invalid model responses before proposing; emit iteration start/end.
  ```python
  def dominates(left: tuple[float, ...], right: tuple[float, ...]) -> bool:
      return all(a >= b for a, b in zip(left, right)) and any(a > b for a, b in zip(left, right))
  # Normalize minimize metrics before comparison; vectors are same-length and finite.
  ```
- [ ] **Step 4: Run green.** Run the focused test and `test_plugin_contracts.py` so built-in names and file plugins coexist.
- [ ] **Step 5: Commit.** `git commit -m "Implement bounded GEPA reflective search"` after staging task files.

### Task 5: Meta-Harness and Ecdysis loops

**Files:** Create `src/agent_optimizer/optimizers/{meta_harness,ecdysis}.py`; modify `src/agent_optimizer/registry.py`, `tests/test_research.py`.

**Interfaces:** Both implement `Optimizer.optimize(context, seeds, config) -> OptimizationResult`, require a declared editable scaffold file, call the shared proposer, and emit per-round events. `MetaHarnessOptimizer` validates candidate interface and tracks the best validation frontier; `EcdysisOptimizer` groups train failures by distinct task IDs, runs bounded configurable multi-pass collaborative analysis and accepts only strict train-score improvements.

- [ ] **Step 1: Write red fixtures.** Assert Meta-Harness rejects invalid candidate code before scoring and retains an improved runnable scaffold. Assert Ecdysis distinguishes repeated cross-task failures from two failures of one task, emits the multi-pass specification and rejects an equal-score candidate; confirm no baseline/synthetic fallback on model failure.
  ```python
  groups = group_failures([{"task_id": "A", "pattern": "timeout"},
                           {"task_id": "B", "pattern": "timeout"},
                           {"task_id": "A", "pattern": "parse"}])
  self.assertEqual(groups["timeout"]["distinct_tasks"], 2)
  self.assertEqual(groups["parse"]["distinct_tasks"], 1)
  ```
- [ ] **Step 2: Run red.** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_research.py -v` fails on the absent implementations.
- [ ] **Step 3: Implement loops independently.** Use bounded `context.history` and `context.evaluate_validation`, pass only summarized train evidence to the model; for Ecdysis compare `train` aggregates before/after editing. Preserve rejected proposals and checkpoint decisions; return candidate lists and never invoke a sibling optimizer.
  ```python
  def group_failures(records):
      groups = {}
      for record in records:
          group = groups.setdefault(record["pattern"], {"records": [], "distinct_tasks": 0})
          group["records"].append(record)
          group["distinct_tasks"] = len({r["task_id"] for r in group["records"]})
      return groups
  ```
- [ ] **Step 4: Run green with boundary tests.** Focused suite, `test_boundaries.py`, `test_run_lifecycle.py` pass; run a small real model call only when credentials and evaluator exist, recording actual results.
- [ ] **Step 5: Commit.** `git commit -m "Implement Meta-Harness and Ecdysis search loops"` after staging task files.

### Task 6: Wizard, scriptable CLI and terminal progress

**Files:** Create `src/agent_optimizer/{setup_wizard,terminal_report}.py`, `tests/test_cli_experience.py`; modify `src/agent_optimizer/cli.py`.

**Interfaces:** `agent-opt datasets list|prepare <name> [--offline]`, `agent-opt init --agent PATH --argv ARG ... --editable PATH --dataset NAME --optimizer NAME [--extensions PATH] [--yes]`, `agent-opt tui [--extensions PATH]`, and existing `plan/run/report` commands. `write_experiment(config_root: Path, *, agent: Path, harness: dict, dataset: dict, stages: list[dict], plugins: dict) -> Path` writes valid input manifests under ignored `runs/configs/<name>/` and returns the experiment path; `run` uses one event callback for TTY and stderr renderers.

- [ ] **Step 1: Write red CLI tests.** Non-TTY no dataset exits 2 without downloads, `--dataset` with a prepared local fixture creates a loadable experiment and selected team extension registrations, plain stderr progress does not corrupt JSON stdout, and interactive prompt cancellation creates no files.
  ```python
  with patch("sys.stdin.isatty", return_value=False):
      self.assertEqual(main(["init", "--agent", str(source)]), 2)
  self.assertFalse((root / "runs" / "configs").exists())
  ```
- [ ] **Step 2: Run red.** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_cli_experience.py -v` fails on absent subcommands.
- [ ] **Step 3: Generate settings via existing schemas.** Use `load_experiment` to validate the generated manifests before any actual run. TTY wizard asks one choice at a time and confirms the full plan; terminal renderer polls active event state to update elapsed time even while a subprocess blocks. Surface component inventory from the selected extension manifest, not literals in UI code.
  ```python
  path = write_experiment(config_root, agent=agent, harness=harness, dataset=dataset,
                          stages=stages, plugins=extensions.get("plugins", {}))
  load_experiment(path)  # A broken wizard output must never be reported as ready.
  ```
- [ ] **Step 4: Run green plus old CLI tests.** Run focused suite, `test_menu.py`, `test_core.py`; demonstrate an installed `agent-opt --help` command.
- [ ] **Step 5: Commit.** `git commit -m "Add interactive and scriptable optimizer setup"` after staging task files.

### Task 7: Standalone HTML report

**Files:** Create `src/agent_optimizer/html_report.py`, `tests/test_html_report.py`; modify `src/agent_optimizer/{runner,cli}.py` and `src/agent_optimizer/results.py`.

**Interfaces:** `write_html_report(root: Path, summary: dict) -> Path` reads run-local events/manifest, escapes every Agent-derived string and writes `report.html` atomically. Called from `run_experiment`'s `finally` for completed, error and interrupted statuses. `agent-opt report <run_dir> --html` writes/displays the same artifact.

- [ ] **Step 1: Write red report tests.** Use a small run with two algorithm stages and slow tasks; assert HTML has split-aware baseline/winner tables, stage and task wall times, provenance, partial/nullable usage and a visible missing-test label. Inject `<script>alert(1)</script>` in feedback and verify only escaped text appears; interrupt a fixture run and assert report still exists.
  ```python
  page = write_html_report(root, summary).read_text(encoding="utf-8")
  self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
  self.assertNotIn("<script>alert(1)</script>", page)
  ```
- [ ] **Step 2: Run red.** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_html_report.py -v` fails on absent writer.
- [ ] **Step 3: Render from persisted records.** Limit displayed untrusted text lengths, use `html.escape`, local-only CSS/JS, stable file-relative links and manifest/event-derived totals. Never embed private reference files or remote assets. Report regeneration leaves summary and CSV semantics unchanged.
  ```python
  def text(value: object, limit: int = 4000) -> str:
      return html.escape(str(value)[:limit], quote=True)
  target = root / "report.html"
  target.write_text("<!doctype html><html><body>" + text(summary["status"]) + "</body></html>",
                    encoding="utf-8")
  ```
- [ ] **Step 4: Run green.** Run focused test, `test_results.py` and `test_run_lifecycle.py`, open the generated HTML in a browser if available to check legibility and empty/failure states.
- [ ] **Step 5: Commit.** `git commit -m "Render self-contained run reports"` after staging task files.

### Task 8: Team guide, compatibility and release evidence

**Files:** Modify `README.md`, `docs/{CONTEXT,status,NEXT_STEPS,FUTURE,adding-components,SOURCES}.md`, `THIRD_PARTY.md`, `experiments/README.md`; create example team extension manifests and add integration tests to `tests/test_catalog.py`.

**Interfaces:** A copyable team dataset + harness + optimizer is visible to `datasets list`, runs from `agent-opt init --extensions <manifest>` and appears with hashes in HTML/JSON. No central registry or CLI source changes in the example addition.

- [ ] **Step 1: Add acceptance regression.** Copy the three team templates under a temporary folder, load via an extension manifest and execute a tiny local fixture end to end; assert original source unchanged and test evaluated only after selection.
  ```python
  inventory = load_extensions(team / "extensions.toml", root)
  self.assertEqual(set(inventory["plugins"]), {"datasets", "harnesses", "optimizers", "evaluators"})
  self.assertEqual(original.read_bytes(), before)
  ```
- [ ] **Step 2: Run red against current docs/examples.** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_catalog.py -v` fails until the copied examples have runnable references.
- [ ] **Step 3: Update all user instructions with exact commands.** Differentiate slots, fixture behavior, real benchmark tool verification and model evidence; record pinned source/revision and consumed files without changing ACE/CVDP SHA. Give Mac and Ubuntu prepared-tool commands and missing-credential diagnostics. Check docs for stale claims that rich TUI/three algorithms/Verilog-Eval are deferred.
  ```bash
  agent-opt datasets list --extensions experiments/my-team/extensions.toml
  agent-opt init --agent ./my-agent --dataset verilog-spec --optimizer gepa --editable prompts/system.md --command-json '["python3","{agent_dir}/agent.py","{task_dir}"]' --yes
  agent-opt run runs/configs/my-agent/experiment.toml
  agent-opt report runs/<run-id> --html
  ```
- [ ] **Step 4: Verify fresh behavior.** Run `PYTHONPATH=src python3 -m unittest discover -s tests -p test_plugin_contracts.py -v`, `PYTHONPATH=src python3 -m unittest discover -s tests -v`, `PYTHONPATH=src python3 -m agent_optimizer run examples/minimal/experiment.toml`, `make lint`, and `git diff --check`. Record exact skipped environment-dependent checks; do not call a fixture result a live optimizer success.
- [ ] **Step 5: Commit and publish.** Inspect worktree status/diff/log, commit only intended files, push the worktree branch and create a PR with `gh pr create`; include exact verification and limitations, return its URL, then ask before merging.
