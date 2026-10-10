from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from agent_optimizer.contracts import RunRequest, UnavailableError
from agent_optimizer.harnesses.command import CommandHarness
from agent_optimizer.locale import opencode_error_detail

_SAFE_ENDPOINT_SEGMENTS = {
    "api", "openai", "compatible", "chat", "completions", "responses", "embeddings",
    "messages", "models", "generate", "inference", "rerank", "moderations", "audio", "images",
}


def _safe_endpoint(value):
    if not isinstance(value, str):
        return None, False
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None, False
        port = parsed.port
    except ValueError:
        return None, False
    host = parsed.hostname.lower()
    if port is not None:
        host += f":{port}"
    path = parsed.path or "/"
    missing_openai_version = parsed.hostname.lower() == "api.openai.com" and path == "/chat/completions"
    secret_values = [value for name, value in os.environ.items()
                     if value and any(marker in name.upper() for marker in ("KEY", "TOKEN", "SECRET", "AUTH"))]
    safe_segments = []
    for segment in path.split("/"):
        decoded = unquote(segment)
        known_route = (decoded.lower() in _SAFE_ENDPOINT_SEGMENTS
                       or re.fullmatch(r"v\d+(?:beta\d*)?", decoded, flags=re.IGNORECASE))
        contains_credential = any(secret in decoded for secret in secret_values)
        safe_segments.append(decoded if not contains_credential and (known_route or not decoded)
                             else "[비공개]")
    path = "/".join(safe_segments)
    endpoint = host + path
    if len(endpoint) > 512 or any(ord(char) < 32 for char in endpoint):
        return None, False
    return endpoint, missing_openai_version


def _error_detail(event):
    error = event.get("error")
    data = error.get("data") if isinstance(error, dict) else None
    data = data if isinstance(data, dict) else {}
    status = data.get("statusCode", error.get("statusCode") if isinstance(error, dict) else None)
    if type(status) is not int or not 100 <= status <= 599:
        status = None
    metadata = data.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    endpoint, missing_openai_version = _safe_endpoint(metadata.get("url"))
    return opencode_error_detail(status, endpoint, missing_openai_version=missing_openai_version)


class OpenCodeHarness(CommandHarness):
    def argv(self, request: RunRequest) -> list[str]:
        model_env = request.profile.get("model_env", "AGENT_OPT_MODEL")
        model = os.environ.get(model_env)
        if not model:
            raise UnavailableError(f"Set {model_env} to a provider/model identifier")
        command = ["opencode", "run", "--format", "json", "--model", model]
        if request.profile.get("agent"):
            command += ["--agent", request.profile["agent"]]
        command += [request.prompt]
        return command

    def run(self, request: RunRequest):
        result = super().run(request)
        reported_tokens = 0
        reported_cost = 0.0
        saw_tokens = saw_cost = False
        invalid = 0
        with Path(result.stdout_path).open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    invalid += 1
                    continue
                if not isinstance(event, dict):
                    invalid += 1
                    continue
                if event.get("type") == "error":
                    result.status = "infrastructure_error"
                    result.detail = _error_detail(event)
                if event.get("type") == "step_finish":
                    part = event.get("part", {})
                    if not isinstance(part, dict):
                        invalid += 1
                        continue
                    tokens = part.get("tokens", {})
                    tokens = tokens if isinstance(tokens, dict) else {}
                    # Keep this explicitly partial: child sessions may not be in this stream.
                    if all(type(tokens.get(k)) is int and tokens[k] >= 0 for k in ("input", "output")):
                        reported_tokens += tokens["input"] + tokens["output"]
                        saw_tokens = True
                    cost = part.get('cost')
                    try:
                        valid_cost = type(cost) in (int, float) and math.isfinite(cost) and cost >= 0
                    except OverflowError:
                        valid_cost = False
                    if valid_cost:
                        reported_cost += cost
                        saw_cost = True
        try:
            finite_tokens = math.isfinite(reported_tokens)
        except OverflowError:
            finite_tokens = False
        result.metrics.update(harness_reported_io_tokens=reported_tokens if saw_tokens and finite_tokens else None,
                              harness_reported_cost_usd=reported_cost if saw_cost and math.isfinite(reported_cost) else None,
                              unparsed_event_lines=float(invalid))
        # Complete agent totals intentionally remain unavailable until child-session accounting
        # is verified for a pinned OpenCode version. Never report a partial total as complete.
        return result
