#!/bin/sh
# POSIX entry point: only setup may install anything. Never eval user arguments.
set -eu

help() {
    if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
        printf '\033[36m%s\033[0m\n' '개발 명령: setup doctor test lint demo smoke live menu help'
    else
        printf '%s\n' '개발 명령: setup doctor test lint demo smoke live menu help'
    fi
    printf '%s\n' \
        '사전 준비: Mac/Ubuntu, Git. ACE 전체 준비에는 Docker Engine과 Compose도 필요합니다.' \
        '시작: make setup-core → make doctor-core → make demo.' \
        'make가 없다면 sh scripts/bootstrap.sh <명령> [옵션]을 사용하세요.' \
        '--core나 --dataset이 없는 setup/doctor는 ACE 전체 환경을 대상으로 합니다.' \
        'setup: --core, --dataset ID, --offline, --platform linux/amd64|linux/arm64 (ACE 전체 전용)' \
        'doctor: --core, --dataset ID, --json, --platform, --model (실제 API 호출). --core와 --dataset/--platform/--model은 함께 쓸 수 없습니다.' \
        'smoke/live: --platform; live: --iterations 1..20' \
        'menu: 대화형 번호 메뉴(TTY 필요). 준비 후 사용자 CLI 도움말은 .venv/bin/agent-opt --help로 확인하세요.' \
        'test/lint/demo는 설치나 Docker 실행 없이 기존 .venv를 사용합니다.' \
        'make doctor ARGS="--json" (ARGS에는 일반 셸 인수 구문을 사용합니다).' \
        '상세 옵션: python3 scripts/dev.py --help 또는 python3 scripts/dev.py <명령> --help.'
}

fail() {
    if [ -t 2 ] && [ -z "${NO_COLOR:-}" ] && [ "$json_output" = false ]; then
        printf '\033[31m%s\033[0m\n' "$*" >&2
    else
        printf '%s\n' "$*" >&2
    fi
    exit 2
}

setup_status() {
    if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
        printf '\033[%sm%s\033[0m\n' "$1" "$2"
    else
        printf '%s\n' "$2"
    fi
}

progress_pid=
start_setup_progress() {
    [ -t 2 ] || return 0
    label=$1
    (
        started=$(date +%s)
        while sleep 1; do
            now=$(date +%s)
            printf '\r[setup] %s elapsed=%ss' "$label" "$((now-started))" >&2
        done
    ) &
    progress_pid=$!
}

stop_setup_progress() {
    [ -n "$progress_pid" ] || return 0
    kill "$progress_pid" 2>/dev/null || :
    wait "$progress_pid" 2>/dev/null || :
    progress_pid=
    if [ -z "${NO_COLOR:-}" ]; then printf '\r\033[K' >&2; else printf '\n' >&2; fi
}

command=${1:-help}
[ "$#" -eq 0 ] || shift
json_output=false
for option do
    if [ "$option" = --json ]; then json_output=true; fi
done
case "$command" in
    help|-h|--help) [ "$#" -eq 0 ] || fail 'help takes no options'; help; exit 0 ;;
    setup|doctor|test|lint|demo|smoke|live|menu) ;;
    *) fail "Unknown command: $command. Run sh scripts/bootstrap.sh help." ;;
esac

# Validate before prerequisites, installers, or Python, keeping argv untouched.
offline=false
core=false
full_option=false
want_platform=false
want_iterations=false
want_dataset=false
dataset=
show_help=false
for option do
    if [ "$want_dataset" = true ]; then
        dataset=$option
        want_dataset=false
        case "$dataset" in
            ''|[!a-z0-9]*|*[!a-z0-9_.-]*) fail '--dataset requires an identifier (lowercase letters, digits, _, . or -)' ;;
        esac
        continue
    fi
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
        setup:--core|doctor:--core) core=true ;;
        setup:--dataset|doctor:--dataset)
            [ -z "$dataset" ] || fail '--dataset may be specified only once'
            want_dataset=true ;;
        setup:--dataset=*|doctor:--dataset=*)
            [ -z "$dataset" ] || fail '--dataset may be specified only once'
            dataset=${option#*=}
            case "$dataset" in
                ''|[!a-z0-9]*|*[!a-z0-9_.-]*) fail '--dataset requires an identifier (lowercase letters, digits, _, . or -)' ;;
            esac ;;
        doctor:--json) ;;
        doctor:--model) full_option=true ;;
        live:--iterations) want_iterations=true ;;
        live:--iterations=*)
            count=${option#*=}
            case "$count" in ''|*[!0-9]*) fail '--iterations requires an integer from 1 to 20' ;; esac
            [ "$count" -ge 1 ] && [ "$count" -le 20 ] || fail '--iterations requires 1..20' ;;
        setup:--platform|doctor:--platform|smoke:--platform|live:--platform) want_platform=true; full_option=true ;;
        setup:--platform=*|doctor:--platform=*|smoke:--platform=*|live:--platform=*)
            full_option=true
            if [ "$command" != doctor ]; then
                case "${option#*=}" in linux/amd64|linux/arm64) ;; *) fail "Unsupported platform: $option" ;; esac
            fi ;;
        *) fail "Unsupported option for $command: $option. Run sh scripts/bootstrap.sh help." ;;
    esac
done
[ "$want_platform" = false ] || fail '--platform requires linux/amd64 or linux/arm64'
[ "$want_iterations" = false ] || fail '--iterations requires 1..20'
[ "$want_dataset" = false ] || fail '--dataset requires an identifier'
if [ "$core" = true ] && [ -n "$dataset" ]; then
    fail '--core cannot be combined with --dataset'
fi
if [ -n "$dataset" ] && [ "$full_option" = true ]; then
    fail '--dataset cannot be combined with --platform or --model'
fi
if [ "$core" = true ] && [ "$full_option" = true ]; then
    fail '--core cannot be combined with --platform or --model. Omit --core for full ACE commands; run sh scripts/bootstrap.sh help.'
fi
setup_command='sh scripts/bootstrap.sh setup'
case "$command:$core" in
    *:true|test:*|lint:*|demo:*|menu:*) setup_command="$setup_command --core" ;;
esac
if [ -n "$dataset" ]; then
    setup_command="$setup_command --dataset $dataset"
fi
if [ "$show_help" = true ]; then
    if [ "$command" = menu ]; then
        printf '%s\n' 'menu: 대화형 번호 메뉴(TTY와 Python >=3.11 필요).' \
            'sh scripts/bootstrap.sh menu로 실행하세요. 자동화에는 setup/doctor/demo/live 명령을 사용하세요.'
    else
        help
    fi
    exit 0
fi

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
PATH="$ROOT/.cache/uv/bin:$PATH"
export PATH
# Diagnostics must not write bytecode or obtain tools through interpreter startup.
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONHOME

# Use Ubuntu's existing full system trust, including installed proxy CAs. Explicit empty opts out.
case "$command" in
    setup|doctor|smoke|live)
        if [ "${AGENT_OPT_CA_BUNDLE+x}" != x ] && [ -r /etc/ssl/certs/ca-certificates.crt ]; then
            AGENT_OPT_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
            export AGENT_OPT_CA_BUNDLE
        fi ;;
esac

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
        fail "Python >=3.11 is unavailable. Run $setup_command; no installation was attempted."
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

if [ "$core" = true ] || [ -n "$dataset" ]; then
    setup_status 33 '[setup] core prerequisites: checking host OS and Git'
else
    setup_status 33 '[setup] prerequisites: checking Git, Docker daemon and Compose'
fi
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
if [ "$core" = false ] && [ -z "$dataset" ]; then
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
fi
[ "$missing" = false ] || fail "setup prerequisites failed; repair the items above and rerun $setup_command."
setup_status 32 '[setup] prerequisites: complete'

stage='uv preparation'
logs="$ROOT/external/setup-logs"
trap 'stop_setup_progress; printf "setup interrupted during %s; inspect %s and rerun %s.\n" "$stage" "$logs" "$setup_command" >&2; exit 130' HUP INT TERM
trap 'stop_setup_progress' EXIT
if ! command -v uv >/dev/null 2>&1; then
    [ "$offline" = false ] || fail "setup offline: uv missing; provision uv with online $setup_command first."
    downloader=
    if command -v curl >/dev/null 2>&1; then downloader=curl
    elif command -v wget >/dev/null 2>&1; then downloader=wget
    else fail "setup uv download: install curl/wget (Mac: brew install curl; Ubuntu: sudo apt install curl), then rerun $setup_command."
    fi
    mkdir -p "$logs" || fail "setup $stage: cannot create $logs; repair the path/permissions and rerun $setup_command."
    setup_status 33 "[setup] uv preparation: installing 0.10.7; log: $logs/bootstrap-uv.log"
    installer=$(mktemp "${TMPDIR:-/tmp}/agent-opt-uv.XXXXXXXX") ||
        fail "setup $stage: cannot allocate installer in ${TMPDIR:-/tmp}; set TMPDIR to a writable directory and rerun $setup_command."
    wget_config=
    trap 'stop_setup_progress; rm -f "$installer"; [ -z "$wget_config" ] || rm -f "$wget_config"' EXIT
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
    start_setup_progress 'uv installer'
    (
        if [ -n "$wget_config" ]; then export WGETRC="$wget_config"; fi
        if [ "$downloader" = curl ]; then
            curl -fLsS "$url" -o "$installer" || fail "setup uv download failed; rerun $setup_command after checking connectivity to $url"
        else
            wget -q "$url" -O "$installer" || fail "setup uv download failed; rerun $setup_command after checking connectivity to $url"
        fi
        UV_INSTALL_DIR="$ROOT/.cache/uv/bin" UV_NO_MODIFY_PATH=1 sh "$installer" >"$logs/bootstrap-uv.log" 2>&1 ||
            fail "setup uv installer failed; see $logs/bootstrap-uv.log; repair and rerun $setup_command."
    ) || exit 2
    stop_setup_progress
    rm -f "$installer"
    [ -z "$wget_config" ] || rm -f "$wget_config"
    trap - EXIT
    command -v uv >/dev/null 2>&1 || fail "setup uv installation missing at $ROOT/.cache/uv/bin; see $logs/bootstrap-uv.log; repair and rerun $setup_command."
fi

trap 'stop_setup_progress' EXIT
stage='project Python and frozen dependencies'
python_request=3.12
if [ -e "$ROOT/.venv" ] || [ -L "$ROOT/.venv" ]; then
    # Preserve even an invalid environment; uv must not silently replace it.
    short_probe 'setup existing project Python check' "$ROOT/.venv/bin/python" -I -B -c 'import sys; from pathlib import Path; assert sys.version_info >= (3, 11); assert sys.prefix != sys.base_prefix; assert Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve()' "$ROOT/.venv" ||
        fail "setup: existing $ROOT/.venv is incompatible and preserved. Move it aside explicitly, then rerun $setup_command."
    python_request="$ROOT/.venv/bin/python"
fi
mkdir -p "$logs" || fail "setup $stage: cannot create $logs; repair the path/permissions and rerun $setup_command."
setup_status 33 "[setup] $stage; log: $logs/project-uv.log"
export UV_PROJECT_ENVIRONMENT="$ROOT/.venv"
if [ "$offline" = true ]; then export UV_PYTHON_DOWNLOADS=never; fi
cd "$ROOT"
start_setup_progress "$stage"
if [ "$offline" = true ]; then
    uv --offline sync --frozen --python "$python_request" --extra dev >"$logs/project-uv.log" 2>&1 ||
        fail "setup offline project sync failed; see $logs/project-uv.log. Provision missing cache/Python online with $setup_command, then rerun $setup_command --offline."
else
    uv sync --frozen --python "$python_request" --extra dev >"$logs/project-uv.log" 2>&1 ||
        fail "setup project sync failed; see $logs/project-uv.log; repair and rerun $setup_command."
fi
stop_setup_progress
setup_status 32 "[setup] $stage: complete"
stage='Python dispatch'
compatible_python "$ROOT/.venv/bin/python" ||
    fail "setup $stage: $ROOT/.venv/bin/python unavailable after sync; inspect $logs/project-uv.log, repair the interpreter/permissions and rerun $setup_command."
export AGENT_OPT_BOOTSTRAPPED="$ROOT"
exec "$ROOT/.venv/bin/python" -B "$ROOT/scripts/dev.py" setup "$@"
