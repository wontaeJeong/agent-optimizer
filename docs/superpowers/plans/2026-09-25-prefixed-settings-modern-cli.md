# Prefixed Settings and Modern CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give project-owned environment settings an `AGENT_OPT_` prefix, use Pydantic Settings for model input, Typer for public CLI parsing, and Rich for interactive progress.

**Architecture:** Keep `ModelSettings.from_env(env=None) -> ModelSettings` and its validated public fields as the sole model settings entry point. Move only `agent-opt` parsing into Typer; dispatch to the current experiment/registry/doctor logic. Rich owns TTY rendering, while existing event summaries continue on non-TTY stderr and JSON remains on stdout.

**Tech Stack:** Python >=3.11, `pydantic-settings` (Pydantic v2), Typer, Rich, uv frozen lock, unittest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-25-prefixed-settings-modern-cli-design.md`

## Global Constraints

- Project-owned names become `AGENT_OPT_MODEL_ENDPOINT`, `AGENT_OPT_MODEL_BASE_URL`, `AGENT_OPT_MODEL_ID`, `AGENT_OPT_MODEL_API_KEY`, `AGENT_OPT_CVDP_PYTHON`; old `MODEL_*`/`CVDP_PYTHON` inputs stop working immediately.
- External names `OSS_SIM_IMAGE`, `OPENCODE_CONFIG`, `OPENROUTER_API_KEY`, proxy/TLS/`DOCKER_DEFAULT_PLATFORM`/`UV_*`/`PATH`/`PYTHONPATH` remain their existing interfaces.
- Do not load `.env` automatically, expose keys in diagnostics/representations, alter score or dataset/source pins, or place credentials in experiment artifacts.
- Keep `scripts/dev.py`/bootstrap standard-library compatible before package installation; keep read-only doctor and JSON stdout behavior.
- The canonical Agent command input for `agent-opt init` is `--command-json` (JSON argv array); remove `--argv`.
- Do not modify archived verification evidence to imply prior runs used these changes.

## File map

- `pyproject.toml`, `uv.lock`: new runtime dependencies and their frozen compatible lock.
- `src/agent_optimizer/models.py`: one settings source and existing validated model transport, redacted request boundary.
- `src/agent_optimizer/cli.py`: Typer public command definitions and dispatch; keep business rules here rather than introducing parallel registries.
- `src/agent_optimizer/terminal_report.py`: Rich interactive stderr displays and stable plain non-TTY lines.
- `src/agent_optimizer/readiness.py`, `scripts/menu.py`, `examples/ace-rtl/environment/{diagnostics.py,setup.py,model_checks.py}`, `examples/ace-rtl/evaluator.py`, `scripts/dev.py`: explicit environment consumers/producers.
- `examples/ace-rtl/harness.toml`, `examples/ace-rtl/environment/openai-compatible.json`, `examples/rtl-debugger/{harness.toml,compatible.json,endpoint-plugin.mjs}`: environment passthrough and provider template consumers.
- `.env.example`, `README.md`, `docs/development.md`, `experiments/simple-feedback/README.md`, `examples/{ace-rtl,rtl-debugger}/README.md`, `docs/SOURCES.md`: active user instructions and library documentation mapping.
- `tests/test_models.py`, `tests/test_cli_experience.py`, `tests/test_progress.py`, `tests/test_menu.py`, `tests/test_dev_environment.py`, `tests/test_demo_environment.py`, `tests/test_network.py` and any other existing fixtures matching old variable names: focused regressions plus mechanical updates where the name is the test's input.

### Task 1: Lock packages and prefix the model input

**Files:** Modify `pyproject.toml`, `uv.lock`, `src/agent_optimizer/models.py`, `tests/test_models.py`.

**Interfaces:** Retain `ModelSettings.from_env(env=None) -> ModelSettings`, `.endpoint`, `.model`, `.api_key`, and the worker's `{"settings": {...}}` payload shape. Subsequent tasks use these fields and the new `AGENT_OPT_MODEL_*` names.

- [ ] **Step 1: Write failing model tests.** Change model tests to use `AGENT_OPT_MODEL_ENDPOINT`, `AGENT_OPT_MODEL_BASE_URL`, `AGENT_OPT_MODEL_ID`, `AGENT_OPT_MODEL_API_KEY`. Add explicit-mapping isolation, old-name rejection, and key redaction assertions:

```python
def test_prefixed_only_and_explicit_mapping_isolation(self):
    new = {"AGENT_OPT_MODEL_ENDPOINT": "https://example.invalid/v1/chat/completions",
           "AGENT_OPT_MODEL_API_KEY": "fixture-secret"}
    with patch.dict(os.environ, {"MODEL_ENDPOINT": new["AGENT_OPT_MODEL_ENDPOINT"],
                                 "MODEL_API_KEY": "old-secret"}, clear=True):
        with self.assertRaises((ConfigurationError, UnavailableError)):
            ModelSettings.from_env()
        settings = ModelSettings.from_env(new)
        self.assertEqual(settings.model, "glm5.3-flash")
        self.assertNotIn("fixture-secret", repr(settings))
        with self.assertRaises((ConfigurationError, UnavailableError)):
            ModelSettings.from_env({"MODEL_ENDPOINT": new["AGENT_OPT_MODEL_ENDPOINT"],
                                    "MODEL_API_KEY": "old-secret"})
```

- [ ] **Step 2: Run focused red.** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_models.py -v` should fail for the new names.
- [ ] **Step 3: Add dependency declarations and refresh lock.** Set `dependencies = ["pydantic-settings>=2,<3", "typer>=0.16,<1", "rich>=14,<15"]` in `pyproject.toml`; run `uv lock` then `uv sync --frozen --python 3.12 --extra dev` in this worktree (verify actual resolved releases support Python 3.11 and frozen setup). If a dependency's current stable release exceeds the named bound, change the bound to include the compatible stable major and re-lock rather than claiming a stale pin is latest.
- [ ] **Step 4: Implement settings without changing callers.** Inside `ModelSettings.from_env` lazily import `pydantic_settings` (the pre-install developer help/doctor path imports `models.py` indirectly through `registry.py`); use a private `BaseSettings` model for `endpoint`, `base_url`, `id`, `api_key` with `SettingsConfigDict(env_prefix="AGENT_OPT_MODEL_", env_file=None)`. For an explicit `env` mapping initialize *every* field from that mapping to block ambient fallback. Keep the current URL and whitespace checks and return the existing redacted `ModelSettings` dataclass. Convert/contain missing dependency and Pydantic validation errors without printing the credential; a model-specific check can report unavailable before setup, while core help/doctor still starts. Keep `asdict(settings)` only in the worker payload, never in a diagnostic. Add a direct test for endpoint/base exclusivity and a request to the local HTTP fixture.
- [ ] **Step 5: Run focused green.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_models.py -v` must pass, including the timeout/HTTP and secret-redaction cases.
- [ ] **Step 6: Commit.** Inspect status/diff/log, stage only these four files, commit `Use prefixed Pydantic model settings`.

### Task 2: Propagate project-owned names through diagnostics and examples

**Files:** Modify `src/agent_optimizer/readiness.py`, `scripts/menu.py`, `scripts/dev.py`, `examples/ace-rtl/{evaluator.py,harness.toml,README.md}`, `examples/ace-rtl/environment/{diagnostics.py,setup.py,model_checks.py,openai-compatible.json}`, `examples/rtl-debugger/{harness.toml,compatible.json,endpoint-plugin.mjs,README.md}`, `tests/test_menu.py`, `tests/test_dev_environment.py`, `tests/test_demo_environment.py`, `tests/test_network.py`, `tests/test_cli_experience.py` plus any remaining active consumer/fixture identified by a full literal search.

**Interfaces:** Consume `ModelSettings.from_env` from Task 1. `AGENT_OPT_MODEL` remains the OpenCode selector, `OSS_SIM_IMAGE` remains the verified upstream driver input. Environment lists refer to the new prefixed names.

- [ ] **Step 1: Add red cross-boundary tests.** In `test_cli_experience.py`, configure a research plan using only prefixed names and assert `model.configuration` is `ok`, then configure *only* old names and assert it is `error`; assert JSON has no key value. In `test_menu.py`, add a staged menu configuration check that its child environment has `AGENT_OPT_MODEL_API_KEY` and no `MODEL_API_KEY`. In `test_dev_environment.py`, check `validate_live` sets the prefixed model ID and passes the configured selector; retain `OSS_SIM_IMAGE` in the evaluator driver tests.

```python
with patch.dict(os.environ, {"MODEL_ENDPOINT": "https://example.invalid/v1/chat/completions",
                             "MODEL_API_KEY": "legacy-secret"}, clear=True):
    result = collect_plan(research_plan, Registry())
    self.assertEqual(next(r["status"] for r in result["checks"]
                          if r["id"] == "model.configuration"), "error")
    self.assertNotIn("legacy-secret", json.dumps(result))
```

- [ ] **Step 2: Run red.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -v` and the new menu/dev cases should fail on old consumers.
- [ ] **Step 3: Update active consumers and fixtures.** Rename only project-owned environment names in Python, TOML, JS, JSON, and test fixtures. Update `readiness.py` remedies, `scripts/menu.py`'s session keys, `setup.validate_live`'s exported ID, provider `env_passthrough`, OpenCode placeholders, and the example evaluator's Python override. Keep the external `OSS_SIM_IMAGE` export to the pinned driver, and do not add model secrets to evaluator passthrough. Use a full project search for `MODEL_ENDPOINT|MODEL_BASE_URL|MODEL_ID|MODEL_API_KEY|CVDP_PYTHON`; expected remaining unprefixed occurrences are only historical docs, literal negative tests, and explicit migration explanation.
- [ ] **Step 4: Run scoped green.** Run `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_menu.py -v`, `test_cli_experience.py`, `test_dev_environment.py`, `test_demo_environment.py`, and `test_network.py`. Diagnose any failure before changing the contract.
- [ ] **Step 5: Commit.** Review status/diff/log, stage only related consumers and tests, commit `Propagate prefixed model settings to examples and diagnostics`.

### Task 3: Migrate the public CLI parser to Typer

**Files:** Modify `src/agent_optimizer/cli.py`, `tests/test_cli_experience.py`, `tests/test_progress.py`, `README.md`, `docs/development.md`, `docs/adding-components.md`, `src/agent_optimizer/setup_wizard.py` only if its generated argv changes.

**Interfaces:** Preserve `main(argv: list[str] | None = None) -> int` for `scripts/agent-opt`, `__main__`, tests, and TUI recursion. Preserve `show(value) -> None`, `doctor() -> dict`, `_dispatch(args) -> int` (move current branch logic here), and `Registry` resolution; canonical input `--command-json` becomes `list[str]` only after validation. Existing nonzero results remain 2 for invalid configuration/readiness, 3 for incomplete runs, 130 on interruption.

- [ ] **Step 1: Write failing parser tests.** Add a valid `init --command-json '["python", "agent.py", "--input", "{task_dir}"]'` run against the fixture project; assert generated harness `command` equals that exact list. Assert `--argv` is rejected without preparing a dataset; repeated `--dataset`, `--editable`, `--optimizer` still work; `doctor --plan examples/minimal/experiment.toml --json` emits one JSON document and stays read-only; invalid options exit 2 and print to stderr. Test `main(["--help"])` and nested `main(["datasets", "--help"])` without invoking plugins or mutating paths.

- [ ] **Step 2: Run red.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -v`; the removed `--argv` test should currently fail.
- [ ] **Step 3: Replace parser only.** Keep one `typer.Typer` app and a nested `datasets` app; register `plugins`, `doctor`, `datasets list/prepare`, `init`, `tui`, `run-session`, `agents`, `validate`, `plan`, `run`, `report` with typed `Path`, `str`, `bool`, `int`, `float`, `list[str]` arguments/options. Convert command parameters to `types.SimpleNamespace` or an equivalent existing request passed to `_dispatch(args)`; do not copy business rules into callback bodies. Use Typer/Click's non-standalone programmatic invocation to keep `main(argv)`'s integer return:

```python
from types import SimpleNamespace
import click
import typer

app = typer.Typer(no_args_is_help=True)
dataset_app = typer.Typer()
app.add_typer(dataset_app, name="datasets")

def _invoke(command: str, **kwargs) -> int:
    return _dispatch(SimpleNamespace(command=command, **kwargs))

def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    previous = sys.dont_write_bytecode
    if argv and argv[0] == "doctor":
        sys.dont_write_bytecode = True
    try:
        return typer.main.get_command(app).main(args=argv, prog_name="agent-opt",
                                                 standalone_mode=False) or 0
    except click.ClickException as exc:
        exc.show(file=sys.stderr)
        return exc.exit_code
    except click.exceptions.Exit as exc:
        return exc.exit_code
    finally:
        sys.dont_write_bytecode = previous
```

For instance, register the run callback as:

```python
@app.command("run")
def run_command(experiment: Path, output: Path | None = typer.Option(None, "--output")) -> int:
    return _invoke("run", experiment=experiment, output=output)
```

For `init`, use `command_json: str | None = typer.Option(None, "--command-json")`, `dataset: list[str] = typer.Option([])`, `editable: list[str] = typer.Option([])`, `optimizer: list[str] = typer.Option([])`; mirror the current numeric defaults, `--yes`, paths, `--agent`, `--revision`, `--prompt-file`, `--evaluator`, `--metric`, `--direction`, `--harness`, `--optimizer-config`, `--scaffold-file`, and `--target-file`. Build `SimpleNamespace` with attributes the existing branch reads, including `command_json` and without `argv`, and change that branch to parse only `command_json` before `prepare_selection`. `doctor` must populate `dataset`, `plan`, `project_root`, `json`, and `model`; other callbacks populate their branch's attributes. Treat `rerank` as an explicit deferred error. Verify exceptions from Typer parsing never masquerade as successful exits, and keep `doctor`'s bytecode guard before project loading.
- [ ] **Step 4: Update help/examples.** In active docs and setup wizard, use `--command-json` with a complete JSON string instead of multi-token `--argv`, including dash-prefixed child arguments. Keep `scripts/dev.py`/bootstrap and the packaging script-file entry point unchanged.
- [ ] **Step 5: Run green and smoke.** Run `test_cli_experience.py`, `test_progress.py`, `test_plugin_contracts.py`, `test_dev_onboarding.py` and `PYTHONPATH=src .venv/bin/python -m agent_optimizer --help`; compare exit/output of selected `init`, `doctor`, `plan`, `datasets list`, `run`, `report` commands with expected fixtures. In particular confirm TUI recursion captures only JSON stdout.
- [ ] **Step 6: Commit.** Review status/diff/log; commit `Migrate public CLI parsing to Typer` with the parser, tests, and associated help edits.

### Task 4: Render interactive progress with Rich

**Files:** Modify `src/agent_optimizer/terminal_report.py`, `tests/test_progress.py`, `tests/test_dev_onboarding.py` if they assert preparation output.

**Interfaces:** Retain `ProgressDisplay(stream=None).configure_budget(max_trials)`, `.start()`, `.__call__(event)`, context-manager protocol, and `PreparationStatus(name, stream=None)`; callers need no changes. Stderr stays the default stream.

- [ ] **Step 1: Write red TTY/non-TTY checks.** Use `io.StringIO` for non-TTY, plus a small test stream overriding `isatty()` to return True. Assert non-TTY lines still carry iteration, used/remaining budget, and descending slow-task durations with no escape codes; TTY path instantiates a Rich `Console(file=stream)`/`Live`, emits event status, and tears it down on both normal/error exit. Capture `stdout` separately and assert progress never appends to a JSON value.

```python
class TtyBuffer(io.StringIO):
    def isatty(self):
        return True

def test_progress_uses_rich_only_for_tty(self):
    out = TtyBuffer()
    with ProgressDisplay(stream=out) as progress:
        progress.configure_budget(4)
        progress({"event": "trial_completed", "timestamp": "2026-09-24T10:00:00Z",
                  "task_id": "slow", "metrics": {"task_wall_time_seconds": 5.0}})
    self.assertIn("slow", out.getvalue())
```

- [ ] **Step 2: Run red.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_progress.py -v`; require a Rich-specific assertion (e.g. patched `Live` calls) to fail before implementation, rather than a pre-existing plain-text assertion.
- [ ] **Step 3: Replace custom ANSI thread rendering.** Use Rich `Console(file=self.stream, stderr=True, force_terminal=self.tty)` and `Live` or `Progress` only when `isatty()` is true; call `.update()` from the same event data under the existing lock and close the display in `__exit__` even on error. Preserve the current plain non-TTY summary and `PreparationStatus` completion/failure messages; do not print markup or escape codes in redirected stderr.
- [ ] **Step 4: Run green.** Run `test_progress.py`, `test_cli_experience.py`, `test_dev_onboarding.py`; confirm `PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml` produces one JSON result on stdout and only progress on stderr.
- [ ] **Step 5: Commit.** Review status/diff/log, stage terminal and its tests, commit `Use Rich for interactive progress rendering`.

### Task 5: Refresh active guidance and verify the frozen project

**Files:** Modify `.env.example`, `README.md`, `docs/development.md`, `experiments/simple-feedback/README.md`, `examples/{ace-rtl,rtl-debugger}/README.md`, `docs/SOURCES.md`, any remaining active fixture files from Task 2. Do not alter `docs/verification.md` historical commands/results.

**Interfaces:** Document the exact new settings, credential-only environment handling, canonical `--command-json`, and `uv.lock`-based setup; do not claim a real model call or pinned evaluation occurred.

- [ ] **Step 1: Update and audit active instructions.** Replace live `MODEL_*` exports and `--argv` snippets, document the no-alias breaking change, update the documented external/package sources in `docs/SOURCES.md` with official Pydantic Settings/Typer/Rich docs and their consuming files. Search active code/config/readmes for old names; allow old names only in literal rejection tests and historical docs. Check `git diff` for secrets and upstream-pinned hashes.
- [ ] **Step 2: Verify locked setup.** Run `uv sync --frozen --python 3.12 --extra dev`, `make doctor ARGS="--core"`, `make lint`, `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`, `PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml`, and `.venv/bin/python -m build`. Keep synthetic fixture success distinct from external integration validation.
- [ ] **Step 3: Final checks.** Run `git diff --check`; inspect `git status --short --branch`, `git diff`, `git log --oneline -10`, and the base worktree's `git status --short --branch`/`git worktree list`. Fix only issues found by checks and rerun affected checks.
- [ ] **Step 4: Commit.** Stage only active docs and necessary final fixes, commit `Document prefixed configuration and modern CLI setup`.
- [ ] **Step 5: Delivery.** Fetch/compare against `origin/main` as needed, push the work branch and open a PR with `gh`, include actual verification results and PR URL. Ask for explicit merge approval; do not merge as part of PR creation.
