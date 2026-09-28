"""ACE/CVDP read-only checks, kept separate from the mutating setup entry points."""
import hashlib
import os
import re
import shutil
import uuid
from pathlib import Path
from types import ModuleType
import json

from agent_optimizer import diagnostics
from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.models import ModelSettings
from agent_optimizer.network import ca_fingerprint
from agent_optimizer.readiness import Runner

# This adapter also works when loaded by file path, without developer scripts.
_setup_path = Path(__file__).with_name("setup.py")
setup = ModuleType("ace_diagnostic_inputs")
setup.__file__ = str(_setup_path)
exec(compile(_setup_path.read_bytes(), str(_setup_path), "exec"), setup.__dict__)
SETUP = "Run sh scripts/bootstrap.sh setup (or python3 scripts/dev.py setup)."
PLATFORMS = {"linux/amd64", "linux/arm64"}
DOCKER_REMEDY = ("Mac: install/start Docker Desktop or Colima with Compose. "
                 "Ubuntu: install Docker Engine and docker-compose-plugin; start the daemon "
                 "and grant your user Docker socket access.")


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
    docker_cli = runner.run(["docker", "--version"], label="docker") if docker else None
    runner.add("docker.cli", docker_cli is not None and docker_cli.succeeded,
               "Docker CLI execution.", DOCKER_REMEDY,
               cause=(None if docker_cli is not None and docker_cli.succeeded else
                      diagnostics.summarize_failure(docker_cli, environment=environment)
                      if docker_cli is not None else "docker executable not found"),
               retry="docker --version")
    native = runner.probe("docker.daemon", ["docker", "version", "--format", "{{.Server.Os}}/{{.Server.Arch}}"],
                          "Docker daemon access.", DOCKER_REMEDY, requires=("docker.cli",),
                          retry="docker info")
    runner.probe("docker.compose", ["docker", "compose", "version"], "Docker Compose execution.",
                 DOCKER_REMEDY, requires=("docker.cli",), retry="docker compose version")
    native_platform = native.stdout.strip() if native is not None and native.succeeded else None
    selected = native_platform if platform is None else platform
    platform_ok = isinstance(selected, str) and selected in PLATFORMS
    runner.add("docker.platform", platform_ok,
               "Selected Docker platform support.", "Use --platform linux/amd64 or --platform linux/arm64.",
               requires=("docker.daemon",) if platform is None else (),
               cause=None if platform_ok else "Docker did not report a supported Linux platform",
               retry="docker info" if platform is None else
               "sh scripts/bootstrap.sh doctor --platform linux/amd64")
    lock = None
    lock_error = None
    try:
        lock = json.loads((external / "environment-lock.json").read_text())
    except (OSError, ValueError) as exc:
        lock_error = diagnostics.summarize_exception(exc, environment=environment)
    lock_valid = valid_lock(lock)
    locked = runner.add("environment.lock", lock_valid,
                        "Prepared environment lock schema and pinned inputs.", SETUP,
                        cause=None if lock_valid else lock_error or
                        "environment lock is missing or has invalid pinned inputs",
                        retry="sh scripts/bootstrap.sh setup")
    runner.add("environment.platform", locked and lock["platform"] == selected,
               "Prepared lock matches selected platform.",
               "Use the prepared --platform or rerun setup for the intended platform.",
               requires=("environment.lock", "docker.platform"),
               cause="prepared image platform differs from the selected Docker platform",
               retry="sh scripts/bootstrap.sh setup")
    runner.add("environment.ca", locked and lock.get("ca_bundle_sha256") == ca_fingerprint(environment),
               "Prepared images match the selected CA bundle.", SETUP,
               requires=("environment.lock",), cause="prepared images use a different CA bundle",
               retry="sh scripts/bootstrap.sh setup")

    # Source and data checks remain independent of a missing or malformed lock.
    git = shutil.which("git", path=environment.get("PATH", os.defpath)) is not None
    git_result = runner.run(["git", "--version"], label="git") if git else None
    runner.add("source.git", git_result is not None and git_result.succeeded,
               "Git available for source inspection.", "Install Git and ensure git --version succeeds.",
               cause=(None if git_result is not None and git_result.succeeded else
                      diagnostics.summarize_failure(git_result, environment=environment)
                      if git_result is not None else "git executable not found"),
               retry="git --version")
    for name, (_, revision) in setup.REPOS.items():
        path = external / name
        exists = (path / ".git").exists()
        head = runner.run(["git", "rev-parse", "HEAD"], cwd=path, label="git rev-parse") \
            if exists and runner.ok("source.git") else None
        dirty = runner.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=path,
                           label="git status") if exists and runner.ok("source.git") else None
        source_ok = (head is not None and head.succeeded and head.stdout.strip() == revision
                     and dirty is not None and dirty.succeeded and not dirty.stdout.strip())
        source_cause = None
        if not source_ok and exists and runner.ok("source.git"):
            failed = head if head is None or not head.succeeded else dirty
            source_cause = (diagnostics.summarize_failure(failed, environment=environment)
                            if failed is not None and not failed.succeeded else
                            "checkout revision differs from the pin or contains local changes")
        elif not source_ok and not exists:
            source_cause = "pinned checkout directory or .git metadata is missing"
        runner.add(f"source.{name}", source_ok,
                   f"Pinned clean {name} checkout." if git or not exists else f"Cannot inspect {name} without Git.",
                   "Install Git; preserve any local changes, then run setup to prepare missing pinned sources.",
                    requires=("source.git",) if exists else (), cause=source_cause,
                    retry="sh scripts/bootstrap.sh setup")
    for name, expected in setup.ASSETS.items():
        asset_ok = digest(external / "cvdp-data" / setup.DATA_REVISION / name) == expected
        runner.add(f"data.{name}", asset_ok, f"Verified cached {name} asset.", SETUP,
                   cause=None if asset_ok else "asset is missing or does not match its pinned SHA-256",
                   retry="sh scripts/bootstrap.sh setup")

    python = external / "cvdp-venv/bin/python"
    python_result = runner.run([str(python), "-I", "-B", "-c",
                                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                               label="driver Python") if python.is_file() else None
    version = python_result.stdout.strip() if python_result is not None and python_result.succeeded else None
    driver_python_ok = version == "3.12"
    driver_python_cause = (None if driver_python_ok else
                           diagnostics.summarize_failure(python_result, environment=environment)
                           if python_result is not None and not python_result.succeeded else
                           "CVDP driver Python 3.12 is missing or incompatible")
    runner.add("driver.python", driver_python_ok, "CVDP driver Python 3.12.",
               "Preserve the existing external/cvdp-venv by moving it aside, then rerun setup.",
               cause=driver_python_cause, retry="sh scripts/bootstrap.sh setup")
    requirements = digest(root / setup.DRIVER_LOCK)
    upstream = digest(external / "cvdp_benchmark/requirements.txt")
    driver_lock_ok = (locked and requirements == lock["driver_requirements"]["sha256"]
                      and upstream == setup.REQUIREMENTS_SHA256)
    runner.add("driver.lock", driver_lock_ok,
               "Driver requirements input and compiled lock hashes.", SETUP,
               requires=("environment.lock",),
               cause=None if driver_lock_ok else
               "driver requirements or compiled lock hash differs from its pin",
               retry="sh scripts/bootstrap.sh setup")
    uv_exists = shutil.which("uv", path=environment.get("PATH", os.defpath)) is not None
    uv_outcome = runner.run(["uv", "--version"], label="uv") if uv_exists else None
    uv_ok = uv_outcome is not None and uv_outcome.succeeded
    runner.add("driver.uv", uv_ok, "uv available for offline driver inventory.", SETUP,
               cause=(None if uv_ok else
                      diagnostics.summarize_failure(uv_outcome, environment=environment)
                      if uv_outcome is not None else "uv executable not found"),
               retry="sh scripts/bootstrap.sh setup")
    package_outcome = (runner.run(["uv", "--offline", "pip", "freeze", "--python", str(python)],
                                  timeout=30, label="uv pip")
                       if runner.ok("driver.python") and locked and runner.ok("driver.uv") else None)
    packages = (package_outcome.stdout.strip() if package_outcome is not None
                and package_outcome.succeeded else None)
    packages_ok = (packages is not None and locked
                   and sorted(packages.splitlines()) == sorted(lock["driver_packages"].splitlines()))
    packages_cause = (None if packages_ok or package_outcome is None else
                      diagnostics.summarize_failure(package_outcome, environment=environment)
                      if not package_outcome.succeeded else
                      "installed driver packages differ from the prepared lock")
    runner.add("driver.packages", packages_ok,
               "Installed driver packages match prepared lock (requires uv).", SETUP,
               requires=("driver.python", "environment.lock", "driver.uv"),
               cause=packages_cause, retry="sh scripts/bootstrap.sh setup")
    runner.probe("driver.imports", [str(python), "-I", "-B", "-c",
                  "import yaml, requests, pydantic, openai, dotenv, psutil, nltk, tabulate, numpy, colorama, ruamel.yaml, tiktoken"],
                  "Driver dependencies import successfully.", SETUP, requires=("driver.python",),
                  retry="sh scripts/bootstrap.sh setup")

    for name in ("evaluation", "agent"):
        dependencies = ("docker.daemon", "environment.lock", "environment.platform")
        identity_ok = False
        identity_outcome = None
        identity_cause = None
        if all(runner.ok(d) for d in dependencies):
            image = lock["images"][name]
            identity_outcome = runner.run(["docker", "image", "inspect", image["tag"]],
                                          label="docker image inspect")
            try:
                if not identity_outcome.succeeded:
                    raise ValueError("Image inspect command failed")
                info = json.loads(identity_outcome.stdout)[0]
                identity_ok = (info["Id"] == image["id"]
                               and f"{info['Os']}/{info['Architecture']}" == selected)
                if not identity_ok:
                    identity_cause = "local image identity or platform differs from the prepared lock"
            except (ValueError, TypeError, KeyError, IndexError):
                identity_cause = (diagnostics.summarize_failure(identity_outcome, environment=environment)
                                  if identity_outcome is not None and not identity_outcome.succeeded else
                                  "docker image inspect returned invalid image metadata")
        runner.add(f"image.{name}", identity_ok,
                   f"Local {name} image identity and platform.", SETUP, requires=dependencies,
                   cause=identity_cause, retry="sh scripts/bootstrap.sh setup")
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
                          expected=setup.OPENCODE_VERSION if name == "agent" else None,
                          retry="sh scripts/bootstrap.sh setup")
        finally:
            if container is not None:
                runner.run(["docker", "rm", "--force", container], timeout=15)

    runner.area = "live"
    key_present = bool(environment.get("AGENT_OPT_MODEL_API_KEY", "").strip())
    runner.add("live.key", key_present,
               "Live credential presence (not authentication).", "Set AGENT_OPT_MODEL_API_KEY in your environment.",
               cause=None if key_present else "model API key is not configured",
               retry="sh scripts/bootstrap.sh doctor --model")
    try:
        ModelSettings.from_env({**environment, "AGENT_OPT_MODEL_API_KEY": "configuration-check"})
        model_valid = True
        model_cause = None
    except (ConfigurationError, UnavailableError, ValueError) as exc:
        model_valid = False
        model_cause = diagnostics.summarize_exception(exc, environment=environment)
    runner.add("live.model", model_valid, "OpenAI-compatible model configuration (not endpoint availability).",
                "Set AGENT_OPT_MODEL_BASE_URL; optional AGENT_OPT_MODEL_ID defaults to glm5.3-flash.",
                cause=model_cause, retry="sh scripts/bootstrap.sh doctor --model")
    return runner.checks
