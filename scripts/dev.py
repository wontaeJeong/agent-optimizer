"""Development commands: setup -> doctor -> demo; run from any working directory."""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Direct Python invocation must be read-only before any project imports/loaders.
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.results import write_json
from agent_optimizer.network import network_environment, ca_fingerprint, demo_environment
from agent_optimizer.registry import Registry
from agent_optimizer import readiness
from agent_optimizer.terminal_style import style


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_core(command):
    """Use the project venv, never uv run's implicit environment installation."""
    python = ROOT / ".venv/bin/python"  # Do not resolve executable symlinks.
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"PYTHONHOME", "PYTHONPATH"}}
    probe = subprocess.run(
        [str(python), "-I", "-B", "-c",
         "import sys; from pathlib import Path; assert sys.version_info >= (3, 11); "
         "assert sys.prefix != sys.base_prefix; "
         "assert Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve()", str(ROOT / ".venv")],
        cwd=ROOT, env=environment, capture_output=True, timeout=15, shell=False,
    )
    if probe.returncode:
        raise UnavailableError("Project .venv is unavailable/incompatible; run sh scripts/bootstrap.sh setup --core")
    commands = {
        "test": ["unittest", "discover", "-s", "tests", "-v"],
        "lint": ["ruff", "check", "."],
        "demo": ["agent_optimizer", "run", "examples/minimal/experiment.toml"],
    }
    code = subprocess.run([str(python), "-m", *commands[command]], cwd=ROOT,
                          env=environment, shell=False).returncode
    if code:
        print(style(f"{command} failed (exit {code})", "error") + "; inspect the command output above. "
              "If dependencies are missing, run sh scripts/bootstrap.sh setup --core.", flush=True)
    return code


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        "Core prerequisites: Git; full ACE setup also needs Docker Engine/Compose. No Python/make? "
        "Use sh scripts/bootstrap.sh setup --core. make <command> ARGS='...' uses normal shell arguments."
    ))
    commands = parser.add_subparsers(dest="command")
    descriptions = {
        "setup": "Without --core/--dataset: full ACE setup; with --core: core and fixture; "
                 "with --dataset ID: selected dataset preparation",
        "doctor": "Without --core/--dataset: full ACE diagnostics; --core: core-only; "
                  "--dataset ID: selected dataset diagnostics (read-only; --model opts in to model calls)",
        "test": "Run unittest in the project .venv (no Docker requirement)",
        "lint": "Run Ruff in the project .venv",
        "demo": "Run the minimal synthetic demo without Docker/API",
        "smoke": "Run real RTL/CVDP evaluator checks",
        "live": "Run iterative optimization with the configured model (authentication required)",
        "menu": "Open the numbered interactive menu (TTY required; session-only model settings)",
        "help": "Show this help without probing or installing tools",
    }
    for name, description in descriptions.items():
        command = commands.add_parser(name, help=description, description=description, allow_abbrev=False)
        if name in {"setup", "doctor"}:
            command.add_argument("--core", action="store_true", help="Core tooling only; no Docker/ACE checks (excludes --dataset/--platform/--model)")
            command.add_argument("--dataset", metavar="ID", help="Prepare or diagnose one registered dataset (excludes --core/--platform/--model)")
        if name in {"setup", "doctor", "smoke", "live"}:
            command.add_argument("--platform",
                                 help="Default: Docker daemon native platform")
        if name == "setup":
            command.add_argument("--offline", action="store_true", help="Reuse verified cached assets; no downloads/builds")
        if name == "doctor":
            command.add_argument("--json", action="store_true", help="Emit a single JSON report")
            command.add_argument("--model", action="store_true", help="Explicitly call host API and container OpenCode tools")
        if name == "live":
            command.add_argument("--iterations", type=int, help="Override optimizer iterations (1..20, default 3)")
    args = parser.parse_args(argv)
    if args.command in {None, "help"}:
        parser.print_help()
        return 0
    if args.command == "menu":
        return load("dev_menu", "scripts/menu.py").main([])
    if args.command == "live" and args.iterations is not None and not 1 <= args.iterations <= 20:
        parser.error("--iterations must be from 1 to 20")
    core_only = getattr(args, "core", False)
    dataset_id = getattr(args, "dataset", None)
    if dataset_id is not None and not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", dataset_id):
        parser.error("--dataset requires an identifier (lowercase letters, digits, _, . or -)")
    if core_only and dataset_id is not None:
        parser.error("--core cannot be combined with --dataset")
    if dataset_id is not None and (args.platform is not None or getattr(args, "model", False)):
        parser.error("--dataset cannot be combined with --platform or --model")
    if core_only and (args.platform is not None or getattr(args, "model", False)):
        parser.error("--core cannot be combined with --platform or --model; omit --core for full ACE commands")
    setup_command = "sh scripts/bootstrap.sh setup"
    if core_only or args.command in {"test", "lint", "demo"}:
        setup_command += " --core"
    elif dataset_id is not None:
        setup_command += f" --dataset {dataset_id}"
    repair = f"Inspect external/setup-logs/ and rerun {setup_command}"
    stage = args.command
    try:
        if args.command == "doctor":
            doctor = load("dev_doctor", Path(__file__).resolve().with_name("dev_doctor.py"))
            if dataset_id is not None:
                report = doctor.collect_report(ROOT, dataset=dataset_id)
            else:
                report = doctor.collect_report(ROOT, args.platform, core_only=True) if core_only else doctor.collect_report(ROOT, args.platform)
            if args.model:
                checks = load("ace_model_checks", "examples/ace-rtl/environment/model_checks.py")
                checks.check_models(ROOT, report)
            doctor.render_report(report, json_output=args.json)
            return 0 if report["ready"] else 2
        local_bin = str(ROOT / ".cache/uv/bin")
        if local_bin not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = local_bin + os.pathsep + os.environ.get("PATH", "")
        if args.command in {"setup", "smoke", "live"}:
            os.environ.update(demo_environment())
        os.environ.update(network_environment())
        if args.command in {"test", "lint", "demo"}:
            return run_core(args.command)
        if args.command == "setup" and os.environ.get("AGENT_OPT_BOOTSTRAPPED") != str(ROOT):
            return subprocess.run(["sh", str(ROOT / "scripts/bootstrap.sh"), *argv],
                                  cwd=ROOT, shell=False).returncode
        os.chdir(ROOT)
        if args.command == "setup" and dataset_id is not None:
            stage = "dataset registration"
            registry = Registry()
            registry.load_project(ROOT)
            if dataset_id not in registry.factories["datasets"]:
                raise ConfigurationError(f"Unknown dataset ID: {dataset_id}; run agent-opt datasets list "
                                         "or register it in src/agent_optimizer/registry.py")
            provider = registry.resolve("datasets", dataset_id)()
            stage = "dataset preparation"
            prepared = provider.prepare(ROOT / "external/datasets" / dataset_id, offline=args.offline)
            evaluator_id = prepared.get("evaluator")
            if not isinstance(evaluator_id, str) or ":" in evaluator_id:
                raise ConfigurationError("Registered dataset provider must return a registered evaluator ID")
            try:
                registry.resolve("evaluators", evaluator_id)
            except UnavailableError:
                raise ConfigurationError(f"Dataset provider returned unregistered evaluator ID {evaluator_id!r}; "
                                         "register it in src/agent_optimizer/registry.py") from None
            stage = "final doctor"
            doctor = load("dev_doctor", Path(__file__).resolve().with_name("dev_doctor.py"))
            report = doctor.collect_report(ROOT, dataset=dataset_id)
            doctor.render_report(report)
            if not report["ready"]:
                raise UnavailableError("Selected dataset doctor failed; follow the diagnostic repair instructions")
            print(json.dumps({"status": "ready", "scope": "dataset", "dataset": dataset_id,
                              "next": f'make doctor ARGS="--dataset {dataset_id} --json"'}))
            return 0
        if not core_only:
            setup = load("ace_environment", "examples/ace-rtl/environment/setup.py")
            if args.command == "live":
                setup.validate_live()  # Before image probes, data reads, or any model execution.
            args.platform = setup.validate_platform(args.platform)
        if args.command == "setup":
            if not core_only:
                stage = "example environment"
                print(style(f"[setup] {stage}: starting", "warning")
                      + f"; logs: {ROOT / 'external/setup-logs'}", flush=True)
                dataset, lock = setup.prepare_environment(offline=args.offline, platform=args.platform)
                print(style(f"[setup] {stage}: complete", "success"), flush=True)
                stage = "dataset preparation"
                print(style(f"[setup] {stage}: starting", "warning")
                      + f"; output: {ROOT / 'datasets/ace-demo'}", flush=True)
                prepare = load("ace_prepare", "examples/ace-rtl/prepare.py")
                manifest = prepare.prepare_dataset(dataset, ROOT / "datasets/ace-demo/all-tasks.json", lock)
                demo = load("ace_demo", "examples/ace-rtl/environment/demo.py")
                manifest = demo.select_tasks(manifest)
                write_json(ROOT / "datasets/ace-demo/tasks.json", manifest)
                print(style(f"[setup] {stage}: complete", "success"), flush=True)
            stage = "final doctor"
            print(style(f"[setup] {stage}: starting", "warning") + " (read-only)", flush=True)
            doctor = load("dev_doctor", Path(__file__).resolve().with_name("dev_doctor.py"))
            report = doctor.collect_report(ROOT, args.platform, core_only=True) if core_only else doctor.collect_report(ROOT, args.platform)
            doctor.render_report(report)
            if not report["ready"]:
                raise UnavailableError("Final doctor failed; follow the diagnostic repair instructions")
            print(style(f"[setup] {stage}: complete", "success"), flush=True)
            stage = "minimal demo"
            print(style(f"[setup] {stage}: starting", "warning")
                  + f"; results: {ROOT / 'runs'}", flush=True)
            code = run_core("demo")
            if code:
                raise UnavailableError(f"Minimal demo failed (exit {code}); inspect runs/")
            print(style(f"[setup] {stage}: complete", "success"), flush=True)
            if core_only:
                print(json.dumps({"status": "ready", "scope": "core", "results": "runs/",
                                  "next": 'make doctor ARGS="--core"; make menu; make demo'}))
            else:
                print(json.dumps({"status": "ready", "environment_lock": "external/environment-lock.json",
                                  "results": "runs/", "next": "make doctor; make test; make smoke"}))
            return 0
        lock_path = ROOT / "external/environment-lock.json"
        if not lock_path.is_file():
            raise UnavailableError("blocked_environment: run python scripts/dev.py setup first")
        lock = setup.read_environment_lock(lock_path)
        if lock["platform"] != args.platform:
            raise ConfigurationError("Prepared platform differs; use matching --platform")
        if lock.get("ca_bundle_sha256") != ca_fingerprint():
            raise ConfigurationError("CA bundle differs from prepared images; rerun setup")
        setup.prepare_sources(ROOT / "external", offline=True)
        setup.prepare_data(ROOT / "external", offline=True)
        setup.validate_driver_lock(ROOT / "external", lock)
        sim_image = setup.verified_sim_image(lock)
        capability = setup.doctor(ROOT / "external", args.platform,
                                  lock["images"]["evaluation"]["id"], lock["images"]["agent"]["id"])
        write_json(ROOT / "external/setup-logs/doctor.json", capability)
        if not capability["ready"]:
            raise UnavailableError("blocked_environment: execution doctor failed; inspect external/setup-logs/doctor.json")
        os.environ["DOCKER_DEFAULT_PLATFORM"] = args.platform
        os.environ["OSS_SIM_IMAGE"] = sim_image
        example = load("ace_dev_checks", "examples/ace-rtl/environment/checks.py")
        if args.command == "smoke":
            return example.smoke(lock)
        return example.live(lock, iterations=args.iterations) if args.iterations is not None else example.live(lock)
    except (ConfigurationError, UnavailableError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "blocked", "stage": stage, "reason": str(exc),
                          "repair": repair}))
        return 2
    except KeyboardInterrupt:
        print(json.dumps({"status": "interrupted", "stage": stage,
                          "repair": repair}))
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
