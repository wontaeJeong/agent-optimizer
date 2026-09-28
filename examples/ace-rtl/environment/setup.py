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
from agent_optimizer import diagnostics
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
            outcome = _outcome_from_exception("docker version", exc)
            cause = diagnostics.summarize_failure(outcome, environment=os.environ)
            raise _attach_setup_failure(
                "Docker platform detection", cause, None,
                fix="Start Docker and confirm daemon/socket access.",
                retry="docker info",
            ) from None
    if platform not in {"linux/amd64", "linux/arm64"}:
        raise ConfigurationError(f"Unsupported platform {platform!r}; supported: linux/amd64 or linux/arm64")
    return platform


def validate_live():
    settings = ModelSettings.from_env()
    model = "compatible/" + settings.model
    os.environ.update(AGENT_OPT_MODEL_ID=settings.model, AGENT_OPT_MODEL=model,
                      OPENCODE_CONFIG="/opt/agent-optimizer/compatible.json")
    return model


def fetch_asset(url, destination, expected_sha256, *, offline=False,
                retry="sh scripts/bootstrap.sh setup"):
    """Publish only verified complete bytes; never destroy an old cache on failure."""
    destination = Path(destination)
    if not url.startswith("https://"):
        raise ConfigurationError("Dataset downloads require HTTPS")
    if destination.is_symlink():
        raise ConfigurationError("Dataset cache must not be a symlink")
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == expected_sha256:
        return {"url": url, "sha256": expected_sha256, "bytes": destination.stat().st_size}
    if offline:
        raise _attach_setup_failure(
            "dataset download", "offline cache miss: asset is missing or has a hash mismatch", None,
            fix="Prepare the pinned dataset asset while online before using offline mode.",
            retry=retry,
        ) from None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        cause = diagnostics.summarize_exception(exc, environment=os.environ)
        raise _attach_setup_failure(
            "dataset cache", cause, None,
            fix="Check write permission for the selected dataset cache directory.",
            retry=retry,
        ) from None
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
            error = ConfigurationError(f"Dataset SHA-256 mismatch: {destination.name}")
            error.failure_diagnostic = {
                "stage": "dataset download",
                "cause": "downloaded asset did not match its pinned SHA-256",
                "log": None,
                "fix": "Check the network cache/source and preserve the expected asset pin.",
                "retry": retry,
            }
            raise error from None
        temporary.replace(destination)
    except OSError as exc:
        outcome = diagnostics.CommandOutcome("dataset download", 1, stderr=str(exc))
        cause = diagnostics.summarize_failure(outcome, environment=os.environ)
        raise _attach_setup_failure(
            "dataset download", cause, None,
            fix="Check DNS, proxy, CA trust, and access to the pinned dataset source.",
            retry=retry,
        ) from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"url": url, "sha256": expected_sha256, "bytes": destination.stat().st_size}


def prepare_data(external, *, offline=False, retry="sh scripts/bootstrap.sh setup"):
    cache = Path(external) / "cvdp-data" / DATA_REVISION
    locks = {}
    for name, digest in ASSETS.items():
        url = f"https://huggingface.co/datasets/nvidia/cvdp-benchmark-dataset/resolve/{DATA_REVISION}/{name}"
        locks[name] = fetch_asset(url, cache / name, digest, offline=offline, retry=retry)
    return cache / DATA_FILE, {"revision": DATA_REVISION, "files": locks}

def run(args, cwd=ROOT, log=None):
    environment = host_environment({**os.environ, "UV_PROJECT_ENVIRONMENT": str(ROOT / ".venv")})
    with configured_build(args, cwd, environment) as command:
        _run(command, cwd, log, environment)


def _command_label(args):
    executable = Path(str(args[0])).name if args else "command"
    safe_subcommands = {
        "docker": {"build", "image", "run", "info", "version", "compose"},
        "git": {"clone", "checkout", "rev-parse", "status"},
        "uv": {"venv", "pip", "sync", "--version"},
    }
    if len(args) > 1 and args[1] in safe_subcommands.get(executable, set()):
        return f"{executable} {args[1]}"
    return executable


def _captured_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) else ""


def _outcome_from_exception(command, exc):
    timed_out = isinstance(exc, subprocess.TimeoutExpired)
    return diagnostics.CommandOutcome(
        command,
        exc.returncode if isinstance(exc, subprocess.CalledProcessError) else None,
        _captured_text(getattr(exc, "output", None)),
        _captured_text(getattr(exc, "stderr", None)),
        timed_out=timed_out,
        error_kind=("missing" if isinstance(exc, FileNotFoundError) else
                    "permission" if isinstance(exc, PermissionError) else
                    "timeout" if timed_out else type(exc).__name__.lower()),
    )


def _setup_stage(label):
    name = Path(label).name
    if name.startswith("source-") and name.endswith(".log"):
        detail = name[len("source-"):-len(".log")]
        for action in ("clone", "checkout"):
            suffix = "-" + action
            if detail.endswith(suffix):
                return f"{detail[:-len(suffix)]} source {action}"
    return {
        "bootstrap-uv.log": "uv installer",
        "project-uv.log": "project dependency sync",
        "driver-venv.log": "driver virtual environment",
        "driver-uv.log": "driver dependency sync",
        "evaluation-build.log": "evaluation image",
        "agent-build.log": "agent image",
        "doctor.json": "example tool verification",
    }.get(Path(label).name, label)


def _attach_setup_failure(stage, cause, log, *, fix, retry, error_type=UnavailableError, message=None):
    diagnostic = {"stage": stage, "cause": cause,
                  "log": str(log) if log is not None else None,
                  "fix": fix, "retry": retry}
    error = error_type(message or cause)
    error.failure_diagnostic = diagnostic
    return error


def _run(args, cwd, log, environment):
    label = log.name if log else " ".join(args[:2])
    stage = _setup_stage(label)
    print(f"[setup] {label}: {human('starting')}; {human('log')}: {log or human('terminal')}", flush=True)
    with PreparationStatus(log.name if log else args[0], action="setup", subject="check"):
        try:
            if log is None:
                result = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                                        shell=False, env=environment)
            else:
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open("w", encoding="utf-8") as stream:
                    stream.write(json.dumps(args) + "\n")
                    stream.flush()
                    result = subprocess.run(args, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                            shell=False, env=environment)
        except (OSError, subprocess.SubprocessError) as exc:
            outcome = diagnostics.CommandOutcome(
                _command_label(args), None,
                error_kind=("missing" if isinstance(exc, FileNotFoundError) else
                            "permission" if isinstance(exc, PermissionError) else
                            "timeout" if isinstance(exc, subprocess.TimeoutExpired) else
                            type(exc).__name__.lower()),
            )
            cause = diagnostics.summarize_failure(outcome, environment=environment)
            raise _attach_setup_failure(
                stage, cause, log,
                fix="Repair the command, access, or selected environment input.",
                retry="sh scripts/bootstrap.sh setup",
            ) from None
        if result.returncode:
            log_lines = diagnostics.summarize_log(log, environment=environment) if log else []
            outcome = diagnostics.CommandOutcome(
                _command_label(args), result.returncode,
                stdout="" if log else str(result.stdout or ""),
                stderr="\n".join(log_lines) if log else str(result.stderr or ""),
            )
            cause = diagnostics.summarize_failure(outcome, environment=environment)
            if log_lines and cause.endswith("non-zero exit code"):
                cause += ": " + log_lines[-1]
            raise _attach_setup_failure(
                stage, cause, log,
                fix="Repair the reported tool, network, permission, or pinned input issue.",
                retry="sh scripts/bootstrap.sh setup",
            ) from None
    print(f"[setup] {label}: {human('complete')}", flush=True)


def prepare_sources(external, *, offline=False, names=None):
    external.mkdir(parents=True, exist_ok=True)
    logs = external / "setup-logs"
    for name in (REPOS if names is None else names):
        url, sha = REPOS[name]
        path = external / name
        if not path.exists():
            if offline:
                raise _attach_setup_failure(
                    f"{name} source checkout", f"{name} pinned source is missing from offline cache", None,
                    fix="Prepare the pinned source checkout while online before using offline mode.",
                    retry="sh scripts/bootstrap.sh setup",
                    message=f"Offline source missing: {name}",
                ) from None
            run(["git", "clone", "--no-checkout", url, str(path)],
                log=logs / f"source-{name}-clone.log")
            run(["git", "checkout", "--detach", sha], path,
                log=logs / f"source-{name}-checkout.log")
        revision_command = ["git", "rev-parse", "HEAD"]
        status_command = ["git", "status", "--porcelain", "--untracked-files=no"]
        command = revision_command
        try:
            actual = subprocess.check_output(
                command, cwd=path, text=True,
                stderr=subprocess.PIPE, timeout=30,
            ).strip()
            command = status_command
            dirty = subprocess.check_output(
                command, cwd=path,
                text=True, stderr=subprocess.PIPE, timeout=30,
            ).strip()
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            cause = diagnostics.summarize_failure(
                _outcome_from_exception(_command_label(command), exc), environment=os.environ,
            )
            raise _attach_setup_failure(
                f"{name} source verification", cause, None,
                fix="Restore the pinned checkout or move the preserved source directory aside.",
                retry="sh scripts/bootstrap.sh setup",
            ) from None
        if actual != sha or dirty:
            message = f"Existing checkout differs/dirty: {path}; preserved without modification"
            fix = ("Restore the pinned source or move it aside, then run online setup before retrying offline."
                   if offline else
                   "Restore the pinned checkout or move the preserved source directory aside.")
            raise _attach_setup_failure(
                f"{name} source verification", "Pinned source checkout differs or has local changes", None,
                fix=fix,
                retry="sh scripts/bootstrap.sh setup", error_type=ConfigurationError,
                message=message,
            ) from None


def validate_driver_python(python):
    repair = (f"Existing environment is preserved. Move {python.parent.parent} aside and rerun "
              "scripts/dev.py setup to create it with uv and Python 3.12.")
    try:
        version = subprocess.check_output(
            [str(python), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            text=True, stderr=subprocess.PIPE, timeout=15,
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        cause = diagnostics.summarize_failure(
            _outcome_from_exception("driver Python", exc), environment=os.environ)
        raise _attach_setup_failure("driver Python validation", cause, None,
                                    fix=repair, retry="sh scripts/bootstrap.sh setup",
                                    message=f"{cause}. {repair}") from None
    if version != "3.12":
        safe_version = diagnostics.sanitize_text(version, os.environ)[:32] or "unknown"
        cause = f"CVDP driver requires Python 3.12, found {safe_version}"
        raise _attach_setup_failure("driver Python validation", cause, None,
                                    fix=repair, retry="sh scripts/bootstrap.sh setup",
                                    message=f"{cause}. {repair}") from None


def driver_requirements(external):
    upstream = external / "cvdp_benchmark/requirements.txt"
    if hashlib.sha256(upstream.read_bytes()).hexdigest() != REQUIREMENTS_SHA256:
        raise _attach_setup_failure(
            "driver requirements lock", "CVDP requirements input hash differs from the pinned lock", None,
            fix="Review the upstream requirements and recompile the pinned CVDP driver lock.",
            retry="sh scripts/bootstrap.sh setup", error_type=ConfigurationError,
            message="CVDP requirements input hash differs; review and recompile the driver lock",
        ) from None
    return {"path": DRIVER_LOCK, "sha256": hashlib.sha256((ROOT / DRIVER_LOCK).read_bytes()).hexdigest(),
            "upstream_sha256": REQUIREMENTS_SHA256, "python": "3.12"}


def driver_packages(external):
    try:
        return subprocess.check_output(
            ["uv", "--offline", "pip", "freeze", "--python", str(external / "cvdp-venv/bin/python")],
            text=True, stderr=subprocess.PIPE, timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        cause = diagnostics.summarize_failure(
            _outcome_from_exception("uv pip freeze", exc), environment=os.environ)
        raise _attach_setup_failure(
            "driver package inspection", cause, None,
            fix="Confirm the CVDP driver environment and uv cache are available.",
            retry="sh scripts/bootstrap.sh setup",
        ) from None


def validate_driver_lock(external, lock):
    if lock.get("driver_requirements") != driver_requirements(external):
        raise _attach_setup_failure(
            "driver lock validation", "CVDP driver lock differs or is missing", None,
            fix="Restore the pinned CVDP driver lock with online setup.",
            retry="sh scripts/bootstrap.sh setup", error_type=ConfigurationError,
            message="CVDP driver lock differs or is missing; rerun online setup",
        ) from None
    if sorted(driver_packages(external).splitlines()) != sorted(lock.get("driver_packages", "").splitlines()):
        raise _attach_setup_failure(
            "driver lock validation", "Installed CVDP driver packages differ from the prepared lock", None,
            fix="Restore the prepared CVDP driver packages with online setup.",
            retry="sh scripts/bootstrap.sh setup", error_type=ConfigurationError,
            message="CVDP driver packages differ from the prepared lock; rerun online setup",
        ) from None


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
        cause = diagnostics.summarize_failure(
            _outcome_from_exception("docker image inspect", exc), environment=os.environ)
        raise _attach_setup_failure(
            "evaluation image inspection", cause, None,
            fix="Check Docker daemon access and rebuild the pinned evaluation image.",
            retry="sh scripts/bootstrap.sh setup",
        ) from None
    except (ValueError, IndexError, KeyError, TypeError) as exc:
        raise _attach_setup_failure(
            "evaluation image inspection", "docker image inspect returned invalid metadata", None,
            fix="Rebuild the pinned evaluation image and preserve the expected platform.",
            retry="sh scripts/bootstrap.sh setup",
        ) from None
    if info["Id"] != image["id"] or f"{info['Os']}/{info['Architecture']}" != lock["platform"]:
        raise _attach_setup_failure(
            "evaluation image inspection", "local image identity or platform differs from prepared lock",
            None, fix="Rebuild the pinned evaluation image for the locked platform.",
            retry="sh scripts/bootstrap.sh setup", error_type=ConfigurationError,
        )
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
            checks[name] = {"returncode": result.returncode}
            if result.returncode:
                cause = diagnostics.summarize_failure(
                    diagnostics.CommandOutcome(_command_label(argv), result.returncode,
                                               result.stdout or "", result.stderr or ""),
                    environment=os.environ,
                )
                checks[name].update(cause=cause, error=cause)
        except UnavailableError as exc:
            cause = diagnostics.summarize_exception(exc, environment=os.environ)
            checks[name] = {"returncode": None, "cause": cause, "error": cause}
        except (OSError, subprocess.TimeoutExpired) as exc:
            outcome = diagnostics.CommandOutcome(
                _command_label(argv), None,
                _captured_text(exc.output) if isinstance(exc, subprocess.TimeoutExpired) else "",
                _captured_text(exc.stderr) if isinstance(exc, subprocess.TimeoutExpired) else "",
                timed_out=isinstance(exc, subprocess.TimeoutExpired),
                error_kind=("missing" if isinstance(exc, FileNotFoundError) else
                            "permission" if isinstance(exc, PermissionError) else
                            "timeout" if isinstance(exc, subprocess.TimeoutExpired) else
                            type(exc).__name__.lower()),
            )
            cause = diagnostics.summarize_failure(outcome, environment=os.environ)
            checks[name] = {"returncode": None, "cause": cause, "error": cause}
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


def inspect_image(tag, platform, *, offline=False):
    offline_fix = (" Run online CVDP setup to rebuild and pin the selected image before offline retry."
                   if offline else "")
    try:
        info = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", tag], text=True, stderr=subprocess.PIPE, timeout=15))[0]
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        cause = diagnostics.summarize_failure(
            _outcome_from_exception("docker image inspect", exc), environment=os.environ)
        raise _attach_setup_failure(
            "evaluation image inspection", cause, None,
            fix="Check Docker daemon access and rebuild the selected CVDP image." + offline_fix,
            retry="agent-opt datasets prepare cvdp",
        ) from None
    except (ValueError, IndexError, KeyError, TypeError):
        raise _attach_setup_failure(
            "evaluation image inspection", "docker image inspect returned invalid metadata", None,
            fix="Rebuild the selected CVDP image and preserve the expected platform." + offline_fix,
            retry="agent-opt datasets prepare cvdp",
        ) from None
    if (not isinstance(info, dict) or f"{info.get('Os')}/{info.get('Architecture')}" != platform
            or not isinstance(info.get("Id"), str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", info["Id"])):
        raise _attach_setup_failure(
            "evaluation image inspection",
            "evaluation image identity or platform differs from the selected platform", None,
            fix="Rebuild the selected CVDP image for the expected platform." + offline_fix,
            retry="agent-opt datasets prepare cvdp", error_type=ConfigurationError,
            message=f"Evaluation image identity/platform invalid: {tag}",
        ) from None
    return {"tag": tag, "id": info["Id"]}


def verify_evaluation_tools(image_id, platform, *, offline=False):
    """Check the pinned official image's actual simulator versions before trusting it."""
    offline_fix = (" Run online CVDP setup to rebuild and pin the evaluation image before offline retry."
                   if offline else "")
    for name, flag, version in (("yosys", "-V", r"\bYosys 0\.40\b"),
                                ("iverilog", "-V", r"\bIcarus Verilog version 13\b"),
                                ("vvp", "-V", r"\bIcarus Verilog runtime version 13\b"),
                                ("verilator", "--version", r"\bVerilator 5\.038\b")):
        argv = ["docker", "run", "--rm", "--pull", "never", "--platform", platform,
                "--network", "none", image_id, name, flag]
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=120, shell=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            cause = diagnostics.summarize_failure(
                _outcome_from_exception(f"docker run {name}", exc), environment=os.environ)
            raise _attach_setup_failure(
                f"{name} simulator verification", cause, None,
                fix="Check Docker daemon access and rebuild the pinned evaluation image." + offline_fix,
                retry="sh scripts/bootstrap.sh setup",
            ) from None
        if result.returncode or not re.search(version, result.stdout + result.stderr):
            cause = (diagnostics.summarize_failure(
                diagnostics.CommandOutcome(f"docker run {name}", result.returncode,
                                           result.stdout or "", result.stderr or ""),
                environment=os.environ) if result.returncode else
                f"{name} simulator version differs from its pin")
            raise _attach_setup_failure(
                f"{name} simulator verification", cause, None,
                fix="Rebuild the pinned evaluation image and verify its simulator versions." + offline_fix,
                retry="sh scripts/bootstrap.sh setup",
            ) from None


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
        message = "Offline CVDP evaluation lock missing or platform/CA differs; rerun online setup"
        raise _attach_setup_failure(
            "CVDP evaluation lock validation", "Offline CVDP lock is missing or platform/CA differs",
            None, fix="Run online CVDP setup with the selected platform and CA bundle before offline retry.",
            retry="agent-opt datasets prepare cvdp", message=message,
        ) from None
    venv = external / "cvdp-venv"
    if venv.exists():
        validate_driver_python(venv / "bin/python")
    logs = Path(cache) / "setup-logs"
    prepare_sources(external, offline=offline, names=("cvdp_benchmark",))
    requirements = driver_requirements(external)
    if offline:
        validate_driver_lock(external, previous)
    dataset, data_lock = prepare_data(
        external, offline=offline, retry="agent-opt datasets prepare cvdp")
    if offline and previous.get("dataset") != data_lock:
        raise _attach_setup_failure(
            "CVDP dataset lock validation", "Offline CVDP dataset lock differs from the prepared cache",
            None, fix="Run online CVDP setup to restore the pinned dataset lock.",
            retry="agent-opt datasets prepare cvdp", error_type=ConfigurationError,
            message="Offline CVDP dataset lock differs; rerun online setup",
        ) from None
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
    image = inspect_image(tag, platform, offline=offline)
    if offline and previous.get("images", {}).get("evaluation") != image:
        raise _attach_setup_failure(
            "CVDP evaluation image identity", "Offline evaluation image identity differs from the lock",
            logs / "evaluation-build.log",
            fix="Run online CVDP setup to rebuild and pin the evaluation image for this platform.",
            retry="agent-opt datasets prepare cvdp", error_type=ConfigurationError,
            message="Offline evaluation image identity differs; rerun online setup",
        ) from None
    verify_evaluation_tools(image["id"], platform, offline=offline)
    packages = driver_packages(external)
    if offline and sorted(packages.splitlines()) != sorted(previous.get("driver_packages", "").splitlines()):
        raise _attach_setup_failure(
            "CVDP driver package lock", "Offline CVDP driver packages differ from the prepared lock",
            logs / "driver-uv.log",
            fix="Run online CVDP setup to restore the pinned driver packages.",
            retry="agent-opt datasets prepare cvdp", error_type=ConfigurationError,
            message="Offline CVDP driver packages differ; rerun online setup",
        ) from None
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
        lock_error = None
    except (OSError, ValueError) as exc:
        lock = None
        lock_error = diagnostics.summarize_exception(exc, environment=os.environ)
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
                  "Run agent-opt datasets prepare cvdp to repair the evaluation lock",
                  cause=None if valid else lock_error or "CVDP evaluation lock is invalid or incomplete",
                  retry="agent-opt datasets prepare cvdp")]

    def probe(argv, *, cwd=None):
        try:
            value = subprocess.check_output(
                argv, cwd=cwd, text=True, stderr=subprocess.PIPE, timeout=30,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "GIT_OPTIONAL_LOCKS": "0"},
            ).strip()
            return value, None
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            cause = diagnostics.summarize_failure(
                _outcome_from_exception(_command_label(argv), exc), environment=os.environ)
            return None, cause

    source = external / "cvdp_benchmark"
    source_exists = (source / ".git").exists()
    head, head_error = (probe(["git", "rev-parse", "HEAD"], cwd=source)
                        if source_exists else (None, None))
    dirty, dirty_error = (probe(["git", "status", "--porcelain", "--untracked-files=no"], cwd=source)
                          if source_exists and head == REPOS["cvdp_benchmark"][1] else (None, None))
    pinned = source_exists and head == REPOS["cvdp_benchmark"][1] and dirty == ""
    source_cause = (None if pinned else head_error or dirty_error or
                    "pinned clean CVDP checkout is missing, changed, or dirty")
    rows.append(check("dataset.cvdp.source", "dataset", pinned, "Pinned clean CVDP checkout",
                      "Install Git; preserve changes and rerun agent-opt datasets prepare cvdp",
                      cause=source_cause, retry="agent-opt datasets prepare cvdp"))
    for name, sha in ASSETS.items():
        path = external / "cvdp-data" / DATA_REVISION / name
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None
        except OSError:
            digest = None
        asset_ok = (valid and digest == sha
                    and lock["dataset"]["files"].get(name, {}).get("sha256") == sha)
        rows.append(check(f"dataset.cvdp.data.{name}", "dataset", asset_ok,
                          "Pinned CVDP dataset asset",
                          f"Restore verified {name} with agent-opt datasets prepare cvdp",
                          cause=None if asset_ok else "asset is missing or does not match its pinned SHA-256",
                          retry="agent-opt datasets prepare cvdp"))
    python = external / "cvdp-venv/bin/python"
    version, python_error = (probe([str(python), "-I", "-B", "-c",
                                    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"])
                             if python.is_file() else (None, None))
    python_ok = version == "3.12"
    rows.append(check("dataset.cvdp.python", "dataset", python_ok, "CVDP driver Python 3.12",
                      "Repair the CVDP Python 3.12 driver and rerun agent-opt datasets prepare cvdp",
                      cause=None if python_ok else python_error or
                      "CVDP driver Python 3.12 is missing or incompatible",
                      retry="agent-opt datasets prepare cvdp"))
    requirements = lock["driver_requirements"] if valid else {}
    try:
        compiled = hashlib.sha256((ROOT / DRIVER_LOCK).read_bytes()).hexdigest()
        upstream = hashlib.sha256((source / "requirements.txt").read_bytes()).hexdigest()
    except OSError:
        compiled = upstream = None
    driver_lock_ok = (valid and requirements == {"path": DRIVER_LOCK, "sha256": compiled,
                                                 "upstream_sha256": REQUIREMENTS_SHA256,
                                                 "python": "3.12"}
                      and upstream == REQUIREMENTS_SHA256)
    rows.append(check("dataset.cvdp.driver.lock", "dataset", driver_lock_ok,
                      "Pinned driver requirements",
                      "Restore the compiled driver lock and pinned source; rerun agent-opt datasets prepare cvdp",
                      cause=None if driver_lock_ok else
                      "driver requirements or compiled lock hash differs from its pin",
                      retry="agent-opt datasets prepare cvdp"))
    packages, package_error = (probe(["uv", "--offline", "pip", "freeze", "--python", str(python)])
                               if version == "3.12" else (None, None))
    packages_ok = (valid and packages is not None
                   and sorted(packages.splitlines()) == sorted(lock["driver_packages"].splitlines()))
    packages_cause = (None if packages_ok else package_error or
                      "uv is missing or installed driver packages differ from the prepared lock")
    rows.append(check("dataset.cvdp.driver.packages", "dataset", packages_ok,
                      "Prepared driver packages", "Install uv and rerun agent-opt datasets prepare cvdp",
                      cause=packages_cause, retry="agent-opt datasets prepare cvdp"))
    image = lock["images"]["evaluation"] if valid else {}
    tag, identity = image.get("tag"), image.get("id")
    platform = lock["platform"] if valid else None
    proper = (isinstance(tag, str) and platform is not None and tag == evaluation_image(platform, selected=True)
              and isinstance(identity, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", identity)
              and lock.get("ca_bundle_sha256") == ca_fingerprint())
    info = None
    image_error = None
    if proper:
        try:
            image_output, image_error = probe(["docker", "image", "inspect", tag])
            info = json.loads(image_output)[0] if image_output is not None else None
        except (ValueError, TypeError, IndexError, KeyError):
            image_error = "docker image inspect returned invalid image metadata"
    image_ok = (proper and isinstance(info, dict) and info.get("Id") == identity
                and f"{info.get('Os')}/{info.get('Architecture')}" == platform)
    rows.append(check("dataset.cvdp.image", "dataset", image_ok,
                      "Verified official CVDP simulator image identity and platform",
                      "Start Docker and rerun agent-opt datasets prepare cvdp for this platform/CA bundle",
                      cause=None if image_ok else image_error or
                      "prepared image identity, platform, or CA fingerprint differs",
                      retry="agent-opt datasets prepare cvdp"))
    return rows


def prepare_environment(*, offline=False, platform=None):
    platform = validate_platform(platform)
    external = ROOT / "external"
    fingerprint = ca_fingerprint()
    previous_path = external / "environment-lock.json"
    previous = read_environment_lock(previous_path) if previous_path.exists() else {}
    if offline and previous.get("ca_bundle_sha256") != fingerprint:
        raise _attach_setup_failure(
            "environment lock validation", "Offline CA bundle differs from prepared image lock", None,
            fix="Run online setup with the selected CA bundle to rebuild and pin the images.",
            retry="sh scripts/bootstrap.sh setup", error_type=ConfigurationError,
            message="CA bundle differs from prepared images; rerun online setup",
        ) from None
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
        raise _attach_setup_failure(
            "environment lock validation", "Offline environment lock is missing or platform differs",
            None, fix="Run online setup for the selected platform to build and pin the ACE images.",
            retry="sh scripts/bootstrap.sh setup",
            message="Offline verified environment lock missing or platform differs",
        ) from None
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
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            cause = diagnostics.summarize_failure(
                _outcome_from_exception("docker image inspect", exc), environment=os.environ)
            raise _attach_setup_failure(
                f"{name} image inspection", cause, logs / f"{name}-build.log",
                fix="Check Docker daemon access and restore the pinned image identity.",
                retry="sh scripts/bootstrap.sh setup",
            ) from None
        except (ValueError, TypeError, KeyError, IndexError):
            raise _attach_setup_failure(
                f"{name} image inspection", "docker image inspect returned invalid metadata",
                logs / f"{name}-build.log",
                fix="Restore the pinned image identity for the selected platform.",
                retry="sh scripts/bootstrap.sh setup",
            ) from None
        if f"{info['Os']}/{info['Architecture']}" != platform:
            fix = ("Build the image for the selected Docker platform with online setup before offline retry."
                   if offline else "Build the image for the selected Docker platform.")
            raise _attach_setup_failure(
                f"{name} image inspection", "image OS/architecture differs from the selected platform",
                logs / f"{name}-build.log",
                fix=fix,
                retry="sh scripts/bootstrap.sh setup",
                error_type=ConfigurationError,
            ) from None
        image_locks[name] = {"tag": image, "id": info["Id"]}
        if offline and previous.get("images", {}).get(name) != image_locks[name]:
            raise _attach_setup_failure(
                f"{name} image identity", "Offline image identity differs from the prepared lock",
                logs / f"{name}-build.log",
                fix=f"Run online setup to rebuild and pin the {name} image for the selected platform.",
                retry="sh scripts/bootstrap.sh setup", error_type=ConfigurationError,
                message=f"Offline image identity differs: {image}",
            ) from None
        print(f"[setup] {human(name + ' image')}: {human('complete')}", flush=True)
    print(f"[setup] {human('example tool checks')}: {human('starting')}; {human('log')}: {logs / 'doctor.json'}", flush=True)
    with PreparationStatus("example-tools", action="setup", subject="check"):
        capability = doctor(external, platform, images["evaluation"], images["agent"])
        write_json(logs / "doctor.json", capability)
        if not capability["ready"]:
            failed = [row for row in capability["checks"] if row["returncode"] != 0]
            cause = next((row.get("cause") or row.get("error") for row in failed
                          if row.get("cause") or row.get("error")),
                         "one or more example tool checks failed")
            raise _attach_setup_failure(
                "example tool verification", cause, logs / "doctor.json",
                fix="Repair the reported driver, simulator, or OpenCode tool issue.",
                retry="sh scripts/bootstrap.sh setup",
            ) from None
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
