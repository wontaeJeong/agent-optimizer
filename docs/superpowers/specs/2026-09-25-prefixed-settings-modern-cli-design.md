# Prefixed settings and modern CLI design

## Goal and decisions

Use one `AGENT_OPT_` namespace for project-owned environment variables, and adopt
Pydantic Settings, Typer, and Rich where they simplify existing settings, public
CLI parsing, and terminal progress. The previous unprefixed `MODEL_*` variables
stop working immediately; there is no alias, fallback, or deprecation period.
The user permits a change to the `agent-opt init` argv syntax.

## Environment boundary

`MODEL_ENDPOINT`, `MODEL_BASE_URL`, `MODEL_ID`, and `MODEL_API_KEY` become
`AGENT_OPT_MODEL_ENDPOINT`, `AGENT_OPT_MODEL_BASE_URL`, `AGENT_OPT_MODEL_ID`, and
`AGENT_OPT_MODEL_API_KEY`. `AGENT_OPT_MODEL` remains the OpenCode model selector;
`AGENT_OPT_CA_BUNDLE` remains the optional project CA setting. The example-only
`CVDP_PYTHON` override becomes `AGENT_OPT_CVDP_PYTHON`. Update each consumer,
diagnostic, session menu, example config, declared container passthrough, test
fixture, `.env.example`, and active usage documentation together. Do not rewrite
historical verification records as though they used the new names.

Environment names dictated by external programs stay intact. In particular,
`OSS_SIM_IMAGE` is the pinned CVDP driver's Dockerfile/Compose interface;
`OPENCODE_CONFIG` and `OPENROUTER_API_KEY` are provider interfaces; proxy,
TLS, `DOCKER_DEFAULT_PLATFORM`, `UV_*`, `PATH`, and `PYTHONPATH` remain external
interfaces. Pass these through only in their existing explicit contexts; do not
introduce automatic credential copying into experiment reports or agent files.

## Settings and runtime configuration

Use Pydantic Settings for the model environment input, with explicit prefixed
names and no automatic `.env` loading. Preserve the existing endpoint/base-URL
exclusive choice, HTTPS/loopback-only HTTP validation, model ID checks, missing
credential failure, and redaction of the API key in repr, diagnostics, errors,
and report output. Callers that pass an explicit environment mapping (menu,
tests, doctor) must validate that mapping rather than accidentally falling back
to process environment. The short-lived request worker receives the same
validated endpoint/model/key and retains its total timeout and `shell=False`.
The bootstrap/developer diagnostic path imports model modules before installation;
load the Pydantic dependency only when model settings are actually validated.
Without the package, a model-specific check reports an unavailable dependency
instead of preventing the core help/doctor commands from starting.
Keep existing TOML/JSON experiment contracts and source/evaluator isolation;
do not convert the full schema to Pydantic in this change.

## CLI and terminal flow

Replace `agent-opt`'s argparse command parsing with Typer while reusing the
existing registry, preparation, validation, runner, report, and doctor logic.
Retain command names, JSON output shapes, meaningful nonzero exit statuses,
read-only doctor behavior, and the TUI's use of the same `init` path. For `init`,
use the existing `--command-json '["python", "agent.py", "--input", "{task_dir}"]'`
as the canonical argv-array input; remove the ambiguous `--argv` multi-token
form and update active examples. The bootstrap and `scripts/dev.py` remain
standard-library entry points so setup/help/doctor work before packages are
installed. Team component discovery remains registry-driven, never encoded in
CLI option choices or installation entry points.

Use Rich for interactive stderr progress/preparation displays, retaining the
event-driven information (dataset, stage, task, phase, iteration, elapsed,
trial budget, slowest tasks). Keep non-TTY progress stable and readable without
control sequences; JSON stdout remains a single machine-readable document.
No global output replacement is needed for plain diagnostic JSON or saved
reports. Detect TTY per display, and do not let a display failure turn an
experiment error into success.

## Dependencies and verification

Add the chosen supported releases of `pydantic-settings`, `typer`, and `rich`
to runtime dependencies and refresh the project `uv.lock` for frozen installs.
Keep Python >=3.11 support and the existing core setup/offline path. Do not
change pinned benchmark source, CVDP driver dependencies, Docker images,
model provider versions, or scoring rules as a side effect of this update.

Add focused tests for prefixed-only settings and precedence, secret redaction,
diagnostic/menu/container propagation, Typer command parsing and exit codes,
canonical JSON argv, read-only doctor, and stderr/JSON separation in TTY and
non-TTY output. Update existing tests that intentionally use old variable
names. Run relevant targeted tests, the full unittest suite, Ruff, the minimal
API-free demo, frozen package/build checks, and review the diff for accidental
credential or historical-record changes. Real provider calls and benchmark
scoring are outside this refactor's verification claim.
