"""Session-only model input for interactive experiments."""
from __future__ import annotations

import getpass
import os
import sys
import warnings
from contextlib import contextmanager

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.locale import t
from agent_optimizer.models import ModelSettings


def _ask(label: str) -> str:
    print(label, end="", file=sys.stderr, flush=True)
    try:
        return input().strip()
    except EOFError:
        raise ConfigurationError("모델 설정 입력이 종료되었습니다") from None


def ensure_model_api(env: dict[str, str]) -> dict[str, str]:
    staged = dict(env)
    if staged.get("AGENT_OPT_MODEL_ENDPOINT"):
        ModelSettings.from_env(staged)
    missing = not staged.get("AGENT_OPT_MODEL_BASE_URL") or not staged.get("AGENT_OPT_MODEL_API_KEY")
    if not staged.get("AGENT_OPT_MODEL_BASE_URL"):
        staged["AGENT_OPT_MODEL_BASE_URL"] = _ask("AGENT_OPT_MODEL_BASE_URL: ")
    if missing and not staged.get("AGENT_OPT_MODEL_ID"):
        staged["AGENT_OPT_MODEL_ID"] = _ask("AGENT_OPT_MODEL_ID [glm5.3-flash]: ") or "glm5.3-flash"
    if not staged.get("AGENT_OPT_MODEL_API_KEY"):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                staged["AGENT_OPT_MODEL_API_KEY"] = getpass.getpass(t("모델 API 키 (숨김): "))
        except (EOFError, getpass.GetPassWarning):
            raise ConfigurationError("모델 API 키를 숨겨서 입력할 수 없습니다") from None
    ModelSettings.from_env(staged)
    return staged


def ensure_model_selector(env: dict[str, str], key: str) -> dict[str, str]:
    staged = dict(env)
    if not staged.get(key):
        staged[key] = _ask(t("{key} (OpenCode 모델): ", key=key))
        if not staged[key]:
            raise ConfigurationError(f"{key}를 입력하세요")
    return staged


@contextmanager
def session_environment(env: dict[str, str]):
    previous = dict(os.environ)
    try:
        os.environ.update(env)
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)
