# Iterative Demo and Environment Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a bounded LLM feedback optimizer against ACE-RTL through OpenCode with reproducible setup and actionable diagnostics.

**Architecture:** Keep the flat Python core, argparse CLI, existing runner and file-plugin contracts. Add one small model transport and one example optimizer; extend the existing ACE setup entry point rather than introduce a second environment manager. A local OpenCode config hook rewrites only its chat completion request URL when an exact endpoint is configured.

**Tech Stack:** Python 3.11+ stdlib, uv/Python 3.12 CVDP driver, Docker/Compose, pinned OpenCode 1.18.31, existing unittest/ruff.

**Spec:** `docs/superpowers/specs/2026-09-22-environment-cleanup-design.md`

## Global Constraints

- Default model `glm5.3-flash`; model, endpoint and Bearer token are environment configuration.
- No real deployment address or credentials in repository files, commits or PR text.
- Keep `contracts.py`, candidate snapshots, editable enforcement, train-only optimization and validation selection.
- Keep fixed ACE/CVDP/data revisions and driver dependency lock.
- Missing metrics are null, never inferred zero; complete Agent totals remain distinct from partial Harness metrics.
- No TUI, parallel scheduler, resume or research algorithm implementation.
- Docker target is Ubuntu Linux x86_64; distinguish Mac ARM64 and mock evidence.
- Fetch and merge latest `origin/main` immediately before PR; rerun verification and merge after CI.

## Task 1: Model transport and exact endpoint integration

**Files:** create `src/agent_optimizer/models.py`, `tests/test_models.py`, `examples/rtl-debugger/endpoint-plugin.mjs`; modify the example Dockerfile and compatible config.

**Interfaces:** `ModelSettings.from_env(env=None)` yields endpoint/model/key (key excluded from repr); `complete(messages, *, settings=None, timeout=60, tools=None, tool_choice=None) -> dict` returns validated OpenAI JSON. `probe_model() -> dict` performs a bounded forced function call and reports only safe status/usage. The OpenCode plugin keeps the bundled OpenAI-compatible SDK and its streaming/tool semantics.

- [ ] Add local HTTP server tests for exact `/v1/chat/completion` vs standard base URL, Bearer, model override, malformed response, HTTP errors and refused redirect.

```python
with patch.dict(os.environ, {"MODEL_ENDPOINT": server_url + "/v1/chat/completion",
                             "MODEL_API_KEY": "fixture-token"}, clear=True):
    result = complete([{"role": "user", "content": "hello"}])
    self.assertEqual(captured[0]["path"], "/v1/chat/completion")
    self.assertEqual(captured[0]["body"]["model"], "glm5.3-flash")
```

- [ ] Run `PYTHONPATH=src python3 -m unittest discover -s tests -p test_models.py -v`; expect missing-module failure.
- [ ] Implement strict env URL selection (exact endpoint OR base URL), HTTPS except loopback fixtures, no credentials/query in URL, no secret response body in errors, bounded response size, normal TLS/proxy handling.
- [ ] Implement the dependency-free OpenCode hook; configure only the named compatible provider and forward request init/body/signal untouched.

```javascript
export default async () => ({
  config: async (config) => {
    const endpoint = process.env.MODEL_ENDPOINT;
    if (!endpoint) return;
    const options = config.provider.compatible.options;
    const expected = options.baseURL.replace(/\/$/, "") + "/chat/completions";
    options.fetch = (url, init) => {
      if (String(url) !== expected) throw new Error("Unexpected model request path");
      return fetch(endpoint, { ...init, redirect: "error" });
    };
  },
});
```

- [ ] Test hook routing using Node's built-in test runner and a fixture fetch; then exercise pinned OpenCode in Docker against a streaming tool-call HTTP fixture.
- [ ] Rerun model tests, inspect diff and commit this deliverable.

## Task 2: Bounded feedback optimizer and nullable usage

**Files:** create `experiments/simple-feedback/optimizer.py`, its README and `tests/test_feedback_optimizer.py`; modify `contracts.py`, `runner.py`, `results.py` and plugin documentation.

**Interfaces:** file plugin `Optimizer.optimize(context, seeds, config)` accepts `iterations` (default 3), `file`, `request_timeout_seconds` (default 60). It uses `models.complete`, `context.evaluate/history/propose/record_usage`. `record_usage` accepts nullable input/output counts without breaking existing integer calls. Optional `remaining_seconds()` on runtime Context bounds the model request without requiring old plugins to implement it.

- [ ] Write fake-server + real-runner tests with one synthetic seed, separate train/validation/test tasks, 3 generated candidates and seed retained. Assert model messages contain only selected train status/metrics/feedback, never full trial artifacts or validation sentinel.

```python
self.assertEqual(len(result.candidates), 4)
self.assertEqual(len(context.train_calls), 4)
self.assertEqual([u["input_tokens"] for u in usage], [None, 10, 10])
self.assertNotIn("private-validation-sentinel", json.dumps(requests))
```

- [ ] Run focused tests and verify RED.
- [ ] Implement strict configuration, one target file, bounded content, structured `{"content": "..."}` reply, usage recorded before parsing candidate content, failure on invalid train row, and snapshot proposals only. Use the latest candidate as next parent, return every candidate for runner validation.
- [ ] Add optional progress to stderr and checkpoint metadata (model, iterations, candidate IDs); expose durable usage/iteration information in report without treating unknown cost as free.
- [ ] Rerun focused and lifecycle/plugin/boundary suites; inspect diff and commit.

## Task 3: Usable setup and structured diagnostics

**Files:** modify `scripts/dev.py`, `examples/ace-rtl/environment/setup.py`, `src/agent_optimizer/network.py`; create `examples/ace-rtl/environment/diagnostics.py`, `tests/test_demo_environment.py`; update existing environment tests.

**Interfaces:** `diagnostics.prerequisites(offline=False) -> dict` checks tools and returns `ready/checks` with actionable repairs. `diagnostics.inspect_environment(setup, platform, check_model=False) -> dict` accumulates prepared-environment checks and optional host/container model probes. `network_environment` honors explicit CA and reuses readable Ubuntu system bundle when selected by demo setup.

- [ ] Add tests for missing uv/Compose/Buildx before installation, failed daemon, setup absence, independent errors, host OpenCode absence with working container, unchanged offline lock checks, and secret-free diagnostics.

```python
self.assertFalse(report["ready"])
self.assertEqual(report["checks"]["compose"]["status"], "blocked")
self.assertIn("docker compose", report["checks"]["compose"]["repair"])
self.assertNotIn("fixture-secret", json.dumps(report))
```

- [ ] Run focused tests and verify RED.
- [ ] Retain `python3 scripts/dev.py setup|doctor|smoke|live`; add `doctor --model`, JSON result option and stderr phase progress. `doctor` works before setup and reports all independent blockers. Setup runs preflight first; normal doctor never calls a model.
- [ ] Use explicit bundle first, then Ubuntu system bundle for demo setup/commands; reuse existing container/build propagation and CA drift rejection. Distinguish daemon image-pull trust from build/runtime CA.
- [ ] Replace OpenRouter-specific live preflight with shared model settings; configure `AGENT_OPT_MODEL=compatible/<MODEL_ID>` consistently for the demo and pass endpoint/key/model/config env names into its Docker profile.
- [ ] Add a model probe inside the same Agent image/network/CA path as real execution, with no model credentials in evaluator environment. Probe streaming/tool calls via the pinned Harness fixture and use explicit live tool-call check for the selected endpoint.
- [ ] Run environment/network tests and setup/doctor failure commands, review and commit.

## Task 4: ACE train/validation demo and plugin handoff

**Files:** modify ACE `experiment.toml`, `harness.toml`, `adapter.py`, `environment/checks.py`, `scripts/dev.py`; create example-local demo selection helper and `experiments/harness-template/`; update `.env.example`, root/ACE README, `docs/adding-components.md`, `docs/network.md`, `docs/NEXT_STEPS.md`.

**Interfaces:** `demo.select_tasks(manifest) -> dict` picks two fixed supported IDs with distinct families and assigns one train and one validation; `live(lock, iterations=3)` sizes trial budget for all train/validation evaluations and applies selected locked image. Harness template exports `Harness.run(request)` with explicit unavailable failure until implemented.

- [ ] Inspect fixed downloaded data to select a small supported train problem and existing QAM16 validation, preserving family IDs. Add tests refusing missing tasks/same family and asserting no reference outputs in public files.

```python
selected = select_tasks(manifest)
self.assertEqual({t["split"] for t in selected["tasks"]}, {"train", "validation"})
self.assertEqual(len({t["family"] for t in selected["tasks"]}), 2)
```

- [ ] Run tests and verify RED.
- [ ] Register simple-feedback through `[plugins.optimizers]`, declare helper fingerprints, set iterations=3, retain baseline, allocate `2 * (iterations + 1)` trials for one task per split, expose iteration override on live. Use the approved guidance file and bounded prompt size.
- [ ] Move ACE prefix into a reusable helper if required by the template; keep core domain-free. Provide exact registration steps and clarify Claude Code/Codex authentication/model-protocol work remains per adapter.
- [ ] Document fresh Ubuntu sequence: export env → setup → doctor → doctor --model → smoke → live --iterations 3 → report. Clearly distinguish API-free fixture, evaluator-only smoke and actual model end-to-end.
- [ ] Run plugin registration, demo data, minimal end-to-end and command help tests; commit.

## Task 5: Integration evidence, upstream merge and PR

**Files:** update `docs/SOURCES.md`, `docs/status.md`, `docs/verification.md` with actual commands/results and supported boundaries; update this plan checkboxes.

- [ ] Execute `PYTHONPATH=src python3 -m unittest discover -s tests -v` and `PYTHONPATH=src python3 -m agent_optimizer run examples/minimal/experiment.toml`.
- [ ] Execute `uv run --frozen --extra dev ruff check .`, `uv run --frozen --extra dev python -m build`, and `git diff --check`.
- [ ] Run actual Docker OpenCode streaming/tool-call fixture and official setup/offline/doctor/smoke where available; preserve failures rather than call them successes. Record inaccessible real endpoint as unverified.
- [ ] Review spec coverage, secrets, full diff, source isolation and artifacts; resolve findings with focused regression tests.
- [ ] Commit intended files after status/diff/log inspection. Immediately before PR run `git fetch origin && git merge origin/main`, resolve conflicts and rerun affected/full regression checks on merged code.
- [ ] Review tracking, commits and `git diff origin/main...HEAD`, push branch, create PR via `gh`, inspect CI. Merge after required checks pass using the user's existing approval, then report PR URL and exact verification/blocker status.
