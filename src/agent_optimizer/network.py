"""Optional host/build/container network settings; never disable TLS verification."""
from __future__ import annotations

import os
import ssl
import hashlib
import re
import sys
import tempfile
import shutil
from contextlib import contextmanager
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.workspace import safe_path

PROXY_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
CA_VARIABLES = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "GIT_SSL_CAINFO",
                "PIP_CERT", "NODE_EXTRA_CA_CERTS", "npm_config_cafile")
CONTAINER_CA = "/opt/agent-optimizer/ca-bundle.pem"
SYSTEM_CA = "/etc/ssl/certs/ca-certificates.crt"


def demo_environment(env=None):
    """Select the existing Ubuntu system trust for demo entry points, without mutation."""
    result = dict(os.environ if env is None else env)
    if "AGENT_OPT_CA_BUNDLE" not in result and sys.platform == "linux" and Path(SYSTEM_CA).is_file():
        result["AGENT_OPT_CA_BUNDLE"] = SYSTEM_CA
    return result


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
def _cached_build(command, env):
    env = os.environ if env is None else env
    value = env.get("AGENT_OPT_BUILD_CACHE_DIR")
    if not value:
        yield command
        return
    root = Path(value)
    if not root.is_absolute() or any(char in value for char in ",\n\r\0"):
        raise ConfigurationError("Build cache requires an absolute local directory without separators")
    safe_path(root, ".")
    root.mkdir(parents=True, exist_ok=True)
    tag_index = next((index for index, arg in enumerate(command) if arg in {"-t", "--tag"}), None)
    if tag_index is None:
        raise ConfigurationError("Cached builds require an explicit image tag")
    builder = env.get("AGENT_OPT_BUILD_CACHE_BUILDER")
    if builder and (not isinstance(builder, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", builder)):
        raise ConfigurationError("Build cache builder must be a local builder name")
    key = hashlib.sha256(command[tag_index + 1].encode()).hexdigest()
    # Local build-cache mode targets the supported Mac/Linux hosts only.
    import fcntl
    locks = safe_path(root, ".locks")
    locks.mkdir(exist_ok=True)
    lock_path = safe_path(locks, key + ".lock")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        source = safe_path(root, key)
        backup = safe_path(root, "." + key + ".previous")
        if backup.exists():
            raise ConfigurationError("Previous build cache recovery is required before reuse")
        flags = ["--cache-from", f"type=local,src={source}"] if _cache_index(source) else []
        if builder:
            flags += ["--builder", builder]
        with tempfile.TemporaryDirectory(prefix="export-", dir=root) as temporary:
            destination = Path(temporary) / "cache"
            flags += ["--cache-to", f"type=local,dest={destination},mode=max"]
            yield ["docker", "buildx", "build", "--load", *flags, *command[2:]]
            if not _cache_index(destination):
                raise ConfigurationError("Successful cached build did not export its layer index")
            if source.exists():
                source.rename(backup)
            try:
                destination.rename(source)
            except OSError:
                # Keep the backup outside the temporary export if rollback also fails.
                if backup.exists() and not source.exists():
                    backup.rename(source)
                raise
            if backup.exists():
                shutil.rmtree(backup)


def _cache_index(directory):
    safe_path(directory, ".")
    if not directory.exists():
        return False
    if not directory.is_dir():
        raise ConfigurationError("Build cache entry must be a directory")
    for path in directory.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ConfigurationError("Build cache cannot contain links or special files")
    return (directory / "index.json").is_file()


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
        with _cached_build(command[:2] + flags + command[2:], env) as cached:
            yield cached
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
        with _cached_build(command[:2] + flags + command[2:], env) as cached:
            yield cached
