# Dataset provider template

Copy `provider.py` and `extensions.toml` to `experiments/<team>/` and update the registration path.
`describe()` lists the task form and evaluator ID. `prepare(cache, offline=False)` must return a
dictionary containing a public versioned `benchmark` path, registered `evaluator` name and
`provenance` (source/version and verified hashes). The sample intentionally raises
`UnavailableError` until real preparation and private scoring are connected.

File registrations in `extensions.toml` are relative to the project root. Register any team
harness/optimizer/evaluator under `[plugins.harnesses]`, `[plugins.optimizers]` and
`[plugins.evaluators]` in the same manifest. Dependencies are declared under
`[plugin_dependencies]`; avoid placing test answers or credentials in public task files.
