"""Meta-Harness가 변경할 실제 native 역할 guidance 조립 표면."""


def guidance(role, text):
    return f"역할: {role}\n공개 계약과 target 전체를 확인하세요.\n{text}"
