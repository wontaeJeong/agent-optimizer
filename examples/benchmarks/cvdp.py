"""Opt-in CVDP dataset provider built on the existing reviewed OSS importer."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.datasets import split_families
from agent_optimizer.results import write_json


ROOT = Path(__file__).resolve().parents[2]
SOURCE_REVISION = "8e894cf74414ab1eaea1e2b4e80a02f123df07b6"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ConfigurationError(f"Cannot load reviewed CVDP helper: {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def import_cvdp(path: Path) -> dict:
    if "no_commercial" not in path.name:
        raise ConfigurationError("Only reviewed no_commercial CVDP tasks can be imported")
    raw = path.read_bytes()
    importer = _load(ROOT / "examples/ace-rtl/prepare.py", "agent_opt_cvdp_importer")
    tasks, excluded = importer.convert([json.loads(line) for line in raw.decode().splitlines()
                                        if line.strip()])
    if not tasks:
        raise ConfigurationError("CVDP has no supported OSS tasks")
    splits = split_families([task["family"] for task in tasks])
    for task in tasks:
        task["split"] = splits[task["family"]]
    return {"schema_version": 1, "synthetic": False, "id": "cvdp-reviewed-no-commercial",
            "source_revision": SOURCE_REVISION, "data_sha256": hashlib.sha256(raw).hexdigest(),
            "excluded": excluded, "tasks": tasks}


class Provider:
    def describe(self) -> dict:
        return {"name": "cvdp", "task_form": "rtl-generation", "evaluator": "cvdp",
                "revision": SOURCE_REVISION}

    def prepare(self, cache: Path, *, offline: bool = False) -> dict:
        setup = _load(ROOT / "examples/ace-rtl/environment/setup.py", "agent_opt_cvdp_setup")
        data_path, lock = setup.prepare_environment(offline=offline)
        document = import_cvdp(data_path)
        output = cache / "cvdp" / "tasks.json"
        write_json(output, document)
        return {"benchmark": str(output), "evaluator": "examples/ace-rtl/evaluator.py:CVDPEvaluator",
                "provenance": {"source_revision": SOURCE_REVISION,
                               "dataset": lock.get("dataset"), "sha256": document["data_sha256"]}}
