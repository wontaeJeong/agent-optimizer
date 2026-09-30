"""최종 보고서의 native 계약·집계 의미·안전한 표시 회귀 검증."""
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent_optimizer.report_model import build_report
from agent_optimizer.results import write_json, write_report_artifacts


def fixture(root):
    root.mkdir(parents=True, exist_ok=True)
    objective = {"mode": "lexicographic", "keep": 1, "metrics": [
        {"name": "solve_rate", "source": "passed", "aggregate": "mean", "direction": "maximize"}]}
    write_json(root / "manifest.json", {"experiment": {
        "name": "긴 설정·독립 탐색 검증", "benchmark": "데이터/" + "긴경로" * 100,
        "objective": objective, "budget": {"max_trials": 12},
        "stages": [{"id": "search", "optimizer": "gepa"}]}, "benchmark": {"id": "fixture"}})
    common = {"agent_id": "agent", "harness_id": "harness", "split": "validation", "valid": True}
    base = {**common, "candidate_id": "base", "metrics": {"solve_rate": 0}, "trial_count": 1}
    chosen = {**common, "candidate_id": "chosen", "metrics": {"solve_rate": 0.75}, "trial_count": 1}
    summary = {"run_id": "fixture", "status": "partial", "synthetic": True, "trials_used": 3,
               "groups": [{"agent_id": "agent", "harness_id": "harness", "baseline": base,
                           "selected": [chosen], "final_test": [], "trial_count": 2,
                           "stages": [{"id": "search", "optimizer": "gepa", "status": "completed",
                                       "selected": [chosen], "checkpoint": {"frontier": ["chosen"]}}]}]}
    events = [{"event": "candidate_evaluated", **row, "stage_id": stage}
              for stage, row in (("baseline", base), ("search", chosen))]
    events += [{"event": "trial_completed", **common, "trial_id": name, "candidate_id": candidate,
                "stage_id": stage, "task_id": "task", "repeat": 0, "status": status,
                "metrics": {"passed": passed, "task_wall_time_seconds": 1.25}}
               for name, candidate, stage, status, passed in (
                   ("outer-base", "base", "baseline", "failed", 0),
                   ("outer-chosen", "chosen", "search", "passed", 1))]
    return summary, events


def native_payload():
    return {"schema_version": 1, "execution_mode": "native", "source_revision": "fixed",
            "source_hash": "hash", "profile": "native-fixture", "task_id": "task",
            "candidate_hash": "candidate-hash", "status": "completed", "usage_status": "partial",
            "native_wall_time_seconds": 4.5, "generated_files": ["rtl/out.v"],
            "evidence_paths": ["agent/harness/trials/outer-chosen/logs/native-execution.json"],
            "attempts": [{"attempt": 1, "iteration": 2, "status": "passed",
                          "generated_files": ["rtl/out.v"], "hash": "generated-hash"}],
            "requests": [{"request_id": "g-1", "role": "generator", "model": "fixture-model",
                          "status": "completed", "duration_seconds": 0.5,
                          "input_tokens": 7, "output_tokens": None, "cost_usd": None}]}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        self.scripts += tag == "script"
        self.hrefs.extend(value for key, value in attrs if key == "href")


class FinalReportTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.summary, self.events = fixture(self.root)

    def report(self):
        (self.root / "events.jsonl").write_text("\n".join(map(json.dumps, self.events)) + "\n")
        return build_report(self.root, self.summary)

    def artifacts(self):
        self.report()
        write_report_artifacts(self.root, self.summary, language="ko")
        return (json.loads((self.root / "report.json").read_text()),
                (self.root / "report.html").read_text(), (self.root / "report.md").read_text())

    def test_optional_native_is_scoped_to_outer_trial_and_has_renderer_parity(self):
        self.events[-1]["native_execution"] = native_payload()
        report, page, markdown = self.artifacts()
        self.assertIn("native_execution", report)
        row = report["native_execution"][0]
        self.assertEqual(row["evaluation_ref"], "agent/harness/outer-chosen")
        self.assertEqual(row["native_wall_time_seconds"], 4.5)
        self.assertEqual(row["usage_status"], "partial")
        self.assertIsNone(row["requests"][0]["output_tokens"])
        self.assertEqual(report["counts"]["completed_evaluations"], 2)
        for content in (page, markdown):
            self.assertIn("outer-chosen", content)
            self.assertIn("내부 attempt", content)
            self.assertIn("generator", content)
            self.assertIn("4.5", content)
            self.assertIn("부분 수집", content)

    def test_native_drops_private_unknown_fields_and_unsafe_paths_without_reading_sidecar(self):
        payload = native_payload()
        payload.update(prompt="PRIVATE_SENTINEL", private_evaluator="PRIVATE_SENTINEL")
        payload["requests"][0]["prompt"] = "PRIVATE_SENTINEL"
        payload["attempts"][0]["rtl"] = "PRIVATE_SENTINEL"
        payload["evidence_paths"] += ["../../private.json", "https://secret.invalid", ".env", "missing.json"]
        self.events[-1]["native_execution"] = payload
        report, page, markdown = self.artifacts()
        for content in (json.dumps(report), page, markdown):
            self.assertNotIn("PRIVATE_SENTINEL", content)
        parser = Links()
        parser.feed(page)
        self.assertFalse(any("native-execution" in href or "private.json" in href for href in parser.hrefs))
        self.assertEqual(report["native_execution"][0]["evidence_paths"], [])

    def test_native_duplicate_request_ids_and_invalid_numbers_downgrade_complete_usage(self):
        payload = native_payload()
        payload["usage_status"] = "complete"
        payload["requests"] += [dict(payload["requests"][0])]
        payload["requests"][0]["input_tokens"] = -3
        payload["requests"][0]["duration_seconds"] = True
        self.events[-1]["native_execution"] = payload
        report = self.report()
        self.assertIn("native_execution", report)
        native = report["native_execution"][0]
        self.assertEqual(native["usage_status"], "partial")
        self.assertEqual(len(native["requests"]), 1)
        self.assertIsNone(native["requests"][0]["input_tokens"])
        self.assertIsNone(native["requests"][0]["duration_seconds"])
        self.assertTrue(native["warnings"])
        self.assertEqual(report["evidence"]["status"], "warning")

    def test_invalid_native_schema_warns_and_legacy_has_no_empty_native_section(self):
        legacy, page, _ = self.artifacts()
        self.assertNotIn("native_execution", legacy)
        self.assertNotIn('id="native-execution"', page)
        self.events[-1]["native_execution"] = {"schema_version": 2, "prompt": "PRIVATE_SENTINEL"}
        report, page, _ = self.artifacts()
        self.assertTrue(any(w["code"] == "native_execution_invalid" for w in report["evidence"]["warnings"]))
        self.assertNotIn("PRIVATE_SENTINEL", page)

    def test_each_stage_progress_restarts_from_shared_baseline(self):
        self.events.insert(2, {**self.events[1], "stage_id": "second", "candidate_id": "second",
                               "metrics": {"solve_rate": 0.5}})
        progress = self.report()["groups"][0]["visualization"]["progress"]
        self.assertEqual(progress[2]["improvement"], "improved")
        self.assertEqual(progress[2]["best_metrics"], {"solve_rate": 0.5})
        _, page, _ = self.artifacts()
        self.assertIn("각 단계는 기준 후보에서 독립적으로 시작", page)

    def test_partial_final_test_and_null_baseline_are_visible_in_all_renderers(self):
        group = self.summary["groups"][0]
        group["baseline"]["metrics"]["solve_rate"] = None
        self.events[0]["metrics"] = {"solve_rate": None}
        group["final_test"] = [{**group["selected"][0], "split": "test", "partial": True,
                                "valid": False, "metrics": {"solve_rate": None}}]
        report, page, markdown = self.artifacts()
        self.assertIsNone(report["groups"][0]["comparison"][0]["delta"])
        final = page.split('id="held-out-test"', 1)[1].split('</section>', 1)[0]
        self.assertIn("부분 집계", final)
        self.assertIn("무효", final)
        final_md = markdown.split("## 최종 테스트", 1)[1].split("##", 1)[0]
        self.assertIn("부분 집계", final_md)
        self.assertIn("무효", final_md)
        self.assertIn("null", final_md)

    def test_native_rendering_escapes_injection_in_labels_and_markdown_cells(self):
        payload = native_payload()
        payload["requests"][0]["model"] = '</script><script>bad()</script>|모델'
        self.events[-1]["native_execution"] = payload
        _, page, markdown = self.artifacts()
        parser = Links()
        parser.feed(page)
        self.assertEqual(parser.scripts, 0)
        self.assertIn("&lt;/script&gt;", page)
        self.assertIn("\\|모델", markdown)

    def test_algorithm_trail_keeps_real_review_role_acceptance_and_unknown_fallback(self):
        self.summary["groups"][0]["stages"] = [
            {"id": "search", "optimizer": "ecdysis", "status": "interrupted", "checkpoint": {}},
            {"id": "custom", "optimizer": "unknown", "status": "completed", "checkpoint": {}}]
        self.events += [{"event": "optimizer_review_started", "agent_id": "agent", "harness_id": "harness",
                         "stage_id": "search", "iteration": 1, "pass_number": 2, "role": "moderator"},
                        {"event": "optimizer_iteration_completed", "agent_id": "agent", "harness_id": "harness",
                         "stage_id": "search", "iteration": 1, "candidate_id": "chosen", "accepted": False},
                        {"event": "optimizer_probe_completed", "agent_id": "agent", "harness_id": "harness",
                         "stage_id": "custom", "status": "completed"}]
        report, page, markdown = self.artifacts()
        self.assertIn("algorithm_trail", report["groups"][0])
        for content in (page, markdown):
            self.assertIn("moderator", content)
            self.assertIn("미채택", content)
            self.assertIn("optimizer_probe_completed", content.replace("\\_", "_"))
        self.assertNotIn("reflection_completed", page)

    def test_nonfinite_exponent_event_metrics_become_null_with_warning(self):
        self.events[-1]["metrics"]["agent_cost_usd"] = float("inf")
        source = "\n".join(map(json.dumps, self.events)).replace("Infinity", "1e999")
        (self.root / "events.jsonl").write_text(source)
        report = build_report(self.root, self.summary)
        self.assertIsNone(report["groups"][0]["evaluations"][-1]["metrics"]["agent_cost_usd"])
        json.dumps(report, allow_nan=False)
        self.assertTrue(any(w["code"] == "nonfinite_values" for w in report["evidence"]["warnings"]))

    def test_arbitrary_artifact_and_credential_paths_never_become_convenience_links(self):
        (self.root / ".env").write_text("비밀 아님: fixture")
        (self.root / "private-evaluator.txt").write_text("공개 금지 fixture")
        self.events[-1]["artifacts"] = {"credential": ".env", "private": "private-evaluator.txt"}
        self.events[-1]["execution"] = {"stdout_path": ".env", "stderr_path": "private-evaluator.txt"}
        _, page, _ = self.artifacts()
        parser = Links()
        parser.feed(page)
        self.assertNotIn(".env", parser.hrefs)
        self.assertNotIn("private-evaluator.txt", parser.hrefs)

    def test_large_unknown_event_timeline_has_display_cap_without_truncating_json(self):
        self.events += [{"event": "optimizer_probe_completed", "agent_id": "agent", "harness_id": "harness",
                         "stage_id": "search", "candidate_id": f"probe-{i}"} for i in range(1000)]
        report, page, _ = self.artifacts()
        self.assertEqual(len(report["events"]), 1004)
        self.assertIn("표시 상한", page)
        self.assertIn("전체 기록은 report.json", page)
        self.assertLess(len(page.encode()), 300_000)

    def test_complete_native_usage_requires_all_values_and_keeps_zero_as_collected(self):
        payload = native_payload()
        payload["usage_status"] = "complete"
        payload["evidence_paths"] = []
        payload["requests"][0].update(input_tokens=0, output_tokens=0, cost_usd=0)
        self.events[-1]["native_execution"] = payload
        report = self.report()
        self.assertEqual(report["native_execution"][0]["usage_status"], "complete")
        self.assertEqual(report["native_execution"][0]["requests"][0]["cost_usd"], 0)

    def test_native_present_evidence_is_local_only_and_symlinks_are_rejected(self):
        payload = native_payload()
        relative = payload["evidence_paths"][0]
        path = self.root / relative
        path.parent.mkdir(parents=True)
        path.write_text("PRIVATE_SENTINEL")
        self.events[-1]["native_execution"] = payload
        report, page, _ = self.artifacts()
        self.assertEqual(report["native_execution"][0]["evidence_paths"], [relative])
        self.assertNotIn("PRIVATE_SENTINEL", page)
        parser = Links()
        parser.feed(page)
        self.assertNotIn(relative, parser.hrefs)
        path.unlink()
        path.symlink_to(self.root / "manifest.json")
        self.assertEqual(self.report()["native_execution"][0]["evidence_paths"], [])

    def test_branching_lineage_and_optimizer_kinds_do_not_invent_trace(self):
        for optimizer in ("gepa", "meta_harness", "ecdysis", "file_variants", "unknown"):
            with self.subTest(optimizer=optimizer):
                self.summary["groups"][0]["stages"][0]["optimizer"] = optimizer
                self.events += [{"event": "optimizer_merge_completed", "agent_id": "agent", "harness_id": "harness",
                                 "stage_id": "search", "candidate_id": "chosen", "parents": ["left", "right"]}]
                report, page, _ = self.artifacts()
                self.assertEqual(report["groups"][0]["structure"]["edges"][0]["parents"], ["left", "right"])
                self.assertIn(optimizer, page)
                self.assertNotIn("reflection_completed", page)

    def test_artifact_generation_preserves_raw_events_summary_and_frozen_selection(self):
        self.events[-1]["native_execution"] = native_payload()
        write_json(self.root / "summary.json", self.summary)
        write_json(self.root / "agent/harness/frozen_selection.json", {"selected": ["chosen"]})
        self.report()
        names = ("events.jsonl", "summary.json", "agent/harness/frozen_selection.json")
        before = {name: (self.root / name).read_bytes() for name in names}
        write_report_artifacts(self.root, self.summary, language="ko")
        for name in names:
            self.assertEqual((self.root / name).read_bytes(), before[name])

    def test_empty_final_test_metrics_are_recorded_not_misreported_as_no_test(self):
        self.summary["groups"][0]["final_test"] = [{"candidate_id": "test-only", "split": "test",
                                                    "valid": False, "metrics": {}}]
        _, _, markdown = self.artifacts()
        self.assertIn("test-only", markdown)
        self.assertNotIn("기록된 최종 테스트 없음", markdown)

    def test_native_payload_must_match_outer_task_and_recorded_group(self):
        payload = native_payload()
        payload["task_id"] = "different-task"
        self.events[-1]["native_execution"] = payload
        report = self.report()
        self.assertNotIn("native_execution", report)
        self.assertTrue(any(w["code"] == "native_execution_invalid" for w in report["evidence"]["warnings"]))
        payload["task_id"] = "task"
        self.events[-1]["agent_id"] = "unrecorded-group"
        self.assertNotIn("native_execution", self.report())

    def test_c_generated_file_records_keep_hashes_and_logs_relative_local_evidence(self):
        payload = native_payload()
        relative = "native/attempt_1/iter_02/real_evaluator_result.json"
        logs = self.root / "agent/harness/trials/outer-chosen/logs"
        evidence = logs / relative
        evidence.parent.mkdir(parents=True)
        evidence.write_text("PRIVATE_SENTINEL")
        file = {"path": "rtl/out.v", "sha256": "a" * 64, "evidence_path": relative,
                "content": "PRIVATE_SENTINEL"}
        payload["generated_files"] = [file]
        payload["attempts"][0].update(generated_files=[file], evidence_path=relative)
        payload["evidence_paths"] = ["native"]
        self.events[-1]["native_execution"] = payload
        report, page, markdown = self.artifacts()
        native = report["native_execution"][0]
        self.assertEqual(native["generated_files"], ["rtl/out.v"])
        self.assertEqual(native["generated_file_hashes"], {"rtl/out.v": "a" * 64})
        self.assertEqual(native["attempts"][0]["evidence_paths"],
                         ["agent/harness/trials/outer-chosen/logs/" + relative])
        self.assertIn("a" * 64, page)
        self.assertIn("a" * 64, markdown)
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(report))

    def test_recorded_stdout_absolute_path_inside_own_trial_retains_local_link(self):
        relative = "agent/harness/trials/outer-chosen/logs/stdout.log"
        path = self.root / relative
        path.parent.mkdir(parents=True)
        path.write_text("공개 fixture 로그")
        self.events[-1]["execution"] = {"status": "completed", "stdout_path": str(path)}
        _, page, _ = self.artifacts()
        parser = Links()
        parser.feed(page)
        self.assertIn(relative, parser.hrefs)

    def test_native_nul_paths_warn_without_losing_outer_report_or_inventing_usage(self):
        payload = native_payload()
        payload["evidence_paths"] = ["native/bad\x00.json"]
        payload["generated_files"] = ["rtl/bad\x00.v"]
        payload["attempts"][0]["evidence_path"] = "native/attempt\x00.json"
        self.events[-1]["native_execution"] = payload
        report, page, markdown = self.artifacts()
        row = report["native_execution"][0]
        self.assertEqual(row["evidence_paths"], [])
        self.assertEqual(row["generated_files"], [])
        self.assertEqual(row["attempts"][0]["evidence_paths"], [])
        self.assertIn("unsafe_path", row["warnings"])
        self.assertIsNone(row["requests"][0]["cost_usd"])
        self.assertIsNone(row["requests"][0]["output_tokens"])
        self.assertEqual(report["counts"]["completed_evaluations"], 2)
        for content in (page, markdown):
            self.assertIn("outer-base", content)
            self.assertIn("outer-chosen", content)

    def test_native_unhashable_outer_identity_only_excludes_optional_payload(self):
        for field in ("agent_id", "harness_id", "trial_id"):
            for value in (["malformed"], {"malformed": "identity"}):
                with self.subTest(field=field, value=value):
                    self.summary, self.events = fixture(self.root)
                    malformed = {**self.events[-1], field: value, "native_execution": native_payload()}
                    self.events.append(malformed)
                    report, page, markdown = self.artifacts()
                    self.assertNotIn("native_execution", report)
                    self.assertTrue(any(w["code"] == "native_execution_invalid"
                                        for w in report["evidence"]["warnings"]))
                    self.assertEqual([row["trial_id"] for row in report["groups"][0]["evaluations"][:2]],
                                     ["outer-base", "outer-chosen"])
                    for content in (page, markdown):
                        self.assertIn("outer-chosen", content)

    def test_native_filesystem_path_error_is_warning_not_report_failure(self):
        self.events[-1]["native_execution"] = native_payload()
        self.events[-1]["native_execution"]["evidence_paths"] = ["native/denied.json"]
        from agent_optimizer.workspace import safe_path

        def denied_native_path(root, relative):
            if relative.endswith("native/denied.json"):
                raise PermissionError("fixture 경로 접근 거부")
            return safe_path(root, relative)

        with patch("agent_optimizer.report_model.safe_path", side_effect=denied_native_path):
            report, page, markdown = self.artifacts()
        self.assertIn("evidence_unavailable", report["native_execution"][0]["warnings"])
        self.assertEqual(report["counts"]["completed_evaluations"], 2)
        self.assertIn("outer-chosen", page)
        self.assertIn("outer-chosen", markdown)

    def test_ineligible_baseline_never_seeds_or_suppresses_validation_progress(self):
        for invalid in ({"split": "train"}, {"split": "test"}, {"split": None},
                        {"agent_id": "foreign"}, {"harness_id": "foreign"},
                        {"valid": False}, {"partial": True}):
            with self.subTest(invalid=invalid):
                self.summary, self.events = fixture(self.root)
                baseline = self.summary["groups"][0]["baseline"]
                baseline.update(invalid)
                baseline["metrics"] = {"solve_rate": 0.9}
                # Same candidate ID: an ineligible summary must not suppress real validation evidence.
                self.events[0].update(stage_id="search", metrics={"solve_rate": 0.3})
                self.events[1]["metrics"] = {"solve_rate": 0.5}
                self.summary["groups"][0]["selected"][0]["metrics"] = {"solve_rate": 0.5}
                report, page, _ = self.artifacts()
                group = report["groups"][0]
                self.assertIsNone(group["comparison"][0]["baseline"])
                self.assertIsNone(group["comparison"][0]["delta"])
                self.assertEqual([row["improvement"] for row in group["visualization"]["progress"]],
                                 ["first", "improved"])
                self.assertEqual([row["best_metrics"] for row in group["visualization"]["progress"]],
                                 [{"solve_rate": 0.3}, {"solve_rate": 0.5}])
                self.assertIn('id="progress-0"', page)

    def test_markdown_algorithm_trail_keeps_review_pass_numbers_and_null(self):
        self.events += [{"event": "optimizer_review_started", "agent_id": "agent", "harness_id": "harness",
                         "stage_id": "search", "iteration": 1, "role": "moderator", "pass_number": number}
                        for number in (1, 2, None)]
        report, page, markdown = self.artifacts()
        self.assertEqual([row["pass_number"] for row in report["groups"][0]["algorithm_trail"][0]["events"][-3:]],
                         [1, 2, None])
        self.assertIn("검토 회차", page)
        self.assertIn("| 이벤트 | 반복 | 역할 | 검토 회차 | 후보 | 데이터 구분 | 상태 |", markdown)
        for number in ("1", "2", "null"):
            self.assertIn(f"| optimizer\\_review\\_started | 1 | moderator | {number} | null | null | null |", markdown)

    def test_ineligible_unobserved_baseline_does_not_supply_validation_best(self):
        for invalid in ({"split": "train"}, {"split": "test"},
                        {"agent_id": "foreign"}, {"harness_id": "foreign"}):
            with self.subTest(invalid=invalid):
                self.summary, self.events = fixture(self.root)
                baseline = self.summary["groups"][0]["baseline"]
                baseline.update(invalid)
                baseline["metrics"] = {"solve_rate": 0.9}
                self.events[0].update(candidate_id="first-observed", stage_id="search",
                                      metrics={"solve_rate": 0.3})
                self.events[1]["metrics"] = {"solve_rate": 0.5}
                self.summary["groups"][0]["selected"][0]["metrics"] = {"solve_rate": 0.5}
                report = self.report()
                group = report["groups"][0]
                self.assertIsNone(group["comparison"][0]["baseline"])
                self.assertEqual([row["best_metrics"] for row in group["visualization"]["progress"]],
                                 [{"solve_rate": 0.3}, {"solve_rate": 0.5}])


if __name__ == "__main__":
    unittest.main()
