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

        self.assertEqual(report["report_schema_version"], 1)
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
