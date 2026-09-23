# Central Registry and Shared Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace team `extensions.toml` discovery with central Python registration and make dataset/experiment readiness available to both Agent Optimizer users and the existing developer setup/doctor/menu flows.

**Architecture:** `Registry` owns explicit Python registrations and is the inventory source for CLI/TUI/setup/doctor; existing per-experiment `[plugins.*]` files remain usable. Dataset providers offer an opt-in preparer and a read-only doctor, composed into one readiness report for selected datasets/experiments and existing developer diagnostics. Keep existing ACE/full and core-only flows intact and make selected CVDP setup evaluation-only.

**Tech Stack:** Python >=3.11 stdlib, argparse/TOML/JSON/unittest, POSIX `sh` bootstrap, Mac Docker ARM64 / Ubuntu x86_64 OSS tool paths.

**Spec:** `docs/superpowers/specs/2026-09-24-optimizer-cli-tui-algorithms-design.md`

## Global Constraints

- Team implementations live under `experiments/<team>/` or reusable domain code under `examples/`; centrally register each ID in `src/agent_optimizer/registry.py`. No `extensions.toml`, `--extensions`, import scanning, or install entry-point edits for new team choices.
- Preserve explicit `experiment.toml [plugins.*]` registrations and train/validation/test isolation; generated configurations and manifests record selected code/dependency hashes without credentials.
- `DatasetProvider.prepare(cache: Path, *, offline: bool = False) -> dict` may acquire verified assets only on explicit selection; `DatasetProvider.doctor(cache: Path) -> list[dict]` and `doctor --plan` never download, install, build, run an Agent/optimizer/evaluator, or call a model. Actual model connectivity requires explicit `--model`.
- `make setup` / `make doctor` without `--dataset` retain the full ACE profile; `--core` stays Docker/data-free and conflicts with `--dataset`.
- Dataset-only CVDP setup uses existing CVDP revision `8e894cf74414ab1eaea1e2b4e80a02f123df07b6` and fixed HF hashes; no ACE OpenCode Agent image. Verilog-Eval source remains `c498220d0a52248f8e3fdffe279075215bde2da6` and its separate Icarus v12 image remains mandatory.
- Continue work in the existing `feat/optimizer-cli-tui-html` worktree/PR #12; do not modify base checkout's `.gitignore` or claim actual deployed-model performance without a real run.

## File ownership map

| Unit | Files | Responsibility |
|---|---|---|
| Python registration | `src/agent_optimizer/{registry,setup_wizard,cli,config,runner}.py`; remove `src/agent_optimizer/catalog.py`, `examples/benchmarks/extensions.toml`, `experiments/dataset-template/extensions.toml` | One code registration table; preserve explicit experiment plugins; CLI/TUI inventory and source fingerprinting without extension manifests. |
| Read-only readiness | `src/agent_optimizer/readiness.py`, `contracts.py`, `examples/benchmarks/{cvdp,verilog_eval}.py`, `src/agent_optimizer/cli.py` | Typed checks, dataset `doctor()`, user `doctor --dataset/--plan`; no writes/network/Agent execution. |
| Evaluation-only CVDP | `examples/ace-rtl/environment/{setup,diagnostics}.py`, `examples/benchmarks/cvdp.py`, `examples/benchmarks/verilog_eval.py` | Separate selected evaluation prep/lock from full ACE; dataset doctor validates prepared cache and runtime version. |
| Developer entry points | `scripts/{bootstrap.sh,dev.py,dev_doctor.py,menu.py}`, `Makefile` if needed | Safely forward dataset flags, reuse readiness in developer doctor, route menu to TUI; retain old setup/core/ACE options. |
| Evidence/docs | Focused `tests/test_{catalog,cli_experience,datasets,dev_doctor,dev_onboarding,menu}.py`, `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `experiments/README.md`, `experiments/dataset-template/README.md`, `docs/{CONTEXT,status,NEXT_STEPS,FUTURE,architecture,adding-components,development,SOURCES,verification}.md` | Protect compatibility and factual validation scope. |

---

### Task 1: Code-registered component inventory and wizard

**Files:** Modify `src/agent_optimizer/{registry,setup_wizard,cli,config,runner}.py`; delete `src/agent_optimizer/catalog.py`, `examples/benchmarks/extensions.toml`, `experiments/dataset-template/extensions.toml`; update `tests/{test_catalog,test_cli_experience,test_plugin_contracts}.py`.

**Interfaces:** `Registry.load_project(root: Path) -> None` loads central `PROJECT_COMPONENTS: dict[str, dict[str,str]]` and `PROJECT_DEPENDENCIES: dict[str,list[str]]` from `registry.py` using the existing validated `file.py:Symbol` loader. `Registry.describe()` reflects centrally registered datasets/evaluators/harnesses/optimizers. `component_inventory(project_root: Path) -> tuple[Registry, dict, dict]` returns the same registry and code/dependency references needed for run hashing. `prepare_selection(project_root: Path, selection: str, *, evaluator: str|None=None, offline: bool=False) -> tuple[dict,dict,dict]` and generated plans have no extension argument/key. Existing `[plugins.*]` preflight remains supported.

- [ ] **Step 1: Write failing behavior tests.** Central registry includes CVDP, `verilog-spec`, `verilog-completion`, their evaluators and an example team `DatasetProvider`/Harness/Optimizer registered only in Python. `agent-opt datasets list`, `init`, `plugins` and `tui` use that inventory without `--extensions`; generated plans have no `extensions` key or `extensions_sha256`. Existing explicit `[plugins.optimizers]` team fixture still executes and is hashed. CLI rejects obsolete `--extensions` before preparing assets. Assert observable inventory/run behavior, not source text.
  ```python
  registry = Registry()
  registry.load_project(project_root)
  self.assertIn("verilog-spec", registry.describe()["datasets"]["implemented"])
  self.assertNotIn("extensions", load_experiment(generated)["stages"][0])
  ```
- [ ] **Step 2: Observe red.** Run `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_catalog.py -v` and `-p test_cli_experience.py -v`; expect missing code registration/legacy argument rejection.
- [ ] **Step 3: Implement registration and consumption.** Keep mapping in `registry.py`, load files via existing `plugin_files`/`Registry.load_plugins` so missing/duplicate IDs fail. Remove `load_extensions`, manifest merges and CLI `--extensions` flags; use `Registry.load_project(project_root)` in list/prepare/init/plan/run and record selected file/plugin dependency digests in `runner.py`. Preserve `Registry()` bare builtins and per-experiment plugin checks for old fixtures.
  ```python
  PROJECT_COMPONENTS = {"datasets": {"cvdp": "examples/benchmarks/cvdp.py:Provider",
                                    "verilog-spec": "examples/benchmarks/verilog_eval.py:Provider",
                                    "verilog-completion": "examples/benchmarks/verilog_eval.py:CompletionProvider"},
                        "evaluators": {"cvdp": "examples/ace-rtl/evaluator.py:CVDPEvaluator",
                                       "verilog_eval": "examples/benchmarks/verilog_evaluator.py:VerilogEvaluator"}}
  PROJECT_DEPENDENCIES = {"datasets/cvdp": ["examples/ace-rtl/prepare.py",
                                              "examples/ace-rtl/environment/setup.py"]}
  def load_project(self, root: Path) -> None:
      plugin_files(root, PROJECT_COMPONENTS, PROJECT_DEPENDENCIES)
      self.load_plugins(root, PROJECT_COMPONENTS)
  ```
- [ ] **Step 4: Verify green and compatibility.** Run focused suites plus `test_plugin_contracts.py` and minimal fixture experiment. Check `agent-opt datasets list` from the installed CLI and `git diff --check`.
- [ ] **Step 5: Commit task changes.** `git add` only Task 1 paths, then `git commit -m "Register team integrations centrally in Python"`.

### Task 2: Read-only dataset and experiment readiness

**Files:** Create `src/agent_optimizer/readiness.py`; modify `src/agent_optimizer/{contracts,cli,runner}.py`, `examples/benchmarks/{cvdp,verilog_eval}.py`; add/update `tests/{test_catalog,test_cli_experience,test_datasets,test_dev_doctor}.py`.

**Interfaces:** `collect_dataset(root: Path, dataset_id: str, registry: Registry) -> dict` and `collect_plan(path: Path, registry: Registry, *, model: bool=False) -> dict` return `{"scope": "dataset"|"plan", "ready": bool, "checks": [{"id": str,"area":str,"status":"ok"|"error"|"blocked","message":str,"remedy":str}]}`. Provider `doctor(cache: Path) -> list[dict]` performs read-only local pin/manifest/tool/image probes and returns component checks. `agent-opt doctor --dataset ID [--json]`, `agent-opt doctor --plan PATH [--json] [--model]` use these functions; no-argument `agent-opt doctor` retains existing binary list for compatibility. `--model` is the only actual model API probe.

- [ ] **Step 1: Write red tests.** Unprepared dataset and missing model credentials produce nonzero `ready=false` with named remedial checks and exactly one JSON object. Register a temporary team dataset provider whose `doctor()` reads a prepared local fixture; monkeypatch every download/build/write API to raise, then verify `doctor --dataset` and `doctor --plan` do not call them or mutate directory fingerprints. Task 3 owns the concrete CVDP/v12 image/hash mismatch tests. For a fixture plan, validate Agent argv/editable/prompt source, registered harness/optimizer/evaluator, dataset, model configuration and budget; no Agent trial. Explicit `--model` alone may call the existing model probe.
  ```python
  report = collect_plan(plan_path, Registry())
  self.assertFalse(report["ready"])
  self.assertIn("model.configuration", {row["id"] for row in report["checks"]})
  self.assertEqual(before_files, after_files)
  ```
- [ ] **Step 2: Observe red.** Run `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -v` and `-p test_datasets.py -v`.
- [ ] **Step 3: Implement shared checks and CLI.** Read `load_experiment` inputs without creating run directories, use validated central registry identities, `ModelSettings.from_env()` only to check configuration presence, and provider `doctor()` to inspect cached local assets without acquisition. Disable interpreter bytecode writes during doctor plugin imports. For plan checks, report invalid schema as a structured failure instead of losing other independent checks; never treat missing evaluator or model as a passing baseline. Reuse `readiness.py` from developer doctor in Task 4; Task 3 fills in each benchmark's detailed checks.
  ```python
  def check(identifier: str, area: str, ok: bool, message: str, remedy: str) -> dict:
      return {"id": identifier, "area": area, "status": "ok" if ok else "error",
              "message": message, "remedy": "" if ok else remedy}
  ```
- [ ] **Step 4: Verify green.** Run focused suites, `test_run_lifecycle.py`, `make doctor ARGS="--core --json"` and `git diff --check`; assert JSON contains no credential values.
- [ ] **Step 5: Commit task changes.** Stage only Task 2 paths; `git commit -m "Share read-only dataset and experiment readiness checks"`.

### Task 3: CVDP evaluation-only preparation and provider checks

**Files:** Modify `examples/ace-rtl/environment/{setup,diagnostics}.py` (diagnostics only if needed for reuse), `examples/benchmarks/{cvdp,verilog_eval}.py`; update `tests/{test_datasets,test_dev_environment,test_dev_doctor,test_verilog_live}.py`.

**Interfaces:** `prepare_evaluation_environment(*, offline: bool=False, platform: str|None=None) -> tuple[Path,dict]` in `examples/ace-rtl/environment/setup.py` reuses existing pinned CVDP/HF download, Python 3.12 driver and official evaluation image; writes a separate dataset-evaluation lock under the provider cache, never the ACE full lock. Existing `prepare_environment` keeps the full ACE Agent image path and full lock untouched. `examples/benchmarks/cvdp.py:Provider.prepare` calls evaluation-only helper, `Provider.doctor(cache)` compares pinned data/driver/image lock. Verilog providers' `doctor(cache)` checks pinned checkout + imported tasks + prepared image identity and v12 runtime without downloads.

- [ ] **Step 1: Write red tests.** Patch only external Git/HF/uv/Docker commands, call the CVDP provider and assert no OpenCode Agent-image `docker build`/image-inspect and no ACE full lock replacement; call old `prepare_environment` and assert it still prepares both images. After a verified cache setup, call both providers' doctors offline and verify existing file digests/mtimes unchanged, then mutate one hash/image ID and expect `ready=false` with a concrete repair. Preserve private Verilog refs outside task files.
  ```python
  result = Provider().prepare(cache, offline=True)
  self.assertIn("evaluation", result["provenance"])
  self.assertNotIn("agent_image", result["provenance"])
  self.assertEqual(before_full_lock, full_lock.read_bytes())
  ```
- [ ] **Step 2: Observe red.** Run `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_datasets.py -v` and `-p test_dev_environment.py -v`.
- [ ] **Step 3: Implement evaluation-only path.** Extract shared existing CVDP steps without duplicating SHA/locks or changing full ACE behavior; use a separate provider cache/lock and only the official evaluation Docker image. Validate simulator source SHA/tool version/cache identity before marking ready. Verilog doctor checks v12 image ID/checkout and private test/ref completeness by read-only probes; unavailable tools yield `error`, never an unverified success.
  ```python
  # Full ACE keeps its existing Agent image; selected CVDP does not request it.
  dataset, evaluation_lock = prepare_evaluation_environment(offline=offline)
  return {"benchmark": str(import_public_tasks(dataset)),
          "evaluator": "cvdp", "provenance": {"evaluation": evaluation_lock}}
  ```
- [ ] **Step 4: Verify green and real tool evidence.** Run focused tests, `AGENT_OPT_TEST_VERILOG_EVAL_ROOT=external/verilog-eval/source/c498220d0a52248f8e3fdffe279075215bde2da6 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_verilog_live.py -v` when cached, and real selected CVDP setup/doctor plus `make smoke` if Docker assets available. Distinguish mocked checks from real tools.
- [ ] **Step 5: Commit task changes.** Stage only Task 3 paths; `git commit -m "Prepare CVDP evaluation assets without ACE Agent image"`.

### Task 4: Existing setup/doctor/bootstrap/menu integration

**Files:** Modify `scripts/{bootstrap.sh,dev.py,dev_doctor.py,menu.py}` (and `Makefile` only if its ARGS forwarding needs changes); update `tests/{test_dev_onboarding,test_dev_doctor,test_menu}.py`.

**Interfaces:** `make setup ARGS="--dataset verilog-spec"`, `make setup ARGS="--dataset cvdp --offline"`, and `make doctor ARGS="--dataset verilog-spec --json"` accept exact registered IDs, reject `--core` mixed with `--dataset`, and leave no-argument ACE/core semantics intact. `scripts/dev.py setup --dataset` calls `Registry.load_project` and the selected provider's `prepare`, then shared `readiness.collect_dataset` before reporting success; `scripts/dev_doctor.py` combines existing network/core checks with the same dataset checks under the `dataset` area. Menu adds a general Agent TUI item that executes `.venv/bin/agent-opt tui` without changing ACE item behavior.

- [ ] **Step 1: Write red tests.** Exercise Make/bootstrap/developer Python entrypoints with fake selected provider and bounded subprocesses: setup selects provider after core sync, does not require ACE Compose or build unrelated images; doctor --dataset --json produces one secret-free document and does not write, --core/--dataset conflicts before installer; unknown ID fails with advice. Menu routes the new number to `.venv/bin/agent-opt tui`, keeps existing 1-7/0 semantics and propagates errors.
  ```python
  proc = subprocess.run(["sh", "scripts/bootstrap.sh", "doctor", "--dataset", "verilog-spec", "--json"],
                        capture_output=True, text=True, timeout=30, cwd=root)
  self.assertEqual(json.loads(proc.stdout)["scope"], "dataset")
  self.assertNotIn("setup-logs", created_paths)
  ```
- [ ] **Step 2: Observe red.** Run `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_dev_onboarding.py -v`, `-p test_dev_doctor.py -v`, `-p test_menu.py -v`.
- [ ] **Step 3: Implement argparse/Bootstrap dispatch.** POSIX parser handles `--dataset ID` and `--dataset=ID`, validates identifiers and conflicts before installers, and defers Docker/Compose requirements until the selected provider's setup. Python dev commands reuse `readiness` and central Registry; menu TUI entry keeps no work on startup and handles missing venv/TTY and child failure. `--core` and no-argument full ACE remain unchanged.
  ```sh
  dataset=
  want_dataset=false
  case "$command:$option" in
      setup:--dataset|doctor:--dataset) want_dataset=true ;;
      setup:--dataset=*|doctor:--dataset=*) dataset=${option#*=} ;;
  esac
  # Consume the next argument when want_dataset=true; reject missing/invalid names.
  [ "$core" = false ] || [ -z "$dataset" ] || fail '--core cannot be combined with --dataset'
  ```
- [ ] **Step 4: Verify green.** Run three focused suites, `make setup ARGS="--core"`, `make doctor ARGS="--core --json"`, selected `make doctor ARGS="--dataset verilog-spec --json"`, `make lint`, and `git diff --check`.
- [ ] **Step 5: Commit task changes.** Stage only Task 4 paths; `git commit -m "Connect dataset readiness to developer setup and menu"`.

### Task 5: Documentation, full verification, and PR evidence

**Files:** Update `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `experiments/README.md`, `experiments/dataset-template/{README.md,provider.py}`, `docs/{CONTEXT,status,NEXT_STEPS,FUTURE,architecture,adding-components,development,SOURCES,verification}.md` and the amended spec/plan if implementation diverges. Update relevant tests only if docs expose a real broken command.

**Interfaces:** Team onboarding instructs implementation + central registry edit; end users choose a dataset and use either `agent-opt doctor --plan` or `make doctor ARGS="--dataset ID --json"`, then TUI or CLI run. Docs label v12/CVDP fixture verification distinctly from real model runs and record actual commands, dates and results. Existing PR #12 receives commits after final review and full CI checks; user already authorized merging the PR after completion.

- [ ] **Step 1: Review all stale paths.** Search docs for `extensions.toml`, `--extensions`, claims that `doctor` only lists binaries, and default full ACE readiness being incorrectly equated to selected dataset readiness. Amend only present-tense guidance, retain dated verification evidence verbatim as historical records.
  ```bash
  git grep -n -E 'extensions\.toml|--extensions|doctor' -- README.md AGENTS.md CONTRIBUTING.md docs experiments
  ```
- [ ] **Step 2: Write and check copyable paths.** Update team template and four user commands, then run their `--help`, `datasets list`, dataset doctor and plan doctor from the prepared checkout. Record Docker/Model missing states rather than marking them ready.
  ```bash
  .venv/bin/agent-opt datasets list
  .venv/bin/agent-opt doctor --plan examples/minimal/experiment.toml --json
  make doctor ARGS="--dataset verilog-spec --json"
  ```
- [ ] **Step 3: Run final verification.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_plugin_contracts.py -v`; `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`; `PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml`; `make lint`; `make smoke` if evaluation assets exist; `.venv/bin/python -m build`; `git diff --check`. Record exact passes/skips/blocked environment in `docs/verification.md`.
- [ ] **Step 4: Commit docs and evidence.** Stage intended documentation paths, inspect status/diff/log, `git commit -m "Document code registration and selected dataset readiness"`.
- [ ] **Step 5: PR publishing is a controller action after task/final reviews.** Inspect all commits `origin/main..HEAD`, push to the existing PR #12 branch, wait for Python 3.11/3.12 CI, review final PR diff, and merge only if required checks pass and no load-bearing review finding remains. Do not let the implementer push or merge.
