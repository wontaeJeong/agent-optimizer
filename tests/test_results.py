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
