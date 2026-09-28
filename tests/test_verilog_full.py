"""API-free checks for the pinned Verilog-Eval reference verifier."""
import json
import io
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_optimizer.contracts import ConfigurationError, Evaluation, Task
from examples.benchmarks import verify_verilog_eval_full as cli
from examples.benchmarks.verilog_eval import REVISION, RUNTIME_IMAGE
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


class VerilogFullCLITests(unittest.TestCase):
    task = VerilogFullTests.task

    def setUp(self):
        VerilogFullTests.setUp(self)
        self.tasks = [self.task("Prob001_zero")]
        self.tasks.extend(self.task(f"Prob{number:03d}") for number in range(2, 157))
        self.image_id = "sha256:" + "a" * 64
        self.prepared = {
            "benchmark": str(self.root / "tasks.json"), "evaluator": "verilog_eval",
            "evaluation_runtime": {"kind": "docker", "image": RUNTIME_IMAGE},
            "evaluator_config": {"image_id": self.image_id},
            "provenance": {"url": "https://github.com/NVlabs/verilog-eval.git",
                           "revision": REVISION, "mode": "spec-to-rtl", "image_id": self.image_id},
        }
        self.publish_tasks()
        self.prepare_error = None
        self.doctor_status = "ok"
        self.preflight_error = None
        self.wrong_feedback = "Verilog-Eval: 1 mismatches in 17 samples"
        self.reference_fail = None
        self.prepare_calls = []
        self.doctor_calls = []
        self.evaluations = []

    def publish_tasks(self, *, revision=REVISION):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "tasks.json").write_text(json.dumps({
            "schema_version": 1, "synthetic": False, "source_revision": revision,
            "tasks": [asdict(task) for task in self.tasks],
        }))

    def invoke(self, *args):
        test = self

        class FakeProvider:
            def prepare(self, cache):
                test.prepare_calls.append(cache)
                initial = json.loads((test.run / args[1] / "summary.json").read_text())
                test.assertEqual((initial["expected"], initial["attempted"], initial["unattempted"]),
                                 (156, 0, 156))
                test.assertEqual(initial["status"], "running")
                if test.prepare_error:
                    raise test.prepare_error
                return test.prepared

            def doctor(self, cache):
                test.doctor_calls.append(cache)
                return [{"status": test.doctor_status, "detail": PRIVATE}]

        class FakeRegistry:
            def load_project(self, root):
                test.assertEqual(root, test.root)

            def resolve(self, kind, name):
                test.assertEqual((kind, name), ("datasets", args[1]))
                return FakeProvider

        class FakeEvaluator:
            def __init__(self, config):
                test.assertEqual(config, {"kind": "docker", "image": RUNTIME_IMAGE,
                                          "image_id": test.image_id})

            def validate_benchmark(self, tasks, metadata):
                test.assertEqual(len(tasks), 156)
                test.assertEqual(metadata["source_revision"], REVISION)
                if test.preflight_error:
                    raise test.preflight_error

            def evaluate(self, task, output_dir, timeout_seconds):
                source = (output_dir / "solution.sv").read_text()
                test.evaluations.append((task.id, source))
                if "assign zero = 1'b1" in source:
                    test.assertEqual(task.id, "Prob001_zero")
                    return Evaluation("failed", {"passed": 0.0}, test.wrong_feedback)
                test.assertEqual(source, REFERENCE.replace("module RefModule(output",
                                                           "module TopModule(output"))
                if task.id == test.reference_fail:
                    return Evaluation("failed", {"passed": 0.0},
                                      "Verilog-Eval: 1 mismatches in 17 samples")
                return Evaluation("passed", {"passed": 1.0}, PRIVATE)

        output = io.StringIO()
        with (patch.object(cli, "ROOT", self.root, create=True),
              patch.object(cli, "Registry", FakeRegistry, create=True),
              patch.object(cli, "VerilogEvaluator", FakeEvaluator, create=True),
              redirect_stdout(output), redirect_stderr(output)):
            code = cli.main(list(args))
        return code, output.getvalue()

    def ledger(self, mode="verilog-spec"):
        return json.loads((self.run / mode / "summary.json").read_text())

    def test_cli_rejects_missing_unknown_and_injected_dataset_without_prepare_or_logs(self):
        for argv in ((), ("--dataset", "../private/SECRET_MODEL_KEY"),
                     ("--dataset", "cvdp")):
            with self.subTest(argv=argv):
                code, output = self.invoke(*argv)
                self.assertEqual(code, 2)
                self.assertNotIn("SECRET_MODEL_KEY", output)
                self.assertFalse(self.run.exists())
                self.assertEqual(self.prepare_calls, [])

    def test_direct_script_help_works_with_only_src_on_pythonpath(self):
        root = Path(cli.__file__).resolve().parents[2]
        result = subprocess.run([sys.executable, str(Path(cli.__file__)), "--help"],
                                cwd=root, env={**os.environ, "PYTHONPATH": str(root / "src")},
                                capture_output=True, text=True, timeout=15, shell=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--dataset", result.stdout)

    def test_prepare_and_doctor_fail_with_sanitized_zero_attempt_ledger(self):
        for stage in ("prepare", "doctor"):
            with self.subTest(stage=stage):
                self.root = Path(self.temp.name) / stage
                self.source = self.root / "pinned"
                self.run = self.root / "runs/verilog-eval-full"
                self.prepared["benchmark"] = str(self.root / "tasks.json")
                self.publish_tasks()
                self.prepare_error = RuntimeError(PRIVATE + "/personal/path") if stage == "prepare" else None
                self.doctor_status = "failed" if stage == "doctor" else "ok"
                code, output = self.invoke("--dataset", "verilog-spec")
                summary = self.ledger()
                self.assertNotEqual(code, 0)
                self.assertEqual((summary["expected"], summary["attempted"],
                                  summary["unattempted"], summary["status"]),
                                 (156, 0, 156, "failed"))
                self.assertEqual(summary["reason"], "infrastructure_error")
                self.assertNotIn(PRIVATE, json.dumps(summary) + output)
                self.assertNotIn("/personal/path", json.dumps(summary) + output)

    def test_inventory_revision_image_and_preflight_fail_before_evaluation(self):
        for stage in ("count", "revision", "image", "image_id", "missing_first", "preflight"):
            with self.subTest(stage=stage):
                self.root = Path(self.temp.name) / stage
                self.source = self.root / "pinned"
                self.run = self.root / "runs/verilog-eval-full"
                self.prepared["benchmark"] = str(self.root / "tasks.json")
                self.tasks = self.tasks[:155] if stage == "count" else [self.task("Prob001_zero")]
                if stage not in {"count", "missing_first"}:
                    self.tasks += [self.task(f"Prob{n:03d}") for n in range(2, 157)]
                if stage == "missing_first":
                    self.tasks = [self.task(f"Prob{n:03d}") for n in range(1, 157)]
                self.publish_tasks(revision="wrong" if stage == "revision" else REVISION)
                self.prepared["evaluation_runtime"]["image"] = (
                    "untrusted:v13" if stage == "image" else RUNTIME_IMAGE)
                self.prepared["provenance"]["image_id"] = (
                    "sha256:" + "b" * 64 if stage == "image_id" else self.image_id)
                self.preflight_error = (ConfigurationError(PRIVATE) if stage == "preflight" else None)
                code, output = self.invoke("--dataset", "verilog-spec")
                summary = self.ledger()
                self.assertNotEqual(code, 0)
                self.assertEqual((summary["expected"], summary["attempted"], summary["failed"]),
                                 (156, 0, 0))
                self.assertEqual(summary["reason"], "infrastructure_error")
                self.assertEqual(self.evaluations, [])
                self.assertNotIn(PRIVATE, json.dumps(summary) + output)

    def test_both_modes_attempt_156_references_and_require_proven_wrong_mismatch(self):
        for dataset, mode in (("verilog-spec", "spec-to-rtl"),
                              ("verilog-completion", "code-complete-iccad2023")):
            with self.subTest(dataset=dataset):
                self.tasks = [self.task("Prob001_zero", dataset)]
                self.tasks += [self.task(f"Prob{n:03d}", dataset) for n in range(2, 157)]
                self.publish_tasks()
                self.prepared["provenance"]["mode"] = mode
                code, output = self.invoke("--dataset", dataset)
                summary = self.ledger(dataset)
                self.assertEqual(code, 0, output)
                self.assertEqual((summary["expected"], summary["attempted"],
                                  summary["unattempted"], summary["failed"], summary["status"]),
                                 (156, 156, 0, 0, "passed"))
                self.assertEqual(len(summary["cases"]), 156)
                self.assertEqual(summary["wrong"]["reason"], "mismatch")
                self.assertEqual([item[0] for item in self.evaluations[-157:-1]],
                                 ["Prob001_zero"] + [f"Prob{n:03d}" for n in range(2, 157)])
                self.assertEqual(self.evaluations[-1][0], "Prob001_zero")
                self.assertNotIn(PRIVATE, json.dumps(summary) + output)

    def test_compile_failure_is_not_accepted_as_negative_sanity(self):
        self.wrong_feedback = "Verilog-Eval compile did not complete"
        code, output = self.invoke("--dataset", "verilog-spec")
        summary = self.ledger()
        self.assertNotEqual(code, 0)
        self.assertEqual((summary["attempted"], summary["failed"], summary["status"]),
                         (156, 0, "failed"))
        self.assertEqual(summary["wrong"]["reason"], "compile_failure")
        self.assertNotIn(PRIVATE, json.dumps(summary) + output)

    def test_wrong_rtl_rejected_without_a_proven_mismatch(self):
        self.wrong_feedback = "RTL solution missing"
        code, _ = self.invoke("--dataset", "verilog-spec")
        self.assertNotEqual(code, 0)
        self.assertEqual(self.ledger()["wrong"]["reason"], "reference_invalid")
        self.assertEqual(self.ledger()["status"], "failed")

    def test_reference_failure_cannot_report_success_even_when_wrong_mismatches(self):
        self.reference_fail = "Prob078"
        code, _ = self.invoke("--dataset", "verilog-spec")
        summary = self.ledger()
        self.assertNotEqual(code, 0)
        self.assertEqual((summary["attempted"], summary["failed"], summary["status"]),
                         (156, 1, "failed"))

    def test_existing_ledger_is_not_overwritten_or_prepared(self):
        out = self.run / "verilog-spec"
        out.mkdir(parents=True)
        (out / "summary.json").write_text("existing private ledger")
        code, output = self.invoke("--dataset", "verilog-spec")
        self.assertNotEqual(code, 0)
        self.assertEqual((out / "summary.json").read_text(), "existing private ledger")
        self.assertEqual(self.prepare_calls, [])
        self.assertNotIn("existing private ledger", output)

    def test_symlinked_selected_run_folder_fails_without_exposing_host_path(self):
        self.run.mkdir(parents=True)
        (self.run / "verilog-spec").symlink_to(self.source, target_is_directory=True)
        code, output = self.invoke("--dataset", "verilog-spec")
        self.assertNotEqual(code, 0)
        self.assertNotIn(str(self.root), output)
        self.assertEqual(self.prepare_calls, [])

    def test_ubuntu_flag_stops_on_host_or_daemon_mismatch_without_prepare(self):
        for system, machine, daemon in (("Darwin", "arm64", "linux/amd64"),
                                        ("Linux", "x86_64", "linux/arm64")):
            with self.subTest(system=system, daemon=daemon):
                self.root = Path(self.temp.name) / system / daemon.replace("/", "-")
                self.run = self.root / "runs/verilog-eval-full"
                with (patch.object(cli, "platform", SimpleNamespace(
                          system=lambda: system, machine=lambda: machine), create=True),
                      patch.object(cli, "subprocess", SimpleNamespace(run=lambda *a, **kw:
                          SimpleNamespace(returncode=0, stdout=daemon + "\n", stderr=PRIVATE)),
                          create=True)):
                    code, output = self.invoke("--dataset", "verilog-spec", "--require-ubuntu-amd64")
                self.assertNotEqual(code, 0)
                self.assertEqual(self.ledger()["attempted"], 0)
                self.assertEqual(self.prepare_calls, [])
                self.assertNotIn(PRIVATE, output)

    def test_ubuntu_flag_accepts_matching_host_and_daemon(self):
        def docker_info(argv, **kwargs):
            self.assertEqual(argv, ["docker", "info", "--format",
                                    "{{.Server.Os}}/{{.Server.Arch}}"])
            self.assertFalse(kwargs["shell"])
            return SimpleNamespace(returncode=0, stdout="linux/amd64\n", stderr="")

        with (patch.object(cli, "platform", SimpleNamespace(system=lambda: "Linux",
                                                             machine=lambda: "x86_64")),
              patch.object(cli, "subprocess", SimpleNamespace(run=docker_info))):
            code, output = self.invoke("--dataset", "verilog-spec", "--require-ubuntu-amd64")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.ledger()["status"], "passed")


if __name__ == "__main__":
    unittest.main()
