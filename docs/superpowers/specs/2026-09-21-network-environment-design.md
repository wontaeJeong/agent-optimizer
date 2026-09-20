# Optional proxy and CA environment

## Contract

Use one optional environment contract for host tools, image builds, Agent runtime,
and the supported CVDP evaluator. Existing host/daemon trust is an operator
prerequisite. No system/daemon settings are modified.

- Accept HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, NO_PROXY and lowercase equivalents.
  Lowercase wins if both forms exist, including an explicit empty value; pass the
  resolved value in both cases so tools agree. Preserve NO_PROXY verbatim.
- AGENT_OPT_CA_BUNDLE is an optional readable PEM **complete trust bundle**. It
  should contain public roots as well as extra roots when both are needed; the
  configured host system bundle is a convenient source. Reject invalid files
  before launching a process. Never turn off TLS verification.
- Map the bundle to SSL_CERT_FILE, REQUESTS_CA_BUNDLE, CURL_CA_BUNDLE,
  GIT_SSL_CAINFO, PIP_CERT, NODE_EXTRA_CA_CERTS, and npm_config_cafile. The explicit
  project bundle wins over these tool-specific settings. Without it, host tool
  settings remain untouched; host filesystem paths are not implicitly forwarded
  into containers.

## Implementation

A flat `agent_optimizer/network.py` module provides environment normalization,
bundle validation, container arguments, and a temporary Dockerfile build adapter.
`scripts/network.py` wraps bootstrap/manual commands using that same contract.

Builds pass proxy arguments by name, never embed values in Dockerfiles or command
logs, and do not declare proxy ARG/ENV. With a bundle, use a BuildKit named context
containing only the validated CA file; inject trust configuration immediately
after the single FROM in the two shipped Dockerfiles. The copy is temporary and
the upstream checkout remains unchanged. The CA is intentionally present in the
resulting image (public trust material, not a private key). Package-manager trust
is configured before the first network operation, including npm and apt.

Runtime mounts the bundle read-only at a fixed container path, propagates the
tool variables with container paths, and passes proxies by name. The bundle also
overlays the Debian/Ubuntu system bundle path for system-store consumers. Do not
alter the configured network mode, user, resource limits, or workspace mounts.

The evaluator retains its model-credential allowlist. When network settings are
present, an example-local driver entry point uses the already installed PyYAML
to augment only the private submission's Compose service environment, proxy
build arguments and CA mounts. Environment references rather than proxy values
are written to private files. Original tasks/checker/source files are unchanged.
Supported nested Dockerfiles only alias the prepared simulator image; inherited
image trust covers their build. Arbitrary external plugins/images are not
automatically configured.

## Evidence and errors

Record CA content hash (not proxy values) in the prepared environment lock and
reject changed CA selection on offline reuse. Native tools keep NO_PROXY parsing
semantics; do not invent a universal CIDR implementation. Local tests exercise
real TLS and proxy/bypass behavior plus subprocess/Compose boundary contracts.
Docker smoke verifies actual image trust and read-only runtime configuration when
available. Report full model/upstream evaluation separately from network tests.

## Alternatives considered

Separate network-specific Dockerfiles drift from upstream and duplicate builds.
Global Docker client proxy configuration cannot cover host tools and leaves CA
handling unresolved. The optional shared environment contract is the selected
approach, approved in chat with implementation requested on 2026-09-21.
