"""Prepare Verilog-Eval v2 problem prompts without exposing its private scoring files."""
from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
from pathlib import Path

from agent_optimizer import diagnostics
from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.datasets import acquire_pinned_git, split_families
from agent_optimizer.results import write_json
from agent_optimizer.readiness import check
from agent_optimizer.workspace import safe_path
from agent_optimizer.network import configured_build


SOURCE_URL = "https://github.com/NVlabs/verilog-eval.git"
REVISION = "c498220d0a52248f8e3fdffe279075215bde2da6"
MODES = ("spec-to-rtl", "code-complete-iccad2023")
RUNTIME_IMAGE = "agent-opt/iverilog-v12:4fd52916"
IVERILOG_REVISION = "4fd5291632232fbe1ba49b2c26bb6b2bf1c6c9cf"


def _build_identity() -> dict:
    dockerfile = Path(__file__).with_name("Dockerfile.iverilog12")
    content = dockerfile.read_bytes()
    if not re.search(rb"git checkout --detach " + IVERILOG_REVISION.encode() + rb"(?:\s|$)", content):
        raise ConfigurationError("Verilog-Eval Dockerfile does not pin the reviewed Icarus source")
    return {"image": RUNTIME_IMAGE, "source_revision": IVERILOG_REVISION,
            "dockerfile_sha256": hashlib.sha256(content).hexdigest()}


def _verified_lock(cache: Path, image_id: str) -> bool:
    try:
        lock = json.loads((cache / "runtime-lock.json").read_text())
        return (isinstance(lock, dict) and lock == {**_build_identity(), "image_id": image_id}
                and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)))
    except (OSError, ValueError, ConfigurationError):
        return False


def _runtime_failure(stage: str, cause: str, *, log: Path | None, retry: str, fix: str):
    error = UnavailableError(cause)
    error.failure_diagnostic = {"stage": stage, "cause": cause,
                                "log": str(log) if log is not None else None,
                                "fix": fix, "retry": retry}
    return error


def _runtime_outcome(command: str, exception: BaseException) -> diagnostics.CommandOutcome:
    timeout = isinstance(exception, subprocess.TimeoutExpired)
    return diagnostics.CommandOutcome(
        command,
        exception.returncode if isinstance(exception, subprocess.CalledProcessError) else None,
        str(getattr(exception, "output", "") or ""),
        str(getattr(exception, "stderr", "") or ""),
        timed_out=timeout,
        error_kind=("missing" if isinstance(exception, FileNotFoundError) else
                    "permission" if isinstance(exception, PermissionError) else
                    "timeout" if timeout else type(exception).__name__.lower()),
    )


def prepare_runtime(cache: Path | None = None, *, offline: bool = False,
                    retry: str = "agent-opt datasets prepare verilog-spec") -> dict:
    """Build a separate pinned Icarus v12 image; never accept v13 as a fallback."""
    cache = Path(cache) if cache is not None else Path(__file__).resolve().parents[2] / "external/datasets/verilog-runtime"
    identity = _build_identity()
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        inspect = subprocess.run(["docker", "image", "inspect", RUNTIME_IMAGE],
                                 capture_output=True, text=True, timeout=20, shell=False,
                                 env=environment)
        try:
            image_id = json.loads(inspect.stdout)[0]["Id"] if not inspect.returncode else None
        except (ValueError, TypeError, IndexError, KeyError):
            image_id = None
        built = False
        if not image_id or not _verified_lock(cache, image_id):
            if offline:
                raise _runtime_failure(
                    "Verilog-Eval image cache", "offline cache miss: pinned Icarus v12 image is missing or unverified",
                    log=None, retry=retry,
                    fix="Prepare and verify the pinned Icarus v12 image while online before offline use.",
                ) from None
            dockerfile = Path(__file__).with_name("Dockerfile.iverilog12")
            log = cache / "setup-logs" / "verilog-eval-image-build.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            argv = ["docker", "build", "-f", str(dockerfile), "-t", RUNTIME_IMAGE,
                    str(dockerfile.parent)]
            with log.open("w", encoding="utf-8") as stream:
                stream.write(json.dumps(argv) + "\n")
                stream.flush()
                with configured_build(argv, dockerfile.parent, environment) as command:
                    build = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                           timeout=1800, shell=False, env=environment)
                    if build.returncode:
                        stream.flush()
                        lines = diagnostics.summarize_log(log, environment=environment)
                        details = diagnostics.CommandOutcome(
                            "docker build", build.returncode,
                            str(getattr(build, "stdout", "") or ""),
                            "\n".join(lines) if lines else str(getattr(build, "stderr", "") or ""),
                        )
                        cause = diagnostics.summarize_failure(details, environment=environment)
                        raise _runtime_failure(
                            "Verilog-Eval evaluation image build", cause, log=log, retry=retry,
                            fix="Check Docker build trust/registry access and preserve the pinned Dockerfile.",
                        ) from None
            inspect = subprocess.run(["docker", "image", "inspect", RUNTIME_IMAGE],
                                      capture_output=True, text=True, timeout=20, shell=False,
                                      env=environment)
            built = True
        if inspect.returncode:
            outcome = diagnostics.CommandOutcome("docker image inspect", inspect.returncode,
                                                 inspect.stdout or "", inspect.stderr or "")
            raise _runtime_failure(
                "Verilog-Eval image inspection",
                diagnostics.summarize_failure(outcome, environment=environment),
                log=cache / "setup-logs" / "verilog-eval-image-build.log" if built else None,
                retry=retry, fix="Check Docker daemon access and restore the pinned Icarus v12 image.",
            ) from None
        try:
            image_id = json.loads(inspect.stdout)[0]["Id"]
            if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
                raise ValueError("Invalid image ID")
        except (ValueError, TypeError, IndexError, KeyError) as exc:
            raise _runtime_failure(
                "Verilog-Eval image inspection", diagnostics.summarize_exception(exc, environment=environment),
                log=cache / "setup-logs" / "verilog-eval-image-build.log" if built else None,
                retry=retry, fix="Restore the pinned Icarus v12 image identity.",
            ) from None
        probe = subprocess.run(["docker", "run", "--rm", "--network", "none", RUNTIME_IMAGE,
                                "iverilog", "-V"], capture_output=True, text=True, timeout=30,
                               shell=False, env=environment)
    except (OSError, subprocess.TimeoutExpired) as exc:
        outcome = _runtime_outcome("docker", exc)
        raise _runtime_failure(
            "Verilog-Eval Icarus v12 runtime", diagnostics.summarize_failure(outcome, environment=environment),
            log=None, retry=retry, fix="Check Docker daemon access and the pinned Icarus v12 runtime.",
        ) from None
    if probe.returncode or not re.search(r"Icarus Verilog version 12\b", probe.stdout + probe.stderr):
        cause = (diagnostics.summarize_failure(
            diagnostics.CommandOutcome("docker run iverilog", probe.returncode,
                                       probe.stdout or "", probe.stderr or ""),
            environment=environment) if probe.returncode else
            "pinned evaluation image does not contain Icarus v12")
        raise _runtime_failure(
            "Verilog-Eval simulator verification", cause,
            log=cache / "setup-logs" / "verilog-eval-image-build.log" if built else None,
            retry=retry, fix="Rebuild and verify the pinned Icarus v12 image.",
        ) from None
    if built:
        write_json(cache / "runtime-lock.json", {**identity, "image_id": image_id})
    return {"runtime": {"kind": "docker", "image": RUNTIME_IMAGE},
            "image_id": image_id}


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
        suffix = "spec" if self.mode == MODES[0] else "completion"
        retry = f"agent-opt datasets prepare verilog-{suffix}"
        try:
            source = acquire_pinned_git(cache / "source" / self.revision, self.url,
                                        self.revision, offline=offline)
        except (ConfigurationError, UnavailableError, OSError) as exc:
            diagnostic = getattr(exc, "failure_diagnostic", None)
            if not isinstance(diagnostic, dict):
                diagnostic = {
                    "stage": "Verilog-Eval source checkout",
                    "cause": diagnostics.summarize_exception(exc),
                    "log": None,
                    "fix": "Check the pinned source checkout and preserve local changes.",
                }
            exc.failure_diagnostic = {**diagnostic, "retry": retry}
            raise
        runtime = prepare_runtime(cache, offline=offline,
                                  retry=retry)
        document = import_verilog_eval(source, self.mode)
        document["source_revision"] = self.revision
        for task in document["tasks"]:
            task["evaluation"]["source_dir"] = str(source)
        output = cache / ("verilog-eval-" + self.mode) / "tasks.json"
        write_json(output, document)
        write_json(output.with_name("provenance.json"), {"url": self.url, "revision": self.revision,
                   "mode": self.mode, "image": runtime["runtime"]["image"],
                   "image_id": runtime["image_id"], **_build_identity()})
        return {"benchmark": str(output),
                "evaluator": "verilog_eval",
                "evaluation_runtime": runtime["runtime"],
                "evaluator_config": {"image_id": runtime["image_id"]},
                "provenance": {"url": self.url, "revision": self.revision,
                               "mode": self.mode, "image_id": runtime["image_id"]}}

    def doctor(self, cache: Path) -> list[dict]:
        cache = Path(cache)
        source = cache / "source" / self.revision
        folder = cache / ("verilog-eval-" + self.mode)
        suffix = "spec" if self.mode == MODES[0] else "completion"
        retry = f"agent-opt datasets prepare verilog-{suffix}"
        rows = []
        try:
            provenance = json.loads((folder / "provenance.json").read_text())
            provenance_error = None
        except (OSError, ValueError) as exc:
            provenance = None
            provenance_error = diagnostics.summarize_exception(exc)
        locked = (isinstance(provenance, dict) and provenance.get("url") == self.url
                  and provenance.get("revision") == self.revision
                  and provenance.get("mode") == self.mode
                  and provenance.get("image") == RUNTIME_IMAGE
                  and isinstance(provenance.get("image_id"), str)
                   and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", provenance["image_id"]))
                   and all(provenance.get(key) == value for key, value in _build_identity().items())
                   and _verified_lock(cache, provenance["image_id"]))
        rows.append(check("dataset.verilog.provenance", "dataset", locked,
                          "Pinned Verilog-Eval v12 preparation provenance",
                          "Run " + retry,
                          cause=None if locked else provenance_error or
                          "Verilog-Eval runtime provenance is missing or differs from its pinned inputs",
                          retry=retry))

        def probe(argv, *, cwd=None):
            try:
                result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=30, shell=False,
                                        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "PYTHONDONTWRITEBYTECODE": "1"})
                output = result.stdout.strip() if result.returncode == 0 else None
                cause = (None if result.returncode == 0 else diagnostics.summarize_failure(
                    diagnostics.CommandOutcome(" ".join(argv[:2]), result.returncode,
                                               result.stdout or "", result.stderr or ""),
                    environment=os.environ))
                return output, cause
            except (OSError, subprocess.TimeoutExpired) as exc:
                return None, diagnostics.summarize_failure(
                    _runtime_outcome(" ".join(argv[:2]), exc), environment=os.environ)

        source_exists = (source / ".git").exists()
        head, head_error = probe(["git", "rev-parse", "HEAD"], cwd=source) \
            if source_exists else (None, None)
        dirty, dirty_error = probe(["git", "status", "--porcelain", "--untracked-files=all"], cwd=source) \
            if source_exists and head == self.revision else (None, None)
        pinned = source_exists and head == self.revision and dirty == ""
        source_cause = (None if pinned else head_error or dirty_error or
                        "pinned clean Verilog-Eval source is missing, changed, or dirty")
        rows.append(check("dataset.verilog.source", "dataset", pinned, "Pinned clean Verilog-Eval checkout",
                          "Install Git, preserve local changes and rerun dataset preparation",
                          cause=source_cause, retry=retry))
        task_cause = None
        try:
            document = import_verilog_eval(source, self.mode)
            if document is not None:
                document["source_revision"] = self.revision
                for task in document["tasks"]:
                    task["evaluation"]["source_dir"] = str(source)
            published = json.loads((folder / "tasks.json").read_text())
            complete = bool(document and document["tasks"] and document == published)
        except (OSError, ValueError, ConfigurationError, TypeError, KeyError) as exc:
            complete = False
            task_cause = diagnostics.summarize_exception(exc)
        rows.append(check("dataset.verilog.tasks", "dataset", complete,
                          "Imported public tasks and private test/reference assets are complete",
                          "Restore the pinned private task files and rerun dataset preparation",
                          cause=None if complete else task_cause or
                          "imported task file is missing or differs from the pinned source",
                          retry=retry))
        info = None
        image_error = None
        if locked:
            try:
                output, image_error = probe(["docker", "image", "inspect", RUNTIME_IMAGE])
                info = json.loads(output)[0] if output is not None else None
            except (ValueError, TypeError, IndexError, KeyError):
                image_error = "docker image inspect returned invalid image metadata"
        image_ok = (locked and isinstance(info, dict) and info.get("Id") == provenance["image_id"])
        rows.append(check("dataset.verilog.image", "dataset", image_ok,
                          "Prepared immutable Icarus v12 image identity",
                          "Start Docker and rerun dataset preparation to verify the Icarus v12 image",
                          cause=None if image_ok else image_error or
                          "prepared Icarus v12 image identity is missing or differs from provenance",
                          retry=retry))
        return rows


class CompletionProvider(Provider):
    mode = "code-complete-iccad2023"
