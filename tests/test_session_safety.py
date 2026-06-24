"""SPEC-4 session wiring: BLOCK never executes, CONFIRM/ALLOW audited,
sensitive context flows from executor.context() into the gate."""
from cua.core.events import EventBus, LogMessage
from cua.core.history import ErrorEntry
from cua.core.queue import InputQueue
from cua.core.safety import IrreversibilityGate, SafetyContext, Verdict
from cua.core.session import AgentSession
from cua.models import Click, Key, ProviderResponse, Type
from tests.fakes import FakeExecutor, FakeProvider


class CtxExecutor(FakeExecutor):
    """FakeExecutor that advertises a safety context (window title / URL)."""

    def __init__(self, ctx: SafetyContext, **kw):
        super().__init__(**kw)
        self._ctx = ctx

    async def context(self) -> SafetyContext:
        return self._ctx


class RecordingAudit:
    def __init__(self):
        self.calls = []

    def record(self, action, result, ctx, approved, *, redact_text=False):
        self.calls.append((action, result.verdict, approved, redact_text))


def _session(provider, executor, *, gate=None, confirm=None, audit=None):
    async def auto_yes(_):
        return True
    return AgentSession(
        provider=provider, executor=executor, gate=gate or IrreversibilityGate(),
        bus=EventBus(), queue=InputQueue(), confirm_handler=confirm or auto_yes,
        audit=audit,
    )


async def test_block_verdict_never_executes():
    provider = FakeProvider([
        ProviderResponse([Key("ctrl+alt+del")], done=False, assistant_text="x",
                         model_flagged_risky=False),
        ProviderResponse([], done=True, assistant_text="done", model_flagged_risky=False),
    ])
    executor = FakeExecutor()
    gate = IrreversibilityGate(catastrophic_keys=["ctrl+alt+del"])
    audit = RecordingAudit()
    logs = []
    session = _session(provider, executor, gate=gate, audit=audit)
    session.bus.subscribe(lambda e: logs.append(e.text) if isinstance(e, LogMessage) else None)
    await session.submit("go")
    await session.run()
    assert executor.performed == []                                  # never ran
    assert any("BLOCKED" in t for t in logs)
    assert any(isinstance(e, ErrorEntry) for e in session.history.entries())
    assert audit.calls[0][1] is Verdict.BLOCK and audit.calls[0][2] is None


async def test_confirm_reject_audited_and_not_executed():
    provider = FakeProvider([
        ProviderResponse([Click(1, 1)], done=False, assistant_text="click Submit",
                         model_flagged_risky=False),
        ProviderResponse([], done=True, assistant_text="done", model_flagged_risky=False),
    ])
    executor = FakeExecutor()
    audit = RecordingAudit()

    async def reject(_):
        return False

    session = _session(provider, executor, confirm=reject, audit=audit)
    await session.run()
    assert executor.performed == []
    assert audit.calls[0][1] is Verdict.CONFIRM and audit.calls[0][2] is False


async def test_allow_executes_and_is_audited():
    provider = FakeProvider([
        ProviderResponse([Click(1, 1)], done=False, assistant_text="click box",
                         model_flagged_risky=False),
        ProviderResponse([], done=True, assistant_text="done", model_flagged_risky=False),
    ])
    executor = FakeExecutor()
    audit = RecordingAudit()
    session = _session(provider, executor, audit=audit)
    await session.run()
    assert executor.performed == [Click(1, 1)]
    assert audit.calls[0][1] is Verdict.ALLOW


async def test_sensitive_context_escalates_benign_click_to_confirm():
    """A plain click that would ALLOW becomes CONFIRM because executor.context()
    reports a banking URL — and typed text would be redacted in audit."""
    provider = FakeProvider([
        ProviderResponse([Click(1, 1)], done=False, assistant_text="click button",
                         model_flagged_risky=False),
        ProviderResponse([], done=True, assistant_text="done", model_flagged_risky=False),
    ])
    executor = CtxExecutor(SafetyContext("web", url="https://paypal.com/send"))
    confirmed = []

    async def watch(req):
        confirmed.append(req)
        return True

    audit = RecordingAudit()
    session = _session(provider, executor, confirm=watch, audit=audit)
    await session.run()
    assert len(confirmed) == 1                       # was asked
    assert executor.performed == [Click(1, 1)]       # then ran after approval
    assert audit.calls[0][1] is Verdict.CONFIRM
    assert audit.calls[0][3] is True                 # redact_text flag set on sensitive surface


async def test_missing_context_capability_degrades_gracefully():
    """FakeExecutor has no context() -> ctx None -> gate is context-blind (no crash)."""
    provider = FakeProvider([
        ProviderResponse([Click(1, 1)], done=False, assistant_text="click box",
                         model_flagged_risky=False),
        ProviderResponse([], done=True, assistant_text="done", model_flagged_risky=False),
    ])
    executor = FakeExecutor()
    session = _session(provider, executor)
    await session.run()
    assert executor.performed == [Click(1, 1)]
