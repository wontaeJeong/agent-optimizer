from pathlib import Path

from agent_optimizer.contracts import Evaluation
from agent_optimizer.process import execute
from agent_optimizer.workspace import safe_path


class IcarusVerilog:
    id = "iverilog"

    def __init__(self, runtime: dict | None = None):
        self.runtime = runtime or {"kind": "local"}

    def run(self, workspace: Path, config: dict, timeout_seconds: float) -> Evaluation:
        sources = config["sources"]
        for source in sources:
            if not safe_path(workspace, source).is_file():
                return Evaluation("failed", {"passed": 0.0}, f"Missing source: {source}")
        compile_result = execute(["iverilog", "-g2012", "-s", config.get("top", "tb"),
                                  "-o", "sim.out", *sources], workspace,
                                 workspace / "compile_logs", timeout_seconds, self.runtime)
        if compile_result.status != "completed":
            status = "infrastructure_error" if compile_result.status == "infrastructure_error" else "failed"
            if compile_result.status == "timeout":
                status = "timeout"
            return Evaluation(status, {"passed": None if status == "infrastructure_error" else 0.0},
                              f"Compile {compile_result.status}", {"compile_log": compile_result.stderr_path})
        remaining = timeout_seconds - compile_result.wall_time_seconds
        if remaining <= 0:
            return Evaluation("timeout", {"passed": 0.0}, "Simulation budget exhausted")
        run = execute(["vvp", "sim.out"], workspace, workspace / "simulation_logs",
                      remaining, self.runtime)
        output = Path(run.stdout_path).read_text(encoding="utf-8", errors="replace")
        passed = run.status == "completed" and config.get("pass_marker", "TEST_PASS") in output
        status = "passed" if passed else ("timeout" if run.status == "timeout" else "failed")
        if run.status == "infrastructure_error":
            status = "infrastructure_error"
        return Evaluation(status, {"passed": None if status == "infrastructure_error" else float(passed)},
                          f"Icarus simulation {status}", {"simulation_log": run.stdout_path})
