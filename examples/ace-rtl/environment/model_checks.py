"""Explicit, potentially billable model checks; separate from read-only doctor."""
import json
import os
import uuid

from agent_optimizer.contracts import ConfigurationError, RunRequest, UnavailableError
from agent_optimizer.harnesses.opencode import OpenCodeHarness
from agent_optimizer.models import ModelSettings, probe_model
from agent_optimizer.network import demo_environment, network_environment
from agent_optimizer.terminal_report import PreparationStatus


def probe_harness(root, lock):
    workspace = root / "runs" / ("doctor-model-" + uuid.uuid4().hex[:12])
    task, agent = workspace / "task", workspace / "agent"
    task.mkdir(parents=True)
    agent.mkdir()
    marker = "doctor-" + uuid.uuid4().hex
    runtime = {"kind": "docker", "image": lock["images"]["agent"]["id"], "network": "bridge",
                "env_passthrough": ["AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_ID", "AGENT_OPT_MODEL_API_KEY", "AGENT_OPT_MODEL", "OPENCODE_CONFIG"]}
    request = RunRequest(workspace, agent, task,
                         f"Use the bash tool to write exactly {marker} into task/probe.txt. Then stop.",
                         0, 120, {"model_env": "AGENT_OPT_MODEL", "runtime": runtime}, workspace / "logs")
    result = OpenCodeHarness().run(request)
    output = task / "probe.txt"
    if (result.status != "completed" or output.is_symlink() or not output.is_file()
            or output.read_text().strip() != marker):
        raise UnavailableError("Container model/tool execution failed")


def check_models(root, report):
    """Append safe diagnostics using the same prepared image and network as live."""
    original = dict(os.environ)
    passed = False
    try:
        os.environ.update(demo_environment())
        os.environ.update(network_environment())
        settings = ModelSettings.from_env()
        os.environ.update(AGENT_OPT_MODEL_ID=settings.model, AGENT_OPT_MODEL="compatible/" + settings.model,
                          OPENCODE_CONFIG="/opt/agent-optimizer/compatible.json")
        if not report["ready"]:
            raise UnavailableError("Complete environment preparation first")
        with PreparationStatus("host-api", action="doctor", subject="check"):
            probe_model(settings=settings)
        report["checks"].append({"id": "live.host_api", "area": "live", "status": "ok",
                                 "message": "Actual host API tool-call probe passed.", "remedy": ""})
        lock = json.loads((root / "external/environment-lock.json").read_text())
        os.environ["DOCKER_DEFAULT_PLATFORM"] = lock["platform"]
        with PreparationStatus("container-tool", action="doctor", subject="check"):
            probe_harness(root, lock)
        passed = True
    except (ConfigurationError, UnavailableError, OSError, ValueError, KeyError):
        pass
    finally:
        os.environ.clear()
        os.environ.update(original)
    report["checks"].append({"id": "live.execution", "area": "live", "status": "ok" if passed else "error",
                             "message": "Actual host API and container OpenCode/tool execution.",
                             "remedy": "" if passed else "Check AGENT_OPT_MODEL_* settings, proxy/NO_PROXY, CA and runs/doctor-model-*/logs."})
    report["model_status"] = "passed" if passed else "blocked"
    report["areas"]["live"] = passed
    report["ready"] = report["ready"] and passed
