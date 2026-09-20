"""Prepare pinned upstream sources and reuse the official OSS simulation image."""
import json
import hashlib
import os
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.results import write_json
ROOT = Path(__file__).resolve().parents[3]
REPOS = {
    "ACE-RTL": ("https://github.com/NVlabs/ACE-RTL.git", "fead921f18bb57345b5a41ef93ba625be208e99c"),
    "cvdp_benchmark": ("https://github.com/NVlabs/cvdp_benchmark.git", "8e894cf74414ab1eaea1e2b4e80a02f123df07b6"),
}

DATA_REVISION = "5b807d945f6a99aa645f7e43a64a2115e281b4bf"
DATA_FILE = "cvdp_v1.1.0_nonagentic_code_generation_no_commercial.jsonl"
# Verified against fixed-revision HF Git blob OIDs before computing SHA-256.
# Metadata URL and original blob OIDs are recorded in docs/SOURCES.md.
ASSETS = {
    DATA_FILE: "cbcd81295561ebb16e4d857e096f4d9908d042c33aff3b58abf236e868411857",
    "LICENSE": "cedcd612607018ad841d87d7f1c877630778a50c71692610fe76acdc22700719",
    "NOTICE": "3d8753e57eab52910ccb61a1ee09113c43e9382ccd98d5860b5621aff8d932dd",
}
OPENCODE_VERSION = "1.18.31"
DRIVER_LOCK = "examples/ace-rtl/environment/requirements-cvdp-py312.txt"
REQUIREMENTS_SHA256 = "f79bf21e2e98b96016cf7992afb6a4df4bcfac64d07ff811195d22ddf0af6ad2"


def validate_platform(platform):
    if platform is None:
        try:
            platform = subprocess.check_output(
                ["docker", "version", "--format", "{{.Server.Os}}/{{.Server.Arch}}"],
                text=True, stderr=subprocess.PIPE, timeout=15,
            ).strip()
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise UnavailableError("Cannot detect Docker daemon native platform") from exc
    if platform not in {"linux/amd64", "linux/arm64"}:
        raise ConfigurationError(f"Unsupported platform {platform!r}; supported: linux/amd64 or linux/arm64")
    return platform


def validate_live():
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise UnavailableError("blocked_auth: OPENROUTER_API_KEY is absent")
    model = os.environ.get("AGENT_OPT_MODEL", "")
    if not re.fullmatch(r"openrouter/[A-Za-z0-9_.-]+/[A-Za-z0-9_.:-]+:free", model):
        raise ConfigurationError("blocked_model: set an explicit openrouter/vendor/model:free model")
    return model


def fetch_asset(url, destination, expected_sha256, *, offline=False):
    """Publish only verified complete bytes; never destroy an old cache on failure."""
    destination = Path(destination)
    if not url.startswith("https://"):
        raise ConfigurationError("Dataset downloads require HTTPS")
    if destination.is_symlink():
        raise ConfigurationError("Dataset cache must not be a symlink")
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == expected_sha256:
        return {"url": url, "sha256": expected_sha256, "bytes": destination.stat().st_size}
    if offline:
        raise UnavailableError(f"Offline asset missing or hash mismatch: {destination.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            digest = hashlib.sha256()
            with urllib.request.urlopen(url, timeout=120) as response:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    stream.write(chunk)
        if digest.hexdigest() != expected_sha256:
            raise ConfigurationError(f"Dataset SHA-256 mismatch: {destination.name}")
        temporary.replace(destination)
    except OSError as exc:
        raise UnavailableError(f"Dataset download failed: {destination.name} ({type(exc).__name__})") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"url": url, "sha256": expected_sha256, "bytes": destination.stat().st_size}


def prepare_data(external, *, offline=False):
    cache = Path(external) / "cvdp-data" / DATA_REVISION
    locks = {}
    for name, digest in ASSETS.items():
        url = f"https://huggingface.co/datasets/nvidia/cvdp-benchmark-dataset/resolve/{DATA_REVISION}/{name}"
        locks[name] = fetch_asset(url, cache / name, digest, offline=offline)
    return cache / DATA_FILE, {"revision": DATA_REVISION, "files": locks}

def run(args, cwd=ROOT, log=None):
    environment = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(ROOT / ".venv")}
    try:
        if log is None:
            subprocess.run(args, cwd=cwd, check=True, shell=False, env=environment)
            return
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w") as stream:
            stream.write(json.dumps(args) + "\n")
            stream.flush()
            result = subprocess.run(args, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, shell=False, env=environment)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise UnavailableError(f"Setup command unavailable/failed: {args[0]} ({type(exc).__name__})") from exc
    if result.returncode:
        raise UnavailableError(f"Command failed ({result.returncode}); see {log}")


def prepare_sources(external, *, offline=False):
    external.mkdir(parents=True, exist_ok=True)
    for name, (url, sha) in REPOS.items():
        path = external / name
        if not path.exists():
            if offline:
                raise UnavailableError(f"Offline source missing: {name}")
            run(["git", "clone", "--no-checkout", url, str(path)])
            run(["git", "checkout", "--detach", sha], path)
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=path, text=True).strip()
        if actual != sha or dirty:
            raise ConfigurationError(f"Existing checkout differs/dirty: {path}; preserved without modification")


def validate_driver_python(python):
    repair = (f"Existing environment is preserved. Move {python.parent.parent} aside and rerun "
              "scripts/dev.py setup to create it with uv and Python 3.12.")
    try:
        version = subprocess.check_output(
            [str(python), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            text=True, stderr=subprocess.PIPE, timeout=15,
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise UnavailableError(f"Cannot check CVDP driver Python at {python}. {repair}") from exc
    if version != "3.12":
        raise UnavailableError(f"CVDP driver requires Python 3.12, found {version} at {python}. {repair}")


def driver_requirements(external):
    upstream = external / "cvdp_benchmark/requirements.txt"
    if hashlib.sha256(upstream.read_bytes()).hexdigest() != REQUIREMENTS_SHA256:
        raise ConfigurationError("CVDP requirements input hash differs; review and recompile the driver lock")
    return {"path": DRIVER_LOCK, "sha256": hashlib.sha256((ROOT / DRIVER_LOCK).read_bytes()).hexdigest(),
            "upstream_sha256": REQUIREMENTS_SHA256, "python": "3.12"}


def driver_packages(external):
    try:
        return subprocess.check_output(
            ["uv", "--offline", "pip", "freeze", "--python", str(external / "cvdp-venv/bin/python")],
            text=True, stderr=subprocess.PIPE, timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise UnavailableError("Cannot inspect CVDP driver packages with uv") from exc


def validate_driver_lock(external, lock):
    if lock.get("driver_requirements") != driver_requirements(external):
        raise ConfigurationError("CVDP driver lock differs or is missing; rerun online setup")
    if sorted(driver_packages(external).splitlines()) != sorted(lock.get("driver_packages", "").splitlines()):
        raise ConfigurationError("CVDP driver packages differ from the prepared lock; rerun online setup")


def doctor(external, platform, eval_image, agent_image):
    """Actually execute tools; presence of tags or a valid plan is insufficient."""
    validate_platform(platform)
    commands = {
        "docker": ["docker", "version", "--format", "{{.Server.Version}}"],
        "compose": ["docker", "compose", "version"],
        "driver": [str(external / "cvdp-venv/bin/python"), "-c",
                   "import yaml, requests, pydantic, openai, dotenv, psutil, nltk, tabulate, numpy, colorama, ruamel.yaml, tiktoken; import sys; print(sys.version)"],
        "eval_tools": ["docker", "run", "--rm", "--pull", "never", "--platform", platform,
                       "--network", "none", eval_image, "python3", "-c",
                       "import subprocess; [subprocess.run(cmd, check=True) for cmd in [['yosys','-V'], ['iverilog','-V'], ['vvp','-V'], ['verilator','--version']]]"],
        "opencode": ["docker", "run", "--rm", "--pull", "never", "--platform", platform,
                     "--network", "none", agent_image, "opencode", "--version"],
    }
    checks = {}
    for name, argv in commands.items():
        try:
            if name == "driver":
                validate_driver_python(external / "cvdp-venv/bin/python")
            result = subprocess.run(argv, capture_output=True, text=True, timeout=120, shell=False)
            checks[name] = {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
        except UnavailableError as exc:
            checks[name] = {"returncode": None, "error": str(exc)}
        except (OSError, subprocess.TimeoutExpired) as exc:
            checks[name] = {"returncode": None, "error": type(exc).__name__}
    return {"ready": all(c["returncode"] == 0 for c in checks.values()), "platform": platform, "checks": checks}


def prepare_environment(*, offline=False, platform=None):
    platform = validate_platform(platform)
    external = ROOT / "external"
    venv = external / "cvdp-venv"
    if venv.exists():
        validate_driver_python(venv / "bin/python")
    logs = external / "setup-logs"
    logs.mkdir(parents=True, exist_ok=True)
    uv = ["uv", *(["--offline"] if offline else [])]
    run([*uv, "sync", "--frozen", "--python", "3.12", "--extra", "dev"], log=logs / "project-uv.log")
    prepare_sources(external, offline=offline)
    requirements = driver_requirements(external)
    previous_path = external / "environment-lock.json"
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    if offline:
        validate_driver_lock(external, previous)
    dataset, data_lock = prepare_data(external, offline=offline)
    if not venv.exists():
        run([*uv, "venv", "--python", "3.12", str(venv)], log=logs / "driver-venv.log")
        validate_driver_python(venv / "bin/python")
    cvdp = external / "cvdp_benchmark"
    run([*uv, "pip", "sync", "--python", str(venv / "bin/python"), str(ROOT / DRIVER_LOCK)], log=logs / "driver-uv.log")
    arch = platform.split("/")[1]
    images = {"evaluation": f"agent-optimizer-cvdp:8e894cf-{arch}",
              "agent": f"agent-optimizer-opencode:{OPENCODE_VERSION}-{arch}"}
    if offline and previous.get("platform") != platform:
        raise UnavailableError("Offline verified environment lock missing or platform differs")
    builds = {
        "evaluation": ["docker", "build", "--platform", platform, "-f", "docker/Dockerfile.sim", "-t", images["evaluation"], "."],
        "agent": ["docker", "build", "--platform", platform, "--build-arg", f"OPENCODE_VERSION={OPENCODE_VERSION}",
                  "-f", "Dockerfile", "-t", images["agent"], "."],
    }
    image_locks = {}
    for name, image in images.items():
        if not offline:
            run(builds[name], cvdp if name == "evaluation" else ROOT / "examples/rtl-debugger", logs / f"{name}-build.log")
        try:
            info = json.loads(subprocess.check_output(["docker", "image", "inspect", image], text=True))[0]
        except subprocess.CalledProcessError as exc:
            raise UnavailableError(f"Required image missing: {image}") from exc
        if f"{info['Os']}/{info['Architecture']}" != platform:
            raise ConfigurationError(f"Image platform mismatch: {image}")
        image_locks[name] = {"tag": image, "id": info["Id"]}
        if offline and previous.get("images", {}).get(name) != image_locks[name]:
            raise ConfigurationError(f"Offline image identity differs: {image}")
    capability = doctor(external, platform, images["evaluation"], images["agent"])
    write_json(logs / "doctor.json", capability)
    if not capability["ready"]:
        raise UnavailableError(f"Environment doctor failed; see {logs / 'doctor.json'}")
    freeze = driver_packages(external)
    lock = {"repos": REPOS, "dataset": data_lock, "platform": platform,
            "images": image_locks, "opencode_version": OPENCODE_VERSION, "driver_packages": freeze,
            "driver_requirements": requirements, "doctor": capability}
    write_json(previous_path, lock)
    return dataset, lock


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--platform", help="Default: Docker daemon native linux/amd64 or linux/arm64")
    args = parser.parse_args()
    prepare_environment(offline=args.offline, platform=args.platform)

if __name__ == "__main__":
    main()
