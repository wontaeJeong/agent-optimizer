"""Generate the declared public RTL target with the configured model."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.models import ModelSettings, complete
from agent_optimizer.workspace import safe_path


def main():
    task_dir = Path(sys.argv[1])
    request = json.loads((Path.cwd() / "request.json").read_text(encoding="utf-8"))
    prompt = request["prompt"]
    match = re.search(r"\nWrite target files: ([^\n]+)\nTask files are in \./task\. Modify only task outputs\.\Z",
                      prompt)
    if match is None:
        raise ConfigurationError("Missing public RTL target declaration")
    targets = [item.strip() for item in match.group(1).split(",")]
    if len(targets) != 1:
        raise ConfigurationError("This small Agent requires one public RTL target per task")
    target = targets[0]
    if (not re.fullmatch(r"rtl/[A-Za-z0-9_./-]+\.(?:v|sv)", target)
            or any(part in {"", ".", ".."} for part in target.split("/"))):
        raise ConfigurationError("Declared public RTL target is invalid")
    output = safe_path(task_dir, target)
    if not output.is_file():
        raise ConfigurationError("Declared public RTL target is missing")

    source = Path(__file__)
    system_prompt = (source.parent.parent / "prompts/system.md").read_text(encoding="utf-8")
    agent_env = {"AGENT_OPT_MODEL_BASE_URL": os.environ.get("DEMO_AGENT_MODEL_BASE_URL", ""),
                 "AGENT_OPT_MODEL_ID": os.environ.get("DEMO_AGENT_MODEL_ID", ""),
                 "AGENT_OPT_MODEL_API_KEY": os.environ.get("DEMO_AGENT_MODEL_API_KEY", "")}
    try:
        settings = ModelSettings.from_env(agent_env)
        reply = complete([{"role": "system", "content": system_prompt},
                          {"role": "user", "content": prompt}], settings=settings, timeout=60)
        text = reply["choices"][0]["message"].get("content")
        if not isinstance(text, str) or not text.strip():
            raise UnavailableError("Model did not return RTL text")
    except (ConfigurationError, UnavailableError):
        print(json.dumps({"status": "model_unavailable"}))
        raise SystemExit(2) from None
    output.write_text(text, encoding="utf-8")
    agent_file_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    print(json.dumps({"agent_sha256": agent_file_sha256, "agent_file_sha256": agent_file_sha256,
                       "target": target, "model": settings.model}))


if __name__ == "__main__":
    main()
