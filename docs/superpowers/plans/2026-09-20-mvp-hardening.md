# MVP Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the eight reviewed defects and provide a small, reproducible Docker/CVDP development path with team-owned Optimizer extension points.

**Architecture:** Preserve the flat Python CLI and existing contracts. Sources/candidates, trial execution and reporting, example evaluators, and environment preparation remain separate responsibilities. Use file plugins rather than a new framework.

**Tech Stack:** Python >=3.11 core, Python 3.12 integration environment, unittest, uv, Docker, existing official CVDP OSS image (Yosys/Icarus), pinned OpenCode, Hugging Face dataset files.

**Spec:** `docs/superpowers/specs/2026-09-20-mvp-hardening-design.md`

## Global Constraints

- 기존 Python CLI, 평평한 코어 모듈, `contracts.py`와 파일 플러그인 구조를 유지한다.
- 상세 최적화 알고리즘은 팀원이 담당한다. Meta-Harness를 첫 연결 검토 대상으로 하되, GEPA/Ecdysis 등도 같은 계약으로 연결한다.
- runner가 validation 선택과 final test를 소유하며 알고리즘끼리 직접 호출하지 않는다.
- Agent에 Docker socket이나 비공개 평가 파일을 전달하지 않는다.
- 초기 모델은 OpenRouter 무료 모델이다. 유료 모델로 자동 대체하지 않는다.
- 인증은 환경변수로 전달하고 값은 로그·manifest에 저장하지 않는다.
- ACE/CVDP 소스의 기존 고정 SHA는 필요 근거 없이 갱신하지 않는다.
- 모든 과제가 제외되거나 필수 입력이 없으면 실패한다. 합성 데이터로 대체하지 않는다.
- 상용 EDA 어댑터는 추가하지 않는다.
- Mac Docker와 Ubuntu x86_64의 실제 검증 결과를 구분한다.
- Work only in `.worktrees/mvp-hardening`; no further subagents from implementers/reviewers. Use apply_patch for edits. Commit task code after tests and self-review. Never merge or publish releases.

## File responsibilities

- `workspace.py`, `sources.py`: validated filesystem boundaries, candidate identity and source inclusion.
- `runner.py`, `results.py`, `objectives.py`, `config.py`: interruption semantics, durable usage, selection and schema checks.
- `registry.py`, `experiments/optimizer-template/`: dependency fingerprints and team integration examples.
- `examples/rtl-debugger/`: trusted small RTL checking through synthesis and a private testbench.
- `examples/ace-rtl/environment/`, `prepare.py`, `evaluator.py`: pinned preparation, real-data import and official evaluation.
- `scripts/dev.py`: thin developer command entry point, delegating domain setup to examples.
- `.github/workflows/ci.yml`, docs and README: repeatable verification and truthful handoff.

### Task 1: Candidate and filesystem boundaries

**Files:** Modify `src/agent_optimizer/{workspace,sources,runner}.py`; add `tests/test_boundaries.py`; adjust existing workspace tests only for changed contract.

**Interfaces:** Keep `CandidateStore.create(parent=None, edits=None, producer="baseline")`. Add `CandidateStore.verify(candidate) -> None` backed by an internal issued-candidate mapping; `GroupRunner.verify_candidate` delegates to it. Keep `collect_outputs(source, target)` public signature.

- [ ] Add failing tests for a symlink output root, internal symlink and non-directory/missing root; verify no sentinel host file is copied. Test ID/hash/path/parents/producer substitution on an issued candidate, altered editable/noneditable bytes and positive normal parent lineage.

```python
with self.assertRaises(ConfigurationError):
    store.verify(replace(child, id=baseline.id))
with self.assertRaises(ConfigurationError):
    collect_outputs(link_to_private_directory, target)
self.assertFalse((target / "secret.txt").exists())
```

- [ ] Run `PYTHONPATH=src python3 -m unittest discover -s tests -p test_boundaries.py -v` and capture expected RED.
- [ ] Validate root and components before traversal/copy; reject links even if they resolve inside the root. Reject special files. Preserve legitimate macOS `/var` system path aliases by validating the controlled workspace boundary, not blindly rejecting every host ancestor. A store accepts only exactly issued candidate metadata with current matching contents; unknown IDs cannot seed creation. Only successfully materialized candidates enter the map. Ensure verification occurs before a cache hit.
- [ ] Default-source hidden developer directories remain excluded. Explicit `include` prefixes such as `.opencode/agents/**` may include reviewed runtime assets; default `*` is not an override. Keep `.git`, IDE/cache dirs, `.env*`, recognized auth/credential files unconditionally excluded. Add fixtures for default exclusion, explicit inclusion and explicit attempted auth inclusion; do not blanket-promise detection of arbitrary secrets.
- [ ] Run focused tests and full unittest once. Self-review, update component docs for source selection, commit with a concise imperative subject.

### Task 2: Budget, durable partial results and selection semantics

**Files:** Modify `src/agent_optimizer/{runner,results,objectives,config,contracts}.py` as needed; add `tests/test_run_lifecycle.py`.

**Interfaces:** Consume `CandidateStore.verify`. Keep `OptimizationContext.record_usage(input_tokens, output_tokens, cost_usd)` signature. Persist `optimizer_usage` events at call time with agent/harness/stage identity. Preserve completed summary fields while allowing partial groups with nullable baseline and empty selected/final_test lists.

- [ ] Add RED tests using short local subprocess or controlled monotonic clock: global wall budget below trial timeout must produce `budget_exhausted` and no valid zero-score row; configured per-trial timeout remains a scored failure. Cover source/baseline, stage, and final-test interruption, usage before budget/error, and Ctrl-C with preserved completed records.

```python
self.assertEqual(summary["status"], "budget_exhausted")
self.assertEqual(summary["groups"][0]["selected"], [])
self.assertTrue(any(e["event"] == "optimizer_usage" for e in events))
with self.assertRaises(ConfigurationError):
    validate_objective({"mode": "pareto", "keep": 1, "metrics": metrics})
```

- [ ] Run `PYTHONPATH=src python3 -m unittest discover -s tests -p test_run_lifecycle.py -v`, recording RED.
- [ ] Track whether a trial timeout was shortened by global deadline; when that deadline interrupts evaluation, persist an invalid interrupted record and raise BudgetExceeded. Check remaining time after execution/evaluation even for the last trial. Do not inflate used trials when reservation fails. Preserve actual attempted-trial evidence, usage and current-group state on all runner exits; error summary/CLI behavior stays explicit. Avoid broad swallowing of implementation errors.
- [ ] Keep reporting and rerank compatible with nullable partial data, excluding invalid/partial selections. Pareto returns the whole frontier; reject explicit keep in Pareto both configuration and direct selector usage, while keeping weighted/lexicographic behavior. Update docs for statuses, partial records and keep.
- [ ] Run focused tests, full unittest and minimal demo to a worktree run directory. Review/commit.

### Task 3: Reproducible plugins and team Optimizer extension surface

**Files:** Modify `src/agent_optimizer/{registry,config,runner}.py`; create `experiments/optimizer-template/{README.md,optimizer.py,experiment.toml}`; add `tests/test_plugin_contracts.py`; update `docs/adding-components.md`, RTL example experiment dependency declarations.

**Interfaces:** Add optional experiment `plugin_dependencies` mapping `"evaluators/name" -> ["project/relative/file.py"]`, also usable for optimizers/harnesses. All dependency paths are validated relative to project root. Keep existing `[plugins.<kind>] name="file.py:Symbol"` strings. Manifest includes the directly registered plugin and declared dependency hashes; no automatic Python import crawler.

- [ ] Add RED tests for dependency-only edit changes fingerprint, missing/escaping/dead plugin dependency references fail preflight, and unchanged file registration remains valid. Add an in-memory fake Optimizer exercising train feedback/usage/propose; verify validation/test never enter its public context and external plugin registration can replace a reserved algorithm slot.

```python
self.assertNotEqual(before["plugin_sha256"], after["plugin_sha256"])
self.assertTrue(all(row["split"] == "train" for row in context.history()))
with self.assertRaises(UnavailableError):
    template_optimizer.optimize(context, seeds, {})
```

- [ ] Run focused test file and capture RED.
- [ ] Implement the small fingerprint declaration, add `iverilog.py` to RTL evaluator dependencies, and expose no new optimization framework. Template optimize explicitly raises UnavailableError until team code is supplied; template experiment points at existing minimal source/data/harness and template plugin so `plan` and expected run failure can be tested.
- [ ] Document concrete Meta-Harness adaptation points (candidate text changes, train evaluate/history feedback, optimizer usage, checkpoint metadata), no algorithm implementation or unsupported paper-reproduction claims. Preserve file_variants as runnable contract example.
- [ ] Run focused tests and full suite, self-review and commit.

### Task 4: Trusted toy RTL checking and real simulator regression

**Files:** Modify `examples/rtl-debugger/{evaluator,iverilog}.py`, `tasks.json`, README; update `tests/test_adapters.py` and add `tests/test_rtl_evaluation.py`.

**Interfaces:** Keep `IcarusVerilog.run(workspace, config, timeout_seconds) -> Evaluation`. Add explicit evaluation `design_sources` and `design_top` for the tiny RTL tasks; existing `sources`/`top` still identify trusted simulation composition. Runtime continues through `process.execute` local/Docker; missing Yosys/Icarus is infrastructure_error, not a scored candidate failure.

- [ ] RED contract tests: candidate prints TEST_PASS then `$finish`, correct combinational candidate, wrong output candidate, missing tools, timeouts. Real tests skip unless Yosys+iverilog+vvp are present; later Docker task must run them for real.

```python
attack = 'module dut(input a,b,output y); assign y=a; initial begin $display("TEST_PASS"); $finish; end endmodule'
self.assertNotEqual(evaluate_dut(attack).status, "passed")
self.assertEqual(evaluate_dut(correct_dut).status, "passed")
self.assertEqual(evaluate_dut(wrong_dut).metrics["passed"], 0.0)
```

- [ ] Run focused contract tests and capture RED before implementation.
- [ ] For this small synthesizable RTL example, synthesize only the declared DUT inputs using Yosys into a trusted generated netlist; then run private testbench with that netlist, never original Agent RTL. Synthesis logs cannot satisfy simulator pass markers; `$finish`/unsupported synthesis constructs are rejected explicitly. Keep source selection and intermediate filenames controlled; copy trusted private testbench after DUT preparation. Validate isolation of the phase directories and reserve timeout across both phases. This is a limited toy RTL evaluator, not a general Verilog security sandbox. If an actual Yosys behavior invalidates this design, report the evidence for a controller ruling.
- [ ] Update fixtures and tests to use actual DUT+testbench, not a standalone self-printing module. Follow actual subprocess argv/return code in mocks; do not write tests that merely assert mock output was returned.
- [ ] Run focused tests/full suite, record real tool absence accurately, self-review/commit.

### Task 5: Pinned CVDP preparation and portable Docker developer commands

**Files:** Extend `examples/ace-rtl/environment/setup.py`; create a small dataset acquisition helper in the same directory if separation is useful; extend `prepare.py`, `evaluator.py`, `setup.sh`, README; create `scripts/dev.py`; adjust `pyproject.toml`, `uv.lock`, `.env.example`, `examples/rtl-debugger/Dockerfile`, ACE harness profile; add `tests/test_dev_environment.py`.

**Interfaces:** `python scripts/dev.py setup`, `python scripts/dev.py smoke`, and `python scripts/dev.py live` are the stable user commands. Setup prepares `.venv`/integration environment using uv with Python 3.12, fixed source commits, dataset and Docker images. Support setup `--offline` to reuse verified source/data/images and `--platform linux/amd64` (default) or a validated explicit alternate platform. Smoke does not require an LLM key; live requires OPENROUTER_API_KEY and an explicitly free model. These commands orchestrate existing domain helpers, not a service framework.

- [ ] Inspect pinned upstream actual JSONL rows, CVDP CLI/evaluation behavior, official Dockerfile and license metadata before finalizing import paths. Pin dataset revision `5b807d945f6a99aa645f7e43a64a2115e281b4bf` only after confirming files match the current importer domain. Preserve ACE `fead921f18bb57345b5a41ef93ba625be208e99c` and CVDP `8e894cf74414ab1eaea1e2b4e80a02f123df07b6`. Pin OpenCode `1.18.31` after checking its current provider config/CLI via official docs/Context7.
- [ ] Write RED tests for atomic download/hash validation/cache reuse/offline misses; non-commercial unsupported rows get exclusion reasons, full official data without golden solution still derives reviewed target paths from trusted harness metadata (never guessed paths); empty supported set fails; environment doctor reports actual execution capability; model auth missing/free-only validation fail before live run.

```python
self.assertEqual(first_lock["sha256"], cached_lock["sha256"])
with self.assertRaises((ConfigurationError, UnavailableError)):
    prepare_offline_with_missing_asset()
self.assertNotIn("OPENROUTER_API_KEY", json.dumps(public_manifest_values))
```

- [ ] Implement pinned exact-file HF downloads of `cvdp_v1.1.0_nonagentic_code_generation_no_commercial.jsonl`, LICENSE, NOTICE. Prefer stdlib HTTPS fixed URLs + SHA-256 if sufficient; avoid adding a heavy datasets library. Capture trusted expected hashes during the pinned-source inspection, not from the downloaded content alone. Reuse verified caches, support offline reuse, record versions/platform/image IDs, fail explicitly on errors and preserve preexisting user checkout changes.
- [ ] Reuse official CVDP OSS Dockerfile; avoid separate Icarus/Yosys installations for the Docker development flow. Maintain separate pinned OpenCode image and evaluation image. Host trusted CVDP driver has isolated Python dependencies; Agent containers have no socket/private data. Keep image/platform selection consistent for official nested evaluation containers and avoid killing unrelated containers on timeout.
- [ ] Configure free OpenRouter through existing OpenCode provider config and env substitution; include a generic OpenAI-compatible provider configuration example using endpoint/model env variables. No private deployment purpose in files. Never copy host credentials into generated files, logs, image layers or git. Do not mount credential stores to Agent containers.
- [ ] Smoke runs toy RTL positive/negative/early-exit checks and one official CVDP positive/negative submission, verifying nonempty raw results. Use reviewed reference submission only in the evaluator smoke; never copy it into Agent public inputs. Live invokes ACE skill profile then actual CVDP; unavailable auth/model returns a named blocked/error state without synthetic fallback.
- [ ] Run focused tests/full suite, then setup and smoke on available Mac Docker. Record image build/network/emulation blockers rather than claiming success. Avoid pip-installing globally or changing system Docker settings. Self-review/commit with full commands/results in report.

### Task 6: CI, final developer handoff and integration verification

**Files:** Modify `.github/workflows/ci.yml`, README, CONTRIBUTING, docs/{CONTEXT,architecture,adding-components,SOURCES,status,verification,NEXT_STEPS}.md, relevant example READMEs; update setup/helpers/tests only to resolve concrete cross-task integration failures.

**Interfaces:** Consume `scripts/dev.py` setup/smoke/live and prior task contracts. Keep network/LLM live tests distinct from deterministic CI; retain Python 3.11/3.12 core CI and packaging checks.

- [ ] Run documented dev setup/smoke entry points and inspect results. Ensure actual simulator coverage in Linux CI (small package install or cached official image, chosen for MVP speed), and a manual official CVDP Docker integration job using the same dev commands. External LLM live runs remain explicit with secrets supplied by env.
- [ ] Validate CLI examples via commands; preserve missing-key failures and unsupported optimizer behavior. Run `uv run --frozen --extra dev ruff check .`, `uv run --frozen --extra dev python -m unittest discover -s tests -v`, `uv run --frozen --extra dev python -m agent_optimizer run examples/minimal/experiment.toml`, `uv run --frozen --extra dev python -m build`, and wheel install outside source using a worktree-local temp directory.
- [ ] Document actual observed environment, hashes/model selection, exclusions, real Docker results vs mocks/skips, and remaining blockers. No invented Ubuntu results, LLM execution or algorithm support. Keep requirements, current scope, and team-owned algorithm work distinct.
- [ ] Spec coverage audit: trace all 8 review findings to tests; trace source/data locks, team plugin contract, setup cache/offline, Docker evaluation and model configuration to implemented files and verification evidence. Fix only concrete omissions using regression tests; do not add optional platform features.
- [ ] Self-review, commit, report commands/output and remaining external blockers for final whole-branch review.
