"""Provider selection and lazy SDK-client construction."""
from __future__ import annotations

import sys

from cua.providers.anthropic import AnthropicProvider
from cua.providers.openai import OpenAIProvider
from cua.providers.vision.provider import GenericVisionProvider
from cua.executors.web import WebExecutor
from cua.executors.local import LocalExecutor


_PLATFORM_ENVIRONMENT = {"win32": "windows", "darwin": "mac"}


def environment_for_executor(executor_name: str, platform: str | None = None) -> str:
    """Map an executor backend to the OpenAI computer-use `environment` value.

    web   -> browser
    local -> the real host OS (windows/mac/linux) it is actually driving
    """
    key = executor_name.strip().lower()
    if key == "web":
        return "browser"
    plat = platform if platform is not None else sys.platform
    return _PLATFORM_ENVIRONMENT.get(plat, "linux")


def build_provider(name: str, *, client=None, display_size: tuple[int, int] = (1280, 800),
                   environment: str | None = None, page=None):
    key = name.strip().lower()
    if key == "claude":
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        return AnthropicProvider(client=client, display_size=display_size)
    if key == "openai":
        if client is None:
            import openai
            client = openai.OpenAI()
        if environment is not None:
            return OpenAIProvider(client=client, display_size=display_size,
                                  environment=environment)
        return OpenAIProvider(client=client, display_size=display_size)
    if key in ("generic", "vision"):
        if client is None:
            import openai  # lazy
            client = openai.OpenAI()
        return GenericVisionProvider(client=client, display_size=display_size)
    if key in ("browser", "dom"):
        # DOM Set-of-Marks over a vision chat model — drives the same Playwright page.
        if page is None:
            raise RuntimeError(
                "build_provider('browser') needs the Playwright page it should read "
                "the DOM from; pass page=<playwright page> (use it with --executor web)"
            )
        if client is None:
            import openai  # lazy
            client = openai.OpenAI()
        from cua.providers.browser.provider import DomVisionProvider
        return DomVisionProvider(client=client, page=page, display_size=display_size)
    raise ValueError(
        f"Unknown provider: {name!r} (expected 'claude', 'openai', 'generic', "
        "'vision', or 'browser')")


def build_executor(name, *, page=None, display_size=(1280, 800)):
    key = name.strip().lower()
    if key == "web":
        if page is None:
            raise RuntimeError(
                "build_executor('web') without an injected page requires launching "
                "Playwright; pass page=<playwright page> or launch it in the caller"
            )
        return WebExecutor(page=page, display_size=display_size)
    if key in ("local", "host"):
        # Drives the REAL host desktop via pyautogui — no sandbox.
        return LocalExecutor(display_size=display_size)
    raise ValueError(f"unknown executor: {name!r}")
