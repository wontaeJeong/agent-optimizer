from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, Evaluation, Task
from agent_optimizer.workspace import safe_path


class TextFixtureEvaluator:
    """Exact-text wiring test, not a simulator and not CVDP scoring."""

    def __init__(self, config=None):
        pass

    def validate_benchmark(self, tasks, metadata):
        if not metadata.get("synthetic", False):
            raise ConfigurationError("text_fixture requires explicitly synthetic data")
        if any(t.required_simulator for t in tasks):
            raise ConfigurationError("text_fixture cannot substitute for a simulator")

    def evaluate(self, task: Task, output_dir: Path, timeout_seconds: float) -> Evaluation:
        spec = task.evaluation
        path = safe_path(output_dir, spec["file"])
        passed = path.is_file() and path.read_text(encoding="utf-8") == spec["expected"]
        return Evaluation("passed" if passed else "failed", {"passed": float(passed)},
                          "Synthetic exact-text check; no RTL simulation was performed")
