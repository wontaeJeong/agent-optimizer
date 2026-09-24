"""Read-only development diagnostics; subprocess output is never a public message."""
import json
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.network import CA_VARIABLES, demo_environment, network_environment
from agent_optimizer.registry import Registry
from agent_optimizer import readiness

SETUP = "Run sh scripts/bootstrap.sh setup (or python3 scripts/dev.py setup)."


def load_module(name, path):
    # Read source from the implementation checkout, not the root being diagnosed.
    # Unlike a normal source loader this does not create __pycache__ directories.
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


class Runner:
    """Small collector with explicit prerequisites and bounded, captured probes."""

    def __init__(self, root, area, environment=None):
        self.root = root
        self.area = area
        self.checks = []
        self.environment = dict(os.environ if environment is None else environment)

    def add(self, name, ok, message, remedy, *, requires=()):
        failed = [dependency for dependency in requires if not self.ok(dependency)]
        status = "blocked" if failed else "ok" if ok else "error"
        self.checks.append({
            "id": name, "area": self.area, "status": status,
            "message": ("Requires: " + ", ".join(failed)) if failed else message,
            "remedy": ("Resolve " + ", ".join(failed) + " first. " + remedy)
            if failed else "" if ok else remedy,
        })
        return status == "ok"

    def ok(self, name):
        return any(c["id"] == name and c["status"] == "ok" for c in self.checks)

    def run(self, argv, *, cwd=None, timeout=15):
        environment = {k: v for k, v in self.environment.items()
                       if k not in {"PYTHONPATH", "PYTHONHOME"}}
        environment.update(PYTHONDONTWRITEBYTECODE="1", GIT_OPTIONAL_LOCKS="0")
        try:
            result = subprocess.run(
                argv, cwd=cwd or self.root, env=environment, capture_output=True,
                text=True, timeout=timeout, shell=False,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.SubprocessError, UnicodeError):
            return None

    def probe(self, name, argv, message, remedy, *, requires=(), expected=None, timeout=15):
        output = self.run(argv, timeout=timeout) if all(self.ok(d) for d in requires) else None
        self.add(name, output is not None and (expected is None or output == expected),
                 message, remedy, requires=requires)
        return output


def core_checks(root, environment=None):
    runner = Runner(root, "core", environment)
    runner.add("core.host", sys.platform in {"darwin", "linux"} and sys.version_info >= (3, 11),
               "Host OS and diagnostic Python compatibility (Mac/Linux, Python >=3.11).",
               "Use Mac or Ubuntu with Python >=3.11; run sh scripts/bootstrap.sh setup.")
    for tool, remedy in (("git", "Install Git: Mac: xcode-select --install; Ubuntu: sudo apt install git."),
                         ("uv", SETUP)):
        available = shutil.which(tool, path=runner.environment.get("PATH", os.defpath)) is not None
        output = runner.run([tool, "--version"]) if available else None
        runner.add(f"core.{tool}", output is not None, f"Host {tool} executable.", remedy)
    python = root / ".venv/bin/python"
    version = runner.run([str(python), "-I", "-B", "-c",
                          "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"]
                         ) if python.is_file() else None
    # Core CI supports both 3.11 and 3.12; the example driver specifically needs 3.12.
    runner.add("core.python", version is not None and version.startswith("3.")
               and version[2:].isdigit() and int(version[2:]) >= 11,
               "Project .venv Python >=3.11.", SETUP)
    runner.probe("core.venv", [str(python), "-I", "-B", "-c",
                 "import sys; from pathlib import Path; "
                 "assert sys.prefix != sys.base_prefix; "
                 "assert Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve()",
                 str(root / ".venv")],
                 "Interpreter belongs to the project virtualenv.", SETUP, requires=("core.python",))
    runner.probe("core.package", [str(python), "-I", "-B", "-c",
                 "import agent_optimizer; import importlib.metadata as m; "
                 "m.distribution('agent-optimizer')"],
                 "Installed project package in .venv.", SETUP, requires=("core.venv",))
    runner.probe("core.cli", [str(root / ".venv/bin/agent-opt"), "--help"],
                 "Installed agent-opt executable.", SETUP, requires=("core.package",))
    for tool in ("ruff", "build"):
        runner.probe(f"core.{tool}", [str(python), "-I", "-B", "-m", tool, "--version"],
                     f"Project {tool} development tool.", SETUP, requires=("core.venv",))
    return runner.checks


@lru_cache(maxsize=1)
def example_adapter():
    return load_module("ace_diagnostics", Path(__file__).resolve().parents[1]
                       / "examples/ace-rtl/environment/diagnostics.py")


def collect_report(root: Path, platform: str | None = None, *, core_only: bool = False,
                   dataset: str | None = None) -> dict:
    # Own validation here so malformed optional trust never bypasses aggregation.
    # Child-only settings prevent normalized proxies/CA paths leaking into later calls.
    environment = demo_environment()
    network = Runner(root, "core")
    try:
        environment.update(network_environment(environment))
        valid = True
    except ConfigurationError:
        valid = False
        # All current doctor probes inspect local state (offline inventory, no-pull
        # images, network-none containers). None needs the invalid trust override.
        for key in (*CA_VARIABLES, "AGENT_OPT_CA_BUNDLE"):
            environment.pop(key, None)
        environment.update(network_environment(environment))
    network.add("network.configuration", valid, "Optional proxy and CA configuration.",
                "Correct or unset AGENT_OPT_CA_BUNDLE; provide a readable valid full PEM trust bundle "
                "without private keys, then rerun doctor.")
    local_bin = str(Path(root) / ".cache/uv/bin")
    environment["PATH"] = local_bin + os.pathsep + environment.get("PATH", os.defpath)
    checks = network.checks + core_checks(Path(root), environment)
    if core_only:
        for check in checks:
            check["remedy"] = check["remedy"].replace("setup", "setup --core")
        ready = all(c["status"] == "ok" for c in checks)
        return {"scope": "core", "ready": ready, "areas": {"core": ready}, "checks": checks}
    if dataset is not None:
        selected = readiness.collect_dataset(Path(root), dataset, Registry())
        checks += selected["checks"]
        core_ready = all(c["status"] == "ok" for c in checks if c["area"] == "core")
        return {"scope": "dataset", "ready": core_ready and selected["ready"],
                "areas": {"core": core_ready, "dataset": selected["ready"]}, "checks": checks}
    checks += example_adapter().collect_checks(Path(root), platform, environment=environment)
    areas = {area: all(c["status"] == "ok" for c in checks if c["area"] == area)
             for area in ("core", "evaluation", "live")}
    ready = areas["core"] and areas["evaluation"]
    areas["live"] = ready and areas["live"]
    return {"ready": ready, "areas": areas, "checks": checks}


def render_report(report: dict, *, json_output: bool = False) -> None:
    if json_output:
        print(json.dumps(report))
        return
    title = ("Core development environment: " if report.get("scope") == "core" else
             "Selected dataset environment: " if report.get("scope") == "dataset" else "Development environment: ")
    print(title + ("ready" if report["ready"] else "not ready"))
    for area, ready in report["areas"].items():
        print(f"  {area}: {'ready' if ready else 'not ready'}")
    for check in report["checks"]:
        print(f"[{check['status']}] {check['id']}: {check['message']}")
        if check["remedy"]:
            print(f"  Fix: {check['remedy']}")
    if report.get("scope") == "core":
        print("ACE evaluation and model readiness not checked; use full setup/doctor (menu option 7 prepares ACE).")
    elif report.get("scope") == "dataset":
        print("Selected dataset checks are read-only; no ACE Agent image or model was checked.")
    elif "model_status" in report:
        print("Explicit model probes: " + report["model_status"])
    else:
        print("Live checks validate configuration only; no model endpoint or smoke was exercised. Use doctor --model for actual calls.")
