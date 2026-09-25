"""Small composition point; domain adapters live outside the core."""
import hashlib
import importlib.util
import sys
from pathlib import Path
from agent_optimizer.config import read_toml
from agent_optimizer.contracts import ConfigurationError, UnavailableError, BUILTIN_HARNESSES
from agent_optimizer.workspace import safe_path
from agent_optimizer.harnesses.command import CommandHarness, FixtureHarness
from agent_optimizer.harnesses.opencode import OpenCodeHarness
from agent_optimizer.optimizers.baseline import BaselineOptimizer
from agent_optimizer.optimizers.file_variants import FileVariantsOptimizer
from agent_optimizer.optimizers.gepa import GEPAOptimizer
from agent_optimizer.optimizers.meta_harness import MetaHarnessOptimizer
from agent_optimizer.optimizers.ecdysis import EcdysisOptimizer


PROJECT_COMPONENTS: dict[str, dict[str, str]] = {
    "datasets": {"cvdp": "examples/benchmarks/cvdp.py:Provider",
                 "verilog-spec": "examples/benchmarks/verilog_eval.py:Provider",
                 "verilog-completion": "examples/benchmarks/verilog_eval.py:CompletionProvider",
                 "sample_text": "experiments/sample-team/provider.py:Provider"},
    "evaluators": {"cvdp": "examples/ace-rtl/evaluator.py:CVDPEvaluator",
                   "verilog_eval": "examples/benchmarks/verilog_evaluator.py:VerilogEvaluator",
                   "sample_eval": "examples/minimal/evaluator.py:TextFixtureEvaluator"},
    "harnesses": {"sample_command": "experiments/sample-team/harness.py:Harness"},
    "optimizers": {"sample_baseline": "experiments/sample-team/optimizer.py:Optimizer"},
}

PROJECT_DEPENDENCIES: dict[str, list[str]] = {
    "datasets/cvdp": ["examples/ace-rtl/prepare.py", "examples/ace-rtl/environment/setup.py"],
    "datasets/verilog-spec": ["examples/benchmarks/Dockerfile.iverilog12"],
    "datasets/verilog-completion": ["examples/benchmarks/Dockerfile.iverilog12"],
    "evaluators/cvdp": ["examples/ace-rtl/environment/network_driver.py"],
    "evaluators/verilog_eval": ["examples/benchmarks/verilog_eval.py"],
}


def is_source_checkout(root: Path) -> bool:
    marker = root / "pyproject.toml"
    try:
        return marker.is_file() and read_toml(marker).get("project", {}).get("name") == "agent-optimizer"
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def plugin_files(root, plugins, dependencies):
    """Validate explicit file dependencies; do not discover Python imports."""
    if not isinstance(plugins, dict):
        raise ConfigurationError("plugins must be a mapping")
    for kind, entries in plugins.items():
        if kind not in {"optimizers", "harnesses", "evaluators", "datasets"}:
            raise ConfigurationError(f"Unknown plugin kind: {kind}")
        if not isinstance(entries, dict):
            raise ConfigurationError(f"plugins.{kind} must be a mapping")
        for name, reference in entries.items():
            if (not isinstance(reference, str) or ":" not in reference
                    or not all(reference.rsplit(":", 1))):
                raise ConfigurationError(f"plugins.{kind}.{name} requires a file.py:Symbol reference")
    if not isinstance(dependencies, dict):
        raise ConfigurationError("plugin_dependencies must be a mapping of kind/name to path lists")
    registered = {f"{kind}/{name}" for kind, entries in plugins.items() for name in entries}
    files = {ref: safe_path(root, ref.rsplit(":", 1)[0])
             for entries in plugins.values() for ref in entries.values()}
    for key, paths in dependencies.items():
        if key not in registered:
            raise ConfigurationError(f"plugin_dependencies references an unregistered file plugin: {key}")
        if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
            raise ConfigurationError(f"plugin_dependencies[{key!r}] must be a string list")
        for path in paths:
            file = safe_path(root, path)
            if path in files and files[path] != file:
                raise ConfigurationError(f"Plugin dependency conflicts with a registered fingerprint key: {path}")
            files[path] = file
    for reference, file in files.items():
        if not file.is_file():
            raise ConfigurationError(f"Plugin file does not exist or is not a regular file: {reference}")
    return files


class Registry:
    def __init__(self):
        self.factories = {
            "optimizers": {"baseline": BaselineOptimizer, "file_variants": FileVariantsOptimizer,
                           "gepa": GEPAOptimizer, "meta_harness": MetaHarnessOptimizer,
                           "ecdysis": EcdysisOptimizer},
            "harnesses": {"command": CommandHarness, "fixture": FixtureHarness, "opencode": OpenCodeHarness},
            "evaluators": {},
            "datasets": {},
        }
        self.reserved = {"optimizers": set(),
                         "harnesses": {"claude_code", "codex", "openagent"},
                         "evaluators": set(), "datasets": set()}
        self.loaded = {}

    def load_project(self, root: Path) -> None:
        if not is_source_checkout(root):
            return
        plugin_files(root, PROJECT_COMPONENTS, PROJECT_DEPENDENCIES)
        self.load_plugins(root, PROJECT_COMPONENTS)

    def selected_files(self, root: Path, spec: dict) -> dict[str, Path]:
        """Return source and declared helpers for only the selected project components."""
        selected = {kind: {} for kind in PROJECT_COMPONENTS}
        names = {
            "datasets": [spec.get("_benchmark_metadata", {}).get("dataset_provider")],
            "evaluators": [spec.get("evaluator")],
            "harnesses": [profile["adapter"] for profile in spec.get("_profiles", [])],
            "optimizers": [stage["optimizer"] for stage in spec.get("stages", [])],
        }
        for kind, requested in names.items():
            for name in requested:
                if name in PROJECT_COMPONENTS[kind]:
                    selected[kind][name] = PROJECT_COMPONENTS[kind][name]
                elif kind == "datasets" and name:
                    raise ConfigurationError(f"Unregistered dataset provider: {name}")
        dependencies = {key: paths for key, paths in PROJECT_DEPENDENCIES.items()
                        if key.split("/", 1)[1] in selected.get(key.split("/", 1)[0], {})}
        files = plugin_files(root, selected, dependencies)
        files.update(plugin_files(root, spec.get("plugins", {}), spec.get("plugin_dependencies", {})))
        return files

    def load_plugins(self, root, config):
        # Validate the whole inventory before importing any trusted team code.
        for kind, entries in config.items():
            if kind not in self.factories:
                raise ConfigurationError(f"Unknown plugin kind: {kind}")
            for name in entries:
                if name in self.factories[kind] and (kind, name) not in self.loaded:
                    raise ConfigurationError(f"Duplicate plugin registration: {kind}/{name}")
        for kind, entries in config.items():
            if kind not in self.factories:
                raise ConfigurationError(f"Unknown plugin kind: {kind}")
            for name, reference in entries.items():
                path, symbol = reference.rsplit(":", 1)
                file = safe_path(root, path)
                key = (kind, name)
                fingerprint = (str(file), symbol)
                if self.loaded.get(key) == fingerprint:
                    continue
                if name in self.factories[kind]:
                    raise ConfigurationError(f"Duplicate plugin registration: {kind}/{name}")
                module_name = "agent_opt_plugin_" + hashlib.sha256(str(file).encode()).hexdigest()[:16]
                spec = importlib.util.spec_from_file_location(module_name, file)
                if spec is None or spec.loader is None:
                    raise ConfigurationError(f"Cannot load plugin: {reference}")
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                try:
                    spec.loader.exec_module(module)
                except ImportError as exc:
                    raise UnavailableError(f"{kind}/{name}: Python dependency unavailable "
                                           f"({exc.name or type(exc).__name__})") from None
                try:
                    implementation = getattr(module, symbol)
                except AttributeError:
                    raise ConfigurationError(f"Plugin {kind}/{name} does not export {symbol}") from None
                self.factories[kind][name] = implementation
                self.loaded[key] = fingerprint

    def resolve(self, kind, name):
        if name in self.factories[kind]:
            return self.factories[kind][name]
        status = "not implemented" if name in self.reserved[kind] else "unregistered plugin"
        raise UnavailableError(f"{kind}/{name}: {status}; register a file plugin in [plugins.{kind}]. "
                               "Installed entry-point discovery and research slots are deferred; see deferred/README.md")

    def describe(self):
        result = {kind: {"implemented": sorted(items)}
                  for kind, items in self.factories.items()}
        result["capabilities"] = BUILTIN_HARNESSES
        return result
