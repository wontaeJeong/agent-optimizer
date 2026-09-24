"""API-free synthetic dataset example; never fetches or infers a scoring rule."""
from pathlib import Path

from agent_optimizer.config import load_tasks
from agent_optimizer.contracts import ConfigurationError


ROOT = Path(__file__).resolve().parents[2]


class Provider:
    def describe(self) -> dict:
        return {"name": "sample_text", "task_form": "synthetic text fixture",
                "evaluator": "sample_eval"}

    def prepare(self, cache: Path, *, offline: bool = False) -> dict:
        benchmark = ROOT / "examples/minimal/tasks.json"
        return {"benchmark": str(benchmark), "evaluator": "sample_eval",
                "provenance": {"synthetic": True, "source": "examples/minimal/tasks.json"}}

    def doctor(self, cache: Path) -> list[dict]:
        """Inspect shipped fixture inputs without preparing or evaluating anything."""
        benchmark = ROOT / "examples/minimal/tasks.json"
        evaluator = ROOT / "examples/minimal/evaluator.py"
        try:
            tasks, metadata = load_tasks(benchmark)
            valid = (metadata.get("synthetic") is True and
                     all(isinstance(task.evaluation.get("file"), str) and
                         isinstance(task.evaluation.get("expected"), str) for task in tasks))
        except (ConfigurationError, OSError, ValueError, KeyError, TypeError):
            valid = False
        available = evaluator.is_file()
        return [
            {"id": "dataset.sample_text.tasks", "area": "dataset", "status": "ok" if valid else "error",
             "message": "Synthetic fixture tasks are valid" if valid else "Synthetic fixture tasks are unavailable",
             "remedy": "" if valid else "Restore examples/minimal/tasks.json with a valid synthetic task manifest"},
            {"id": "dataset.sample_text.evaluator", "area": "evaluator",
             "status": "ok" if available else "error",
             "message": "Synthetic fixture evaluator is available" if available else "Synthetic fixture evaluator is missing",
             "remedy": "" if available else "Restore examples/minimal/evaluator.py"},
        ]
