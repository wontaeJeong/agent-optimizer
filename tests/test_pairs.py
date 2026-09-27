import contextlib
import io
import json
import unittest
from unittest.mock import patch

from agent_optimizer import config
from agent_optimizer.cli import main
from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError, OptimizationResult
from agent_optimizer.harnesses.command import FixtureHarness
from agent_optimizer.registry import Registry
from agent_optimizer.runner import GroupRunner, preflight, run_experiment
from agent_optimizer.workspace import digest

from support import test_project


class PairSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary, self.root = test_project()
        self.addCleanup(self.temporary.cleanup)
        self.example = self.root / "examples/minimal"
        self.experiment = self.example / "experiment.toml"
        self.original = self.experiment.read_text(encoding="utf-8")
        harness = (self.example / "harness.toml").read_text(encoding="utf-8")
        (self.example / "fixture-alt.toml").write_text(
            harness.replace('id = "fixture"', 'id = "fixture-alt"'), encoding="utf-8"
        )
        self.matrix = self.original.replace(
            'harnesses = ["examples/minimal/harness.toml"]',
            'harnesses = ["examples/minimal/harness.toml", "examples/minimal/fixture-alt.toml"]',
        )
        self.sparse = (self.matrix + '\n[[pairs]]\nagent = "rtl-team"\nharness = "fixture-alt"\n'
                       '[[pairs]]\nagent = "rtl-solo"\nharness = "fixture"\n')

    def load(self, text):
        self.experiment.write_text(text, encoding="utf-8")
        return load_experiment(self.experiment)

    def plan(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["plan", str(self.experiment)])
        return code, json.loads(output.getvalue()) if code == 0 else None

    def limited(self, text, trials):
        return (text.replace('max_trials = 40', f'max_trials = {trials}')
                .replace('inputs = ["baseline"]', 'inputs = ["baseline"]\nmax_trials = 1'))

    def test_absent_pairs_selects_agent_major_full_product(self):
        spec = self.load(self.matrix)
        self.assertEqual([(agent.id, profile["id"]) for agent, profile in config.selected_pairs(spec)], [
            ("rtl-solo", "fixture"), ("rtl-solo", "fixture-alt"),
            ("rtl-team", "fixture"), ("rtl-team", "fixture-alt"),
        ])

    def test_declared_pairs_follow_order_and_keep_raw_config(self):
        spec = self.load(self.matrix + '\n[[pairs]]\nagent = "rtl-team"\nharness = "fixture-alt"\n'
                         '[[pairs]]\nagent = "rtl-solo"\nharness = "fixture"\n')
        self.assertEqual([(agent.id, profile["id"]) for agent, profile in config.selected_pairs(spec)], [
            ("rtl-team", "fixture-alt"), ("rtl-solo", "fixture"),
        ])
        self.assertEqual(spec["pairs"], [
            {"agent": "rtl-team", "harness": "fixture-alt"},
            {"agent": "rtl-solo", "harness": "fixture"},
        ])

    def test_invalid_pair_declarations_fail_during_loading(self):
        valid = '\n[[pairs]]\nagent = "rtl-team"\nharness = "fixture-alt"\n'
        cases = {
            "empty list": 'pairs = []\n',
            "string": 'pairs = "bad"\n',
            "string item": 'pairs = ["bad"]\n',
            "extra key": valid + 'unused = true\n[[pairs]]\nagent = "rtl-solo"\nharness = "fixture"\n',
            "missing id": valid + '[[pairs]]\nagent = "rtl-solo"\n',
            "empty id": valid + '[[pairs]]\nagent = "rtl-solo"\nharness = ""\n',
            "non-string id": valid + '[[pairs]]\nagent = 42\nharness = "fixture"\n',
            "duplicate": valid + '[[pairs]]\nagent = "rtl-team"\nharness = "fixture-alt"\n',
            "unknown agent": valid + '[[pairs]]\nagent = "unknown"\nharness = "fixture"\n',
            "unknown profile": valid + '[[pairs]]\nagent = "rtl-solo"\nharness = "unknown"\n',
            "unused agent": valid + '[[pairs]]\nagent = "rtl-team"\nharness = "fixture"\n',
            "unused profile": '[[pairs]]\nagent = "rtl-solo"\nharness = "fixture"\n'
                              '[[pairs]]\nagent = "rtl-team"\nharness = "fixture"\n',
        }
        for label, declaration in cases.items():
            with self.subTest(label=label), self.assertRaises(ConfigurationError) as caught:
                text = (self.matrix.replace('[budget]', declaration + '\n[budget]', 1)
                        if declaration.startswith('pairs = ') else self.matrix + '\n' + declaration)
                self.load(text)
            self.assertNotIn("Unknown experiment keys", str(caught.exception))

    def test_support_is_checked_only_for_selected_pairs(self):
        solo = self.example / "solo.toml"
        solo.write_text(solo.read_text(encoding="utf-8").replace(
            '["fixture", "opencode", "command"]', '["fixture"]'), encoding="utf-8")
        alt = self.example / "fixture-alt.toml"
        alt.write_text('id = "fixture-alt"\nadapter = "command"\nallow_local = true\n'
                       '[runtime]\nkind = "local"\n', encoding="utf-8")
        with self.assertRaises(ConfigurationError):
            self.load(self.matrix)
        spec = self.load(self.matrix + '\n[[pairs]]\nagent = "rtl-team"\nharness = "fixture-alt"\n'
                         '[[pairs]]\nagent = "rtl-solo"\nharness = "fixture"\n')
        self.assertEqual([(agent.id, profile["id"]) for agent, profile in config.selected_pairs(spec)], [
            ("rtl-team", "fixture-alt"), ("rtl-solo", "fixture"),
        ])
        with self.assertRaises(ConfigurationError):
            self.load(self.matrix + '\n[[pairs]]\nagent = "rtl-solo"\nharness = "fixture-alt"\n'
                      '[[pairs]]\nagent = "rtl-team"\nharness = "fixture"\n')

    def test_default_selection_reads_current_agents_and_profiles(self):
        spec = self.load(self.original)
        other = dict(spec["_profiles"][0], id="fixture-alt")
        spec["_profiles"].append(other)
        self.assertEqual([(agent.id, profile["id"]) for agent, profile in config.selected_pairs(spec)], [
            ("rtl-solo", "fixture"), ("rtl-solo", "fixture-alt"),
            ("rtl-team", "fixture"), ("rtl-team", "fixture-alt"),
        ])
        spec["_agents"] = spec["_agents"][1:]
        self.assertEqual([(agent.id, profile["id"]) for agent, profile in config.selected_pairs(spec)], [
            ("rtl-team", "fixture"), ("rtl-team", "fixture-alt"),
        ])

    def test_default_matrix_runs_and_persists_agent_major_full_product(self):
        spec = self.load(self.limited(self.matrix, 16))
        expected = [("rtl-solo", "fixture"), ("rtl-solo", "fixture-alt"),
                    ("rtl-team", "fixture"), ("rtl-team", "fixture-alt")]
        code, plan = self.plan()
        self.assertEqual(code, 0)
        self.assertEqual([(row["agent"], row["harness"]) for row in plan["matrix"]], expected)
        run, summary = run_experiment(spec, Registry(), self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["planned_groups"], 4)
        self.assertEqual(summary["trials_used"], 14)
        self.assertEqual([(row["agent_id"], row["harness_id"]) for row in summary["groups"]], expected)
        self.assertNotIn("pairs", json.loads((run / "manifest.json").read_text())["experiment"])
        self.assertEqual(len(json.loads((run / "manifest.json").read_text())["agents"]), 2)
        self.assertEqual(json.loads((run / "summary.json").read_text())["planned_groups"], 4)
        self.assertEqual([(row["agent_id"], row["harness_id"])
                          for row in json.loads((run / "report.json").read_text())["groups"]], expected)

    def test_declared_matrix_runs_and_persists_only_ordered_pairs(self):
        origins = {"rtl-team": ("team", b"team snapshot origin\n"),
                   "rtl-solo": ("solo", b"solo snapshot origin\n")}
        for directory, marker in origins.values():
            (self.example / "agents" / directory / "configs/pair-origin.txt").write_bytes(marker)
        spec = self.load(self.limited(self.sparse, 8))
        expected = [("rtl-team", "fixture-alt"), ("rtl-solo", "fixture")]
        code, plan = self.plan()
        self.assertEqual(code, 0)
        self.assertEqual([(row["agent"], row["harness"]) for row in plan["matrix"]], expected)
        run, summary = run_experiment(spec, Registry(), self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["planned_groups"], 2)
        self.assertEqual(summary["trials_used"], 7)
        self.assertEqual([(row["agent_id"], row["harness_id"]) for row in summary["groups"]], expected)
        manifest = json.loads((run / "manifest.json").read_text())
        self.assertEqual(manifest["experiment"]["pairs"], [
            {"agent": "rtl-team", "harness": "fixture-alt"},
            {"agent": "rtl-solo", "harness": "fixture"},
        ])
        self.assertEqual({agent["id"] for agent in manifest["agents"]}, set(origins))
        locks = {agent["id"]: agent for agent in manifest["agents"]}
        self.assertEqual(len(locks), 2)
        for agent_id, (directory, marker) in origins.items():
            source = self.example / "agents" / directory
            bundle = run / "sources" / agent_id / "bundle"
            lock = json.loads((run / "sources" / agent_id / "source-lock.json").read_text())
            original_files = {
                path.relative_to(source).as_posix(): (path.read_bytes(), path.stat().st_mode & 0o111)
                for name in ("configs", "overlays", "prompts", "src")
                for path in (source / name).rglob("*") if path.is_file()
            }
            snapshot_files = {path.relative_to(bundle).as_posix():
                              (path.read_bytes(), path.stat().st_mode & 0o111)
                              for path in bundle.rglob("*") if path.is_file()}
            self.assertEqual(snapshot_files, original_files)
            self.assertEqual(snapshot_files["configs/pair-origin.txt"][0], marker)
            self.assertEqual(lock["agent_id"], agent_id)
            self.assertEqual(lock["path"], str(source.resolve()))
            self.assertEqual(locks[agent_id]["path"], str(source.resolve()))
            self.assertEqual(locks[agent_id]["content_hash"], lock["content_hash"])
            self.assertEqual(locks[agent_id]["content_hash"], digest(bundle))
            harness_id = next(harness for owner, harness in expected if owner == agent_id)
            self.assertEqual(digest(run / agent_id / harness_id / "candidates/c0001/bundle"),
                             locks[agent_id]["content_hash"])
        self.assertNotEqual(locks["rtl-team"]["content_hash"], locks["rtl-solo"]["content_hash"])
        saved = json.loads((run / "summary.json").read_text())
        self.assertEqual(saved["planned_groups"], 2)
        self.assertEqual([(row["agent_id"], row["harness_id"]) for row in saved["groups"]], expected)
        self.assertEqual([(row["agent_id"], row["harness_id"])
                          for row in json.loads((run / "report.json").read_text())["groups"]], expected)
        events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
        self.assertEqual({(row["agent_id"], row["harness_id"]) for row in events
                          if row["event"] == "trial_completed"}, set(expected))
        self.assertFalse((run / "rtl-team" / "fixture").exists())
        self.assertFalse((run / "rtl-solo" / "fixture-alt").exists())
        self.assertTrue((run / "report.html").is_file())

    def test_later_selected_harness_failure_preserves_only_selected_group_evidence(self):
        spec = self.load(self.limited(self.sparse, 8))

        class FailingSecondHarness(FixtureHarness):
            def run(self, request):
                if request.profile["id"] == "fixture":
                    raise RuntimeError("second selected harness failed")
                return super().run(request)

        registry = Registry()
        registry.factories["harnesses"]["fixture"] = FailingSecondHarness
        with self.assertRaisesRegex(RuntimeError, "second selected harness failed"):
            run_experiment(spec, registry, self.root / "runs")

        run, = (self.root / "runs").iterdir()
        summary = json.loads((run / "summary.json").read_text())
        report = json.loads((run / "report.json").read_text())
        manifest = json.loads((run / "manifest.json").read_text())
        events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
        selected = [("rtl-team", "fixture-alt"), ("rtl-solo", "fixture")]

        self.assertEqual(summary["status"], "error")
        self.assertEqual(summary["error_type"], "RuntimeError")
        self.assertEqual(summary["planned_groups"], 2)
        self.assertEqual(summary["trials_used"], 4)
        first, second = summary["groups"]
        self.assertEqual([(row["agent_id"], row["harness_id"]) for row in summary["groups"]], selected)
        self.assertEqual((first["status"], first["trial_count"]), ("completed", 3))
        self.assertIsNotNone(first["baseline"])
        self.assertTrue(first["selected"])
        self.assertTrue(first["final_test"])
        self.assertEqual((second["status"], second["trial_count"]), ("error", 1))
        self.assertIsNone(second["baseline"])
        self.assertEqual(second["stages"], [])
        self.assertEqual(second["selected"], [])
        self.assertEqual(second["final_test"], [])
        self.assertEqual({agent["id"] for agent in manifest["agents"]}, {"rtl-team", "rtl-solo"})
        self.assertEqual([(row["agent_id"], row["harness_id"]) for row in report["groups"]], selected)
        self.assertEqual(report["identity"]["status"], "error")
        self.assertEqual(report["counts"]["groups"], 2)
        self.assertEqual(report["counts"]["evaluations"], 4)
        self.assertEqual(report["groups"][0]["selected"], first["selected"])
        self.assertEqual(report["groups"][1]["baseline"], None)
        self.assertEqual(report["groups"][1]["selected"], [])
        failed, = report["groups"][1]["evaluations"]
        self.assertEqual((failed["status"], failed["valid"]), ("error", False))
        self.assertIsNone(failed["metrics"]["passed"])
        self.assertEqual(failed["failure"]["category"], "run_error")

        trials = [row for row in events if row["event"] == "trial_completed"]
        self.assertEqual([(row["agent_id"], row["harness_id"]) for row in trials],
                         [selected[0]] * 3 + [selected[1]])
        self.assertEqual((trials[-1]["status"], trials[-1]["valid"]), ("error", False))
        self.assertIsNone(trials[-1]["metrics"]["passed"])
        self.assertFalse(any(row["event"] == "candidate_evaluated" and
                             (row["agent_id"], row["harness_id"]) == selected[1] for row in events))
        self.assertEqual(events[-1]["event"], "error")
        self.assertEqual({(row["agent_id"], row["harness_id"]) for row in events
                          if "agent_id" in row and "harness_id" in row}, set(selected))
        result = run / "rtl-solo" / "fixture" / "trials" / trials[-1]["trial_id"] / "result.json"
        self.assertEqual(json.loads(result.read_text())["valid"], False)
        self.assertFalse((run / "rtl-team" / "fixture").exists())
        self.assertFalse((run / "rtl-solo" / "fixture-alt").exists())
        self.assertTrue((run / "report.html").is_file())

    def test_budget_minimum_tracks_pairs_even_when_doctor_has_other_failures(self):
        sparse = self.load(self.limited(self.sparse, 8))
        preflight(sparse, Registry())
        self.assertEqual(self.plan()[0], 0)
        (self.example / "agents/solo/prompts/system.md").unlink()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["doctor", "--plan", str(self.experiment), "--json"]), 2)
        checks = {row["id"]: row for row in json.loads(output.getvalue())["checks"]}
        self.assertEqual(checks["agent.prompt"]["status"], "error")
        self.assertEqual(checks["budget.trials"]["status"], "ok")
        full = self.load(self.limited(self.matrix, 8))
        with self.assertRaisesRegex(ConfigurationError, "at least 16 trials"):
            preflight(full, Registry())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["doctor", "--plan", str(self.experiment), "--json"]), 2)
        checks = {row["id"]: row for row in json.loads(output.getvalue())["checks"]}
        self.assertEqual(checks["budget.trials"]["status"], "error")
        self.assertIn("16", checks["budget.trials"]["message"])

    def test_selected_groups_keep_stage_history_and_freeze_before_test(self):
        spec = self.load(self.sparse)
        spec["stages"] = [
            {"id": "a", "optimizer": "history_fixture", "max_trials": 3, "config": {"repair": True}},
            {"id": "b", "optimizer": "history_fixture", "max_trials": 3, "config": {"repair": False}},
        ]
        spec.pop("final_stages")

        class HistoryOptimizer:
            def optimize(self, context, seeds, options):
                baseline, = seeds
                initial = context.history()
                context.evaluate(baseline)
                child = context.propose(baseline, {"configs/strategy.json":
                                                 json.dumps({"repair": options["repair"]})}, "history_fixture")
                context.evaluate(child)
                return OptimizationResult([child], {"initial": initial, "history": context.history(),
                                                     "baseline": baseline.id, "candidate": child.id})

        registry = Registry()
        registry.factories["optimizers"]["history_fixture"] = HistoryOptimizer
        original_trial = GroupRunner.trial

        def check_frozen(group, candidate, task, repeat):
            if task.split == "test":
                frozen = json.loads((group.root / "frozen_selection.json").read_text())
                self.assertEqual(frozen, group.summary["selected"])
                self.assertTrue(all(stage["status"] == "completed" for stage in group.summary["stages"]))
            return original_trial(group, candidate, task, repeat)

        with patch.object(GroupRunner, "trial", check_frozen):
            run, summary = run_experiment(spec, registry, self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        self.assertEqual([(row["agent_id"], row["harness_id"]) for row in summary["groups"]],
                         [("rtl-team", "fixture-alt"), ("rtl-solo", "fixture")])
        for group in summary["groups"]:
            a, b = [stage["checkpoint"] for stage in group["stages"]]
            self.assertEqual(a["initial"], [])
            self.assertEqual({row["candidate_id"] for row in b["initial"]}, {a["baseline"]})
            self.assertNotIn(a["candidate"], {row["candidate_id"] for row in b["history"]})
            self.assertEqual({row["candidate_id"] for row in b["history"]},
                             {b["baseline"], b["candidate"]})
            self.assertTrue(all(row["split"] == "train" and row["agent_id"] == group["agent_id"]
                                and row["harness_id"] == group["harness_id"] for row in b["history"]))
            frozen = run / group["agent_id"] / group["harness_id"] / "frozen_selection.json"
            self.assertEqual(json.loads(frozen.read_text()), group["selected"])
            self.assertTrue(group["final_test"])


if __name__ == "__main__":
    unittest.main()
