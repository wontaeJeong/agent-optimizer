"""Opt-in CVDP dataset provider built on the existing reviewed OSS importer."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.datasets import split_families
from agent_optimizer.results import write_json
from agent_optimizer.readiness import check


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
        lock_path = cache / "evaluation-lock.json"
        if offline:
            try:
                previous = json.loads(lock_path.read_text())
            except (OSError, ValueError) as exc:
                raise UnavailableError("CVDP imported tasks provenance missing offline; rerun online preparation") from exc
            if (not isinstance(previous, dict) or not isinstance(previous.get("tasks_sha256"), str)
                    or len(previous["tasks_sha256"]) != 64):
                raise UnavailableError("CVDP imported tasks provenance missing offline; rerun online preparation")
            try:
                tasks = cache / "cvdp" / "tasks.json"
                if (tasks.is_symlink() or hashlib.sha256(tasks.read_bytes()).hexdigest() != previous["tasks_sha256"]):
                    raise UnavailableError("CVDP imported tasks changed offline; rerun online preparation")
            except OSError as exc:
                raise UnavailableError("CVDP imported tasks missing offline; rerun online preparation") from exc
        data_path, lock = setup.prepare_evaluation_environment(offline=offline, cache=cache)
        document = import_cvdp(data_path)
        output = cache / "cvdp" / "tasks.json"
        write_json(output, document)
        lock["tasks_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
        write_json(lock_path, lock)
        return {"benchmark": str(output), "evaluator": "cvdp",
                "evaluator_config": {"repo": str(ROOT / "external/cvdp_benchmark"),
                                     "python": str(ROOT / "external/cvdp-venv/bin/python"),
                                     "sim_image": lock["images"]["evaluation"]["tag"],
                                     "sim_image_id": lock["images"]["evaluation"]["id"]},
                "provenance": {"source_revision": SOURCE_REVISION,
                               "evaluation": lock, "dataset": lock.get("dataset"),
                               "sha256": document["data_sha256"],
                               "image_id": lock["images"]["evaluation"]["id"]}}

    def doctor(self, cache: Path) -> list[dict]:
        setup = _load(ROOT / "examples/ace-rtl/environment/setup.py", "agent_opt_cvdp_diagnostics")
        rows = setup.evaluation_checks(cache)
        try:
            lock = json.loads((cache / "evaluation-lock.json").read_text())
            path = cache / "cvdp" / "tasks.json"
            published = path.read_bytes() if path.is_file() and not path.is_symlink() else b""
            expected = import_cvdp(setup.ROOT / "external" / "cvdp-data" / setup.DATA_REVISION / setup.DATA_FILE)
            valid = (isinstance(lock, dict) and isinstance(lock.get("tasks_sha256"), str)
                     and bool(published) and hashlib.sha256(published).hexdigest() == lock["tasks_sha256"]
                     and json.loads(published) == expected)
        except (OSError, ValueError, KeyError, TypeError, ConfigurationError):
            valid = False
        rows.append(check("dataset.cvdp.tasks", "dataset", valid,
                          "Imported public CVDP tasks match pinned source/data and recorded digest",
                          "Rerun agent-opt datasets prepare cvdp online to restore trusted imported tasks"))
        return rows
