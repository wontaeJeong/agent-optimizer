"""Export deterministic Textual screenshots used in the TUI UX verification record."""
from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.tui import OptimizerApp
from support import test_project


def _save(app: OptimizerApp, directory: Path, name: str) -> None:
    app.save_screenshot(filename=name, path=str(directory))
    path = directory / name
    svg = path.read_text(encoding="utf-8")
    path.write_text(
        "\n".join(line.rstrip() for line in svg.splitlines()) + "\n",
        encoding="utf-8",
    )


def _check(identifier: str, area: str, status: str, message: str, remedy: str = "") -> dict:
    return {"id": identifier, "area": area, "status": status, "message": message, "remedy": remedy}


async def capture(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    temporary, root = test_project()
    try:
        with patch.dict(os.environ, {"AGENT_OPT_LANG": "ko"}):
            app = OptimizerApp(root)
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                _save(app, output, "tui-ux-home.svg")
                await pilot.press("enter")
                await pilot.pause()
                _save(app, output, "tui-ux-selection.svg")

            model_env = {
                "AGENT_OPT_MODEL": "compatible/glm5.3-flash",
                "AGENT_OPT_MODEL_BASE_URL": "https://model.example/v1",
                "AGENT_OPT_MODEL_ID": "glm5.3-flash",
                "AGENT_OPT_MODEL_API_KEY": "screenshot-fixture-secret",
            }
            with patch.dict(os.environ, model_env):
                app = OptimizerApp(root)
                async with app.run_test(size=(100, 30)) as pilot:
                    await pilot.press("enter", "enter", "enter", "enter", "enter")
                    await pilot.pause()
                    _save(app, output, "tui-ux-model.svg")
                    app.model_values = dict(model_env)
                    app.model_sources = {field: "environment" for field in model_env}
                    app._show("Review")
                    await pilot.pause()
                    _save(app, output, "tui-ux-review.svg")

        app = OptimizerApp(root)
        app.preparation_lines = [
            "✓ Pinned Git source ready",
            "✓ CVDP dataset ready",
            "✓ Driver ready",
            "✓ Docker images verified",
        ]
        app.preparation_complete = True
        async with app.run_test(size=(100, 30)) as pilot:
            app._show("Preparing")
            await pilot.pause()
            _save(app, output, "tui-ux-preparing.svg")

        app = OptimizerApp(root)
        app.experiment = root / "examples/minimal/experiment.toml"
        app.doctor_report = {"scope": "plan", "ready": True, "checks": [
            _check("plan.schema", "plan", "ok", "Experiment schema is valid"),
            _check("components.files", "components", "ok",
                   "Registered component files and declared dependencies are available"),
            _check("runtime.binary", "runtime", "ok", "Declared runtime binaries are available"),
            _check("dataset.manifest", "dataset", "ok", "Custom benchmark schema and splits are valid"),
            _check("model.probe", "model", "ok", "Model connectivity probe passed"),
        ]}
        async with app.run_test(size=(100, 30)) as pilot:
            app._show("Doctor")
            await pilot.pause()
            _save(app, output, "tui-ux-doctor.svg")
            app.doctor_report = {"scope": "plan", "ready": False, "checks": [
                _check("plan.schema", "plan", "ok", "Experiment schema is valid"),
                _check("model.probe", "model", "error", "Model connectivity probe failed",
                       "Verify model credentials, endpoint, connectivity, and tool-call support"),
                _check("integration.assets", "integration", "blocked",
                       "Pinned ACE lock or Docker images are unavailable", "Run the selected preparation."),
            ]}
            app._show("Doctor")
            await pilot.pause()
            _save(app, output, "tui-ux-doctor-blocked.svg")

        app = OptimizerApp(root)
        async with app.run_test(size=(100, 30)) as pilot:
            app.run_optimizer = "GEPA"
            app.run_status = "running"
            app.run_started_at = time.monotonic() - 134
            app.progress_state.configure_budget(9)
            app._show("Running")
            for event in (
                {"event": "stage_started", "timestamp": "2026-09-29T10:00:00Z",
                 "stage_id": "gepa"},
                {"event": "optimizer_iteration_started", "timestamp": "2026-09-29T10:00:01Z",
                 "stage_id": "gepa", "iteration": 2, "total": 3},
                {"event": "trial_started", "timestamp": "2026-09-29T10:00:02Z",
                 "stage_id": "gepa", "task_id": "prob_001", "phase": "agent"},
                {"event": "agent_started", "timestamp": "2026-09-29T10:00:03Z",
                 "stage_id": "gepa", "task_id": "prob_001", "phase": "agent"},
                {"event": "evaluation_started", "timestamp": "2026-09-29T10:00:12Z",
                 "stage_id": "gepa", "task_id": "prob_001", "phase": "evaluation"},
                {"event": "trial_completed", "timestamp": "2026-09-29T10:00:18Z",
                 "stage_id": "gepa", "task_id": "prob_001", "status": "passed",
                 "metrics": {"passed": 1.0, "task_wall_time_seconds": 16.2}},
            ):
                app._handle_run_event(event)
            await pilot.pause()
            _save(app, output, "tui-ux-running.svg")
            app._finish({"status": "completed", "trials_used": 7, "max_trials": 9,
                         "run_dir": Path("runs/20260929T100000Z-capture"),
                         "report_html": Path("runs/20260929T100000Z-capture/report.html"),
                         "artifacts": [Path("runs/20260929T100000Z-capture/summary.json"),
                                       Path("runs/20260929T100000Z-capture/events.jsonl"),
                                       Path("runs/20260929T100000Z-capture/report.md")]})
            await pilot.pause()
            _save(app, output, "tui-ux-result.svg")
            app._finish({"status": "failed", "stage": "gepa", "reason": "Connection timeout",
                         "run_dir": Path("runs/20260929T100001Z-failed"),
                         "artifacts": [Path("runs/20260929T100001Z-failed/summary.json"),
                                       Path("runs/20260929T100001Z-failed/events.jsonl")]})
            await pilot.pause()
            _save(app, output, "tui-ux-result-failed.svg")
    finally:
        temporary.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/assets"))
    args = parser.parse_args()
    asyncio.run(capture(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
