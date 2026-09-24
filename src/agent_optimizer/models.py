"""Small OpenAI-compatible transport shared by example optimizers and diagnostics."""
from __future__ import annotations

import json
import math
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from urllib.parse import urlsplit

from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.network import ca_bundle, network_environment


@lru_cache(maxsize=1)
def _environment_settings():
    # Developer help and core doctor import this module before project setup.
    try:
        from pydantic import SecretStr
        from pydantic_settings import BaseSettings, SettingsConfigDict
    except ImportError:
        raise UnavailableError("Model settings require the project environment; run setup --core") from None

    class EnvironmentSettings(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="AGENT_OPT_MODEL_", env_file=None)

        endpoint: str = ""
        base_url: str = ""
        id: str = "glm5.3-flash"
        api_key: SecretStr = SecretStr("")

    return EnvironmentSettings


@dataclass(frozen=True)
class ModelSettings:
    endpoint: str
    model: str
    api_key: str = field(repr=False)

    @classmethod
    def from_env(cls, env=None):
        Settings = _environment_settings()
        # Supply every field for an explicit mapping, so unrelated process values
        # cannot leak into a menu session or a read-only diagnostic.
        values = ({} if env is None else {
            "endpoint": env.get("AGENT_OPT_MODEL_ENDPOINT", ""),
            "base_url": env.get("AGENT_OPT_MODEL_BASE_URL", ""),
            "id": env.get("AGENT_OPT_MODEL_ID", "glm5.3-flash"),
            "api_key": env.get("AGENT_OPT_MODEL_API_KEY", ""),
        })
        try:
            settings = Settings(**values)
        except ValueError:
            raise ConfigurationError("Invalid AGENT_OPT_MODEL_ settings") from None
        endpoint, base = settings.endpoint, settings.base_url
        if bool(endpoint) == bool(base):
            raise ConfigurationError("Set exactly one of AGENT_OPT_MODEL_ENDPOINT (full URL) or AGENT_OPT_MODEL_BASE_URL")
        url = endpoint or base.rstrip("/") + "/chat/completions"
        parts = urlsplit(url)
        if (parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment or any(c.isspace() for c in url)
                or (parts.scheme == "http" and parts.hostname not in {"localhost", "127.0.0.1", "::1"})):
            raise ConfigurationError("Model URL must be HTTPS (HTTP only on loopback), without credentials/query/fragment")
        model = settings.id
        key = settings.api_key.get_secret_value()
        if not model or any(c.isspace() for c in model):
            raise ConfigurationError("AGENT_OPT_MODEL_ID must be a nonempty model identifier")
        if not key or any(c.isspace() for c in key):
            raise UnavailableError("blocked_auth: set AGENT_OPT_MODEL_API_KEY to a Bearer token")
        return cls(url, model, key)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def complete(messages, *, settings=None, timeout=60, tools=None, tool_choice=None):
    settings = settings or ModelSettings.from_env()
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ConfigurationError("Model timeout must be finite and positive")
    # A socket timeout is not a whole-request deadline (DNS and trickling bodies can exceed it).
    # A short-lived stdlib worker gives every caller a bounded, cancellable request on all platforms.
    payload = {"settings": asdict(settings), "messages": messages, "timeout": timeout,
               "tools": tools, "tool_choice": tool_choice}
    try:
        result = subprocess.run([sys.executable, "-m", "agent_optimizer.models", "--request"],
                                input=json.dumps(payload), text=True, capture_output=True, timeout=timeout,
                                env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}, shell=False)
    except subprocess.TimeoutExpired:
        raise UnavailableError("Model request exceeded its total timeout") from None
    except OSError:
        raise UnavailableError("Cannot start model request worker") from None
    try:
        output = json.loads(result.stdout)
    except ValueError:
        raise UnavailableError("Model request worker failed") from None
    if result.returncode:
        raise UnavailableError(output.get("error", "Model request worker failed"))
    return output


def _complete(messages, *, settings, timeout, tools=None, tool_choice=None):
    body = {"model": settings.model, "messages": messages, "stream": False}
    if tools is not None:
        body.update(tools=tools, tool_choice=tool_choice)
    request = urllib.request.Request(settings.endpoint, json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + settings.api_key,
    })
    bundle = ca_bundle()
    context = ssl.create_default_context(cafile=str(bundle) if bundle else None)
    # Pass normalized proxies explicitly: urllib ignores uppercase HTTP_PROXY in CGI environments.
    network = network_environment()
    proxies = {name: network[name.upper() + "_PROXY"] for name in ("http", "https", "no")
               if name.upper() + "_PROXY" in network}
    opener = urllib.request.build_opener(_NoRedirect(), urllib.request.ProxyHandler(proxies),
                                        urllib.request.HTTPSHandler(context=context))
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise UnavailableError("Model response exceeds 2 MiB")
        result = json.loads(raw)
        message = result["choices"][0]["message"]
        if not isinstance(message, dict) or not (isinstance(message.get("content"), str) or message.get("tool_calls")):
            raise ValueError("missing assistant message")
        return result
    except urllib.error.HTTPError as exc:
        exc.close()
        raise UnavailableError(f"Model HTTP {exc.code}; check authentication, endpoint and model configuration") from None
    except (OSError, urllib.error.URLError, TimeoutError):
        raise UnavailableError("Model connection failed; check endpoint, proxy/NO_PROXY, CA trust and timeout") from None
    except (ValueError, KeyError, IndexError, TypeError):
        raise UnavailableError("Model returned an invalid chat completion response") from None


def probe_model(*, settings=None, timeout=30):
    settings = settings or ModelSettings.from_env()
    name = "connectivity_check"
    reply = complete([{"role": "user", "content": "Call connectivity_check with ok=true."}],
                     settings=settings, timeout=timeout,
                     tools=[{"type": "function", "function": {"name": name, "description": "Check connectivity",
                             "parameters": {"type": "object", "properties": {"ok": {"type": "boolean"}},
                                            "required": ["ok"], "additionalProperties": False}}}])
    try:
        call = reply["choices"][0]["message"]["tool_calls"][0]["function"]
        if call["name"] != name or json.loads(call["arguments"]) != {"ok": True}:
            raise ValueError()
    except (KeyError, IndexError, TypeError, ValueError):
        raise UnavailableError("Model tool-call probe failed; expected connectivity_check(ok=true)") from None
    return {"status": "passed", "model": settings.model, "tool_call": True}


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--request"]:
            payload = json.load(sys.stdin)
            payload["settings"] = ModelSettings(**payload["settings"])
            print(json.dumps(_complete(**payload)))
        else:
            print(json.dumps(probe_model()))
    except (ConfigurationError, UnavailableError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}))
        raise SystemExit(2)
