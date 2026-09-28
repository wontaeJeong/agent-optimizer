"""Textual 화면에서 실제 키 입력으로 프리셋과 실행 확인을 검증한다."""
import asyncio
import io
import json
import os
import threading
import time
import unittest
from pathlib import Path
from contextlib import redirect_stderr
from unittest.mock import patch

from support import test_project


class TextualFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)

    def configure_ace_model_for_review(self, app):
        values = {
            "AGENT_OPT_MODEL": "compatible/glm5.3-flash",
            "AGENT_OPT_MODEL_BASE_URL": "https://model.example/v1",
            "AGENT_OPT_MODEL_ID": "glm5.3-flash",
            "AGENT_OPT_MODEL_API_KEY": "pilot-fixture-key",
        }
        app.model_values.update(values)
        app.model_sources.update({field: "session" for field in values})

    async def test_home_is_first_and_new_optimization_enters_wizard_with_back_navigation(self):
        from agent_optimizer.tui import OptimizerApp

        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                self.assertEqual(app.page, "Home")
                self.assertEqual([row[0] for row in app.rows], [
                    "New Optimization", "Existing Experiment", "Run History",
                    "Advanced Setup", "Quit",
                ])
                await pilot.press("enter")
                self.assertEqual(app.page, "Agent")
                await pilot.press("enter")
                self.assertEqual(app.page, "Harness")
                await pilot.press("escape")
                self.assertEqual(app.page, "Agent")
                self.assertEqual(app.selections["Agent"], "ace-rtl")

    async def test_unavailable_selection_detail_explains_reason_and_alternative(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter")
                index = next(i for i, row in enumerate(app.rows) if not row[2])
                await pilot.press(*(["down"] * index))
                detail = str(app.query_one("#details", Static).render())
                self.assertIn("Why unavailable", detail)
                self.assertIn("Try instead", detail)

    async def test_dataset_leads_to_model_setup_with_shared_default_and_source_labels(self):
        from agent_optimizer.tui import OptimizerApp

        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en", "AGENT_OPT_MODEL": "",
                                     "AGENT_OPT_MODEL_BASE_URL": "",
                                     "AGENT_OPT_MODEL_API_KEY": "", "AGENT_OPT_MODEL_ID": ""}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter", "enter", "enter", "enter", "enter")
                self.assertEqual(app.page, "Model")
                rows = "\n".join(f"{row[0]} {row[1]}" for row in app.rows)
                self.assertIn("glm5.3-flash", rows)
                self.assertIn("default", rows.lower())
                self.assertIn("API Endpoint", rows)

    async def test_model_custom_value_survives_back_and_review_never_shows_environment_key(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input, Static

        secret = "session-model-secret-912"
        endpoint = "https://model.example/v1"
        environment = {"AGENT_OPT_LANG": "en", "AGENT_OPT_MODEL": "compatible/glm5.3-flash",
                       "AGENT_OPT_MODEL_BASE_URL": "https://env.example/v1",
                       "AGENT_OPT_MODEL_ID": "glm5.3-flash",
                       "AGENT_OPT_MODEL_API_KEY": secret}
        with patch.dict(os.environ, environment):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter", "enter", "enter", "enter", "enter")
                self.assertEqual(app.page, "Model")
                endpoint_index = app.model_fields.index("AGENT_OPT_MODEL_BASE_URL")
                await pilot.press(*(["down"] * endpoint_index), "enter")
                self.assertIn("Custom", "\n".join(row[0] for row in app.rows))
                await pilot.press("down", "enter")
                entry = app.query_one(Input)
                self.assertFalse(entry.password)
                entry.value = endpoint
                await pilot.press("enter")
                self.assertEqual(app.model_values["AGENT_OPT_MODEL_BASE_URL"], endpoint)
                self.assertIn("session", str(app.query_one("#details", Static).render()).lower())
                self.assertNotIn(secret, app._review())
                await pilot.press("end", "enter")
                self.assertEqual(app.page, "Review")
                review = str(app.query_one("#review", Static).render())
                self.assertIn("Selection", review)
                self.assertIn("Model", review)
                self.assertIn("Budget", review)
                self.assertIn("Preparation", review)
                self.assertIn("Output", review)
                self.assertIn("configured", review.lower())
                self.assertNotIn(secret, review)
                await pilot.press("escape")
                self.assertEqual(app.page, "Model")
                self.assertIn(endpoint, "\n".join(row[0] for row in app.rows))
                await pilot.press("end", "enter", "enter")
                self.assertEqual(app.page, "Model")
                self.assertIn(endpoint, "\n".join(row[0] for row in app.rows))

    async def test_model_selector_offers_current_environment_before_custom(self):
        from agent_optimizer.tui import OptimizerApp

        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en", "AGENT_OPT_MODEL": "compatible/current-model",
                                     "AGENT_OPT_MODEL_BASE_URL": "https://model.example/v1",
                                     "AGENT_OPT_MODEL_API_KEY": "fixture-key",
                                     "AGENT_OPT_MODEL_ID": "current-model"}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter", "enter", "enter", "enter", "enter", "enter")
                self.assertIn("Current environment · compatible/current-model",
                              "\n".join(row[0] for row in app.rows))
                self.assertIn("Custom", "\n".join(row[0] for row in app.rows))

    async def test_tui_does_not_auto_load_dotenv_file(self):
        from agent_optimizer.tui import OptimizerApp

        endpoint = "https://dotenv-only.example/v1"
        (self.root / ".env").write_text(
            f"AGENT_OPT_MODEL_BASE_URL={endpoint}\nAGENT_OPT_MODEL_API_KEY=dotenv-secret\n")
        environment = {"AGENT_OPT_MODEL": "", "AGENT_OPT_MODEL_BASE_URL": "",
                       "AGENT_OPT_MODEL_API_KEY": "", "AGENT_OPT_MODEL_ID": ""}
        with patch.dict(os.environ, environment):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter", "enter", "enter", "enter", "enter")
                rows = "\n".join(f"{row[0]} {row[1]}" for row in app.rows)
                self.assertNotIn(endpoint, rows)
                self.assertNotIn("dotenv-secret", rows)

    async def test_preparing_progress_is_visible_then_doctor_waits_for_explicit_run(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        entered, release = threading.Event(), threading.Event()
        secret = "preparation-key-secret-914"
        ready_report = {"scope": "plan", "ready": True, "checks": [
            {"id": "plan.schema", "area": "plan", "status": "ok",
             "message": "Experiment schema is valid", "remedy": ""},
            {"id": "runtime.binary", "area": "runtime", "status": "ok",
             "message": "Runtime binaries are available", "remedy": ""},
        ]}
        experiment = self.root / "examples/minimal/experiment.toml"

        def prepare(_root, _agent, _optimizer, *, progress_stream=None):
            progress_stream.write(f"Preparing sample_text: downloading fixture token={secret}\n")
            entered.set()
            release.wait(timeout=5)
            return experiment

        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en", "DATASET_API_KEY": secret}), \
                patch("agent_optimizer.preset_tui.write_sample_selection", side_effect=prepare), \
                patch("agent_optimizer.readiness.collect_plan", return_value=ready_report) as doctor, \
                patch("agent_optimizer.runner.run_experiment") as run:
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter")
                agent_index = next(i for i, row in enumerate(app.rows) if row[0] == "rtl-solo")
                await pilot.press(*(["down"] * agent_index), "enter", "enter", "enter", "enter", "enter")
                self.assertEqual(app.page, "Review")
                await pilot.press("down", "enter")
                self.assertEqual(app.page, "Preparing")
                for _ in range(100):
                    if entered.is_set():
                        break
                    await asyncio.sleep(0.01)
                await pilot.pause()
                details = str(app.query_one("#details", Static).render())
                self.assertIn("Preparing sample_text", details)
                self.assertNotIn(secret, details)
                release.set()
                for _ in range(100):
                    if app.page == "Preparing" and not app.busy:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(app.page, "Preparing")
                hint = str(app.query_one("#hint", Static).render())
                self.assertNotIn("진행 중", hint)
                self.assertIn("Enter", hint)
                continue_index = next(i for i, row in enumerate(app.rows)
                                      if "Continue to Doctor" in row[0])
                await pilot.press(*(["down"] * continue_index), "enter")
                for _ in range(100):
                    if app.page == "Doctor" and not app.busy:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(app.page, "Doctor")
                doctor_hint = str(app.query_one("#hint", Static).render())
                self.assertNotIn("진행 중", doctor_hint)
                text = str(app.query_one("#details", Static).render())
                self.assertIn("2 / 2", text)
                self.assertIn("plan.schema", text)
                self.assertTrue(any("Run Optimization" in row[0] for row in app.rows))
                self.assertFalse(run.called)
                self.assertFalse(doctor.call_args.kwargs["model"])

    async def test_doctor_probe_failure_shows_remedy_retry_and_blocks_optimizer(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input, Static

        plan = self.root / "examples/minimal/experiment.toml"
        plan.write_text(plan.read_text().replace('optimizer = "file_variants"', 'optimizer = "gepa"'))
        failed = {"scope": "plan", "ready": False, "checks": [
            {"id": "model.probe", "area": "model", "status": "error",
             "message": "Model connectivity probe failed", "remedy": "Verify endpoint and key"},
            {"id": "agent.source", "area": "agent", "status": "blocked",
             "message": "Requires components.files", "remedy": "Resolve components.files first"},
        ]}
        ready = {"scope": "plan", "ready": True, "checks": [
            {"id": "model.probe", "area": "model", "status": "ok",
             "message": "Model connectivity probe passed", "remedy": ""},
        ]}
        environment = {"AGENT_OPT_LANG": "en",
                       "AGENT_OPT_MODEL_BASE_URL": "https://model.example/v1",
                       "AGENT_OPT_MODEL_ID": "glm5.3-flash", "AGENT_OPT_MODEL_API_KEY": "fixture-key"}
        with patch.dict(os.environ, environment), \
                patch("agent_optimizer.readiness.collect_plan", side_effect=[failed, ready]) as doctor, \
                patch("agent_optimizer.runner.run_experiment") as run:
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("down", "enter")
                app.query_one(Input).value = "examples/minimal/experiment.toml"
                await pilot.press("enter", "down", "enter")
                for _ in range(100):
                    if app.page == "Preparing" and not app.busy:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(app.page, "Preparing")
                await pilot.press("enter")
                for _ in range(100):
                    if app.page == "Doctor" and not app.busy:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(app.page, "Doctor")
                text = str(app.query_one("#details", Static).render())
                self.assertIn("model.probe", text)
                self.assertIn("Verify endpoint and key", text)
                self.assertTrue(any("○" in row[0] for row in app.rows))
                retry = next(i for i, row in enumerate(app.rows) if "Retry" in row[0])
                await pilot.press(*(["down"] * retry), "enter")
                for _ in range(100):
                    if app.page == "Doctor" and not app.busy and doctor.call_count == 2:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(doctor.call_count, 2)
                self.assertTrue(all(call.kwargs["model"] for call in doctor.call_args_list))
                self.assertTrue(any("Run Optimization" in row[0] for row in app.rows))
                self.assertFalse(run.called)

    async def test_narrow_doctor_can_scroll_check_list_and_show_selected_remedy(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input, OptionList, Static

        report = {"scope": "plan", "ready": False, "checks": [
            {"id": f"check.{index}", "area": "runtime", "status": "blocked",
             "message": f"Check {index} is blocked", "remedy": f"Remedy {index}"}
            for index in range(20)
        ]}
        with patch("agent_optimizer.readiness.collect_plan", return_value=report):
            app = OptimizerApp(self.root)
            async with app.run_test(size=(50, 20)) as pilot:
                await pilot.press("down", "enter")
                app.query_one(Input).value = "examples/minimal/experiment.toml"
                await pilot.press("enter", "down", "enter")
                for _ in range(100):
                    if app.page == "Preparing" and not app.busy:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(app.page, "Preparing")
                await pilot.press("enter")
                for _ in range(100):
                    if app.page == "Doctor" and not app.busy:
                        break
                    await asyncio.sleep(0.01)
                options = app.query_one("#options", OptionList)
                self.assertTrue(options.has_focus)
                await pilot.press(*(["down"] * 19))
                self.assertGreater(options.scroll_y, 0)
                self.assertIn("Remedy 19", str(app.query_one("#details", Static).render()))

    async def test_workspace_escape_returns_to_dataset_after_model_setup(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input

        with patch.dict(os.environ, {"AGENT_OPT_MODEL": "", "AGENT_OPT_MODEL_BASE_URL": "",
                                     "AGENT_OPT_MODEL_API_KEY": "", "AGENT_OPT_MODEL_ID": ""}), \
                patch("agent_optimizer.tui.is_source_checkout", return_value=False):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter", "enter", "enter", "enter", "enter")
                self.assertEqual(app.page, "Workspace")
                app.query_one(Input).value = "chosen workspace"
                await pilot.press("enter")
                self.assertEqual(app.page, "Model")
                await pilot.press("escape")
                self.assertEqual(app.page, "Workspace")
                await pilot.press("escape")
                self.assertEqual(app.page, "Dataset")

    async def test_running_dashboard_accumulates_events_and_shows_budget_activity_and_elapsed(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import RichLog, Static

        app = OptimizerApp(self.root)
        async with app.run_test(size=(50, 20)) as pilot:
            app._show("Running")
            self.assertTrue(app.query("#event-log").nodes)
            self.assertIsNotNone(getattr(app, "progress_state", None))
            app.progress_state.configure_budget(9)
            app.run_started_at = time.monotonic() - 125
            events = [
                {"event": "optimizer_iteration_started", "timestamp": "2026-09-29T10:00:00Z",
                 "stage_id": "gepa", "iteration": 2, "total": 3},
                {"event": "trial_started", "timestamp": "2026-09-29T10:00:01Z",
                 "stage_id": "gepa", "task_id": "prob_001", "phase": "agent"},
                {"event": "trial_completed", "timestamp": "2026-09-29T10:00:16Z",
                 "stage_id": "gepa", "task_id": "prob_001", "status": "passed",
                 "metrics": {"passed": 1.0, "task_wall_time_seconds": 15.0}},
            ]
            with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}):
                for event in events:
                    app._handle_run_event(event)
                app._refresh_run_state()
            await pilot.pause()
            state = str(app.query_one("#run-state", Static).render())
            log = app.query_one("#event-log", RichLog)
            self.assertIn("gepa", state)
            self.assertIn("prob_001", state)
            self.assertIn("2/3", state)
            self.assertIn("1/9", state)
            self.assertIn("02:05", state)
            self.assertNotIn("ETA", state)
            self.assertNotIn("planned", state.lower())
            self.assertIn("completed", state.lower())
            self.assertGreaterEqual(len(log.lines), 3)
            self.assertLessEqual(log.max_lines, 300)
            log_text = "".join(line.text for line in log.lines)
            self.assertIn("trial started", log_text)
            self.assertIn("trial completed", log_text)
            app.busy = True
            await pilot.press("escape", "q")
            self.assertTrue(app.is_running)

    async def test_running_log_caps_lines_and_preserves_manual_scroll_on_narrow_screen(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import RichLog

        app = OptimizerApp(self.root)
        async with app.run_test(size=(50, 20)) as pilot:
            app._show("Running")
            for index in range(350):
                app._handle_run_event({"event": "candidate_created",
                                       "timestamp": "2026-09-29T10:00:00Z",
                                       "stage_id": "gepa", "task_id": f"task-{index:03}"})
            await pilot.pause()
            log = app.query_one("#event-log", RichLog)
            self.assertLessEqual(len(log.lines), 300)
            self.assertTrue(log.has_focus)
            self.assertTrue(log.is_vertical_scroll_end)
            await pilot.press("pageup")
            self.assertFalse(log.is_vertical_scroll_end)
            scroll_y = log.scroll_y
            app._handle_run_event({"event": "candidate_created", "stage_id": "gepa",
                                   "task_id": "latest-task"})
            await pilot.pause()
            self.assertEqual(log.scroll_y, scroll_y)

    async def test_result_report_and_artifacts_scroll_on_narrow_screen(self):
        from agent_optimizer.tui import OptimizerApp

        app = OptimizerApp(self.root)
        async with app.run_test(size=(50, 20)) as pilot:
            app._finish({"status": "failed", "reason": "fixture failure", "stage": "gepa",
                         "trials_used": 4, "max_trials": 9,
                         "run_dir": self.root / "runs/diagnostic",
                         "artifacts": [self.root / f"runs/diagnostic/{name}"
                                       for name in ("summary.json", "events.jsonl", "report.md")]})
            self.assertEqual(app.page, "Result")
            panel = app.query_one("#review-panel")
            self.assertTrue(panel.can_focus)
            await pilot.press("tab", "pagedown")
            self.assertGreater(panel.scroll_y, 0)

    async def test_failed_result_shows_stage_reason_artifacts_and_redacts_secret(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input, RichLog, Static

        secret = "failure-api-secret-915"
        artifacts = self.root / "runs" / "diagnostic-run"
        artifacts.mkdir(parents=True)
        for name in ("summary.json", "events.jsonl", "report.md"):
            (artifacts / name).write_text("diagnostic")
        failure_report = {"scope": "plan", "ready": True, "checks": [
            {"id": "plan.schema", "area": "plan", "status": "ok",
             "message": "Experiment schema is valid", "remedy": ""},
        ]}

        def fail_run(_spec, _registry, *, on_event):
            on_event({"event": "stage_started", "stage_id": "gepa", "timestamp": "2026-09-29T10:00:00Z"})
            on_event({"event": "error", "stage_id": "gepa", "detail": secret})
            error = RuntimeError(f"Connection timeout: {secret}")
            error.run_root = str(artifacts)
            error.failure_diagnostic = {"stage_id": "gepa", "detail": secret}
            raise error

        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en", "AGENT_FAILURE_API_KEY": secret}), \
                patch("agent_optimizer.readiness.collect_plan", return_value=failure_report), \
                patch("agent_optimizer.runner.run_experiment", side_effect=fail_run):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("down", "enter")
                app.query_one(Input).value = "examples/minimal/experiment.toml"
                await pilot.press("enter", "down", "enter")
                for _ in range(100):
                    if app.page == "Preparing" and not app.busy:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(app.page, "Preparing")
                await pilot.press("enter")
                for _ in range(100):
                    if app.page == "Doctor" and not app.busy:
                        break
                    await asyncio.sleep(0.01)
                run_index = len(app.doctor_report["checks"])
                await pilot.press(*(["down"] * run_index), "enter")
                for _ in range(100):
                    if app.page == "Result" and not app.busy:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(app.page, "Result")
                result = str(app.query_one("#review", Static).render())
                self.assertIn("failed", result.lower())
                self.assertIn("gepa", result)
                self.assertIn(str(artifacts), result)
                self.assertIn("summary.json", result)
                self.assertIn("events.jsonl", result)
                self.assertIn("report.md", result)
                self.assertNotIn(secret, result)
                log = app.query_one("#event-log", RichLog)
                event_text = "".join(line.text for line in log.lines)
                self.assertIn("error", event_text.lower())
                self.assertNotIn(secret, event_text)

    async def test_preparation_failure_is_visible_and_retry_does_not_skip_doctor(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        experiment = self.root / "examples/minimal/experiment.toml"
        ready_report = {"scope": "plan", "ready": True, "checks": [
            {"id": "plan.schema", "area": "plan", "status": "ok",
             "message": "Experiment schema is valid", "remedy": ""},
        ]}
        attempts = []

        def prepare(_root, _agent, _optimizer, *, progress_stream=None):
            attempts.append(True)
            if len(attempts) == 1:
                progress_stream.write("Build evaluation image failed\n")
                raise RuntimeError("fixture asset failure")
            progress_stream.write("CVDP assets complete\n")
            return experiment

        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}), \
                patch("agent_optimizer.preset_tui.write_sample_selection", side_effect=prepare), \
                patch("agent_optimizer.readiness.collect_plan", return_value=ready_report) as doctor, \
                patch("agent_optimizer.runner.run_experiment") as run:
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter")
                agent_index = next(i for i, row in enumerate(app.rows) if row[0] == "rtl-solo")
                await pilot.press(*(["down"] * agent_index), "enter", "enter", "enter", "enter", "enter")
                self.assertEqual(app.page, "Review")
                await pilot.press("down", "enter")
                for _ in range(100):
                    if not app.busy:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(app.page, "Preparing")
                failure = str(app.query_one("#details", Static).render())
                self.assertIn("Build evaluation image failed", failure)
                self.assertIn("fixture asset failure", failure)
                self.assertFalse(doctor.called)
                retry = next(i for i, row in enumerate(app.rows) if "Retry preparation" in row[0])
                await pilot.press(*(["down"] * retry), "enter")
                for _ in range(100):
                    if app.page == "Preparing" and not app.busy:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(len(attempts), 2)
                self.assertEqual(app.page, "Preparing")
                await pilot.press("enter")
                for _ in range(100):
                    if app.page == "Doctor" and not app.busy:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(doctor.call_count, 1)
                self.assertEqual(app.page, "Doctor")
                self.assertFalse(run.called)

    async def test_api_key_is_masked_and_password_mode_resets_for_existing_path(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input

        secret = "masked-model-secret-913"
        with patch.dict(os.environ, {"AGENT_OPT_MODEL": "", "AGENT_OPT_MODEL_BASE_URL": "",
                                     "AGENT_OPT_MODEL_API_KEY": "", "AGENT_OPT_MODEL_ID": ""}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter", "enter", "enter", "enter", "enter")
                self.assertEqual(app.page, "Model")
                key_index = app.model_fields.index("AGENT_OPT_MODEL_API_KEY")
                await pilot.press(*(["down"] * key_index), "enter")
                entry = app.query_one(Input)
                self.assertTrue(entry.password)
                entry.value = secret
                self.assertNotIn(secret, str(entry.render()))
                await pilot.press("enter")
                self.assertEqual(app.model_values["AGENT_OPT_MODEL_API_KEY"], secret)
                self.assertFalse(app.query_one(Input).password)
                self.assertEqual(app.query_one(Input).value, "")
                self.assertNotIn(secret, app._review())
                await pilot.press("escape", "escape", "escape", "escape", "escape")
                self.assertEqual(app.page, "Home")
                await pilot.press("down", "enter")
                self.assertEqual(app.page, "Existing")
                self.assertFalse(app.query_one(Input).password)
                self.assertEqual(app.model_values["AGENT_OPT_MODEL_API_KEY"], secret)

    async def test_cli_rejects_piped_output_even_with_tty_input_and_error(self):
        from agent_optimizer.cli import main

        errors = io.StringIO()
        with redirect_stderr(errors), patch("sys.stdin.isatty", return_value=True), \
             patch("sys.stdout.isatty", return_value=False), \
             patch("sys.stderr.isatty", return_value=True):
            self.assertEqual(main(["tui", "--project-root", str(self.root)]), 2)
        self.assertIn("TTY", errors.getvalue())

    async def test_highlight_disabled_and_back_preserve_selection(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import OptionList, Static

        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            self.assertEqual(app.page, "Home")
            await pilot.press("enter")
            self.assertEqual(app.page, "Agent")
            await pilot.press("down")
            self.assertIn("선택할 수 없는 이유", str(app.query_one("#details", Static).render()))
            await pilot.press("up", "enter")
            self.assertEqual(app.page, "Harness")
            await pilot.press("down")
            self.assertIn("선택할 수 없는 이유", str(app.query_one("#details", Static).render()))
            await pilot.press("enter")
            self.assertEqual(app.page, "Harness")
            await pilot.press("up", "enter", "down", "enter", "enter")
            self.configure_ace_model_for_review(app)
            await pilot.press("end", "enter")
            self.assertEqual(app.page, "Review")
            await pilot.press("escape")
            self.assertEqual(app.page, "Model")
            await pilot.press("escape")
            self.assertEqual(app.page, "Dataset")
            await pilot.press("escape", "escape", "escape")
            self.assertEqual(app.page, "Agent")
            self.assertEqual(app.query_one(OptionList).highlighted, 0)
            await pilot.press("q")

    async def test_switching_agent_revalidates_dependent_choices(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import OptionList, Static

        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("enter", "enter", "enter", "down", "enter", "enter")
            self.configure_ace_model_for_review(app)
            await pilot.press("end", "enter")
            self.assertEqual(app.page, "Review")
            await pilot.press("escape", "escape", "escape", "escape", "escape")
            index = next(i for i, row in enumerate(app.rows) if row[0] == "rtl-solo")
            await pilot.press(*(["down"] * index), "enter")
            self.assertEqual(app.page, "Harness")
            self.assertEqual(app.selections["Agent"], "rtl-solo")
            self.assertEqual(app.rows[0][0], "Fixture")
            self.assertIn("Fixture", str(app.query_one("#details", Static).render()))
            self.assertNotIn("Optimizer", app.selections)
            await pilot.press("enter", "enter", "enter", "enter")
            self.assertEqual(app.page, "Review")
            self.assertIn("sample_text", str(app.query_one("#review", Static).render()))

    async def test_existing_config_and_history_are_read_only_until_run(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input, Static

        name = "20260927T120000Z-abcdef12"
        run = self.root / "runs" / name
        run.mkdir(parents=True)
        (run / "summary.json").write_text(json.dumps({"schema_version": 1, "run_id": name,
                                                         "status": "completed", "groups": [],
                                                         "trials_used": 2}))
        (run / "report.html").write_text("report")
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("down", "down", "enter")
            self.assertEqual(app.page, "History")
            self.assertIn(name, str(app.query_one("#details", Static).render()))
            await pilot.press("escape", "up", "enter")
            self.assertEqual(app.page, "Existing")
            app.query_one(Input).value = "examples/minimal/experiment.toml"
            await pilot.press("enter")
            self.assertEqual(app.page, "Review")
            self.assertFalse((self.root / "runs" / "configs").exists())

    async def test_english_home_and_quit(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                self.assertIn("New Optimization", str(app.query_one("#details", Static).render()))
                await pilot.press("q")

    async def test_fixture_runs_in_worker_and_displays_report(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            index = next(i for i, row in enumerate(app.rows) if row[0] == "rtl-solo")
            await pilot.press(*(["down"] * index), "enter", "enter", "enter", "enter")
            await pilot.press("end", "enter")
            self.assertEqual(app.page, "Review")
            await pilot.press("down", "enter")
            for _ in range(150):
                if app.page == "Preparing" and not app.busy:
                    break
                await asyncio.sleep(0.1)
            self.assertEqual(app.page, "Preparing")
            await pilot.press("enter")
            for _ in range(150):
                if app.page == "Doctor" and not app.busy:
                    break
                await asyncio.sleep(0.1)
            self.assertEqual(app.page, "Doctor")
            self.assertIsNotNone(app.doctor_report, app.doctor_error)
            run_index = len(app.doctor_report["checks"])
            await pilot.press(*(["down"] * run_index), "enter")
            for _ in range(150):
                if not app.busy:
                    break
                await asyncio.sleep(0.1)
            self.assertFalse(app.busy)
            self.assertEqual(app.page, "Result")
            text = str(app.query_one("#review", Static).render())
            self.assertIn("report.html", text)
            self.assertIn("완료", text)
            self.assertIn("사용한 trial", text)
            self.assertIn("최대 budget", text)
            self.assertTrue(list((self.root / "runs").glob("*/report.html")))

    async def test_model_setup_back_never_prepares_assets(self):
        from agent_optimizer.tui import OptimizerApp

        with patch.dict(os.environ, {"AGENT_OPT_MODEL": "", "AGENT_OPT_MODEL_BASE_URL": "",
                                     "AGENT_OPT_MODEL_API_KEY": "", "AGENT_OPT_MODEL_ID": ""}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter", "enter", "enter", "enter", "enter")
                self.assertEqual(app.page, "Model")
                await pilot.press("escape")
                self.assertEqual(app.page, "Dataset")
                self.assertFalse((self.root / "runs").exists())

    async def test_history_rejects_replaced_report(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        name = "20260927T120000Z-abcdef12"
        run = self.root / "runs" / name
        run.mkdir(parents=True)
        (run / "summary.json").write_text(json.dumps({"schema_version": 1, "run_id": name,
                                                         "status": "completed", "groups": [],
                                                         "trials_used": 3}))
        report = run / "report.html"
        report.write_text("report")
        outside = self.root / "private.html"
        outside.write_text("private")
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("down", "down", "enter")
            self.assertIn("3", str(app.query_one("#details", Static).render()))
            report.unlink()
            report.symlink_to(outside)
            await pilot.press("enter")
            self.assertIn("안전하게", str(app.query_one("#details", Static).render()))
            self.assertNotIn("private", str(app.query_one("#details", Static).render()))

    async def test_existing_experiment_requires_review_then_runs_directly(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input, Static

        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("escape", "down", "enter")
            app.query_one(Input).value = "examples/minimal/experiment.toml"
            await pilot.press("enter")
            self.assertEqual(app.page, "Review")
            self.assertFalse((self.root / "runs").exists())
            await pilot.press("down", "enter")
            for _ in range(150):
                if app.page == "Preparing" and not app.busy:
                    break
                await asyncio.sleep(0.1)
            self.assertEqual(app.page, "Preparing")
            await pilot.press("enter")
            for _ in range(150):
                if app.page == "Doctor" and not app.busy:
                    break
                await asyncio.sleep(0.1)
            self.assertEqual(app.page, "Doctor")
            run_index = len(app.doctor_report["checks"])
            await pilot.press(*(["down"] * run_index), "enter")
            for _ in range(150):
                if not app.busy:
                    break
                await asyncio.sleep(0.1)
            self.assertEqual(app.page, "Result")
            self.assertFalse(app.busy)
            self.assertIn("report.html", str(app.query_one("#review", Static).render()))
            self.assertTrue(list((self.root / "runs").glob("*/report.html")))

    async def test_unready_existing_experiment_shows_diagnostic_without_running(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input, Static

        plan = self.root / "examples/minimal/experiment.toml"
        plan.write_text(plan.read_text().replace("max_trials = 40", "max_trials = 1"))
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("escape", "down", "enter")
            app.query_one(Input).value = "examples/minimal/experiment.toml"
            await pilot.press("enter")
            self.assertEqual(app.page, "Review")
            await pilot.press("down")
            await pilot.press("enter")
            for _ in range(80):
                if app.page == "Preparing" and not app.busy:
                    break
                await asyncio.sleep(0.1)
            self.assertEqual(app.page, "Preparing")
            await pilot.press("enter")
            for _ in range(80):
                if app.page == "Doctor" and not app.busy:
                    break
                await asyncio.sleep(0.1)
            self.assertEqual(app.page, "Doctor")
            budget_index = next(i for i, row in enumerate(app.rows) if "budget.trials" in row[0])
            await pilot.press(*(["down"] * budget_index))
            text = str(app.query_one("#details", Static).render())
            self.assertIn("budget.trials", text)
            self.assertIn("budget.max_trials", text)
            self.assertFalse(list((self.root / "runs").glob("*/report.html")))

    async def test_recent_history_filters_symlinks_invalid_and_limits_to_ten(self):
        from agent_optimizer.tui import OptimizerApp

        runs = self.root / "runs"
        for number in range(12):
            name = f"20260927T{number:02}0000Z-{number:08x}"
            directory = runs / ("dev-live" if number % 2 else "") / name
            directory.mkdir(parents=True)
            (directory / "summary.json").write_text(json.dumps({
                "schema_version": 1, "run_id": name, "status": "completed",
                "groups": [], "trials_used": number}))
            (directory / "report.html").write_text("report")
        (runs / "20260927T010000Z-00000001" ).symlink_to(runs / "dev-live" / "20260927T110000Z-0000000b")
        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("escape", "down", "down", "enter")
            self.assertEqual(len(app.history), 10)
            self.assertEqual(app.history[0][0], "20260927T110000Z-0000000b")
            self.assertNotIn("20260927T010000Z-00000001", [item[0] for item in app.history])

    async def test_narrow_terminal_stacks_details_below_options(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        app = OptimizerApp(self.root)
        async with app.run_test(size=(50, 24)) as pilot:
            self.assertTrue(app.has_class("narrow"))
            await pilot.press("enter")
            await pilot.press("down")
            self.assertIn("선택할 수 없는 이유", str(app.query_one("#details", Static).render()))
            options = app.query_one("#options")
            details = app.query_one("#details-panel")
            self.assertGreater(details.region.y, options.region.y)

    async def test_existing_opencode_asks_only_its_declared_model(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Input

        harness = self.root / "examples/minimal/harness.toml"
        harness.write_text('id = "opencode"\nadapter = "opencode"\nmodel_env = "TEAM_MODEL"\n'
                           '[runtime]\nkind = "docker"\nimage = "pinned-agent"\n'
                           'env_passthrough = ["TEAM_MODEL", "AGENT_OPT_MODEL_BASE_URL", '
                           '"AGENT_OPT_MODEL_API_KEY"]\n')
        with patch.dict(os.environ, {"TEAM_MODEL": "", "AGENT_OPT_MODEL_BASE_URL": "",
                                     "AGENT_OPT_MODEL_API_KEY": ""}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("escape", "down", "enter")
                app.query_one(Input).value = "examples/minimal/experiment.toml"
                await pilot.press("enter", "enter")
                self.assertEqual(app.page, "Model")
                self.assertEqual(app.model_fields, ["TEAM_MODEL"])
                await pilot.press("escape")
                self.assertFalse((self.root / "runs").exists())

    async def test_bare_ace_model_requires_compatible_api_before_preparation(self):
        from agent_optimizer.tui import OptimizerApp

        with patch.dict(os.environ, {"AGENT_OPT_MODEL": "fixture-id",
                                     "AGENT_OPT_MODEL_BASE_URL": "", "AGENT_OPT_MODEL_ID": "",
                                     "AGENT_OPT_MODEL_API_KEY": ""}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter", "enter", "enter", "down", "down", "enter", "enter")
                self.assertEqual(app.page, "Model")
                self.assertIn("AGENT_OPT_MODEL_BASE_URL", app.model_fields)
                self.assertFalse((self.root / "runs").exists())

    async def test_narrow_review_can_scroll_to_report_with_keyboard(self):
        from agent_optimizer.tui import OptimizerApp

        app = OptimizerApp(self.root)
        async with app.run_test(size=(50, 20)) as pilot:
            await pilot.press("enter", "enter", "enter", "enter", "enter")
            self.configure_ace_model_for_review(app)
            await pilot.press("end", "enter")
            panel = app.query_one("#review-panel")
            self.assertTrue(panel.can_focus)
            await pilot.press("tab", "pagedown")
            self.assertGreater(panel.scroll_y, 0)

    async def test_custom_route_leads_to_cli_setup_without_claiming_compatibility(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        app = OptimizerApp(self.root)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            await pilot.press("enter")
            index = next(i for i, row in enumerate(app.rows) if "Harness" in row[0] and row[2])
            await pilot.press(*(["down"] * index), "enter")
            self.assertEqual(app.page, "Advanced")
            self.assertIn("agent-opt init", str(app.query_one("#details", Static).render()))
            self.assertFalse((self.root / "runs").exists())

    async def test_english_selection_and_review_are_localized(self):
        from agent_optimizer.tui import OptimizerApp
        from textual.widgets import Static

        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}):
            app = OptimizerApp(self.root)
            async with app.run_test() as pilot:
                await pilot.press("enter")
                self.assertIn("Assets to prepare", str(app.query_one("#details", Static).render()))
                await pilot.press("enter", "enter", "enter", "enter")
                self.configure_ace_model_for_review(app)
                await pilot.press("end", "enter")
                text = str(app.query_one("#review", Static).render())
                self.assertIn("Agent model", text)
                self.assertIn("Report: runs/<run-id>/report.html", text)
