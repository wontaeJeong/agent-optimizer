"""API-free synthetic dataset example; never fetches or infers a scoring rule."""
from pathlib import Path


class Provider:
    def describe(self) -> dict:
        return {"name": "sample_text", "task_form": "synthetic text fixture",
                "evaluator": "sample_eval"}

    def prepare(self, cache: Path, *, offline: bool = False) -> dict:
        benchmark = Path(__file__).resolve().parents[2] / "examples/minimal/tasks.json"
        return {"benchmark": str(benchmark), "evaluator": "sample_eval",
                "provenance": {"synthetic": True, "source": "examples/minimal/tasks.json"}}
