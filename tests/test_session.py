# tests/test_session.py
from cua.core.session import AgentSession, SessionState
from cua.core.queue import InputQueue
from cua.core.events import EventBus, StepCompleted, ConfirmRequested, ErrorOccurred, LogMessage
from cua.core.history import History, UserEntry, ErrorEntry
from cua.core.safety import IrreversibilityGate
from cua.models import Click, Type, ProviderResponse, ConfirmRequest
from tests.fakes import FakeProvider, FakeExecutor


def _session(provider, executor, *, confirm=None, queue=None, bus=None, gate=None, max_steps=50):
    async def auto_yes(_req):
        return True
    s = AgentSession(
        provider=provider,
        executor=executor,
        gate=gate or IrreversibilityGate(),
        bus=bus or EventBus(),
        queue=queue or InputQueue(),
        confirm_handler=confirm or auto_yes,
        max_steps=max_steps,
    )
    s.history = History()  # ensure fresh
    return s


async def test_runs_actions_until_provider_done():
    provider = FakeProvider([
        ProviderResponse([Click(1, 1)], done=False, assistant_text="step1", model_flagged_risky=False),
        ProviderResponse([], done=True, assistant_text="finished", model_flagged_risky=False),
    ])
    executor = FakeExecutor()
    session = _session(provider, executor)
    await session.submit("do it")
    await session.run()
    assert executor.performed == [Click(1, 1)]
    assert session.state is SessionState.IDLE


async def test_pending_request_is_drained_into_history_between_steps():
    # provider submits a follow-up request via side effect on first call
    queue = InputQueue()
    provider = FakeProvider([
        ProviderResponse([Click(1, 1)], done=False, assistant_text="s1", model_flagged_risky=False),
        ProviderResponse([], done=True, assistant_text="s2", model_flagged_risky=False),
    ])
    executor = FakeExecutor()
    session = _session(provider, executor, queue=queue)
    await queue.submit("first")
    # queue a second request that should be picked up on the 2nd iteration
    await queue.submit("second")
    await session.run()
    user_texts = [e.text for e in session.history.entries() if isinstance(e, UserEntry)]
    assert user_texts == ["first", "second"]


async def test_gate_triggers_confirm_and_rejection_skips_action():
    provider = FakeProvider([
        ProviderResponse([Click(9, 9)], done=False, assistant_text="click Submit", model_flagged_risky=False),
        ProviderResponse([], done=True, assistant_text="done", model_flagged_risky=False),
    ])
    executor = FakeExecutor()
    seen = []
    bus = EventBus()
    bus.subscribe(lambda e: seen.append(e) if isinstance(e, ConfirmRequested) else None)

    async def reject(_req):
        return False

    session = _session(provider, executor, confirm=reject, bus=bus)
    await session.run()
    # action was skipped
    assert executor.performed == []
    # confirm was requested
    assert len(seen) == 1 and isinstance(seen[0], ConfirmRequested)
    # rejection logged
    assert any(isinstance(e, ErrorEntry) for e in session.history.entries())


async def test_provider_exception_logs_error_and_stops():
    class BoomProvider:
        display_size = (1280, 800)
        async def next_actions(self, screenshot_b64, history):
            raise RuntimeError("api down")

    executor = FakeExecutor()
    errors = []
    bus = EventBus()
    bus.subscribe(lambda e: errors.append(e) if isinstance(e, ErrorOccurred) else None)
    session = _session(BoomProvider(), executor, bus=bus)
    await session.submit("go")
    await session.run()
    assert len(errors) == 1
    assert session.state is SessionState.IDLE


async def test_executor_failure_recorded_in_history():
    provider = FakeProvider([
        ProviderResponse([Type(text="hi")], done=False, assistant_text="typing", model_flagged_risky=False),
        ProviderResponse([], done=True, assistant_text="done", model_flagged_risky=False),
    ])
    executor = FakeExecutor(fail_on=Type)
    session = _session(provider, executor)
    await session.run()
    from cua.core.history import ActionEntry
    failed = [e for e in session.history.entries()
              if isinstance(e, ActionEntry) and not e.result.success]
    assert len(failed) == 1


async def test_max_steps_stops_runaway_loop():
    # provider never reports done
    forever = [
        ProviderResponse([Click(1, 1)], done=False, assistant_text="x", model_flagged_risky=False)
        for _ in range(100)
    ]
    provider = FakeProvider(forever)
    executor = FakeExecutor()
    session = _session(provider, executor, max_steps=3)
    await session.run()
    assert len(executor.performed) == 3
    assert session.state is SessionState.IDLE


async def test_assistant_text_is_surfaced_to_bus():
    """Without this, a provider that returns no actions (error string or 'done'
    reasoning in assistant_text) leaves the user staring at a silent IDLE."""
    provider = FakeProvider([
        ProviderResponse([], done=False, assistant_text="parse error: 400 bad schema",
                         model_flagged_risky=False),
        ProviderResponse([], done=True, assistant_text="all done", model_flagged_risky=False),
    ])
    executor = FakeExecutor()
    logs = []
    bus = EventBus()
    bus.subscribe(lambda e: logs.append(e.text) if isinstance(e, LogMessage) else None)
    session = _session(provider, executor, bus=bus)
    await session.submit("go")
    await session.run()
    # the model's reasoning / error string must reach the user
    assert any("parse error: 400 bad schema" in t for t in logs)
    assert any("all done" in t for t in logs)


async def test_request_stop_halts_remaining_actions():
    """If the user stops mid-step, queued actions after the stop must not run."""
    provider = FakeProvider([
        ProviderResponse([Click(1, 1), Click(2, 2), Click(3, 3)], done=False,
                         assistant_text="three clicks", model_flagged_risky=False),
        ProviderResponse([], done=True, assistant_text="done", model_flagged_risky=False),
    ])

    # an executor that asks the session to stop right after the first action
    class StopAfterFirst(FakeExecutor):
        def __init__(self, session_ref):
            super().__init__()
            self._session_ref = session_ref
        async def do(self, action):
            result = await super().do(action)
            self._session_ref[0].request_stop()
            return result

    ref = [None]
    executor = StopAfterFirst(ref)
    session = _session(provider, executor)
    ref[0] = session
    await session.submit("go")
    await session.run()
    assert executor.performed == [Click(1, 1)]   # 2nd and 3rd never ran
    assert session.state is SessionState.IDLE


async def test_screenshot_failure_is_surfaced_and_state_resets():
    """I-2: executor.screenshot() failure must publish ErrorOccurred and reset state to IDLE."""

    class BoomExecutor(FakeExecutor):
        async def screenshot(self) -> str:
            raise RuntimeError("display lost")

    provider = FakeProvider([
        ProviderResponse([], done=True, assistant_text="never reached", model_flagged_risky=False),
    ])
    executor = BoomExecutor()
    errors = []
    bus = EventBus()
    bus.subscribe(lambda e: errors.append(e) if isinstance(e, ErrorOccurred) else None)
    session = _session(provider, executor, bus=bus)
    await session.submit("go")
    await session.run()
    # (a) ErrorOccurred was published with the exception message
    assert len(errors) == 1
    assert "display lost" in errors[0].message
    # (b) session must return to IDLE, not stay RUNNING
    assert session.state is SessionState.IDLE
