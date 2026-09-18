"""Import public task inputs; retain evaluator assets outside Agent mounts."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from agent_optimizer.workspace import safe_path
from agent_optimizer.results import write_json

COMMERCIAL = re.compile(r"\b(xcelium|xrun|irun|imc|vcs|questa|modelsim|vsim|cadence|synopsys)\b|__VERIF_EDA_IMAGE__|LICENSE_NETWORK", re.I)
# Reviewed initial demo category: binary functional RTL generation, not coverage/PPA.
ALLOWED_CATEGORIES = {"cid003"}

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
        dockerfiles = [v for k, v in harness.items() if Path(k).name.startswith("Dockerfile")]
        if not dockerfiles or any(not re.search(r"^FROM __OSS_SIM_IMAGE__\s*$", d, re.M) for d in dockerfiles):
            reason = "unreviewed simulation image"
        targets = list(row.get("output", {}).get("context", {}))
        if not targets or any(not p.startswith("rtl/") for p in targets):
            reason = "only explicit RTL output targets supported in this demo"
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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("datasets/ace-demo/tasks.json"))
    args = parser.parse_args()
    if "no_commercial" not in args.dataset.name:
        parser.error("Use an official no_commercial dataset")
    raw = args.dataset.read_bytes()
    tasks, excluded = convert([json.loads(line) for line in raw.decode().splitlines() if line.strip()])
    write_json(args.output.with_suffix(".excluded.json"), excluded)
    if not tasks:
        parser.error("No supported OSS functional tasks; inspect exclusion report")
    write_json(args.output, {"schema_version": 1, "synthetic": False, "source": str(args.dataset),
                           "source_sha256": hashlib.sha256(raw).hexdigest(),
                           "environment": json.loads(Path("external/environment-lock.json").read_text()) if Path("external/environment-lock.json").exists() else None,
                           "tasks": tasks})
    print(f"Prepared {len(tasks)} tasks; excluded {len(excluded)}. Validation-only smoke, not a held-out benchmark.")

if __name__ == "__main__":
    main()
