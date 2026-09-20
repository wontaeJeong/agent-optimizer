from __future__ import annotations

import os
import signal
import subprocess
import time
import uuid
from pathlib import Path

from agent_optimizer.contracts import ExecutionResult
from agent_optimizer.network import host_environment, container_network


def run_process(argv: list[str], cwd: Path, logs: Path, timeout: float,
                env: dict[str, str] | None = None) -> ExecutionResult:
    logs.mkdir(parents=True, exist_ok=True)
    stdout, stderr = logs / "stdout.log", logs / "stderr.log"
    started = time.monotonic()
    with stdout.open("wb") as out, stderr.open("wb") as err:
        try:
            proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=err, start_new_session=True)
        except OSError as exc:
            return ExecutionResult("infrastructure_error", None, time.monotonic()-started,
                                   str(stdout), str(stderr), detail=str(exc))
        try:
            code = proc.wait(timeout=max(0.001, timeout))
            status = "completed" if code == 0 else "process_error"
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait()
            status = "timeout"
        except BaseException:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            raise
    return ExecutionResult(status, code, time.monotonic()-started, str(stdout), str(stderr))


def execute(argv: list[str], workspace: Path, logs: Path, timeout: float,
            runtime: dict, env: dict[str, str] | None = None) -> ExecutionResult:
    """Docker mounts the trial workspace and optional read-only CA, never the socket."""
    env = env or {}
    if runtime.get("kind", "local") == "local":
        return run_process(argv, workspace, logs, timeout, host_environment({**os.environ, **env}))
    network_args, network_env = container_network({**os.environ, **env})
    name = "agent-opt-" + uuid.uuid4().hex[:16]
    command = ["docker", "run", "--rm", "--name", name, "--init",
               "--user", f"{os.getuid()}:{os.getgid()}",
               "--cap-drop=ALL", "--security-opt=no-new-privileges",
               "--pids-limit", "256", "--memory", runtime.get("memory", "4g"),
               "--cpus", str(runtime.get("cpus", 2)),
               "--network", runtime.get("network", "none"),
               "--mount", f"type=bind,source={workspace.resolve()},target=/work",
               "--workdir", "/work", "--env", "HOME=/tmp/agent-home"]
    for key, value in env.items():
        if key in network_env or key == "AGENT_OPT_CA_BUNDLE":
            continue
        command += ["--env", f"{key}={value}"]
    for key in runtime.get("env_passthrough", []):
        # An absent bare --env would erase an image default. Empty host values are intentional.
        if key in os.environ and key not in network_env and key != "AGENT_OPT_CA_BUNDLE":
            command += ["--env", key]
    command += network_args
    command += [runtime["image"], *argv]
    try:
        result = run_process(command, workspace, logs, timeout, env={**os.environ, **network_env})
        if result.returncode in {125, 126, 127}:
            result.status = "infrastructure_error"
            result.detail = "Docker/image/entrypoint failure; see stderr log"
        return result
    finally:
        # A killed Docker client does not necessarily stop its container.
        try:
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
