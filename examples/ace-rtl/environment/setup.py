"""Prepare pinned upstream sources and reuse the official OSS simulation image."""
import json
import hashlib
import os
import re
import subprocess
import tempfile
import ssl
import urllib.request
from pathlib import Path
from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.results import write_json
from agent_optimizer.network import host_environment, configured_build, ca_bundle, ca_fingerprint
from agent_optimizer.models import ModelSettings
from agent_optimizer.readiness import check
from agent_optimizer.terminal_report import PreparationStatus
from agent_optimizer.locale import human
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
    settings = ModelSettings.from_env()
    model = "compatible/" + settings.model
    os.environ.update(AGENT_OPT_MODEL_ID=settings.model, AGENT_OPT_MODEL=model,
                      OPENCODE_CONFIG="/opt/agent-optimizer/compatible.json")
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
            bundle = ca_bundle()
            tls = {"context": ssl.create_default_context(cafile=str(bundle))} if bundle else {}
            with urllib.request.urlopen(url, timeout=120, **tls) as response:
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
    environment = host_environment({**os.environ, "UV_PROJECT_ENVIRONMENT": str(ROOT / ".venv")})
    with configured_build(args, cwd, environment) as command:
        _run(command, cwd, log, environment)


def _run(args, cwd, log, environment):
    label = log.name if log else " ".join(args[:2])
    print(f"[setup] {label}: {human('starting')}; {human('log')}: {log or human('terminal')}", flush=True)
    with PreparationStatus(log.name if log else args[0], action="setup", subject="check"):
        try:
            if log is None:
                subprocess.run(args, cwd=cwd, check=True, shell=False, env=environment)
            else:
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open("w") as stream:
                    stream.write(json.dumps(args) + "\n")
                    stream.flush()
                    result = subprocess.run(args, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, shell=False, env=environment)
                if result.returncode:
                    raise UnavailableError(f"Command failed ({result.returncode}); see {log}")
        except (OSError, subprocess.CalledProcessError) as exc:
            raise UnavailableError(f"Setup {label} unavailable/failed: {args[0]} ({type(exc).__name__}); "
                                   f"see {log or 'terminal output'}; repair and rerun setup") from exc
    print(f"[setup] {label}: {human('complete')}", flush=True)


def prepare_sources(external, *, offline=False, names=None):
    external.mkdir(parents=True, exist_ok=True)
    for name in (REPOS if names is None else names):
        url, sha = REPOS[name]
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


def verified_sim_image(lock):
    """FROM needs a named image, not a bare local config ID; verify the local tag."""
    image = lock["images"]["evaluation"]
    tag = image["tag"]
    if (not re.fullmatch(r"agent-optimizer-cvdp:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag) or
            not re.fullmatch(r"sha256:[0-9a-f]{64}", image["id"])):
        raise ConfigurationError("Invalid prepared evaluation image tag or ID")
    try:
        info = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", tag], text=True, stderr=subprocess.PIPE, timeout=15,
        ))[0]
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise UnavailableError(f"Required local evaluation image missing/unavailable: {tag}") from exc
    if info["Id"] != image["id"] or f"{info['Os']}/{info['Architecture']}" != lock["platform"]:
        raise ConfigurationError(f"Evaluation image identity/platform differs from prepared lock: {tag}")
    return tag


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
        "provider_assets": ["docker", "run", "--rm", "--pull", "never", "--platform", platform,
                            "--network", "none", agent_image, "python3", "-c",
                            "from pathlib import Path; import json; p=Path('/opt/agent-optimizer'); "
                            "json.loads((p/'compatible.json').read_text()); assert (p/'endpoint-plugin.mjs').is_file()"],
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


def read_environment_lock(path):
    """Validate persisted inputs before consumers index them; never repair in place."""
    remedy = (f"Invalid environment lock at {path}; existing file preserved. "
              "Restore a known-good lock, or move this file aside and rerun "
              "sh scripts/bootstrap.sh setup online to verify and rebuild the lock.")
    try:
        lock = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ConfigurationError(remedy) from exc
    if not isinstance(lock, dict) or not isinstance(lock.get("platform"), str):
        raise ConfigurationError(remedy)
    images = lock.get("images")
    if not isinstance(images, dict):
        raise ConfigurationError(remedy)
    for name in ("evaluation", "agent"):
        image = images.get(name)
        if not isinstance(image, dict) or any(
                not isinstance(image.get(key), str) or not image[key] for key in ("tag", "id")):
            raise ConfigurationError(remedy)
    # Missing legacy driver metadata is diagnosed by validate_driver_lock; wrong types
    # must not reach its package string operations. Integrity comparisons remain there.
    for key, expected in (("driver_requirements", dict), ("driver_packages", str)):
        if key in lock and not isinstance(lock[key], expected):
            raise ConfigurationError(remedy)
    return lock


def evaluation_image(platform, *, selected=False):
    prefix = "agent-optimizer-cvdp-eval" if selected else "agent-optimizer-cvdp"
    return f"{prefix}:{REPOS['cvdp_benchmark'][1][:7]}-{platform.split('/')[1]}"


def inspect_image(tag, platform):
    try:
        info = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", tag], text=True, stderr=subprocess.PIPE, timeout=15))[0]
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, IndexError, KeyError) as exc:
        raise UnavailableError(f"Required image missing/unavailable: {tag}") from exc
    if (not isinstance(info, dict) or f"{info.get('Os')}/{info.get('Architecture')}" != platform
            or not isinstance(info.get("Id"), str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", info["Id"])):
        raise ConfigurationError(f"Evaluation image identity/platform invalid: {tag}")
    return {"tag": tag, "id": info["Id"]}


def verify_evaluation_tools(image_id, platform):
    """Check the pinned official image's actual simulator versions before trusting it."""
    for name, flag, version in (("yosys", "-V", r"\bYosys 0\.40\b"),
                                ("iverilog", "-V", r"\bIcarus Verilog version 13\b"),
                                ("vvp", "-V", r"\bIcarus Verilog runtime version 13\b"),
                                ("verilator", "--version", r"\bVerilator 5\.038\b")):
        argv = ["docker", "run", "--rm", "--pull", "never", "--platform", platform,
                "--network", "none", image_id, name, flag]
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=120, shell=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UnavailableError(f"CVDP simulator {name} unavailable; repair evaluation image") from exc
        if result.returncode or not re.search(version, result.stdout + result.stderr):
            raise UnavailableError(f"CVDP simulator {name} version differs; repair evaluation image")


def prepare_evaluation_environment(*, offline=False, platform=None, cache: Path):
    """Prepare CVDP scoring assets without touching the full ACE environment lock."""
    platform = validate_platform(platform)
    external = ROOT / "external"
    lock_path = Path(cache) / "evaluation-lock.json"
    previous = {}
    if lock_path.exists():
        try:
            previous = json.loads(lock_path.read_text())
        except (OSError, ValueError) as exc:
            raise ConfigurationError("Invalid CVDP evaluation lock; preserve and repair the provider cache") from exc
        if (not isinstance(previous, dict)
                or not isinstance(previous.get("dataset"), dict)
                or not isinstance(previous.get("driver_requirements"), dict)
                or not isinstance(previous.get("driver_packages"), str)
                or not isinstance(previous.get("images"), dict)
                or not isinstance(previous["images"].get("evaluation"), dict)
                or any(not isinstance(previous["images"]["evaluation"].get(key), str)
                       for key in ("tag", "id"))):
            raise ConfigurationError("Invalid CVDP evaluation lock; existing file preserved. "
                                     "Move it aside and rerun agent-opt datasets prepare cvdp")
    fingerprint = ca_fingerprint()
    if offline and (previous.get("platform") != platform or previous.get("ca_bundle_sha256") != fingerprint):
        raise UnavailableError("Offline CVDP evaluation lock missing or platform/CA differs; rerun online setup")
    venv = external / "cvdp-venv"
    if venv.exists():
        validate_driver_python(venv / "bin/python")
    logs = Path(cache) / "setup-logs"
    prepare_sources(external, offline=offline, names=("cvdp_benchmark",))
    requirements = driver_requirements(external)
    if offline:
        validate_driver_lock(external, previous)
    dataset, data_lock = prepare_data(external, offline=offline)
    if offline and previous.get("dataset") != data_lock:
        raise ConfigurationError("Offline CVDP dataset lock differs; rerun online setup")
    uv = ["uv", *(["--offline"] if offline else [])]
    if not venv.exists():
        run([*uv, "venv", "--python", "3.12", str(venv)], log=logs / "driver-venv.log")
        validate_driver_python(venv / "bin/python")
    run([*uv, "pip", "sync", "--python", str(venv / "bin/python"), str(ROOT / DRIVER_LOCK)],
        log=logs / "driver-uv.log")
    tag = evaluation_image(platform, selected=True)
    if not offline:
        run(["docker", "build", "--platform", platform, "-f", "docker/Dockerfile.sim", "-t", tag, "."],
            external / "cvdp_benchmark", logs / "evaluation-build.log")
    image = inspect_image(tag, platform)
    if offline and previous.get("images", {}).get("evaluation") != image:
        raise ConfigurationError("Offline evaluation image identity differs; rerun online setup")
    verify_evaluation_tools(image["id"], platform)
    packages = driver_packages(external)
    if offline and sorted(packages.splitlines()) != sorted(previous.get("driver_packages", "").splitlines()):
        raise ConfigurationError("Offline CVDP driver packages differ; rerun online setup")
    lock = {"repos": {"cvdp_benchmark": REPOS["cvdp_benchmark"]}, "dataset": data_lock,
            "platform": platform, "ca_bundle_sha256": fingerprint, "images": {"evaluation": image},
            "driver_requirements": requirements, "driver_packages": packages,
            "simulator_verified": True}
    write_json(lock_path, lock)
    return dataset, lock


def evaluation_checks(cache: Path) -> list[dict]:
    """Read-only inventory; probes cannot download, build, run containers or write bytecode."""
    cache = Path(cache)
    external = ROOT / "external"
    try:
        lock = json.loads((cache / "evaluation-lock.json").read_text())
    except (OSError, ValueError):
        lock = None
    valid = (isinstance(lock, dict) and isinstance(lock.get("dataset"), dict)
             and isinstance(lock.get("driver_requirements"), dict)
             and isinstance(lock.get("driver_packages"), str)
             and isinstance(lock.get("images"), dict)
             and isinstance(lock["images"].get("evaluation"), dict)
             and lock.get("repos") == {"cvdp_benchmark": list(REPOS["cvdp_benchmark"])}
             and lock.get("simulator_verified") is True
             and isinstance(lock.get("platform"), str)
             and lock.get("platform") in {"linux/amd64", "linux/arm64"}
             and lock["dataset"].get("revision") == DATA_REVISION
             and isinstance(lock["dataset"].get("files"), dict)
             and all(isinstance(lock["dataset"]["files"].get(name), dict) for name in ASSETS))
    rows = [check("dataset.cvdp.lock", "dataset", valid, "Pinned CVDP evaluation lock",
                  "Run agent-opt datasets prepare cvdp to repair the evaluation lock")]

    def probe(argv, *, cwd=None):
        try:
            return subprocess.check_output(argv, cwd=cwd, text=True, stderr=subprocess.PIPE, timeout=30,
                                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                                                "GIT_OPTIONAL_LOCKS": "0"}).strip()
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None

    source = external / "cvdp_benchmark"
    pinned = (source / ".git").exists() and probe(["git", "rev-parse", "HEAD"], cwd=source) == REPOS["cvdp_benchmark"][1]
    pinned = pinned and probe(["git", "status", "--porcelain", "--untracked-files=no"], cwd=source) == ""
    rows.append(check("dataset.cvdp.source", "dataset", pinned, "Pinned clean CVDP checkout",
                      "Install Git; preserve changes and rerun agent-opt datasets prepare cvdp"))
    for name, sha in ASSETS.items():
        path = external / "cvdp-data" / DATA_REVISION / name
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None
        except OSError:
            digest = None
        rows.append(check(f"dataset.cvdp.data.{name}", "dataset", valid and digest == sha
                          and lock["dataset"]["files"].get(name, {}).get("sha256") == sha,
                          "Pinned CVDP dataset asset", f"Restore verified {name} with agent-opt datasets prepare cvdp"))
    python = external / "cvdp-venv/bin/python"
    version = probe([str(python), "-I", "-B", "-c",
                     "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"]) if python.is_file() else None
    rows.append(check("dataset.cvdp.python", "dataset", version == "3.12", "CVDP driver Python 3.12",
                      "Repair the CVDP Python 3.12 driver and rerun agent-opt datasets prepare cvdp"))
    requirements = lock["driver_requirements"] if valid else {}
    try:
        compiled = hashlib.sha256((ROOT / DRIVER_LOCK).read_bytes()).hexdigest()
        upstream = hashlib.sha256((source / "requirements.txt").read_bytes()).hexdigest()
    except OSError:
        compiled = upstream = None
    rows.append(check("dataset.cvdp.driver.lock", "dataset", valid and
                      requirements == {"path": DRIVER_LOCK, "sha256": compiled,
                                       "upstream_sha256": REQUIREMENTS_SHA256, "python": "3.12"}
                      and upstream == REQUIREMENTS_SHA256, "Pinned driver requirements",
                      "Restore the compiled driver lock and pinned source; rerun agent-opt datasets prepare cvdp"))
    packages = probe(["uv", "--offline", "pip", "freeze", "--python", str(python)]) if version == "3.12" else None
    rows.append(check("dataset.cvdp.driver.packages", "dataset", valid and packages is not None and
                      sorted(packages.splitlines()) == sorted(lock["driver_packages"].splitlines()),
                      "Prepared driver packages", "Install uv and rerun agent-opt datasets prepare cvdp"))
    image = lock["images"]["evaluation"] if valid else {}
    tag, identity = image.get("tag"), image.get("id")
    platform = lock["platform"] if valid else None
    proper = (isinstance(tag, str) and platform is not None and tag == evaluation_image(platform, selected=True)
              and isinstance(identity, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", identity)
              and lock.get("ca_bundle_sha256") == ca_fingerprint())
    info = None
    if proper:
        try:
            info = json.loads(probe(["docker", "image", "inspect", tag]))[0]
        except (ValueError, TypeError, IndexError, KeyError):
            pass
    rows.append(check("dataset.cvdp.image", "dataset", proper and isinstance(info, dict)
                      and info.get("Id") == identity
                      and f"{info.get('Os')}/{info.get('Architecture')}" == platform,
                      "Verified official CVDP simulator image identity and platform",
                      "Start Docker and rerun agent-opt datasets prepare cvdp for this platform/CA bundle"))
    return rows


def prepare_environment(*, offline=False, platform=None):
    platform = validate_platform(platform)
    external = ROOT / "external"
    fingerprint = ca_fingerprint()
    previous_path = external / "environment-lock.json"
    previous = read_environment_lock(previous_path) if previous_path.exists() else {}
    if offline and previous.get("ca_bundle_sha256") != fingerprint:
        raise ConfigurationError("CA bundle differs from prepared images; rerun online setup")
    venv = external / "cvdp-venv"
    if venv.exists():
        validate_driver_python(venv / "bin/python")
    logs = external / "setup-logs"
    logs.mkdir(parents=True, exist_ok=True)
    uv = ["uv", *(["--offline"] if offline else [])]
    # The shell bootstrap owns core sync and preserves the project's Python version.
    print(f"[setup] {human('pinned sources')}: {human('starting')}; {human('checkout')}: {external}", flush=True)
    prepare_sources(external, offline=offline)
    print(f"[setup] {human('pinned sources')}: {human('complete')}", flush=True)
    requirements = driver_requirements(external)
    if offline:
        validate_driver_lock(external, previous)
    print(f"[setup] {human('verified dataset')}: {human('starting')}; {human('cache')}: {external / 'cvdp-data'}", flush=True)
    with PreparationStatus("verified-data", action="setup", subject="check"):
        dataset, data_lock = prepare_data(external, offline=offline)
    print(f"[setup] {human('verified dataset')}: {human('complete')}", flush=True)
    if not venv.exists():
        run([*uv, "venv", "--python", "3.12", str(venv)], log=logs / "driver-venv.log")
        validate_driver_python(venv / "bin/python")
    cvdp = external / "cvdp_benchmark"
    run([*uv, "pip", "sync", "--python", str(venv / "bin/python"), str(ROOT / DRIVER_LOCK)], log=logs / "driver-uv.log")
    arch = platform.split("/")[1]
    images = {"evaluation": evaluation_image(platform),
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
        print(f"[setup] {human(name + ' image')}: {human('verify cached' if offline else 'build')}; "
              f"{human('log')}: {logs / (name + '-build.log')}", flush=True)
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
        print(f"[setup] {human(name + ' image')}: {human('complete')}", flush=True)
    print(f"[setup] {human('example tool checks')}: {human('starting')}; {human('log')}: {logs / 'doctor.json'}", flush=True)
    with PreparationStatus("example-tools", action="setup", subject="check"):
        capability = doctor(external, platform, images["evaluation"], images["agent"])
        write_json(logs / "doctor.json", capability)
        if not capability["ready"]:
            raise UnavailableError(f"Environment doctor failed; see {logs / 'doctor.json'}")
    print(f"[setup] {human('example tool checks')}: {human('complete')}", flush=True)
    freeze = driver_packages(external)
    lock = {"repos": REPOS, "dataset": data_lock, "platform": platform, "ca_bundle_sha256": fingerprint,
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
