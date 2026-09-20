"""Toy RTL boundary contracts; real tool tests also run in the T5 tool image."""
import json
import os
import shlex
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.contracts import ConfigurationError, ExecutionResult, Task
from agent_optimizer.process import execute
from support import IcarusVerilog, ROOT, module

SimulationEvaluator = module("example_rtl_evaluator", ROOT / "examples/rtl-debugger/evaluator.py").SimulationEvaluator
CORRECT = "module dut(input a,b,output y); assign y=a^b; endmodule\n"
WRONG = "module dut(input a,b,output y); assign y=a; endmodule\n"
ATTACK = ('module dut(input a,b,output y); assign y=a; '
          'initial begin $display("TEST_PASS"); $finish; end endmodule\n')
TB = '''module tb;
reg a,b;
wire y;
integer i;
dut u(a,b,y);
initial begin
 for(i=0;i<4;i=i+1) begin
  {a,b}=i; #1;
  if(y !== (a^b)) $fatal(1,"Mismatch");
 end
 $display("TEST_PASS"); $finish;
end
endmodule
'''


def config():
    return {"design_sources": ["dut.sv"], "design_top": "dut",
            "sources": ["dut.sv", "private/tb.sv"], "top": "tb",
            "private_files": {"private/tb.sv": TB}, "pass_marker": "TEST_PASS"}


class RTLContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "output"
        self.root.mkdir()
        (self.root / "dut.sv").write_text(CORRECT)
        self.config = config()
        self.clock = 0.0
        self.calls = []

    def tool(self, argv, cwd, logs, timeout, runtime):
        """Model process side effects and reject broken phase/source composition."""
        self.calls.append((argv, cwd, timeout, runtime))
        self.assertGreater(timeout, 0)
        self.assertFalse(cwd == self.root or cwd.is_relative_to(self.root))
        logs.mkdir(parents=True, exist_ok=True)
        stdout, stderr = logs / "stdout.log", logs / "stderr.log"
        stdout.write_text("TEST_PASS\n" if argv[0] == "yosys" else "")
        stderr.write_text("")
        if argv[0] == "yosys":
            self.assertEqual(argv[1], "-p")
            commands = [shlex.split(command) for command in argv[2].split(";")]
            sources = [word for command in commands if command[0] == "read_verilog"
                       for word in command[1:] if not word.startswith("-")]
            self.assertEqual([p.read_text() for p in map(cwd.joinpath, sources)], [CORRECT])
            self.assertFalse(any(TB in p.read_text() for p in cwd.rglob("*.sv")))
            netlist = commands[-1][-1]
            self.assertEqual(commands[-1][0], "write_verilog")
            (cwd / netlist).write_text("// generated netlist\n" + CORRECT)
        elif argv[0] == "iverilog":
            self.assertEqual(argv[1:5], ["-g2012", "-s", "tb", "-o"])
            contents = [(cwd / name).read_text() for name in argv[6:]]
            self.assertEqual(contents, ["// generated netlist\n" + CORRECT, TB])
            self.assertNotEqual(cwd, self.calls[0][1])
            self.assertFalse(self.calls[0][1].is_relative_to(cwd))
            self.assertFalse(cwd.is_relative_to(self.calls[0][1]))
            (cwd / argv[5]).write_bytes(b"compiled simulation")
        elif argv[0] == "vvp":
            self.assertEqual(len(argv), 2)
            self.assertEqual((cwd / argv[1]).read_bytes(), b"compiled simulation")
            stdout.write_text("TEST_PASS\n")
        else:
            self.fail(f"Unexpected tool: {argv}")
        self.clock += 2
        return ExecutionResult("completed", 0, 2, str(stdout), str(stderr))

    def evaluate(self, tool=None, timeout=10, runtime=None):
        with patch("example_iverilog.execute", side_effect=tool or self.tool), \
             patch("time.monotonic", side_effect=lambda: self.clock):
            return IcarusVerilog(runtime).run(self.root, self.config, timeout)

    def test_only_generated_netlist_and_private_testbench_are_simulated(self):
        # Candidate-supplied files at reserved-looking paths must never be consumed.
        (self.root / "private").mkdir()
        (self.root / "private/tb.sv").write_text("forged testbench")
        (self.root / "netlist.v").write_text("forged netlist")
        (self.root / "sim.out").write_text("forged executable")
        task = Task("toy", "validation", "", {}, self.config)
        with patch("example_iverilog.execute", side_effect=self.tool):
            result = SimulationEvaluator(IcarusVerilog()).evaluate(task, self.root, 10)
        self.assertEqual(result.status, "passed")
        self.assertEqual([call[0][0] for call in self.calls], ["yosys", "iverilog", "vvp"])
        self.assertEqual((self.root / "private/tb.sv").read_text(), "forged testbench")
        self.assertTrue(all(Path(path).is_file() for path in result.artifacts.values()))

    def test_design_filenames_cannot_become_yosys_script_commands(self):
        name = "dut; shell unwanted.sv"
        (self.root / "dut.sv").rename(self.root / name)
        self.config["design_sources"] = [name]
        self.config["sources"][0] = name
        self.assertEqual(self.evaluate().status, "passed")
        self.assertNotIn(name, self.calls[0][0][2])

    def test_private_filename_cannot_overwrite_generated_netlist(self):
        self.config["private_files"] = {"netlist.v": TB}
        self.config["sources"] = ["dut.sv", "netlist.v"]
        self.assertEqual(self.evaluate().status, "passed")

    def test_synthesis_marker_and_partial_simulator_marker_cannot_pass(self):
        for output in ("", "NOT_TEST_PASS", "TEST_PASS_EXTRA"):
            with self.subTest(output=output):
                def tool(*args):
                    result = self.tool(*args)
                    if args[0][0] == "vvp":
                        Path(result.stdout_path).write_text(output)
                    return result
                self.assertEqual(self.evaluate(tool).status, "failed")

    def test_nonzero_exit_after_marker_cannot_pass(self):
        def tool(*args):
            result = self.tool(*args)
            if args[0][0] == "vvp":
                result.status, result.returncode = "process_error", 1
            return result
        self.assertEqual(self.evaluate(tool).metrics["passed"], 0.0)

    def test_missing_tools_are_infrastructure_errors_at_each_phase(self):
        for missing in ("yosys", "iverilog", "vvp"):
            with self.subTest(missing=missing):
                self.clock, self.calls = 0, []
                def tool(*args):
                    if args[0][0] == missing:
                        self.calls.append((args[0], args[1], args[3], args[4]))
                        return ExecutionResult("infrastructure_error", None, 0, "", "", detail="missing tool")
                    return self.tool(*args)
                result = self.evaluate(tool)
                self.assertEqual(result.status, "infrastructure_error")
                self.assertIsNone(result.metrics["passed"])
                self.assertEqual(self.calls[-1][0][0], missing)

    def test_missing_yosys_via_real_local_process_is_not_a_zero_score(self):
        with patch.dict(os.environ, {"PATH": ""}):
            result = IcarusVerilog().run(self.root, self.config, 10)
        self.assertEqual(result.status, "infrastructure_error", result)
        self.assertIsNone(result.metrics["passed"])
        self.assertNotIn("simulation_log", result.artifacts)

    def test_timeouts_stop_at_each_phase_and_share_one_deadline(self):
        for phase in ("yosys", "iverilog", "vvp"):
            with self.subTest(phase=phase):
                self.clock, self.calls = 0, []
                def tool(*args):
                    result = self.tool(*args)
                    if args[0][0] == phase:
                        result.status, result.returncode = "timeout", -9
                    return result
                result = self.evaluate(tool)
                self.assertEqual(result.status, "timeout")
                self.assertEqual(result.metrics["passed"], 0.0)
                self.assertEqual(self.calls[-1][0][0], phase)
        self.clock, self.calls = 0, []
        runtime = {"kind": "docker", "image": "trusted-tools:test"}
        self.assertEqual(self.evaluate(runtime=runtime).status, "passed")
        self.assertEqual([call[2] for call in self.calls], [10, 8, 6])
        self.assertTrue(all(call[3] == runtime for call in self.calls))

    def test_exhausted_deadline_does_not_start_next_phase(self):
        for budget, tools in ((0, []), (2, ["yosys"]), (4, ["yosys", "iverilog"])):
            with self.subTest(budget=budget):
                self.clock, self.calls = 0, []
                self.assertEqual(self.evaluate(timeout=budget).status, "timeout")
                self.assertEqual([call[0][0] for call in self.calls], tools)

    def test_failed_synthesis_never_releases_private_testbench(self):
        def tool(*args):
            result = self.tool(*args)
            result.status, result.returncode = "process_error", 1
            return result
        result = self.evaluate(tool)
        self.assertEqual(result.status, "failed")
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(any(TB in p.read_text() for p in Path(self.tmp.name).rglob("*.sv")))

    def test_missing_generated_netlist_is_infrastructure_error(self):
        def tool(*args):
            result = self.tool(*args)
            for path in args[1].glob("*.v"):
                path.unlink()
            return result
        self.assertEqual(self.evaluate(tool).status, "infrastructure_error")
        self.assertEqual(len(self.calls), 1)

    def test_simulation_controls_and_synthesis_escape_hatches_are_rejected(self):
        for source in (ATTACK, CORRECT + '`include "private/tb.sv"\n',
                       CORRECT.replace("assign y=a^b;", "assign #1 y=a^b;"),
                       "(* blackbox *) " + CORRECT,
                       CORRECT + "// synthesis translate_off\n",
                       CORRECT.replace("assign y=a^b;", "always @* begin $display(\"TEST_PASS\"); end")):
            with self.subTest(source=source), patch("example_iverilog.execute") as run:
                (self.root / "dut.sv").write_text(source)
                result = IcarusVerilog().run(self.root, self.config, 10)
                self.assertEqual(result.status, "failed")
                self.assertIn("Unsupported", result.feedback)
                run.assert_not_called()

    def test_source_and_top_configuration_cannot_bypass_boundary(self):
        changes = [{"design_sources": []}, {"design_top": "dut; shell"},
                   {"design_sources": ["private/tb.sv"]}, {"top": "dut"},
                   {"sources": ["dut.sv", "untrusted.sv"]},
                   {"design_sources": ["../dut.sv"]}, {"design_sources": ["dut.sv", "./dut.sv"]},
                   {"private_files": {"../tb.sv": TB}}, {"pass_marker": ""}]
        for change in changes:
            with self.subTest(change=change), patch("example_iverilog.execute") as run:
                with self.assertRaises(ConfigurationError):
                    IcarusVerilog().run(self.root, {**self.config, **change}, 10)
                run.assert_not_called()

    def test_combinational_sensitivity_lists_are_not_treated_as_attributes(self):
        for sensitivity in ("@*", "@(*)", "@ ( * )"):
            with self.subTest(sensitivity=sensitivity):
                source = (f"module dut(input a,b,output reg y); always {sensitivity} y=a^b; "
                          f"always {sensitivity} begin end endmodule // $finish is only a comment\n")
                (self.root / "dut.sv").write_text(source)
                unavailable = ExecutionResult("infrastructure_error", None, 0, "", "", detail="no Yosys")
                with patch("example_iverilog.execute", return_value=unavailable) as tool:
                    result = IcarusVerilog().run(self.root, self.config, 10)
                self.assertEqual(result.status, "infrastructure_error", result)
                self.assertEqual(tool.call_args.args[0][0], "yosys")

    def test_missing_candidate_is_scored_failure_and_symlink_is_rejected(self):
        (self.root / "dut.sv").unlink()
        self.assertEqual(IcarusVerilog().run(self.root, self.config, 10).metrics["passed"], 0.0)
        (self.root / "dut.sv").symlink_to(self.root / "other.sv")
        with self.assertRaises(ConfigurationError):
            IcarusVerilog().run(self.root, self.config, 10)


@unittest.skipUnless(all(shutil.which(tool) for tool in ("yosys", "iverilog", "vvp")),
                     "Yosys/Icarus/vvp binaries not installed")
class RealRTLTests(unittest.TestCase):
    def evaluate_dut(self, source, evaluation=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "output"
        root.mkdir()
        (root / "dut.sv").write_text(source)
        return IcarusVerilog().run(root, evaluation or config(), 20)

    def test_correct_combinational_candidate_passes(self):
        result = self.evaluate_dut(CORRECT)
        self.assertEqual(result.status, "passed", result)

    def test_correct_always_comb_candidate_passes(self):
        result = self.evaluate_dut("module dut(input a,b,output reg y); always @(*) y=a^b; endmodule")
        self.assertEqual(result.status, "passed", result)

    def test_wrong_output_fails_private_vectors(self):
        result = self.evaluate_dut(WRONG)
        self.assertEqual(result.status, "failed", result)
        self.assertEqual(result.metrics["passed"], 0.0)
        self.assertIn("Mismatch", Path(result.artifacts["simulation_log"]).read_text())

    def test_candidate_print_and_finish_cannot_pass(self):
        result = self.evaluate_dut(ATTACK)
        self.assertEqual(result.status, "failed", result)
        self.assertIn("Unsupported", result.feedback)

    def test_all_shipped_tasks_check_correct_and_wrong_duts(self):
        data = json.loads((ROOT / "examples/rtl-debugger/tasks.json").read_text())
        for task, operator in zip(data["tasks"], ("^", "|", "&")):
            for correct in (False, True):
                with self.subTest(task=task["id"], correct=correct):
                    source = task["files"]["dut.sv"]
                    if correct:
                        source = source.replace("assign y = a;", f"assign y = a {operator} b;")
                    result = self.evaluate_dut(source, task["evaluation"])
                    self.assertEqual(result.status, "passed" if correct else "failed", result)

    def test_unresolved_module_is_rejected_before_private_simulation(self):
        result = self.evaluate_dut("module dut(input a,b,output y); missing u(a,b,y); endmodule")
        self.assertEqual(result.status, "failed", result)
        self.assertNotIn("simulation_log", result.artifacts)

    def test_real_private_simulation_timeout(self):
        evaluation = config()
        evaluation["private_files"]["private/tb.sv"] = '''module tb;
reg a,b;
wire y;
dut u(a,b,y);
initial begin a=0; b=0; forever #1 a=~a; end
endmodule
'''
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "output"
            root.mkdir()
            (root / "dut.sv").write_text(CORRECT)
            result = IcarusVerilog().run(root, evaluation, 1)
            self.assertEqual(result.status, "timeout", result)
            self.assertIn("simulation_log", result.artifacts)

    def test_yosys_display_is_synthesis_output_not_simulation_behavior(self):
        # Characterize the actual synthesis boundary, bypassing the toy input policy.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = WRONG.replace("endmodule", 'initial $display("TEST_PASS"); endmodule')
            (root / "dut.sv").write_text(source)
            result = execute(["yosys", "-p", "read_verilog -sv dut.sv; synth -top dut -flatten -noabc; "
                              "check -assert; write_verilog -noattr netlist.v"],
                             root, root / "synthesis_logs", 10, {"kind": "local"})
            self.assertEqual(result.returncode, 0, Path(result.stderr_path).read_text())
            self.assertIn("TEST_PASS", Path(result.stdout_path).read_text())
            self.assertNotIn("$display", (root / "netlist.v").read_text())
            (root / "tb.sv").write_text(TB)
            compiled = execute(["iverilog", "-g2012", "-s", "tb", "-o", "sim.out", "netlist.v", "tb.sv"],
                               root, root / "compile_logs", 10, {"kind": "local"})
            self.assertEqual(compiled.returncode, 0)
            simulated = execute(["vvp", "sim.out"], root, root / "simulation_logs", 10, {"kind": "local"})
            self.assertNotEqual(simulated.returncode, 0)
            self.assertNotIn("TEST_PASS", Path(simulated.stdout_path).read_text())

    def test_yosys_rejects_candidate_finish(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "dut.sv").write_text(ATTACK)
            result = execute(["yosys", "-p", "read_verilog -sv dut.sv"], root,
                             root / "logs", 10, {"kind": "local"})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("$finish", Path(result.stderr_path).read_text())


if __name__ == "__main__":
    unittest.main()
