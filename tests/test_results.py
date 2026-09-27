import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.results import write_report


class UsageReportTests(unittest.TestCase):
    def test_multiple_valid_selected_candidates_are_not_called_incomparable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(json.dumps({"experiment": {"objective": {
                "metrics": [{"name": "score", "direction": "maximize"}]}}}))
            def row(candidate, score):
                return {"agent_id": "a", "harness_id": "h", "candidate_id": candidate,
                        "split": "validation", "valid": True, "metrics": {"score": score}}
            write_report(root, {"groups": [{"agent_id": "a", "harness_id": "h",
                "baseline": row("base", 0), "selected": [row("first", 1), row("second", 1)],
                "final_test": [], "stages": []}]})
            markdown = (root / "report.md").read_text()
            self.assertIn("first", markdown)
            self.assertIn("second", markdown)
            self.assertNotIn("비교 불가 선택 기록: a/h · second", markdown)

    def test_incomparable_selection_note_does_not_split_later_group_validation_table(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(json.dumps({"experiment": {"objective": {
                "metrics": [{"name": "score", "direction": "maximize"}]}}}))
            def row(agent, candidate, score, valid=True):
                return {"agent_id": agent, "harness_id": "fixture", "candidate_id": candidate,
                        "split": "validation", "valid": valid, "metrics": {"score": score}}
            write_report(root, {"groups": [
                {"agent_id": "first", "harness_id": "fixture", "baseline": row("first", "base", 0),
                 "selected": [row("first", "bad", 1, False)], "stages": [], "final_test": []},
                {"agent_id": "second", "harness_id": "fixture", "baseline": row("second", "base", 0),
                 "selected": [row("second", "chosen", 1)], "stages": [], "final_test": []}]})
            validation = (root / "report.md").read_text().split("## 기준 → 선택 검증", 1)[1].split(
                "## 최종 테스트", 1)[0]
            self.assertLess(validation.index("| second | fixture | chosen |"),
                            validation.index("비교 불가 선택 기록"))

    def test_all_artifacts_warn_when_completed_events_exceed_recorded_group_trials(self):
        from agent_optimizer.results import write_report_artifacts

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(json.dumps({"experiment": {"objective": {
                "metrics": [{"name": "latency", "direction": "minimize"}]}}}))
            def row(agent, candidate, number):
                return {"agent_id": agent, "harness_id": "fixture", "candidate_id": candidate,
                        "split": "validation", "valid": True, "trial_count": 1,
                        "metrics": {"latency": number}}
            summary = {"status": "partial", "trials_used": 3, "groups": [
                {"agent_id": "a", "harness_id": "fixture", "trial_count": 1,
                 "baseline": row("a", "base", 9), "selected": [row("a", "chosen", 7)],
                 "final_test": [{**row("a", "chosen", 4), "split": "test"}], "stages": []},
                {"agent_id": "b", "harness_id": "fixture", "trial_count": 1,
                 "baseline": row("b", "base", 5), "selected": [row("b", "base", 5)],
                 "final_test": [], "stages": []}]}
            (root / "events.jsonl").write_text("\n".join(json.dumps({
                "event": "trial_completed", "agent_id": agent, "harness_id": "fixture",
                "trial_id": f"t{index}", "status": "passed"})
                for index, agent in enumerate(("a", "b", "unknown"))) + "\n{broken\n")
            write_report_artifacts(root, summary)
            model = json.loads((root / "report.json").read_text())
            markdown = (root / "report.md").read_text()
            html = (root / "report.html").read_text()
            self.assertEqual(model["report_schema_version"], 3)
            self.assertEqual(model["evidence"]["completed_events"], 3)
            self.assertEqual(model["counts"]["completed_evaluations"], 2)
            self.assertIn({"code": "group_trial_count_mismatch", "group_key": None,
                           "expected": 2, "observed": 3}, model["evidence"]["warnings"])
            self.assertIn("읽지 못한 이벤트 줄", markdown)
            self.assertIn("읽지 못한 이벤트 줄", html)
            self.assertIn("그룹 평가 건수 불일치", markdown)
            self.assertIn("그룹 평가 건수 불일치", html)
            self.assertIn("| a | fixture | chosen | latency | minimize | 9 | 7 | -2 | improved |",
                          markdown)
            self.assertIn("| a | fixture | chosen | test | latency | 4 | 1 |", markdown)
            self.assertIn("완료된 평가 2건", html)
            self.assertIn("latency", html)
            self.assertIn("chosen", html)
            self.assertEqual([group["counts"]["completed_evaluations"] for group in model["groups"]],
                             [1, 1])
            self.assertEqual([group["comparison_trend"] for group in model["groups"]],
                             ["improved", "unchanged"])

    def test_markdown_separates_validation_test_and_links_recorded_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(json.dumps({"experiment": {"objective": {
                "metrics": [{"name": "accuracy", "direction": "maximize"},
                            {"name": "latency", "direction": "minimize"}]}}}))
            group_root = root / "a" / "h"
            for relative in ("stages/search.json", "candidates/chosen/changes.diff",
                             "trials/trial-1/result.json"):
                path = group_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}")
            (group_root / "candidates/chosen/candidate.json").write_text(json.dumps({
                "id": "chosen", "parents": ["base"], "changed_files": ["prompt.txt"]}))
            (root / "events.jsonl").write_text(json.dumps({
                "event": "trial_completed", "agent_id": "a", "harness_id": "h",
                "trial_id": "trial-1", "candidate_id": "chosen", "split": "validation",
                "status": "failed", "feedback": "bad"}) + "\n")
            (root / "summary.json").write_text("{}")
            def row(candidate, split, accuracy, latency):
                return {"agent_id": "a", "harness_id": "h", "candidate_id": candidate,
                        "split": split, "valid": True, "trial_count": 1,
                        "metrics": {"accuracy": accuracy, "latency": latency}}
            summary = {"status": "completed", "trials_used": 1, "groups": [{
                "agent_id": "a", "harness_id": "h", "trial_count": 1,
                "baseline": row("base", "validation", 0.5, 9),
                "selected": [row("chosen", "validation", 0.5, 7)],
                "final_test": [row("base", "test", 0.4, 10),
                               row("chosen", "test", 0.9, 6)],
                "stages": [{"id": "search", "status": "completed",
                            "selected": [row("chosen", "validation", 0.5, 7)],
                            "checkpoint": {"private": "X" * 300}}]}]}
            write_report(root, summary)
            markdown = (root / "report.md").read_text()
            validation = markdown.split("## 기준 → 선택 검증", 1)[1].split("## 최종 테스트", 1)[0]
            test = markdown.split("## 최종 테스트", 1)[1].split("## ", 1)[0]
            self.assertIn("chosen", validation)
            self.assertIn("latency", validation)
            self.assertIn("minimize", validation)
            self.assertNotIn("| test |", validation)
            self.assertIn("| chosen | test |", test)
            self.assertIn("[changes.diff](a/h/candidates/chosen/changes.diff)", markdown)
            self.assertIn("[search.json](a/h/stages/search.json)", markdown)
            self.assertIn("[trial-1](a/h/trials/trial-1/result.json)", markdown)
            self.assertIn("실패 [trial-1](a/h/trials/trial-1/result.json)", markdown)
            self.assertIn("[events.jsonl](events.jsonl)", markdown)
            self.assertNotIn("X" * 100, markdown)

    def test_markdown_escapes_html_fences_and_long_untrusted_identifiers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            malicious = "a|<img src=x> **bold** [link](javascript:alert(1)) ```\n# heading"
            summary = {"status": "error", "error_type": "RuntimeError",
                       "error": malicious + "L" * 1000, "groups": [{
                "agent_id": malicious, "harness_id": "h", "baseline": None,
                "selected": [], "final_test": [], "stages": []}]}
            write_report(root, summary)
            markdown = (root / "report.md").read_text()
            self.assertNotIn("<img", markdown)
            self.assertNotIn("**bold**", markdown)
            self.assertNotIn("[link](javascript:", markdown)
            self.assertNotIn("\n# heading", markdown)
            self.assertNotIn("```", markdown)
            self.assertIn(r"a\|&lt;img", markdown)
            self.assertLess(len(markdown), 6000)

    def test_markdown_title_follows_language_without_changing_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = {"status": "completed", "groups": []}
            with patch.dict(os.environ, {"AGENT_OPT_LANG": "ko"}):
                write_report(root, summary)
            self.assertTrue((root / "report.md").read_text().startswith("# 실험 보고서\n"))
            with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}):
                write_report(root, summary)
            self.assertTrue((root / "report.md").read_text().startswith("# Experiment report\n"))
            self.assertEqual(summary, {"status": "completed", "groups": []})

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
            self.assertIn("하네스 보고 일부", report)

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
            self.assertIn("| a | h | unknown | 0 완료 | 0 | 0 | score | -1e+308 | 1e+308 | null |", markdown)
            self.assertIn("알 수 없음", html)
            self.assertIn("검증에서 선택된 후보", html)
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
                self.assertIn(trend, markdown)
                self.assertIn({"improved": "개선", "regressed": "악화"}[trend], html)
                self.assertIn("1 완료", markdown)
                self.assertIn("완료 1건", html)
            self.assertIn("사용한 평가 예산: 3; 완료된 평가: 2", markdown)

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
            optimization = markdown.split("## 최적화\n\n", 1)[1].split("## 재현 정보", 1)[0]
            self.assertTrue(optimization.startswith(
                "| Agent | 하네스 | 단계 | 상태 | 후보 |\n"
                "|---|---|---|---|---|\n"
                "| alpha | fixture | prepare | completed | — |\n"
                "| alpha | fixture | polish | completed | — |\n"
                "| beta | fixture | inspect | completed | — |\n\n"), optimization)
            self.assertIn("단계별 선택·체크포인트 원본", optimization)
            self.assertIn("실패 alpha/fixture/failed-alpha: scored_failure — first group failed", optimization)
            self.assertIn("## 최종 테스트", markdown)
            self.assertIn("| alpha | fixture | c1 | test |", markdown)
            self.assertIn("하네스 보고 사용량은 일부일 수 있습니다.", markdown)

    def test_markdown_escapes_untrusted_table_cells_and_keeps_missing_usage_null(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = {"status": "completed", "synthetic": True, "groups": [
                {"agent_id": "a|b", "harness_id": "fixture", "baseline": None,
                 "selected": [{"candidate_id": "c|d", "split": "validation", "trial_count": 1,
                               "metrics": {"label": "x|y"}}], "final_test": [],
                 "stages": [{"id": "s|t", "status": "completed", "checkpoint": {"key": "a|b"}}]}]}

            from agent_optimizer.results import write_report_artifacts
            write_report_artifacts(root, summary)
            markdown = (root / "report.md").read_text()
            self.assertIn(r"| a\|b | fixture | c\|d | validation |", markdown)
            self.assertNotIn(r"x\|y", markdown)
            self.assertIn('"x|y"', (root / "report.json").read_text())
            self.assertIn("[report.json](report.json)", markdown)
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

    def test_markdown_missing_run_failure_reason_is_not_stringified_none(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_report(root, {"status": "interrupted", "groups": [],
                                "run_wall_time_seconds": 3.25})
            markdown = (root / "report.md").read_text(encoding="utf-8")
            self.assertIn("실행 실패: interrupted — 기록되지 않음", markdown)
            self.assertNotIn("실행 실패: interrupted — None", markdown)
            self.assertIn("실측 실행 시간: 3.25 s", markdown)
            write_report(root, {"status": "interrupted", "groups": []})
            self.assertNotIn("실측 실행 시간:", (root / "report.md").read_text(encoding="utf-8"))
