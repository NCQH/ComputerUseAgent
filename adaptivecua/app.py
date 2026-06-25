"""Assemble a wired AgentSession from provider/executor names + injected clients."""
from __future__ import annotations

import time
from pathlib import Path

from adaptivecua.config import build_provider, build_executor, environment_for_executor
from adaptivecua.core.audit import AuditSink, NullAuditSink
from adaptivecua.core.events import EventBus
from adaptivecua.core.queue import InputQueue
from adaptivecua.core.safety import IrreversibilityGate, SafetyConfig
from adaptivecua.core.session import AgentSession
from adaptivecua.telemetry.recorder import TrajectoryRecorder


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
    safety=None,
    session_id=None,
    audit_dir=".cua/audit",
    trajectory_enabled=True,
    runs_dir=".cua/runs",
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
    # `denylist=` kept as a top-level shortcut; a full SafetyConfig (sensitive
    # surfaces, catastrophic BLOCK keys, audit toggle) overrides it when given.
    cfg = safety if safety is not None else SafetyConfig(denylist=denylist)
    gate = IrreversibilityGate.from_config(cfg)
    sid = session_id or time.strftime("%Y%m%d-%H%M%S")

    if cfg.audit_enabled:
        audit = AuditSink(Path(audit_dir) / f"{sid}.jsonl")
    else:
        audit = NullAuditSink()

    bus = EventBus()
    # SPEC-3: post-hoc trajectory record. Purely a bus subscriber — opt out by
    # passing trajectory_enabled=False (tests don't subscribe one).
    if trajectory_enabled:
        bus.subscribe(TrajectoryRecorder(Path(runs_dir) / sid).on_event)
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
        audit=audit,
    )
