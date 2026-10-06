import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from agent_optimizer.config import load_agent
from agent_optimizer.sources import materialize_agent
from agent_optimizer.registry import Registry
ROOT = Path(__file__).resolve().parents[1]
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value
IcarusVerilog = module("example_iverilog", ROOT / "examples/rtl-debugger/iverilog.py").IcarusVerilog

def test_project():
    temporary = tempfile.TemporaryDirectory(prefix="agent-opt-tests-")
    environment = patch.dict(os.environ, {"AGENT_OPT_HOME": str(Path(temporary.name) / "home")})
    environment.start()
    cleanup = temporary.cleanup
    def isolated_cleanup():
        environment.stop()
        cleanup()
    temporary.cleanup = isolated_cleanup
    project = Path(temporary.name) / "project"
    shutil.copytree(ROOT / "examples", project / "examples", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "experiments/sample-team", project / "experiments/sample-team",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(ROOT / "pyproject.toml", project / "pyproject.toml")
    shutil.copyfile(ROOT / ".agent-opt-source", project / ".agent-opt-source")
    return temporary, project

def resolved_agent(path, snapshot):
    return materialize_agent(load_agent(path), snapshot)[0]

def demo_registry():
    registry = Registry()
    return registry

async def choose_row(app, pilot, identifier):
    from textual.widgets import OptionList
    app.query_one(OptionList).highlighted = next(i for i, row in enumerate(app.rows)
                                                if row.id == identifier)
    await pilot.press("enter")

async def legacy_model_page(app, pilot):
    for identifier in ("new", "ace-rtl", "ace-opencode", "gepa", "cvdp"):
        await choose_row(app, pilot, identifier)
