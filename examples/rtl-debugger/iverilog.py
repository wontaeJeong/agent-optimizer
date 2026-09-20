import re
import tempfile
import time
from pathlib import Path, PurePosixPath

from agent_optimizer.contracts import ConfigurationError, Evaluation
from agent_optimizer.process import execute
from agent_optimizer.workspace import safe_path


class IcarusVerilog:
    """Limited synthesizable RTL scorer, not an arbitrary Verilog sandbox."""
    id = "iverilog"

    def __init__(self, runtime: dict | None = None):
        self.runtime = runtime or {"kind": "local"}

    @staticmethod
    def validate_config(config: dict):
        for key in ("sources", "design_sources"):
            values = config.get(key)
            if not isinstance(values, list) or not values or not all(isinstance(v, str) for v in values):
                raise ConfigurationError(f"RTL evaluation requires nonempty {key}")
            if len(set(values)) != len(values):
                raise ConfigurationError(f"Duplicate RTL {key}")
        private = config.get("private_files")
        if not isinstance(private, dict) or not private or not all(isinstance(v, str) for v in private.values()):
            raise ConfigurationError("RTL evaluation requires private_files testbench text")
        for path in [*config["sources"], *config["design_sources"], *private]:
            if not isinstance(path, str) or PurePosixPath(path).as_posix() != path or path == ".":
                raise ConfigurationError(f"Noncanonical RTL path: {path!r}")
            safe_path(Path("/rtl-schema-validation"), path)
        design = set(config["design_sources"])
        if design & private.keys() or set(config["sources"]) != design | private.keys():
            raise ConfigurationError("sources must contain exactly disjoint design_sources and private_files")
        for key in ("design_top", "top"):
            if not isinstance(config.get(key), str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", config[key]):
                raise ConfigurationError(f"RTL evaluation requires a simple {key} module name")
        if config["design_top"] == config["top"]:
            raise ConfigurationError("DUT and private testbench tops must differ")
        marker = config.get("pass_marker", "TEST_PASS")
        if not isinstance(marker, str) or not marker.strip() or marker.splitlines() != [marker]:
            raise ConfigurationError("pass_marker must be a nonempty single line")

    def run(self, workspace: Path, config: dict, timeout_seconds: float) -> Evaluation:
        deadline = time.monotonic() + timeout_seconds
        self.validate_config(config)
        safe_path(workspace, ".")
        inputs = []
        for source in config["design_sources"]:
            path = safe_path(workspace, source)
            if not path.is_file():
                return Evaluation("failed", {"passed": 0.0}, f"Missing source: {source}")
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return Evaluation("failed", {"passed": 0.0}, f"Unsupported non-UTF-8 RTL: {source}")
            # Reject common simulation-only/externally loaded constructs rather than
            # silently accepting Yosys' synthesis-time interpretation or ignored code.
            code = re.sub(r"//[^\n]*|/\*.*?\*/", " ", text, flags=re.DOTALL)
            code = re.sub(r"@\s*\(\s*\*\s*\)", "@*", code)
            if (re.search(r'[$`#"\\]|\(\*|\b(initial|final|specify|force|release|assert|assume|cover)\b', code)
                    or re.search(r"\btranslate_(off|on)\b", text)):
                return Evaluation("failed", {"passed": 0.0},
                                  f"Unsupported construct in limited synthesizable RTL: {source}")
            inputs.append(text)

        # Fresh siblings of candidate output; each execute/Docker mount sees only
        # its phase. Retain logs/netlist beside the trial for result artifacts.
        root = Path(tempfile.mkdtemp(prefix="rtl-evaluation-", dir=workspace.parent))
        design, simulation = root / "design", root / "simulation"
        design.mkdir()
        sources = []
        for index, text in enumerate(inputs):
            name = f"design_{index}.sv"
            (design / name).write_text(text, encoding="utf-8")
            sources.append(name)
        script = (f"read_verilog -sv -noautowire {' '.join(sources)}; "
                  f"synth -top {config['design_top']} -flatten -noabc; "
                  "check -assert; write_verilog -noattr netlist.v")
        private_sources = [name for name in config["sources"] if name in config["private_files"]]
        phases = [
            ("synthesis", design, ["yosys", "-p", script]),
            ("compile", simulation, ["iverilog", "-g2012", "-s", config["top"], "-o", "sim.out",
                                     "netlist.v", *[f"private/{name}" for name in private_sources]]),
            ("simulation", simulation, ["vvp", "sim.out"]),
        ]
        artifacts = {}
        for phase, cwd, argv in phases:
            if time.monotonic() >= deadline:
                return Evaluation("timeout", {"passed": 0.0}, f"Budget exhausted before {phase}", artifacts)
            if phase == "compile":
                netlist = safe_path(design, "netlist.v")
                if not netlist.is_file() or not netlist.stat().st_size:
                    return Evaluation("infrastructure_error", {"passed": None},
                                      "Yosys completed without a netlist", artifacts)
                simulation.mkdir()
                (simulation / "netlist.v").write_bytes(netlist.read_bytes())
                artifacts["netlist"] = str(simulation / "netlist.v")
                # Only now materialize the trusted testbench. Never compile original RTL.
                for name, text in config["private_files"].items():
                    dest = safe_path(simulation, f"private/{name}")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(text, encoding="utf-8")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return Evaluation("timeout", {"passed": 0.0}, f"Budget exhausted before {phase}", artifacts)
            result = execute(argv, cwd, cwd / f"{phase}_logs", remaining, self.runtime)
            for suffix, path in (("log", result.stdout_path), ("stderr", result.stderr_path)):
                if path:
                    artifacts[f"{phase}_{suffix}"] = path
            if result.status == "infrastructure_error":
                return Evaluation("infrastructure_error", {"passed": None},
                                  f"{phase}: {result.detail or result.status}", artifacts)
            if result.status == "timeout" or time.monotonic() >= deadline:
                return Evaluation("timeout", {"passed": 0.0}, f"{phase} timeout", artifacts)
            if result.status != "completed" or result.returncode != 0:
                return Evaluation("failed", {"passed": 0.0}, f"{phase} failed", artifacts)
        output = Path(result.stdout_path).read_text(encoding="utf-8", errors="replace")
        passed = config.get("pass_marker", "TEST_PASS") in output.splitlines()
        status = "passed" if passed else "failed"
        return Evaluation(status, {"passed": float(passed)}, f"Private Icarus simulation {status}", artifacts)
