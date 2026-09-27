#!/bin/sh
# ARGS is whitespace-separated data, never shell syntax. No eval, globbing or re-parsing.
set -eu
bootstrap=$1
command=$2
case "${AGENT_OPT_MAKE_ARGS:-}" in
    *\"*|*"'"*)
        if [ "${AGENT_OPT_LANG:-ko}" = en ]; then
            printf '%s\n' "ARGS does not parse quotes; use sh scripts/bootstrap.sh $command [options] or remove unnecessary quotes. See sh scripts/bootstrap.sh $command --help." >&2
        else
            printf '%s\n' "ARGS는 따옴표를 해석하지 않습니다. 불필요한 따옴표를 빼거나 sh scripts/bootstrap.sh $command [옵션]을 사용하세요. sh scripts/bootstrap.sh $command --help" >&2
        fi
        exit 2 ;;
esac
set -f
IFS=' 	
'
# Deliberate word splitting: shell quotes inside ARGS stay literal and fail CLI validation.
# shellcheck disable=SC2086
set -- ${AGENT_OPT_MAKE_ARGS:-}
exec sh "$bootstrap" "$command" "$@"
