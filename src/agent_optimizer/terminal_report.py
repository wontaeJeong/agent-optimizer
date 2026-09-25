"""Live terminal progress from the same versioned events as the HTML report."""
from __future__ import annotations

import sys
import threading
import time
import os

from rich.console import Console
from rich.progress import Progress, ProgressColumn, SpinnerColumn, TimeElapsedColumn
from rich.table import Column
from rich.text import Text


class _StatusColumn(ProgressColumn):
    def render(self, task):
        return Text(task.description, style=task.fields.get("tone", "yellow"))


def _terminal_progress(stream):
    return Progress(SpinnerColumn(), _StatusColumn(table_column=Column(overflow="fold")),
                    TimeElapsedColumn(),
                    console=Console(file=stream, force_terminal=True, color_system="standard",
                                    no_color=bool(os.environ.get("NO_COLOR"))),
                    refresh_per_second=1, transient=False,
                    redirect_stdout=False, redirect_stderr=False)


class ProgressDisplay:
    def __init__(self, stream=None):
        self.stream = sys.stderr if stream is None else stream
        self.tty = self.stream.isatty()
        self.active = None
        self.active_started = None
        self.completed = 0
        self.max_trials = None
        self.slowest = []
        self.lock = threading.Lock()
        self.progress = None
        self.task_id = None
        self._managed = False

    def configure_budget(self, max_trials):
        with self.lock:
            self.max_trials = max_trials
            self.completed = 0
            self.slowest = []

    def _summary(self):
        budget = (f" · MAX TRIAL BUDGET completed={self.completed} "
                  f"remaining={max(0, self.max_trials - self.completed)} / {self.max_trials}"
                  if self.max_trials is not None else f" · completed={self.completed}")
        if self.slowest:
            budget += " · slowest=" + ", ".join(
                f"{task}: {seconds:.2f}s ({dataset})" for seconds, task, dataset in self.slowest[:3])
        return budget

    def start(self):
        if self.tty and self.progress is None:
            self.progress = _terminal_progress(self.stream)
            self.task_id = self.progress.add_task("waiting for events", total=None)
            self.progress.start()
        return self

    def __enter__(self):
        self._managed = True
        return self.start()

    def __exit__(self, *_):
        if self.progress is not None:
            self.progress.stop()
            self.progress = None
        self._managed = False

    def __call__(self, event):
        name = event["event"]
        interesting = {"trial_started", "agent_started", "evaluation_started", "trial_completed",
                       "optimizer_iteration_started", "optimizer_iteration_completed",
                       "optimizer_review_started", "optimizer_merge_started", "optimizer_merge_completed",
                       "stage_budget_exhausted", "budget_exhausted", "error", "interrupted"}
        if name not in interesting:
            return
        task = event.get("task_id", "-")
        stage = event.get("stage_id", "-")
        dataset = event.get("dataset", "-")
        phase = event.get("phase", name.replace("_", " "))
        iteration = event.get("iteration")
        label = f"dataset={dataset} stage={stage} task={task} phase={phase}"
        if iteration is not None:
            total = event.get("total")
            label += f" iteration={iteration}/{total}" if total is not None else f" iteration={iteration}"
        if name == "trial_completed":
            tone = ("green" if event.get("status", "passed") == "passed" else
                    "yellow" if event["status"] == "interrupted" else "red")
        elif name == "optimizer_iteration_completed":
            tone = ("red" if event.get("status") == "invalid_interface" else
                    "yellow" if event.get("accepted") is False or
                    event.get("status") == "no_failures" else "green")
        elif name == "optimizer_merge_completed":
            tone = "green" if event.get("accepted", True) else "yellow"
        else:
            tone = "red" if name == "error" else "yellow"
        with self.lock:
            if name == "trial_completed":
                self.completed += 1
                seconds = event.get("metrics", {}).get("task_wall_time_seconds")
                if seconds is not None:
                    self.slowest = sorted([*self.slowest, (seconds, task, dataset)], reverse=True)[:5]
                self.active, self.active_started = None, None
            else:
                self.active, self.active_started = label, time.monotonic()
            if self.tty:
                if self.progress is None:
                    self.start()
                self.progress.reset(self.task_id)
                self.progress.update(self.task_id, description=(
                    f"[{event['timestamp'][11:19]}] {label}"
                    + (f" elapsed={seconds:.2f}s" if name == "trial_completed"
                       and seconds is not None else "") + self._summary()), tone=tone)
                self.progress.refresh()
                if not self._managed:
                    self.progress.stop()
                    self.progress = None
            else:
                self.stream.write(f"[{event['timestamp'][11:19]}] {label}"
                                  + (f" elapsed={seconds:.2f}s" if name == "trial_completed"
                                     and seconds is not None else "") + self._summary() + "\n")
                self.stream.flush()


class PreparationStatus:
    """Keep an operation and its elapsed time visible during blocking work."""

    def __init__(self, name: str, stream=None, *, action="prepare", subject="dataset"):
        self.name = name
        self.stream = sys.stderr if stream is None else stream
        self.progress = None
        self.label = f"[{action}] {subject}={name}"

    def __enter__(self):
        self.started = time.monotonic()
        if self.stream.isatty():
            self.progress = _terminal_progress(self.stream)
            self.task_id = self.progress.add_task(f"{self.label} starting",
                                                  total=None, tone="yellow")
            self.progress.start()
        else:
            self.stream.write(f"{self.label} starting\n")
            self.stream.flush()
        return self

    def __exit__(self, error_type, *_):
        status = "failed" if error_type else "complete"
        message = (f"{self.label} {status} "
                   f"elapsed={time.monotonic()-self.started:.1f}s")
        if self.progress is not None:
            self.progress.update(self.task_id, description=message,
                                 tone="red" if error_type else "green")
            self.progress.stop()
        else:
            self.stream.write(message + "\n")
            self.stream.flush()
