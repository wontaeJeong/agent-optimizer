"""Optional host/build/container network settings; never disable TLS verification."""
from __future__ import annotations

import os
import ssl
import hashlib
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError

PROXY_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
CA_VARIABLES = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "GIT_SSL_CAINFO",
                "PIP_CERT", "NODE_EXTRA_CA_CERTS", "npm_config_cafile")
CONTAINER_CA = "/opt/agent-optimizer/ca-bundle.pem"
SYSTEM_CA = "/etc/ssl/certs/ca-certificates.crt"


def ca_bundle(env=None) -> Path | None:
    env = os.environ if env is None else env
    value = env.get("AGENT_OPT_CA_BUNDLE")
    if not value:
        return None
    path = Path(value).expanduser().absolute()
    try:
        if not path.is_file() or any(c in str(path) for c in ",\n\r\0"):
            raise ValueError("not a bind-mountable file")
        content = path.read_bytes()
        if b"PRIVATE KEY" in content:
            raise ValueError("private key is not a trust bundle")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(path))
        if not context.get_ca_certs():
            raise ValueError("no CA certificates")
    except (OSError, ValueError) as exc:
        raise ConfigurationError("AGENT_OPT_CA_BUNDLE must be a readable PEM CA bundle without private keys") from exc
    return path


def network_environment(env=None) -> dict[str, str]:
    env = os.environ if env is None else env
    result = {}
    for upper in PROXY_NAMES:
        lower = upper.lower()
        if lower in env or upper in env:
            value = env[lower] if lower in env else env[upper]
            result.update({upper: value, lower: value})
    bundle = ca_bundle(env)
    if bundle is not None:
        result.update({key: str(bundle) for key in CA_VARIABLES})
        result["AGENT_OPT_CA_BUNDLE"] = str(bundle)
    return result


def host_environment(env=None) -> dict[str, str]:
    env = os.environ if env is None else env
    return {**env, **network_environment(env)}


def container_network(env=None) -> tuple[list[str], dict[str, str]]:
    settings = network_environment(env)
    argv = []
    for key in settings:
        if key.upper() in PROXY_NAMES:
            argv += ["--env", key]
    if bundle := settings.get("AGENT_OPT_CA_BUNDLE"):
        for target in (CONTAINER_CA, SYSTEM_CA):
            argv += ["--mount", f"type=bind,source={bundle},target={target},readonly"]
        for key in CA_VARIABLES:
            argv += ["--env", f"{key}={CONTAINER_CA}"]
    return argv, settings


def ca_fingerprint(env=None) -> str | None:
    bundle = ca_bundle(env)
    return hashlib.sha256(bundle.read_bytes()).hexdigest() if bundle else None


@contextmanager
def configured_build(argv: list[str], cwd: Path, env=None):
    """Adapt single-stage local Docker builds without editing their source/context."""
    if argv[:2] != ["docker", "build"]:
        yield argv
        return
    settings = network_environment(env)
    command = list(argv)
    flags = []
    for key in settings:
        if key.upper() in PROXY_NAMES:
            flags += ["--build-arg", key]
    if not settings.get("AGENT_OPT_CA_BUNDLE"):
        yield command[:2] + flags + command[2:]
        return
    # Scope is deliberately the shipped single-stage Dockerfiles/local contexts.
    # Named contexts require BuildKit; do not retry with TLS verification disabled.
    file_flag = next((i for i, arg in enumerate(command) if arg in {"-f", "--file"}), None)
    source = Path(command[file_flag + 1]) if file_flag is not None else Path(command[-1]) / "Dockerfile"
    if not source.is_absolute():
        source = Path(cwd) / source
    try:
        text = source.read_text()
    except OSError as exc:
        raise ConfigurationError("CA-enabled builds require a local Dockerfile (-f PATH)") from exc
    starts = list(re.finditer(r"^FROM[^\n]*(?:\n|$)", text, re.M | re.I))
    if len(starts) != 1 or "\\" in starts[0].group():
        raise ConfigurationError("CA-enabled builds support one single-line FROM stage")
    with tempfile.TemporaryDirectory(prefix="agent-opt-build-") as directory:
        root = Path(directory)
        context = root / "ca"
        context.mkdir()
        (context / "ca-bundle.pem").write_bytes(Path(settings["AGENT_OPT_CA_BUNDLE"]).read_bytes())
        # Public CA material is intentionally part of the image; no proxy values are.
        trust = (f"\nCOPY --from=agent_opt_ca /ca-bundle.pem {CONTAINER_CA}\n"
                 f"COPY --from=agent_opt_ca /ca-bundle.pem {SYSTEM_CA}\n"
                 "COPY --from=agent_opt_ca /ca-bundle.pem /usr/local/share/ca-certificates/agent-opt.crt\n"
                 + "ENV " + " ".join(f"{key}={CONTAINER_CA}" for key in CA_VARIABLES) + "\n"
                 + "RUN mkdir -p /etc/apt/apt.conf.d && "
                 + f"printf 'Acquire::https::CaInfo \"{CONTAINER_CA}\";\\n' > /etc/apt/apt.conf.d/99agent-opt-ca\n")
        index = starts[0].end()
        generated = root / "Dockerfile"
        generated.write_text(text[:index] + trust + text[index:])
        if file_flag is None:
            flags += ["-f", str(generated)]
        else:
            command[file_flag + 1] = str(generated)
        flags += ["--build-context", f"agent_opt_ca={context}"]
        yield command[:2] + flags + command[2:]
