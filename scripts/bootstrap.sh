#!/bin/sh
# POSIX entry point: only setup may install anything. Never eval user arguments.
set -eu

language=${AGENT_OPT_LANG:-ko}
case "$language" in
    ko|en) ;;
    *) printf '%s\n' 'AGENT_OPT_LANG must be ko or en' >&2; exit 2 ;;
esac

help() {
    if [ "$language" = en ]; then
        if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
            printf '\033[36m%s\033[0m\n' 'Development commands: setup doctor test lint demo smoke live menu help'
        else
            printf '%s\n' 'Development commands: setup doctor test lint demo smoke live menu help'
        fi
        printf '%s\n' \
            'Requirements: Mac/Ubuntu, Git. Full ACE setup also needs Docker Engine and Compose.' \
            'Start: make setup ARGS="--core" → make doctor ARGS="--core" → make demo.' \
            'Without make, use sh scripts/bootstrap.sh <command> [options].' \
            'setup/doctor without --core or --dataset target the full ACE environment.' \
            'setup: --core, --dataset ID, --offline, --platform linux/amd64|linux/arm64 (full ACE only)' \
            'doctor: --core, --dataset ID, --json, --platform, --model (calls the real API). --core cannot be combined with --dataset/--platform/--model.' \
            'smoke/live: --platform; live: --iterations 1..20' \
            'menu: interactive numbered menu (TTY required). After setup, run .venv/bin/agent-opt --help for user commands.' \
            'test/lint/demo use the existing .venv without installation or Docker.' \
            'make doctor ARGS="--json" (ARGS accepts normal shell argument syntax).' \
            'All options: python3 scripts/dev.py --help or python3 scripts/dev.py <command> --help.'
        return
    fi
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
    message=$*
    if [ "$language" = ko ]; then
        case "$message" in
            'help takes no options') message='help 명령에는 옵션을 지정할 수 없습니다' ;;
            'Unknown command: '*) message="알 수 없는 명령: ${message#Unknown command: }" ;;
            'Unsupported option for '*)
                detail=${message#Unsupported option for }
                detail=${detail%. Run sh scripts/bootstrap.sh help.}
                message="지원하지 않는 옵션 ($detail). sh scripts/bootstrap.sh help를 실행하세요." ;;
            '--dataset requires an identifier'* ) message='--dataset에는 소문자·숫자·_·.·-로 된 ID가 필요합니다' ;;
            '--dataset may be specified only once') message='--dataset은 한 번만 지정할 수 있습니다' ;;
            '--iterations requires an integer from 1 to 20'|'--iterations requires 1..20')
                message='--iterations에는 1..20 정수가 필요합니다' ;;
            '--platform requires linux/amd64 or linux/arm64') message='--platform에는 linux/amd64 또는 linux/arm64가 필요합니다' ;;
            'Unsupported platform: '*) message="지원하지 않는 플랫폼: ${message#Unsupported platform: }" ;;
            '--core cannot be combined with --dataset') message='--core와 --dataset은 함께 사용할 수 없습니다' ;;
            '--dataset cannot be combined with --platform or --model') message='--dataset과 --platform/--model은 함께 사용할 수 없습니다' ;;
            '--core cannot be combined with --platform or --model'*)
                message='--core와 --platform/--model은 함께 사용할 수 없습니다. ACE 전체 명령은 --core 없이 실행하세요.' ;;
            'setup offline: uv missing; '*)
                message="오프라인 setup에 uv가 없습니다. 먼저 온라인 $setup_command 명령으로 uv를 준비하세요." ;;
            'setup prerequisites failed; '*)
                message="setup 사전 준비 실패: 위 항목을 수정하고 $setup_command 명령을 다시 실행하세요." ;;
            'Python >=3.11 is unavailable.'*)
                message="Python >=3.11을 사용할 수 없습니다. $setup_command 명령을 실행하세요. 설치는 시도하지 않았습니다." ;;
            'AGENT_OPT_CA_BUNDLE must be a readable PEM CA bundle;'*)
                message='AGENT_OPT_CA_BUNDLE에는 읽기 가능한 PEM CA 번들이 필요합니다. 수정 후 setup을 다시 실행하세요.' ;;
            'AGENT_OPT_CA_BUNDLE must not contain line breaks.')
                message='AGENT_OPT_CA_BUNDLE에는 줄바꿈을 넣을 수 없습니다.' ;;
            'setup offline project sync failed; see '*)
                message="setup 오프라인 동기화 실패; 로그: $logs/project-uv.log. 필요한 cache/Python을 온라인 $setup_command 명령으로 준비하고 $setup_command --offline을 다시 실행하세요." ;;
            'setup project sync failed; see '*)
                message="setup 프로젝트 동기화 실패; 로그: $logs/project-uv.log. 문제를 수정하고 $setup_command 명령을 다시 실행하세요." ;;
            'setup uv download failed; rerun '*)
                message="setup uv 다운로드 실패: $url 연결을 확인하고 $setup_command 명령을 다시 실행하세요." ;;
            'setup uv installer failed; see '*)
                message="setup uv 설치 실패; 로그: $logs/bootstrap-uv.log. 문제를 수정하고 $setup_command 명령을 다시 실행하세요." ;;
            'setup uv download: install curl/wget '*)
                message="setup uv 다운로드에는 curl/wget이 필요합니다 (Mac: brew install curl; Ubuntu: sudo apt install curl). 설치 후 $setup_command 명령을 다시 실행하세요." ;;
            'setup uv download: cannot allocate temporary wget configuration.')
                message='setup uv 다운로드용 임시 wget 설정을 만들지 못했습니다. TMPDIR을 확인하세요.' ;;
            'setup: existing '*'.venv is incompatible and preserved.'*)
                message="setup: 기존 $ROOT/.venv가 호환되지 않아 보존했습니다. 명시적으로 이동한 뒤 $setup_command 명령을 다시 실행하세요." ;;
            'setup '*': cannot create '*'; repair the path/permissions and rerun '*)
                message="setup $stage: $logs 디렉터리를 만들 수 없습니다. 경로·권한을 수정하고 $setup_command 명령을 다시 실행하세요." ;;
            'setup '*': cannot allocate installer in '*)
                message="setup $stage: ${TMPDIR:-/tmp}에 설치 파일을 만들 수 없습니다. 쓰기 가능한 TMPDIR을 지정한 뒤 $setup_command 명령을 다시 실행하세요." ;;
            'setup uv installation missing at '*)
                message="setup uv 설치 후 실행 파일을 찾을 수 없습니다: $ROOT/.cache/uv/bin; 로그: $logs/bootstrap-uv.log. 문제를 수정하고 $setup_command 명령을 다시 실행하세요." ;;
            'setup Python dispatch: '*)
                message="setup Python 전달 실패: $ROOT/.venv/bin/python을 사용할 수 없습니다. $logs/project-uv.log를 확인하고 $setup_command 명령을 다시 실행하세요." ;;
        esac
    fi
    if [ -t 2 ] && [ -z "${NO_COLOR:-}" ] && [ "$json_output" = false ]; then
        printf '\033[31m%s\033[0m\n' "$message" >&2
    else
        printf '%s\n' "$message" >&2
    fi
    exit 2
}

prerequisite_warning() {
    message=$*
    if [ "$language" = ko ]; then
        case "$message" in
            'Host OS unavailable or unsupported:'*) message='호스트 OS를 사용할 수 없거나 지원하지 않습니다. Mac/Ubuntu에서 uname -s를 확인하세요.' ;;
            'Git unavailable.'*) message='Git을 사용할 수 없습니다. Mac: xcode-select --install; Ubuntu: sudo apt install git.' ;;
            'Docker CLI unavailable.'*) message='Docker CLI를 사용할 수 없습니다. Mac: Docker Desktop https://docs.docker.com/desktop/setup/install/mac-install/ ; Ubuntu: Docker Engine과 Compose https://docs.docker.com/engine/install/ubuntu/' ;;
            'Docker daemon unavailable.'*) message='Docker daemon을 사용할 수 없습니다. Mac: Docker Desktop 실행; Ubuntu: sudo systemctl start docker 후 소켓 권한 확인 https://docs.docker.com/engine/install/linux-postinstall/' ;;
            'Docker Compose unavailable.'*) message='Docker Compose를 사용할 수 없습니다. Desktop 갱신 또는 docker-compose-plugin 설치: https://docs.docker.com/compose/install/linux/' ;;
            'CA-enabled builds require docker buildx;'*) message='CA 사용 빌드에는 docker buildx가 필요합니다. docker-buildx-plugin 설치 후 setup을 다시 실행하세요.' ;;
        esac
    fi
    printf '%s\n' "$message" >&2
}

setup_status() {
    message=$2
    if [ "$language" = ko ]; then
        case "$message" in
            '[setup] core prerequisites: checking host OS and Git')
                message='[setup] 코어 사전 준비: 호스트 OS와 Git 검사' ;;
            '[setup] prerequisites: checking Git, Docker daemon and Compose')
                message='[setup] 사전 준비: Git·Docker daemon·Compose 검사' ;;
            '[setup] prerequisites: complete') message='[setup] 사전 준비: 완료' ;;
            '[setup] uv preparation: installing 0.10.7; log: '*)
                message="[setup] uv 준비: 0.10.7 설치; 로그: ${message#*; log: }" ;;
            '[setup] project Python and frozen dependencies; log: '*)
                message="[setup] 프로젝트 Python과 고정 의존성 준비; 로그: ${message#*; log: }" ;;
            '[setup] project Python and frozen dependencies: complete')
                message='[setup] 프로젝트 Python과 고정 의존성 준비: 완료' ;;
        esac
    fi
    if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
        printf '\033[%sm%s\033[0m\n' "$1" "$message"
    else
        printf '%s\n' "$message"
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
        if [ "$language" = en ]; then
            printf '%s\n' 'menu: interactive numbered menu (TTY and Python >=3.11 required).' \
                'Run sh scripts/bootstrap.sh menu. For automation use setup/doctor/demo/live.'
        else
            printf '%s\n' 'menu: 대화형 번호 메뉴(TTY와 Python >=3.11 필요).' \
                'sh scripts/bootstrap.sh menu로 실행하세요. 자동화에는 setup/doctor/demo/live 명령을 사용하세요.'
        fi
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
        if [ "$language" = ko ]; then
            printf '%s 검사 15초 시간 초과; 도구/연결을 수정하고 sh scripts/bootstrap.sh %s 명령을 다시 실행하세요.\n' "$label" "$command" >&2
        else
            printf '%s timed out after 15s; repair the tool/endpoint and rerun sh scripts/bootstrap.sh %s.\n' "$label" "$command" >&2
        fi
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
    prerequisite_warning 'Host OS unavailable or unsupported: use Mac or Ubuntu; check uname -s.'
    missing=true
fi
if ! command -v git >/dev/null 2>&1 || ! short_probe 'setup prerequisites: Git' git --version; then
    prerequisite_warning 'Git unavailable. Mac: xcode-select --install; Ubuntu: sudo apt install git.'
    missing=true
fi
if [ "$core" = false ] && [ -z "$dataset" ]; then
    if ! command -v docker >/dev/null 2>&1; then
        prerequisite_warning 'Docker CLI unavailable. Mac: install/open Docker Desktop https://docs.docker.com/desktop/setup/install/mac-install/ ; Ubuntu: install Engine + Compose plugin https://docs.docker.com/engine/install/ubuntu/'
        missing=true
    else
        if ! short_probe 'setup prerequisites: Docker daemon' docker info; then
            prerequisite_warning 'Docker daemon unavailable. Mac: open Docker Desktop; Ubuntu: sudo systemctl start docker, then check docker info and socket permissions: https://docs.docker.com/engine/install/linux-postinstall/'
            missing=true
        fi
        if ! short_probe 'setup prerequisites: Docker Compose' docker compose version; then
            prerequisite_warning 'Docker Compose unavailable. Mac: update Docker Desktop; Ubuntu: install docker-compose-plugin from the Docker apt repository: https://docs.docker.com/compose/install/linux/'
            missing=true
        fi
        if [ -n "${AGENT_OPT_CA_BUNDLE:-}" ] && [ "$offline" = false ] &&
            ! short_probe 'setup prerequisites: Docker Buildx' docker buildx version; then
            prerequisite_warning 'CA-enabled builds require docker buildx; install docker-buildx-plugin and rerun setup.'
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
