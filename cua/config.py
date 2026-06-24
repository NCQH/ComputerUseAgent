"""Provider/executor selection via the registry (SPEC-5) + lazy SDK clients.

Built-ins register a factory next to their peers; `build_provider`/`build_executor`
resolve through the registry. Same construction logic and lazy-import behaviour as
the old if/elif chain — only the dispatch moved.
"""
from __future__ import annotations

import sys

from cua.registry import EXECUTORS, PROVIDERS

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


def _openai_client(client):
    if client is None:
        import openai  # lazy
        client = openai.OpenAI()
    return client


# --- provider factories ------------------------------------------------------

@PROVIDERS.register("claude")
def _build_claude(*, client=None, display_size=(1280, 800), environment=None, page=None):
    from cua.providers.anthropic import AnthropicProvider
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    return AnthropicProvider(client=client, display_size=display_size)


@PROVIDERS.register("openai")
def _build_openai(*, client=None, display_size=(1280, 800), environment=None, page=None):
    from cua.providers.openai import OpenAIProvider
    client = _openai_client(client)
    if environment is not None:
        return OpenAIProvider(client=client, display_size=display_size, environment=environment)
    return OpenAIProvider(client=client, display_size=display_size)


@PROVIDERS.register("generic", "vision")
def _build_generic(*, client=None, display_size=(1280, 800), environment=None, page=None):
    from cua.providers.vision.provider import GenericVisionProvider
    return GenericVisionProvider(client=_openai_client(client), display_size=display_size)


@PROVIDERS.register("browser", "dom")
def _build_browser(*, client=None, display_size=(1280, 800), environment=None, page=None):
    # DOM Set-of-Marks over a vision chat model — drives the same Playwright page.
    if page is None:
        raise RuntimeError(
            "build_provider('browser') needs the Playwright page it should read the "
            "DOM from; pass page=<playwright page> (use it with --executor web)"
        )
    from cua.providers.browser.provider import DomVisionProvider
    return DomVisionProvider(client=_openai_client(client), page=page, display_size=display_size)


@PROVIDERS.register("a11y", "uia")
def _build_a11y(*, client=None, display_size=(1280, 800), environment=None, page=None):
    # Accessibility-tree Set-of-Marks — the desktop twin of 'browser'. Pair with
    # --executor local. Windows UIA backend; degrades to grid/point off-tree.
    from cua.providers.a11y.provider import A11yVisionProvider
    from cua.providers.a11y.uia_backend import UiaBackend
    return A11yVisionProvider(client=_openai_client(client), backend=UiaBackend(),
                              display_size=display_size)


# --- executor factories ------------------------------------------------------

@EXECUTORS.register("web")
def _build_web(*, page=None, display_size=(1280, 800)):
    from cua.executors.web import WebExecutor
    if page is None:
        raise RuntimeError(
            "build_executor('web') without an injected page requires launching "
            "Playwright; pass page=<playwright page> or launch it in the caller"
        )
    return WebExecutor(page=page, display_size=display_size)


@EXECUTORS.register("local", "host")
def _build_local(*, page=None, display_size=(1280, 800)):
    # Drives the REAL host desktop via pyautogui — no sandbox.
    from cua.executors.local import LocalExecutor
    return LocalExecutor(display_size=display_size)


# --- public API (unchanged signatures) --------------------------------------

def build_provider(name: str, *, client=None, display_size: tuple[int, int] = (1280, 800),
                   environment: str | None = None, page=None):
    return PROVIDERS.create(name, client=client, display_size=display_size,
                            environment=environment, page=page)


def build_executor(name, *, page=None, display_size=(1280, 800)):
    return EXECUTORS.create(name, page=page, display_size=display_size)
