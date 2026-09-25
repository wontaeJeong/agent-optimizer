# Deferred advanced features

현재 MVP는 복수 팀 Agent × 호환 Harness 프로필과 독립적으로 등록한 복수 Optimizer를 지원한다.
모든 stage는 해당 그룹의 변경되지 않은 baseline에서 시작한다. baseline 평가가 cache에서
반환되어도 train 이력에는 baseline과 자기 stage의 후보만 포함된다. `gepa`, `meta_harness`,
`ecdysis`는 현재 내장 Optimizer ID다. 파일 플러그인은 중복 등록이 거부되므로 다른 ID를 사용해야 한다.

The features below are retired from the active runtime, not hidden behind flags.
Their original implementations and acceptance tests are recoverable from Git
revision **`9afcabe`**. Inspect an original file with
`git show 9afcabe:<original-path>` and review it before restoring functionality.
The `.txt` snapshots below are unchanged archival material, not runnable example
profiles or discoverable Python plugins. No experimental runtime is provided.

| Retired feature | Original source / example paths | Original test paths | Reason / restoration condition |
|---|---|---|---|
| Cross-stage chaining, validation gates, skipped-input routing | `src/agent_optimizer/config.py` (`load_experiment`), `src/agent_optimizer/runner.py` (`GroupRunner.run`, `gate_passes`); `examples/minimal/branching.toml`; chained `prompt-review` in `examples/minimal/experiment.toml` | `tests/test_core.py` (`test_branch_gate_skip_does_not_remove_other_branch`) | Independent team comparisons come first. Restore only with an explicit orchestration requirement and defined cross-stage feedback/selection semantics. |
| Weighted/Pareto selection, weights/scales, constraints, multiple winners, max/p95 aggregation | `src/agent_optimizer/config.py` (`validate_objective`), `src/agent_optimizer/objectives.py` | `tests/test_core.py` (`ObjectiveTests`), `tests/test_run_lifecycle.py` (`SelectionTests`) | Keep selection interpretable: lexicographic, one winner, mean/sum. Restore after concrete metric tradeoff/frontier requirements and invalid/partial/null regression coverage. |
| Stored-result reranking | `src/agent_optimizer/cli.py` (`main`, rerank parser and branch) | `tests/test_core.py` (`test_rerank_rejects_changed_metric_semantics`), `tests/test_run_lifecycle.py` (`test_report_and_rerank_accept_nullable_baseline`) | Preserve one frozen validation selection. Restore when offline reselection semantics and provenance are required; never use test scores. Report JSON/CSV remains available. |
| Installed entry-point auto-discovery | `src/agent_optimizer/registry.py` (`resolve`) | `tests/test_plugin_contracts.py` (file registration and dependency contracts); no dedicated installed-entry-point acceptance test existed | Explicit file registration is sufficient for team integration. Restore only with a packaging/distribution use case and duplicate/provenance tests. |
| 과거 미구현 연구 슬롯과 계획 목록 | 당시 `src/agent_optimizer/optimizers/gepa.py`, `meta_harness.py`, `ecdysis.py`; `src/agent_optimizer/registry.py` (`describe`); `examples/minimal/research-planned.toml` | 당시 `tests/test_core.py` (`test_planned_optimizer_never_falls_back`), `tests/test_plugin_contracts.py` (`test_file_plugin_can_replace_reserved_optimizer_slot`) | 슬롯은 이력 자료다. 현재 세 ID는 별도의 내장 자체 구현이며, 다른 팀 알고리즘은 중복되지 않는 ID로 등록한다. |

## Preserved snapshots

Each path maps to the original path obtained by removing `deferred/` and `.txt`:

- `deferred/examples/minimal/branching.toml.txt`
- `deferred/examples/minimal/research-planned.toml.txt`
- `deferred/src/agent_optimizer/optimizers/gepa.py.txt`
- `deferred/src/agent_optimizer/optimizers/meta_harness.py.txt`
- `deferred/src/agent_optimizer/optimizers/ecdysis.py.txt`

Mixed active modules and original acceptance tests stay archived in `9afcabe`
rather than duplicated as another runtime. Current tests explicitly refuse the
retired options and preserve multi-Agent/Harness execution, independent optimizer
comparison, baseline-cache history isolation, error/lifecycle and data boundaries.

## Active compatibility

- Agent/Harness arrays, file plugin API and stage/result envelopes remain.
- `inputs` may be omitted or exactly `["baseline"]`; any `when` is rejected.
- With stages, the default final pool includes every independent stage's selected
  candidate. `final_stages` remains an explicit subset (including `baseline` if
  desired). With no stages, the default pool is baseline. No unavailable optimizer
  silently falls back to baseline.
- `objective.mode` is omitted or `lexicographic`; `keep` is omitted or integer 1.
  Metric sources remain generic, directions maximize/minimize, aggregates mean/sum.
  Constraints, weights and scales are rejected even when empty/default-valued.
- `rerank` returns an actionable deferred error and is absent from public help.
  `report`, CSV export, frozen selections and existing persisted schemas remain.
- Optimizer usage records additionally identify the registered `optimizer` name;
  nullable/partial usage reporting remains distinct from selection priorities.
