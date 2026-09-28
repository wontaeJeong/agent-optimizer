"""API-free checks for the pinned Verilog-Eval reference verifier."""
import json
import tempfile
import time
import unittest
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, Evaluation, Task
from examples.benchmarks.verify_verilog_eval_full import reference_submission, verify_tasks


REFERENCE = ("  module RefModule(output zero);\n"
             "    // RefModule in a comment must remain unchanged\n"
             "    assign zero = 1'b0;\n"
             "  endmodule\n")
PRIVATE = "private test sentinel: SECRET_TEST"


class RecordingEvaluator:
    def __init__(self, outcomes, source):
        self.outcomes = outcomes
        self.source = source
        self.calls = []

    def evaluate(self, task, output_dir, timeout_seconds):
        self.calls.append(task.id)
        assert timeout_seconds == 90
        assert output_dir.parts[-5:-1] == ("verilog-eval-full", task.evaluation["dataset"],
                                           "cases", task.id)
        assert sorted(path.name for path in output_dir.iterdir()) == ["solution.sv"]
        assert (output_dir / "solution.sv").read_text() == REFERENCE.replace(
            "module RefModule(output", "module TopModule(output")
        assert (self.source / ("dataset_" + task.evaluation["mode"]) /
                f"{task.id}_test.sv").read_text() == PRIVATE
        outcome = self.outcomes[task.id]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class VerilogFullTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "pinned"
        self.run = self.root / "runs/verilog-eval-full"

    def task(self, problem, dataset="verilog-spec", reference=REFERENCE):
        mode = {"verilog-spec": "spec-to-rtl",
                "verilog-completion": "code-complete-iccad2023"}[dataset]
        folder = self.source / ("dataset_" + mode)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (problem + "_ref.sv")).write_text(reference)
        (folder / (problem + "_test.sv")).write_text(PRIVATE)
        return Task(problem, "validation", "public prompt", {"solution.sv": ""},
                    {"source_dir": str(self.source), "problem_id": problem,
                     "mode": mode, "dataset": dataset})

    def test_reference_rewrites_only_single_line_start_declaration_in_both_modes(self):
        for dataset in ("verilog-spec", "verilog-completion"):
            with self.subTest(dataset=dataset):
                task = self.task("Prob001_zero", dataset)
                directory = self.source / ("dataset_" + task.evaluation["mode"])
                original = (directory / "Prob001_zero_ref.sv").read_bytes()
                self.assertEqual(reference_submission(directory, task.id),
                                 REFERENCE.replace("module RefModule(output", "module TopModule(output"))
                self.assertEqual((directory / "Prob001_zero_ref.sv").read_bytes(), original)
                self.assertEqual((directory / "Prob001_zero_test.sv").read_text(), PRIVATE)

    def test_reference_rejects_missing_or_multiple_declarations(self):
        for reference in ("module TopModule(); endmodule", REFERENCE + REFERENCE):
            with self.subTest(reference=reference):
                task = self.task("Prob001_zero", reference=reference)
                with self.assertRaises(ConfigurationError):
                    reference_submission(self.source / "dataset_spec-to-rtl", task.id)

    def test_reference_rejects_symlinks_and_escaping_ids(self):
        task = self.task("Prob001_zero")
        folder = self.source / "dataset_spec-to-rtl"
        (folder / "Prob002_ref.sv").symlink_to(folder / "Prob001_zero_ref.sv")
        for problem in ("Prob002", "../outside", "nested/other", "bad\\id", "bad.txt"):
            with self.subTest(problem=problem), self.assertRaises(ConfigurationError):
                reference_submission(folder, problem)
        linked = self.root / "linked"
        linked.symlink_to(folder, target_is_directory=True)
        with self.assertRaises(ConfigurationError):
            reference_submission(linked, task.id)

    def test_sorted_cases_continue_after_failed_verdict_and_sanitize_feedback(self):
        tasks = [self.task("Prob002"), self.task("Prob001_zero")]
        outcomes = {
            "Prob001_zero": Evaluation("failed", {"passed": 0.0},
                                       "Verilog-Eval: 3 mismatches in 17 samples"),
            "Prob002": Evaluation("passed", {"passed": 1.0},
                                  f"success; {PRIVATE}; /private/test.sv"),
        }
        evaluator = RecordingEvaluator(outcomes, self.source)
        out = self.run / "verilog-spec"
        summary = verify_tasks(tasks, evaluator, out, "verilog-spec")
        self.assertEqual(evaluator.calls, ["Prob001_zero", "Prob002"])
        self.assertEqual(summary["expected"], 156)
        self.assertEqual(summary["attempted"], 2)
        self.assertEqual(summary["unattempted"], 0)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual([case["reason"] for case in summary["cases"]], ["mismatch", "passed"])
        self.assertEqual([case["passed"] for case in summary["cases"]], [0.0, 1.0])
        self.assertEqual(json.loads((out / "summary.json").read_text()), summary)
        self.assertNotIn(PRIVATE, (out / "summary.json").read_text())
        self.assertNotIn("/private/", (out / "summary.json").read_text())

    def test_exception_timeout_null_and_compile_failure_still_visit_remaining_cases(self):
        tasks = [self.task(f"Prob00{number}") for number in (5, 4, 3, 2, 1)]
        outcomes = {
            "Prob001": RuntimeError(f"private reference: {PRIVATE}"),
            "Prob002": Evaluation("timeout", {"passed": 0.0}, PRIVATE),
            "Prob003": None,
            "Prob004": Evaluation("failed", {"passed": 0.0},
                                  "Verilog-Eval compile did not complete"),
            "Prob005": Evaluation("passed", {"passed": 1.0}, PRIVATE),
        }
        evaluator = RecordingEvaluator(outcomes, self.source)
        summary = verify_tasks(tasks, evaluator, self.run / "verilog-spec", "verilog-spec")
        self.assertEqual(evaluator.calls, ["Prob001", "Prob002", "Prob003", "Prob004", "Prob005"])
        self.assertEqual(summary["attempted"], 5)
        self.assertEqual(summary["unattempted"], 0)
        self.assertEqual(summary["failed"], 4)
        self.assertEqual([case["reason"] for case in summary["cases"]],
                         ["infrastructure_error", "timeout", "infrastructure_error",
                          "compile_failure", "passed"])
        self.assertEqual(summary["status"], "failed")
        self.assertNotIn(PRIVATE, json.dumps(summary))

    def test_only_proven_simulation_mismatches_are_labeled_mismatch(self):
        task = self.task("Prob001_zero")
        outcomes = (
            ("RTL solution missing", "reference_invalid"),
            ("Candidate contains unsupported simulation control", "reference_invalid"),
            ("Verilog-Eval: 2 mismatches in 17 samples", "mismatch"),
            ("Verilog-Eval: 0 mismatches in 17 samples", "infrastructure_error"),
            ("Verilog-Eval: 2 mismatches in 0 samples", "infrastructure_error"),
            (f"Verilog-Eval: 2 mismatches in 17 samples; {PRIVATE}", "infrastructure_error"),
            (f"compiler aborted: {PRIVATE}", "infrastructure_error"),
            ("Verilog-Eval compile did not complete", "compile_failure"),
        )
        for number, (feedback, reason) in enumerate(outcomes):
            with self.subTest(feedback=feedback):
                evaluator = RecordingEvaluator({task.id: Evaluation("failed", {"passed": 0.0},
                                                                     feedback)}, self.source)
                out = self.root / f"run{number}" / "verilog-eval-full/verilog-spec"
                summary = verify_tasks([task], evaluator, out, "verilog-spec")
                self.assertEqual(summary["cases"][0]["reason"], reason)
                self.assertEqual(summary["failed"], 1)
                self.assertEqual(summary["status"], "failed")
                self.assertNotIn(PRIVATE, (out / "summary.json").read_text())

    def test_summary_exists_before_first_evaluation_and_counts_only_visited_cases(self):
        tasks = [self.task("Prob002"), self.task("Prob001")]
        out = self.run / "verilog-spec"

        class InspectingEvaluator(RecordingEvaluator):
            def evaluate(inner, task, output_dir, timeout_seconds):
                snapshot = json.loads((out / "summary.json").read_text())
                self.assertEqual(snapshot["attempted"], len(inner.calls))
                self.assertEqual(snapshot["unattempted"], 2 - len(inner.calls))
                self.assertEqual(snapshot["status"], "running")
                return super().evaluate(task, output_dir, timeout_seconds)

        evaluator = InspectingEvaluator({task.id: Evaluation("passed", {"passed": 1.0})
                                         for task in tasks}, self.source)
        summary = verify_tasks(tasks, evaluator, out, "verilog-spec")
        self.assertEqual(summary["attempted"], 2)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["unattempted"], 0)
        self.assertEqual(summary["status"], "failed")  # A two-case fixture is not 156 cases.

    def test_bad_reference_is_recorded_without_leaking_text_or_stopping_next_case(self):
        bad = self.task("Prob001", reference="module TopModule; endmodule\n" + PRIVATE)
        good = self.task("Prob002")
        evaluator = RecordingEvaluator({good.id: Evaluation("passed", {"passed": 1.0})}, self.source)
        summary = verify_tasks([good, bad], evaluator, self.run / "verilog-spec", "verilog-spec")
        self.assertEqual(evaluator.calls, ["Prob002"])
        self.assertEqual(summary["attempted"], 2)
        self.assertEqual(summary["cases"][0]["reason"], "reference_invalid")
        self.assertNotIn(PRIVATE, json.dumps(summary))

    def test_existing_summary_is_never_overwritten(self):
        task = self.task("Prob001_zero")
        out = self.run / "verilog-spec"
        out.mkdir(parents=True)
        (out / "summary.json").write_text("preexisting ledger")
        with self.assertRaisesRegex(ConfigurationError, "summary.json"):
            verify_tasks([task], RecordingEvaluator({}, self.source), out, "verilog-spec")
        self.assertEqual((out / "summary.json").read_text(), "preexisting ledger")

    def test_unselected_mode_never_creates_or_writes_a_public_summary(self):
        task = self.task("Prob001_zero")
        secret_mode = "../private/SECRET_MODEL_KEY"
        out = self.run / "unknown"
        with self.assertRaises(ConfigurationError) as caught:
            verify_tasks([task], RecordingEvaluator({}, self.source), out, secret_mode)
        self.assertNotIn(secret_mode, str(caught.exception))
        self.assertFalse(out.exists())
        self.assertFalse((out / "summary.json").exists())

    def test_verifier_rejects_unsafe_id_and_symlinked_output(self):
        task = self.task("Prob001_zero")
        for identifier in ("../secret", "nested/other", "bad\\id", "bad.txt"):
            with self.subTest(identifier=identifier):
                invalid = Task(identifier, task.split, task.prompt, task.files, task.evaluation)
                out = self.run / identifier.replace("/", "_").replace("\\", "_")
                summary = verify_tasks([invalid], RecordingEvaluator({}, self.source),
                                       out, "verilog-spec")
                self.assertEqual(summary["cases"][0]["reason"], "reference_invalid")
                self.assertNotIn(identifier, json.dumps(summary))
        linked = self.root / "linked-output"
        linked.symlink_to(self.root / "actual-output", target_is_directory=True)
        with self.assertRaises(ConfigurationError):
            verify_tasks([task], RecordingEvaluator({}, self.source), linked, "verilog-spec")

    def test_invalid_id_type_and_symlinked_case_do_not_stop_other_cases(self):
        first = self.task("Prob001")
        second = self.task("Prob002")
        invalid = Task(None, first.split, first.prompt, first.files, first.evaluation)
        out = self.run / "verilog-spec"
        (out / "cases").mkdir(parents=True)
        (out / "cases/Prob001").symlink_to(self.root, target_is_directory=True)
        evaluator = RecordingEvaluator({second.id: Evaluation("passed", {"passed": 1.0})},
                                       self.source)
        summary = verify_tasks([second, first, invalid], evaluator, out, "verilog-spec")
        self.assertEqual(evaluator.calls, ["Prob002"])
        self.assertEqual(summary["attempted"], 3)
        self.assertEqual(summary["failed"], 2)
        self.assertEqual([case["reason"] for case in summary["cases"]],
                         ["reference_invalid", "reference_invalid", "passed"])
        self.assertNotIn("null", json.dumps([case["id"] for case in summary["cases"]]))

    def test_exactly_156_passed_cases_can_complete_a_single_mode(self):
        tasks = [self.task(f"Prob{number:03d}", "verilog-completion")
                 for number in range(1, 157)]
        evaluator = RecordingEvaluator({task.id: Evaluation("passed", {"passed": 1.0})
                                        for task in tasks}, self.source)
        out = self.run / "verilog-completion"
        summary = verify_tasks(tasks[::-1], evaluator, out, "verilog-completion")
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["attempted"], 156)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["unattempted"], 0)
        self.assertEqual(len(summary["cases"]), 156)
        self.assertEqual(json.loads((out / "summary.json").read_text()), summary)

    def test_middle_failure_still_persists_all_156_attempts_as_failed(self):
        tasks = [self.task(f"Prob{number:03d}") for number in range(1, 157)]
        outcomes = {task.id: Evaluation("passed", {"passed": 1.0}) for task in tasks}
        outcomes["Prob078"] = Evaluation("failed", {"passed": 0.0},
                                         "Verilog-Eval: 1 mismatches in 23 samples")
        evaluator = RecordingEvaluator(outcomes, self.source)
        out = self.run / "verilog-spec"
        summary = verify_tasks(tasks[::-1], evaluator, out, "verilog-spec")
        persisted = json.loads((out / "summary.json").read_text())
        self.assertEqual(evaluator.calls, [f"Prob{number:03d}" for number in range(1, 157)])
        self.assertEqual(persisted, summary)
        self.assertEqual(persisted["attempted"], 156)
        self.assertEqual(persisted["unattempted"], 0)
        self.assertEqual(persisted["failed"], 1)
        self.assertEqual(persisted["status"], "failed")
        self.assertEqual(len(persisted["cases"]), 156)
        self.assertEqual(persisted["cases"][77]["reason"], "mismatch")
        self.assertEqual(persisted["cases"][155]["status"], "passed")

    def test_case_elapsed_time_reflects_an_actual_evaluation(self):
        task = self.task("Prob001_zero")

        class SlowEvaluator(RecordingEvaluator):
            def evaluate(inner, task, output_dir, timeout_seconds):
                time.sleep(0.02)
                return super().evaluate(task, output_dir, timeout_seconds)

        evaluator = SlowEvaluator({task.id: Evaluation("passed", {"passed": 1.0})}, self.source)
        summary = verify_tasks([task], evaluator, self.run / "verilog-spec", "verilog-spec")
        self.assertGreaterEqual(summary["cases"][0]["elapsed_seconds"], 0.02)


if __name__ == "__main__":
    unittest.main()
