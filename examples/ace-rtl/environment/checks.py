"""Small, example-local developer checks using the existing evaluators and runner."""
import json
import importlib.util
import uuid
from dataclasses import asdict
from pathlib import Path

from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError, Task, UnavailableError
from agent_optimizer.process import execute
from agent_optimizer.registry import Registry
from agent_optimizer.results import write_json
from agent_optimizer.runner import run_experiment

ROOT = Path(__file__).resolve().parents[3]


def require_verdict(result, expected, *, official=False):
    if result.status != expected or result.metrics.get("passed") != float(expected == "passed"):
        raise UnavailableError(f"Smoke expected {expected}, got {result.status}: {result.feedback}")
    if official:
        artifact = Path(result.artifacts.get("raw_result", ""))
        raw = json.loads(artifact.read_text()) if artifact.is_file() else {}
        if not raw or any(not r.get("tests") for r in raw.values()):
            raise UnavailableError("Official smoke requires nonempty raw tests")


def smoke(lock):
    root = ROOT / "runs" / ("dev-smoke-" + uuid.uuid4().hex[:12])
    root.mkdir(parents=True)
    report = {"status": "running", "environment": lock, "checks": []}
    write_json(root / "summary.json", report)
    runtime = {"kind": "docker", "image": lock["images"]["evaluation"]["id"], "network": "none"}
    registry = Registry()
    registry.load_plugins(ROOT, {"evaluators": {
        "toy": "examples/rtl-debugger/evaluator.py:create",
        "official": "examples/ace-rtl/evaluator.py:CVDPEvaluator",
    }})
    try:
        # A skip is a failed gate: all nine T4 real-tool tests must execute.
        code = ("import unittest; suite=unittest.defaultTestLoader.loadTestsFromName('test_rtl_evaluation.RealRTLTests'); "
                "r=unittest.TextTestRunner(verbosity=2).run(suite); "
                "raise SystemExit(0 if r.testsRun == 9 and r.wasSuccessful() and not r.skipped else 1)")
        tools = execute(["python3", "-c", code], ROOT, root / "real-tool-tests", 300, runtime,
                        {"PYTHONPATH": "/work/src:/work/tests", "PYTHONDONTWRITEBYTECODE": "1"})
        report["checks"].append({"name": "T4-real-tools", **asdict(tools)})
        tool_gate_failed = tools.status != "completed"
        if tools.status not in {"completed", "process_error"}:
            raise UnavailableError(f"T4 tool gate failed; see {root / 'real-tool-tests'}")
        task = Task(**json.loads((ROOT / "examples/rtl-debugger/tasks.json").read_text())["tasks"][0])
        evaluator = registry.resolve("evaluators", "toy")(runtime)
        wrong = task.files["dut.sv"]
        cases = [("positive", wrong.replace("assign y = a;", "assign y = a ^ b;"), "passed"),
                 ("negative", wrong, "failed"),
                 ("early-exit", wrong.replace("endmodule", 'initial begin $display("TEST_PASS"); $finish; end endmodule'), "failed")]
        for name, source, expected in cases:
            out = root / ("toy-" + name) / "output"
            out.mkdir(parents=True)
            (out / "dut.sv").write_text(source)
            result = evaluator.evaluate(task, out, 60)
            report["checks"].append({"name": "host-docker-" + name, **asdict(result)})
            write_json(out.parent / "result.json", asdict(result))
            require_verdict(result, expected)
        # Only this trusted smoke reads a reference submission; it never enters an Agent trial.
        source = ROOT / "external/cvdp_benchmark/example_dataset/cvdp_v1.1.0_example_nonagentic_code_generation_no_commercial_with_solutions.jsonl"
        reference = next(r for r in map(json.loads, source.read_text().splitlines()) if r["id"] == "cvdp_copilot_lfsr_0001")
        spec = importlib.util.spec_from_file_location("ace_smoke_prepare", ROOT / "examples/ace-rtl/prepare.py")
        prepare = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prepare)
        tasks, excluded = prepare.convert([reference])
        if not tasks:
            raise UnavailableError(f"Reviewed reference smoke is unsupported: {excluded}")
        task = Task(**tasks[0])
        official = registry.resolve("evaluators", "official")()
        official.validate_benchmark([task], {"synthetic": False})
        for name, expected in [("positive", "passed"), ("negative", "failed")]:
            out = root / ("cvdp-" + name) / "output"
            for target, text in reference["output"]["context"].items():
                file = out / target
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(text if name == "positive" else
                                "module lfsr_8bit(input clock, reset, input [7:0] lfsr_seed, "
                                "output [7:0] lfsr_out); assign lfsr_out = 8'hff; endmodule\n")
            result = official.evaluate(task, out, 180)
            report["checks"].append({"name": "official-" + name, **asdict(result)})
            write_json(out.parent / "result.json", asdict(result))
            require_verdict(result, expected, official=True)
        if tool_gate_failed:
            raise UnavailableError(f"T4 tool gate failed; independent checks retained in {root}")
        report["status"] = "passed"
    except BaseException:
        report["status"] = "failed"
        raise
    finally:
        write_json(root / "summary.json", report)
        print(json.dumps({"status": report["status"], "results": str(root)}))
    return 0


def live(lock, iterations=None):
    spec = load_experiment(ROOT / "examples/ace-rtl/experiment.toml")
    if iterations is not None:
        if type(iterations) is not int or not 1 <= iterations <= 20:
            raise ConfigurationError("Iterations must be an integer from 1 to 20")
        spec["stages"][0]["config"]["iterations"] = iterations
    count = spec["stages"][0]["config"]["iterations"]
    if {t.split for t in spec["_tasks"]} != {"train", "validation"} or len(spec["_tasks"]) != 2:
        raise ConfigurationError("Live demo needs prepared train/validation tasks; rerun setup")
    spec["budget"]["max_trials"] = 2 * (count + 1)
    spec["budget"]["max_wall_time_seconds"] = 2 * (count + 1) * spec["budget"]["trial_timeout_seconds"] + count * 60 + 180
    for profile in spec["_profiles"]:
        profile["runtime"]["image"] = lock["images"]["agent"]["id"]
    root, summary = run_experiment(spec, Registry(), ROOT / "runs/dev-live")
    print(json.dumps({"status": summary["status"], "results": str(root)}))
    return 0 if summary["status"] == "completed" else 3
