"""argparse 기본 안내 문구를 프로젝트 사용자 언어로 표시합니다."""

import argparse

from agent_optimizer.locale import current_language


class KoreanArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if current_language() == "ko":
            self._positionals.title = "위치 인수"
            self._optionals.title = "옵션"
            for action in self._actions:
                if action.dest == "help":
                    action.help = "도움말 표시 후 종료"

    def format_help(self):
        output = super().format_help()
        return output.replace("usage: ", "사용법: ", 1) if current_language() == "ko" else output

    def format_usage(self):
        output = super().format_usage()
        return output.replace("usage: ", "사용법: ", 1) if current_language() == "ko" else output
