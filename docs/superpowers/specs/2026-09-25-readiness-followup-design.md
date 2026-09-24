# Readiness follow-up design

## Goal and evidence boundary

Make the existing user configuration path work for structured optimizer settings,
and establish a small, testable configuration path for alternative package and Git
transports and self-hosted CI. Preserve the current CLI/TUI, explicit dataset choice,
common contracts, pinned source commits, dataset hashes, and opt-in network settings.
The current synthetic fixture proves wiring, not real Agent performance. A model
endpoint and its credentials are unavailable in this environment, so an ACE live
run and remote-runner success cannot be reported as verified here.

## User experiment creation

`agent-opt init --optimizer-config` accepts a mapping of optimizer IDs to option
objects, including arrays of nested objects such as `file_variants.variants`. The
writer in `setup_wizard.py` must serialize these values as valid TOML (inline tables
use `=`, strings remain escaped) rather than embedding JSON object syntax in TOML.
Round-trip the generated configuration through the existing `load_experiment`.
If generation or validation fails after creating a new config directory, remove
only that newly owned directory so a corrected command can reuse the name. Never
remove a directory that existed before the call; data preparation caches are
separate from the generated configuration. Cover nested settings, ordinary scalar
settings, malformed configuration, and successful CLI init/doctor/run/report with
the existing synthetic Agent and file-variants optimizer.

## Portable transport and CI

Use existing tool-native configuration instead of adding a mirror manager:
Git URL rewrite (or an explicit pinned Agent URL), uv/pip index environment,
Docker daemon/registry configuration, and the existing optional proxy/full CA
bundle. A rewritten source must still resolve to the pinned commit; downloaded
dataset assets must still match their pinned hashes. Document which fixed example
URLs are public defaults and how to prepare a compatible source/data cache when
the original endpoint is unavailable. Do not change the pinned revisions or make
transport overrides bypass verification. Check a local Git rewrite against a test
repository without credentials, and exercise available network/CA contract tests.

The existing workflows already accept `CI_RUNNER_LABELS` and check native simulator
tools on self-hosted runners. Tighten only concrete readiness gaps found while
reviewing the workflows: describe runner prerequisites, dependency/action access,
proxy/CA and artifact availability as external runner responsibilities; keep the
normal jobs model-free and the official Docker job explicitly opt-in. Locally check
the same commands used by core CI and inspect workflow syntax. Do not present a
local workflow check as a remote CI run.

## Verification and completion

Run regression tests, `make lint`, the full test suite, the synthetic CLI
init/doctor/run/report path, core doctor, and relevant packaging checks. Report
skips and the unavailable external checks explicitly. When an endpoint and its
credentials become available, run the separately documented ACE setup, doctor,
smoke, model probe and small live experiment; compare actual reports rather than
inferring improvement from a fixture. Remote runner results require an actual
workflow run on that runner. Do not store credentials, proxy values, or private
endpoint details in project files or results.
