from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.cli import main
from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError, ExecutionResult, RunRequest, UnavailableError
from agent_optimizer.harnesses.claude_code import ClaudeCodeHarness
from agent_optimizer.locale import render_diagnostic
from agent_optimizer.readiness import collect_plan
from agent_optimizer.registry import Registry
from agent_optimizer.setup_wizard import supports_generated_profile
from support import ROOT, module, test_project


SUCCESS = {"type": "result", "subtype": "success", "is_error": False,
           "usage": {"input_tokens": 12, "output_tokens": 3}, "total_cost_usd": 0.01}


class ClaudeCodeContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.logs = self.root / "logs"
        self.request = RunRequest(self.workspace, self.workspace / "agent", self.workspace / "task",
                                  "prompt ; $(ignored)", 5, 3, {"runtime": {"kind": "local"}}, self.logs)
        self.harness = ClaudeCodeHarness()

    def run_events(self, events, *, status="completed", returncode=0, version="2.1.261 (Claude Code)\n"):
        self.logs.mkdir(exist_ok=True)
        output, err = self.logs / "stdout.log", self.logs / "stderr.log"
        output.write_text("\n".join(json.dumps(event) if not isinstance(event, str) else event
                                    for event in events), encoding="utf-8")
        err.write_text("", encoding="utf-8")
        fixture = ExecutionResult(status, returncode, 0.1, str(output), str(err))
        with patch("agent_optimizer.harnesses.claude_code.subprocess.run",
                   return_value=subprocess.CompletedProcess(["claude", "--version"], 0, version, "")), \
             patch("agent_optimizer.harnesses.command.execute", return_value=fixture):
            return self.harness.run(self.request)

    def test_argv_keeps_prompt_separate_and_refuses_docker(self):
        self.assertEqual(self.harness.argv(self.request),
                         ["claude", "-p", self.request.prompt, "--output-format", "stream-json",
                          "--verbose", "--max-turns", "8", "--tools", "Read,Write,Edit",
                          "--allowedTools", "Read,Write,Edit"])
        docker = RunRequest(self.workspace, self.request.agent_dir, self.request.task_dir,
                            self.request.prompt, 5, 3, {"runtime": {"kind": "docker"}}, self.logs)
        with self.assertRaises(UnavailableError):
            self.harness.argv(docker)
        with patch("agent_optimizer.harnesses.claude_code.subprocess.run") as version:
            with self.assertRaises(UnavailableError):
                self.harness.run(docker)
            version.assert_not_called()

    def test_success_records_only_partial_usage_and_observed_version(self):
        result = self.run_events([SUCCESS])
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.metrics["harness_reported_io_tokens"], 15)
        self.assertEqual(result.metrics["harness_reported_cost_usd"], 0.01)
        self.assertEqual(result.metrics["unparsed_event_lines"], 0)
        self.assertIsNone(result.metrics["agent_tokens"])
        self.assertIsNone(result.metrics["agent_cost_usd"])
        self.assertEqual((self.logs / "cli-version.txt").read_text(), "2.1.261\n")
        self.assertTrue((self.workspace / "request.json").exists())

    def test_missing_bad_or_ambiguous_result_is_infrastructure_error(self):
        cases = {
            "missing": [],
            "execution_error": [{**SUCCESS, "subtype": "error_during_execution"}],
            "is_error": [{**SUCCESS, "is_error": True, "result": "secret model output"}],
            "malformed": ['{"type":"result",', "not json"],
            "duplicate": [SUCCESS, SUCCESS],
            "model_error": [{"type": "error", "error": {"message": "private credential"}}, SUCCESS],
            "auth_error": [{"type": "auth_status", "error": "private credential"}, SUCCESS],
        }
        for label, events in cases.items():
            with self.subTest(label=label):
                result = self.run_events(events)
                self.assertEqual(result.status, "infrastructure_error")
                self.assertNotIn("secret model output", result.detail)
                self.assertNotIn("private credential", result.detail)
                if label == "malformed":
                    self.assertEqual(result.metrics["unparsed_event_lines"], 2)

    def test_malformed_line_before_success_result_is_infrastructure_error(self):
        result = self.run_events(['{"type":"error","message":"private credential"', SUCCESS])
        self.assertEqual(result.status, "infrastructure_error")
        self.assertEqual(result.metrics["unparsed_event_lines"], 1)
        self.assertNotIn("private credential", result.detail)

    def test_bad_cost_and_incomplete_usage_remain_unreported(self):
        for cost in (-0.1, float("nan"), True, "0.01", 10**1000):
            with self.subTest(cost=cost):
                result = self.run_events([{**SUCCESS, "total_cost_usd": cost}])
                self.assertEqual(result.status, "completed")
                self.assertIsNone(result.metrics["harness_reported_cost_usd"])
        for usage in ({"input_tokens": 12}, {"input_tokens": -1, "output_tokens": 3},
                      {"input_tokens": True, "output_tokens": 3},
                      {"input_tokens": float("nan"), "output_tokens": 3}):
            with self.subTest(usage=usage):
                result = self.run_events([{**SUCCESS, "usage": usage}])
                self.assertEqual(result.status, "completed")
                self.assertIsNone(result.metrics["harness_reported_io_tokens"])

    def test_process_failure_stays_noncompleted_and_timeout_stays_timeout(self):
        for status, code in (("process_error", 1), ("timeout", -9), ("infrastructure_error", None)):
            with self.subTest(status=status):
                result = self.run_events([SUCCESS], status=status, returncode=code)
                self.assertNotEqual(result.status, "completed")
                self.assertEqual(result.status, "infrastructure_error" if status == "process_error" else status)

    def test_version_mismatch_and_failed_probe_are_nullable_infrastructure_results(self):
        self.request.profile["required_cli_version"] = "2.1.261"
        for version in (subprocess.CompletedProcess(["claude", "--version"], 0, "2.1.260 (Claude Code)\n", ""),
                        subprocess.CompletedProcess(["claude", "--version"], 1, "", "private credential"),
                        subprocess.CompletedProcess(["claude", "--version"], 0, "", "")):
            with self.subTest(version=version.returncode, stdout=version.stdout):
                with patch("agent_optimizer.harnesses.claude_code.subprocess.run", return_value=version), \
                     patch("agent_optimizer.harnesses.command.execute") as execute:
                    result = self.harness.run(self.request)
                execute.assert_not_called()
                self.assertEqual(result.status, "infrastructure_error")
                self.assertIsNone(result.returncode)
                self.assertNotIn("private credential", result.detail)
        self.assertFalse((self.logs / "cli-version.txt").exists())

    def test_missing_cli_and_version_timeout_are_infrastructure_errors(self):
        for failure in (FileNotFoundError("private credential"),
                        subprocess.TimeoutExpired(["claude", "--version"], 5, stderr=b"private credential")):
            with self.subTest(failure=type(failure).__name__):
                with patch("agent_optimizer.harnesses.claude_code.subprocess.run", side_effect=failure), \
                     patch("agent_optimizer.harnesses.command.execute") as execute:
                    result = self.harness.run(self.request)
                execute.assert_not_called()
                self.assertEqual(result.status, "infrastructure_error")
                self.assertNotIn("private credential", result.detail)

    def test_fake_cli_passes_through_real_process_execute(self):
        binary = self.root / "bin"
        binary.mkdir()
        fake = binary / "claude"
        fake.write_text("#!/usr/bin/env python3\n"
                        "import json, pathlib, sys\n"
                        "if sys.argv[1:] == ['--version']:\n"
                        "    print('2.1.261 (Claude Code)')\n"
                        "else:\n"
                        "    assert sys.argv[1:4] == ['-p', 'prompt ; $(ignored)', '--output-format']\n"
                        "    pathlib.Path('task/answer.txt').write_text('fixture result')\n"
                        f"    print(json.dumps({SUCCESS!r}))\n", encoding="utf-8")
        fake.chmod(0o755)
        self.request.task_dir.mkdir()
        self.request.profile["required_cli_version"] = "2.1.261"
        with patch.dict(os.environ, {"PATH": str(binary) + os.pathsep + os.environ.get("PATH", "")}):
            result = self.harness.run(self.request)
        self.assertEqual(result.status, "completed", result.detail)
        self.assertEqual(result.metrics["harness_reported_io_tokens"], 15)
        self.assertEqual(result.metrics["harness_reported_cost_usd"], 0.01)
        self.assertEqual((self.request.task_dir / "answer.txt").read_text(), "fixture result")
        self.assertEqual((self.logs / "cli-version.txt").read_text(), "2.1.261\n")


class ClaudeCodeSelectionTests(unittest.TestCase):
    def test_builtin_harness_is_resolvable_and_can_generate_profile(self):
        registry = Registry()
        self.assertIs(registry.resolve("harnesses", "claude_code"), ClaudeCodeHarness)
        self.assertTrue(supports_generated_profile(ClaudeCodeHarness))
        capabilities = registry.describe()["capabilities"]["claude_code"]
        self.assertEqual(capabilities.trace, "json_events")
        self.assertFalse(capabilities.complete_token_accounting)
        self.assertFalse(capabilities.isolated_runtime_available)

    def test_init_creates_local_claude_code_profile_without_example_version_pin(self):
        temporary, root = test_project()
        self.addCleanup(temporary.cleanup)
        arguments = ["init", "--project-root", str(root), "--name", "claude-demo",
                     "--agent", str(root / "examples/minimal/agents/solo"),
                     "--dataset", str(root / "examples/minimal/tasks.json"),
                     "--evaluator", "examples/minimal/evaluator.py:TextFixtureEvaluator",
                     "--optimizer", "baseline", "--editable", "configs/strategy.json",
                     "--harness", "claude_code", "--yes"]
        with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(arguments), 0)
        experiment = Path(json.loads(output.getvalue())["experiment"])
        profile = load_experiment(experiment)["_profiles"][0]
        self.assertEqual(profile["adapter"], "claude_code")
        self.assertEqual(profile["runtime"]["kind"], "local")
        self.assertTrue(profile["allow_local"])
        self.assertNotIn("command", profile)
        self.assertNotIn("required_cli_version", profile)

    def test_experiment_accepts_nonempty_version_pin_and_rejects_invalid_types(self):
        temporary, root = test_project()
        self.addCleanup(temporary.cleanup)
        profile = root / "examples/minimal/harness.toml"
        original = profile.read_text(encoding="utf-8")
        experiment = root / "examples/minimal/experiment.toml"
        profile.write_text('required_cli_version = "2.1.261"\n' + original, encoding="utf-8")
        self.assertEqual(load_experiment(experiment)["_profiles"][0]["required_cli_version"], "2.1.261")
        for invalid in ('""', '"   "', '261', 'true'):
            with self.subTest(invalid=invalid):
                profile.write_text(f"required_cli_version = {invalid}\n" + original, encoding="utf-8")
                with self.assertRaises(ConfigurationError):
                    load_experiment(experiment)

    def test_doctor_plan_checks_missing_and_present_claude_binary(self):
        temporary, root = test_project()
        self.addCleanup(temporary.cleanup)
        profile = root / "examples/minimal/harness.toml"
        profile.write_text('id = "claude"\nadapter = "claude_code"\nallow_local = true\n'
                           '[runtime]\nkind = "local"\n', encoding="utf-8")
        for name in ("solo", "team"):
            manifest = root / f"examples/minimal/{name}.toml"
            manifest.write_text(manifest.read_text(encoding="utf-8").replace(
                'supported_harnesses = ["fixture", "opencode", "command"]',
                'supported_harnesses = ["claude_code"]'), encoding="utf-8")
        plan = root / "examples/minimal/experiment.toml"
        for available, expected in ((False, "error"), (True, "ok")):
            with self.subTest(available=available), patch(
                    "agent_optimizer.readiness.shutil.which",
                    side_effect=lambda name: "/usr/bin/claude" if available and name == "claude" else None):
                report = collect_plan(plan, Registry())
            check = next(row for row in report["checks"] if row["id"] == "runtime.binary")
            self.assertEqual(next(row for row in report["checks"] if row["id"] == "plan.schema")["status"], "ok")
            self.assertEqual(check["status"], expected)
            if not available:
                self.assertFalse(report["ready"])
                self.assertIn("Claude Code", check["remedy"])
                self.assertIn("claude", check["remedy"])
                self.assertIn("설치하세요", render_diagnostic(check, lang="ko")[1])
                self.assertIn("Claude Code (claude)", render_diagnostic(check, lang="en")[1])
            else:
                self.assertEqual(check["remedy"], "")
                self.assertTrue(report["ready"], report)


class ACEClaudeExampleTests(unittest.TestCase):
    def setUp(self):
        self.temporary, self.root = test_project()
        self.addCleanup(self.temporary.cleanup)
        benchmark = self.root / "datasets/ace-demo/tasks.json"
        benchmark.parent.mkdir(parents=True)
        public = json.loads((self.root / "examples/minimal/tasks.json").read_text(encoding="utf-8"))
        public["tasks"] = public["tasks"][:2]
        benchmark.write_text(json.dumps(public), encoding="utf-8")

    def test_separate_claude_experiment_selects_ace_and_four_trial_budget(self):
        original = load_experiment(self.root / "examples/ace-rtl/experiment.toml")
        claude = load_experiment(self.root / "examples/ace-rtl/experiment-claude.toml")
        self.assertEqual(original["_agents"][0].supported_harnesses,
                         ("ace_opencode", "ace_claude_code"))
        self.assertEqual(original["_profiles"][0]["adapter"], "ace_opencode")
        self.assertEqual(original["stages"][0]["config"]["iterations"], 3)
        self.assertEqual(claude["name"], "ace-rtl-claude-cvdp-demo")
        self.assertEqual(claude["benchmark"], "datasets/ace-demo/tasks.json")
        self.assertEqual(claude["evaluator"], "cvdp")
        self.assertFalse(claude["final_test"])
        self.assertEqual(claude["budget"]["max_trials"], 4)
        self.assertEqual(claude["stages"][0]["optimizer"], "simple_feedback")
        self.assertEqual(claude["stages"][0]["config"]["iterations"], 1)
        self.assertEqual(claude["stages"][0]["config"]["file"],
                         "skills/ace-rtl/references/role-guidance.md")
        self.assertEqual({task.split for task in claude["_tasks"]}, {"train", "validation"})
        self.assertEqual(claude["_profiles"][0]["adapter"], "ace_claude_code")
        self.assertEqual(claude["_profiles"][0]["runtime"]["kind"], "local")
        self.assertTrue(claude["_profiles"][0]["allow_local"])
        self.assertEqual(claude["_profiles"][0]["required_cli_version"], "2.1.261")
        registry = Registry()
        registry.load_plugins(self.root, {"harnesses": claude["plugins"]["harnesses"]})
        self.assertTrue(issubclass(registry.resolve("harnesses", "ace_claude_code"), ClaudeCodeHarness))

    def test_claude_adapter_prepends_candidate_guidance_without_mutating_request(self):
        adapter = module("ace_claude_adapter_guidance", ROOT / "examples/ace-rtl/adapter.py")
        agent = self.root / "candidate"
        guidance = agent / "skills/ace-rtl/references/role-guidance.md"
        guidance.parent.mkdir(parents=True)
        guidance.write_text("candidate-guidance", encoding="utf-8")
        request = RunRequest(self.root, agent, self.root / "task", "public task", 0, 30,
                             {"runtime": {"kind": "local"}}, self.root / "logs")
        with patch.object(ClaudeCodeHarness, "run", return_value="executed") as execute:
            self.assertEqual(adapter.ACEClaudeCode().run(request), "executed")
        submitted = execute.call_args.args[0]
        self.assertIn("candidate-guidance", submitted.prompt)
        self.assertTrue(submitted.prompt.endswith("public task"))
        self.assertEqual(request.prompt, "public task")

    def test_claude_launcher_rejects_unapproved_source_and_uses_selected_lifecycle(self):
        adapter = module("ace_claude_adapter_launcher", ROOT / "examples/ace-rtl/adapter.py")
        approved = {"_source": ROOT / "examples/ace-rtl/experiment-claude.toml", "_root": ROOT}
        for altered in ({**approved, "_source": ROOT / "examples/ace-rtl/experiment.toml"},
                        {**approved, "_root": self.root}):
            with self.subTest(altered=altered), self.assertRaises(ConfigurationError):
                adapter.ACEClaudeCode.launch_existing(altered)
        stub = self.root / "lifecycle.py"
        stub.write_text('def run(root, *, experiment_file="experiment.toml"):\n'
                        '    return 17 if experiment_file == "experiment-claude.toml" else 18\n', encoding="utf-8")
        with patch.object(adapter, "safe_path", return_value=stub):
            self.assertEqual(adapter.ACEClaudeCode.launch_existing(approved), 17)

    def test_claude_preflight_checks_credentials_before_assets_and_cli(self):
        lifecycle = module("ace_claude_lifecycle_missing", ROOT / "examples/ace-rtl/environment/lifecycle.py")
        credentials = {"ANTHROPIC_AUTH_TOKEN": "fixture-secret", "ANTHROPIC_BASE_URL": "https://example.invalid",
                       "ANTHROPIC_MODEL": "fixture-model"}
        for missing in credentials:
            with self.subTest(missing=missing), patch.dict(os.environ, {**credentials, missing: ""}, clear=True), \
                 patch.object(lifecycle, "inspect") as inspect, \
                 patch.object(lifecycle, "load_example") as loader, \
                 patch("agent_optimizer.harnesses.claude_code.subprocess.run") as cli:
                with self.assertRaises(UnavailableError) as error:
                    lifecycle.run(ROOT, experiment_file="experiment-claude.toml")
                self.assertIn(missing, str(error.exception))
                self.assertNotIn("fixture-secret", str(error.exception))
                inspect.assert_not_called()
                loader.assert_not_called()
                cli.assert_not_called()

    def test_claude_preflight_stops_on_missing_evaluation_assets_without_cli(self):
        lifecycle = module("ace_claude_lifecycle_unready", ROOT / "examples/ace-rtl/environment/lifecycle.py")
        credentials = {"ANTHROPIC_AUTH_TOKEN": "fixture-secret", "ANTHROPIC_BASE_URL": "https://example.invalid",
                       "ANTHROPIC_MODEL": "fixture-model"}
        report = {"ready": False, "checks": [{"id": "image.evaluation", "area": "evaluation", "status": "error"}]}
        with patch.dict(os.environ, credentials, clear=True), \
             patch.object(lifecycle, "inspect", return_value=report) as inspect, \
             patch.object(lifecycle, "load_example") as loader, \
             patch("agent_optimizer.harnesses.claude_code.subprocess.run") as cli:
            with self.assertRaisesRegex(UnavailableError, "image.evaluation"):
                lifecycle.run(ROOT, experiment_file="experiment-claude.toml")
            inspect.assert_called_once()
            loader.assert_not_called()
            cli.assert_not_called()
            self.assertNotIn("OPENCODE_CONFIG", os.environ)

    def test_claude_preflight_passes_selected_experiment_without_opencode_setup(self):
        lifecycle = module("ace_claude_lifecycle_ready", ROOT / "examples/ace-rtl/environment/lifecycle.py")
        credentials = {"ANTHROPIC_AUTH_TOKEN": "fixture-secret", "ANTHROPIC_BASE_URL": "https://example.invalid",
                       "ANTHROPIC_MODEL": "fixture-model"}
        lock = {"platform": "linux/amd64", "images": {"evaluation": {"id": "eval"}}}
        report = {"ready": True, "checks": [], "lock": lock, "platform": "linux/amd64", "sim_image": "sim"}
        seen = []

        def load(root, relative, name):
            if relative.endswith("setup.py"):
                return SimpleNamespace(validate_live=lambda: self.fail("OpenCode setup called"))
            if relative.endswith("checks.py"):
                return SimpleNamespace(live=lambda *args, **kwargs: seen.append((args, kwargs, dict(os.environ))) or 0)
            self.fail(relative)

        with patch.dict(os.environ, credentials, clear=True), \
             patch.object(lifecycle, "inspect", return_value=report), \
             patch.object(lifecycle, "load_example", side_effect=load):
            self.assertEqual(lifecycle.run(ROOT, experiment_file="experiment-claude.toml"), 0)
            self.assertEqual(dict(os.environ), credentials)
        self.assertEqual(seen[0][0], (lock,))
        self.assertEqual(seen[0][1]["experiment_file"], "experiment-claude.toml")
        self.assertEqual(seen[0][2]["OSS_SIM_IMAGE"], "sim")
        self.assertNotIn("OPENCODE_CONFIG", seen[0][2])

    def test_claude_preflight_does_not_require_opencode_agent_image(self):
        lifecycle = module("ace_claude_lifecycle_local_assets", ROOT / "examples/ace-rtl/environment/lifecycle.py")
        credentials = {"ANTHROPIC_AUTH_TOKEN": "fixture-secret", "ANTHROPIC_BASE_URL": "https://example.invalid",
                       "ANTHROPIC_MODEL": "fixture-model"}
        rows = [{"id": name, "area": "evaluation", "status": status}
                for name, status in (("environment.lock", "ok"), ("image.evaluation", "ok"),
                                     ("tools.evaluation", "ok"), ("image.agent", "error"),
                                     ("tools.opencode", "error"))]
        lock = {"platform": "linux/amd64", "images": {"evaluation": {"id": "eval"}}}
        calls = []

        def load(root, relative, name):
            if relative.endswith("diagnostics.py"):
                return SimpleNamespace(collect_checks=lambda *args, **kwargs: rows)
            if relative.endswith("setup.py"):
                return SimpleNamespace(read_environment_lock=lambda path: lock,
                                       verified_sim_image=lambda prepared: "sim")
            if relative.endswith("checks.py"):
                return SimpleNamespace(live=lambda *args, **kwargs: calls.append(kwargs) or 0)
            self.fail(relative)

        with patch.dict(os.environ, credentials, clear=True), patch.object(lifecycle, "load_example", side_effect=load):
            self.assertFalse(lifecycle.inspect(ROOT)["ready"])
            self.assertEqual(lifecycle.run(ROOT, experiment_file="experiment-claude.toml"), 0)
        self.assertEqual(calls, [{"iterations": None, "experiment_file": "experiment-claude.toml"}])

    def test_claude_live_uses_local_profile_without_agent_image(self):
        checks = module("ace_claude_live", ROOT / "examples/ace-rtl/environment/checks.py")
        captured = []

        def run(spec, registry, output, *, on_event):
            captured.append(spec)
            return output / "fixture", {"status": "completed"}

        with patch.object(checks, "ROOT", self.root), patch.object(checks, "run_experiment", side_effect=run), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(checks.live({"images": {"evaluation": {"id": "eval"}}},
                                         experiment_file="experiment-claude.toml"), 0)
        self.assertEqual(captured[0]["_profiles"][0]["runtime"], {"kind": "local"})
        self.assertEqual(captured[0]["budget"]["max_trials"], 4)
        self.assertEqual(captured[0]["budget"]["max_wall_time_seconds"], 4 * 600 + 60 + 180)

    def test_claude_live_rejects_unprepared_tasks_before_runner(self):
        checks = module("ace_claude_live_unprepared", ROOT / "examples/ace-rtl/environment/checks.py")
        benchmark = self.root / "datasets/ace-demo/tasks.json"
        fixture = json.loads(benchmark.read_text(encoding="utf-8"))
        fixture["tasks"] = fixture["tasks"][1:]
        benchmark.write_text(json.dumps(fixture), encoding="utf-8")
        with patch.object(checks, "ROOT", self.root), patch.object(checks, "run_experiment") as run:
            with self.assertRaises(ConfigurationError):
                checks.live({"images": {"evaluation": {"id": "eval"}}},
                            experiment_file="experiment-claude.toml")
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
