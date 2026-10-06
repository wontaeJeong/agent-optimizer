"""Submit pinned references to the existing private Verilog-Eval evaluator."""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


class _ReferenceInvalid(ConfigurationError):
    """A task or _ref declaration is invalid independent of the filesystem."""


def _public_id(problem_id: str) -> str:
    if not isinstance(problem_id, str) or not _ID.fullmatch(problem_id):
        raise _ReferenceInvalid("Invalid Verilog-Eval problem ID")
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
        raise _ReferenceInvalid("Verilog-Eval reference needs exactly one RefModule declaration")
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
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=out,
                                     prefix="summary.json.", suffix=".tmp", delete=False) as stream:
        staged = Path(stream.name)
    try:
        with staged.open("w", encoding="utf-8") as stream:
            json.dump(summary, stream, ensure_ascii=False, allow_nan=False)
        os.link(staged, summary_path)
    finally:
        staged.unlink(missing_ok=True)
    return summary_path


def _initial_summary(mode: str, remaining: int, scope: str = "full") -> dict:
    return {"dataset": mode, "scope": scope, "expected": 1 if scope == "smoke" else 156,
            "attempted": 0,
            "unattempted": remaining, "failed": 0, "cases": [], "status": "running",
            "host": {"os": None, "arch": None},
            "docker_daemon": {"os": None, "arch": None},
            "image_platform": {"os": None, "arch": None},
            "source_revision": None, "image_id": None, "actual_task_count": None}


def verify_tasks(tasks: list[Task], evaluator, out: Path, mode: str, *, timeout: float = 90,
                 _summary: dict | None = None, _finalize: bool = True,
                 scope: str = "full", jobs: int = 1) -> dict:
    """Visit all supplied tasks, recording only public IDs and categorized verdicts."""
    if not isinstance(mode, str) or mode not in _MODES:
        raise ConfigurationError("Unsupported Verilog-Eval dataset")
    if scope not in {"full", "smoke"}:
        raise ConfigurationError("Unsupported Verilog-Eval verification scope")
    if type(jobs) is not int or not 1 <= jobs <= 16:
        raise ConfigurationError("Verilog-Eval jobs must be an integer from 1 to 16")
    out = Path(out)
    if _summary is None:
        summary = _initial_summary(mode, len(tasks), scope)
        summary_path = _start_ledger(out, summary)
    else:
        summary_path = safe_path(out, "summary.json")
        safe_path(out, "summary.json.tmp")
        initial = _initial_summary(mode, 1 if scope == "smoke" else 156, scope)
        core = ("dataset", "scope", "expected", "attempted", "unattempted", "failed",
                "cases", "status")
        if (summary_path.is_symlink() or not summary_path.is_file()
                or (out / "summary.json.tmp").exists()
                or json.loads(summary_path.read_text(encoding="utf-8")) != _summary
                or any(_summary.get(key) != initial[key] for key in core)):
            raise ConfigurationError("Verilog-Eval initialized ledger is invalid")
        summary = _summary

    def evaluate_case(task, duplicate):
        started = time.monotonic()
        case_id = task.id if isinstance(task.id, str) and _ID.fullmatch(task.id) else "<invalid>"
        case = {"id": case_id, "status": "failed", "passed": None,
                "reason": "reference_invalid"}
        try:
            _public_id(task.id)
            if duplicate or task.evaluation.get("problem_id") != task.id:
                raise _ReferenceInvalid("Duplicate or mismatched Verilog-Eval problem ID")
            if task.evaluation.get("mode") != _MODES[mode]:
                raise _ReferenceInvalid("Verilog-Eval task mode mismatch")
            source = task.evaluation.get("source_dir")
            if not isinstance(source, (str, Path)) or not source:
                raise _ReferenceInvalid("Verilog-Eval source is missing")
            directory = safe_path(Path(source), "dataset_" + _MODES[mode])
            candidate = reference_submission(directory, task.id)
            candidate_dir = safe_path(out, f"cases/{task.id}/output")
            candidate_path = safe_path(candidate_dir, "solution.sv")
            if candidate_dir.exists():
                raise ConfigurationError("Verilog-Eval case output already exists")
            candidate_dir.mkdir(parents=True)
            with candidate_path.open("x", encoding="utf-8") as stream:
                stream.write(candidate)
        except _ReferenceInvalid:
            pass
        except (ConfigurationError, OSError, ValueError, TypeError):
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
        return case

    def record(case):
        summary["cases"].append(case)
        summary["cases"].sort(key=lambda row: row["id"])
        summary["attempted"] += 1
        summary["unattempted"] = len(tasks) - summary["attempted"]
        summary["failed"] += case["status"] != "passed"
        write_json(summary_path, summary)

    seen = set()
    scheduled = []
    for task in sorted(tasks, key=lambda row: row.id if isinstance(row.id, str) else ""):
        duplicate = isinstance(task.id, str) and task.id in seen
        if isinstance(task.id, str):
            seen.add(task.id)
        scheduled.append((task, duplicate))
    if jobs == 1:
        for task, duplicate in scheduled:
            record(evaluate_case(task, duplicate))
    else:
        # Only the coordinator writes the ledger; workers own disjoint case paths.
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            futures = [executor.submit(evaluate_case, task, duplicate) for task, duplicate in scheduled]
            for future in as_completed(futures):
                record(future.result())

    if _finalize:
        summary["status"] = ("passed" if len(tasks) == summary["expected"]
                             and not summary["failed"] else "failed")
    write_json(summary_path, summary)
    return summary


def _docker_daemon() -> dict:
    try:
        result = subprocess.run(["docker", "version", "--format", "{{.Server.Os}}/{{.Server.Arch}}"],
                                capture_output=True, text=True, timeout=20, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UnavailableError("Verilog-Eval Docker daemon is unavailable") from exc
    match = re.fullmatch(r"(linux|windows)/(amd64|arm64)", result.stdout.strip()) if not result.returncode else None
    if not match:
        raise UnavailableError("Verilog-Eval Docker daemon platform is unavailable")
    return {"os": match[1], "arch": match[2]}


def _inspected_image() -> dict:
    try:
        result = subprocess.run(["docker", "image", "inspect", RUNTIME_IMAGE],
                                capture_output=True, text=True, timeout=20, shell=False)
        image = json.loads(result.stdout)[0] if not result.returncode else None
        image_id = image["Id"]
        image_os = image["Os"]
        image_arch = image["Architecture"]
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, IndexError, KeyError) as exc:
        raise UnavailableError("Verilog-Eval image platform could not be inspected") from exc
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise UnavailableError("Verilog-Eval image identity is invalid")
    if image_os not in {"linux", "windows"} or image_arch not in {"amd64", "arm64"}:
        raise UnavailableError("Verilog-Eval image platform is invalid")
    return {"id": image_id, "os": image_os, "arch": image_arch}


def _validate_cache(cache: Path, mode: str) -> None:
    safe_path(cache, ".")
    for name in ("source", f"source/{REVISION}", "verilog-eval-" + _MODES[mode]):
        path = safe_path(cache, name)
        if path.exists() and not path.is_dir():
            raise ConfigurationError("Verilog-Eval cache directory is invalid")
    for name in ("runtime-lock.json", "runtime-lock.json.tmp",
                 f"verilog-eval-{_MODES[mode]}/tasks.json",
                 f"verilog-eval-{_MODES[mode]}/tasks.json.tmp",
                 f"verilog-eval-{_MODES[mode]}/provenance.json",
                 f"verilog-eval-{_MODES[mode]}/provenance.json.tmp"):
        path = safe_path(cache, name)
        if path.exists() and not path.is_file():
            raise ConfigurationError("Verilog-Eval cache file is invalid")


def _prepared_tasks(prepared: dict, provider, cache: Path, mode: str,
                    summary: dict, ledger: Path, *, require_ubuntu_amd64: bool = False):
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
    image = _inspected_image()
    summary["image_id"] = image["id"]
    summary["image_platform"] = {"os": image["os"], "arch": image["arch"]}
    write_json(ledger, summary)
    if summary["image_id"] != image_id:
        raise ConfigurationError("Verilog-Eval Docker image differs from prepared identity")
    if image["os"] != "linux" or (require_ubuntu_amd64 and image["arch"] != "amd64"):
        raise UnavailableError("Verilog-Eval Docker image platform is unsupported")
    evaluator.validate_benchmark(tasks, metadata)
    return tasks, evaluator


class _SafeParser(argparse.ArgumentParser):
    def error(self, message):
        super().error("Invalid Verilog-Eval command arguments")


def main(argv: list[str] | None = None) -> int:
    parser = _SafeParser(description="고정 Verilog-Eval reference 검증")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--require-ubuntu-amd64", action="store_true")
    parser.add_argument("--smoke-one", action="store_true")
    parser.add_argument("--jobs", type=int, default=1)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    if (args.dataset not in _MODES or (args.smoke_one and args.require_ubuntu_amd64)
            or not 1 <= args.jobs <= 16):
        try:
            parser.error("Unsupported Verilog-Eval dataset")
        except SystemExit:
            return 2

    scope = "smoke" if args.smoke_one else "full"
    summary = _initial_summary(args.dataset, 1 if args.smoke_one else 156, scope)
    try:
        out = safe_path(ROOT, f"runs/verilog-eval-{scope}/{args.dataset}")
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
        _validate_cache(cache, args.dataset)
        registry = Registry()
        registry.load_project(ROOT)
        provider = registry.resolve("datasets", args.dataset)()
        prepared = provider.prepare(cache)
        tasks, evaluator = _prepared_tasks(prepared, provider, cache, args.dataset, summary, ledger,
                                           require_ubuntu_amd64=args.require_ubuntu_amd64)
        selected = ([next(task for task in tasks if task.id == "Prob001_zero")]
                    if args.smoke_one else tasks)
        summary = verify_tasks(selected, evaluator, out, args.dataset, _summary=summary,
                               _finalize=False, scope=scope, jobs=args.jobs)
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
        summary["status"] = ("passed" if summary["attempted"] == summary["expected"]
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
    print(f"Verilog-Eval {scope}: {summary['attempted']} reference passed; wrong mismatch confirmed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
