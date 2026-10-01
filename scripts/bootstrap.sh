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
            'Start: make setup-core → make doctor-core → make demo.' \
            'Without make, use sh scripts/bootstrap.sh <command> [options].' \
            'setup/doctor without --core or --dataset target the full ACE environment.' \
            'setup: --core, --dataset ID, --offline, --platform linux/amd64|linux/arm64 (full ACE only)' \
            'doctor: --core, --dataset ID, --json, --platform, --model (calls the real API). --core cannot be combined with --dataset/--platform/--model.' \
            'smoke/live: --platform; live: --iterations 1..20' \
            'menu: interactive numbered menu (TTY required). After setup, run .venv/bin/agent-opt --help for user commands.' \
            'test/lint/demo use the existing .venv without installation or Docker.' \
            'make doctor ARGS="--json" (ARGS accepts quoted options, not shell operations).' \
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
        '기존 외부 코어 환경은 AGENT_OPT_CORE_PYTHON=/절대/venv/bin/python으로 명시합니다. setup의 설치 대상은 바꾸지 않습니다.' \
        'make doctor ARGS="--json" (ARGS에는 인용된 옵션을 쓰고 셸 연산은 넣지 않습니다).' \
        '상세 옵션: python3 scripts/dev.py --help 또는 python3 scripts/dev.py <명령> --help.'
}

command_help() {
    if [ "$language" = en ]; then
        case "$1" in
            setup) printf '%s\n' 'setup: --core prepares .venv and a synthetic demo; --dataset ID prepares one selected dataset; no selector prepares full ACE.' \
                '--offline skips downloads/builds but still syncs, diagnoses and runs a core/full demo; --platform linux/amd64|linux/arm64 is full ACE only.' \
                '--core and --dataset conflict; either conflicts with --platform. Setup may download dependencies/data and build Docker images; results: runs/<run-id>/report.html.' ;;
            doctor) printf '%s\n' 'doctor: --core checks core; --dataset ID checks selected assets; no selector checks full ACE.' \
                '--json prints one JSON object; --model calls the real API and container tools for full ACE.' \
                '--core and --dataset conflict; either conflicts with --platform/--model. No installation; ready is not Agent/model execution success.' ;;
            test) printf '%s\n' 'test: run unittest in the existing .venv; no installation. Repair: sh scripts/bootstrap.sh setup --core.' ;;
            lint) printf '%s\n' 'lint: run Ruff in the existing .venv; no installation. Repair: sh scripts/bootstrap.sh setup --core.' ;;
            demo) printf '%s\n' 'demo: run synthetic fixture in the existing .venv without Docker/model; creates runs/<run-id>/report.html. Repair: setup --core.' ;;
            smoke) printf '%s\n' 'smoke: [--platform linux/amd64|linux/arm64] check prepared ACE Docker/tools and official positive/negative evaluation without a model.' \
                'First run setup (full ACE); result: runs/dev-smoke-*/summary.json.' ;;
            live) printf '%s\n' 'live: [--platform linux/amd64|linux/arm64] [--iterations 1..20] run actual model/Agent/official evaluator; default 3.' \
                'Requires full setup and model credentials; results: runs/dev-live/<run-id>/report.html.' ;;
            menu) printf '%s\n' 'menu: interactive numbered menu (TTY and Python >=3.11 required).' \
                'Run sh scripts/bootstrap.sh menu. For automation use setup/doctor/demo/live.' ;;
        esac
    else
        case "$1" in
            setup) printf '%s\n' 'setup: --core는 .venv와 합성 데모, --dataset ID는 선택 데이터셋, 선택자 없으면 ACE 전체를 준비합니다.' \
                '--offline은 다운로드·빌드 없이 캐시 동기화·진단·코어/전체 데모를 실행합니다; --platform linux/amd64|linux/arm64는 ACE 전체 전용입니다.' \
                '--core와 --dataset은 충돌하며 둘 다 --platform과 함께 쓸 수 없습니다. 의존성/데이터 다운로드·Docker 빌드 가능; 결과: runs/<run-id>/report.html.' ;;
            doctor) printf '%s\n' 'doctor: --core 코어, --dataset ID 선택 자산, 선택자 없으면 ACE 전체를 읽기 전용 진단합니다.' \
                '--json은 단일 JSON; --model은 ACE 전체의 실제 API·컨테이너 도구를 호출합니다.' \
                '--core와 --dataset은 충돌하며 둘 다 --platform/--model과 함께 쓸 수 없습니다. 설치 없음; ready는 Agent/모델 실행 성공이 아닙니다.' ;;
            test) printf '%s\n' 'test: 기존 .venv에서 unittest 실행; 설치 없음. 복구: sh scripts/bootstrap.sh setup --core.' ;;
            lint) printf '%s\n' 'lint: 기존 .venv에서 Ruff 실행; 설치 없음. 복구: sh scripts/bootstrap.sh setup --core.' ;;
            demo) printf '%s\n' 'demo: 기존 .venv에서 Docker/모델 없는 합성 fixture 실행; runs/<run-id>/report.html 생성. 복구: setup --core.' ;;
            smoke) printf '%s\n' 'smoke: [--platform linux/amd64|linux/arm64] 준비된 ACE Docker/도구와 공식 정답·오답 평가 검사; 모델 호출 없음.' \
                '먼저 전체 setup을 실행하세요. 결과: runs/dev-smoke-*/summary.json.' ;;
            live) printf '%s\n' 'live: [--platform linux/amd64|linux/arm64] [--iterations 1..20] 실제 모델·Agent·공식 평가 실행; 기본 3회.' \
                '전체 setup과 모델 인증 필요; 결과: runs/dev-live/<run-id>/report.html.' ;;
            menu) printf '%s\n' 'menu: 대화형 번호 메뉴(TTY와 Python >=3.11 필요).' \
                'sh scripts/bootstrap.sh menu로 실행하세요. 자동화에는 setup/doctor/demo/live 명령을 사용하세요.' ;;
        esac
    fi
}

fail() {
    message=$*
    if [ "$language" = ko ]; then
        case "$message" in
            'help takes no options') message='help 명령에는 옵션을 지정할 수 없습니다' ;;
            'Unknown command: '*) message="알 수 없는 명령: ${message#Unknown command: }" ;;
            'Unsupported option for '*)
                detail=${message#Unsupported option for }
                detail=${detail%. Run sh scripts/bootstrap.sh * --help.}
                message="지원하지 않는 옵션 ($detail). sh scripts/bootstrap.sh $command --help를 실행하세요." ;;
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
    if [ "${setup_command+x}" != x ] && [ "$command" != help ]; then
        if [ "$language" = ko ]; then
            printf '수정할 명령을 확인하세요: sh scripts/bootstrap.sh %s --help\n' "$command" >&2
        else
            printf 'Check a valid command: sh scripts/bootstrap.sh %s --help\n' "$command" >&2
        fi
    fi
    exit 2
}

prerequisite_warning() {
    original_message=$*
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
    case "$original_message" in
        'Host OS unavailable or unsupported:'*)
            prerequisite_diagnostic 'core.host' 'unsupported-host' 'host' 'uname -s' ;;
        'Git unavailable.'*)
            prerequisite_diagnostic 'core.git' 'missing-git' 'git' 'git --version' ;;
        'Docker CLI unavailable.'*)
            prerequisite_diagnostic 'docker.cli' 'missing-docker' 'docker-cli' 'docker --version' ;;
        'Docker daemon unavailable.'*)
            prerequisite_diagnostic 'docker.daemon' 'daemon' 'docker-daemon' 'docker info' ;;
        'Docker Compose unavailable.'*)
            prerequisite_diagnostic 'docker.compose' 'missing-compose' 'docker-compose' 'docker compose version' ;;
        'CA-enabled builds require docker buildx;'*)
            prerequisite_diagnostic 'docker.buildx' 'missing-buildx' 'docker-buildx' 'docker buildx version' ;;
    esac
}

prerequisite_diagnostic() {
    check_id=$1
    cause_key=$2
    fix_key=$3
    retry_command=$4
    if [ "$language" = ko ]; then
        case "$cause_key" in
            unsupported-host) cause='호스트 OS 또는 Python 버전이 지원되지 않습니다' ;;
            missing-git) cause='git 실행 파일을 찾을 수 없습니다' ;;
            missing-docker) cause='docker 실행 파일을 찾을 수 없습니다' ;;
            daemon) cause='docker info 실패: daemon 중지 또는 Docker socket 권한 문제' ;;
            missing-compose) cause='Docker Compose plugin을 사용할 수 없습니다' ;;
            missing-buildx) cause='Docker Buildx plugin을 사용할 수 없습니다' ;;
        esac
        case "$fix_key" in
            host) fix='Mac/Ubuntu와 Python 3.11+를 사용하세요.' ;;
            git) fix='Git을 설치하고 실행 권한을 확인하세요.' ;;
            docker-cli) fix='Docker CLI를 설치하세요.' ;;
            docker-daemon) fix='Docker Desktop/Engine을 시작하고 현재 사용자의 socket 접근 권한을 확인하세요.' ;;
            docker-compose) fix='Docker Compose plugin을 설치하거나 Docker Desktop을 갱신하세요.' ;;
            docker-buildx) fix='Docker Buildx plugin을 설치하세요.' ;;
        esac
        printf '[error] %s: 준비되지 않았습니다\n  원인: %s\n  해결: %s\n  재실행: %s\n' \
            "$check_id" "$cause" "$fix" "$retry_command" >&2
    else
        case "$cause_key" in
            unsupported-host) cause='Host OS or Python version is unsupported' ;;
            missing-git) cause='git executable was not found' ;;
            missing-docker) cause='docker executable was not found' ;;
            daemon) cause='docker info failed: daemon stopped or Docker socket permission denied' ;;
            missing-compose) cause='Docker Compose plugin is unavailable' ;;
            missing-buildx) cause='Docker Buildx plugin is unavailable' ;;
        esac
        case "$fix_key" in
            host) fix='Use Mac/Ubuntu with Python 3.11+.' ;;
            git) fix='Install Git and check execution permissions.' ;;
            docker-cli) fix='Install the Docker CLI.' ;;
            docker-daemon) fix='Start Docker Desktop/Engine and check the current user socket access.' ;;
            docker-compose) fix='Install the Docker Compose plugin or update Docker Desktop.' ;;
            docker-buildx) fix='Install the Docker Buildx plugin.' ;;
        esac
        printf '[error] %s: not ready\n  Cause: %s\n  Fix: %s\n  Retry: %s\n' \
            "$check_id" "$cause" "$fix" "$retry_command" >&2
    fi
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

setup_log_cause() {
    log_file=$1
    [ -r "$log_file" ] || { printf '%s' 'unknown'; return; }
    category=$(awk '
        {
            line = tolower($0)
            if (line ~ /(x509|certificate|unknown authority|tls|ssl)/) cause_kind = "tls"
            else if (line ~ /(could not resolve|name resolution|dns|network is unreachable|connection refused)/) cause_kind = "dns"
            else if (line ~ /(permission denied|operation not permitted)/) cause_kind = "permission"
            else if (line ~ /(not found in cache|cache miss|no cached distribution)/) cause_kind = "cache"
            else if (line ~ /(no solution found|lockfile|platform mismatch)/) cause_kind = "lock"
            else if (line ~ /(no such file|executable not found)/) cause_kind = "missing"
        }
        END { if (cause_kind == "") print "unknown"; else print cause_kind }
    ' "$log_file")
    printf '%s' "$category"
}

setup_failure() {
    failure_stage=$1
    failure_cause=$2
    failure_log=$3
    failure_fix=$4
    failure_retry=$5
    if [ "$failure_fix" = offline ] && [ "$offline" = true ]; then
        failure_fix=offline-cache
    fi
    if [ "$language" = ko ]; then
        case "$failure_stage" in
            uv-download) failure_stage='uv 다운로드' ;;
            uv-installer) failure_stage='uv installer' ;;
            project-sync) failure_stage='프로젝트 의존성 동기화' ;;
            project-sync-offline) failure_stage='프로젝트 오프라인 동기화' ;;
            project-python) failure_stage='프로젝트 Python 검증' ;;
            python-dispatch) failure_stage='Python 실행 전달' ;;
            existing-venv) failure_stage='기존 프로젝트 .venv 검증' ;;
            network-configuration) failure_stage='네트워크/CA 설정' ;;
        esac
        case "$failure_cause" in
            tls) failure_cause='TLS 인증서 검증에 실패했습니다' ;;
            dns) failure_cause='DNS 또는 네트워크 연결에 실패했습니다' ;;
            permission) failure_cause='실행 권한 또는 socket 권한이 거부되었습니다' ;;
            cache) failure_cause='필요한 패키지가 오프라인 cache에 없습니다' ;;
            lock) failure_cause='dependency lock 또는 platform 설정이 일치하지 않습니다' ;;
            missing) failure_cause='필요한 실행 파일이나 파일을 찾을 수 없습니다' ;;
            offline-uv) failure_cause='오프라인 setup에 uv가 없습니다' ;;
            invalid) failure_cause='기존 Python virtualenv가 호환되지 않습니다' ;;
            configuration) failure_cause='선택한 network 또는 CA 설정이 잘못되었습니다' ;;
            *) failure_cause='하위 명령이 비정상 종료했습니다' ;;
        esac
        case "$failure_fix" in
            network) failure_fix='네트워크, proxy 및 CA trust 설정을 확인하세요.' ;;
            installer) failure_fix='로그 원인을 확인하고 uv 설치/실행 권한을 수정하세요.' ;;
            dependencies) failure_fix='Python, uv와 고정 의존성 lock을 확인하세요.' ;;
            offline) failure_fix='먼저 online setup으로 누락된 package cache를 준비하세요.' ;;
            offline-cache) failure_fix="먼저 online setup으로 누락된 package cache를 준비한 뒤 다음 오프라인 명령을 실행하세요: $setup_retry_command" ;;
            filesystem) failure_fix='프로젝트 setup 경로의 쓰기 권한과 여유 공간을 확인하세요.' ;;
            downloader) failure_fix='curl 또는 wget을 설치한 뒤 setup을 다시 실행하세요.' ;;
            python) failure_fix='Python 3.11+ 설치와 프로젝트 .venv 실행 권한을 확인하세요.' ;;
            venv) failure_fix='기존 .venv를 보존해 옮긴 뒤 setup을 다시 실행하세요.' ;;
        esac
    else
        case "$failure_cause" in
            tls) failure_cause='TLS certificate verification failed' ;;
            dns) failure_cause='DNS or network connection failed' ;;
            permission) failure_cause='Executable or socket permission denied' ;;
            cache) failure_cause='Required package is missing from the offline cache' ;;
            lock) failure_cause='Dependency lock or platform configuration mismatch' ;;
            missing) failure_cause='Required executable or file was not found' ;;
            offline-uv) failure_cause='uv is missing for offline setup' ;;
            invalid) failure_cause='Existing project virtualenv is incompatible' ;;
            configuration) failure_cause='Selected network or CA configuration is invalid' ;;
            *) failure_cause='Child command exited unsuccessfully' ;;
        esac
        case "$failure_fix" in
            network) failure_fix='Check network, proxy, and CA trust settings.' ;;
            installer) failure_fix='Inspect the log cause and repair uv installation or execution permissions.' ;;
            dependencies) failure_fix='Check Python, uv, and the frozen dependency lock.' ;;
            offline) failure_fix='Prepare the missing package cache with online setup first.' ;;
            offline-cache) failure_fix="Prepare the missing package cache online, then rerun offline with: $setup_retry_command" ;;
            filesystem) failure_fix='Check write permissions and available space for setup paths.' ;;
            downloader) failure_fix='Install curl or wget, then rerun setup.' ;;
            python) failure_fix='Check Python 3.11+ installation and project .venv execution permissions.' ;;
            venv) failure_fix='Preserve and move the existing .venv aside, then rerun setup.' ;;
        esac
    fi
    if [ -n "$failure_log" ]; then
        case "$failure_log" in "$ROOT"/*) failure_log=${failure_log#"$ROOT"/} ;; esac
    fi
    if [ "$language" = ko ]; then
        printf '[setup] %s: 실패\n  원인: %s\n' "$failure_stage" "$failure_cause" >&2
        [ -z "$failure_log" ] || printf '  로그: %s\n' "$failure_log" >&2
        printf '  해결: %s\n  재실행: %s\n' "$failure_fix" "$failure_retry" >&2
    else
        printf '[setup] %s: failed\n  Cause: %s\n' "$failure_stage" "$failure_cause" >&2
        [ -z "$failure_log" ] || printf '  Log: %s\n' "$failure_log" >&2
        printf '  Fix: %s\n  Retry: %s\n' "$failure_fix" "$failure_retry" >&2
    fi
    exit 2
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
selected_platform=
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
        selected_platform=$option
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
            selected_platform=${option#*=}
            if [ "$command" != doctor ]; then
                case "${option#*=}" in linux/amd64|linux/arm64) ;; *) fail "Unsupported platform: $option" ;; esac
            fi ;;
        *) fail "Unsupported option for $command: $option. Run sh scripts/bootstrap.sh $command --help." ;;
    esac
done
[ "$want_platform" = false ] || fail '--platform requires linux/amd64 or linux/arm64'
[ "$want_iterations" = false ] || fail '--iterations requires 1..20'
[ "$want_dataset" = false ] || fail '--dataset requires an identifier'
if [ "$command" = doctor ] && [ "$selected_platform" ]; then
    for option do
        if [ "$option" = --model ]; then
            case "$selected_platform" in linux/amd64|linux/arm64) ;; *) fail '--platform requires linux/amd64 or linux/arm64' ;; esac
        fi
    done
fi
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
if [ -n "$selected_platform" ]; then
    setup_command="$setup_command --platform $selected_platform"
fi
setup_retry_command=$setup_command
if [ "$offline" = true ]; then
    setup_retry_command="$setup_command --offline"
fi
if [ "$show_help" = true ]; then
    command_help "$command"
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
    if [ -n "${AGENT_OPT_CORE_PYTHON:-}" ]; then
        case "$AGENT_OPT_CORE_PYTHON" in /*) ;; *) fail 'AGENT_OPT_CORE_PYTHON에는 기존 interpreter 절대경로가 필요합니다' ;; esac
        compatible_python "$AGENT_OPT_CORE_PYTHON" || fail 'AGENT_OPT_CORE_PYTHON interpreter를 사용할 수 없습니다'
        python="$AGENT_OPT_CORE_PYTHON"
    elif compatible_python "$ROOT/.venv/bin/python"; then
        python="$ROOT/.venv/bin/python"
    elif command -v python3 >/dev/null 2>&1 && compatible_python python3; then
        python=python3
    elif command -v python >/dev/null 2>&1 && compatible_python python; then
        python=python
    else
        fail "Python >=3.11 is unavailable. Run $setup_retry_command; no installation was attempted."
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
        setup_failure network-configuration configuration "" network "$setup_retry_command"
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
[ "$missing" = false ] || fail "setup prerequisites failed; repair the items above and rerun $setup_retry_command."
setup_status 32 '[setup] prerequisites: complete'

stage='uv preparation'
logs="$ROOT/external/setup-logs"
trap 'stop_setup_progress; printf "setup interrupted during %s; inspect %s and rerun %s.\n" "$stage" "$logs" "$setup_retry_command" >&2; exit 130' HUP INT TERM
trap 'stop_setup_progress' EXIT
if ! command -v uv >/dev/null 2>&1; then
    [ "$offline" = false ] || setup_failure uv-installer offline-uv "" offline "$setup_command"
    downloader=
    if command -v curl >/dev/null 2>&1; then downloader=curl
    elif command -v wget >/dev/null 2>&1; then downloader=wget
    else setup_failure uv-download missing "" downloader "$setup_retry_command"
    fi
    mkdir -p "$logs" 2>/dev/null ||
        setup_failure uv-installer permission "$logs" filesystem "$setup_retry_command"
    setup_status 33 "[setup] uv preparation: installing 0.10.7; log: $logs/bootstrap-uv.log"
    installer=$(mktemp "${TMPDIR:-/tmp}/agent-opt-uv.XXXXXXXX" 2>/dev/null) ||
        setup_failure uv-download permission "" filesystem "$setup_retry_command"
    : > "$logs/bootstrap-uv.log" 2>/dev/null ||
        setup_failure uv-installer permission "$logs/bootstrap-uv.log" filesystem "$setup_retry_command"
    wget_config=
    trap 'stop_setup_progress; rm -f "$installer"; [ -z "$wget_config" ] || rm -f "$wget_config"' EXIT
    if [ "$downloader" = wget ] && [ -n "${AGENT_OPT_CA_BUNDLE:-}" ]; then
        # The pinned installer invokes wget again for the archive; CLI flags on
        # only the first download would lose trust. Preserve user configuration.
        case "$AGENT_OPT_CA_BUNDLE" in
            *'
'*|*"$(printf '\r')"*) fail 'AGENT_OPT_CA_BUNDLE must not contain line breaks.' ;;
        esac
        wget_config=$(mktemp "${TMPDIR:-/tmp}/agent-opt-wget.XXXXXXXX" 2>/dev/null) ||
            setup_failure uv-download permission "" filesystem "$setup_retry_command"
        if [ -f "${WGETRC:-$HOME/.wgetrc}" ]; then
            if ! cat "${WGETRC:-$HOME/.wgetrc}" > "$wget_config" 2>>"$logs/bootstrap-uv.log"; then
                setup_failure uv-download permission "$logs/bootstrap-uv.log" filesystem "$setup_retry_command"
            fi
        fi
        printf '\nca_certificate = %s\n' "$AGENT_OPT_CA_BUNDLE" >> "$wget_config"
        # Subshell scopes WGETRC to both downloads without changing later tools.
    fi
    url=https://astral.sh/uv/0.10.7/install.sh
    start_setup_progress 'uv installer'
    (
        if [ -n "$wget_config" ]; then export WGETRC="$wget_config"; fi
        if [ "$downloader" = curl ]; then
            if ! curl -fLsS "$url" -o "$installer" 2>>"$logs/bootstrap-uv.log"; then
                setup_failure uv-download "$(setup_log_cause "$logs/bootstrap-uv.log")" \
                    "$logs/bootstrap-uv.log" network "$setup_command"
            fi
        else
            if ! wget -q "$url" -O "$installer" 2>>"$logs/bootstrap-uv.log"; then
                setup_failure uv-download "$(setup_log_cause "$logs/bootstrap-uv.log")" \
                    "$logs/bootstrap-uv.log" network "$setup_command"
            fi
        fi
        if ! UV_INSTALL_DIR="$ROOT/.cache/uv/bin" UV_NO_MODIFY_PATH=1 sh "$installer" \
                >>"$logs/bootstrap-uv.log" 2>&1; then
            setup_failure uv-installer "$(setup_log_cause "$logs/bootstrap-uv.log")" \
                "$logs/bootstrap-uv.log" installer "$setup_command"
        fi
    ) || exit 2
    stop_setup_progress
    rm -f "$installer"
    [ -z "$wget_config" ] || rm -f "$wget_config"
    trap - EXIT
    command -v uv >/dev/null 2>&1 || setup_failure uv-installer missing \
        "$logs/bootstrap-uv.log" installer "$setup_command"
fi

trap 'stop_setup_progress' EXIT
stage='project Python and frozen dependencies'
python_request=3.12
if [ -e "$ROOT/.venv" ] || [ -L "$ROOT/.venv" ]; then
    # Preserve even an invalid environment; uv must not silently replace it.
    short_probe 'setup existing project Python check' "$ROOT/.venv/bin/python" -I -B -c 'import sys; from pathlib import Path; assert sys.version_info >= (3, 11); assert sys.prefix != sys.base_prefix; assert Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve()' "$ROOT/.venv" ||
        setup_failure existing-venv invalid "" venv "$setup_retry_command"
    python_request="$ROOT/.venv/bin/python"
fi
mkdir -p "$logs" 2>/dev/null ||
    setup_failure project-sync permission "$logs" filesystem "$setup_retry_command"
setup_status 33 "[setup] $stage; log: $logs/project-uv.log"
export UV_PROJECT_ENVIRONMENT="$ROOT/.venv"
if [ "$offline" = true ]; then export UV_PYTHON_DOWNLOADS=never; fi
cd "$ROOT"
start_setup_progress "$stage"
if [ "$offline" = true ]; then
    if ! uv --offline sync --frozen --python "$python_request" --extra dev >"$logs/project-uv.log" 2>&1; then
        setup_failure project-sync-offline "$(setup_log_cause "$logs/project-uv.log")" \
            "$logs/project-uv.log" offline "$setup_command"
    fi
else
    if ! uv sync --frozen --python "$python_request" --extra dev >"$logs/project-uv.log" 2>&1; then
        setup_failure project-sync "$(setup_log_cause "$logs/project-uv.log")" \
            "$logs/project-uv.log" dependencies "$setup_command"
    fi
fi
stop_setup_progress
setup_status 32 "[setup] $stage: complete"
stage='Python dispatch'
compatible_python "$ROOT/.venv/bin/python" ||
    setup_failure python-dispatch invalid "$logs/project-uv.log" python "$setup_retry_command"
export AGENT_OPT_BOOTSTRAPPED="$ROOT"
exec "$ROOT/.venv/bin/python" -B "$ROOT/scripts/dev.py" setup "$@"
