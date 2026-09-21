#!/bin/sh
# POSIX entry point: only setup may install anything. Never eval user arguments.
set -eu

help() {
    printf '%s\n' \
        'Development commands: setup doctor test lint demo smoke live help' \
        'Prerequisites: Mac/Ubuntu, Git, Docker Engine + Compose (running daemon).' \
        'Start: sh scripts/bootstrap.sh setup; then make doctor and make demo.' \
        'No make? Use sh scripts/bootstrap.sh <command> [options].' \
        'setup: --offline, --platform linux/amd64|linux/arm64' \
        'doctor: --json, --platform, --model (actual API calls); smoke/live: --platform; live: --iterations 1..20' \
        'test/lint/demo use .venv without installing or requiring Docker.' \
        'make doctor ARGS="--json" (ARGS uses normal shell command arguments).' \
        'Full command help: python3 scripts/dev.py --help or <command> --help.'
}

fail() { printf '%s\n' "$*" >&2; exit 2; }

command=${1:-help}
[ "$#" -eq 0 ] || shift
case "$command" in
    help|-h|--help) [ "$#" -eq 0 ] || fail 'help takes no options'; help; exit 0 ;;
    setup|doctor|test|lint|demo|smoke|live) ;;
    *) fail "Unknown command: $command. Run sh scripts/bootstrap.sh help." ;;
esac

# Validate before prerequisites, installers, or Python, keeping argv untouched.
offline=false
want_platform=false
want_iterations=false
show_help=false
for option do
    if [ "$want_iterations" = true ]; then
        case "$option" in ''|*[!0-9]*) fail '--iterations requires an integer from 1 to 20' ;; esac
        [ "$option" -ge 1 ] && [ "$option" -le 20 ] || fail '--iterations requires 1..20'
        want_iterations=false
        continue
    fi
    if [ "$want_platform" = true ]; then
        if [ "$command" != doctor ]; then
            case "$option" in linux/amd64|linux/arm64) ;; *) fail "Unsupported platform: $option" ;; esac
        fi
        want_platform=false
        continue
    fi
    case "$command:$option" in
        *:--help|*:-h) show_help=true ;;
        setup:--offline) offline=true ;;
        doctor:--json) ;;
        doctor:--model) ;;
        live:--iterations) want_iterations=true ;;
        live:--iterations=*)
            count=${option#*=}
            case "$count" in ''|*[!0-9]*) fail '--iterations requires an integer from 1 to 20' ;; esac
            [ "$count" -ge 1 ] && [ "$count" -le 20 ] || fail '--iterations requires 1..20' ;;
        setup:--platform|doctor:--platform|smoke:--platform|live:--platform) want_platform=true ;;
        setup:--platform=*|doctor:--platform=*|smoke:--platform=*|live:--platform=*)
            if [ "$command" != doctor ]; then
                case "${option#*=}" in linux/amd64|linux/arm64) ;; *) fail "Unsupported platform: $option" ;; esac
            fi ;;
        *) fail "Unsupported option for $command: $option. Run sh scripts/bootstrap.sh help." ;;
    esac
done
[ "$want_platform" = false ] || fail '--platform requires linux/amd64 or linux/arm64'
[ "$want_iterations" = false ] || fail '--iterations requires 1..20'
if [ "$show_help" = true ]; then help; exit 0; fi

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
PATH="$ROOT/.cache/uv/bin:$PATH"
export PATH
# Diagnostics must not write bytecode or obtain tools through interpreter startup.
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONHOME

# Use Ubuntu's existing full system trust, including installed proxy CAs. Explicit empty opts out.
if [ "${AGENT_OPT_CA_BUNDLE+x}" != x ] && [ -r /etc/ssl/certs/ca-certificates.crt ]; then
    AGENT_OPT_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
    export AGENT_OPT_CA_BUNDLE
fi

# POSIX tools available on Mac/Ubuntu; no Python or GNU timeout prerequisite.
# Stop parents before walking their children so a waiting wrapper cannot resume
# and launch more work during cleanup. Never signal the caller's process group.
stop_probe_tree() (
    pid=$1
    kill -STOP "$pid" 2>/dev/null || exit 0
    for child in $(ps -eo pid=,ppid= | awk -v parent="$pid" '$2 == parent {print $1}'); do
        stop_probe_tree "$child"
    done
    kill -KILL "$pid" 2>/dev/null || :
)

short_probe() (
    label=$1
    shift
    probe=
    timer=
    # Invoked by the EXIT trap, including signal/error exits.
    # shellcheck disable=SC2329
    cleanup() {
        [ -z "$timer" ] || stop_probe_tree "$timer"
        [ -z "$probe" ] || stop_probe_tree "$probe"
        wait 2>/dev/null || :
    }
    # Mac /bin/sh can report a killed background job between cleanup commands,
    # before wait's own redirection takes effect. Scope silence to cleanup only;
    # the watchdog's timeout/repair message remains visible.
    trap 'cleanup 2>/dev/null' EXIT
    trap 'exit 130' HUP INT TERM
    "$@" >/dev/null 2>&1 &
    probe=$!
    (
        sleep 15
        printf '%s timed out after 15s; repair the tool/endpoint and rerun sh scripts/bootstrap.sh %s.\n' "$label" "$command" >&2
        stop_probe_tree "$probe"
    ) &
    timer=$!
    code=0
    wait "$probe" 2>/dev/null || code=$?
    probe=
    exit "$code"
)

compatible_python() {
    short_probe "$command Python interpreter check" "$1" -I -B -c 'import sys; assert sys.version_info >= (3, 11)'
}

if [ "$command" != setup ]; then
    if compatible_python "$ROOT/.venv/bin/python"; then
        python="$ROOT/.venv/bin/python"
    elif command -v python3 >/dev/null 2>&1 && compatible_python python3; then
        python=python3
    elif command -v python >/dev/null 2>&1 && compatible_python python; then
        python=python
    else
        fail 'Python >=3.11 is unavailable. Run sh scripts/bootstrap.sh setup; no installation was attempted.'
    fi
    exec "$python" -B "$ROOT/scripts/dev.py" "$command" "$@"
fi

# Python may not exist yet. Match network.py's lowercase/empty proxy precedence
# and export trust paths before the first installer or uv Python download.
if [ "${http_proxy+x}${HTTP_PROXY+x}" ]; then export HTTP_PROXY="${http_proxy-${HTTP_PROXY-}}"; export http_proxy="$HTTP_PROXY"; fi
if [ "${https_proxy+x}${HTTPS_PROXY+x}" ]; then export HTTPS_PROXY="${https_proxy-${HTTPS_PROXY-}}"; export https_proxy="$HTTPS_PROXY"; fi
if [ "${all_proxy+x}${ALL_PROXY+x}" ]; then export ALL_PROXY="${all_proxy-${ALL_PROXY-}}"; export all_proxy="$ALL_PROXY"; fi
if [ "${no_proxy+x}${NO_PROXY+x}" ]; then export NO_PROXY="${no_proxy-${NO_PROXY-}}"; export no_proxy="$NO_PROXY"; fi
if [ -n "${AGENT_OPT_CA_BUNDLE:-}" ]; then
    case "$AGENT_OPT_CA_BUNDLE" in
        \~/*) AGENT_OPT_CA_BUNDLE="$HOME/${AGENT_OPT_CA_BUNDLE#\~/}" ;;
    esac
    case "$AGENT_OPT_CA_BUNDLE" in /*) ;; *) AGENT_OPT_CA_BUNDLE="$PWD/$AGENT_OPT_CA_BUNDLE" ;; esac
    [ -f "$AGENT_OPT_CA_BUNDLE" ] && [ -r "$AGENT_OPT_CA_BUNDLE" ] ||
        fail 'AGENT_OPT_CA_BUNDLE must be a readable PEM CA bundle; repair it and rerun setup.'
    export AGENT_OPT_CA_BUNDLE
    export SSL_CERT_FILE="$AGENT_OPT_CA_BUNDLE" REQUESTS_CA_BUNDLE="$AGENT_OPT_CA_BUNDLE"
    export CURL_CA_BUNDLE="$AGENT_OPT_CA_BUNDLE" GIT_SSL_CAINFO="$AGENT_OPT_CA_BUNDLE"
    export PIP_CERT="$AGENT_OPT_CA_BUNDLE" NODE_EXTRA_CA_CERTS="$AGENT_OPT_CA_BUNDLE" npm_config_cafile="$AGENT_OPT_CA_BUNDLE"
fi

printf '%s\n' '[setup] prerequisites: checking Git, Docker daemon and Compose'
missing=false
# Expand uname inside the bounded child, not in this parent shell.
# shellcheck disable=SC2016
if ! short_probe 'setup prerequisites: host OS' sh -c 'case "$(uname -s)" in Darwin|Linux) exit 0;; *) exit 1;; esac'; then
    printf '%s\n' 'Host OS unavailable or unsupported: use Mac or Ubuntu; check uname -s.' >&2
    missing=true
fi
if ! command -v git >/dev/null 2>&1 || ! short_probe 'setup prerequisites: Git' git --version; then
    printf '%s\n' 'Git unavailable. Mac: xcode-select --install; Ubuntu: sudo apt install git.' >&2
    missing=true
fi
if ! command -v docker >/dev/null 2>&1; then
    printf '%s\n' 'Docker CLI unavailable. Mac: install/open Docker Desktop https://docs.docker.com/desktop/setup/install/mac-install/ ; Ubuntu: install Engine + Compose plugin https://docs.docker.com/engine/install/ubuntu/' >&2
    missing=true
else
    if ! short_probe 'setup prerequisites: Docker daemon' docker info; then
        printf '%s\n' 'Docker daemon unavailable. Mac: open Docker Desktop; Ubuntu: sudo systemctl start docker, then check docker info and socket permissions: https://docs.docker.com/engine/install/linux-postinstall/' >&2
        missing=true
    fi
    if ! short_probe 'setup prerequisites: Docker Compose' docker compose version; then
        printf '%s\n' 'Docker Compose unavailable. Mac: update Docker Desktop; Ubuntu: install docker-compose-plugin from the Docker apt repository: https://docs.docker.com/compose/install/linux/' >&2
        missing=true
    fi
    if [ -n "${AGENT_OPT_CA_BUNDLE:-}" ] && [ "$offline" = false ] &&
        ! short_probe 'setup prerequisites: Docker Buildx' docker buildx version; then
        printf '%s\n' 'CA-enabled builds require docker buildx; install docker-buildx-plugin and rerun setup.' >&2
        missing=true
    fi
fi
[ "$missing" = false ] || fail 'setup prerequisites failed; repair the items above and rerun sh scripts/bootstrap.sh setup.'
printf '%s\n' '[setup] prerequisites: complete'

stage='uv preparation'
logs="$ROOT/external/setup-logs"
trap 'printf "setup interrupted during %s; inspect %s and rerun sh scripts/bootstrap.sh setup.\n" "$stage" "$logs" >&2; exit 130' HUP INT TERM
if ! command -v uv >/dev/null 2>&1; then
    [ "$offline" = false ] || fail 'setup offline: uv missing; provision uv with online sh scripts/bootstrap.sh setup first.'
    downloader=
    if command -v curl >/dev/null 2>&1; then downloader=curl
    elif command -v wget >/dev/null 2>&1; then downloader=wget
    else fail 'setup uv download: install curl/wget (Mac: brew install curl; Ubuntu: sudo apt install curl), then rerun setup.'
    fi
    mkdir -p "$logs" || fail "setup $stage: cannot create $logs; repair the path/permissions and rerun setup."
    printf '[setup] uv preparation: installing 0.10.7; log: %s/bootstrap-uv.log\n' "$logs"
    installer=$(mktemp "${TMPDIR:-/tmp}/agent-opt-uv.XXXXXXXX") ||
        fail "setup $stage: cannot allocate installer in ${TMPDIR:-/tmp}; set TMPDIR to a writable directory and rerun setup."
    wget_config=
    trap 'rm -f "$installer"; [ -z "$wget_config" ] || rm -f "$wget_config"' EXIT
    if [ "$downloader" = wget ] && [ -n "${AGENT_OPT_CA_BUNDLE:-}" ]; then
        # The pinned installer invokes wget again for the archive; CLI flags on
        # only the first download would lose trust. Preserve user configuration.
        case "$AGENT_OPT_CA_BUNDLE" in
            *'
'*|*"$(printf '\r')"*) fail 'AGENT_OPT_CA_BUNDLE must not contain line breaks.' ;;
        esac
        wget_config=$(mktemp "${TMPDIR:-/tmp}/agent-opt-wget.XXXXXXXX") ||
            fail 'setup uv download: cannot allocate temporary wget configuration.'
        if [ -f "${WGETRC:-$HOME/.wgetrc}" ]; then
            cat "${WGETRC:-$HOME/.wgetrc}" > "$wget_config"
        fi
        printf '\nca_certificate = %s\n' "$AGENT_OPT_CA_BUNDLE" >> "$wget_config"
        # Subshell scopes WGETRC to both downloads without changing later tools.
    fi
    url=https://astral.sh/uv/0.10.7/install.sh
    (
        if [ -n "$wget_config" ]; then export WGETRC="$wget_config"; fi
        if [ "$downloader" = curl ]; then
            curl -fLsS "$url" -o "$installer" || fail "setup uv download failed; rerun setup after checking connectivity to $url"
        else
            wget -q "$url" -O "$installer" || fail "setup uv download failed; rerun setup after checking connectivity to $url"
        fi
        UV_INSTALL_DIR="$ROOT/.cache/uv/bin" UV_NO_MODIFY_PATH=1 sh "$installer" >"$logs/bootstrap-uv.log" 2>&1 ||
            fail "setup uv installer failed; see $logs/bootstrap-uv.log; repair and rerun setup."
    ) || exit 2
    rm -f "$installer"
    [ -z "$wget_config" ] || rm -f "$wget_config"
    trap - EXIT
    command -v uv >/dev/null 2>&1 || fail "setup uv installation missing at $ROOT/.cache/uv/bin; see $logs/bootstrap-uv.log; repair and rerun setup."
fi

stage='project Python and frozen dependencies'
python_request=3.12
if [ -e "$ROOT/.venv" ] || [ -L "$ROOT/.venv" ]; then
    # Preserve even an invalid environment; uv must not silently replace it.
    short_probe 'setup existing project Python check' "$ROOT/.venv/bin/python" -I -B -c 'import sys; from pathlib import Path; assert sys.version_info >= (3, 11); assert sys.prefix != sys.base_prefix; assert Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve()' "$ROOT/.venv" ||
        fail "setup: existing $ROOT/.venv is incompatible and preserved. Move it aside explicitly, then rerun setup."
    python_request="$ROOT/.venv/bin/python"
fi
mkdir -p "$logs" || fail "setup $stage: cannot create $logs; repair the path/permissions and rerun setup."
printf '[setup] %s; log: %s/project-uv.log\n' "$stage" "$logs"
export UV_PROJECT_ENVIRONMENT="$ROOT/.venv"
if [ "$offline" = true ]; then export UV_PYTHON_DOWNLOADS=never; fi
cd "$ROOT"
if [ "$offline" = true ]; then
    uv --offline sync --frozen --python "$python_request" --extra dev >"$logs/project-uv.log" 2>&1 ||
        fail "setup offline project sync failed; see $logs/project-uv.log. Provision missing cache/Python online, then rerun setup --offline."
else
    uv sync --frozen --python "$python_request" --extra dev >"$logs/project-uv.log" 2>&1 ||
        fail "setup project sync failed; see $logs/project-uv.log; repair and rerun setup."
fi
printf '[setup] %s: complete\n' "$stage"
stage='Python dispatch'
compatible_python "$ROOT/.venv/bin/python" ||
    fail "setup $stage: $ROOT/.venv/bin/python unavailable after sync; inspect $logs/project-uv.log, repair the interpreter/permissions and rerun setup."
export AGENT_OPT_BOOTSTRAPPED="$ROOT"
exec "$ROOT/.venv/bin/python" -B "$ROOT/scripts/dev.py" setup "$@"
