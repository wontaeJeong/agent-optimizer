"""ACE/CVDP read-only checks, kept separate from the mutating setup entry points."""
import hashlib
import os
import re
import shutil
import uuid
from pathlib import Path
from types import ModuleType
import json

from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.models import ModelSettings
from agent_optimizer.network import ca_fingerprint

# This adapter also works when loaded by file path, from any working directory.
_helper_path = Path(__file__).resolve().parents[3] / "scripts/dev_doctor.py"
_helper = ModuleType("diagnostic_runner")
_helper.__file__ = str(_helper_path)
exec(compile(_helper_path.read_bytes(), str(_helper_path), "exec"), _helper.__dict__)
setup = _helper.load_module("ace_diagnostic_inputs", Path(__file__).with_name("setup.py"))
Runner = _helper.Runner
SETUP = _helper.SETUP
PLATFORMS = {"linux/amd64", "linux/arm64"}
DOCKER_REMEDY = ("Mac: install/start Docker Desktop or Colima with Compose. "
                 "Ubuntu: install Docker Engine and docker-compose-plugin; start the daemon "
                 "and grant your user Docker socket access. Retry docker info and docker compose version.")


def digest(path):
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def valid_lock(lock):
    """Validate every consumed field before using values as command arguments."""
    if not isinstance(lock, dict):
        return False
    platform = lock.get("platform")
    if not isinstance(platform, str) or platform not in PLATFORMS:
        return False
    repos = lock.get("repos")
    if not isinstance(repos, dict) or repos != {k: list(v) for k, v in setup.REPOS.items()}:
        return False
    dataset = lock.get("dataset")
    if not isinstance(dataset, dict) or dataset.get("revision") != setup.DATA_REVISION:
        return False
    files = dataset.get("files")
    if not isinstance(files, dict):
        return False
    for name, expected in setup.ASSETS.items():
        if not isinstance(files.get(name), dict) or files[name].get("sha256") != expected:
            return False
    requirements = lock.get("driver_requirements")
    if not isinstance(requirements, dict):
        return False
    if (requirements.get("path") != setup.DRIVER_LOCK or requirements.get("python") != "3.12"
            or requirements.get("upstream_sha256") != setup.REQUIREMENTS_SHA256
            or not isinstance(requirements.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", requirements["sha256"])):
        return False
    if not isinstance(lock.get("driver_packages"), str) or not lock["driver_packages"].strip():
        return False
    if lock.get("opencode_version") != setup.OPENCODE_VERSION:
        return False
    images = lock.get("images")
    if not isinstance(images, dict):
        return False
    for name, prefix in (("evaluation", "agent-optimizer-cvdp"), ("agent", "agent-optimizer-opencode")):
        image = images.get(name)
        if (not isinstance(image, dict) or not isinstance(image.get("tag"), str)
                or not isinstance(image.get("id"), str)
                or not re.fullmatch(prefix + r":[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", image["tag"])
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", image["id"])):
            return False
    return True


def collect_checks(root: Path, platform: str | None = None, *, environment=None) -> list[dict]:
    root = Path(root)
    runner = Runner(root, "evaluation", environment)
    environment = runner.environment
    external = root / "external"
    docker = shutil.which("docker", path=environment.get("PATH", os.defpath)) is not None
    runner.add("docker.cli", docker and runner.run(["docker", "--version"]) is not None,
               "Docker CLI execution.", DOCKER_REMEDY)
    native = runner.probe("docker.daemon", ["docker", "version", "--format", "{{.Server.Os}}/{{.Server.Arch}}"],
                          "Docker daemon access.", DOCKER_REMEDY, requires=("docker.cli",))
    runner.probe("docker.compose", ["docker", "compose", "version"], "Docker Compose execution.",
                 DOCKER_REMEDY, requires=("docker.cli",))
    selected = native if platform is None else platform
    runner.add("docker.platform", isinstance(selected, str) and selected in PLATFORMS,
               "Selected Docker platform support.", "Use --platform linux/amd64 or --platform linux/arm64.",
               requires=("docker.daemon",) if platform is None else ())
    lock = None
    try:
        lock = json.loads((external / "environment-lock.json").read_text())
    except (OSError, ValueError):
        pass
    locked = runner.add("environment.lock", valid_lock(lock),
                        "Prepared environment lock schema and pinned inputs.", SETUP)
    runner.add("environment.platform", locked and lock["platform"] == selected,
               "Prepared lock matches selected platform.", "Use the prepared --platform or rerun setup for the intended platform.",
               requires=("environment.lock", "docker.platform"))
    runner.add("environment.ca", locked and lock.get("ca_bundle_sha256") == ca_fingerprint(environment),
               "Prepared images match the selected CA bundle.", SETUP, requires=("environment.lock",))

    # Source and data checks remain independent of a missing or malformed lock.
    git = shutil.which("git", path=environment.get("PATH", os.defpath)) is not None
    runner.add("source.git", git and runner.run(["git", "--version"]) is not None,
               "Git available for source inspection.", "Install Git and ensure git --version succeeds.")
    for name, (_, revision) in setup.REPOS.items():
        path = external / name
        exists = (path / ".git").exists()
        head = runner.run(["git", "rev-parse", "HEAD"], cwd=path) if exists and runner.ok("source.git") else None
        dirty = runner.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=path) if exists and runner.ok("source.git") else None
        runner.add(f"source.{name}", head == revision and dirty == "",
                   f"Pinned clean {name} checkout." if git or not exists else f"Cannot inspect {name} without Git.",
                   "Install Git; preserve any local changes, then run setup to prepare missing pinned sources.",
                   requires=("source.git",) if exists else ())
    for name, expected in setup.ASSETS.items():
        runner.add(f"data.{name}", digest(external / "cvdp-data" / setup.DATA_REVISION / name) == expected,
                   f"Verified cached {name} asset.", SETUP)

    python = external / "cvdp-venv/bin/python"
    version = runner.run([str(python), "-I", "-B", "-c",
                          "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"]
                         ) if python.is_file() else None
    runner.add("driver.python", version == "3.12", "CVDP driver Python 3.12.",
               "Preserve the existing external/cvdp-venv by moving it aside, then rerun setup.")
    requirements = digest(root / setup.DRIVER_LOCK)
    upstream = digest(external / "cvdp_benchmark/requirements.txt")
    runner.add("driver.lock", locked and requirements == lock["driver_requirements"]["sha256"]
               and upstream == setup.REQUIREMENTS_SHA256,
               "Driver requirements input and compiled lock hashes.", SETUP, requires=("environment.lock",))
    runner.add("driver.uv", shutil.which("uv", path=environment.get("PATH", os.defpath)) is not None and runner.run(["uv", "--version"]) is not None,
               "uv available for offline driver inventory.", SETUP)
    packages = runner.run(["uv", "--offline", "pip", "freeze", "--python", str(python)], timeout=30
                          ) if runner.ok("driver.python") and locked and runner.ok("driver.uv") else None
    runner.add("driver.packages", packages is not None and locked
               and sorted(packages.splitlines()) == sorted(lock["driver_packages"].splitlines()),
               "Installed driver packages match prepared lock (requires uv).", SETUP,
               requires=("driver.python", "environment.lock", "driver.uv"))
    runner.probe("driver.imports", [str(python), "-I", "-B", "-c",
                 "import yaml, requests, pydantic, openai, dotenv, psutil, nltk, tabulate, numpy, colorama, ruamel.yaml, tiktoken"],
                 "Driver dependencies import successfully.", SETUP, requires=("driver.python",))

    for name in ("evaluation", "agent"):
        dependencies = ("docker.daemon", "environment.lock", "environment.platform")
        identity_ok = False
        if all(runner.ok(d) for d in dependencies):
            image = lock["images"][name]
            output = runner.run(["docker", "image", "inspect", image["tag"]])
            try:
                info = json.loads(output)[0]
                identity_ok = (info["Id"] == image["id"]
                               and f"{info['Os']}/{info['Architecture']}" == selected)
            except (ValueError, TypeError, KeyError, IndexError):
                pass
        runner.add(f"image.{name}", identity_ok, f"Local {name} image identity and platform.", SETUP,
                   requires=dependencies)
        argv = []
        container = None
        if runner.ok(f"image.{name}"):
            container = "agent-opt-doctor-" + uuid.uuid4().hex
            argv = ["docker", "run", "--rm", "--name", container,
                    "--pull", "never", "--platform", selected,
                    "--network", "none", lock["images"][name]["id"]]
            if name == "evaluation":
                argv += ["python3", "-B", "-c", "import subprocess; [subprocess.run(cmd, check=True) for cmd in "
                         "[['yosys','-V'], ['iverilog','-V'], ['vvp','-V'], ['verilator','--version']]]"]
            else:
                argv += ["python3", "-B", "-c", "from pathlib import Path; import json, subprocess, sys; "
                         "p=Path('/opt/agent-optimizer'); json.loads((p/'compatible.json').read_text()); "
                         "assert (p/'endpoint-plugin.mjs').is_file(); subprocess.run(sys.argv[1:], check=True)",
                         "opencode", "--version"]
        try:
            runner.probe("tools.evaluation" if name == "evaluation" else "tools.opencode", argv,
                         "Actual simulator execution." if name == "evaluation" else "Actual pinned OpenCode execution.",
                         SETUP, requires=(f"image.{name}",), timeout=120,
                         expected=setup.OPENCODE_VERSION if name == "agent" else None)
        finally:
            if container is not None:
                runner.run(["docker", "rm", "--force", container], timeout=15)

    runner.area = "live"
    runner.add("live.key", bool(environment.get("MODEL_API_KEY", "").strip()),
               "Live credential presence (not authentication).", "Set MODEL_API_KEY in your environment.")
    try:
        ModelSettings.from_env({**environment, "MODEL_API_KEY": "configuration-check"})
        model_valid = True
    except (ConfigurationError, UnavailableError, ValueError):
        model_valid = False
    runner.add("live.model", model_valid, "OpenAI-compatible model configuration (not endpoint availability).",
               "Set exactly one of MODEL_ENDPOINT/MODEL_BASE_URL; optional MODEL_ID defaults to glm5.3-flash.")
    return runner.checks
