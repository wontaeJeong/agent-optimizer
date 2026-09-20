"""Add network settings to a private submission, then execute the pinned driver.

Runs in the existing CVDP Python environment, which already provides PyYAML.
Only Compose environment/build arguments/CA mounts change, never checker code.
"""
import json
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.network import network_environment, PROXY_NAMES, CA_VARIABLES, CONTAINER_CA, SYSTEM_CA


def mapping(value):
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return {v.partition("=")[0]: v.partition("=")[2] if "=" in v else None for v in value}
    raise ConfigurationError("Unsupported Compose environment/build arguments")


def configure_compose(data, environment):
    settings = network_environment(environment)
    proxies = {key: None for key in settings if key.upper() in PROXY_NAMES}
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict):
        raise ConfigurationError("Private Compose file has no services")
    for service in data["services"].values():
        env = mapping(service.get("environment", {}))
        env.update(proxies)
        if bundle := settings.get("AGENT_OPT_CA_BUNDLE"):
            env.update({key: CONTAINER_CA for key in CA_VARIABLES})
            volumes = service.setdefault("volumes", [])
            for target in (CONTAINER_CA, SYSTEM_CA):
                # A dollar sign in a bind path must survive Compose interpolation.
                volumes.append({"type": "bind", "source": bundle.replace("$", "$$"),
                                "target": target, "read_only": True,
                                "bind": {"create_host_path": False}})
        service["environment"] = env
        if "build" in service:
            build = service["build"]
            if isinstance(build, str):
                build = {"context": build}
                service["build"] = build
            args = mapping(build.get("args", {}))
            args.update(proxies)
            build["args"] = args


def configure_submission(path, environment):
    import yaml
    rows = []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        files = row["harness"]["files"]
        compose = yaml.safe_load(files["docker-compose.yml"])
        configure_compose(compose, environment)
        files["docker-compose.yml"] = yaml.safe_dump(compose, sort_keys=False)
        rows.append(row)
    destination = path.with_name("network-submission.jsonl")
    destination.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return destination


def main():
    import os
    script, *args = sys.argv[1:]
    index = args.index("-f") + 1
    args[index] = str(configure_submission(Path(args[index]), os.environ))
    sys.argv = [script, *args]
    sys.path.insert(0, str(Path(script).parent))
    runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
