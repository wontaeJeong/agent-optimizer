"""Prepare Verilog-Eval v2 problem prompts without exposing its private scoring files."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.datasets import acquire_pinned_git, split_families
from agent_optimizer.results import write_json
from agent_optimizer.workspace import safe_path


SOURCE_URL = "https://github.com/NVlabs/verilog-eval.git"
REVISION = "c498220d0a52248f8e3fdffe279075215bde2da6"
MODES = ("spec-to-rtl", "code-complete-iccad2023")
RUNTIME_IMAGE = "agent-opt/iverilog-v12:4fd52916"


def prepare_runtime(*, offline: bool = False) -> dict:
    """Build a separate pinned Icarus v12 image; never accept v13 as a fallback."""
    try:
        inspect = subprocess.run(["docker", "image", "inspect", RUNTIME_IMAGE],
                                 capture_output=True, text=True, timeout=20, shell=False)
        if inspect.returncode:
            if offline:
                raise UnavailableError("Verilog-Eval v12 image is missing offline")
            dockerfile = Path(__file__).with_name("Dockerfile.iverilog12")
            build = subprocess.run(["docker", "build", "-f", str(dockerfile), "-t", RUNTIME_IMAGE,
                                    str(dockerfile.parent)], capture_output=True, text=True,
                                   timeout=1800, shell=False)
            if build.returncode:
                raise UnavailableError("Verilog-Eval Icarus v12 image build failed")
            inspect = subprocess.run(["docker", "image", "inspect", RUNTIME_IMAGE],
                                     capture_output=True, text=True, timeout=20, shell=False)
        if inspect.returncode:
            raise UnavailableError("Verilog-Eval v12 image is unavailable")
        probe = subprocess.run(["docker", "run", "--rm", "--network", "none", RUNTIME_IMAGE,
                                "iverilog", "-V"], capture_output=True, text=True, timeout=30,
                               shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UnavailableError("Cannot prepare Verilog-Eval Icarus v12 runtime") from exc
    if probe.returncode or not re.search(r"Icarus Verilog version 12\b", probe.stdout + probe.stderr):
        raise UnavailableError("Verilog-Eval image does not contain Icarus v12")
    return {"runtime": {"kind": "docker", "image": RUNTIME_IMAGE},
            "image_id": json.loads(inspect.stdout)[0]["Id"]}


def import_verilog_eval(tree: Path, mode: str) -> dict:
    if mode not in MODES:
        raise ConfigurationError(f"Unsupported Verilog-Eval task mode: {mode}")
    directory = safe_path(tree, "dataset_" + mode)
    if not directory.is_dir():
        raise ConfigurationError(f"Missing Verilog-Eval dataset_{mode} directory")
    prompts = sorted(directory.glob("*_prompt.txt"))
    families = [path.name.removesuffix("_prompt.txt") for path in prompts]
    splits = split_families(families)
    tasks = []
    for stem in families:
        prompt = safe_path(directory, stem + "_prompt.txt").read_text(encoding="utf-8")
        for suffix in ("_test.sv", "_ref.sv"):
            if not safe_path(directory, stem + suffix).is_file():
                raise ConfigurationError(f"Missing private Verilog-Eval asset for {stem}")
        if mode == "code-complete-iccad2023":
            interface = safe_path(directory, stem + "_ifc.txt").read_text(encoding="utf-8")
            prompt += "\nKeep this module interface:\n" + interface
        tasks.append({"id": stem, "family": stem, "split": splits[stem],
                      "prompt": prompt, "files": {"solution.sv": ""},
                      "evaluation": {"problem_id": stem, "mode": mode}})
    return {"schema_version": 1, "synthetic": False, "id": f"verilog-eval-v2-{mode}",
            "source_revision": REVISION, "tasks": tasks}


class Provider:
    mode = "spec-to-rtl"

    def __init__(self, *, url: str = SOURCE_URL, revision: str = REVISION):
        self.url = url
        self.revision = revision

    def describe(self) -> dict:
        return {"name": "verilog-eval-" + self.mode, "task_form": self.mode,
                "evaluator": "verilog_eval", "revision": self.revision}

    def prepare(self, cache: Path, *, offline: bool = False) -> dict:
        source = acquire_pinned_git(cache / "source" / self.revision, self.url,
                                    self.revision, offline=offline)
        runtime = prepare_runtime(offline=offline)
        document = import_verilog_eval(source, self.mode)
        document["source_revision"] = self.revision
        for task in document["tasks"]:
            task["evaluation"]["source_dir"] = str(source)
        output = cache / ("verilog-eval-" + self.mode) / "tasks.json"
        write_json(output, document)
        return {"benchmark": str(output),
                "evaluator": "verilog_eval",
                "evaluation_runtime": runtime["runtime"],
                "evaluator_config": {"image_id": runtime["image_id"]},
                "provenance": {"url": self.url, "revision": self.revision,
                               "mode": self.mode, "image_id": runtime["image_id"]}}


class CompletionProvider(Provider):
    mode = "code-complete-iccad2023"
