"""Live smoke of the full AgentSession loop + safety gate (no API key, no desktop).

A scripted provider stands in for the LLM and a recording fake gui stands in for
pyautogui, so this drives the real AgentSession, real IrreversibilityGate, real
EventBus, and a real LocalExecutor end to end. Shows:
  1. a normal action executing,
  2. a denylisted "Submit" action pausing for confirmation and being rejected.
"""
import asyncio
import sys

# Windows consoles default to cp1252; the gate's reason strings are Vietnamese.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from cua.core.events import EventBus
from cua.core.queue import InputQueue
from cua.core.safety import IrreversibilityGate
from cua.core.session import AgentSession
from cua.executors.local import LocalExecutor
from cua.models import Click, ProviderResponse
from cua.ui.format import format_event


class FakeGui:
    """Records pyautogui-style calls; screenshot returns deterministic PNG bytes."""
    def moveTo(self, x, y): pass
    def click(self, **k): pass
    def typewrite(self, t): pass
    def hotkey(self, *k): pass
    def scroll(self, a): pass
    def hscroll(self, a): pass
    def size(self): return (1280, 800)
    def screenshot(self): return b"PNG"


class ScriptedProvider:
    """Stands in for Claude/OpenAI: emits a safe action, then a risky one, then done."""
    display_size = (1280, 800)

    def __init__(self):
        self._steps = [
            ProviderResponse([Click(10, 10)], done=False,
                             assistant_text="clicking the search box", model_flagged_risky=False),
            ProviderResponse([Click(200, 400)], done=False,
                             assistant_text="click the Submit button", model_flagged_risky=False),
            ProviderResponse([], done=True, assistant_text="finished", model_flagged_risky=False),
        ]
        self._i = 0

    async def next_actions(self, screenshot_b64, history):
        r = self._steps[self._i]
        self._i += 1
        return r


async def main():
    confirm_log = []

    async def reject_confirm(request):
        confirm_log.append(request)
        print(f"  >>> CONFIRM ASKED: {request.reason} -> auto-REJECT")
        return False

    executor = LocalExecutor(gui=FakeGui())
    bus = EventBus()
    bus.subscribe(lambda e: (lambda s: print("  [event]", s) if s else None)(format_event(e)))
    session = AgentSession(
        provider=ScriptedProvider(),
        executor=executor,
        gate=IrreversibilityGate(),     # default denylist incl. "submit"
        bus=bus,
        queue=InputQueue(),
        confirm_handler=reject_confirm,
        max_steps=10,
    )
    await session.submit("tìm kiếm rồi gửi biểu mẫu")
    print("[run] starting agent loop against the local executor...\n")
    await session.run()

    print("\n[verify]")
    print(f"  confirmations asked: {len(confirm_log)} (expected 1 — the 'Submit' click)")
    assert len(confirm_log) == 1
    assert "submit" in confirm_log[0].reason.lower()
    print(f"  reason: {confirm_log[0].reason}")
    print(f"  final session state: {session.state.value}")
    print("\n[OK] full loop + safety gate ran; the irreversible 'Submit' was held for confirmation.")


if __name__ == "__main__":
    asyncio.run(main())
