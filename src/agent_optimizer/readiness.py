"""Static, read-only readiness checks for selected datasets and experiment plans."""
from __future__ import annotations

import contextlib
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from agent_optimizer import diagnostics
from agent_optimizer.config import load_experiment, read_toml, selected_pairs
from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer import models
from agent_optimizer.registry import (PROJECT_COMPONENTS, PROJECT_DEPENDENCIES, Registry,
                                      is_source_checkout, plugin_files)
from agent_optimizer.sources import selected
from agent_optimizer.workspace import safe_path


class Runner:
    """Read-only checks with explicit prerequisites and bounded, captured probes."""

    def __init__(self, root, area, environment=None):
        self.root = root
        self.area = area
        self.checks = []
        self.environment = dict(os.environ if environment is None else environment)

    def add(self, name, ok, message, remedy, *, requires=(), cause=None, retry=None):
        failed = [dependency for dependency in requires if not self.ok(dependency)]
        status = "blocked" if failed else "ok" if ok else "error"
        if failed:
            message = f"{message}\nBlocked by: {', '.join(failed)}"
        elif status == "error" and cause:
            message = f"{message}\nCause: {cause}"
        fix = ("Resolve " + ", ".join(failed) + " first. " + remedy
               if failed else "" if status == "ok" else remedy)
        if status != "ok" and retry:
            fix += f"\nRetry: {retry}"
        self.checks.append({"id": name, "area": self.area, "status": status,
                            "message": message, "remedy": fix})
        return status == "ok"

    def ok(self, name):
        return any(c["id"] == name and c["status"] == "ok" for c in self.checks)

    def run(self, argv: Sequence[str], *, cwd=None, timeout=15, label=None) -> diagnostics.CommandOutcome:
        command = label or _command_label(argv)
        environment = {k: v for k, v in self.environment.items()
                       if k not in {"PYTHONPATH", "PYTHONHOME"}}
        environment.update(PYTHONDONTWRITEBYTECODE="1", GIT_OPTIONAL_LOCKS="0")
        started = time.monotonic()
        try:
            result = subprocess.run(argv, cwd=cwd or self.root, env=environment,
                                    capture_output=True, text=True, timeout=timeout, shell=False)
            return diagnostics.CommandOutcome(
                command, result.returncode, _text(result.stdout), _text(result.stderr),
                elapsed_seconds=time.monotonic() - started,
            )
        except FileNotFoundError:
            return diagnostics.CommandOutcome(command, None, error_kind="missing",
                                              elapsed_seconds=time.monotonic() - started)
        except PermissionError:
            return diagnostics.CommandOutcome(command, None, error_kind="permission",
                                              elapsed_seconds=time.monotonic() - started)
        except subprocess.TimeoutExpired as exc:
            return diagnostics.CommandOutcome(
                command, None, _text(exc.stdout), _text(exc.stderr), timed_out=True,
                error_kind="timeout", elapsed_seconds=time.monotonic() - started,
            )
        except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
            return diagnostics.CommandOutcome(
                command, None, error_kind=type(exc).__name__.lower(),
                elapsed_seconds=time.monotonic() - started,
            )

    def probe(self, name, argv, message, remedy, *, requires=(), expected=None, timeout=15,
              retry=None):
        if any(not self.ok(dependency) for dependency in requires):
            self.add(name, False, message, remedy, requires=requires, retry=retry)
            return None
        outcome = self.run(argv, timeout=timeout)
        output = outcome.stdout.strip() if outcome.succeeded else None
        passed = outcome.succeeded and (expected is None or output == expected)
        cause = None
        if not passed:
            cause = (diagnostics.summarize_failure(outcome, environment=self.environment)
                     if not outcome.succeeded else f"{outcome.command} returned unexpected output")
        self.add(name, passed, message, remedy, requires=requires, cause=cause, retry=retry)
        return outcome


def _text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) else ""


def _command_label(argv: Sequence[str]) -> str:
    if not argv:
        return "command"
    executable = Path(str(argv[0])).name
    known = {
        "docker": {"info", "version", "compose", "image", "run", "rm", "build"},
        "git": {"--version", "rev-parse", "status", "clone", "checkout"},
        "uv": {"--version", "sync", "pip", "venv"},
    }
    if len(argv) > 1 and argv[1] in known.get(executable, set()):
        return f"{executable} {argv[1]}"
    return executable


def check(identifier: str, area: str, ok: bool, message: str, remedy: str, *,
          cause: str | None = None, retry: str | None = None) -> dict:
    if not ok and cause:
        message = f"{message}\nCause: {cause}"
    fix = "" if ok else remedy
    if not ok and retry:
        fix += f"\nRetry: {retry}"
    return {"id": identifier, "area": area, "status": "ok" if ok else "error",
            "message": message, "remedy": fix}


def sanitize_provider_row(row: dict) -> dict:
    """Redact secrets from an untrusted provider row while keeping its 5-key shape."""
    return {**row, "message": diagnostics.redact_text(row["message"]),
            "remedy": diagnostics.redact_text(row["remedy"])}


def _report(scope: str, checks: list[dict]) -> dict:
    return {"scope": scope, "ready": bool(checks) and all(row["status"] == "ok" for row in checks),
            "checks": checks}


@contextlib.contextmanager
def _no_bytecode():
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = previous


def _dataset(root: Path, dataset_id: str, registry: Registry) -> list[dict]:
    reference = PROJECT_COMPONENTS["datasets"].get(dataset_id)
    if reference is None:
        return [check("dataset.registration", "dataset", False,
                      "Dataset provider is unavailable",
                      "Use agent-opt datasets list and register the selected provider",
                      cause="dataset ID is not registered", retry="agent-opt datasets list")]
    registration = None
    try:
        if is_source_checkout(root):
            plugin_files(root, PROJECT_COMPONENTS, PROJECT_DEPENDENCIES)
    except (ConfigurationError, UnavailableError, OSError, ValueError, TypeError) as exc:
        registration = check("dataset.registration", "dataset", False,
                             "Central component inventory is incomplete",
                             "Restore missing registered integration files",
                             cause=diagnostics.summarize_exception(exc),
                             retry=f"agent-opt doctor --dataset {dataset_id}")
    # Only the selected trusted provider may execute Python during diagnosis.
    # A missing evaluator must not hide that provider's file-specific checks.
    try:
        plugin_files(root, {"datasets": {dataset_id: reference}}, {})
        registry.load_plugins(root, {"datasets": {dataset_id: reference}})
        provider = registry.resolve("datasets", dataset_id)()
    except (ConfigurationError, UnavailableError, OSError, ValueError, TypeError) as exc:
        return [registration or check("dataset.registration", "dataset", False,
                                      "Dataset provider is unavailable",
                                      "Use agent-opt datasets list and register the selected provider",
                                      cause=diagnostics.summarize_exception(exc),
                                      retry="agent-opt datasets list")]
    prefix = [registration] if registration else []
    if not callable(getattr(provider, "doctor", None)):
        return [*prefix, check("dataset.doctor", "dataset", False,
                       "Dataset provider has no read-only readiness check",
                       "Implement doctor(cache) for this dataset provider",
                       cause="provider has no doctor(cache) implementation")]
    try:
        rows = provider.doctor(root / "external" / "datasets" / dataset_id)
        if (not isinstance(rows, list) or not rows or
                any(not isinstance(row, dict) or set(row) != {"id", "area", "status", "message", "remedy"}
                    or not all(isinstance(value, str) for value in row.values())
                    or row["status"] not in {"ok", "error", "blocked"}
                    or (row["status"] != "ok" and not row["remedy"]) for row in rows)
                or len({row["id"] for row in rows}) != len(rows)):
            raise ConfigurationError("Invalid provider checks")
        return [*prefix, *(sanitize_provider_row(row) for row in rows)]
    except (ConfigurationError, UnavailableError, OSError, ValueError, TypeError) as exc:
        return [*prefix, check("dataset.doctor", "dataset", False,
                               "Dataset inspection failed", "Inspect the selected provider and its local cache",
                               cause=diagnostics.summarize_exception(exc),
                               retry=f"agent-opt doctor --dataset {dataset_id}")]


def _registered(registry: Registry, plugins: dict, kind: str, name: str) -> bool:
    """Resolve an ID from declarations only; never import its implementation."""
    if not isinstance(name, str) or not isinstance(plugins, dict):
        return False
    explicit = plugins.get(kind, {})
    if not isinstance(explicit, dict):
        return False
    if name in explicit and (name in registry.factories[kind] or name in PROJECT_COMPONENTS[kind]):
        return False
    return (name in registry.factories[kind] or name in PROJECT_COMPONENTS[kind]
            or name in explicit)


def collect_dataset(root: Path, dataset_id: str, registry: Registry) -> dict:
    with _no_bytecode():
        return _report("dataset", _dataset(root.resolve(), dataset_id, registry))


def _source_checks(spec: dict) -> list[dict]:
    sources, prompts, editables = [], [], []
    deferred = False
    for agent in spec["_agents"]:
        source = agent.source
        local = source is not None and source.kind == "local"
        if source is not None and source.kind == "git":
            # load_agent already validates the locator and full commit SHA. Only
            # declarations can be inspected until materialize_agent snapshots it.
            deferred = True
            sources.append(True)
            try:
                safe_path(Path("/schema-validation"), agent.prompt_file)
                prompts.append(selected(agent.prompt_file, source))
            except (ConfigurationError, OSError, ValueError):
                prompts.append(False)
            try:
                for pattern in agent.editable:
                    safe_path(Path("/schema-validation"), pattern)
                editables.append(bool(agent.editable) and all(
                    selected(pattern, source) or any(
                        not any(char in included for char in "*?[") and
                        fnmatch.fnmatchcase(included, pattern) and
                        selected(included, source) and
                        bool(safe_path(Path("/schema-validation"), included))
                        for included in source.include)
                    for pattern in agent.editable))
            except (ConfigurationError, OSError, ValueError):
                editables.append(False)
            continue
        try:
            root = safe_path(source.path, source.subdir) if local else None
        except (ConfigurationError, OSError, ValueError):
            root = None
        present = root is not None and root.is_dir()
        sources.append(present)
        if not local or not present:
            continue
        try:
            prompt = safe_path(root, agent.prompt_file)
            prompts.append(prompt.is_file() and selected(agent.prompt_file, source))
        except (ConfigurationError, OSError, ValueError):
            prompts.append(False)
        try:
            paths = []
            for pattern in agent.editable:
                safe_path(root, pattern)
                candidates = list(root.glob(pattern))
                if pattern.endswith("/**"):
                    candidates += list(root.glob(pattern + "/*"))
                for path in candidates:
                    relative = path.relative_to(root).as_posix()
                    if not selected(relative, source):
                        continue
                    safe_path(root, relative)
                    if path.is_file():
                        paths.append(path)
            editables.append(bool(paths))
        except (ConfigurationError, OSError, ValueError):
            editables.append(False)
    note = "; pinned Git source contents unverified until run snapshot" if deferred else ""
    return [check("agent.source", "agent", all(sources),
                  "Agent source declarations checked" + note if deferred else "Local Agent sources are available",
                   "Provide existing local Agent sources or prepare pinned Git sources",
                   cause=None if all(sources) else "one or more local Agent source directories are missing or unsafe"),
            check("agent.prompt", "agent", len(prompts) == len(sources) and all(prompts),
                  "Declared Agent prompt paths checked" + note if deferred else
                  "Declared Agent prompt sources are available",
                  "Provide each declared prompt_file in Agent source",
                  cause=None if len(prompts) == len(sources) and all(prompts) else
                  "a declared prompt file is missing or excluded by source filters"),
            check("agent.editable", "agent", len(editables) == len(sources) and all(editables),
                  "Declared editable Agent paths checked" + note if deferred else "Editable Agent files exist",
                  "Declare editable paths matching existing Agent files",
                  cause=None if len(editables) == len(sources) and all(editables) else
                  "editable patterns match no safe Agent files")]


def _budget_check(spec: dict) -> dict:
    stages = spec.get("stages", [])
    repetitions = spec.get("repetitions", 1)
    validation = sum(task.split == "validation" for task in spec["_tasks"]) * repetitions
    tests = sum(task.split == "test" for task in spec["_tasks"]) * repetitions
    per_group = validation + sum(stage.get("max_trials", 1) for stage in stages)
    if spec.get("final_test", False):
        per_group += 2 * tests
    required = per_group * len(selected_pairs(spec))
    configured = spec.get("budget", {}).get("max_trials", 100)
    valid = configured >= required
    return check("budget.trials", "budget", valid,
                 f"Trial budget must reserve at least {required} trials",
                 f"Set budget.max_trials to at least {required} or reduce stage allowances",
                 cause=None if valid else
                 f"configured budget is {configured} trials; required reserve is {required} trials")


def _optimizer_options(spec: dict) -> dict:
    valid = True
    for stage in spec.get("stages", []):
        name, options = stage["optimizer"], stage.get("config", {})
        if name not in {"gepa", "meta_harness", "ecdysis"}:
            continue
        if not isinstance(options, dict):
            valid = False
            continue
        filename = options.get("file")
        surface = (isinstance(filename, str) and bool(filename) and
                   (name == "gepa" or filename.endswith(".py")))
        if surface:
            try:
                surface = all(any(fnmatch.fnmatchcase(filename, pattern) for pattern in agent.editable) and
                                agent.source is not None and
                                selected(filename, agent.source) and
                                (safe_path(safe_path(agent.source.path, agent.source.subdir), filename).is_file()
                                 if agent.source.kind == "local" else
                                 bool(safe_path(Path("/schema-validation"), filename)))
                              for agent in spec["_agents"])
            except ConfigurationError:
                surface = False
        setting = "rounds" if name == "ecdysis" else "iterations"
        number = options.get(setting, 3)
        valid &= (bool(surface) and type(number) is int and 1 <= number <= 100 and
                  bool([task for task in spec["_tasks"] if task.split == "train"]))
    return check("optimizer.options", "optimizer", valid,
                 "Research optimizer options and editable source files are valid",
                  "Declare an existing editable optimizer file, train tasks, and positive iteration allowance",
                  cause=None if valid else
                  "optimizer file, train task, or iteration allowance is missing or invalid")


def _ace_asset_check(spec: dict) -> dict:
    """Read only the selected ACE lock and image identities; never run a container."""
    root = spec["_root"]
    retry = f"agent-opt prepare {spec['_source']}"
    if not is_source_checkout(root):
        from agent_optimizer.integrations import verified_integration
        try:
            marker = verified_integration(root)
            if marker is None or marker["id"] != "ace-rtl":
                raise ConfigurationError("ACE integration marker missing")
        except (ConfigurationError, OSError, ValueError) as exc:
            return check("integration.assets", "integration", False,
                         "Pinned ACE integration has not been prepared",
                         retry, cause=diagnostics.summarize_exception(exc), retry=retry)
    cause = None
    try:
        lock = json.loads((root / "external/environment-lock.json").read_text())
        from agent_optimizer.preset_tui import _lifecycle
        example_diagnostics = _lifecycle(root).load_example(
            root, "examples/ace-rtl/environment/diagnostics.py", "ace_plan_diagnostics")
        if not example_diagnostics.valid_lock(lock):
            raise ValueError("Invalid ACE lock")
        runner = Runner(root, "integration")
        for name in ("agent", "evaluation"):
            image = lock["images"][name]
            identity = runner.run(["docker", "image", "inspect", image["tag"]],
                                  label="docker image inspect")
            if not identity.succeeded:
                cause = diagnostics.summarize_failure(identity, environment=runner.environment)
                raise UnavailableError(cause)
            details = json.loads(identity.stdout)[0]
            if (details["Id"] != image["id"] or
                    f"{details['Os']}/{details['Architecture']}" != lock["platform"]):
                raise ValueError("ACE image identity or platform differs from the lock")
    except (OSError, KeyError, TypeError, ValueError, IndexError,
            ConfigurationError, UnavailableError) as exc:
        return check("integration.assets", "integration", False,
                     "Pinned ACE lock or Docker images are unavailable",
                     retry, cause=cause or diagnostics.summarize_exception(exc), retry=retry)
    return check("integration.assets", "integration", True,
                 "Pinned ACE lock and Docker image identities are available", "")


def _seed_check(spec: dict) -> dict:
    seeds = spec.get("candidate_seed_files", {})
    valid = isinstance(seeds, dict)
    if valid:
        for path, source in seeds.items():
            try:
                valid = (isinstance(path, str) and isinstance(source, str)
                         and bool(safe_path(Path("/schema-validation"), path))
                         and safe_path(spec["_root"], source).is_file()
                         and all(any(fnmatch.fnmatchcase(path, pattern) for pattern in agent.editable)
                                 and "agent/" + path in agent.build for agent in spec["_agents"]))
            except (ConfigurationError, OSError, TypeError, ValueError):
                valid = False
            if not valid:
                break
    return check("candidate.seed", "agent", valid,
                 "Candidate scaffold seed is available and executed from editable snapshot",
                  "Restore the declared candidate seed and active build entry",
                  cause=None if valid else "candidate seed is missing or outside the editable build surface")


def collect_plan(path: Path, registry: Registry, *, model: bool = False) -> dict:
    rows = []
    with _no_bytecode():
        try:
            raw = read_toml(path)
        except (OSError, ValueError) as exc:
            return _report("plan", [check("plan.schema", "plan", False,
                                            "Experiment file is missing or invalid",
                                            "Provide a valid experiment.toml",
                                            cause=diagnostics.summarize_exception(exc),
                                            retry=f"agent-opt doctor --plan {path}")])
        if "integration" in raw:
            from agent_optimizer.integrations import resolve_pointer
            try:
                prepared = resolve_pointer(path)
            except UnavailableError as exc:
                return _report("plan", [{"id": "integration.prepare", "area": "integration",
                                         "status": "blocked",
                                         "message": "선택한 연동의 준비가 필요합니다\nCause: "
                                                    + diagnostics.summarize_exception(exc),
                                         "remedy": f"agent-opt prepare {path}\nRetry: agent-opt prepare {path}"}])
            except (ConfigurationError, OSError, ValueError, TypeError) as exc:
                return _report("plan", [check("integration.pin", "integration", False,
                                               "선택형 연동의 ID·pin을 검증할 수 없습니다",
                                               "검토된 실험 선언을 복원하세요",
                                               cause=diagnostics.summarize_exception(exc),
                                               retry=f"agent-opt doctor --plan {path}")])
            return collect_plan(prepared, registry, model=model)
        project_root = raw.get("project_root", "../..")
        if not isinstance(project_root, str):
            return _report("plan", [check("plan.schema", "plan", False,
                                           "Experiment project_root is invalid",
                                           "Set project_root to a directory path string")])
        root = (path.parent / project_root).resolve()
        try:
            spec = load_experiment(path)
            rows.append(check("plan.schema", "plan", True, "Experiment schema is valid", ""))
        except (ConfigurationError, OSError, ValueError, KeyError, TypeError) as exc:
            spec = None
            rows.append(check("plan.schema", "plan", False, "Experiment schema or referenced input is invalid",
                              "Correct the experiment, Agent, harness, and benchmark declarations",
                              cause=diagnostics.summarize_exception(exc),
                              retry=f"agent-opt doctor --plan {path}"))
        plugins = raw.get("plugins", {})
        files_cause = None
        try:
            if is_source_checkout(root):
                plugin_files(root, PROJECT_COMPONENTS, PROJECT_DEPENDENCIES)
            plugin_files(root, plugins, raw.get("plugin_dependencies", {}))
            if spec is not None:
                registry.selected_files(root, spec)
            files_ok = True
        except (ConfigurationError, UnavailableError, OSError, ValueError, KeyError, TypeError) as exc:
            files_ok = False
            files_cause = diagnostics.summarize_exception(exc)
        rows.append(check("components.files", "components", files_ok,
                          "Registered component files and declared dependencies are available",
                          "Restore the selected registered component and declared dependency files",
                          cause=files_cause,
                          retry=f"agent-opt doctor --plan {path}"))
        profiles = []
        profile_cause = None
        try:
            profiles = (spec["_profiles"] if spec is not None else
                        [read_toml(safe_path(root, name)) for name in raw.get("harnesses", [])])
            argv_valid = True
            for profile in profiles:
                if not _registered(registry, plugins, "harnesses", profile["adapter"]):
                    raise UnavailableError("Unregistered harness")
                command = profile.get("command")
                if profile["adapter"] == "command" and (not isinstance(command, list) or not command):
                    argv_valid = False
            rows.append(check("agent.argv", "agent", argv_valid, "Agent execution argv is declared",
                              "Declare a nonempty harness.command argv array"))
            rows.append(check("harness.registration", "harness", True, "Harnesses are registered", ""))
        except (ConfigurationError, UnavailableError, OSError, ValueError, KeyError, TypeError) as exc:
            profile_cause = diagnostics.summarize_exception(exc)
            rows.append(check("harness.registration", "harness", False,
                              "Harness or declared plugin files are unavailable",
                              "Register the harness and provide its declared plugin files",
                              cause=profile_cause, retry=f"agent-opt doctor --plan {path}"))
        claude_profiles = [profile for profile in profiles
                           if profile.get("adapter") in {"claude_code", "ace_claude_code"}]
        if claude_profiles:
            rows.append(check("harness.runtime", "harness", all(
                profile.get("runtime", {}).get("kind", "local") == "local"
                for profile in claude_profiles), "Claude Code requires a local runtime",
                "Use a local runtime for Claude Code harnesses"))
        required = {"docker" for profile in profiles if profile.get("runtime", {}).get("kind") == "docker"}
        if spec is not None and spec.get("evaluation_runtime", {}).get("kind") == "docker":
            required.add("docker")
        required.update("opencode" for profile in profiles if profile.get("adapter") == "opencode"
                        and profile.get("runtime", {}).get("kind", "local") == "local")
        required.update("claude" for profile in claude_profiles
                        if profile.get("runtime", {}).get("kind", "local") == "local")
        missing_runtime = sorted(name for name in required if not shutil.which(name))
        runtime_ok = not missing_runtime
        rows.append(check("runtime.binary", "runtime", runtime_ok,
                          "Declared runtime binaries are available",
                          "Install the declared Docker, OpenCode, or Claude Code (claude) runtime executable",
                          cause=None if runtime_ok else "Missing runtime executable(s): "
                          + ", ".join(missing_runtime), retry=f"agent-opt doctor --plan {path}"))
        try:
            if not _registered(registry, plugins, "evaluators", raw["evaluator"]):
                raise UnavailableError("Unregistered evaluator")
            rows.append(check("evaluator.registration", "evaluator", True, "Evaluator is registered", ""))
        except (KeyError, TypeError, UnavailableError, ConfigurationError) as exc:
            rows.append(check("evaluator.registration", "evaluator", False, "Evaluator is not registered",
                              "Register the selected evaluator or supply an explicit evaluator plugin",
                              cause=diagnostics.summarize_exception(exc),
                              retry=f"agent-opt doctor --plan {path}"))
        stages = raw.get("stages", [])
        try:
            for stage in stages:
                if not _registered(registry, plugins, "optimizers", stage["optimizer"]):
                    raise UnavailableError("Unregistered optimizer")
            rows.append(check("optimizer.registration", "optimizer", True, "Optimizers are registered", ""))
        except (KeyError, UnavailableError, ConfigurationError, TypeError) as exc:
            rows.append(check("optimizer.registration", "optimizer", False, "Optimizer is not registered",
                              "Select a registered optimizer",
                              cause=diagnostics.summarize_exception(exc),
                              retry=f"agent-opt doctor --plan {path}"))
        if spec is not None:
            rows.extend(_source_checks(spec))
            if spec.get("preset_selection"):
                rows.append(_ace_asset_check(spec))
            rows.append(check("agent.output", "agent", all(task.files for task in spec["_tasks"]),
                              "Task output files are declared", "Declare task output file paths in the benchmark"))
            rows.append(_budget_check(spec))
            rows.append(_optimizer_options(spec))
            if "candidate_seed_files" in spec:
                rows.append(_seed_check(spec))
            provider_id = spec["_benchmark_metadata"].get("dataset_provider")
            if provider_id:
                rows.extend(_dataset(root, provider_id, registry))
                try:
                    expected = registry.resolve("datasets", provider_id)().describe()["evaluator"]
                    matched = expected == spec["evaluator"]
                    dataset_cause = None if matched else "dataset provider evaluator does not match the plan"
                except (ConfigurationError, UnavailableError, KeyError, TypeError) as exc:
                    matched = False
                    dataset_cause = diagnostics.summarize_exception(exc)
                rows.append(check("dataset.evaluator", "dataset", matched,
                                  "Selected dataset and evaluator match",
                                  "Use the registered evaluator ID from the selected dataset provider",
                                  cause=dataset_cause,
                                  retry=f"agent-opt doctor --plan {path}"))
            else:
                rows.append(check("dataset.manifest", "dataset", True,
                                  "Custom benchmark schema and splits are valid", ""))
        research = any(isinstance(stage, dict) and stage.get("optimizer") in
                       {"gepa", "meta_harness", "ecdysis"} for stage in stages)
        harness_models = [profile.get("model_env", "AGENT_OPT_MODEL") for profile in profiles
                          if profile.get("adapter") == "opencode" or
                          (profile.get("adapter") == "ace_opencode" and spec is not None
                           and spec.get("preset_selection"))]
        if research or harness_models:
            try:
                if research:
                    models.ModelSettings.from_env()
                configured = all(isinstance(key, str) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", key)
                                 and bool(os.environ.get(key)) for key in harness_models)
            except (ConfigurationError, UnavailableError) as exc:
                configured = False
                model_cause = diagnostics.summarize_exception(exc)
            else:
                model_cause = None
            rows.append(check("model.configuration", "model", configured,
                              "Required model configuration is present",
                               "Set AGENT_OPT_MODEL_BASE_URL and AGENT_OPT_MODEL_API_KEY for research optimizers; "
                              "set " + ", ".join(harness_models or ["AGENT_OPT_MODEL"]) + " for OpenCode harnesses",
                              cause=model_cause,
                              retry=f"agent-opt doctor --plan {path}"))
        if model:
            try:
                models.probe_model()
                rows.append(check("model.probe", "model", True, "Model connectivity probe passed", ""))
            except (ConfigurationError, UnavailableError, OSError) as exc:
                rows.append(check("model.probe", "model", False, "Model connectivity probe failed",
                                  "Verify model credentials, endpoint, connectivity, and tool-call support",
                                  cause=diagnostics.summarize_exception(exc),
                                  retry=f"agent-opt doctor --plan {path} --model"))
    return _report("plan", rows)
