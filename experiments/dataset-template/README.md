# Dataset provider template

Copy `provider.py` to `experiments/<team>/`, implement `prepare()` and read-only `doctor()`,
and register IDs in `src/agent_optimizer/registry.py` under `PROJECT_COMPONENTS`:

```python
"datasets": {"team_dataset": "experiments/my-team/provider.py:Provider"},
"evaluators": {"team_evaluator": "experiments/my-team/evaluator.py:Evaluator"},
```

Add harness/optimizer IDs to their corresponding mappings and declared helper paths to
`PROJECT_DEPENDENCIES` (for example `"datasets/team_dataset": ["experiments/my-team/importer.py"]`).
Keep existing registrations when editing those mappings. No CLI choice or install entry-point edit is needed.
`describe()` lists the task form and evaluator ID. `prepare(cache, offline=False)` must return a
dictionary containing a public versioned `benchmark` path, registered `evaluator` name and
`provenance` (source/version and verified hashes). The sample intentionally raises
`UnavailableError` until real preparation and private scoring are connected.

`doctor(cache)` returns checks with `id`, `area`, `status`, `message`, `remedy`; it only inspects
local prepared assets and must not download, install, build, execute an evaluator or call a model.
Run `.venv/bin/agent-opt datasets list`, then `agent-opt doctor --dataset team_dataset --json`
and `agent-opt doctor --plan runs/configs/<name>/experiment.toml --json` before running.
An `error` remains an error until the verified assets and evaluator are implemented.
Avoid placing private test answers or credentials in public task files. One-off experiment
`[plugins.*]` file references remain supported separately from central discovery.
