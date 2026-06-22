"""Provider selection and lazy SDK-client construction."""
from __future__ import annotations

from cua.providers.anthropic import AnthropicProvider
from cua.providers.openai import OpenAIProvider
from cua.executors.web import WebExecutor
from cua.executors.desktop import DesktopExecutor


def build_provider(name: str, *, client=None, display_size: tuple[int, int] = (1280, 800)):
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
        return OpenAIProvider(client=client, display_size=display_size)
    raise ValueError(f"Unknown provider: {name!r} (expected 'claude' or 'openai')")


def build_executor(name, *, page=None, client=None, display_size=(1280, 800)):
    key = name.strip().lower()
    if key == "web":
        if page is None:
            raise RuntimeError(
                "build_executor('web') without an injected page requires launching "
                "Playwright; pass page=<playwright page> or launch it in the caller"
            )
        return WebExecutor(page=page, display_size=display_size)
    if key == "desktop":
        if client is None:
            import httpx  # lazy; only needed for the real HTTP client
            client = httpx.AsyncClient()
        return DesktopExecutor(client=client, display_size=display_size)
    raise ValueError(f"unknown executor: {name!r}")
