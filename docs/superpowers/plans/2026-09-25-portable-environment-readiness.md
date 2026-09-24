# Portable Environment Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Demonstrate pinned Git-source redirection without an extra mirror layer and document/test the existing CI and network prerequisites accurately.

**Architecture:** Git already honors `url.*.insteadOf` in its child processes and the project verifies source commits and data hashes; prove this with an offline integration test. Use Git, uv/pip and Docker's native configuration rather than a new transport API, and explicitly distinguish local CI-equivalent evidence from remote workflow runs.

**Tech Stack:** Python 3.11+ stdlib `unittest`, Git, uv, Docker (optional integration), GitHub Actions YAML.

**Spec:** `docs/superpowers/specs/2026-09-25-readiness-followup-design.md`

## Global Constraints

- Keep fixed revisions and hashes intact; alternate transports must not bypass pinned commit/hash verification.
- Proxy and CA are optional; the current complete PEM bundle, uppercase/lowercase proxy and `NO_PROXY` contract remains unchanged.
- Keep the regular CI model-free and the Docker official integration opt-in.
- Do not store credentials, private endpoints or proxy values in project files.
- The current environment has no model endpoint credentials and cannot demonstrate remote runner success.

---

## File map

- `tests/test_integrations.py`: offline Git-rewrite + pinned commit integration case using a temporary local repository.
- `docs/network.md`: concise native transport and alternative cache instructions next to existing network setup.
- `CONTRIBUTING.md`: runnable self-hosted runner prerequisites and exact CI-equivalent checks.
- `.github/workflows/ci.yml`: inspect; edit only if the documented route exposes a concrete broken step.

### Task 1: Prove source redirection retains pinned identity

**Files:**
- Test: `tests/test_integrations.py` (`SourceTests`)
- Modify: `docs/network.md`

**Interfaces:**
- Consumes: `materialize_agent(agent: AgentSpec, target: Path)` in `src/agent_optimizer/sources.py`; existing source `SourceSpec(kind="git", url=..., revision=...)`.
- Produces: offline regression showing Git's environment-scoped URL rewrite fetches a local repository while the source lock retains and checks the requested full commit; a documented example using standard Git configuration and pinned revision.

- [ ] **Step 1: Add a meaningful local Git integration test.** Create a temporary Git repo with `prompts/system.md` and a small editable file, commit with inline `git -c user.name=... -c user.email=... commit`, read the full commit SHA, and form an `AgentSpec` with `SourceSpec(kind="git", url="https://github.com/example/pinned-agent.git", revision=sha)`. Pass Git's process-scoped configuration through `patch.dict(os.environ, {"GIT_CONFIG_COUNT":"1", "GIT_CONFIG_KEY_0":"url.file://<absolute temporary repo path>.insteadOf", "GIT_CONFIG_VALUE_0":"https://github.com/example/pinned-agent.git"})`. Call `materialize_agent` and assert `source-lock.json` has `requested_commit == resolved_commit == sha`, the original public URL is recorded, and the copied file contents are those of the pinned commit. Make a second incompatible revision request and assert failure without accepting the redirected repository's HEAD. Reuse the existing test helper for fixtures and source creation if available.
- [ ] **Step 2: Run only the new test.** Run `PYTHONPATH=src:tests .venv/bin/python -m unittest test_integrations.SourceTests.test_git_url_rewrite_preserves_pinned_source_identity -v`; if already green, the capability exists and the test is acceptance evidence, not a reason to add source-code layers.
- [ ] **Step 3: Add concise guidance to `docs/network.md`.** Show an environment-scoped Git rewrite command shape (`GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=url.<replacement>.insteadOf`, `GIT_CONFIG_VALUE_0=<public-prefix>`), `UV_INDEX_URL`/`PIP_INDEX_URL`, and Docker daemon registry configuration responsibility. State that pinned SHA/hash validation remains mandatory, public default URLs remain in the manifest, and local verified caches can be prepared in advance for offline reuse. Do not put real URLs or credentials in examples.
- [ ] **Step 4: Run focused source and network tests; commit test and guidance.** Run `PYTHONPATH=src:tests .venv/bin/python -m unittest test_integrations.SourceTests test_network.NetworkTests -v`; use a concise commit message, e.g. `Verify pinned source URL redirection`.

### Task 2: Exercise the existing CI contract and report limits

**Files:**
- Modify: `CONTRIBUTING.md:44-63`
- Inspect: `.github/workflows/ci.yml`, `.github/workflows/release.yml`

**Interfaces:**
- Consumes: `CI_RUNNER_LABELS` (JSON label array), existing `make help/lint/test/demo`, pinned uv setup, optional `workflow_dispatch` Docker job and existing network variables.
- Produces: concise instructions and observed local evidence for a self-hosted runner and optional Docker integration, without claiming a workflow ran remotely.

- [ ] **Step 1: Map each existing job to prerequisites.** Verify the current `ci.yml` steps, Python 3.11/3.12, Node 22, `yosys`, `iverilog`, `vvp`, uv/pip, Docker/Compose/Buildx for the optional job, action availability, proxy/CA and artifact behavior. Identify whether a concrete step is broken before editing the workflow.
- [ ] **Step 2: Document the prerequisite contract in `CONTRIBUTING.md`.** Include the `CI_RUNNER_LABELS` JSON example, the tools that must be preinstalled on a self-hosted runner, where proxy/CA and package/Git/image configuration must be supplied, how to trigger the existing optional Docker job, and the distinction between CI result and local command success. Describe the existing artifact upload condition accurately.
- [ ] **Step 3: Run equivalent local checks without asserting remote success.** Run `make help`, `make lint`, `make test`, `make demo`, `.venv/bin/python -m build`, `node --test tests/endpoint-plugin.test.mjs` if Node is available, plus `make doctor ARGS="--core --json"`. Run Docker network integration with `AGENT_OPT_NETWORK_DOCKER=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_network.DockerNetworkIntegrationTests -v` only if Docker daemon and Buildx are usable; report skips or the exact blocker.
- [ ] **Step 4: Inspect tracked changes and commit documentation/any necessary workflow correction.** Example message: `Clarify portable CI runner prerequisites`. State explicitly if no workflow change was necessary, and do not mark the remote workflow or ACE live run verified.

## Handoff verification

Review the spec against both plans, run `git diff --check`, and report actual verification output and any unavailable model/remote-runner paths. When credentials and the remote environment become available, the separate acceptance sequence is `make setup`, `make doctor`, `make setup ARGS="--offline"`, `make smoke`, explicit `make doctor ARGS="--model"`, and a small `make live ARGS="--iterations 3"`; a remote workflow run must be inspected independently. Do not turn a missing credential into a synthetic-success claim.
