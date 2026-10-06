"""API-free checks for the pinned Verilog-Eval reference verifier."""
import json
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import threading
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

    def test_parallel_cases_overlap_keep_all_verdicts_and_private_files_unchanged(self):
        tasks = [self.task("Prob002"), self.task("Prob001_zero")]
        barrier = threading.Barrier(2)
        evaluator = RecordingEvaluator({
            "Prob001_zero": Evaluation("passed", {"passed": 1.0}, "ok"),
            "Prob002": Evaluation("failed", {"passed": 0.0}, "Verilog-Eval: 1 mismatches in 2 samples"),
        }, self.source)
        original = evaluator.evaluate
        def evaluate(*args):
            barrier.wait(timeout=2)
            return original(*args)
        evaluator.evaluate = evaluate
        summary = verify_tasks(tasks, evaluator, self.run / "verilog-spec", "verilog-spec", jobs=2)
        self.assertEqual(summary["attempted"], 2)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual([case["id"] for case in summary["cases"]], ["Prob001_zero", "Prob002"])
        self.assertEqual(summary["cases"][1]["reason"], "mismatch")
        self.assertEqual(sorted(evaluator.calls), ["Prob001_zero", "Prob002"])
        for task in tasks:
            source = self.source / "dataset_spec-to-rtl"
            self.assertEqual((source / f"{task.id}_test.sv").read_text(), PRIVATE)
            self.assertEqual((source / f"{task.id}_ref.sv").read_text(), REFERENCE)

    def test_invalid_parallelism_does_not_create_a_ledger(self):
        for jobs in (0, -1, 17, True):
            out = self.run / f"bad-{jobs}"
            with self.subTest(jobs=jobs), self.assertRaises(ConfigurationError):
                verify_tasks([], None, out, "verilog-spec", jobs=jobs)
            self.assertFalse(out.exists())

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

    def test_initial_summary_is_not_published_when_serialization_is_interrupted(self):
        out = self.run / "verilog-spec"

        def interrupted(summary, stream, **kwargs):
            stream.write('{"status":')
            raise OSError("interrupted")

        with patch.object(cli.json, "dump", side_effect=interrupted), self.assertRaises(OSError):
            verify_tasks([], RecordingEvaluator({}, self.source), out, "verilog-spec")
        self.assertFalse((out / "summary.json").exists())
        self.assertEqual(list(out.iterdir()), [])

    def test_initial_summary_publish_race_preserves_existing_ledger(self):
        out = self.run / "verilog-spec"

        def competing_writer(source, destination):
            Path(destination).write_text("another writer")
            raise FileExistsError("competing ledger")

        with patch("os.link", side_effect=competing_writer), self.assertRaises(FileExistsError):
            verify_tasks([], RecordingEvaluator({}, self.source), out, "verilog-spec")
        self.assertEqual((out / "summary.json").read_text(), "another writer")
        self.assertEqual([entry.name for entry in out.iterdir()], ["summary.json"])

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
                         ["reference_invalid", "infrastructure_error", "passed"])
        self.assertNotIn("null", json.dumps([case["id"] for case in summary["cases"]]))

    def test_existing_case_output_and_missing_reference_are_infrastructure_errors(self):
        first = self.task("Prob001")
        second = self.task("Prob002")
        missing = self.task("Prob003")
        (self.source / "dataset_spec-to-rtl/Prob003_ref.sv").unlink()
        out = self.run / "verilog-spec"
        (out / "cases/Prob001/output").mkdir(parents=True)
        evaluator = RecordingEvaluator({second.id: Evaluation("passed", {"passed": 1.0})},
                                       self.source)
        summary = verify_tasks([first, missing, second], evaluator, out, "verilog-spec")
        self.assertEqual([row["reason"] for row in summary["cases"]],
                         ["infrastructure_error", "passed", "infrastructure_error"])
        self.assertEqual(evaluator.calls, ["Prob002"])
        self.assertEqual(list((out / "cases/Prob001/output").iterdir()), [])

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
        self.host_os = "Darwin"
        self.host_arch = "arm64"
        self.daemon_platform = "linux/arm64\n"
        self.observed_image_id = self.image_id
        self.image_os = "linux"
        self.image_arch = "arm64"
        self.docker_calls = []
        self.validations = []

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
                                 (1, 0, 1) if "--smoke-one" in args else (156, 0, 156))
                test.assertEqual(initial["scope"], "smoke" if "--smoke-one" in args else "full")
                test.assertEqual(initial["status"], "running")
                test.assertEqual(initial["host"], {"os": "Darwin", "arch": "arm64"}
                                     if test.host_os == "Darwin" else
                                     {"os": "Linux", "arch": "x86_64"})
                test.assertEqual(initial["docker_daemon"], {"os": "linux", "arch": "arm64"}
                                     if test.daemon_platform == "linux/arm64\n" else
                                     {"os": "linux", "arch": "amd64"})
                test.assertIsNone(initial["source_revision"])
                test.assertIsNone(initial["image_id"])
                test.assertEqual(initial["image_platform"], {"os": None, "arch": None})
                test.assertIsNone(initial["actual_task_count"])
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
                test.validations.append(True)
                test.assertEqual(len(tasks), 156)
                test.assertEqual(metadata["source_revision"], REVISION)
                snapshot = test.ledger(args[1])
                test.assertEqual(snapshot["actual_task_count"], 156)
                test.assertEqual(snapshot["source_revision"], REVISION)
                test.assertEqual(snapshot["image_id"], test.observed_image_id)
                test.assertEqual(snapshot["image_platform"],
                                 {"os": test.image_os, "arch": test.image_arch})
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

        def docker_run(argv, **kwargs):
            test.docker_calls.append(argv)
            test.assertFalse(kwargs["shell"])
            if argv == ["docker", "version", "--format", "{{.Server.Os}}/{{.Server.Arch}}"]:
                return SimpleNamespace(returncode=0, stdout=test.daemon_platform, stderr=PRIVATE)
            test.assertEqual(argv, ["docker", "image", "inspect", RUNTIME_IMAGE])
            return SimpleNamespace(returncode=0, stdout=json.dumps([{
                "Id": test.observed_image_id, "Os": test.image_os,
                "Architecture": test.image_arch}]),
                                    stderr=PRIVATE)

        output = io.StringIO()
        with (patch.object(cli, "ROOT", self.root, create=True),
              patch.object(cli, "Registry", FakeRegistry, create=True),
              patch.object(cli, "VerilogEvaluator", FakeEvaluator, create=True),
              patch.object(cli, "platform", SimpleNamespace(system=lambda: test.host_os,
                                                              machine=lambda: test.host_arch)),
              patch.object(cli, "subprocess", SimpleNamespace(run=docker_run)),
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
                self.assertEqual(summary["host"], {"os": "Darwin", "arch": "arm64"})
                self.assertEqual(summary["docker_daemon"], {"os": "linux", "arch": "arm64"})
                self.assertIsNone(summary["source_revision"])
                self.assertIsNone(summary["image_id"])
                self.assertIsNone(summary["actual_task_count"])
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
                    self.tasks = [self.task(f"Prob{n:03d}") for n in range(2, 158)]
                    self.assertEqual(len(self.tasks), 156)
                    self.assertNotIn("Prob001_zero", [task.id for task in self.tasks])
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
                self.assertEqual(summary["actual_task_count"], 155 if stage == "count" else
                                 156 if stage in {"revision", "missing_first", "preflight"} else None)
                self.assertEqual(summary["source_revision"], REVISION if stage in
                                 {"count", "missing_first", "preflight"} else None)
                self.assertEqual(summary["image_id"], self.image_id if stage == "preflight" else None)
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
                self.assertEqual(summary["host"], {"os": "Darwin", "arch": "arm64"})
                self.assertEqual(summary["docker_daemon"], {"os": "linux", "arch": "arm64"})
                self.assertEqual(summary["source_revision"], REVISION)
                self.assertEqual(summary["image_id"], self.image_id)
                self.assertEqual(summary["image_platform"], {"os": "linux", "arch": "arm64"})
                self.assertEqual(summary["actual_task_count"], 156)
                self.assertIn(["docker", "image", "inspect", RUNTIME_IMAGE], self.docker_calls)
                self.assertEqual([item[0] for item in self.evaluations[-157:-1]],
                                 ["Prob001_zero"] + [f"Prob{n:03d}" for n in range(2, 157)])
                self.assertEqual(self.evaluations[-1][0], "Prob001_zero")
                self.assertNotIn(PRIVATE, json.dumps(summary) + output)

    def test_smoke_evaluates_only_first_reference_and_wrong_in_each_mode(self):
        for dataset, mode in (("verilog-spec", "spec-to-rtl"),
                              ("verilog-completion", "code-complete-iccad2023")):
            with self.subTest(dataset=dataset):
                self.root = Path(self.temp.name) / dataset
                self.source = self.root / "pinned"
                self.run = self.root / "runs/verilog-eval-smoke"
                self.tasks = [self.task("Prob001_zero", dataset)]
                self.tasks += [self.task(f"Prob{n:03d}", dataset) for n in range(2, 157)]
                self.prepared["benchmark"] = str(self.root / "tasks.json")
                self.prepared["provenance"]["mode"] = mode
                self.publish_tasks()
                self.evaluations = []
                code, output = self.invoke("--dataset", dataset, "--smoke-one")
                self.assertEqual(code, 0, output)
                summary = self.ledger(dataset)
                self.assertEqual((summary["scope"], summary["expected"], summary["attempted"],
                                  summary["unattempted"], summary["actual_task_count"],
                                  summary["status"]), ("smoke", 1, 1, 0, 156, "passed"))
                self.assertEqual([case["id"] for case in summary["cases"]], ["Prob001_zero"])
                self.assertEqual(summary["cases"][0]["passed"], 1.0)
                self.assertEqual((summary["wrong"]["status"], summary["wrong"]["reason"],
                                  summary["wrong"]["passed"]), ("failed", "mismatch", 0.0))
                self.assertEqual([row[0] for row in self.evaluations],
                                 ["Prob001_zero", "Prob001_zero"])
                self.assertEqual(json.loads((self.run / dataset / "summary.json").read_text()),
                                 summary)
                self.assertNotIn(PRIVATE, json.dumps(summary) + output)

    def test_smoke_rejects_bad_reference_or_unproven_wrong_verdict(self):
        for failure in ("reference", "wrong"):
            with self.subTest(failure=failure):
                self.root = Path(self.temp.name) / failure
                self.source = self.root / "pinned"
                self.run = self.root / "runs/verilog-eval-smoke"
                self.tasks = [self.task("Prob001_zero")]
                self.tasks += [self.task(f"Prob{n:03d}") for n in range(2, 157)]
                self.prepared["benchmark"] = str(self.root / "tasks.json")
                self.publish_tasks()
                self.evaluations = []
                self.reference_fail = "Prob001_zero" if failure == "reference" else None
                self.wrong_feedback = ("Verilog-Eval compile did not complete" if failure == "wrong"
                                       else "Verilog-Eval: 1 mismatches in 17 samples")
                code, _ = self.invoke("--dataset", "verilog-spec", "--smoke-one")
                self.assertEqual(code, 1)
                summary = self.ledger()
                self.assertEqual((summary["scope"], summary["expected"], summary["attempted"],
                                  summary["status"]), ("smoke", 1, 1, "failed"))
                self.assertEqual(len(self.evaluations), 2)

    def test_smoke_and_ubuntu_full_flags_conflict_before_ledger_or_prepare(self):
        code, output = self.invoke("--dataset", "verilog-spec", "--smoke-one",
                                   "--require-ubuntu-amd64")
        self.assertEqual(code, 2)
        self.assertFalse(self.run.exists())
        self.assertEqual(self.prepare_calls, [])
        self.assertNotIn(PRIVATE, output)

    def test_compile_failure_is_not_accepted_as_negative_sanity(self):
        self.wrong_feedback = "Verilog-Eval compile did not complete"
        code, output = self.invoke("--dataset", "verilog-spec")
        summary = self.ledger()
        self.assertNotEqual(code, 0)
        self.assertEqual((summary["attempted"], summary["failed"], summary["status"]),
                         (156, 0, "failed"))
        self.assertEqual(summary["wrong"]["reason"], "compile_failure")
        self.assertNotIn(PRIVATE, json.dumps(summary) + output)

    def test_inspected_image_id_mismatch_blocks_attempts_and_records_observation(self):
        self.observed_image_id = "sha256:" + "b" * 64
        code, output = self.invoke("--dataset", "verilog-spec")
        summary = self.ledger()
        self.assertNotEqual(code, 0)
        self.assertEqual(summary["attempted"], 0)
        self.assertEqual(summary["actual_task_count"], 156)
        self.assertEqual(summary["source_revision"], REVISION)
        self.assertEqual(summary["image_id"], self.observed_image_id)
        self.assertEqual(self.validations, [])
        self.assertEqual(self.evaluations, [])
        self.assertNotIn(PRIVATE, json.dumps(summary) + output)

    def test_ubuntu_rejects_wrong_image_platform_before_evaluator_validation(self):
        self.host_os = "Linux"
        self.host_arch = "x86_64"
        self.daemon_platform = "linux/amd64\n"
        self.image_arch = "arm64"
        code, output = self.invoke("--dataset", "verilog-spec", "--require-ubuntu-amd64")
        summary = self.ledger()
        self.assertEqual(code, 1)
        self.assertEqual(summary["image_platform"], {"os": "linux", "arch": "arm64"})
        self.assertEqual(summary["image_id"], self.image_id)
        self.assertEqual((summary["status"], summary["attempted"]), ("failed", 0))
        self.assertEqual(self.validations, [])
        self.assertEqual(self.evaluations, [])
        self.assertNotIn(PRIVATE, json.dumps(summary) + output)

    def test_invalid_inspected_image_os_cannot_report_passed(self):
        self.image_os = "windows"
        code, output = self.invoke("--dataset", "verilog-spec")
        self.assertEqual(code, 1)
        self.assertEqual(self.ledger()["status"], "failed")
        self.assertEqual(self.evaluations, [])
        self.assertNotIn(PRIVATE, output)

    def test_unrecognized_host_and_daemon_output_never_enter_ledger(self):
        self.host_os = PRIVATE + "/host"
        self.host_arch = PRIVATE + "/arch"
        self.daemon_platform = PRIVATE + "/daemon"
        code, output = self.invoke("--dataset", "verilog-spec")
        summary = self.ledger()
        self.assertNotEqual(code, 0)
        self.assertEqual(summary["host"], {"os": None, "arch": None})
        self.assertEqual(summary["docker_daemon"], {"os": None, "arch": None})
        self.assertIsNone(summary["source_revision"])
        self.assertIsNone(summary["image_id"])
        self.assertIsNone(summary["actual_task_count"])
        self.assertEqual(self.prepare_calls, [])
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

    def test_cache_symlinks_and_files_are_rejected_before_provider_prepare(self):
        for stage in ("external", "datasets", "mode", "mode_file", "datasets_file"):
            with self.subTest(stage=stage):
                self.root = Path(self.temp.name) / stage
                self.root.mkdir()
                self.run = self.root / "runs/verilog-eval-full"
                external = self.root / "external"
                datasets = external / "datasets"
                mode = datasets / "verilog-spec"
                outside = self.root / "other"
                outside.mkdir()
                if stage == "external":
                    external.symlink_to(outside, target_is_directory=True)
                else:
                    external.mkdir()
                    if stage == "datasets":
                        datasets.symlink_to(outside, target_is_directory=True)
                    elif stage == "datasets_file":
                        datasets.write_text("existing file")
                    else:
                        datasets.mkdir()
                        if stage == "mode":
                            mode.symlink_to(outside, target_is_directory=True)
                        else:
                            mode.write_text("existing file")
                code, output = self.invoke("--dataset", "verilog-spec")
                self.assertNotEqual(code, 0)
                self.assertEqual(self.prepare_calls, [])
                self.assertEqual(self.doctor_calls, [])
                self.assertEqual(self.ledger()["attempted"], 0)
                self.assertEqual(self.ledger()["reason"], "infrastructure_error")
                self.assertEqual(list(outside.iterdir()), [])
                self.assertNotIn(str(self.root), output)

    def test_existing_directory_cache_is_passed_to_provider_unchanged(self):
        cache = self.root / "external/datasets/verilog-spec"
        cache.mkdir(parents=True)
        (cache / "existing.lock").write_text("pinned")
        code, output = self.invoke("--dataset", "verilog-spec")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.prepare_calls, [cache])
        self.assertEqual(self.doctor_calls, [cache])
        self.assertEqual((cache / "existing.lock").read_text(), "pinned")

    def test_nested_cache_write_targets_rejected_before_prepare(self):
        for number, relative in enumerate(("source", f"source/{REVISION}",
                                           "runtime-lock.json", "runtime-lock.json.tmp",
                                           "verilog-eval-spec-to-rtl",
                                           "verilog-eval-spec-to-rtl/tasks.json",
                                           "verilog-eval-spec-to-rtl/tasks.json.tmp",
                                           "verilog-eval-spec-to-rtl/provenance.json",
                                           "verilog-eval-spec-to-rtl/provenance.json.tmp")):
            for kind in ("symlink", "wrong_type"):
                with self.subTest(relative=relative, kind=kind):
                    self.root = Path(self.temp.name) / f"nested-{number}-{kind}"
                    self.root.mkdir()
                    self.run = self.root / "runs/verilog-eval-full"
                    cache = self.root / "external/datasets/verilog-spec"
                    target = cache / relative
                    target.parent.mkdir(parents=True)
                    outside = self.root / "outside"
                    outside.mkdir()
                    if kind == "symlink":
                        target.symlink_to(outside / "escaped", target_is_directory=True)
                    elif relative in ("source", f"source/{REVISION}",
                                      "verilog-eval-spec-to-rtl"):
                        target.write_text("not a directory")
                    else:
                        target.mkdir()
                    self.prepare_calls.clear()
                    self.doctor_calls.clear()
                    code, output = self.invoke("--dataset", "verilog-spec")
                    self.assertEqual(code, 1)
                    self.assertEqual(self.prepare_calls, [])
                    self.assertEqual(self.doctor_calls, [])
                    self.assertEqual(self.ledger()["attempted"], 0)
                    self.assertEqual(list(outside.iterdir()), [])
                    self.assertNotIn(str(self.root), output)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO unavailable")
    def test_special_file_cache_is_rejected_before_prepare(self):
        cache = self.root / "external/datasets/verilog-spec"
        cache.mkdir(parents=True)
        os.mkfifo(cache / "runtime-lock.json")
        code, output = self.invoke("--dataset", "verilog-spec")
        self.assertEqual(code, 1)
        self.assertEqual(self.prepare_calls, [])
        self.assertEqual(self.ledger()["attempted"], 0)
        self.assertNotIn(str(self.root), output)

    def test_ubuntu_flag_stops_on_host_or_daemon_mismatch_without_prepare(self):
        for system, machine, daemon in (("Darwin", "arm64", "linux/amd64"),
                                        ("Linux", "x86_64", "linux/arm64")):
            with self.subTest(system=system, daemon=daemon):
                self.root = Path(self.temp.name) / system / daemon.replace("/", "-")
                self.run = self.root / "runs/verilog-eval-full"
                self.host_os = system
                self.host_arch = machine
                self.daemon_platform = daemon + "\n"
                code, output = self.invoke("--dataset", "verilog-spec", "--require-ubuntu-amd64")
                self.assertNotEqual(code, 0)
                snapshot = self.ledger()
                self.assertEqual(snapshot["attempted"], 0)
                self.assertEqual(snapshot["host"], {"os": system, "arch": machine})
                self.assertEqual(snapshot["docker_daemon"],
                                 {"os": "linux", "arch": "arm64"} if system == "Linux" else
                                 {"os": None, "arch": None})
                self.assertIsNone(snapshot["source_revision"])
                self.assertIsNone(snapshot["image_id"])
                self.assertIsNone(snapshot["actual_task_count"])
                self.assertEqual(self.prepare_calls, [])
                self.assertNotIn(PRIVATE, output)

    def test_ubuntu_flag_accepts_matching_host_and_daemon(self):
        self.host_os = "Linux"
        self.host_arch = "x86_64"
        self.daemon_platform = "linux/amd64\n"
        self.image_arch = "amd64"
        code, output = self.invoke("--dataset", "verilog-spec", "--require-ubuntu-amd64")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.ledger()["status"], "passed")
        self.assertEqual(self.ledger()["host"], {"os": "Linux", "arch": "x86_64"})
        self.assertEqual(self.ledger()["docker_daemon"], {"os": "linux", "arch": "amd64"})
        self.assertEqual(self.ledger()["image_platform"], {"os": "linux", "arch": "amd64"})
        self.assertEqual(self.docker_calls[0], ["docker", "version", "--format",
                                                "{{.Server.Os}}/{{.Server.Arch}}"])


class VerilogFullWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow_path = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"
        cls.workflow_text = cls.workflow_path.read_text()
        cls.workflow = cls._load_workflow(cls.workflow_path, cls.workflow_text)

    @staticmethod
    def _block(lines, indent, key):
        marker = " " * indent + key + ":"
        starts = [index for index, line in enumerate(lines) if line == marker]
        if len(starts) != 1:
            raise AssertionError(f"Expected one scoped YAML key: {key}")
        start = starts[0] + 1
        end = start
        while end < len(lines):
            line = lines[end]
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            end += 1
        return lines[start:end]

    @staticmethod
    def _scalar(value):
        if value is None:
            return None
        if value in ("true", "false"):
            return value == "true"
        if value.isdecimal():
            return int(value)
        if value.startswith("[") and value.endswith("]"):
            return [part.strip().strip("\"'") for part in value[1:-1].split(",")]
        if value.startswith(("'", '"')) and value.endswith(value[0]):
            return value[1:-1]
        return value

    @classmethod
    def _fields(cls, lines, indent):
        fields = {}
        for line in lines:
            match = re.fullmatch(rf" {{{indent}}}([\w-]+):(?: (.*))?", line)
            if match:
                key, value = match.groups()
                if key in fields:
                    raise AssertionError(f"Duplicate scoped YAML key: {key}")
                fields[key] = cls._scalar(value)
        return fields

    @classmethod
    def _fallback_workflow(cls, text):
        # Parse only the tested boundaries, with exact indentation and unique keys.
        lines = text.splitlines()
        events = cls._block(lines, 0, "on")
        dispatch = cls._block(events, 2, "workflow_dispatch")
        inputs = cls._block(dispatch, 4, "inputs")
        jobs = cls._block(lines, 0, "jobs")
        tests = cls._block(jobs, 2, "tests")
        official = cls._fields(cls._block(jobs, 2, "official-cvdp"), 4)
        full_lines = cls._block(jobs, 2, "verilog-eval-full")
        full = cls._fields(full_lines, 4)
        strategy = cls._block(full_lines, 4, "strategy")
        full["strategy"] = {**cls._fields(strategy, 6),
                            "matrix": cls._fields(cls._block(strategy, 6, "matrix"), 8)}
        step_lines = cls._block(full_lines, 4, "steps")
        starts = [index for index, line in enumerate(step_lines)
                  if re.fullmatch(r"      - (uses|name): .+", line)]
        if not starts or step_lines[:starts[0]] not in ([], [""]):
            raise AssertionError("Verilog-Eval job steps are malformed")
        steps = []
        for start, end in zip(starts, starts[1:] + [len(step_lines)]):
            rows = step_lines[start:end]
            rows = [rows[0].replace("      - ", "        ", 1), *rows[1:]]
            step = cls._fields(rows, 8)
            if "with" in step:
                step["with"] = cls._fields(cls._block(rows, 8, "with"), 10)
            if step.get("run") == "|":
                index = rows.index("        run: |")
                script = []
                for line in rows[index + 1:]:
                    if line.strip() and len(line) - len(line.lstrip()) <= 8:
                        break
                    script.append(line)
                step["run"] = "\n".join(line.strip() for line in script)
            steps.append(step)
        full["steps"] = steps
        return {"on": {"pull_request": cls._block(events, 2, "pull_request"),
                       "workflow_dispatch": {"inputs": {
                           key: cls._fields(cls._block(inputs, 6, key), 8)
                           for key in ("official_cvdp", "verilog_eval_full")}}},
                "jobs": {"tests": {"strategy": {"matrix": cls._fields(
                    cls._block(cls._block(tests, 4, "strategy"), 6, "matrix"), 8)}},
                         "official-cvdp": official, "verilog-eval-full": full}}

    @classmethod
    def _load_workflow(cls, workflow_path, text):
        if not shutil.which("ruby"):
            return cls._fallback_workflow(text)
        result = subprocess.run(
            ["ruby", "-rjson", "-ryaml", "-e",
             "puts JSON.generate(YAML.safe_load(File.read(ARGV.fetch(0))))", str(workflow_path)],
            capture_output=True, text=True, timeout=15, shell=False,
        )
        if result.returncode:
            raise AssertionError(result.stderr)
        return json.loads(result.stdout)

    def test_full_job_only_runs_for_explicit_manual_opt_in_without_changing_existing_ci(self):
        events = self.workflow.get("on", self.workflow.get("true"))
        dispatch = events["workflow_dispatch"]["inputs"]
        self.assertEqual(dispatch["official_cvdp"]["default"], False)
        self.assertIn("verilog_eval_full", dispatch)
        self.assertEqual(dispatch["verilog_eval_full"]["type"], "boolean")
        self.assertIs(dispatch["verilog_eval_full"]["default"], False)
        self.assertIn("pull_request", events)
        jobs = self.workflow["jobs"]
        self.assertEqual(jobs["tests"]["strategy"]["matrix"]["python"], ["3.11", "3.12"])
        self.assertEqual(jobs["official-cvdp"]["if"],
                         "github.event_name == 'workflow_dispatch' && inputs.official_cvdp")
        self.assertIn("verilog-eval-full", jobs)
        full = jobs["verilog-eval-full"]
        self.assertEqual(full["if"],
                         "github.event_name == 'workflow_dispatch' && inputs.verilog_eval_full")
        self.assertNotIn("needs", full)

    def test_each_full_mode_gets_pinned_environment_and_strict_host_check(self):
        self.assertIn("verilog-eval-full", self.workflow["jobs"])
        full = self.workflow["jobs"]["verilog-eval-full"]
        self.assertEqual(full["strategy"]["matrix"]["dataset"],
                         ["verilog-spec", "verilog-completion"])
        self.assertIs(full["strategy"]["fail-fast"], False)
        self.assertEqual(full["runs-on"], "ubuntu-24.04")
        self.assertEqual(full["timeout-minutes"], 330)
        steps = full["steps"]
        setup = next(step for step in steps if step.get("uses", "").startswith("actions/setup-python@"))
        self.assertEqual(setup["with"]["python-version"], "3.12")
        bootstrap = next(index for index, step in enumerate(steps)
                         if "uv==0.10.7" in step.get("run", ""))
        preparation = next(index for index, step in enumerate(steps)
                           if "make setup-core" in step.get("run", ""))
        evaluation = next(index for index, step in enumerate(steps)
                          if "verify_verilog_eval_full.py" in step.get("run", ""))
        self.assertLess(bootstrap, preparation)
        self.assertLess(preparation, evaluation)
        self.assertIn("uname -m", steps[evaluation]["run"])
        self.assertIn("docker version --format '{{.Server.Os}}/{{.Server.Arch}}'",
                      steps[evaluation]["run"])
        self.assertIn(".venv/bin/python examples/benchmarks/verify_verilog_eval_full.py",
                      steps[evaluation]["run"])
        self.assertIn("--dataset '${{ matrix.dataset }}' --require-ubuntu-amd64",
                      steps[evaluation]["run"])

    def test_failure_artifact_contains_only_selected_mode_sanitized_summary(self):
        self.assertIn("verilog-eval-full", self.workflow["jobs"])
        steps = self.workflow["jobs"]["verilog-eval-full"]["steps"]
        checkouts = [step for step in steps if step.get("uses", "").startswith("actions/checkout@")]
        self.assertEqual(len(checkouts), 1)
        self.assertEqual(checkouts[0].get("with"), {"persist-credentials": False})
        uploads = [step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@")]
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0]["uses"], "actions/upload-artifact@v4")
        self.assertEqual(uploads[0]["if"],
                         "always() && github.server_url == 'https://github.com'")
        self.assertEqual(uploads[0]["with"]["path"],
                         "runs/verilog-eval-full/${{ matrix.dataset }}/summary.json")
        self.assertEqual(uploads[0]["with"].get("if-no-files-found"), "error")
        self.assertIn("${{ matrix.dataset }}", uploads[0]["with"]["name"])
        self.assertTrue(all("env" not in step for step in steps))

    def test_python_only_path_enforces_scope_and_artifact_contract(self):
        with patch("shutil.which", return_value=None):
            self.workflow = self._load_workflow(self.workflow_path, self.workflow_text)
            self.assertIsInstance(self.workflow, dict)
            self.test_full_job_only_runs_for_explicit_manual_opt_in_without_changing_existing_ci()
            self.test_each_full_mode_gets_pinned_environment_and_strict_host_check()
            self.test_failure_artifact_contains_only_selected_mode_sanitized_summary()
            original = self.workflow_text
            try:
                self.workflow_text = original.replace(
                    "    if: github.event_name == 'workflow_dispatch' && inputs.verilog_eval_full",
                    "    if: always()", 1)
                self.workflow = self._load_workflow(self.workflow_path, self.workflow_text)
                with self.assertRaises(AssertionError):
                    self.test_full_job_only_runs_for_explicit_manual_opt_in_without_changing_existing_ci()
                self.workflow_text = original.replace(
                    "          path: runs/verilog-eval-full/${{ matrix.dataset }}/summary.json",
                    "          path: runs/verilog-eval-full/${{ matrix.dataset }}/", 1)
                self.workflow = self._load_workflow(self.workflow_path, self.workflow_text)
                with self.assertRaises(AssertionError):
                    self.test_failure_artifact_contains_only_selected_mode_sanitized_summary()
                self.workflow_text = original.replace(
                    "        dataset: [verilog-spec, verilog-completion]",
                    "        dataset: [verilog-spec]", 1)
                self.workflow = self._load_workflow(self.workflow_path, self.workflow_text)
                with self.assertRaises(AssertionError):
                    self.test_each_full_mode_gets_pinned_environment_and_strict_host_check()
                self.workflow_text = original.replace(
                    "          path: runs/verilog-eval-full/${{ matrix.dataset }}/summary.json\n"
                    "          if-no-files-found: error",
                    "          path: runs/verilog-eval-full/${{ matrix.dataset }}/summary.json", 1)
                self.workflow = self._load_workflow(self.workflow_path, self.workflow_text)
                with self.assertRaises(AssertionError):
                    self.test_failure_artifact_contains_only_selected_mode_sanitized_summary()
            finally:
                self.workflow_text = original


if __name__ == "__main__":
    unittest.main()
