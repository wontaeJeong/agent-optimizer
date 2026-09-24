"""Live terminal progress from the same versioned events as the HTML report."""
from __future__ import annotations

import sys
import threading
import time

from agent_optimizer.terminal_style import style


class ProgressDisplay:
    def __init__(self, stream=None):
        self.stream = stream or sys.stderr
        self.tty = self.stream.isatty()
        self.active = None
        self.active_started = None
        self.completed = 0
        self.max_trials = None
        self.slowest = []
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.thread = None

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
        if self.tty:
            self.thread = threading.Thread(target=self._refresh, daemon=True)
            self.thread.start()
        return self

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=2)
            self.stream.write("\n")
            self.stream.flush()


    def _refresh(self):
        while not self.stopped.wait(1):
            with self.lock:
                if self.active and self.active_started is not None:
                    label = self.active
                    elapsed = time.monotonic() - self.active_started
                    self.stream.write(f"\r\x1b[2K  {style('◉', 'warning', stream=self.stream)} {label} · {elapsed:.0f}s elapsed"
                                      + self._summary())
                    self.stream.flush()

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
                self.stream.write("\r\x1b[2K")
            tone = ("error" if name == "error" else "warning" if name in {
                "interrupted", "stage_budget_exhausted", "budget_exhausted"} else
                "success" if name in {"trial_completed", "optimizer_iteration_completed",
                                       "optimizer_merge_completed"} else "warning")
            self.stream.write(f"[{event['timestamp'][11:19]}] "
                              + style(label, tone, stream=self.stream)
                              + (f" elapsed={seconds:.2f}s" if name == "trial_completed"
                                 and seconds is not None else "") + self._summary() + "\n")
            self.stream.flush()


class PreparationStatus:
    """Keep the selected dataset and elapsed time visible during blocking setup."""

    def __init__(self, name: str, stream=None):
        self.name = name
        self.stream = stream or sys.stderr
        self.stopped = threading.Event()
        self.thread = None

    def __enter__(self):
        self.started = time.monotonic()
        self.stream.write(f"{style('[prepare]', 'warning', stream=self.stream)} dataset={self.name} starting\n")
        self.stream.flush()
        if self.stream.isatty():
            self.thread = threading.Thread(target=self._refresh, daemon=True)
            self.thread.start()
        return self

    def _refresh(self):
        while not self.stopped.wait(1):
            self.stream.write(f"\r\x1b[2K{style('[prepare]', 'warning', stream=self.stream)} dataset={self.name} "
                              f"elapsed={time.monotonic()-self.started:.0f}s")
            self.stream.flush()

    def __exit__(self, error_type, *_):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=2)
            self.stream.write("\r\x1b[2K")
        status = "failed" if error_type else "complete"
        tone = "error" if error_type else "success"
        self.stream.write(f"[prepare] dataset={self.name} {style(status, tone, stream=self.stream)} "
                          f"elapsed={time.monotonic()-self.started:.1f}s\n")
        self.stream.flush()
