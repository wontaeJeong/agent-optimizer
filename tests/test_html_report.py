"""Offline reports must be useful after success or failure and escape untrusted feedback."""
import contextlib
import io
import json
import re
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
        for detail in ("Agent Optimizer", "Baseline", "validation", "test",
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

        self.assertIn("multi-agent-demo", html)
        self.assertIn("examples/minimal/tasks.json", html)
        self.assertIn("maximize", html)
        self.assertIn("max_trials", html)
        self.assertIn("Synthetic fixture", html)
        self.assertIn('scope="col"', html)
        self.assertIn("<caption", html)
        self.assertNotIn('src="https://', html)
        self.assertIn('<strong>7</strong><span>Completed evaluations', html)
        self.assertEqual(model["counts"]["completed_evaluations"], 7)
        self.assertEqual(len(re.findall(r'<tr[^>]+id="evaluation-', html)), 7)
        self.assertIn('href="rtl-solo/fixture/candidates/c0002/changes.diff"', html)
        self.assertIn('href="rtl-team/fixture/candidates/c0001/changes.diff"', html)
        self.assertIn('href="rtl-solo/fixture/candidates/c0002/bundle/"', html)
        self.assertIn('href="rtl-team/fixture/candidates/c0001/bundle/"', html)
        self.assertIn("+1.000", html)  # solo 0 -> 1; team 1 -> 1
        self.assertIn("+0.000", html)
        self.assertIn('id="held-out-test"', html)
        self.assertIn("diff preview", html.lower())

    def test_long_untrusted_feedback_keeps_full_text_in_details(self):
        class FailingEvaluator:
            def __init__(self, config=None):
                pass

            def evaluate(self, task, output_dir, timeout_seconds):
                return Evaluation("failed", {"passed": 0.0}, "A" * 5001 + "<script>tail</script>")

        registry = Registry()
        registry.factories["evaluators"]["text_fixture"] = FailingEvaluator
        self.spec["plugins"]["evaluators"] = {}
        self.spec.update(stages=[], final_stages=["baseline"], final_test=False)
        run, _ = run_experiment(self.spec, registry, self.root / "runs")
        page = (run / "report.html").read_text(encoding="utf-8")
        self.assertIn("A" * 5001 + "&lt;script&gt;tail&lt;/script&gt;", page)
        self.assertNotIn("<script>tail</script>", page)
        self.assertIn("<details", page)

    def test_explicit_infrastructure_failure_and_unknown_optimizer_have_evaluation_fallback(self):
        run = self.root / "recorded"
        run.mkdir()
        summary = {"run_id": "recorded", "status": "partial", "trials_used": 2, "groups": [
            {"agent_id": "solo", "harness_id": "fixture-harness", "baseline": None,
             "selected": [], "final_test": [], "stages": [{"id": "opaque", "optimizer": "unknown-plugin",
                                                   "checkpoint": {"internal": [1, 2]}}]}]}
        (run / "events.jsonl").write_text(json.dumps({
            "event": "trial_completed", "trial_id": "infra-1", "agent_id": "solo",
            "harness_id": "fixture-harness", "candidate_id": "c0001", "task_id": "unit-1",
            "split": "train", "status": "infrastructure_error", "feedback": "timeout text only",
            "execution": {"status": "infrastructure_error", "detail": "worker unavailable"},
        }) + "\n", encoding="utf-8")
        page = write_html_report(run, summary).read_text(encoding="utf-8")
        self.assertIn("unknown-plugin", page)
        self.assertIn("No recorded structure", page)
        self.assertIn('id="evaluations"', page)
        self.assertIn("infra-1", page)
        self.assertIn("infrastructure", page)
        self.assertIn("worker unavailable", page)
        self.assertNotIn("category: timeout", page)
        self.assertIn('scope="row"', page)

    def test_untrusted_candidate_paths_are_not_links_and_large_durations_are_not_summed(self):
        run = self.root / "unsafe"
        run.mkdir()
        (run / "outside.diff").write_text("secret")
        summary = {"run_id": "unsafe", "status": "completed", "groups": [
            {"agent_id": "solo", "harness_id": "fixture-harness", "baseline": None,
             "selected": [{"candidate_id": "../../outside", "split": "validation"}],
             "final_test": [], "stages": []}]}
        (run / "events.jsonl").write_text("\n".join(json.dumps({
            "event": "trial_completed", "trial_id": f"large-{number}", "agent_id": "solo",
            "harness_id": "fixture-harness", "candidate_id": "../../outside", "status": "passed",
            "metrics": {"task_wall_time_seconds": 10 ** 400},
        }) for number in range(2)) + "\n", encoding="utf-8")
        page = write_html_report(run, summary).read_text(encoding="utf-8")
        self.assertNotIn('href="../', page)
        self.assertNotIn("Summed task wall time", page)
        self.assertNotIn("infs", page)
        self.assertIn("2 completed", page)


if __name__ == "__main__":
    unittest.main()
