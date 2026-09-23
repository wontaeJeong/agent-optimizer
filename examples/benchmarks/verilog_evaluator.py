"""Private, pinned Verilog-Eval v2 testbench runner."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, Evaluation, UnavailableError
from agent_optimizer.process import execute, run_process
from agent_optimizer.workspace import safe_path
from examples.benchmarks.verilog_eval import REVISION


class VerilogEvaluator:
    def __init__(self, config=None):
        self.runtime = config or {"kind": "local"}

    def validate_benchmark(self, tasks, metadata):
        if metadata.get("synthetic") or not tasks:
            raise ConfigurationError("Verilog-Eval requires imported, real tasks")
        if metadata.get("source_revision") != REVISION:
            raise ConfigurationError("Verilog-Eval source revision differs from the reviewed pin")
        for task in tasks:
            data = task.evaluation
            if data.get("mode") not in {"spec-to-rtl", "code-complete-iccad2023"}:
                raise ConfigurationError("Unsupported Verilog-Eval task mode")
            if not data.get("source_dir") or not data.get("problem_id"):
                raise ConfigurationError("Verilog-Eval requires pinned source and problem ID")
            tree = Path(data["source_dir"])
            directory = safe_path(tree, "dataset_" + data["mode"])
            for suffix in ("_test.sv", "_ref.sv"):
                if not safe_path(directory, data["problem_id"] + suffix).is_file():
                    raise UnavailableError("Verilog-Eval private testbench is missing")
        if self.runtime.get("kind", "local") == "docker":
            image = self.runtime["image"]
            command = ["docker", "image", "inspect", image]
        else:
            command = [os.environ.get("VERILOG_EVAL_IVERILOG", "iverilog"), "-V"]
        try:
            probe = subprocess.run(command, capture_output=True, text=True, timeout=15, shell=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UnavailableError("Verilog-Eval requires an Icarus v12 evaluation runtime") from exc
        if probe.returncode or (self.runtime.get("kind", "local") != "docker" and
                                not re.search(r"Icarus Verilog version 12\b", probe.stdout + probe.stderr)):
            raise UnavailableError("Verilog-Eval requires an installed Icarus v12 evaluation runtime")

    def evaluate(self, task, output_dir: Path, timeout_seconds: float) -> Evaluation:
        candidate = safe_path(output_dir, "solution.sv")
        if not candidate.is_file() or not candidate.read_text(encoding="utf-8").strip():
            return Evaluation("failed", {"passed": 0.0}, "RTL solution missing")
        content = candidate.read_text(encoding="utf-8")
        if re.search(r"\$(?:display|write|monitor|finish|stop|fatal|system|readmemh|readmemb)\b", content):
            return Evaluation("failed", {"passed": 0.0}, "Candidate contains unsupported simulation control")
        data = task.evaluation
        source = safe_path(Path(data["source_dir"]), "dataset_" + data["mode"])
        scoring = output_dir.parent / "verilog_evaluation"
        scoring.mkdir(exist_ok=False)
        shutil.copyfile(candidate, scoring / "solution.sv")
        for suffix, target in (("_test.sv", "test.sv"), ("_ref.sv", "ref.sv")):
            shutil.copyfile(safe_path(source, data["problem_id"] + suffix), scoring / target)
        argv = ["iverilog", "-Wall", "-Winfloop", "-Wno-timescale", "-g2012", "-s", "tb",
                "-o", "simv", "solution.sv", "test.sv", "ref.sv"]
        if self.runtime.get("kind", "local") == "docker":
            compile_result = execute(argv, scoring, scoring / "compile_logs", timeout_seconds, self.runtime)
        else:
            argv[0] = os.environ.get("VERILOG_EVAL_IVERILOG", "iverilog")
            compile_result = run_process(argv, scoring, scoring / "compile_logs", timeout_seconds,
                                         env={key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR") if key in os.environ})
        if compile_result.status != "completed":
            status = "failed" if compile_result.status == "process_error" else compile_result.status
            return Evaluation(status, {"passed": 0.0 if status in {"failed", "timeout"} else None},
                              "Verilog-Eval compile did not complete")
        if self.runtime.get("kind", "local") == "docker":
            run = execute(["vvp", "simv"], scoring, scoring / "run_logs", timeout_seconds, self.runtime)
        else:
            run = run_process([os.environ.get("VERILOG_EVAL_VVP", "vvp"), "simv"], scoring,
                              scoring / "run_logs", timeout_seconds,
                              env={key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR") if key in os.environ})
        if run.status != "completed":
            return Evaluation("timeout" if run.status == "timeout" else "infrastructure_error",
                              {"passed": 0.0 if run.status == "timeout" else None},
                              "Verilog-Eval simulation did not complete")
        output = Path(run.stdout_path).read_text(errors="replace")
        matches = re.findall(r"^Mismatches: (\d+) in (\d+) samples$", output, re.M)
        if "TIMEOUT" in output or len(matches) != 1 or int(matches[0][1]) < 1:
            return Evaluation("infrastructure_error", {"passed": None},
                              "Verilog-Eval produced no trustworthy mismatch verdict")
        passed = int(matches[0][0]) == 0
        return Evaluation("passed" if passed else "failed", {"passed": float(passed)},
                          f"Verilog-Eval: {matches[0][0]} mismatches in {matches[0][1]} samples")
