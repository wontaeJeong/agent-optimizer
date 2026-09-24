"""argparse 기본 안내 문구를 프로젝트 사용자 언어로 표시합니다."""

import argparse


class KoreanArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._positionals.title = "위치 인수"
        self._optionals.title = "옵션"
        for action in self._actions:
            if action.dest == "help":
                action.help = "도움말 표시 후 종료"

    def format_help(self):
        return super().format_help().replace("usage: ", "사용법: ", 1)

    def format_usage(self):
        return super().format_usage().replace("usage: ", "사용법: ", 1)
