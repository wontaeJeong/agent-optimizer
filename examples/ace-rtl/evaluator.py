"""Official CVDP Docker evaluation of submitted RTL; no Agent-reported pass flags."""
import copy
import json
import os
import subprocess
from pathlib import Path
from agent_optimizer.contracts import ConfigurationError, Evaluation, UnavailableError
from agent_optimizer.process import run_process
from agent_optimizer.workspace import safe_path

class CVDPEvaluator:
    def __init__(self, config=None):
        self.repo = Path(os.environ.get("CVDP_REPO", "external/cvdp_benchmark")).resolve()
        self.python = Path(os.environ.get("CVDP_PYTHON", "external/cvdp-venv/bin/python")).resolve()

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
        # Golden mode here means evaluate the supplied output.context; it contains
        # candidate RTL, never a golden/reference solution.
        result = run_process([str(self.python), str(self.repo / "run_benchmark.py"),
                              "-f", str(dataset), "-i", row["id"], "-p", str(prefix)],
                             self.repo, scoring / "logs", timeout_seconds)
        artifact = prefix / "raw_result.json"
        if result.status == "timeout":
            return Evaluation("timeout", {"passed": 0.0}, "CVDP evaluation timed out")
        if not artifact.is_file() or result.status != "completed":
            return Evaluation("infrastructure_error", {"passed": None}, "CVDP did not produce a valid evaluation", {"logs": str(scoring / "logs")})
        try:
            record = json.loads(artifact.read_text())[row["id"]]
            tests = record["tests"]
            if not tests or any(type(t.get("result")) is not int for t in tests):
                raise ValueError("Missing test status")
            # Conservative setup-error classification; do not expose private test logs.
            errors = " ".join(str(t.get("error_msg", "")) for t in tests).lower()
            if any(term in errors for term in ["cannot connect to the docker", "no such image", "permission denied", "command not found", "no such file or directory"]):
                return Evaluation("infrastructure_error", {"passed": None}, "CVDP environment failure; inspect private evaluator logs")
            passed = all(t["result"] == 0 for t in tests)
            return Evaluation("passed" if passed else "failed", {"passed": float(passed)},
                              f"Official CVDP: {sum(t['result'] == 0 for t in tests)}/{len(tests)} tests passed", {"raw_result": str(artifact)})
        except (KeyError, TypeError, ValueError):
            return Evaluation("infrastructure_error", {"passed": None}, "Unsupported CVDP result schema")
