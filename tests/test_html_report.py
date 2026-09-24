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
from agent_optimizer.html_report import write_html_report
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
        manifest_path = run / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["benchmark"]["dataset_provenance"] = {"image_id": "sha256:checked",
                                                       "revision": "verified-source"}
        manifest_path.write_text(json.dumps(manifest))
        write_html_report(run, summary)
        page = (run / "report.html").read_text(encoding="utf-8")
        for detail in ("Agent Optimizer", "Baseline", "validation", "test", "Slowest tasks",
                       "fixture-validation", "Optimizer usage", "Candidate changes"):
            with self.subTest(detail=detail):
                self.assertIn(detail, page)
        self.assertIn("changes.diff", page)
        self.assertIn("sha256:checked", page)
        self.assertNotIn("extensions_sha256", page)
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

    def test_report_html_rebuilds_legacy_derived_artifacts_without_changing_source_or_csv(self):
        run, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        source = (run / "summary.json").read_bytes()
        csv_path = run / "export.csv"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["report", str(run), "--csv", str(csv_path)]), 0)
        exported = csv_path.read_bytes()
        (run / "report.json").unlink(missing_ok=True)
        (run / "report.md").write_text("old")
        (run / "report.html").write_text("old")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["report", str(run), "--html"]), 0)

        self.assertEqual(json.loads(output.getvalue()),
                         {"html": str(run / "report.html"), "status": summary["status"]})
        self.assertEqual((run / "summary.json").read_bytes(), source)
        self.assertEqual(csv_path.read_bytes(), exported)
        model = json.loads((run / "report.json").read_text())
        self.assertEqual(model["groups"][0]["selected"], summary["groups"][0]["selected"])
        self.assertNotEqual((run / "report.md").read_text(), "old")
        self.assertNotEqual((run / "report.html").read_text(), "old")

    def test_two_group_run_writes_matching_selected_and_completed_counts(self):
        spec = load_experiment(self.root / "examples/minimal/experiment.toml")
        run, summary = run_experiment(spec, Registry(), self.root / "runs")
        model = json.loads((run / "report.json").read_text())
        markdown = (run / "report.md").read_text()
        html = (run / "report.html").read_text()
        self.assertEqual(len(model["groups"]), 2)
        self.assertEqual([g["selected"] for g in model["groups"]],
                         [g["selected"] for g in summary["groups"]])
        for group in model["groups"]:
            self.assertGreater(group["counts"]["completed_evaluations"], 0)
            for content in (markdown, html):
                self.assertIn(group["agent_id"], content)
                self.assertIn(f'{group["counts"]["completed_evaluations"]} completed', content)
                self.assertIn(group["comparison_trend"], content)


if __name__ == "__main__":
    unittest.main()
