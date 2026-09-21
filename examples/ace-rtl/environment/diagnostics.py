"""Example-local diagnostics; no package installation or model call by default."""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, RunRequest, UnavailableError
from agent_optimizer.harnesses.opencode import OpenCodeHarness
from agent_optimizer.models import probe_model
from agent_optimizer.network import ca_fingerprint, network_environment

MODEL_ENV = ["MODEL_ENDPOINT", "MODEL_BASE_URL", "MODEL_ID", "MODEL_API_KEY", "AGENT_OPT_MODEL", "OPENCODE_CONFIG"]


def configure_network():
    # Ubuntu's existing complete trust bundle includes locally installed proxy CAs.
    system = Path("/etc/ssl/certs/ca-certificates.crt")
    if "AGENT_OPT_CA_BUNDLE" not in os.environ and sys.platform == "linux" and system.is_file():
        os.environ["AGENT_OPT_CA_BUNDLE"] = str(system)


def prerequisites(*, offline=False):
    commands = {
        "uv": (["uv", "--version"], "Install uv and make it available on PATH; see README bootstrap."),
        "git": (["git", "--version"], "Install git and make it available on PATH."),
        "docker": (["docker", "version", "--format", "{{.Server.Version}}"], "Start Docker and grant this user daemon access."),
        "compose": (["docker", "compose", "version"], "Install the docker compose plugin."),
    }
    if os.environ.get("AGENT_OPT_CA_BUNDLE") and not offline:
        commands["buildx"] = (["docker", "buildx", "version"], "Install docker buildx (BuildKit named CA context is required).")
    checks = {"python": {"status": "passed" if sys.version_info >= (3, 11) else "blocked",
                         "repair": "Run this command with Python 3.11+; setup provisions the Python 3.12 driver."}}
    for name, (argv, repair) in commands.items():
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=15, shell=False)
            passed = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            passed = False
        checks[name] = {"status": "passed" if passed else "blocked", "repair": repair if not passed else ""}
    return {"ready": all(c["status"] == "passed" for c in checks.values()), "checks": checks}


def model_runtime(lock):
    return {"kind": "docker", "image": lock["images"]["agent"]["id"], "network": "bridge", "env_passthrough": MODEL_ENV}


def probe_harness(root, lock):
    workspace = root / "runs" / ("doctor-model-" + uuid.uuid4().hex[:12])
    task = workspace / "task"
    task.mkdir(parents=True)
    agent = workspace / "agent"
    agent.mkdir()
    marker = "doctor-" + uuid.uuid4().hex
    request = RunRequest(workspace, agent, task,
                         f"Use the bash tool to write exactly {marker} into task/probe.txt. Then stop.",
                         0, 120, {"model_env": "AGENT_OPT_MODEL", "runtime": model_runtime(lock)},
                         workspace / "logs")
    result = OpenCodeHarness().run(request)
    output = task / "probe.txt"
    if (result.status != "completed" or output.is_symlink() or not output.is_file()
            or output.read_text().strip() != marker):
        raise UnavailableError("Container model/tool execution failed; inspect runs/doctor-model-*/logs and check provider/CA/proxy")
    return {"status": "passed", "streaming_tool_execution": True}


def inspect_environment(setup, platform=None, *, check_model=False):
    report = prerequisites(offline=True)
    checks = report["checks"]
    report["model_status"] = "not_checked"

    def check(name, action, repair):
        try:
            action()
            checks[name] = {"status": "passed"}
            return True
        except (ConfigurationError, UnavailableError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            # Do not print environment values, provider payloads or subprocess output.
            checks[name] = {"status": "blocked", "repair": repair}
            return False

    check("network", network_environment, "Check proxy variable syntax and AGENT_OPT_CA_BUNDLE: use a full PEM trust bundle.")
    report["network"] = {"proxy_variables": [k for k in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy") if k in os.environ],
                         "ca_bundle_configured": bool(os.environ.get("AGENT_OPT_CA_BUNDLE"))}
    external = setup.ROOT / "external"
    lock = {}

    def prepared():
        lock.update(json.loads((external / "environment-lock.json").read_text()))
        if not lock or lock["platform"] != setup.validate_platform(platform):
            raise ConfigurationError("Prepared platform differs")
        if lock.get("ca_bundle_sha256") != ca_fingerprint():
            raise ConfigurationError("CA bundle differs")

    ready = check("prepared", prepared, "Run python3 scripts/dev.py setup with the selected platform and CA bundle.")
    if ready:
        report["platform"] = lock["platform"]
        check("sources", lambda: setup.prepare_sources(external, offline=True), "Rerun setup; preserve any modified upstream checkout separately.")
        check("data", lambda: setup.prepare_data(external, offline=True), "Rerun online setup to restore pinned dataset assets.")
        check("driver_lock", lambda: setup.validate_driver_lock(external, lock), "Rerun setup to sync the pinned Python 3.12 driver.")
        check("evaluation_image", lambda: setup.verified_sim_image(lock), "Rerun setup to restore the locked evaluation image/tag.")

        def tools():
            capability = setup.doctor(external, lock["platform"], lock["images"]["evaluation"]["id"], lock["images"]["agent"]["id"])
            for name, row in capability["checks"].items():
                checks[name] = {"status": "passed" if row["returncode"] == 0 else "blocked",
                                "repair": "Rerun setup; inspect external/setup-logs/doctor.json." if row["returncode"] != 0 else ""}
            if not capability["ready"]:
                raise UnavailableError("Tools unavailable")

        check("runtime", tools, "Rerun setup; check Docker execution and Python driver imports.")
    if check_model:
        configured = check("model_config", setup.validate_live, "Set MODEL_API_KEY and exactly one of MODEL_ENDPOINT/MODEL_BASE_URL; optional MODEL_ID.")
        if configured:
            check("host_model", probe_model, "Check model authentication, endpoint, proxy/NO_PROXY, CA and tool-call support.")
            if ready and checks.get("runtime", {}).get("status") == "passed":
                check("container_model", lambda: probe_harness(setup.ROOT, lock), "Check Agent container provider, proxy/CA and tool execution; inspect runs/doctor-model-*.")
            else:
                checks["container_model"] = {"status": "blocked", "repair": "Complete setup before container model verification."}
        report["model_status"] = "passed" if all(checks.get(k, {}).get("status") == "passed" for k in
                                                 ("model_config", "host_model", "container_model")) else "blocked"
    report["ready"] = all(c["status"] == "passed" for c in checks.values())
    return report
