"""Assemble a wired AgentSession from provider/executor names + injected clients."""
from __future__ import annotations

from cua.config import build_provider, build_executor, environment_for_executor
from cua.core.events import EventBus
from cua.core.queue import InputQueue
from cua.core.safety import IrreversibilityGate
from cua.core.session import AgentSession


def validate_display_size(display_size) -> None:
    if not isinstance(display_size, (tuple, list)) or len(display_size) != 2:
        raise ValueError(f"display_size must be a 2-tuple, got {display_size!r}")
    w, h = display_size
    # bool is a subclass of int — reject it explicitly so (True, 800) is not (1, 800).
    if isinstance(w, bool) or isinstance(h, bool):
        raise ValueError(f"display_size dimensions must be ints, not bools, got {display_size!r}")
    if not (isinstance(w, int) and isinstance(h, int)) or w <= 0 or h <= 0:
        raise ValueError(f"display_size must be positive ints, got {display_size!r}")


def build_session(
    provider_name,
    executor_name,
    *,
    confirm_handler,
    provider_client=None,
    page=None,
    display_size=(1280, 800),
    denylist=None,
    max_steps=50,
    provider_retries=2,
    max_runtime_seconds=None,
    max_repeated_actions=None,
) -> AgentSession:
    validate_display_size(display_size)
    environment = environment_for_executor(executor_name)
    # The DOM (browser) provider reads the DOM from the same Playwright page the
    # web executor drives, so it is given `page` too; other providers ignore it.
    provider = build_provider(provider_name, client=provider_client, display_size=display_size,
                              environment=environment, page=page)
    if executor_name.strip().lower() == "web":
        executor = build_executor("web", page=page, display_size=display_size)
    else:
        executor = build_executor(executor_name, display_size=display_size)
    gate = IrreversibilityGate(denylist=denylist)
    bus = EventBus()
    queue = InputQueue()
    return AgentSession(
        provider=provider,
        executor=executor,
        gate=gate,
        bus=bus,
        queue=queue,
        confirm_handler=confirm_handler,
        max_steps=max_steps,
        provider_retries=provider_retries,
        max_runtime_seconds=max_runtime_seconds,
        max_repeated_actions=max_repeated_actions,
    )
