import pytest
from cua.app import build_session, validate_display_size
from cua.core.session import AgentSession
from cua.core.events import EventBus
from cua.providers.anthropic import AnthropicProvider
from cua.executors.web import WebExecutor


async def _confirm(_req):
    return True


def test_validate_display_size_rejects_bad_values():
    for bad in [(0, 100), (100, -1), (100,), "1280x800", (1280, 800, 1)]:
        with pytest.raises(ValueError):
            validate_display_size(bad)
    validate_display_size((1280, 800))  # valid → no raise


def test_build_session_wires_claude_web():
    session = build_session(
        "claude", "web",
        confirm_handler=_confirm,
        provider_client=object(),
        page=object(),
        display_size=(800, 600),
    )
    assert isinstance(session, AgentSession)
    assert isinstance(session.provider, AnthropicProvider)
    assert isinstance(session.executor, WebExecutor)
    assert isinstance(session.bus, EventBus)
    assert session.executor.display_size == (800, 600)
    assert session.confirm_handler is _confirm


def test_build_session_rejects_bad_display_size():
    with pytest.raises(ValueError):
        build_session("claude", "web", confirm_handler=_confirm,
                      provider_client=object(), page=object(), display_size=(0, 0))


def test_build_session_desktop_uses_http_client():
    from cua.executors.desktop import DesktopExecutor
    session = build_session(
        "openai", "desktop",
        confirm_handler=_confirm,
        provider_client=object(),
        http_client=object(),
    )
    assert isinstance(session.executor, DesktopExecutor)
