import pytest
from cua.app import build_session, validate_display_size
from cua.core.session import AgentSession
from cua.core.events import EventBus
from cua.core.queue import InputQueue
from cua.core.safety import IrreversibilityGate
from cua.providers.anthropic import AnthropicProvider
from cua.executors.web import WebExecutor


async def _confirm(_req):
    return True


def test_validate_display_size_rejects_bad_values():
    for bad in [(0, 100), (100, -1), (100,), "1280x800", (1280, 800, 1),
                (True, 800), (800, False), (1.0, 800)]:
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
    # the gate/queue/max_steps must actually be wired into the session
    assert isinstance(session.gate, IrreversibilityGate)
    assert isinstance(session.queue, InputQueue)
    assert session.max_steps == 50


def test_build_session_rejects_bad_display_size():
    with pytest.raises(ValueError):
        build_session("claude", "web", confirm_handler=_confirm,
                      provider_client=object(), page=object(), display_size=(0, 0))


def test_build_session_local_openai_uses_host_environment():
    from cua.config import environment_for_executor
    from cua.providers.openai import OpenAIProvider
    session = build_session(
        "openai", "local",
        confirm_handler=_confirm,
        provider_client=object(),
    )
    assert isinstance(session.provider, OpenAIProvider)
    assert session.provider.environment == environment_for_executor("local")


def test_build_session_threads_runtime_guards():
    session = build_session(
        "claude", "web",
        confirm_handler=_confirm,
        provider_client=object(),
        page=object(),
        provider_retries=4,
        max_runtime_seconds=90,
        max_repeated_actions=6,
    )
    assert session.provider_retries == 4
    assert session.max_runtime_seconds == 90
    assert session.max_repeated_actions == 6


def test_build_session_local_uses_local_executor():
    from cua.executors.local import LocalExecutor
    session = build_session(
        "openai", "local",
        confirm_handler=_confirm,
        provider_client=object(),
    )
    assert isinstance(session.executor, LocalExecutor)
