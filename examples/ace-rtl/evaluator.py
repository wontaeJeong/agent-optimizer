"""Official CVDP Docker evaluation of submitted RTL; no Agent-reported pass flags."""
import copy
import json
import os
import subprocess
import uuid
from pathlib import Path
from agent_optimizer.contracts import ConfigurationError, Evaluation, UnavailableError
from agent_optimizer.process import run_process
from agent_optimizer.workspace import safe_path
from agent_optimizer.network import network_environment


def cleanup_network(network, logs):
    """Clean only this evaluation's unique network, including after driver SIGKILL."""
    logs.mkdir(parents=True, exist_ok=True)
    commands = []
    try:
        listing = subprocess.run(["docker", "ps", "-aq", "--filter", f"network={network}"],
                                 capture_output=True, text=True, timeout=15, shell=False)
        commands.append({"command": "list-owned-containers", "returncode": listing.returncode})
        for container in listing.stdout.split() if listing.returncode == 0 else []:
            removed = subprocess.run(["docker", "rm", "-f", container], capture_output=True,
                                     text=True, timeout=15, shell=False)
            commands.append({"container": container, "returncode": removed.returncode})
        removed = subprocess.run(["docker", "network", "rm", network], capture_output=True,
                                 text=True, timeout=15, shell=False)
        commands.append({"network": network, "returncode": removed.returncode})
    except (OSError, subprocess.TimeoutExpired) as exc:
        commands.append({"cleanup_error": type(exc).__name__})
    (logs / "cleanup.json").write_text(json.dumps(commands, indent=2))


class CVDPEvaluator:
    def __init__(self, config=None):
        self.repo = Path(os.environ.get("CVDP_REPO", "external/cvdp_benchmark")).resolve()
        # Resolving a venv's Python symlink bypasses pyvenv.cfg and its dependencies.
        self.python = Path(os.environ.get("CVDP_PYTHON", "external/cvdp-venv/bin/python")).absolute()

    def validate_benchmark(self, tasks, metadata):
        if metadata.get("synthetic"):
            raise ConfigurationError("CVDP requires real benchmark rows")
        if not (self.repo / "run_benchmark.py").is_file() or not self.python.is_file():
            raise UnavailableError("Run examples/ace-rtl/setup.sh first")
        for task in tasks:
            if "row" not in task.evaluation or "targets" not in task.evaluation:
                raise ConfigurationError("Use examples/ace-rtl/prepare.py")

    def evaluate(self, task, output_dir, timeout_seconds):
        row = copy.deepcopy(task.evaluation["row"])
        submitted = {}
        for target in task.evaluation["targets"]:
            file = safe_path(output_dir, target)
            if not file.is_file() or not file.read_text().strip():
                return Evaluation("failed", {"passed": 0.0}, "Required RTL output missing")
            submitted[target] = file.read_text()
        row["output"] = {"response": "", "context": submitted}
        scoring = output_dir.parent / "cvdp_evaluation"
        scoring.mkdir()
        dataset = scoring / "submission.jsonl"
        dataset.write_text(json.dumps(row)+"\n")
        prefix = scoring / "work"
        network = "agent-opt-cvdp-" + uuid.uuid4().hex
        # Official code can interpolate OPENAI_USER_KEY into a generated script.
        # Binary OSS evaluation needs no model credentials, including dotenv ones.
        environment = {k: v for k, v in os.environ.items() if k in {
            "PATH", "HOME", "TMPDIR", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG",
            "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "SSL_CERT_FILE", "SSL_CERT_DIR",
            "OSS_SIM_IMAGE", "DOCKER_DEFAULT_PLATFORM",
        }}
        environment["OPENAI_USER_KEY"] = ""
        network_settings = network_environment()
        environment.update(network_settings)
        driver = [str(self.python)]
        if network_settings:
            driver.append(str(Path(__file__).parent / "environment/network_driver.py"))
        driver.append(str(self.repo / "run_benchmark.py"))
        # Golden mode here means evaluate the supplied output.context; it contains
        # candidate RTL, never a golden/reference solution.
        try:
            result = run_process([*driver,
                                  "--network-name", network, "-f", str(dataset), "-i", row["id"], "-p", str(prefix)],
                                 self.repo, scoring / "logs", timeout_seconds, env=environment)
        finally:
            cleanup_network(network, scoring / "logs")
        artifact = prefix / "raw_result.json"
        if result.status == "timeout":
            return Evaluation("timeout", {"passed": 0.0}, "CVDP evaluation timed out")
        if not artifact.is_file() or result.status != "completed":
            return Evaluation("infrastructure_error", {"passed": None}, "CVDP did not produce a valid evaluation", {"logs": str(scoring / "logs")})
        try:
            artifact = safe_path(scoring, "work/raw_result.json")
            record = json.loads(artifact.read_text())[row["id"]]
            tests = record["tests"]
            if not tests or any(type(t.get("result")) is not int for t in tests):
                raise ValueError("Missing test status")
            # Conservative setup-error classification; do not expose private test logs.
            errors = " ".join(str(t.get("error_msg", "")) for t in tests).lower()
            if (any(t["result"] in {125, 126, 127} for t in tests) or
                    any(term in errors for term in ["cannot connect to the docker", "no such image", "permission denied", "command not found", "no such file or directory", "failed to execute objective harness"])):
                return Evaluation("infrastructure_error", {"passed": None}, "CVDP environment failure; inspect private evaluator logs")
            for test in tests:
                # Upstream log_run returns result=1/error_msg=null even when Compose
                # cannot build or launch. Read only this run's owned private artifact.
                if test["result"] == 0 or test.get("log") is None:
                    continue
                log = Path(test["log"])
                relative = log.relative_to(prefix.absolute()).as_posix() if log.is_absolute() else test["log"]
                private_log = safe_path(prefix, relative).read_text(errors="replace").lower()
                # Keep these Docker-specific: HDL diagnostics can also say missing
                # file, permission denied, compilation failed, or make Error 1/2.
                if any(term in private_log for term in (
                    "pull access denied", "insufficient_scope: authorization failed",
                    "failed to resolve source metadata for", "cannot connect to the docker daemon",
                    "error response from daemon:", "oci runtime create failed",
                )):
                    return Evaluation("infrastructure_error", {"passed": None},
                                      "CVDP environment failure; inspect private evaluator logs", {"raw_result": str(artifact)})
            passed = all(t["result"] == 0 for t in tests)
            return Evaluation("passed" if passed else "failed", {"passed": float(passed)},
                              f"Official CVDP: {sum(t['result'] == 0 for t in tests)}/{len(tests)} tests passed", {"raw_result": str(artifact)})
        except (KeyError, TypeError, ValueError):
            return Evaluation("infrastructure_error", {"passed": None}, "Unsupported CVDP result schema")
        except (OSError, ConfigurationError):
            return Evaluation("infrastructure_error", {"passed": None}, "Invalid CVDP private result artifact")
