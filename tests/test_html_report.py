"""Offline reports must be useful after success or failure and escape untrusted feedback."""
import contextlib
import io
import json
import unittest
from pathlib import Path

from agent_optimizer.cli import main
from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import Evaluation, UnavailableError
from agent_optimizer.registry import Registry
from agent_optimizer.runner import run_experiment
from support import test_project


class HTMLReportTests(unittest.TestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)
        self.spec = load_experiment(self.root / "examples/minimal/experiment.toml")
        self.spec["_agents"] = self.spec["_agents"][:1]

    def test_completed_report_shows_splits_timeline_usage_and_candidate_links(self):
        run, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        page = (run / "report.html").read_text(encoding="utf-8")
        for detail in ("Agent Optimizer", "Baseline", "validation", "test", "Slowest tasks",
                       "fixture-validation", "Optimizer usage", "Candidate changes"):
            with self.subTest(detail=detail):
                self.assertIn(detail, page)
        self.assertIn("changes.diff", page)
        self.assertNotIn('src="https://', page)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["report", str(run), "--html"]), 0)
        self.assertEqual(Path(json.loads(output.getvalue())["html"]), run / "report.html")

    def test_untrusted_feedback_is_escaped_in_incomplete_report(self):
        class FailingEvaluator:
            def __init__(self, config=None):
                pass

            def evaluate(self, task, output_dir, timeout_seconds):
                return Evaluation("failed", {"passed": 0.0}, '<script>alert(1)</script>')

        registry = Registry()
        registry.factories["evaluators"]["text_fixture"] = FailingEvaluator
        self.spec["plugins"]["evaluators"] = {}
        self.spec.update(stages=[], final_stages=["baseline"], final_test=False)
        run, summary = run_experiment(self.spec, registry, self.root / "runs")
        page = (run / "report.html").read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("Not evaluated", page)

    def test_run_failure_still_writes_inspectable_html(self):
        class FailingOptimizer:
            def optimize(self, context, seeds, config):
                raise UnavailableError("model failed")

        registry = Registry()
        registry.factories["optimizers"]["file_variants"] = FailingOptimizer
        with self.assertRaisesRegex(UnavailableError, "model failed"):
            run_experiment(self.spec, registry, self.root / "runs")
        run = next((self.root / "runs").glob("*/summary.json")).parent
        page = (run / "report.html").read_text(encoding="utf-8")
        self.assertIn("model failed", page)
        self.assertIn("error", page)


if __name__ == "__main__":
    unittest.main()
