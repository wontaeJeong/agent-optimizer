"""Optional real simulator proof, using a separately prepared pinned source tree."""
import os
import tempfile
import unittest
from pathlib import Path

from agent_optimizer.contracts import Task
from examples.benchmarks.verilog_evaluator import VerilogEvaluator
from examples.benchmarks.verilog_eval import RUNTIME_IMAGE


@unittest.skipUnless(os.environ.get("AGENT_OPT_TEST_VERILOG_EVAL_ROOT"),
                     "Set AGENT_OPT_TEST_VERILOG_EVAL_ROOT to the prepared pinned checkout")
class VerilogEvalIntegrationTests(unittest.TestCase):
    def test_reference_passes_and_wrong_rtl_fails_private_testbench(self):
        root = Path(os.environ["AGENT_OPT_TEST_VERILOG_EVAL_ROOT"])
        problem = "Prob001_zero"
        source = root / "dataset_spec-to-rtl"
        correct = (source / f"{problem}_ref.sv").read_text().replace("RefModule", "TopModule")
        candidate = {"source_dir": str(root), "problem_id": problem, "mode": "spec-to-rtl"}
        task = Task(problem, "validation", "always zero", {"solution.sv": ""}, candidate)
        evaluator = VerilogEvaluator({"kind": "docker", "image": RUNTIME_IMAGE})
        evaluator.validate_benchmark([task], {"source_revision": "c498220d0a52248f8e3fdffe279075215bde2da6"})
        # Colima shares the repository, but not macOS's /private/var temporary path.
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "external") as directory:
            for label, content, expected in (
                ("correct", correct, "passed"),
                ("wrong", "module TopModule(output zero); assign zero = 1'b1; endmodule", "failed"),
            ):
                with self.subTest(label=label):
                    output_dir = Path(directory) / label / "output"
                    output_dir.mkdir(parents=True)
                    (output_dir / "solution.sv").write_text(content)
                    result = evaluator.evaluate(task, output_dir, 60)
                    diagnostic = output_dir.parent / "verilog_evaluation/compile_logs/stderr.log"
                    self.assertEqual(result.status, expected,
                                     result.feedback + " / " + diagnostic.read_text(errors="replace"))


if __name__ == "__main__":
    unittest.main()
