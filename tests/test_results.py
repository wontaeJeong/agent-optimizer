import json
import tempfile
import unittest
from pathlib import Path

from agent_optimizer.results import write_report


class UsageReportTests(unittest.TestCase):
    def test_report_shows_observed_partial_usage_without_summing_missing_trials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [{"candidate_id": "c1", "split": "validation", "trial_count": 2, "metrics": {"score": 1}},
                    {"candidate_id": "c2", "split": "validation", "trial_count": 2, "metrics": {"score": 1}}]
            summary = {"status": "completed", "synthetic": True, "groups": [{"agent_id": "a", "harness_id": "h",
                       "baseline": rows[0], "selected": [rows[1]], "final_test": [], "stages": []}]}
            events = [{"event": "trial_completed", "agent_id": "a", "harness_id": "h", "candidate_id": candidate,
                       "split": "validation", "valid": True, "metrics": {"harness_reported_io_tokens": tokens,
                       "harness_reported_cost_usd": None}} for candidate, tokens in [("c1", 3), ("c1", 4), ("c2", 5), ("c2", None)]]
            (root / "events.jsonl").write_text("\n".join(map(json.dumps, events)))
            write_report(root, summary)
            report = (root / "report.md").read_text()
            self.assertIn("| a | h | c1 | validation | 7 | null |", report)
            self.assertIn("| a | h | c2 | validation | null | null |", report)
            self.assertIn("partial", report)

    def test_overflowing_usage_writes_all_artifacts_without_masking_run_error(self):
        from agent_optimizer.results import write_report_artifacts

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = {"candidate_id": "c1", "split": "validation", "trial_count": 2,
                   "metrics": {"score": 1}}
            summary = {"status": "error", "synthetic": True, "error_type": "RuntimeError",
                       "error": "original run error", "groups": [{"agent_id": "a", "harness_id": "h",
                       "baseline": row, "selected": [], "final_test": [], "stages": []}]}
            events = [{"event": "trial_completed", "agent_id": "a", "harness_id": "h",
                       "candidate_id": "c1", "split": "validation", "valid": True,
                       "metrics": {"harness_reported_io_tokens": 1e308}}
                      for _ in range(2)]
            (root / "events.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n")

            self.assertEqual(write_report_artifacts(root, summary), root / "report.html")
            model = json.loads((root / "report.json").read_text())
            self.assertIsNone(model["groups"][0]["agent_usage"][0]["harness_reported_io_tokens"])
            self.assertEqual(model["identity"]["error"], "original run error")
            self.assertIn("| a | h | c1 | validation | null | null |",
                          (root / "report.md").read_text())
            self.assertIn("original run error", (root / "report.html").read_text())

    def test_large_integer_usage_writes_null_without_blocking_artifacts(self):
        from agent_optimizer.results import write_report_artifacts

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = {"candidate_id": "c1", "split": "validation", "trial_count": 2,
                   "metrics": {"score": 1}}
            summary = {"status": "completed", "synthetic": True, "groups": [
                {"agent_id": "a", "harness_id": "h", "baseline": row,
                 "selected": [], "final_test": [], "stages": []}]}
            events = [{"event": "trial_completed", "agent_id": "a", "harness_id": "h",
                       "candidate_id": "c1", "split": "validation", "valid": True,
                       "metrics": {"harness_reported_io_tokens": 10**308}}
                      for _ in range(2)]
            (root / "events.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n")

            self.assertEqual(write_report_artifacts(root, summary), root / "report.html")
            model = json.loads((root / "report.json").read_text())
            self.assertIsNone(model["groups"][0]["agent_usage"][0]["harness_reported_io_tokens"])
            self.assertIn("| a | h | c1 | validation | null | null |",
                          (root / "report.md").read_text())
            self.assertIn("Agent Optimizer", (root / "report.html").read_text())

    def test_unrepresentable_integer_usage_still_renders_html_and_preserves_evidence(self):
        from agent_optimizer.results import write_report_artifacts

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = {"candidate_id": "c1", "split": "validation", "trial_count": 1,
                   "metrics": {"score": 1}}
            summary = {"status": "completed", "synthetic": True, "groups": [
                {"agent_id": "a", "harness_id": "h", "baseline": row,
                 "selected": [], "final_test": [], "stages": []}]}
            event = {"event": "trial_completed", "agent_id": "a", "harness_id": "h",
                     "candidate_id": "c1", "split": "validation", "valid": True,
                     "metrics": {"harness_reported_io_tokens": 10**400}}
            (root / "events.jsonl").write_text(json.dumps(event) + "\n")

            self.assertEqual(write_report_artifacts(root, summary), root / "report.html")
            model = json.loads((root / "report.json").read_text())
            self.assertIsNone(model["groups"][0]["agent_usage"][0]["harness_reported_io_tokens"])
            self.assertEqual(model["groups"][0]["evaluations"][0]["metrics"], event["metrics"])
            self.assertIn("| a | h | c1 | validation | null | null |",
                          (root / "report.md").read_text())
            self.assertIn("harness_reported_io_tokens", (root / "report.html").read_text())

    def test_overflowing_comparison_delta_keeps_raw_scores_in_all_artifacts(self):
        from agent_optimizer.results import write_report_artifacts

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(json.dumps({"experiment": {"objective": {
                "metrics": [{"name": "score", "direction": "maximize"}]}}}))
            def row(candidate, score):
                return {"agent_id": "a", "harness_id": "h", "candidate_id": candidate,
                        "split": "validation", "valid": True, "metrics": {"score": score}}
            baseline, selected = row("base", -1e308), row("chosen", 1e308)
            summary = {"status": "completed", "synthetic": True, "groups": [
                {"agent_id": "a", "harness_id": "h", "baseline": baseline,
                 "selected": [selected], "final_test": [], "stages": []}]}

            self.assertEqual(write_report_artifacts(root, summary), root / "report.html")
            model = json.loads((root / "report.json").read_text())
            group = model["groups"][0]
            self.assertEqual(group["baseline"], baseline)
            self.assertEqual(group["selected"], [selected])
            self.assertEqual(group["comparison"][0]["baseline"], -1e308)
            self.assertEqual(group["comparison"][0]["selected"], 1e308)
            self.assertIsNone(group["comparison"][0]["delta"])
            self.assertEqual(group["comparison_trend"], "unknown")
            markdown = (root / "report.md").read_text()
            html = (root / "report.html").read_text()
            self.assertIn("-1e+308", markdown)
            self.assertIn("1e+308", markdown)
            self.assertIn("| a | h | unknown | 0 completed | 0 | 0 | score | -1e+308 | 1e+308 | null |", markdown)
            self.assertIn("unknown", html)
            self.assertIn("Validation winner", html)
            self.assertIn("chosen", html)

    def test_common_artifacts_compare_two_groups_without_cross_group_ranking(self):
        from agent_optimizer.results import write_report_artifacts

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(json.dumps({"experiment": {"objective": {
                "metrics": [{"name": "score", "direction": "maximize"}]}}}))
            groups = []
            events = []
            for agent, before, after, status in (
                ("alpha", 0.4, 0.8, "passed"), ("beta", 0.9, 0.7, "failed")):
                def row(candidate, score):
                    return {"agent_id": agent, "harness_id": "fixture", "candidate_id": candidate,
                            "split": "validation", "valid": True, "trial_count": 1,
                            "metrics": {"score": score}}
                groups.append({"agent_id": agent, "harness_id": "fixture", "baseline": row("base", before),
                               "selected": [row("chosen", after)], "final_test": [], "stages": []})
                events.append({"event": "trial_completed", "trial_id": agent, "agent_id": agent,
                               "harness_id": "fixture", "candidate_id": "chosen", "split": "validation",
                               "status": status, "valid": True, "metrics": {"score": after}})
            (root / "events.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n")
            summary = {"run_id": "demo", "status": "completed", "synthetic": True,
                       "trials_used": 3, "groups": groups}

            self.assertEqual(write_report_artifacts(root, summary), root / "report.html")
            model = json.loads((root / "report.json").read_text())
            markdown = (root / "report.md").read_text()
            html = (root / "report.html").read_text()
            self.assertEqual([group["selected"] for group in model["groups"]],
                             [group["selected"] for group in groups])
            self.assertEqual([group["comparison_trend"] for group in model["groups"]],
                             ["improved", "regressed"])
            self.assertEqual(model["counts"]["completed_evaluations"], 2)
            for agent, trend in (("alpha", "improved"), ("beta", "regressed")):
                for artifact in (markdown, html):
                    self.assertIn(agent, artifact)
                    self.assertIn(trend, artifact)
                    self.assertIn("1 completed", artifact)
            self.assertIn("Reserved trials: 3; completed evaluations: 2", markdown)

    def test_markdown_keeps_all_stage_rows_together_before_group_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def group(agent, stages):
                validation = {"candidate_id": "c1", "split": "validation", "valid": True,
                              "trial_count": 1, "metrics": {"score": 1}}
                return {"agent_id": agent, "harness_id": "fixture", "baseline": validation,
                        "selected": [validation], "final_test": [
                            {**validation, "split": "test"}],
                        "stages": [{"id": name, "status": "completed", "checkpoint": {}}
                                   for name in stages]}

            summary = {"status": "completed", "synthetic": True, "groups": [
                group("alpha", ["prepare", "polish"]), group("beta", ["inspect"])]}
            (root / "events.jsonl").write_text(json.dumps({
                "event": "trial_completed", "trial_id": "failed-alpha", "agent_id": "alpha",
                "harness_id": "fixture", "candidate_id": "c1", "split": "validation",
                "valid": True, "status": "failed", "feedback": "first group failed",
                "metrics": {"harness_reported_io_tokens": 5}}) + "\n")

            write_report(root, summary)
            markdown = (root / "report.md").read_text()
            optimization = markdown.split("## Optimization\n\n", 1)[1].split("## Reproducibility", 1)[0]
            self.assertTrue(optimization.startswith(
                "| Agent | Harness | Stage | Status | Checkpoint |\n"
                "|---|---|---|---|---|\n"
                "| alpha | fixture | prepare | completed | {} |\n"
                "| alpha | fixture | polish | completed | {} |\n"
                "| beta | fixture | inspect | completed | {} |\n\n"), optimization)
            self.assertIn("Optimizer usage (alpha/fixture):", optimization)
            self.assertIn("Optimizer usage (beta/fixture):", optimization)
            self.assertIn("Failure alpha/fixture/failed-alpha: scored_failure — first group failed", optimization)
            self.assertIn("Candidate changes: see this group's candidates/*/changes.diff.", optimization)
            self.assertIn("| alpha | fixture | c1 | test |", markdown)
            self.assertIn("Harness-reported usage can be partial.", markdown)

    def test_markdown_escapes_untrusted_table_cells_and_keeps_missing_usage_null(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = {"status": "completed", "synthetic": True, "groups": [
                {"agent_id": "a|b", "harness_id": "fixture", "baseline": None,
                 "selected": [{"candidate_id": "c|d", "split": "validation", "trial_count": 1,
                               "metrics": {"label": "x|y"}}], "final_test": [],
                 "stages": [{"id": "s|t", "status": "completed", "checkpoint": {"key": "a|b"}}]}]}

            write_report(root, summary)
            markdown = (root / "report.md").read_text()
            self.assertIn(r"| a\|b | fixture | c\|d | validation |", markdown)
            self.assertIn(r"x\|y", markdown)
            self.assertIn(r"| a\|b | fixture | c\|d | validation | null | null |", markdown)
            self.assertIn(r"s\|t", markdown)

    def test_markdown_uses_recorded_structure_failures_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(json.dumps({"benchmark": {"id": "fixture-set"},
                                                       "benchmark_sha256": "checked-sha"}))
            (root / "events.jsonl").write_text("\n".join(map(json.dumps, [
                {"event": "report_unit", "agent_id": "a", "harness_id": "h", "stage_id": "search",
                 "unit_id": "g0", "unit_type": "generation", "label": "Generation 0",
                 "candidate_ids": ["c1"]},
                {"event": "trial_completed", "agent_id": "a", "harness_id": "h",
                 "trial_id": "trial-1", "candidate_id": "c1", "status": "failed",
                 "feedback": "bad|score"}])) + "\n")
            write_report(root, {"status": "partial", "synthetic": True,
                                "groups": [{"agent_id": "a", "harness_id": "h", "baseline": None,
                                            "selected": [], "final_test": [], "stages": []}]})
            markdown = (root / "report.md").read_text()
            self.assertIn("Generation 0", markdown)
            self.assertIn("scored_failure", markdown)
            self.assertIn("bad\\|score", markdown)
            self.assertIn("fixture-set", markdown)
            self.assertIn("checked-sha", markdown)
