"""Check actual official CVDP verdicts from a prepared, wheel-only ACE workspace.

Run this optional Docker integration check with the installed wheel's Python,
using the selected workspace as cwd. It does not run a model or expose reference
answers to an Agent trial.
"""

import importlib.util
import json
import os
import uuid
from pathlib import Path

from agent_optimizer.contracts import Task
from agent_optimizer.integrations import resolve_pointer


def load(root: Path, relative: str, name: str):
    path = root / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    root = Path.cwd()
    resolve_pointer(root / "experiment.toml")
    lifecycle = load(root, "examples/ace-rtl/environment/lifecycle.py", "selected_lifecycle")
    report = lifecycle.inspect(root)
    if not report["ready"]:
        raise AssertionError(f"선택한 작업공간의 실도구 진단이 실패했습니다: {report['checks']}")
    os.environ["DOCKER_DEFAULT_PLATFORM"] = report["platform"]
    os.environ["OSS_SIM_IMAGE"] = report["sim_image"]

    source = root / "external/cvdp_benchmark/example_dataset/" \
        "cvdp_v1.1.0_example_nonagentic_code_generation_no_commercial_with_solutions.jsonl"
    reference = next(row for row in map(json.loads, source.read_text().splitlines())
                     if row["id"] == "cvdp_copilot_lfsr_0001")
    prepare = load(root, "examples/ace-rtl/prepare.py", "selected_prepare")
    tasks, excluded = prepare.convert([reference])
    if len(tasks) != 1 or excluded:
        raise AssertionError(f"공식 평가 과제 변환 실패: {excluded}")
    task = Task(**tasks[0])
    evaluator = load(root, "examples/ace-rtl/evaluator.py", "selected_evaluator").CVDPEvaluator()
    evaluator.validate_benchmark([task], {"synthetic": False})

    results = root / "runs" / ("wheel-official-" + uuid.uuid4().hex[:12])
    for name, expected in (("positive", "passed"), ("negative", "failed")):
        output = results / name / "output"
        for relative, answer in reference["output"]["context"].items():
            file = output / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(answer if name == "positive" else
                            "module lfsr_8bit(input clock, reset, input [7:0] lfsr_seed, "
                            "output [7:0] lfsr_out); assign lfsr_out = 8'hff; endmodule\n")
        verdict = evaluator.evaluate(task, output, 180)
        artifact = Path(verdict.artifacts.get("raw_result", ""))
        raw = json.loads(artifact.read_text()) if artifact.is_file() else {}
        if (verdict.status != expected or verdict.metrics.get("passed") != float(name == "positive")
                or not raw or any(not row.get("tests") for row in raw.values())):
            raise AssertionError(f"공식 평가 {name} 결과가 예상과 다릅니다: {verdict}")
    print(json.dumps({"status": "passed", "workspace": str(root), "results": str(results),
                      "evaluation": {"positive": "passed", "negative": "failed"}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
