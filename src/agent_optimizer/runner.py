from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import time
import uuid
from dataclasses import replace
from pathlib import Path

from agent_optimizer import __version__
from agent_optimizer.config import validate_objective, validate_stages
from agent_optimizer.contracts import (
    BudgetExceeded, Candidate, ConfigurationError, Evaluation, RunRequest, StageBudgetExceeded,
    UnavailableError, jsonable,
)
from agent_optimizer.objectives import aggregate, select
from agent_optimizer.process import execute
from agent_optimizer.workspace import CandidateStore, collect_outputs, copy_tree, safe_path
from agent_optimizer.results import EventStore, write_json
from agent_optimizer.sources import materialize_agent


class Budget:
    def __init__(self, settings):
        self.limit = settings.get("max_trials", 100)
        self.deadline = time.monotonic() + settings.get("max_wall_time_seconds", 3600)
        self.trial_timeout = settings.get("trial_timeout_seconds", 120)
        self.used = 0
        self.stage_used = {}

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise BudgetExceeded("Experiment wall-time budget exhausted")
        return remaining

    def reserve(self, stage_key=None, stage_limit=None):
        if stage_limit is not None and self.stage_used.get(stage_key, 0) >= stage_limit:
            raise StageBudgetExceeded("Optimizer stage trial allowance exhausted")
        if self.used >= self.limit:
            raise BudgetExceeded("Experiment trial budget exhausted")
        timeout = min(self.remaining(), self.trial_timeout)
        self.used += 1
        if stage_limit is not None:
            self.stage_used[stage_key] = self.stage_used.get(stage_key, 0) + 1
        return timeout


def evaluator_settings(spec):
    runtime = spec.get("evaluation_runtime", {"kind": "local"})
    extra = spec.get("evaluator_config", {})
    if not isinstance(extra, dict) or set(runtime).intersection(extra):
        raise ConfigurationError("evaluator_config must not override evaluation_runtime")
    return {**runtime, **extra}


class Context:
    """Trusted in-process plugin interface, not an OS security boundary."""
    def __init__(self, group, baseline, stage):
        self._group = group
        self._candidate_ids = {baseline.id}
        self._stage_id = stage["id"]
        self._optimizer = stage["optimizer"]

    def propose(self, parent: Candidate, files: dict[str, str], producer: str) -> Candidate:
        self._group.budget.remaining()
        self._group.verify_candidate(parent)
        candidate = self._group.candidates.create(parent, files, producer)
        self._candidate_ids.add(candidate.id)
        return candidate

    def evaluate(self, candidate: Candidate):
        return self._group.evaluate(candidate, "train")

    def train_task_ids(self):
        return [task.id for task in self._group.spec["_tasks"] if task.split == "train"]

    def evaluate_batch(self, candidate: Candidate, task_ids: list[str]):
        if candidate.id not in self._candidate_ids:
            raise ConfigurationError("Cannot evaluate another stage's candidate")
        known = set(self.train_task_ids())
        if (not isinstance(task_ids, list) or not task_ids or len(set(task_ids)) != len(task_ids)
                or not all(type(task_id) is str and task_id in known for task_id in task_ids)):
            raise ConfigurationError("Optimization minibatch must contain distinct train task IDs")
        return self._group.evaluate(candidate, "train", task_ids=task_ids)

    def evaluate_validation(self, candidate: Candidate):
        if candidate.id not in self._candidate_ids:
            raise ConfigurationError("Cannot evaluate another stage's candidate")
        row = self._group.evaluate(candidate, "validation")
        records = [r for r in self._group.records
                   if r["candidate_id"] == candidate.id and r["split"] == "validation"]
        return {"split": "validation", "valid": row["valid"], "metrics": row["metrics"],
                "tasks": [{"task_id": r["task_id"], "metrics": r["metrics"], "valid": r["valid"]}
                          for r in records]}

    def emit(self, event: str, **fields):
        self._group.events.append({"event": event, **fields,
                                   "agent_id": self._group.agent.id,
                                   "harness_id": self._group.profile["id"],
                                   "stage_id": self._stage_id, "optimizer": self._optimizer})

    def history(self):
        return [r for r in self._group.records
                if r["split"] == "train" and r["candidate_id"] in self._candidate_ids]

    def remaining_seconds(self):
        return self._group.budget.remaining()

    def record_usage(self, input_tokens: int | None, output_tokens: int | None, cost_usd: float | None):
        if any(v is not None and (type(v) is not int or v < 0) for v in (input_tokens, output_tokens)):
            raise ConfigurationError("Optimizer token counts must be nonnegative integers or None")
        if cost_usd is not None and (not math.isfinite(cost_usd) or cost_usd < 0):
            raise ConfigurationError("Invalid optimizer cost")
        usage = {"agent_id": self._group.agent.id, "harness_id": self._group.profile["id"],
                 "stage_id": self._stage_id, "optimizer": self._optimizer, "input_tokens": input_tokens,
                 "output_tokens": output_tokens, "cost_usd": cost_usd}
        self._group.events.append({"event": "optimizer_usage", **usage})
        self._group.optimizer_usage.append(usage)


class GroupRunner:
    def __init__(self, experiment, agent, profile, root, registry, budget, events):
        self.spec, self.agent, self.profile, self.root = experiment, agent, profile, root
        self.registry, self.budget, self.events = registry, budget, events
        registry.load_plugins(experiment["_root"], experiment.get("plugins", {}))
        self.harness = registry.resolve("harnesses", profile["adapter"])()
        self.evaluator = registry.resolve("evaluators", experiment["evaluator"])(
            evaluator_settings(experiment))
        self.candidates = CandidateStore(root / "candidates", agent)
        self.records, self.optimizer_usage, self.cache = [], [], {}
        self.current_stage = None
        self.summary = {"agent_id": agent.id, "harness_id": profile["id"], "baseline": None,
                        "stages": [], "selected": [], "final_test": [],
                        "optimizer_usage": self.optimizer_usage, "trial_count": 0, "status": "running"}

    def verify_candidate(self, candidate):
        self.candidates.verify(candidate)

    def trial(self, candidate, task, repeat):
        stage_key = ((self.agent.id, self.profile["id"], self.current_stage["id"])
                     if self.current_stage else None)
        timeout = self.budget.reserve(stage_key, self.current_stage.get("max_trials")
                                      if self.current_stage else None)
        started = time.monotonic()
        trial_deadline = min(started + timeout, self.budget.deadline)
        globally_limited = timeout < self.budget.trial_timeout
        trial_id = f"{candidate.id}-{task.id}-{repeat}-{len(self.records):04d}"
        identity = {"agent_id": self.agent.id, "harness_id": self.profile["id"],
                    "candidate_id": candidate.id, "task_id": task.id, "split": task.split,
                    "stage_id": self.current_stage["id"] if self.current_stage else "baseline",
                    "dataset": self.spec["_benchmark_metadata"].get("name", self.spec["name"]),
                    "repeat": repeat, "trial_id": trial_id}
        self.events.append({"event": "trial_started", "phase": "workspace", **identity})
        trial = self.root / "trials" / trial_id
        workspace = trial / "agent_workspace"
        agent_dir, task_dir = workspace / "agent", workspace / "task"
        seed = self.spec.get("seed", 0) + repeat
        execution = None
        error = {}
        evaluation = Evaluation("error", {"passed": None})
        try:
            copy_tree(candidate.path, agent_dir)
            task_dir.mkdir(parents=True)
            for filename, content in task.files.items():
                target = safe_path(task_dir, filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            overlay = agent_dir / "overlays" / self.profile["adapter"]
            if overlay.is_dir():
                copy_tree(overlay, workspace)
            # Only public task data is delivered; evaluation files stay outside the mounted workspace.
            prompt = safe_path(agent_dir, self.agent.prompt_file).read_text(encoding="utf-8")
            prompt += "\n\n" + task.prompt + "\nTask files are in ./task. Modify only task outputs."
            self.budget.remaining()
            self.events.append({"event": "agent_started", "phase": "agent", **identity})
            if self.agent.build:
                build = execute(list(self.agent.build), workspace, trial / "build_logs",
                                max(0.001, trial_deadline-time.monotonic()), self.profile.get("runtime", {}))
                execution = build
                self.budget.remaining()
                if build.status == "completed" and time.monotonic() < trial_deadline:
                    execution = None
            if execution is None and time.monotonic() < trial_deadline:
                request = RunRequest(workspace, agent_dir, task_dir, prompt, seed,
                                     trial_deadline-time.monotonic(), self.profile, trial / "harness_logs")
                execution = self.harness.run(request)
            self.events.append({"event": "agent_completed", "phase": "agent", **identity})
            self.budget.remaining()
            if execution is not None and execution.status == "timeout" and globally_limited:
                raise BudgetExceeded("Experiment wall-time budget interrupted execution")
            remaining = trial_deadline-time.monotonic()
            if execution is not None and execution.status != "completed":
                invalid = execution.status in {"infrastructure_error", "unsupported"}
                evaluation = Evaluation(execution.status, {"passed": None if invalid else 0.0}, execution.detail)
            elif remaining <= 0:
                evaluation = Evaluation("timeout", {"passed": 0.0}, "Per-trial timeout exhausted")
            else:
                eval_dir = trial / "evaluation_workspace"
                safe_path(trial, task_dir.relative_to(trial).as_posix())
                collect_outputs(task_dir, eval_dir)
                self.budget.remaining()
                remaining = trial_deadline-time.monotonic()
                if remaining <= 0:
                    evaluation = Evaluation("timeout", {"passed": 0.0}, "Per-trial timeout exhausted")
                else:
                    self.events.append({"event": "evaluation_started", "phase": "evaluation", **identity})
                    evaluation = self.evaluator.evaluate(task, eval_dir, remaining)
                    self.events.append({"event": "evaluation_completed", "phase": "evaluation", **identity})
            self.budget.remaining()
            if evaluation.status == "timeout" and globally_limited:
                raise BudgetExceeded("Experiment wall-time budget interrupted evaluation")
            if time.monotonic() >= trial_deadline and evaluation.status == "passed":
                evaluation = Evaluation("timeout", {"passed": 0.0}, "Per-trial timeout exhausted")
        except (Exception, KeyboardInterrupt) as exc:
            status = "interrupted" if isinstance(exc, (BudgetExceeded, KeyboardInterrupt)) else "error"
            evaluation = Evaluation(status, {"passed": None}, str(exc))
            error = {"error_type": type(exc).__name__, "error": str(exc)}
            raise
        finally:
            execution_metrics = execution.metrics if execution is not None else {}
            metrics = {**execution_metrics, **evaluation.metrics,
                       "agent_wall_time_seconds": execution.wall_time_seconds if execution is not None else None,
                       "task_wall_time_seconds": time.monotonic()-started,
                       "agent_tokens": execution_metrics.get("agent_tokens"),
                       "agent_cost_usd": execution_metrics.get("agent_cost_usd")}
            record = {"schema_version": 1, "trial_id": trial_id, "agent_id": self.agent.id,
                      "harness_id": self.profile["id"], "candidate_id": candidate.id,
                      "content_hash": candidate.content_hash, "task_id": task.id, "split": task.split,
                      "repeat": repeat, "seed_requested": seed, "status": evaluation.status,
                      "valid": evaluation.status not in {"infrastructure_error", "unsupported", "interrupted", "error"},
                      "metrics": metrics, "feedback": evaluation.feedback,
                      "execution": jsonable(execution), "artifacts": evaluation.artifacts, **error}
            write_json(trial / "result.json", record)
            self.events.append({"event": "trial_completed", "dataset": identity["dataset"],
                                "stage_id": identity["stage_id"], **record})
            self.records.append(record)
            self.summary["trial_count"] = len(self.records)
        return record

    def evaluate(self, candidate, split, task_ids=None):
        self.verify_candidate(candidate)
        key = (candidate.id, split) if task_ids is None else (candidate.id, split, tuple(sorted(task_ids)))
        if key in self.cache:
            return self.cache[key]
        tasks = [t for t in self.spec["_tasks"] if t.split == split and
                 (task_ids is None or t.id in task_ids)]
        if not tasks:
            raise ConfigurationError(f"No tasks in split {split}")
        records = [self.trial(candidate, task, repeat) for task in tasks
                   for repeat in range(self.spec.get("repetitions", 1))]
        metrics = aggregate(records, self.spec["objective"]["metrics"])
        valid = all(r["valid"] for r in records)
        if not valid:
            metrics = {name: None for name in metrics}
        row = {"candidate_id": candidate.id, "agent_id": self.agent.id,
               "harness_id": self.profile["id"], "split": split,
               "trial_count": len(records), "valid": valid, "metrics": metrics}
        self.cache[key] = row
        return row

    def run(self):
        baseline = self.candidates.create()
        self.summary["baseline"] = self.evaluate(baseline, "validation")
        outputs, by_id, stages = {"baseline": [baseline]}, {baseline.id: baseline}, self.summary["stages"]
        for stage in self.spec.get("stages", []):
            t0 = time.monotonic()
            stage_result = {"id": stage["id"], "optimizer": stage["optimizer"], "status": "running",
                            "selected": [], "evaluated": [], "checkpoint": {}}
            stages.append(stage_result)
            self.budget.remaining()
            self.verify_candidate(baseline)
            context = Context(self, baseline, stage)
            optimizer = self.registry.resolve("optimizers", stage["optimizer"])()
            self.current_stage = stage
            try:
                result = optimizer.optimize(context, [baseline], stage.get("config", {}))
                stage_result["checkpoint"] = result.checkpoint
                self.budget.remaining()
                rows = stage_result["evaluated"]
                for candidate in result.candidates:
                    self.verify_candidate(candidate)
                    by_id[candidate.id] = candidate
                    rows.append(self.evaluate(candidate, "validation"))
                chosen = select(rows, self.spec["objective"])
                outputs[stage["id"]] = [by_id[r["candidate_id"]] for r in chosen]
                stage_result.update(status="completed", selected=chosen)
            except StageBudgetExceeded as exc:
                stage_result.update(status="budget_exhausted", detail=str(exc))
                self.events.append({"event": "stage_budget_exhausted", "stage_id": stage["id"],
                                    "agent_id": self.agent.id, "harness_id": self.profile["id"]})
            finally:
                self.current_stage = None
                stage_result["stage_wall_time_seconds"] = time.monotonic()-t0
                write_json(self.root / "stages" / (stage["id"] + ".json"), stage_result)
        final_names = self.spec.get("final_stages", [stage["id"] for stage in stages
                                                       if stage["id"] in outputs] or ["baseline"])
        final_names = [name for name in final_names if name in outputs]
        pool = {c.id: c for name in final_names for c in outputs[name]}
        winners = select([self.evaluate(c, "validation") for c in pool.values()], self.spec["objective"])
        # Freeze selection before test; test scores never choose a winner or trigger a stage.
        write_json(self.root / "frozen_selection.json", winners)
        self.summary["selected"] = winners
        test_rows = self.summary["final_test"]
        if self.spec.get("final_test", False):
            test_candidates = {baseline.id: baseline, **{r["candidate_id"]: by_id[r["candidate_id"]]
                                                        for r in winners}}
            for candidate in test_candidates.values():
                test_rows.append(self.evaluate(candidate, "test"))
        self.budget.remaining()
        self.summary["status"] = ("partial" if winners and any(s["status"] != "completed" for s in stages)
                                  else "completed" if winners else "no_eligible_candidate")
        return self.summary


def preflight(spec, registry):
    validate_objective(spec["objective"])
    validate_stages(spec)
    stages = spec.get("stages", [])
    if stages and all("max_trials" in stage for stage in stages):
        validation = sum(t.split == "validation" for t in spec["_tasks"])
        tests = sum(t.split == "test" for t in spec["_tasks"])
        per_group = validation + sum(stage["max_trials"] for stage in stages)
        if spec.get("final_test", False):
            per_group += 2 * tests  # Baseline and one frozen winner; they may be the same.
        required = per_group * len(spec["_agents"]) * len(spec["_profiles"])
        if spec.get("budget", {}).get("max_trials", 100) < required:
            raise ConfigurationError(f"Trial budget must reserve at least {required} trials for "
                                     "baseline, stage allowances and final test")
    registry.load_project(spec["_root"])
    registry.selected_files(spec["_root"], spec)
    registry.load_plugins(spec["_root"], spec.get("plugins", {}))
    for profile in spec["_profiles"]:
        registry.resolve("harnesses", profile["adapter"])
    evaluator = registry.resolve("evaluators", spec["evaluator"])(evaluator_settings(spec))
    for stage in spec.get("stages", []):
        registry.resolve("optimizers", stage["optimizer"])
        if stage["optimizer"] in {"gepa", "meta_harness", "ecdysis"}:
            from agent_optimizer.models import ModelSettings
            ModelSettings.from_env()
    if hasattr(evaluator, "validate_benchmark"):
        evaluator.validate_benchmark(spec["_tasks"], spec["_benchmark_metadata"])


def run_experiment(spec, registry, output: Path | None = None, on_event=None):
    preflight(spec, registry)
    base = output or safe_path(spec["_root"], spec.get("output_dir", "runs"))
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    root = base.resolve() / run_id
    root.mkdir(parents=True, exist_ok=False)
    budget = Budget(spec.get("budget", {}))
    events = EventStore(root / "events.jsonl", on_event=on_event)
    summary = {"schema_version": 1, "run_id": run_id, "status": "running",
               "synthetic": spec["_benchmark_metadata"].get("synthetic", False),
               "groups": [], "trials_used": 0,
               "planned_groups": len(spec["_agents"])*len(spec["_profiles"])}
    resolved_agents, source_locks = [], []
    clean = {k: v for k, v in spec.items() if not k.startswith("_")}
    manifest = {"schema_version": 1, "run_id": run_id, "version": __version__,
                "python": platform.python_version(), "platform": platform.platform(),
                "experiment": clean, "resolved_profiles": spec["_profiles"],
                "resolved_models": {h["id"]: os.environ.get(h["model_env"])
                                    for h in spec["_profiles"] if "model_env" in h},
                "benchmark": spec["_benchmark_metadata"],
                "agents": source_locks}
    phase = "manifest"
    group = None
    try:
        manifest["plugin_sha256"] = {
            ref: hashlib.sha256(file.read_bytes()).hexdigest()
            for ref, file in registry.selected_files(spec["_root"], spec).items()}
        manifest["benchmark_sha256"] = hashlib.sha256(
            safe_path(spec["_root"], spec["benchmark"]).read_bytes()).hexdigest()
        write_json(root / "manifest.json", manifest)
        phase = "source"
        for agent in spec["_agents"]:
            remaining = budget.remaining()
            bounded = agent
            if agent.source is not None:
                bounded = replace(agent, source=replace(agent.source, timeout_seconds=min(
                    agent.source.timeout_seconds, remaining)))
            try:
                resolved, lock = materialize_agent(bounded, root / "sources" / agent.id)
            except UnavailableError:
                budget.remaining()
                raise
            resolved_agents.append(resolved)
            source_locks.append({"id": agent.id, **lock, "build": agent.build,
                                 "supported_harnesses": agent.supported_harnesses})
            budget.remaining()
        phase = "groups"
        for agent in resolved_agents:
            for profile in spec["_profiles"]:
                budget.remaining()
                summary["groups"].append({"agent_id": agent.id, "harness_id": profile["id"],
                                          "baseline": None, "stages": [], "selected": [], "final_test": [],
                                          "optimizer_usage": [], "trial_count": 0, "status": "running"})
                group = GroupRunner(spec, agent, profile, root / agent.id / profile["id"],
                                    registry, budget, events)
                summary["groups"][-1] = group.summary
                group.run()
        summary["status"] = ("completed" if all(g["status"] == "completed" for g in summary["groups"])
                             else "partial" if any(g["status"] == "partial" for g in summary["groups"])
                             else "no_eligible_candidate")
    except KeyboardInterrupt:
        summary["status"] = "interrupted"
        events.append({"event": "interrupted"})
    except BudgetExceeded as exc:
        summary["status"] = "budget_exhausted"
        events.append({"event": "budget_exhausted", "detail": str(exc)})
    except Exception as exc:
        summary.update(status="source_error" if phase == "source" else "error",
                       error_type=type(exc).__name__, error=str(exc))
        events.append({"event": summary["status"], "error_type": type(exc).__name__, "detail": str(exc)})
        raise
    finally:
        if group is not None and group.summary["status"] == "running":
            for stage in group.summary["stages"]:
                if stage["status"] == "running":
                    stage["status"] = summary["status"]
                write_json(group.root / "stages" / (stage["id"] + ".json"), stage)
        for current in summary["groups"]:
            if current["status"] == "running":
                current["status"] = summary["status"]
        summary["trials_used"] = budget.used
        write_json(root / "manifest.json", manifest)
        write_json(root / "summary.json", summary)
        from agent_optimizer.results import write_report
        write_report(root, summary)
        from agent_optimizer.html_report import write_html_report
        write_html_report(root, summary)
    return root, summary
