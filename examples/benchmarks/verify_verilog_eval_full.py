"""Submit pinned references to the existing private Verilog-Eval evaluator."""
from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import time
from pathlib import Path

from agent_optimizer.config import load_tasks
from agent_optimizer.contracts import ConfigurationError, Evaluation, Task, UnavailableError
from agent_optimizer.registry import Registry
from agent_optimizer.results import write_json
from agent_optimizer.workspace import safe_path
if __package__:
    from .verilog_eval import REVISION, RUNTIME_IMAGE
    from .verilog_evaluator import VerilogEvaluator
else:
    from verilog_eval import REVISION, RUNTIME_IMAGE
    from verilog_evaluator import VerilogEvaluator


_MODES = {"verilog-spec": "spec-to-rtl", "verilog-completion": "code-complete-iccad2023"}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
ROOT = Path(__file__).resolve().parents[2]
_WRONG_RTL = "module TopModule(output zero); assign zero = 1'b1; endmodule"


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
        feedback = result.feedback
        if feedback == "Verilog-Eval compile did not complete":
            return "failed", 0.0, "compile_failure"
        if feedback in {"RTL solution missing", "Candidate contains unsupported simulation control"}:
            return "failed", 0.0, "reference_invalid"
        if isinstance(feedback, str) and re.fullmatch(
            r"Verilog-Eval: [1-9][0-9]* mismatches in [1-9][0-9]* samples", feedback
        ):
            return "failed", 0.0, "mismatch"
        return "infrastructure_error", None, "infrastructure_error"
    if status == "timeout":
        return "timeout", 0.0, "timeout"
    return "infrastructure_error", None, "infrastructure_error"


def _start_ledger(out: Path, summary: dict) -> Path:
    safe_path(out, ".")
    summary_path = safe_path(out, "summary.json")
    temporary = safe_path(out, "summary.json.tmp")
    if summary_path.exists() or summary_path.is_symlink() or temporary.exists():
        raise ConfigurationError("Existing summary.json ledger cannot be overwritten")
    out.mkdir(parents=True, exist_ok=True)
    with summary_path.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, allow_nan=False)
    return summary_path


def _initial_summary(mode: str, remaining: int) -> dict:
    return {"dataset": mode, "expected": 156, "attempted": 0,
            "unattempted": remaining, "failed": 0, "cases": [], "status": "running",
            "host": {"os": None, "arch": None},
            "docker_daemon": {"os": None, "arch": None},
            "source_revision": None, "image_id": None, "actual_task_count": None}


def verify_tasks(tasks: list[Task], evaluator, out: Path, mode: str, *, timeout: float = 90,
                 _summary: dict | None = None, _finalize: bool = True) -> dict:
    """Visit all supplied tasks, recording only public IDs and categorized verdicts."""
    if not isinstance(mode, str) or mode not in _MODES:
        raise ConfigurationError("Unsupported Verilog-Eval dataset")
    out = Path(out)
    if _summary is None:
        summary = _initial_summary(mode, len(tasks))
        summary_path = _start_ledger(out, summary)
    else:
        summary_path = safe_path(out, "summary.json")
        safe_path(out, "summary.json.tmp")
        initial = _initial_summary(mode, 156)
        core = ("dataset", "expected", "attempted", "unattempted", "failed", "cases", "status")
        if (summary_path.is_symlink() or not summary_path.is_file()
                or (out / "summary.json.tmp").exists()
                or json.loads(summary_path.read_text(encoding="utf-8")) != _summary
                or any(_summary.get(key) != initial[key] for key in core)):
            raise ConfigurationError("Verilog-Eval initialized ledger is invalid")
        summary = _summary

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

    if _finalize:
        summary["status"] = ("passed" if len(tasks) == summary["expected"]
                             and not summary["failed"] else "failed")
    write_json(summary_path, summary)
    return summary


def _docker_daemon() -> dict:
    try:
        result = subprocess.run(["docker", "info", "--format", "{{.Server.Os}}/{{.Server.Arch}}"],
                                capture_output=True, text=True, timeout=20, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UnavailableError("Verilog-Eval Docker daemon is unavailable") from exc
    match = re.fullmatch(r"(linux|windows)/(amd64|arm64)", result.stdout.strip()) if not result.returncode else None
    if not match:
        raise UnavailableError("Verilog-Eval Docker daemon platform is unavailable")
    return {"os": match[1], "arch": match[2]}


def _inspected_image_id() -> str:
    try:
        result = subprocess.run(["docker", "image", "inspect", RUNTIME_IMAGE],
                                capture_output=True, text=True, timeout=20, shell=False)
        image_id = json.loads(result.stdout)[0]["Id"] if not result.returncode else None
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, IndexError, KeyError) as exc:
        raise UnavailableError("Verilog-Eval image identity could not be inspected") from exc
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise UnavailableError("Verilog-Eval image identity is invalid")
    return image_id


def _prepared_tasks(prepared: dict, provider, cache: Path, mode: str,
                    summary: dict, ledger: Path):
    if (not isinstance(prepared, dict) or prepared.get("evaluator") != "verilog_eval"
            or not isinstance(prepared.get("provenance"), dict)
            or prepared["provenance"].get("revision") != REVISION
            or prepared["provenance"].get("mode") != _MODES[mode]):
        raise ConfigurationError("Verilog-Eval pinned source provenance is invalid")
    runtime = prepared["evaluation_runtime"]
    config = prepared["evaluator_config"]
    image_id = config["image_id"]
    if (runtime != {"kind": "docker", "image": RUNTIME_IMAGE}
            or not isinstance(image_id, str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)
            or prepared["provenance"].get("image_id") != image_id):
        raise ConfigurationError("Verilog-Eval pinned Icarus v12 image identity is invalid")
    checks = provider.doctor(cache)
    if not checks or any(item["status"] != "ok" for item in checks):
        raise UnavailableError("Pinned Verilog-Eval assets are not ready")
    tasks, metadata = load_tasks(Path(prepared["benchmark"]))
    summary["actual_task_count"] = len(tasks)
    if metadata.get("source_revision") == REVISION:
        summary["source_revision"] = REVISION
    write_json(ledger, summary)
    if (len(tasks) != 156 or metadata.get("source_revision") != REVISION
            or not any(task.id == "Prob001_zero" for task in tasks)
            or any(task.evaluation.get("mode") != _MODES[mode] for task in tasks)):
        raise ConfigurationError("Verilog-Eval pinned task inventory is incomplete")
    evaluator = VerilogEvaluator({**runtime, **config})
    summary["image_id"] = _inspected_image_id()
    write_json(ledger, summary)
    if summary["image_id"] != image_id:
        raise ConfigurationError("Verilog-Eval Docker image differs from prepared identity")
    evaluator.validate_benchmark(tasks, metadata)
    return tasks, evaluator


class _SafeParser(argparse.ArgumentParser):
    def error(self, message):
        super().error("Invalid Verilog-Eval command arguments")


def main(argv: list[str] | None = None) -> int:
    parser = _SafeParser(description="고정 Verilog-Eval 전체 reference 검증")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--require-ubuntu-amd64", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    if args.dataset not in _MODES:
        try:
            parser.error("Unsupported Verilog-Eval dataset")
        except SystemExit:
            return 2

    summary = _initial_summary(args.dataset, 156)
    try:
        out = safe_path(ROOT, f"runs/verilog-eval-full/{args.dataset}")
        ledger = _start_ledger(out, summary)
    except (OSError, ConfigurationError):
        print("infrastructure_error: Verilog-Eval ledger unavailable")
        return 1

    try:
        host_os, host_arch = platform.system(), platform.machine()
        summary["host"] = {"os": host_os if host_os in {"Linux", "Darwin", "Windows"} else None,
                           "arch": host_arch if host_arch in {"x86_64", "arm64", "aarch64"} else None}
        write_json(ledger, summary)
        if args.require_ubuntu_amd64 and (host_os != "Linux" or host_arch != "x86_64"):
            raise UnavailableError("Ubuntu amd64 host is required")
        summary["docker_daemon"] = _docker_daemon()
        write_json(ledger, summary)
        if args.require_ubuntu_amd64 and summary["docker_daemon"] != {"os": "linux", "arch": "amd64"}:
            raise UnavailableError("Ubuntu amd64 Docker daemon is required")
        cache = safe_path(ROOT, f"external/datasets/{args.dataset}")
        if cache.exists() and not cache.is_dir():
            raise ConfigurationError("Verilog-Eval cache must be a directory")
        registry = Registry()
        registry.load_project(ROOT)
        provider = registry.resolve("datasets", args.dataset)()
        prepared = provider.prepare(cache)
        tasks, evaluator = _prepared_tasks(prepared, provider, cache, args.dataset, summary, ledger)
        summary = verify_tasks(tasks, evaluator, out, args.dataset, _summary=summary,
                               _finalize=False)
        wrong = next(task for task in tasks if task.id == "Prob001_zero")
        output = safe_path(out, "sanity/Prob001_zero/output")
        candidate = safe_path(output, "solution.sv")
        output.mkdir(parents=True, exist_ok=False)
        with candidate.open("x", encoding="utf-8") as stream:
            stream.write(_WRONG_RTL)
        try:
            verdict = _verdict(evaluator.evaluate(wrong, output, 90))
        except TimeoutError:
            verdict = ("timeout", 0.0, "timeout")
        except Exception:
            verdict = ("infrastructure_error", None, "infrastructure_error")
        summary["wrong"] = {"id": "Prob001_zero", "status": verdict[0],
                            "passed": verdict[1], "reason": verdict[2]}
        summary["status"] = ("passed" if summary["attempted"] == 156
                             and summary["failed"] == 0 and verdict[2] == "mismatch"
                             else "failed")
        write_json(ledger, summary)
    except Exception:
        summary["status"] = "failed"
        summary["reason"] = "infrastructure_error"
        write_json(ledger, summary)
    if summary["status"] != "passed":
        print("infrastructure_error: Verilog-Eval verification failed")
        return 1
    print("Verilog-Eval: 156 reference passed; wrong mismatch confirmed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
