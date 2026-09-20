"""Portable entry points for the ACE/CVDP example; run from any working directory."""
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.results import write_json


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "doctor", "smoke", "live"])
    parser.add_argument("--offline", action="store_true", help="setup: reuse verified cached assets")
    parser.add_argument("--platform", default="linux/amd64")
    args = parser.parse_args()
    os.chdir(ROOT)
    setup = load("ace_environment", "examples/ace-rtl/environment/setup.py")
    try:
        setup.validate_platform(args.platform)
        if args.command == "live":
            setup.validate_live()  # Before image probes, data reads, or any model execution.
        if args.command == "setup":
            dataset, lock = setup.prepare_environment(offline=args.offline, platform=args.platform)
            prepare = load("ace_prepare", "examples/ace-rtl/prepare.py")
            manifest = prepare.prepare_dataset(dataset, ROOT / "datasets/ace-demo/all-tasks.json", lock)
            manifest["tasks"] = [t for t in manifest["tasks"] if t["id"] == "cvdp_copilot_16qam_mapper_0001"]
            if not manifest["tasks"]:
                raise ConfigurationError("Reviewed QAM16 live task absent from pinned dataset")
            write_json(ROOT / "datasets/ace-demo/tasks.json", manifest)
            print(json.dumps({"status": "ready", "environment_lock": "external/environment-lock.json"}))
            return 0
        lock_path = ROOT / "external/environment-lock.json"
        if not lock_path.is_file():
            raise UnavailableError("blocked_environment: run python scripts/dev.py setup first")
        lock = json.loads(lock_path.read_text())
        if lock["platform"] != args.platform:
            raise ConfigurationError("Prepared platform differs; use matching --platform")
        setup.prepare_sources(ROOT / "external", offline=True)
        setup.prepare_data(ROOT / "external", offline=True)
        capability = setup.doctor(ROOT / "external", args.platform,
                                  lock["images"]["evaluation"]["id"], lock["images"]["agent"]["id"])
        write_json(ROOT / "external/setup-logs/doctor.json", capability)
        if not capability["ready"]:
            raise UnavailableError("blocked_environment: execution doctor failed; inspect external/setup-logs/doctor.json")
        if args.command == "doctor":
            print(json.dumps(capability))
            return 0
        os.environ["DOCKER_DEFAULT_PLATFORM"] = args.platform
        os.environ["OSS_SIM_IMAGE"] = lock["images"]["evaluation"]["id"]
        example = load("ace_dev_checks", "examples/ace-rtl/environment/checks.py")
        return example.smoke(lock) if args.command == "smoke" else example.live(lock)
    except (ConfigurationError, UnavailableError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
