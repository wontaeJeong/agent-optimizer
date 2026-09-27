"""Small command adapter for explicit model configuration/transport failures."""

import json
from pathlib import Path

from agent_optimizer.harnesses.command import CommandHarness


class ModelRTLCommand(CommandHarness):
    def run(self, request):
        result = super().run(request)
        if result.status != "process_error" or result.returncode != 2:
            return result
        try:
            with Path(result.stdout_path).open(encoding="utf-8") as stream:
                raw = stream.read(4097)
            if len(raw) > 4096 or json.loads(raw) != {"status": "model_unavailable"}:
                return result
        except (OSError, UnicodeError, ValueError):
            return result
        result.status = "infrastructure_error"
        result.detail = "Agent model configuration or request unavailable"
        return result
