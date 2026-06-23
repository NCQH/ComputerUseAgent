import pytest
from cua.config import build_provider, environment_for_executor
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


def test_build_openai_threads_environment():
    p = build_provider("openai", client=object(), environment="windows")
    assert p.environment == "windows"


def test_build_openai_defaults_to_browser_when_unset():
    p = build_provider("openai", client=object())
    assert p.environment == "browser"


def test_environment_for_executor_maps_backends():
    assert environment_for_executor("web") == "browser"
    assert environment_for_executor("local", platform="win32") == "windows"
    assert environment_for_executor("host", platform="darwin") == "mac"
    assert environment_for_executor("local", platform="linux") == "linux"
