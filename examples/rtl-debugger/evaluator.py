from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, Task


class SimulationEvaluator:
    def __init__(self, simulator):
        self.simulator = simulator

    def validate_benchmark(self, tasks, metadata):
        for task in tasks:
            if task.required_simulator and task.required_simulator != self.simulator.id:
                raise ConfigurationError(f"Task {task.id} requires {task.required_simulator}")
            self.simulator.validate_config(task.evaluation)

    def evaluate(self, task: Task, output_dir: Path, timeout_seconds: float):
        # The simulator prepares DUT-only synthesis before materializing private files.
        return self.simulator.run(output_dir, task.evaluation, timeout_seconds)


def create(config):
    import importlib.util
    path = Path(__file__).with_name("iverilog.py")
    spec = importlib.util.spec_from_file_location("rtl_example_iverilog", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return SimulationEvaluator(module.IcarusVerilog(config))
