#!/bin/sh
# Convert Make ARGS data into argv without invoking a shell parser or eval.
set -eu
bootstrap=$1
command=$2

fail_args() {
    case "$1" in
        operation) korean='셸 연산은 옵션으로 전달할 수 없습니다'; english='shell operations are not options' ;;
        quote) korean='닫히지 않은 따옴표가 있습니다'; english='unclosed quote' ;;
    esac
    if [ "${AGENT_OPT_LANG:-ko}" = en ]; then
        printf 'Invalid Make ARGS: %s. See sh scripts/bootstrap.sh %s --help.\n' "$english" "$command" >&2
    else
        printf '잘못된 Make ARGS: %s. sh scripts/bootstrap.sh %s --help를 확인하세요.\n' "$korean" "$command" >&2
    fi
    exit 2
}

remaining=${AGENT_OPT_MAKE_ARGS:-}
set --
word=
quoted=
started=false
tab=$(printf '\t')
newline='
'
while [ -n "$remaining" ]; do
    character=${remaining%"${remaining#?}"}
    remaining=${remaining#?}
    case "$character" in
        '$'|'`'|';'|'|'|'&'|'<'|'>'|'('|')'|'\'|"$newline")
            fail_args operation ;;
    esac
    if [ -n "$quoted" ]; then
        if [ "$character" = "$quoted" ]; then quoted=; else word=$word$character; fi
    else
        case "$character" in
            "'"|'"') quoted=$character; started=true ;;
            ' '|"$tab")
                if [ "$started" = true ]; then
                    set -- "$@" "$word"
                    word=
                    started=false
                fi ;;
            *) word=$word$character; started=true ;;
        esac
    fi
done
[ -z "$quoted" ] || fail_args quote
if [ "$started" = true ]; then set -- "$@" "$word"; fi
exec sh "$bootstrap" "$command" "$@"
