"""Import public task inputs; retain evaluator assets outside Agent mounts."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.workspace import safe_path
from agent_optimizer.results import write_json

COMMERCIAL = re.compile(r"\b(xcelium|xrun|irun|imc|vcs|questa|modelsim|vsim|cadence|synopsys)\b|__VERIF_EDA_IMAGE__|LICENSE_NETWORK", re.I)
# Reviewed initial demo category: binary functional RTL generation, not coverage/PPA.
ALLOWED_CATEGORIES = {"cid003"}


def reviewed_targets(row, harness):
    """Use explicit outputs or literal source paths in trusted private metadata."""
    targets = list(row.get("output", {}).get("context", {}))
    if not targets:
        declarations = re.findall(r"^\s*VERILOG_SOURCES\s*=\s*([^\n]+)", harness.get("src/.env", ""), re.M)
        if len(declarations) != 1:
            return []
        sources = declarations[0].split()
        if not sources or any(not p.startswith("/code/rtl/") for p in sources):
            return []
        targets = [p.removeprefix("/code/") for p in sources]
    for target in targets:
        if not re.fullmatch(r"rtl/[A-Za-z0-9_./-]+\.(?:sv|v)", target) or any(part in {".", "..", ""} for part in target.split("/")):
            return []
    return targets


def reviewed_image(harness):
    compose = harness.get("docker-compose.yml", "")
    if not compose.strip():
        return False  # Without Compose, upstream switches to subjective/model evaluation.
    images = re.findall(r"^\s+image\s*:\s*(\S+)\s*$", compose, re.M)
    if any(i != "__OSS_SIM_IMAGE__" for i in images):
        return False
    dockerfiles = [v for k, v in harness.items() if Path(k).name.startswith("Dockerfile")]
    if dockerfiles:
        # The reviewed example builds only a trivial alias of the official image.
        return all(d.strip() == "FROM __OSS_SIM_IMAGE__" for d in dockerfiles)
    return bool(images) and all(i == "__OSS_SIM_IMAGE__" for i in images) and not re.search(r"^\s+build\s*:", compose, re.M)

def convert(rows):
    tasks, excluded = [], []
    for row in rows:
        reason = None
        harness = row.get("harness", {}).get("files", {})
        categories = set(row.get("categories", []))
        if not categories.intersection(ALLOWED_CATEGORIES):
            reason = "category not reviewed for binary functional scoring"
        if COMMERCIAL.search(json.dumps(harness)):
            reason = "commercial tool dependency"
        if not reviewed_image(harness):
            reason = "unreviewed simulation image"
        targets = reviewed_targets(row, harness)
        if not targets:
            reason = "no reviewed literal RTL targets in output/context or harness src/.env"
        if reason:
            excluded.append({"id": row.get("id"), "reason": reason})
            continue
        files = dict(row["input"].get("context", {}))
        for p in [*files, *targets]:
            safe_path(Path("/validation"), p)
        for p in targets:
            files.setdefault(p, "")
        # Never copy supplied reference solutions into task inputs or retained rows.
        clean = json.loads(json.dumps(row))
        clean["output"] = {"response": "", "context": {p: "" for p in targets}}
        tasks.append({"id": row["id"], "split": "validation", "family": row["id"],
                      "prompt": row["input"]["prompt"] + "\nWrite target files: " + ", ".join(targets),
                      "files": files, "evaluation": {"row": clean, "targets": targets}})
    return tasks, excluded


def prepare_dataset(dataset, output, environment=None):
    raw = dataset.read_bytes()
    tasks, excluded = convert([json.loads(line) for line in raw.decode().splitlines() if line.strip()])
    write_json(output.with_suffix(".excluded.json"), excluded)
    if not tasks:
        raise ConfigurationError("No supported OSS functional tasks; inspect exclusion report")
    manifest = {"schema_version": 1, "synthetic": False, "source": str(dataset),
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "environment": environment, "tasks": tasks}
    write_json(output, manifest)
    return manifest

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("datasets/ace-demo/tasks.json"))
    args = parser.parse_args()
    if "no_commercial" not in args.dataset.name:
        parser.error("Use an official no_commercial dataset")
    lock = Path("external/environment-lock.json")
    try:
        manifest = prepare_dataset(args.dataset, args.output, json.loads(lock.read_text()) if lock.exists() else None)
    except ConfigurationError as exc:
        parser.error(str(exc))
    print(f"Prepared {len(manifest['tasks'])} tasks. Validation-only import, not a held-out benchmark.")

if __name__ == "__main__":
    main()
