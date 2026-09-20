from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import AgentSpec, Candidate, ConfigurationError, ExecutionResult, SourceSpec
from agent_optimizer.results import EventStore
from agent_optimizer.runner import Budget, GroupRunner
from agent_optimizer.sources import materialize_agent
from agent_optimizer.workspace import CandidateStore, collect_outputs, digest, safe_path
from support import ROOT, demo_registry, resolved_agent


class BoundaryFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "prompt.md").write_text("original")
        (self.source / "fixed.txt").write_text("fixed")
        self.agent = AgentSpec("agent", self.root, self.source, "test", ("command",),
                               ("prompt.md",), "prompt.md",
                               source=SourceSpec("local", path=self.source))


class OutputBoundaryTests(BoundaryFixture):
    def test_symlink_output_root_never_copies_host_sentinel(self):
        private = self.root / "private"
        private.mkdir()
        (private / "secret.txt").write_text("host sentinel")
        link_to_private_directory = self.root / "task"
        link_to_private_directory.symlink_to(private, target_is_directory=True)
        target = self.root / "evaluation"
        with self.assertRaises(ConfigurationError):
            collect_outputs(link_to_private_directory, target)
        self.assertFalse((target / "secret.txt").exists())

    def test_internal_links_rejected_before_any_copy(self):
        for index, link_target in enumerate((self.source / "prompt.md", self.root / "private.txt", self.source)):
            with self.subTest(target=link_target):
                (self.root / "private.txt").write_text("host sentinel")
                link = self.source / "z-link"
                link.symlink_to(link_target)
                target = self.root / f"evaluation-{index}"
                try:
                    with self.assertRaises(ConfigurationError):
                        collect_outputs(self.source, target)
                    self.assertFalse((target / "fixed.txt").exists())
                    self.assertFalse((target / "z-link").exists())
                finally:
                    link.unlink()

    def test_missing_or_nondirectory_output_root_rejected(self):
        for source in (self.root / "missing", self.source / "prompt.md"):
            with self.subTest(source=source), self.assertRaises(ConfigurationError):
                collect_outputs(source, self.root / "evaluation")

    def test_special_output_file_rejected_before_copy(self):
        os.mkfifo(self.source / "z-pipe")
        target = self.root / "evaluation"
        with self.assertRaises(ConfigurationError):
            collect_outputs(self.source, target)
        self.assertFalse((target / "fixed.txt").exists())

    def test_destination_link_cannot_overwrite_host_file(self):
        target = self.root / "evaluation"
        target.mkdir()
        private = self.root / "private.txt"
        private.write_text("host sentinel")
        (target / "fixed.txt").symlink_to(private)
        with self.assertRaises(ConfigurationError):
            collect_outputs(self.source, target)
        self.assertEqual(private.read_text(), "host sentinel")

    def test_safe_path_rejects_links_even_within_boundary(self):
        (self.source / "nested").mkdir()
        (self.source / "link").symlink_to(self.source / "nested", target_is_directory=True)
        with self.assertRaises(ConfigurationError):
            safe_path(self.source, "link/new.txt")

    def test_directory_output_destination_rejected_before_any_copy(self):
        (self.source / "foo").write_bytes(b"attacker output")
        private = self.root / "private.txt"
        private.write_bytes(b"host sentinel")
        target = self.root / "evaluation"
        (target / "foo").mkdir(parents=True)
        (target / "foo/foo").symlink_to(private)
        try:
            with self.assertRaises(ConfigurationError):
                collect_outputs(self.source, target)
        finally:
            self.assertEqual(private.read_bytes(), b"host sentinel")
            self.assertFalse((target / "fixed.txt").exists())

    def test_normal_outputs_and_host_ancestor_alias_are_supported(self):
        alias = self.root / "host-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        target = alias / "evaluation"
        collect_outputs(alias / "source", target)
        self.assertEqual((target / "prompt.md").read_text(), "original")
        self.assertEqual((target / "fixed.txt").read_text(), "fixed")


class CandidateBoundaryTests(BoundaryFixture):
    def setUp(self):
        super().setUp()
        self.store = CandidateStore(self.root / "candidates", self.agent)

    def verify(self, candidate):
        self.assertTrue(callable(getattr(self.store, "verify", None)),
                        "CandidateStore.verify must enforce issued identity and current bytes")
        self.store.verify(candidate)

    def test_normal_parent_lineage_and_exact_metadata_copy(self):
        baseline = self.store.create()
        child = self.store.create(baseline, {"prompt.md": "changed"}, "optimizer")
        grandchild = self.store.create(child, {"prompt.md": "next"}, "optimizer")
        self.verify(replace(baseline))
        self.verify(child)
        self.verify(grandchild)
        self.assertEqual(child.parents, (baseline.id,))
        self.assertEqual(grandchild.parents, (child.id,))
        self.assertEqual((self.source / "prompt.md").read_text(), "original")

    def test_issued_candidate_metadata_substitution_rejected(self):
        baseline = self.store.create()
        child = self.store.create(baseline, {"prompt.md": "changed"}, "optimizer")
        substitutions = {"id": baseline.id, "agent_id": "another-agent",
                         "content_hash": baseline.content_hash, "path": baseline.path,
                         "parents": (), "producer": "baseline"}
        for field, value in substitutions.items():
            with self.subTest(field=field), self.assertRaises(ConfigurationError):
                self.verify(replace(child, **{field: value}))

    def test_unknown_id_cannot_seed_creation(self):
        candidate = replace(self.store.create(), id="unissued")
        with self.assertRaises(ConfigurationError):
            self.store.create(candidate, {"prompt.md": "changed"})

    def test_same_agent_candidate_from_other_store_rejected(self):
        other = CandidateStore(self.root / "other", self.agent)
        self.store.create()
        with self.assertRaises(ConfigurationError):
            self.store.create(other.create())

    def test_editable_and_noneditable_mutation_rejected_even_with_new_hash(self):
        for relative in ("prompt.md", "fixed.txt"):
            with self.subTest(relative=relative):
                candidate = self.store.create()
                (candidate.path / relative).write_text("tampered")
                with self.assertRaises(ConfigurationError):
                    self.verify(candidate)
                forged = replace(candidate, content_hash=digest(candidate.path))
                with self.assertRaises(ConfigurationError):
                    self.verify(forged)
                with self.assertRaises(ConfigurationError):
                    self.store.create(forged)

    def test_added_cache_file_changes_candidate_contents(self):
        candidate = self.store.create()
        cache = candidate.path / "__pycache__"
        cache.mkdir()
        (cache / "extra.pyc").write_bytes(b"tampered")
        with self.assertRaises(ConfigurationError):
            self.verify(candidate)

    def test_failed_materialization_does_not_issue_candidate(self):
        candidate_dir = self.store.root / "c0001"
        (candidate_dir / "candidate.json").mkdir(parents=True)
        with self.assertRaises(OSError):
            self.store.create()
        bundle = candidate_dir / "bundle"
        failed = Candidate("c0001", self.agent.id, bundle, digest(bundle))
        with self.assertRaises(ConfigurationError):
            self.verify(failed)
        with self.assertRaises(ConfigurationError):
            self.store.create(failed)

    def test_candidate_bundle_and_parent_directory_links_rejected(self):
        for replace_parent in (False, True):
            with self.subTest(replace_parent=replace_parent):
                candidate = self.store.create()
                replaced = candidate.path.parent if replace_parent else candidate.path
                saved = self.root / (candidate.id + "-saved")
                replaced.rename(saved)
                replaced.symlink_to(saved, target_is_directory=True)
                with self.assertRaises(ConfigurationError):
                    self.verify(candidate)
                with self.assertRaises(ConfigurationError):
                    self.store.create(candidate)

    def test_preexisting_destination_link_is_rejected(self):
        private = self.root / "private"
        private.mkdir()
        (self.store.root / "c0001").symlink_to(private, target_is_directory=True)
        with self.assertRaises(ConfigurationError):
            self.store.create()
        self.assertFalse((private / "bundle").exists())

    def test_verification_precedes_cached_evaluation(self):
        spec = load_experiment(ROOT / "examples/minimal/experiment.toml")
        agent = resolved_agent(ROOT / "examples/minimal/solo.toml", self.root / "resolved")
        group = GroupRunner(spec, agent, spec["_profiles"][0], self.root / "group",
                            demo_registry(), Budget(spec["budget"]),
                            EventStore(self.root / "events.jsonl"))
        baseline = group.candidates.create()
        cached = group.evaluate(baseline, "validation")
        self.assertEqual(group.evaluate(baseline, "validation"), cached)
        child = group.candidates.create(baseline, {"prompts/system.md": "changed"})
        with self.assertRaises(ConfigurationError):
            group.evaluate(replace(child, id=baseline.id), "validation")
        (baseline.path / "prompts/system.md").write_text("tampered")
        with self.assertRaises(ConfigurationError):
            group.evaluate(baseline, "validation")
        self.assertEqual(group.budget.used, 1)

    def test_runner_rejects_replaced_workspace_ancestor_before_collection(self):
        private = self.root / "private"
        (private / "task").mkdir(parents=True)
        (private / "task/secret.txt").write_text("host sentinel")

        class ReplacingHarness:
            def run(self, request):
                shutil.rmtree(request.workspace)
                request.workspace.symlink_to(private, target_is_directory=True)
                return ExecutionResult("completed", 0, 0.0, "", "")

        spec = load_experiment(ROOT / "examples/minimal/experiment.toml")
        agent = resolved_agent(ROOT / "examples/minimal/solo.toml", self.root / "resolved")
        group = GroupRunner(spec, agent, spec["_profiles"][0], self.root / "group",
                            demo_registry(), Budget(spec["budget"]),
                            EventStore(self.root / "events.jsonl"))
        group.harness = ReplacingHarness()
        with self.assertRaises(ConfigurationError):
            group.evaluate(group.candidates.create(), "validation")
        self.assertFalse(list((group.root / "trials").glob("*/evaluation_workspace/secret.txt")))


class SourceSelectionTests(BoundaryFixture):
    def write_asset(self, name):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("reviewed runtime asset")

    def snapshot(self, include=("*",), exclude=()):
        agent = replace(self.agent, bundle=None,
                        source=replace(self.agent.source, include=include, exclude=exclude))
        return materialize_agent(agent, self.root / "snapshot")[0].bundle

    def test_default_wildcards_do_not_include_developer_directories(self):
        names = (".opencode/agents/review.md", ".claude/agents/review.md",
                 ".codex/config.toml", ".cursor/rules/review.md")
        for name in names:
            self.write_asset(name)
        bundle = self.snapshot(("*", "**/*.md", ".*/**"))
        self.assertTrue((bundle / "prompt.md").is_file())
        for name in names:
            self.assertFalse((bundle / name).exists())

    def test_explicit_developer_prefix_includes_only_reviewed_assets(self):
        self.write_asset(".opencode/agents/review.md")
        self.write_asset(".opencode/plugins/local.py")
        self.write_asset(".claude/agents/review.md")
        bundle = self.snapshot(("*", ".opencode/agents/**"))
        self.assertTrue((bundle / ".opencode/agents/review.md").is_file())
        self.assertEqual((bundle / ".opencode/agents/review.md").read_text(),
                         "reviewed runtime asset")
        self.assertFalse((bundle / ".opencode/plugins/local.py").exists())
        self.assertFalse((bundle / ".claude/agents/review.md").exists())

    def test_explicit_exclude_still_wins_over_reviewed_prefix(self):
        self.write_asset(".opencode/agents/review.md")
        bundle = self.snapshot(("*", ".opencode/agents/**"), ("**/review.md",))
        self.assertFalse((bundle / ".opencode/agents/review.md").exists())

    def test_explicit_auth_env_ide_and_cache_includes_cannot_override_exclusions(self):
        names = (".env", ".env.local", ".envrc", "nested/.env.example",
                 ".opencode/auth.json", ".codex/auth.json", ".claude/.credentials.json",
                 "credentials.json", "nested/auth.json", ".netrc", ".git-credentials",
                 ".git/config", ".vscode/settings.json", ".idea/project.xml",
                 ".venv/config", "__pycache__/module.pyc", ".pytest_cache/state")
        for name in names:
            self.write_asset(name)
        bundle = self.snapshot(("*", *names))
        for name in names:
            with self.subTest(name=name):
                self.assertFalse((bundle / name).exists())

    def test_local_source_root_and_subdir_links_rejected(self):
        alias = self.root / "source-link"
        alias.symlink_to(self.source, target_is_directory=True)
        for source in (replace(self.agent.source, path=alias),
                       replace(self.agent.source, path=self.root, subdir="source-link")):
            with self.subTest(source=source), self.assertRaises(ConfigurationError):
                materialize_agent(replace(self.agent, source=source), self.root / "snapshot")
            if (self.root / "snapshot").exists():
                shutil.rmtree(self.root / "snapshot")

    def test_selected_special_source_file_rejected(self):
        os.mkfifo(self.source / "pipe")
        with self.assertRaises(ConfigurationError):
            self.snapshot()
