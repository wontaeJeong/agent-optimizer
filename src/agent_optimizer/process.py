from __future__ import annotations

import os
import signal
import subprocess
import time
import uuid
from pathlib import Path

from agent_optimizer.contracts import ExecutionResult


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
    """Docker mounts exactly one trial workspace. Agent receives no Docker socket."""
    env = env or {}
    if runtime.get("kind", "local") == "local":
        return run_process(argv, workspace, logs, timeout, {**os.environ, **env})
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
        command += ["--env", f"{key}={value}"]
    for key in runtime.get("env_passthrough", []):
        command += ["--env", key]
    command += [runtime["image"], *argv]
    try:
        result = run_process(command, workspace, logs, timeout)
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
