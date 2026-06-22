import pytest
from cua.config import build_provider
from cua.providers.anthropic import AnthropicProvider
from cua.providers.openai import OpenAIProvider


def test_build_claude_with_injected_client():
    p = build_provider("claude", client=object(), display_size=(800, 600))
    assert isinstance(p, AnthropicProvider)
    assert p.display_size == (800, 600)


def test_build_openai_case_insensitive():
    p = build_provider("OpenAI", client=object())
    assert isinstance(p, OpenAIProvider)


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        build_provider("gemini", client=object())
