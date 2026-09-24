"""Dataset preparation must preserve held-out and private evaluator boundaries."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_optimizer.config import validate_runtime
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.readiness import collect_dataset, collect_plan
from agent_optimizer.registry import PROJECT_COMPONENTS, Registry
from agent_optimizer.datasets import CustomDataset, acquire_pinned_git
from agent_optimizer.contracts import ExecutionResult, Task, UnavailableError
from examples.benchmarks.verilog_eval import REVISION, RUNTIME_IMAGE, Provider, CompletionProvider, import_verilog_eval, prepare_runtime, split_families
from examples.benchmarks.verilog_evaluator import VerilogEvaluator
from examples.benchmarks import cvdp as cvdp_provider
from examples.benchmarks.cvdp import import_cvdp
from test_dev_environment import official_row
from support import module, ROOT, test_project


class DatasetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for mode in ("dataset_spec-to-rtl", "dataset_code-complete-iccad2023"):
            directory = self.root / mode
            directory.mkdir()
            for number in range(1, 5):
                stem = f"Prob{number:03d}_task"
                (directory / f"{stem}_prompt.txt").write_text(f"Implement {stem}\n")
                (directory / f"{stem}_test.sv").write_text("private_testbench_sentinel")
                (directory / f"{stem}_ref.sv").write_text("private_reference_sentinel")
                if mode.endswith("iccad2023"):
                    (directory / f"{stem}_ifc.txt").write_text("module TopModule();\n")

    def test_dataset_doctor_uses_team_provider_read_only_and_reports_missing_cache(self):
        temporary, project = test_project()
        self.addCleanup(temporary.cleanup)
        provider = project / "experiments/sample-team/diagnostic.py"
        provider.write_text('''from pathlib import Path
class Provider:
    def describe(self):
        return {"name": "team_fixture", "evaluator": "sample_eval"}
    def prepare(self, cache, *, offline=False):
        raise AssertionError("preparation is forbidden")
    def doctor(self, cache: Path):
        ok = (cache / "prepared.txt").is_file()
        return [{"id": "dataset.fixture", "area": "dataset", "status": "ok" if ok else "error",
                 "message": "Fixture ready" if ok else "Fixture absent",
                 "remedy": "" if ok else "Run agent-opt datasets prepare team_fixture"}]
''')
        with patch.dict(PROJECT_COMPONENTS["datasets"], {"team_fixture": "experiments/sample-team/diagnostic.py:Provider"}):
            before = {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()}
            with patch("agent_optimizer.runner.preflight", side_effect=AssertionError("preflight")), \
                    patch("agent_optimizer.datasets.acquire_pinned_git", side_effect=AssertionError("download")), \
                    patch("examples.benchmarks.verilog_eval.prepare_runtime", side_effect=AssertionError("build")):
                missing = collect_dataset(project, "team_fixture", Registry())
                self.assertFalse(missing["ready"])
                self.assertEqual({row["id"] for row in missing["checks"] if row["status"] == "error"},
                                 {"dataset.fixture"})
                self.assertEqual(before, {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()})
                (project / "external/datasets/team_fixture").mkdir(parents=True)
                (project / "external/datasets/team_fixture/prepared.txt").write_text("ready")
                before = {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()}
                ready = collect_dataset(project, "team_fixture", Registry())
                self.assertTrue(ready["ready"], ready)
                self.assertEqual(before, {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()})
                self.assertFalse(list(project.rglob("*.pyc")))

                benchmark = project / "examples/minimal/tasks.json"
                benchmark.write_text(json.dumps({**json.loads(benchmark.read_text()),
                                                 "dataset_provider": "team_fixture"}))
                experiment = project / "examples/minimal/experiment.toml"
                experiment.write_text(experiment.read_text().replace('evaluator = "text_fixture"',
                                                                 'evaluator = "sample_eval"'))
                before = {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()}
                with patch("agent_optimizer.runner.preflight", side_effect=AssertionError("preflight")), \
                        patch("agent_optimizer.datasets.acquire_pinned_git", side_effect=AssertionError("download")):
                    plan = collect_plan(experiment, Registry())
                self.assertTrue(plan["ready"], plan)
                self.assertIn("dataset.fixture", {row["id"] for row in plan["checks"]})
                self.assertEqual(before, {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()})

    def test_unregistered_dataset_is_structured_failure(self):
        temporary, project = test_project()
        self.addCleanup(temporary.cleanup)
        report = collect_dataset(project, "unknown", Registry())
        self.assertFalse(report["ready"])
        self.assertEqual(report["checks"][0]["status"], "error")
        self.assertIn("datasets list", report["checks"][0]["remedy"])

    def test_importer_keeps_related_tasks_in_same_split_without_private_bytes(self):
        specification = import_verilog_eval(self.root, "spec-to-rtl")
        completion = import_verilog_eval(self.root, "code-complete-iccad2023")
        self.assertEqual(len(specification["tasks"]), 4)
        self.assertEqual({t["family"]: t["split"] for t in specification["tasks"]},
                         {t["family"]: t["split"] for t in completion["tasks"]})
        self.assertEqual(set(t["split"] for t in specification["tasks"]),
                         {"train", "validation", "test"})
        for task in [*specification["tasks"], *completion["tasks"]]:
            public = json.dumps({"prompt": task["prompt"], "files": task["files"]})
            self.assertNotIn("private_testbench_sentinel", public)
            self.assertNotIn("private_reference_sentinel", public)
            self.assertNotIn("_test.sv", public)
            self.assertNotIn("_ref.sv", public)

    def test_too_few_families_cannot_be_split_into_three_sets(self):
        with self.assertRaisesRegex(ConfigurationError, "families"):
            split_families(["one", "two"])

    def test_pinned_git_download_is_atomic_reused_offline_and_rejects_dirty_tree(self):
        origin = self.root / "origin"
        origin.mkdir()
        subprocess.run(["git", "init", "-q", str(origin)], check=True)
        (origin / "README.md").write_text("pinned version\n")
        subprocess.run(["git", "-C", str(origin), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(origin), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
        revision = subprocess.check_output(["git", "-C", str(origin), "rev-parse", "HEAD"], text=True).strip()
        target = self.root / "cache" / "checkout"
        with self.assertRaises(UnavailableError):
            acquire_pinned_git(target, str(origin), revision, offline=True)
        self.assertFalse(target.exists())
        self.assertEqual(acquire_pinned_git(target, str(origin), revision), target)
        self.assertEqual(acquire_pinned_git(target, str(origin), revision, offline=True), target)
        (target / "README.md").write_text("modified")
        with self.assertRaises(ConfigurationError):
            acquire_pinned_git(target, str(origin), revision, offline=True)

    def test_provider_prepares_public_manifest_from_a_pinned_local_source(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
        revision = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()
        provider = Provider(url=str(self.root), revision=revision)
        cache = self.root / "prepared"
        with self.assertRaises(UnavailableError):
            provider.prepare(cache, offline=True)
        with patch("examples.benchmarks.verilog_eval.prepare_runtime",
                   return_value={"runtime": {"kind": "docker", "image": "verified-v12"},
                                 "image_id": "sha256:verified"}):
            prepared = provider.prepare(cache)
        document = json.loads(Path(prepared["benchmark"]).read_text())
        self.assertEqual(document["source_revision"], revision)
        self.assertEqual(prepared["evaluator"], "verilog_eval")
        self.assertEqual(len(document["tasks"]), 4)
        self.assertEqual(prepared["evaluation_runtime"]["image"], "verified-v12")
        self.assertEqual(prepared["evaluator_config"]["image_id"], "sha256:verified")
        with patch("examples.benchmarks.verilog_eval.prepare_runtime",
                   return_value={"runtime": {"kind": "docker", "image": "verified-v12"},
                                 "image_id": "sha256:verified"}):
            self.assertEqual(provider.prepare(cache, offline=True)["benchmark"], prepared["benchmark"])
        validate_runtime(prepared["evaluation_runtime"])
        self.assertEqual(prepared["provenance"]["image_id"], "sha256:verified")

    def test_verilog_doctor_checks_both_modes_private_completeness_and_image_identity_without_writes(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
        revision = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()
        cache = self.root / "prepared"
        providers = (Provider(url=str(self.root), revision=revision),
                     CompletionProvider(url=str(self.root), revision=revision))
        with patch("examples.benchmarks.verilog_eval.prepare_runtime", return_value={
                "runtime": {"kind": "docker", "image": RUNTIME_IMAGE},
                "image_id": "sha256:" + "a" * 64}):
            for provider in providers:
                provider.prepare(cache)
        real_run = subprocess.run

        def inspect(argv, **kwargs):
            if argv[0] == "git":
                return real_run(argv, **kwargs)
            self.assertEqual(argv[:3], ["docker", "image", "inspect"])
            self.assertNotIn("run", argv)
            return subprocess.CompletedProcess(argv, 0, json.dumps([{"Id": "sha256:" + "a" * 64}]), "")

        with patch("examples.benchmarks.verilog_eval.subprocess.run", side_effect=inspect):
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in cache.rglob("*") if p.is_file()}
            for provider in providers:
                rows = provider.doctor(cache)
                self.assertTrue(all(row["status"] == "ok" for row in rows), rows)
            self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns)
                                      for p in cache.rglob("*") if p.is_file()})
            (cache / "source" / revision / "dataset_spec-to-rtl/Prob001_task_ref.sv").unlink()
            rows = providers[0].doctor(cache)
            self.assertTrue(any(row["status"] == "error" and row["remedy"] for row in rows), rows)
            rows = providers[1].doctor(cache)
            self.assertEqual(next(row["status"] for row in rows if row["id"] == "dataset.verilog.tasks"), "ok")
            with patch("examples.benchmarks.verilog_eval.subprocess.run", return_value=
                       subprocess.CompletedProcess([], 0, '[{"Id":"sha256:changed"}]', "")):
                rows = providers[1].doctor(cache)
            self.assertTrue(any("image" in row["id"] and row["status"] == "error"
                                and row["remedy"] for row in rows), rows)
        with patch("examples.benchmarks.verilog_eval.subprocess.run", side_effect=FileNotFoundError):
            rows = providers[1].doctor(cache)
        self.assertTrue(any("image" in row["id"] and row["status"] == "error" for row in rows), rows)

    def test_missing_v12_image_blocks_offline_prepare(self):
        with patch("examples.benchmarks.verilog_eval.subprocess.run") as run:
            run.return_value.returncode = 1
            with self.assertRaisesRegex(UnavailableError, "offline"):
                prepare_runtime(offline=True)

    def test_verilog_evaluator_rejects_unverified_simulator_version(self):
        tool = self.root / "iverilog"
        tool.write_text("#!/usr/bin/env python3\nprint('Icarus Verilog version 13.0')\n")
        tool.chmod(0o755)
        task = Task(id="Prob001_task", split="validation", family="Prob001_task",
                    prompt="Implement", files={"solution.sv": ""},
                    evaluation={"source_dir": str(self.root), "problem_id": "Prob001_task",
                                "mode": "spec-to-rtl"})
        previous = os.environ.get("VERILOG_EVAL_IVERILOG")
        os.environ["VERILOG_EVAL_IVERILOG"] = str(tool)
        self.addCleanup(lambda: os.environ.pop("VERILOG_EVAL_IVERILOG", None)
                        if previous is None else os.environ.__setitem__("VERILOG_EVAL_IVERILOG", previous))
        with self.assertRaisesRegex(UnavailableError, "v12"):
            VerilogEvaluator({"kind": "local"}).validate_benchmark([task], {"source_revision": REVISION})

    def test_verilog_evaluator_refuses_a_mismatched_source_revision(self):
        task = Task(id="Prob001_task", split="validation", family="Prob001_task",
                    prompt="Implement", files={"solution.sv": ""},
                    evaluation={"source_dir": str(self.root), "problem_id": "Prob001_task",
                                "mode": "spec-to-rtl"})
        with self.assertRaisesRegex(ConfigurationError, "revision"):
            VerilogEvaluator({"kind": "docker", "image": "local-test"}).validate_benchmark(
                [task], {"source_revision": "unreviewed"})

    def test_verilog_evaluator_rejects_changed_private_checker_before_scoring(self):
        tool = self.root / "iverilog"
        tool.write_text("#!/usr/bin/env python3\nprint('Icarus Verilog version 12.0')\n")
        tool.chmod(0o755)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
        revision = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()
        (self.root / "dataset_spec-to-rtl/Prob001_task_test.sv").write_text("modified checker")
        task = Task(id="Prob001_task", split="validation", family="Prob001_task",
                    prompt="Implement", files={"solution.sv": ""},
                    evaluation={"source_dir": str(self.root), "problem_id": "Prob001_task",
                                "mode": "spec-to-rtl"})
        with patch("examples.benchmarks.verilog_evaluator.REVISION", revision), \
                patch.dict(os.environ, {"VERILOG_EVAL_IVERILOG": str(tool)}):
            with self.assertRaisesRegex(ConfigurationError, "differs"):
                VerilogEvaluator({"kind": "local"}).validate_benchmark(
                    [task], {"source_revision": revision})

    def test_verilog_evaluator_rechecks_docker_v12_before_a_later_run(self):
        task = Task(id="Prob001_task", split="validation", family="Prob001_task",
                    prompt="Implement", files={"solution.sv": ""},
                    evaluation={"source_dir": str(self.root), "problem_id": "Prob001_task",
                                "mode": "spec-to-rtl"})
        image = subprocess.CompletedProcess(["docker", "image", "inspect"], 0,
                                            '[{"Id":"sha256:local"}]', "")
        wrong_version = subprocess.CompletedProcess(["docker", "run"], 0,
                                                    "Icarus Verilog version 13.0", "")
        with patch("examples.benchmarks.verilog_evaluator.subprocess.run",
                   side_effect=[image, wrong_version]):
            with self.assertRaisesRegex(UnavailableError, "v12"):
                VerilogEvaluator({"kind": "docker", "image": "misleading-v12"}).validate_benchmark(
                    [task], {"source_revision": REVISION})

    def test_verilog_evaluator_refuses_changed_pinned_image_identity(self):
        task = Task(id="Prob001_task", split="validation", family="Prob001_task",
                    prompt="Implement", files={"solution.sv": ""},
                    evaluation={"source_dir": str(self.root), "problem_id": "Prob001_task",
                                "mode": "spec-to-rtl"})
        changed = subprocess.CompletedProcess(["docker", "image", "inspect"], 0,
                                              '[{"Id":"sha256:changed"}]', "")
        with patch("examples.benchmarks.verilog_evaluator.subprocess.run", return_value=changed):
            with self.assertRaisesRegex(ConfigurationError, "image"):
                VerilogEvaluator({"kind": "docker", "image": "local-v12",
                                  "image_id": "sha256:prepared"}).validate_benchmark(
                    [task], {"source_revision": REVISION})

    def test_verilog_compile_and_simulation_share_one_trial_deadline(self):
        task = Task("Prob001_task", "validation", "Implement", {"solution.sv": ""},
                    {"source_dir": str(self.root), "problem_id": "Prob001_task", "mode": "spec-to-rtl"})
        output_dir = self.root / "outputs" / "candidate"
        output_dir.mkdir(parents=True)
        (output_dir / "solution.sv").write_text("module TopModule(output zero); assign zero=0; endmodule")
        now = [100.0]
        seen = []

        def execute(argv, workspace, logs, timeout, runtime):
            seen.append((argv[0], timeout))
            logs.mkdir(parents=True)
            stdout = logs / "stdout.log"
            stdout.write_text("Mismatches: 0 in 20 samples\n" if argv[0] == "vvp" else "")
            if argv[0] == "iverilog":
                now[0] += 4.0
            return ExecutionResult("completed", 0, 0, str(stdout), str(logs / "stderr.log"))

        with patch("examples.benchmarks.verilog_evaluator.acquire_pinned_git", return_value=self.root), \
                patch("examples.benchmarks.verilog_evaluator.execute", side_effect=execute), \
                patch("time.monotonic", side_effect=lambda: now[0]):
            result = VerilogEvaluator({"kind": "docker", "image": "fixture"}).evaluate(task, output_dir, 10)
        self.assertEqual(result.status, "passed")
        self.assertEqual(seen, [("iverilog", 10), ("vvp", 6)])

    def test_cvdp_importer_uses_reviewed_rows_and_family_disjoint_splits(self):
        rows = []
        for index in range(4):
            row = official_row()
            row["id"] = f"cvdp_copilot_demo_{index:04d}"
            rows.append(row)
        data = self.root / "no_commercial.jsonl"
        data.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        manifest = import_cvdp(data)
        self.assertEqual({task["split"] for task in manifest["tasks"]},
                         {"train", "validation", "test"})
        self.assertEqual(len(manifest["tasks"]), 4)
        self.assertNotIn("PRIVATE_CHECKER", json.dumps([task["files"] for task in manifest["tasks"]]))

    def test_cvdp_provider_preserves_prepared_evaluation_image_for_later_runs(self):
        data = self.root / "no_commercial.jsonl"
        rows = []
        for number in range(3):
            row = official_row()
            row["id"] = f"cvdp_copilot_{number:04d}"
            rows.append(row)
        data.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        original_load = cvdp_provider._load

        def reviewed_or_fixture(path, name):
            if path.name == "setup.py":
                return SimpleNamespace(prepare_evaluation_environment=lambda **options:
                                        (data, {"images": {"evaluation": {"tag": "pinned-sim:v1",
                                                                            "id": "sha256:pinned"}}}))
            return original_load(path, name)

        with patch.object(cvdp_provider, "_load", side_effect=reviewed_or_fixture):
            result = cvdp_provider.Provider().prepare(self.root / "cache")
        self.assertEqual(result["evaluator"], "cvdp")
        self.assertEqual(result["evaluator_config"]["sim_image"], "pinned-sim:v1")
        self.assertEqual(result["evaluator_config"]["sim_image_id"], "sha256:pinned")
        self.assertTrue(result["evaluator_config"]["python"].endswith("cvdp-venv/bin/python"))

    def test_cvdp_evaluator_rejects_changed_prepared_image(self):
        repo = self.root / "cvdp"
        repo.mkdir()
        (repo / "run_benchmark.py").write_text("# fixture\n")
        driver = self.root / "python"
        driver.write_text("# fixture\n")
        evaluator = module("cvdp_image_check", ROOT / "examples/ace-rtl/evaluator.py").CVDPEvaluator(
            {"repo": str(repo), "python": str(driver), "sim_image": "prepared:v1",
             "sim_image_id": "sha256:prepared"})
        task = Task("one", "validation", "implement", {"rtl/dut.sv": ""},
                    {"row": official_row(), "targets": ["rtl/dut.sv"]})
        changed = subprocess.CompletedProcess(["docker", "image", "inspect"], 0,
                                              '[{"Id":"sha256:changed"}]', "")
        with patch("cvdp_image_check.subprocess.run", return_value=changed):
            with self.assertRaisesRegex(ConfigurationError, "image"):
                evaluator.validate_benchmark([task], {"synthetic": False})

    def test_custom_dataset_requires_scorer_and_records_a_stable_family_split(self):
        source = self.root / "custom.json"
        source.write_text(json.dumps({"schema_version": 1, "tasks": [
            {"id": f"task-{i}", "family": f"family-{i}", "prompt": "Answer",
             "files": {"input.txt": str(i)}, "evaluation": {"expected": str(i)}}
            for i in range(4)]}))
        with self.assertRaisesRegex(ConfigurationError, "evaluator"):
            CustomDataset(source, evaluator="").prepare(self.root / "output")
        prepared = CustomDataset(source, evaluator="team_eval").prepare(self.root / "output")
        result = json.loads(Path(prepared["benchmark"]).read_text())
        self.assertEqual({task["split"] for task in result["tasks"]},
                         {"train", "validation", "test"})
        self.assertEqual(prepared["evaluator"], "team_eval")

    def test_invalid_custom_split_cannot_publish_a_benchmark(self):
        source = self.root / "leaky.json"
        source.write_text(json.dumps({"schema_version": 1, "tasks": [
            {"id": f"t{index}", "family": "same", "split": split, "prompt": "Answer",
             "files": {"input.txt": str(index)}, "evaluation": {"expected": str(index)}}
            for index, split in enumerate(("train", "validation"))]}))
        output = self.root / "cache/custom/leaky.json"
        with self.assertRaisesRegex(ConfigurationError, "leaks"):
            CustomDataset(source, evaluator="team_eval").prepare(self.root / "cache")
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
