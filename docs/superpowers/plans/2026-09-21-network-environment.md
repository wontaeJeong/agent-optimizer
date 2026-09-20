# Optional Network Environment Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Carry optional proxies, NO_PROXY and a verified CA bundle through supported setup and execution paths.

**Architecture:** One flat network helper translates environment settings at host/build/container boundaries. Example-local Compose adaptation stays outside the product core.

**Tech Stack:** Python standard library, Docker BuildKit/Compose, existing driver PyYAML.

**Spec:** `docs/superpowers/specs/2026-09-21-network-environment-design.md`

## Global Constraints

- Python >=3.11; no new core dependencies; keep upstream SHAs and scoring unchanged.
- Run argv with shell=False; credentials belong in environment, never tracked files.
- AGENT_OPT_CA_BUNDLE is a complete PEM trust bundle; keep TLS verification enabled.
- Absent configuration preserves current behavior; explicit empty proxies are retained.

### Task 1: Host and container contract

Files: create `src/agent_optimizer/network.py`, `tests/test_network.py`; modify
`process.py`, `sources.py`.

Interfaces: `host_environment(env=None) -> dict`, `network_environment(env=None) -> dict`,
`ca_bundle(env=None) -> Path | None`, `container_network(env=None) -> tuple[list[str], dict]`.

- [x] Add failing cases for precedence, empty values, invalid PEM, and runtime CA translation.
  Assert `network_environment({'http_proxy': '', 'HTTP_PROXY': 'ignored'})['HTTP_PROXY'] == ''`.
  Patch `process.run_process`; assert proxy credentials never appear in Docker argv,
  CA mounts are readonly, and the Docker client's env carries the actual proxy.
- [x] Run `PYTHONPATH=src python3 -m unittest discover -s tests -p test_network.py -v`.
- [x] Implement helpers and wire local/Docker execute and Git source subprocesses.
- [x] Repeat focused tests; add actual local HTTPS trust and proxy/NO_PROXY requests.

### Task 2: Build and bootstrap paths

Files: network helper, `scripts/network.py`, ACE `environment/setup.py`, focused tests.

Interface: `configured_build(argv, cwd, env=None)` context manager yields Docker argv.

- [x] Test that the temporary Dockerfile installs trust before the first RUN, the
  source Dockerfile remains byte-identical, the added context contains only the CA,
  proxy args contain names only, and temporary files are removed after failures.
- [x] Run focused tests for RED, implement BuildKit context adaptation and wrapper.
- [x] Apply host environment to setup commands and explicit TLS context to downloads;
  record `ca_bundle_sha256` and compare it before offline reuse.
- [x] Run network and setup regressions; verify no upstream/version changes.

### Task 3: Private evaluator propagation

Files: create ACE `environment/network_driver.py`; modify `evaluator.py`; focused tests.

Interface: driver `configure_submission(path, environment)` updates only the private
submission Compose configuration using PyYAML; main runs the pinned driver via runpy.

- [x] Test list/map environments, proxy build args, readonly CA mounts, absence of
  model credentials and proxy values in serialized data, and unchanged checker bytes.
- [x] Verify RED; implement driver and evaluator environment allowlist wiring.
- [x] Verify GREEN including existing evaluator cleanup/error classification tests.

### Task 4: Documentation and verification

Files: `.env.example`, `docs/network.md`, README, SOURCES/status/verification.

- [x] Document bootstrap, normal setup/run, direct build wrapper, CA renewal, offline
  identity checks, remote Docker bind-path requirements, and NO_PROXY tool semantics.
- [x] Run full unittest, minimal CLI, lint, diff checks, and available Docker smoke.
- [x] Review intended diff and record exact results/limits in `docs/verification.md`.

Delivery: commit the reviewed changes, push the work branch, and create the PR;
track delivery status in the session task list and final PR report.
