"""사람에게 표시하는 문구의 언어를 고릅니다. 실행 데이터는 번역하지 않습니다."""

import os


MESSAGES = {
    "remedy": ("해결", "Remedy"),
}


def current_language(raw: str | None = None) -> str:
    selected = os.environ.get("AGENT_OPT_LANG", "") if raw is None else raw
    if selected in ("", "ko"):
        return "ko"
    if selected == "en":
        return "en"
    raise ValueError("AGENT_OPT_LANG must be ko or en")


def t(key: str, *, lang: str | None = None, **values: object) -> str:
    ko, en = MESSAGES[key]
    return (en if (lang or current_language()) == "en" else ko).format(**values)
