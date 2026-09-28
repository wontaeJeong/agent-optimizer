"""Submit pinned references to the existing private Verilog-Eval evaluator."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, Evaluation, Task
from agent_optimizer.results import write_json
from agent_optimizer.workspace import safe_path


_MODES = {"verilog-spec": "spec-to-rtl", "verilog-completion": "code-complete-iccad2023"}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")


def _public_id(problem_id: str) -> str:
    if not isinstance(problem_id, str) or not _ID.fullmatch(problem_id):
        raise ConfigurationError("Invalid Verilog-Eval problem ID")
    return problem_id


def reference_submission(directory: Path, problem_id: str) -> str:
    """Read one private reference and rename its declaration without changing the source."""
    path = safe_path(Path(directory), _public_id(problem_id) + "_ref.sv")
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ConfigurationError("Verilog-Eval reference is unavailable") from exc
    submission, count = re.subn(r"(?m)^([ \t]*)module[ \t]+RefModule\b",
                                r"\1module TopModule", source)
    if count != 1:
        raise ConfigurationError("Verilog-Eval reference needs exactly one RefModule declaration")
    return submission


def _verdict(result: Evaluation | None) -> tuple[str, float | None, str]:
    if not isinstance(result, Evaluation) or not isinstance(result.metrics, dict):
        return "infrastructure_error", None, "infrastructure_error"
    status = result.status
    passed = result.metrics.get("passed")
    if isinstance(passed, bool) or passed not in (0, 0.0, 1, 1.0):
        return "infrastructure_error", None, "infrastructure_error"
    if status == "passed" and passed == 1:
        return "passed", 1.0, "passed"
    if status == "failed" and passed == 0:
        reason = "compile_failure" if "compile" in str(result.feedback).lower() else "mismatch"
        return "failed", 0.0, reason
    if status == "timeout":
        return "timeout", 0.0, "timeout"
    return "infrastructure_error", None, "infrastructure_error"


def verify_tasks(tasks: list[Task], evaluator, out: Path, mode: str, *, timeout: float = 90) -> dict:
    """Visit all supplied tasks, recording only public IDs and categorized verdicts."""
    out = Path(out)
    safe_path(out, ".")
    summary_path = safe_path(out, "summary.json")
    safe_path(out, "summary.json.tmp")
    if summary_path.exists() or summary_path.is_symlink():
        raise ConfigurationError("Existing summary.json ledger cannot be overwritten")
    if (out / "summary.json.tmp").exists():
        raise ConfigurationError("Existing summary.json.tmp ledger cannot be overwritten")
    summary = {"dataset": mode, "expected": 156, "attempted": 0,
               "unattempted": len(tasks), "failed": 0, "cases": [], "status": "running"}
    out.mkdir(parents=True, exist_ok=True)
    with summary_path.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, allow_nan=False)

    if mode not in _MODES:
        summary["status"] = "failed"
        write_json(summary_path, summary)
        raise ConfigurationError("Unsupported Verilog-Eval dataset")

    seen = set()
    for task in sorted(tasks, key=lambda row: row.id if isinstance(row.id, str) else ""):
        started = time.monotonic()
        case_id = task.id if isinstance(task.id, str) and _ID.fullmatch(task.id) else "<invalid>"
        case = {"id": case_id, "status": "failed", "passed": None,
                "reason": "reference_invalid"}
        try:
            _public_id(task.id)
            if task.id in seen or task.evaluation.get("problem_id") != task.id:
                raise ConfigurationError("Duplicate or mismatched Verilog-Eval problem ID")
            seen.add(task.id)
            if task.evaluation.get("mode") != _MODES[mode]:
                raise ConfigurationError("Verilog-Eval task mode mismatch")
            source = task.evaluation.get("source_dir")
            if not isinstance(source, (str, Path)) or not source:
                raise ConfigurationError("Verilog-Eval source is missing")
            directory = safe_path(Path(source), "dataset_" + _MODES[mode])
            candidate = reference_submission(directory, task.id)
            candidate_dir = safe_path(out, f"cases/{task.id}/output")
            candidate_path = safe_path(candidate_dir, "solution.sv")
            if candidate_dir.exists():
                raise ConfigurationError("Verilog-Eval case output already exists")
            candidate_dir.mkdir(parents=True)
            with candidate_path.open("x", encoding="utf-8") as stream:
                stream.write(candidate)
        except ConfigurationError:
            pass
        except (OSError, ValueError, TypeError):
            case["status"] = "infrastructure_error"
            case["reason"] = "infrastructure_error"
        else:
            try:
                result = evaluator.evaluate(task, candidate_dir, timeout)
                case["status"], case["passed"], case["reason"] = _verdict(result)
            except TimeoutError:
                case["status"] = "timeout"
                case["reason"] = "timeout"
            except Exception:
                case["status"] = "infrastructure_error"
                case["reason"] = "infrastructure_error"
        case["elapsed_seconds"] = time.monotonic() - started
        summary["cases"].append(case)
        summary["attempted"] += 1
        summary["unattempted"] = len(tasks) - summary["attempted"]
        summary["failed"] += case["status"] != "passed"
        write_json(summary_path, summary)

    summary["status"] = ("passed" if len(tasks) == summary["expected"]
                         and not summary["failed"] else "failed")
    write_json(summary_path, summary)
    return summary
