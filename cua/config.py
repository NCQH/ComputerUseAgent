"""Provider selection and lazy SDK-client construction."""
from __future__ import annotations

from cua.providers.anthropic import AnthropicProvider
from cua.providers.openai import OpenAIProvider


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
