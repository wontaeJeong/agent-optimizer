"""Bounded dataset execution with isolated registries and parent-owned progress."""
from __future__ import annotations

import contextlib
import multiprocessing
import os
import queue as queue_module
import signal
import time
import traceback
from pathlib import Path

from agent_optimizer.config import load_experiment
from agent_optimizer.history import list_history, record_lifecycle
from agent_optimizer.registry import PROJECT_COMPONENTS, PROJECT_DEPENDENCIES, Registry
from agent_optimizer.runner import run_experiment
from agent_optimizer.terminal_report import SessionProgress


class SessionInterrupted(KeyboardInterrupt):
    def __init__(self, entries: list[dict]):
        self.entries = entries


def _project_event(record: dict) -> dict:
    fields = ("event", "timestamp", "dataset", "stage_id", "task_id", "phase",
              "iteration", "total", "status")
    result = {key: record[key] for key in fields if key in record}
    metrics = record.get("metrics")
    if isinstance(metrics, dict) and "task_wall_time_seconds" in metrics:
        result["metrics"] = {"task_wall_time_seconds": metrics["task_wall_time_seconds"]}
    return result


def _report(run_base: Path, session_root: Path) -> str | None:
    rows = list_history(app_home=session_root / '.unused-home', run_bases=(run_base,), limit=2)
    report = rows[0]['report_path'] if len(rows) == 1 else None
    return Path(report).relative_to(session_root.resolve()).as_posix() if report else None


def _run_directory(run_base: Path, session_root: Path) -> str | None:
    rows = list_history(app_home=session_root / '.unused-home', run_bases=(run_base,), limit=2)
    return Path(rows[0]['run_dir']).relative_to(session_root.resolve()).as_posix() if len(rows) == 1 else None


def _stop_worker(process) -> None:
    # Give the runner a chance to stop Agent children and record interruption.
    try:
        os.kill(process.pid, signal.SIGINT)
    except ProcessLookupError:
        pass
    process.join(timeout=5)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join()


def _worker(index: int, item: dict, run_base: Path, messages,
            components: dict, dependencies: dict) -> None:
    run_base.mkdir(parents=True, exist_ok=True)
    run_base = run_base.resolve()
    with (run_base / "logs.txt").open("w", encoding="utf-8") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                PROJECT_COMPONENTS.clear()
                PROJECT_COMPONENTS.update(components)
                PROJECT_DEPENDENCIES.clear()
                PROJECT_DEPENDENCIES.update(dependencies)
                spec = load_experiment(Path(item["experiment"]))
                spec['_session_id'] = run_base.parent.parent.name
                root, result = run_experiment(
                    spec, Registry(), run_base,
                    on_event=lambda record: messages.put(("event", index, _project_event(record))))
                entry = {"dataset": item["dataset"], "status": result["status"],
                         "run_dir": root.relative_to(run_base.parent.parent).as_posix(),
                         "report": (root / "report.html").relative_to(run_base.parent.parent).as_posix(),
                         "trials_used": result["trials_used"]}
            except Exception as exc:
                traceback.print_exc()
                entry = {"dataset": item["dataset"], "status": "error", "error": str(exc),
                         "run_dir": _run_directory(run_base, run_base.parent.parent),
                         "report": _report(run_base, run_base.parent.parent)}
            messages.put(("done", index, entry))


def run_session(experiments: list[dict], session_root: Path, *, jobs: int,
                progress: SessionProgress) -> list[dict]:
    if not isinstance(jobs, int) or jobs < 1:
        raise ValueError("--jobs는 1 이상의 정수여야 합니다")
    session_root = session_root.absolute()
    lifecycle = record_lifecycle(session_root, status='running', kind='session')
    try:
        context = multiprocessing.get_context("spawn")
        messages = context.Queue()
    except BaseException as exc:
        record_lifecycle(session_root, status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'error',
                         kind='session', created_at=lifecycle['created_at'])
        raise
    components = {kind: dict(entries) for kind, entries in PROJECT_COMPONENTS.items()}
    dependencies = {key: list(paths) for key, paths in PROJECT_DEPENDENCIES.items()}
    entries: list[dict | None] = [None] * len(experiments)
    active: dict[int, tuple[multiprocessing.Process, float]] = {}
    dead_since: dict[int, float] = {}
    next_index = 0
    interrupted = False
    failed = False

    def launch():
        nonlocal next_index
        while next_index < len(experiments) and len(active) < jobs:
            index = next_index
            next_index += 1
            process = context.Process(target=_worker,
                                      args=(index, experiments[index],
                                            session_root / "runs" / f"{index + 1:02d}",
                                            messages, components, dependencies))
            try:
                process.start()
            except OSError as exc:
                entries[index] = {"dataset": experiments[index]["dataset"],
                                  "status": "error", "error": str(exc), "report": None}
                progress.finish(index, "error", 0)
                continue
            active[index] = (process, time.monotonic())
            progress.start(index)

    try:
        launch()
        while active:
            try:
                kind, index, value = messages.get(timeout=0.1)
            except queue_module.Empty:
                kind = None
            if kind == "event" and index in active and entries[index] is None:
                progress.event(index, value)
            elif kind == "done" and index in active and entries[index] is None:
                entries[index] = value
                process, started = active.pop(index)
                process.join()
                progress.finish(index, value["status"], time.monotonic() - started)
                launch()
            for index, (process, started) in list(active.items()):
                if process.is_alive() or process.exitcode is None:
                    dead_since.pop(index, None)
                    continue
                if time.monotonic() - dead_since.setdefault(index, time.monotonic()) < 0.5:
                    continue  # Let the Queue feeder deliver the last result first.
                process.join()
                value = {"dataset": experiments[index]["dataset"], "status": "error",
                         "error": f"실행 프로세스 종료 (exit={process.exitcode})",
                         "report": _report(session_root / "runs" / f"{index + 1:02d}", session_root)}
                entries[index] = value
                active.pop(index)
                progress.finish(index, "error", time.monotonic() - started)
                launch()
    except KeyboardInterrupt:
        interrupted = True
        for index, (process, started) in active.items():
            _stop_worker(process)
            entries[index] = {"dataset": experiments[index]["dataset"], "status": "interrupted",
                              "report": _report(session_root / "runs" / f"{index + 1:02d}", session_root)}
            progress.finish(index, "interrupted", time.monotonic() - started)
        for index in range(next_index, len(experiments)):
            entries[index] = {"dataset": experiments[index]["dataset"], "status": "interrupted",
                              "report": None}
            progress.finish(index, "interrupted", 0)
        raise SessionInterrupted(entries) from None
    except BaseException:
        failed = True
        for process, _ in active.values():
            _stop_worker(process)
        raise
    finally:
        messages.close()
        messages.join_thread()
        for index, entry in enumerate(entries):
            if entry is None:
                entry = {'dataset': experiments[index]['dataset'], 'status': 'error', 'report': None}
                entries[index] = entry
            if entry is not None and 'run_dir' not in entry:
                entry['run_dir'] = _run_directory(session_root / 'runs' / f'{index + 1:02d}', session_root)
        statuses = [entry['status'] for entry in entries if entry is not None]
        status = ('interrupted' if interrupted else 'error' if failed else 'completed' if len(statuses) == len(entries)
                  and all(value == 'completed' for value in statuses) else 'error'
                  if not statuses or all(value in {'error', 'source_error'} for value in statuses) else 'partial')
        record_lifecycle(session_root, status=status, kind='session',
                         created_at=lifecycle['created_at'], children=[entry for entry in entries if entry is not None])
    return entries
