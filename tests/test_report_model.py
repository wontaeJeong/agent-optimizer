"""저장된 실행 증거를 그룹별 공통 리포트 모델로 보존한다."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_optimizer.report_model import build_report


class ReportModelTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def candidate(self, agent, harness, candidate_id, parents=(), diff=""):
        directory = self.root / agent / harness / "candidates" / candidate_id
        directory.mkdir(parents=True)
        (directory / "candidate.json").write_text(json.dumps({
            "id": candidate_id, "parents": list(parents), "producer": "fixture",
            "changed_files": ["prompt.txt"] if parents else [],
        }), encoding="utf-8")
        (directory / "changes.diff").write_text(diff, encoding="utf-8")
        (directory / "bundle").mkdir()

    def manifest_objective(self, metrics):
        (self.root / "manifest.json").write_text(json.dumps({
            "experiment": {"objective": {"mode": "lexicographic", "metrics": metrics}},
        }), encoding="utf-8")

    def group(self, baseline=None, selected=None, final_test=None, **fields):
        return {"agent_id": "agent-a", "harness_id": "harness", "baseline": baseline,
                "selected": selected if selected is not None else [],
                "final_test": final_test if final_test is not None else [], **fields}

    def row(self, metrics, **fields):
        return {"candidate_id": "c0001", "agent_id": "agent-a", "harness_id": "harness",
                "split": "validation", "valid": True, "metrics": metrics} | fields

    def events(self, rows):
        (self.root / "events.jsonl").write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    def test_progress_uses_recorded_validation_aggregates_and_lexicographic_best(self):
        self.manifest_objective([{"name": "solve_rate", "direction": "maximize"},
                                 {"name": "seconds", "direction": "minimize"}])
        base = self.row({"solve_rate": 0.5, "seconds": 12}, candidate_id="base")
        chosen = self.row({"solve_rate": 0.5, "seconds": 10}, candidate_id="chosen")
        common = {"agent_id": "agent-a", "harness_id": "harness", "split": "validation"}
        self.events([{"event": "candidate_evaluated", **common, "stage_id": stage,
                      "candidate_id": candidate, "valid": valid, "metrics": score,
                      "trial_ids": [trial]}
                     for stage, candidate, valid, score, trial in (
                         ("baseline", "base", True, base["metrics"], "b"),
                         ("search", "rejected", True, {"solve_rate": 0.5, "seconds": 11}, "r"),
                         ("search", "chosen", True, chosen["metrics"], "c"),
                         ("search", "not-final", True, {"solve_rate": 0.8, "seconds": 15}, "n"),
                         ("search", "broken", False, {"solve_rate": 1.0, "seconds": 1}, "x"))])
        report = build_report(self.root, {"groups": [self.group(base, [chosen])]})
        points = report["groups"][0]["visualization"]["progress"]
        self.assertEqual([p["improvement"] for p in points],
                         ["baseline", "improved", "improved", "improved", "invalid"])
        self.assertEqual([p["best_metrics"]["solve_rate"] if p["best_metrics"] else None
                          for p in points], [0.5, 0.5, 0.5, 0.8, 0.8])
        self.assertEqual([p["selected"] for p in points], [False, False, True, False, False])
        self.assertEqual(points[3]["source"], "candidate_evaluated")
        self.assertEqual(points[2]["trial_refs"], ["agent-a/harness/c"])
        self.assertEqual(report["report_schema_version"], 2)

    def test_conflicting_summary_and_aggregate_events_do_not_claim_a_progress_curve(self):
        self.manifest_objective([{"name": "score", "direction": "maximize"}])
        base = self.row({"score": 0.4}, candidate_id="base")
        chosen = self.row({"score": 0.8}, candidate_id="chosen")
        self.events([{"event": "candidate_evaluated", "agent_id": "agent-a", "harness_id": "harness",
                      "split": "validation", "candidate_id": name, "valid": True,
                      "metrics": {"score": score}} for name, score in (("base", 0.5), ("chosen", 0.9))])
        group = build_report(self.root, {"groups": [self.group(base, [chosen])]})["groups"][0]
        self.assertEqual(group["visualization"]["progress"], [])
        self.assertEqual(group["comparison"][0]["delta"], 0.4)

    def test_trial_timeline_and_task_comparison_keep_real_split_and_duration(self):
        self.manifest_objective([{"name": "solve_rate", "source": "passed",
                                 "direction": "maximize", "aggregate": "mean"}])
        base = self.row({"solve_rate": 0.0}, candidate_id="base")
        chosen = self.row({"solve_rate": 1.0}, candidate_id="best")
        common = {"event": "trial_completed", "agent_id": "agent-a", "harness_id": "harness",
                  "task_id": "alu", "stage_id": "search", "repeat": 0}
        self.events([{**common, "candidate_id": "base", "trial_id": "b", "split": "validation",
                      "status": "failed", "valid": True,
                      "metrics": {"passed": 0, "task_wall_time_seconds": 2.5}},
                     {**common, "candidate_id": "best", "trial_id": "s", "split": "validation",
                      "status": "passed", "valid": True,
                      "metrics": {"passed": 1, "task_wall_time_seconds": 1.0}},
                     {**common, "candidate_id": "best", "trial_id": "t", "split": "test",
                      "status": "passed", "valid": True,
                      "metrics": {"passed": 1, "task_wall_time_seconds": 99}},
                     {**common, "candidate_id": "best", "trial_id": "i", "split": "train",
                      "status": "infrastructure_error", "valid": False,
                      "metrics": {"passed": None, "task_wall_time_seconds": None}}])
        visual = build_report(self.root, {"groups": [self.group(base, [chosen])]})["groups"][0]["visualization"]
        self.assertEqual(visual["task_comparison"], [
            {"task_id": "alu", "baseline": "failed", "selected": "passed"}])
        self.assertEqual([row["duration_seconds"] for row in visual["trial_timeline"]],
                         [2.5, 1.0, 99, None])
        self.assertEqual(visual["outcomes"]["infrastructure"], 1)
        self.assertEqual(visual["outcomes"]["scored_failure"], 1)

    def test_missing_aggregate_events_never_invents_progress(self):
        self.manifest_objective([{"name": "score", "direction": "maximize"}])
        visual = build_report(self.root, {"groups": [self.group(
            self.row({"score": 0}, candidate_id="base"),
            [self.row({"score": 1}, candidate_id="best")])]})["groups"][0]["visualization"]
        self.assertEqual(visual["progress"], [])
        self.assertEqual(visual["trial_timeline"], [])

    def test_aggregate_only_candidate_is_available_to_visual_trail(self):
        self.manifest_objective([{"name": "score", "direction": "maximize"}])
        self.events([{"event": "candidate_evaluated", "agent_id": "agent-a",
                     "harness_id": "harness", "candidate_id": "aggregate-only",
                     "split": "validation", "valid": True, "metrics": {"score": 2}}])
        group = build_report(self.root, {"groups": [self.group()]})["groups"][0]
        self.assertEqual([item["candidate_id"] for item in group["candidates"]], ["aggregate-only"])
        self.assertEqual(group["visualization"]["progress"][0]["improvement"], "first")

    def test_common_iteration_events_keep_recorded_order_without_checkpoint_inference(self):
        self.events([{"event": "optimizer_iteration_started", "agent_id": "agent-a",
                      "harness_id": "harness", "stage_id": "search", "optimizer": "unknown",
                      "iteration": number, "candidate_id": "A"}
                     for number in (2, 1)])
        group = build_report(self.root, {"groups": [self.group(
            stages=[{"id": "search", "checkpoint": {"generations": [0, 1]}}])]})["groups"][0]

        self.assertEqual(group["structure"]["kind"], "iteration")
        self.assertEqual([u["unit_id"] for u in group["structure"]["units"]],
                         ["search/iteration-2", "search/iteration-1"])
        self.assertEqual(group["structure"]["units"][0]["candidate_ids"], ["A"])

    def test_explicit_generations_allow_multiple_candidates_and_unassessed_members(self):
        for name in ("A", "B", "C"):
            self.candidate("agent-a", "harness", name)
        self.events([{"event": "report_unit", "agent_id": "agent-a", "harness_id": "harness",
                      "stage_id": "search", "unit_id": "g0", "unit_type": "generation",
                      "label": "Generation 0", "candidate_ids": ["A", "B"]},
                     {"event": "report_unit", "agent_id": "agent-a", "harness_id": "harness",
                      "stage_id": "search", "unit_id": "g1", "parent_unit_id": "g0",
                      "unit_type": "generation", "label": "Generation 1",
                      "candidate_ids": ["B", "C"]},
                     {"event": "trial_completed", "agent_id": "agent-a", "harness_id": "harness",
                      "trial_id": "one", "candidate_id": "A", "stage_id": "search",
                      "split": "train", "status": "passed"}])
        group = build_report(self.root, {"groups": [self.group()]})["groups"][0]

        self.assertEqual(group["structure"]["kind"], "generation")
        self.assertEqual([u["unit_id"] for u in group["structure"]["units"]], ["g0", "g1"])
        self.assertEqual(group["structure"]["units"][1]["parent_unit_id"], "g0")
        self.assertEqual(group["structure"]["units"][1]["candidate_ids"], ["B", "C"])
        self.assertEqual(group["structure"]["units"][0]["evaluation_refs"], [])
        self.assertEqual(len(group["evaluations"]), 1)
        self.assertEqual(len(group["candidates"]), 3)

    def test_reused_unit_ids_in_distinct_stages_have_unambiguous_parent_refs(self):
        self.events([{"event": "report_unit", "agent_id": "agent-a", "harness_id": "harness",
                      "stage_id": stage, "unit_id": unit_id, "parent_unit_id": parent,
                      "unit_type": "generation", "label": unit_id, "candidate_ids": [candidate]}
                     for stage, unit_id, parent, candidate in (
                         ("search", "g0", None, "A"), ("refine", "g0", None, "B"),
                         ("refine", "g1", "g0", "B"), ("search", "g1", "g0", "A"))])

        units = build_report(self.root, {"groups": [self.group()]})["groups"][0]["structure"]["units"]

        self.assertEqual([u["unit_id"] for u in units], ["g0", "g0", "g1", "g1"])
        self.assertEqual([u.get("unit_ref") for u in units],
                         ["agent-a/harness/search/report_unit/g0",
                          "agent-a/harness/refine/report_unit/g0",
                          "agent-a/harness/refine/report_unit/g1",
                          "agent-a/harness/search/report_unit/g1"])
        self.assertEqual([u.get("parent_unit_ref") for u in units],
                         [None, None, "agent-a/harness/refine/report_unit/g0",
                          "agent-a/harness/search/report_unit/g0"])
        self.assertEqual([u["parent_unit_id"] for u in units], [None, None, "g0", "g0"])
        self.assertEqual([u["candidate_ids"] for u in units], [["A"], ["B"], ["B"], ["A"]])

    def test_unit_evaluation_refs_require_explicit_matching_stage_split_and_candidate(self):
        common = {"agent_id": "agent-a", "harness_id": "harness", "candidate_id": "A"}
        self.events([
            {"event": "report_unit", **common, "stage_id": "search", "unit_id": "g0",
             "unit_type": "generation", "candidate_ids": ["A"],
             "evaluation_refs": ["agent-a/harness/train", "agent-a/harness/validation",
                                 "agent-a/harness/test", "agent-a/harness/other-stage",
                                 "agent-a/harness/other-candidate", "other/harness/foreign"]},
            {"event": "report_unit", **common, "stage_id": "search", "unit_id": "g1",
             "unit_type": "generation", "candidate_ids": ["A"]},
            *[{"event": "trial_completed", **common, "trial_id": trial, "stage_id": stage,
               "split": split, "status": "passed"}
              for trial, stage, split in (("train", "search", "train"),
                                          ("validation", "search", "validation"),
                                          ("test", "search", "test"),
                                          ("other-stage", "refine", "train"))],
            {"event": "trial_completed", **(common | {"candidate_id": "B"}),
             "trial_id": "other-candidate", "stage_id": "search", "split": "train",
             "status": "passed"},
        ])

        units = build_report(self.root, {"groups": [self.group()]})["groups"][0]["structure"]["units"]
        self.assertEqual(units[0]["evaluation_refs"],
                         ["agent-a/harness/train", "agent-a/harness/validation"])
        self.assertEqual(units[1]["evaluation_refs"], [])

    def test_unit_evaluation_refs_respect_declared_split_and_repeated_unit_events(self):
        common = {"event": "report_unit", "agent_id": "agent-a", "harness_id": "harness",
                  "stage_id": "search", "unit_id": "g0", "unit_type": "generation",
                  "candidate_ids": ["A"]}
        self.events([
            {**common, "split": "train", "evaluation_refs": ["agent-a/harness/a"]},
            {**common, "split": "validation", "evaluation_refs": ["agent-a/harness/b"]},
            *[{"event": "trial_completed", "agent_id": "agent-a", "harness_id": "harness",
               "candidate_id": "A", "stage_id": "search", "trial_id": trial,
               "split": split, "status": "passed"}
              for trial, split in (("a", "train"), ("b", "validation"))],
        ])
        unit = build_report(self.root, {"groups": [self.group()]})["groups"][0]["structure"]["units"][0]
        self.assertEqual(unit["evaluation_refs"], ["agent-a/harness/a", "agent-a/harness/b"])

    def test_unscoped_unit_cannot_claim_unscoped_trial_as_related(self):
        self.events([{"event": "report_unit", "agent_id": "agent-a", "harness_id": "harness",
                      "unit_id": "g0", "unit_type": "generation", "candidate_ids": ["A"],
                      "evaluation_refs": ["agent-a/harness/unknown"]},
                     {"event": "trial_completed", "agent_id": "agent-a", "harness_id": "harness",
                      "trial_id": "unknown", "candidate_id": "A", "split": "train",
                      "status": "passed"}])
        unit = build_report(self.root, {"groups": [self.group()]})["groups"][0]["structure"]["units"][0]
        self.assertEqual(unit["evaluation_refs"], [])

    def test_wall_time_is_reported_only_when_measured_in_summary(self):
        summary = {"groups": [], "run_wall_time_seconds": 2.125}
        self.assertEqual(build_report(self.root, summary)["identity"]["run_wall_time_seconds"], 2.125)
        for summary in ({"groups": []}, {"groups": [], "run_wall_time_seconds": None},
                        {"groups": [], "run_wall_time_seconds": float('inf')}):
            self.assertNotIn("run_wall_time_seconds", build_report(self.root, summary)["identity"])

    def test_explicit_iteration_name_cannot_resolve_parent_to_automatic_iteration(self):
        common = {"agent_id": "agent-a", "harness_id": "harness", "stage_id": "search"}
        self.events([{"event": "optimizer_iteration_started", **common, "iteration": 1,
                      "candidate_id": "A"},
                     {"event": "report_unit", **common, "unit_id": "branch",
                      "parent_unit_id": "iteration-1", "unit_type": "branch",
                      "label": "Branch", "candidate_ids": ["B"]},
                     {"event": "report_unit", **common, "unit_id": "iteration-1",
                      "unit_type": "phase", "label": "Explicit phase", "candidate_ids": ["C"]},
                     {"event": "optimizer_iteration_completed", **common, "iteration": 1,
                      "candidate_id": "D"},
                     {"event": "report_unit", **common, "unit_id": "orphan",
                      "parent_unit_id": "missing", "unit_type": "branch",
                      "label": "Unlinked", "candidate_ids": ["E"]}])
        units = build_report(self.root, {"groups": [self.group()]})["groups"][0]["structure"]["units"]

        self.assertEqual([u["unit_id"] for u in units],
                         ["search/iteration-1", "branch", "iteration-1", "orphan"])
        self.assertEqual([u["unit_ref"] for u in units],
                         ["agent-a/harness/search/iteration-1",
                          "agent-a/harness/search/report_unit/branch",
                          "agent-a/harness/search/report_unit/iteration-1",
                          "agent-a/harness/search/report_unit/orphan"])
        self.assertEqual(units[1]["parent_unit_ref"], units[2]["unit_ref"])
        self.assertNotEqual(units[1]["parent_unit_ref"], units[0]["unit_ref"])
        self.assertIsNone(units[3]["parent_unit_ref"])
        self.assertEqual(units[3]["parent_unit_id"], "missing")
        self.assertEqual(units[0]["candidate_ids"], ["A", "D"])

    def test_repeated_explicit_unit_id_merges_members_without_ambiguous_parent(self):
        common = {"event": "report_unit", "agent_id": "agent-a", "harness_id": "harness",
                  "stage_id": "search", "unit_type": "generation"}
        self.events([{**common, "unit_id": unit, "parent_unit_id": parent,
                      "label": label, "candidate_ids": candidates}
                     for unit, parent, label, candidates in (
                         ("g0", None, "First", ["A"]), ("g0", None, "Repeated", ["A", "B"]),
                         ("g1", "g0", "Child", ["C"]), ("g1", "g0", "Child", ["D"]),
                         ("g2", "g0", "Conflicting", ["E"]),
                         ("g2", "g1", "Conflicting", ["F"]))])
        units = build_report(self.root, {"groups": [self.group()]})["groups"][0]["structure"]["units"]

        self.assertEqual([u["unit_id"] for u in units], ["g0", "g1", "g2"])
        self.assertEqual([u["candidate_ids"] for u in units],
                         [["A", "B"], ["C", "D"], ["E", "F"]])
        self.assertEqual(units[0]["label"], "First")
        self.assertEqual(units[1]["parent_unit_ref"], units[0]["unit_ref"])
        self.assertIsNone(units[2]["parent_unit_ref"])
        self.assertIsNone(units[2]["parent_unit_id"])

    def test_merge_event_preserves_multiple_parents_independent_of_candidate_metadata(self):
        for name, parents in (("A", ()), ("B", ("A",)), ("C", ("A",)), ("D", ("B",))):
            self.candidate("agent-a", "harness", name, parents)
        self.events([{"event": "optimizer_merge_completed", "agent_id": "agent-a",
                      "harness_id": "harness", "stage_id": "search", "candidate_id": "D",
                      "parents": ["B", "C"]}])
        group = build_report(self.root, {"groups": [self.group()]})["groups"][0]

        self.assertTrue(group["structure"].get("edges"), "merge lineage must be present")
        self.assertEqual(group["structure"]["edges"][-1]["parents"], ["B", "C"])
        self.assertEqual(group["structure"]["edges"][-1]["candidate_id"], "D")
        self.assertEqual(next(c for c in group["candidates"] if c["candidate_id"] == "D")["parents"],
                         ["B", "C"])

    def test_unknown_optimizer_with_no_units_falls_back_to_recorded_lineage_and_evaluations(self):
        self.candidate("agent-a", "harness", "A")
        self.candidate("agent-a", "harness", "B", ("A",))
        self.events([{"event": "trial_completed", "agent_id": "agent-a", "harness_id": "harness",
                      "trial_id": "only", "candidate_id": "A", "status": "passed"}])
        group = build_report(self.root, {"groups": [self.group(stages=[
            {"id": "search", "optimizer": "unknown", "checkpoint": {"iterations": [1, 2]}}])]})["groups"][0]

        self.assertEqual(group["structure"]["units"], [])
        self.assertTrue(group["structure"].get("edges"), "recorded lineage must be present")
        self.assertEqual(group["structure"]["edges"][0]["parents"], ["A"])
        self.assertEqual([r["trial_id"] for r in group["evaluations"]], ["only"])

    def test_minimize_comparison_uses_validation_aggregates_not_test(self):
        self.manifest_objective([{"name": "latency", "direction": "minimize", "aggregate": "mean"}])
        baseline = self.row({"latency": 12})
        chosen = self.row({"latency": 9}, candidate_id="c0002")
        test = self.row({"latency": 100}, split="test", candidate_id="c0002")

        group = build_report(self.root, {"groups": [self.group(baseline, [chosen], [test])]})["groups"][0]

        self.assertEqual(group["comparison"], [{"name": "latency", "direction": "minimize",
                                                "baseline": 12, "selected": 9, "delta": -3,
                                                "trend": "improved"}])
        self.assertEqual(group["comparison_trend"], "improved")
        self.assertEqual(group["final_test"], [test])

    def test_lexicographic_comparison_uses_first_different_metric(self):
        self.manifest_objective([{"name": "accuracy", "direction": "maximize"},
                                 {"name": "latency", "direction": "minimize"}])
        baseline = self.row({"accuracy": 0.8, "latency": 12})
        selected = self.row({"accuracy": 0.8, "latency": 9})
        group = build_report(self.root, {"groups": [self.group(baseline, [selected])]})["groups"][0]

        self.assertEqual([row["trend"] for row in group["comparison"]],
                         ["unchanged", "improved"])
        self.assertEqual(group["comparison_trend"], "improved")

        selected["metrics"] = {"accuracy": 0.7, "latency": 1}
        group = build_report(self.root, {"groups": [self.group(baseline, [selected])]})["groups"][0]
        self.assertEqual([row["trend"] for row in group["comparison"]],
                         ["regressed", "improved"])
        self.assertEqual(group["comparison_trend"], "regressed")

    def test_missing_or_invalid_baseline_and_non_validation_selected_are_not_comparable(self):
        self.manifest_objective([{"name": "latency", "direction": "minimize"}])
        selected = self.row({"latency": 9})
        groups = [self.group(None, [selected]),
                  self.group(self.row({"latency": 12}, valid=False), [selected]),
                  self.group(self.row({"latency": 12}), [self.row({"latency": 1}, split="test")]),
                  self.group(self.row({"latency": 12}),
                             [self.row({"latency": 1}, agent_id="agent-b")]),
                  self.group(self.row({"latency": 12}),
                             [self.row({"latency": 1}, partial=True)])]
        results = build_report(self.root, {"groups": groups})["groups"]

        self.assertEqual(results[0]["comparison"][0]["baseline"], None)
        self.assertEqual(results[0]["comparison"][0]["delta"], None)
        self.assertEqual(results[0]["comparison_trend"], "unknown")
        self.assertEqual(results[1]["comparison"][0]["trend"], "unknown")
        self.assertEqual(results[2]["comparison"], [])
        self.assertEqual(results[3]["comparison"], [])
        self.assertEqual(results[4]["comparison"], [])

    def test_missing_objective_does_not_claim_unchanged_performance(self):
        group = build_report(self.root, {"groups": [self.group(
            self.row({"latency": 12}), [self.row({"latency": 9})])]})["groups"][0]

        self.assertEqual(group["comparison"], [])
        self.assertEqual(group["comparison_trend"], "unknown")

    def test_passed_mean_fraction_has_percentage_point_delta_only_when_confirmed(self):
        self.manifest_objective([{"name": "solve_rate", "source": "passed",
                                 "direction": "maximize", "aggregate": "mean"},
                                 {"name": "quality", "source": "quality",
                                  "direction": "maximize", "aggregate": "mean"}])
        group = build_report(self.root, {"groups": [self.group(
            self.row({"solve_rate": 0.5, "quality": 0.5}),
            [self.row({"solve_rate": 0.75, "quality": 0.75})])]})["groups"][0]

        self.assertEqual(group["comparison"][0]["delta_pp"], 25)
        self.assertNotIn("delta_pp", group["comparison"][1])

        group = build_report(self.root, {"groups": [self.group(
            self.row({"solve_rate": 0.5}), [self.row({"solve_rate": 1.5})])]})["groups"][0]
        self.assertNotIn("delta_pp", group["comparison"][0])

        self.manifest_objective([{"name": "solve_rate", "source": "passed",
                                 "direction": "maximize", "aggregate": "sum"}])
        group = build_report(self.root, {"groups": [self.group(
            self.row({"solve_rate": 0.5}), [self.row({"solve_rate": 0.75})])]})["groups"][0]
        self.assertNotIn("delta_pp", group["comparison"][0])

    def test_completed_counts_distinguish_budget_and_explicit_failure_causes(self):
        events = [
            {"event": "trial_completed", "trial_id": "infra", "agent_id": "agent-a",
             "harness_id": "harness", "status": "infrastructure_error", "feedback": "agent failed",
             "execution": {"status": "infrastructure_error", "detail": "worker unavailable"}},
            {"event": "trial_completed", "trial_id": "time", "agent_id": "agent-a",
             "harness_id": "harness", "status": "timeout", "feedback": "deadline exceeded",
             "execution": {"status": "timeout", "detail": "timed out"}},
            {"event": "trial_completed", "trial_id": "score", "agent_id": "agent-b",
             "harness_id": "harness", "status": "failed", "feedback": "timeout mentioned in feedback",
             "execution": {"status": "completed", "detail": ""}},
        ]
        (self.root / "events.jsonl").write_text(
            "\n".join(json.dumps(row) for row in events) + "\n", encoding="utf-8")
        report = build_report(self.root, {"trials_used": 4, "groups": [
            self.group(trials_used=2), {"agent_id": "agent-b", "harness_id": "harness"}]})

        self.assertEqual(report["counts"]["evaluations"], 3)
        self.assertEqual(report["counts"]["trials_used"], 4)
        self.assertEqual(report["counts"]["failed_evaluations"], 3)
        self.assertEqual(report["counts"]["passed_evaluations"], 0)
        self.assertEqual(report["groups"][0]["counts"]["evaluations"], 2)
        self.assertEqual(report["groups"][0]["counts"]["trials_used"], 2)
        self.assertIsNone(report["groups"][1]["counts"]["trials_used"])
        self.assertEqual([row["category"] for group in report["groups"]
                          for row in group["failures"]],
                         ["infrastructure", "timeout", "scored_failure"])
        self.assertEqual(report["groups"][0]["failures"][0]["message"], "worker unavailable")
        self.assertEqual(report["groups"][1]["failures"][0]["message"],
                         "timeout mentioned in feedback")

    def test_agent_usage_requires_every_expected_valid_trial_for_each_metric(self):
        group = self.group(
            {"candidate_id": "base", "split": "validation", "trial_count": 2},
            [{"candidate_id": "chosen", "split": "validation", "trial_count": 2}])
        self.events([{"event": "trial_completed", "agent_id": "agent-a", "harness_id": "harness",
                      "candidate_id": candidate, "split": "validation", "valid": valid,
                      "metrics": {"harness_reported_io_tokens": tokens,
                                  "harness_reported_cost_usd": cost}}
                     for candidate, valid, tokens, cost in (
                         ("base", True, 3, 0.2), ("base", True, 4, None),
                         ("chosen", True, 5, 0.1), ("chosen", False, 6, 0.2))])

        usage = build_report(self.root, {"groups": [group]})["groups"][0]["agent_usage"]

        self.assertEqual(usage, [
            {"candidate_id": "base", "split": "validation",
             "harness_reported_io_tokens": 7, "harness_reported_cost_usd": None},
            {"candidate_id": "chosen", "split": "validation",
             "harness_reported_io_tokens": None, "harness_reported_cost_usd": None},
        ])

    def test_agent_usage_distinguishes_missing_valid_from_explicit_null(self):
        self.events([{"event": "trial_completed", "agent_id": "agent-a", "harness_id": "harness",
                      "candidate_id": "missing-valid", "split": "validation",
                      "metrics": {"harness_reported_io_tokens": 3}},
                     {"event": "trial_completed", "agent_id": "agent-a", "harness_id": "harness",
                      "candidate_id": "invalid", "split": "validation", "valid": None,
                      "metrics": {"harness_reported_io_tokens": 4}}])
        rows = [{"candidate_id": name, "split": "validation", "trial_count": 1}
                for name in ("missing-valid", "invalid")]

        usage = build_report(self.root, {"groups": [self.group(selected=rows)]})["groups"][0]["agent_usage"]

        self.assertEqual([item["harness_reported_io_tokens"] for item in usage], [3, None])

    def test_agent_usage_overflow_is_null_while_independent_finite_cost_is_preserved(self):
        self.events([{"event": "trial_completed", "agent_id": "agent-a", "harness_id": "harness",
                      "candidate_id": "c1", "split": "validation", "valid": True,
                      "metrics": {"harness_reported_io_tokens": 1e308,
                                  "harness_reported_cost_usd": cost}}
                     for cost in (0.5, 0.25)])
        row = {"candidate_id": "c1", "split": "validation", "trial_count": 2}

        report = build_report(self.root, {"groups": [self.group(selected=[row])]})

        self.assertEqual(report["groups"][0]["agent_usage"], [{
            "candidate_id": "c1", "split": "validation",
            "harness_reported_io_tokens": None, "harness_reported_cost_usd": 0.75}])
        json.dumps(report, allow_nan=False)

    def test_large_integer_usage_sum_is_null_without_discarding_other_usage(self):
        self.events([{"event": "trial_completed", "agent_id": "agent-a", "harness_id": "harness",
                      "candidate_id": "c1", "split": "validation", "valid": True,
                      "metrics": {"harness_reported_io_tokens": 10**308,
                                  "harness_reported_cost_usd": cost}}
                     for cost in (1, 2)])
        row = {"candidate_id": "c1", "split": "validation", "trial_count": 2}

        report = build_report(self.root, {"groups": [self.group(selected=[row])]})

        self.assertEqual(report["groups"][0]["agent_usage"], [{
            "candidate_id": "c1", "split": "validation",
            "harness_reported_io_tokens": None, "harness_reported_cost_usd": 3}])
        json.dumps(report, allow_nan=False)

    def test_unrepresentable_integer_usage_value_is_null(self):
        self.events([{"event": "trial_completed", "agent_id": "agent-a", "harness_id": "harness",
                      "candidate_id": "c1", "split": "validation", "valid": True,
                      "metrics": {"harness_reported_io_tokens": 10**400}}])
        row = {"candidate_id": "c1", "split": "validation", "trial_count": 1}

        report = build_report(self.root, {"groups": [self.group(selected=[row])]})

        self.assertIsNone(report["groups"][0]["agent_usage"][0]["harness_reported_io_tokens"])
        json.dumps(report, allow_nan=False)

    def test_overflowing_validation_delta_keeps_scores_but_trend_unknown(self):
        self.manifest_objective([{"name": "quality", "direction": "maximize"},
                                 {"name": "latency", "direction": "minimize"}])
        baseline = self.row({"quality": -1e308, "latency": 1e308})
        selected = self.row({"quality": 1e308, "latency": -1e308}, candidate_id="c0002")

        report = build_report(self.root, {"groups": [self.group(baseline, [selected])]})
        group = report["groups"][0]

        self.assertEqual(group["baseline"], baseline)
        self.assertEqual(group["selected"], [selected])
        self.assertEqual(group["comparison"], [
            {"name": "quality", "direction": "maximize", "baseline": -1e308,
             "selected": 1e308, "delta": None, "trend": "unknown"},
            {"name": "latency", "direction": "minimize", "baseline": 1e308,
             "selected": -1e308, "delta": None, "trend": "unknown"}])
        self.assertEqual(group["comparison_trend"], "unknown")
        json.dumps(report, allow_nan=False)

    def test_explicit_execution_and_error_type_classification_never_uses_feedback(self):
        events = [
            {"event": "trial_completed", "trial_id": "execution", "agent_id": "agent-a",
             "harness_id": "harness", "status": "failed", "feedback": "bad score",
             "execution": {"status": "unsupported", "detail": "adapter unavailable"}},
            {"event": "trial_completed", "trial_id": "error", "agent_id": "agent-a",
             "harness_id": "harness", "status": "error", "feedback": "timeout word",
             "error_type": "RuntimeError", "error": "optimizer raised"},
            {"event": "trial_completed", "trial_id": "explicit-timeout", "agent_id": "agent-a",
             "harness_id": "harness", "status": "error", "error_type": "TimeoutError",
             "error": "deadline reached"},
        ]
        (self.root / "events.jsonl").write_text(
            "\n".join(json.dumps(row) for row in events) + "\n", encoding="utf-8")
        report = build_report(self.root, {"status": "error", "error_type": "RuntimeError",
                                        "error": "run stopped", "groups": [self.group()]})

        self.assertEqual([row["category"] for row in report["groups"][0]["failures"]],
                         ["unsupported", "run_error", "timeout"])
        self.assertEqual(report["groups"][0]["failures"][1]["message"], "optimizer raised")
        self.assertEqual(report["identity"]["failure"],
                         {"category": "run_error", "message": "run stopped"})

    def test_nonzero_process_status_is_counted_as_execution_failure(self):
        event = {"event": "trial_completed", "trial_id": "nonzero", "agent_id": "agent-a",
                 "harness_id": "harness", "status": "process_error", "feedback": "",
                 "execution": {"status": "process_error", "returncode": 2, "detail": ""}}
        (self.root / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

        report = build_report(self.root, {"groups": [self.group()]})
        group = report["groups"][0]

        self.assertEqual(group["evaluations"][0]["failure"],
                         {"category": "execution", "message": None})
        self.assertEqual(group["failures"], [{"evaluation_ref": "agent-a/harness/nonzero",
                                              "category": "execution", "message": None}])
        self.assertEqual(group["counts"]["failed_evaluations"], 1)
        self.assertEqual(report["counts"]["failed_evaluations"], 1)

    def test_failed_score_with_process_error_execution_is_not_scored_failure(self):
        event = {"event": "trial_completed", "trial_id": "mismatch", "agent_id": "agent-a",
                 "harness_id": "harness", "status": "failed", "feedback": "low score",
                 "execution": {"status": "process_error", "returncode": 1,
                               "detail": "command exited nonzero"}}
        (self.root / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

        report = build_report(self.root, {"groups": [self.group()]})
        group = report["groups"][0]

        self.assertEqual(group["evaluations"][0]["failure"],
                         {"category": "execution", "message": "command exited nonzero"})
        self.assertEqual(group["failures"][0]["category"], "execution")
        self.assertEqual(group["counts"]["failed_evaluations"], 1)

    def test_partial_run_and_non_failure_status_are_not_labeled_as_failures(self):
        events = [
            {"event": "trial_completed", "trial_id": "one", "agent_id": "agent-a",
             "harness_id": "harness", "status": "passed"},
            {"event": "trial_completed", "trial_id": "two", "agent_id": "agent-a",
             "harness_id": "harness", "status": "completed"},
            {"event": "trial_completed", "trial_id": "unknown", "agent_id": "agent-a",
             "harness_id": "harness", "status": "future_status"},
        ]
        (self.root / "events.jsonl").write_text(
            "\n".join(json.dumps(row) for row in events) + "\n", encoding="utf-8")

        report = build_report(self.root, {"status": "partial", "groups": [self.group()]})

        self.assertNotIn("failure", report["identity"])
        self.assertEqual(report["counts"]["evaluations"], 3)
        self.assertEqual(report["counts"]["passed_evaluations"], 1)
        self.assertEqual(report["counts"]["failed_evaluations"], 0)
        self.assertEqual(report["groups"][0]["failures"], [])

    def test_preserves_selection_and_repeated_evaluations_across_groups(self):
        objective = {"metrics": [{"name": "cost", "direction": "minimize"}]}
        (self.root / "manifest.json").write_text(json.dumps({
            "run_id": "run-1", "benchmark": {"id": "sample"},
            "experiment": {"name": "sample", "objective": objective, "budget": {"max_trials": 9}},
        }), encoding="utf-8")
        self.candidate("agent-a", "harness", "c0001")
        self.candidate("agent-a", "harness", "c0002", ["c0001"], "+patched\n")
        self.candidate("agent-b", "harness", "c0001")
        selected = {"candidate_id": "c0002", "split": "validation", "valid": True,
                    "metrics": {"cost": 2.5}, "trial_count": 2}
        summary = {"run_id": "run-1", "status": "completed", "synthetic": True,
                   "trials_used": 4, "groups": [
                       {"agent_id": "agent-a", "harness_id": "harness",
                        "baseline": {"candidate_id": "c0001", "metrics": {"cost": 3.0}},
                        "selected": [selected], "final_test": [],
                        "stages": [{"id": "stage-1", "checkpoint": {"raw": "kept"}}]},
                       {"agent_id": "agent-b", "harness_id": "harness", "baseline": None,
                        "selected": [], "final_test": [], "stages": []},
                   ]}
        records = [
            {"event": "trial_completed", "trial_id": f"a-{repeat}", "agent_id": "agent-a",
             "harness_id": "harness", "candidate_id": "c0001", "task_id": "task-1",
             "stage_id": "baseline", "split": "validation", "repeat": repeat,
             "seed_requested": 11 + repeat, "status": "passed", "valid": True,
             "metrics": {"cost": 3.0 + repeat}, "feedback": f"repeat {repeat}",
             "execution": {"status": "completed"}, "artifacts": {"log": "log.txt"},
             "timestamp": f"2026-09-25T00:00:0{repeat}Z"}
            for repeat in range(2)
        ]
        records.append({"event": "trial_completed", "trial_id": "b-0", "agent_id": "agent-b",
                        "harness_id": "harness", "candidate_id": "c0001", "task_id": "task-2",
                        "split": "train", "repeat": 0, "status": "failed", "valid": True,
                        "metrics": {"cost": 7.0}, "feedback": "failure", "execution": None})
        (self.root / "events.jsonl").write_text(
            "\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")

        report = build_report(self.root, summary)

        self.assertEqual(report["report_schema_version"], 2)
        self.assertEqual(report["identity"], {"run_id": "run-1", "status": "completed",
                                               "synthetic": True})
        self.assertEqual(report["objective"], objective)
        self.assertEqual(report["events"], records)
        first, second = report["groups"]
        self.assertEqual(first["selected"], summary["groups"][0]["selected"])
        self.assertEqual(first["baseline"], summary["groups"][0]["baseline"])
        self.assertEqual(first["stages"], summary["groups"][0]["stages"])
        self.assertEqual(first["comparison"], [])
        self.assertEqual(len(first["evaluations"]), 2)
        self.assertEqual([row["trial_id"] for row in first["evaluations"]], ["a-0", "a-1"])
        self.assertEqual([row["repeat"] for row in first["evaluations"]], [0, 1])
        self.assertEqual([row["candidate_ref"] for row in first["evaluations"]],
                         ["agent-a/harness/c0001"] * 2)
        self.assertEqual(first["evaluations"][0]["metrics"], records[0]["metrics"])
        self.assertEqual(first["evaluations"][0]["feedback"], records[0]["feedback"])
        self.assertEqual(first["evaluations"][0]["execution"], records[0]["execution"])
        self.assertEqual(first["evaluations"][0]["artifacts"], records[0]["artifacts"])
        self.assertEqual(first["evaluations"][0]["seed_requested"], 11)
        self.assertEqual(first["candidates"][1]["parents"], ["c0001"])
        self.assertEqual(first["candidates"][1]["diff_preview"], "+patched\n")
        self.assertEqual(first["candidates"][1]["diff_path"],
                         "agent-a/harness/candidates/c0002/changes.diff")
        self.assertNotEqual(first["candidates"][0]["id"], second["candidates"][0]["id"])
        self.assertNotEqual(first["evaluations"][0]["candidate_ref"],
                            second["evaluations"][0]["candidate_ref"])
        self.assertEqual(second["evaluations"][0]["status"], "failed")
        self.assertEqual(report["counts"]["trials_used"], 4)
        self.assertEqual(report["counts"]["completed_evaluations"], 3)
        self.assertEqual(first["counts"]["completed_evaluations"], 2)
        json.dumps(report, allow_nan=False)

    def test_missing_manifest_and_broken_event_lines_preserve_valid_evidence(self):
        self.candidate("agent-a", "harness", "c0001")
        event = {"event": "trial_completed", "trial_id": "one", "agent_id": "agent-a",
                 "harness_id": "harness", "candidate_id": "c0001", "status": "passed"}
        (self.root / "events.jsonl").write_text(
            json.dumps(event) + "\n{broken\n" + json.dumps({"event": "stage_completed"}) + "\n",
            encoding="utf-8")
        summary = {"groups": [{"agent_id": "agent-a", "harness_id": "harness",
                               "selected": [], "final_test": []}]}

        report = build_report(self.root, summary)

        self.assertEqual(report["configuration"], {})
        self.assertEqual(report["provenance"], {})
        self.assertEqual(report["objective"], {})
        self.assertEqual(report["events"], [event, {"event": "stage_completed"}])
        self.assertEqual(len(report["groups"][0]["evaluations"]), 1)
        self.assertEqual(report["groups"][0]["selected"], [])

    def test_invalid_utf8_event_line_does_not_hide_surrounding_evaluations(self):
        first = {"event": "trial_completed", "trial_id": "first", "agent_id": "agent-a",
                 "harness_id": "harness", "candidate_id": "c0001", "status": "passed"}
        last = {"event": "trial_completed", "trial_id": "last", "agent_id": "agent-a",
                "harness_id": "harness", "candidate_id": "c0001", "status": "failed"}
        (self.root / "events.jsonl").write_bytes(
            json.dumps(first).encode() + b"\n" + b'{"event":"broken", "value":"\xff"}\n'
            + json.dumps(last).encode() + b"\n")
        summary = {"groups": [{"agent_id": "agent-a", "harness_id": "harness"}]}

        report = build_report(self.root, summary)

        self.assertEqual(report["events"], [first, last])
        self.assertEqual([row["trial_id"] for row in report["groups"][0]["evaluations"]],
                         ["first", "last"])
        self.assertEqual(report["counts"]["completed_evaluations"], 2)

    def test_recorded_candidates_survive_missing_or_corrupt_metadata(self):
        directory = self.root / "agent-a" / "harness" / "candidates" / "c0002"
        directory.mkdir(parents=True)
        (directory / "candidate.json").write_text("{broken", encoding="utf-8")
        selected = [{"candidate_id": "c0001", "split": "validation", "metrics": {"cost": 1}}]
        event = {"event": "trial_completed", "trial_id": "trial-2", "agent_id": "agent-a",
                 "harness_id": "harness", "candidate_id": "c0002", "status": "passed"}
        (self.root / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
        summary = {"groups": [{"agent_id": "agent-a", "harness_id": "harness",
                               "selected": selected}]}

        report = build_report(self.root, summary)

        group = report["groups"][0]
        self.assertEqual(group["selected"], selected)
        self.assertEqual([item["id"] for item in group["candidates"]],
                         ["agent-a/harness/c0001", "agent-a/harness/c0002"])
        self.assertEqual([item["metadata"] for item in group["candidates"]], [{}, {}])
        self.assertEqual([item["parents"] for item in group["candidates"]], [[], []])
        self.assertEqual(group["evaluations"][0]["candidate_ref"], "agent-a/harness/c0002")
        self.assertEqual(group["counts"]["candidates"], 2)

    def test_unrecorded_directories_require_matching_candidate_metadata(self):
        candidates = self.root / "agent-a" / "harness" / "candidates"
        (candidates / "empty").mkdir(parents=True)
        (candidates / "damaged").mkdir()
        (candidates / "damaged" / "candidate.json").write_text("{broken", encoding="utf-8")
        (candidates / "wrong-id").mkdir()
        (candidates / "wrong-id" / "candidate.json").write_text(
            json.dumps({"id": "someone-else"}), encoding="utf-8")
        self.candidate("agent-a", "harness", "c0003")

        report = build_report(self.root, {"groups": [
            {"agent_id": "agent-a", "harness_id": "harness"}]})

        self.assertEqual([item["candidate_id"] for item in report["groups"][0]["candidates"]],
                         ["c0003"])
        self.assertEqual(report["groups"][0]["counts"]["candidates"], 1)
        self.assertEqual(report["counts"]["candidates"], 1)

    def test_recorded_candidates_with_missing_or_null_metadata_id_hide_metadata(self):
        candidates = self.root / "agent-a" / "harness" / "candidates"
        for candidate_id, metadata in (
            ("c0001", {"parents": ["fabricated"], "producer": "unverified"}),
            ("c0002", {"id": None, "parents": ["fabricated"], "producer": "unverified"}),
        ):
            directory = candidates / candidate_id
            directory.mkdir(parents=True)
            (directory / "candidate.json").write_text(json.dumps(metadata), encoding="utf-8")
        event = {"event": "trial_completed", "trial_id": "trial-2", "agent_id": "agent-a",
                 "harness_id": "harness", "candidate_id": "c0002", "status": "passed"}
        (self.root / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
        summary = {"groups": [{"agent_id": "agent-a", "harness_id": "harness",
                               "selected": [{"candidate_id": "c0001"}]}]}

        report = build_report(self.root, summary)

        group = report["groups"][0]
        self.assertEqual([item["candidate_id"] for item in group["candidates"]], ["c0001", "c0002"])
        self.assertEqual([item["metadata"] for item in group["candidates"]], [{}, {}])
        self.assertEqual([item["parents"] for item in group["candidates"]], [[], []])
        self.assertEqual([item["producer"] for item in group["candidates"]], [None, None])
        self.assertEqual(group["evaluations"][0]["candidate_ref"], "agent-a/harness/c0002")

    def test_untrusted_candidate_id_cannot_read_outside_group(self):
        (self.root / "secret.json").write_text('{"producer": "secret"}', encoding="utf-8")
        summary = {"groups": [{"agent_id": "agent-a", "harness_id": "harness",
                               "selected": [{"candidate_id": "../../secret"}]}]}

        report = build_report(self.root, summary)

        self.assertEqual(report["groups"][0]["selected"], summary["groups"][0]["selected"])
        self.assertEqual(report["groups"][0]["candidates"], [])
        json.dumps(report, allow_nan=False)

    def test_run_error_is_retained_and_candidate_diff_is_bounded(self):
        self.candidate("agent-a", "harness", "c0001", diff="x" * 5000)
        summary = {"status": "error", "error_type": "RuntimeError", "error": "실행 중단",
                   "groups": [{"agent_id": "agent-a", "harness_id": "harness"}]}

        report = build_report(self.root, summary)

        self.assertEqual(report["identity"]["error_type"], "RuntimeError")
        self.assertEqual(report["identity"]["error"], "실행 중단")
        candidate = report["groups"][0]["candidates"][0]
        self.assertEqual(len(candidate["diff_preview"]), 2000)
        self.assertEqual(candidate["snapshot_path"], "agent-a/harness/candidates/c0001/bundle")


if __name__ == "__main__":
    unittest.main()
