"""GUI integration smoke: real PySide6 window + qasync loop, fake brain/hands.

Builds an AgentSession with a fake provider (returns one Click then 'done') and a
fake executor (no real desktop), launches the actual run_gui() window, then via
QTimers types a task into the box, clicks "Gửi", and asserts the log reflects the
full path: request -> model text -> action executed. Proves the GUI wiring
(EventBus -> log, button -> SessionRunner -> session loop) without an API key,
without touching the desktop, and without a model.
"""
from __future__ import annotations

import base64
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QTextEdit

from cua.core.events import EventBus
from cua.core.queue import InputQueue
from cua.core.safety import IrreversibilityGate
from cua.core.session import AgentSession
from cua.models import Click, ProviderResponse, StepResult
from cua.ui.confirm import auto_approve
from cua.ui.gui import run_gui

TINY_PNG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\nFAKE").decode()
TASK = "open notepad and type hello"


class FakeExecutor:
    display_size = (800, 600)

    def __init__(self) -> None:
        self.actions: list = []

    async def start(self) -> None: ...
    async def close(self) -> None: ...
    async def screenshot(self) -> str:
        return TINY_PNG_B64

    async def do(self, action) -> StepResult:
        self.actions.append(action)
        return StepResult(success=True, screenshot_b64=TINY_PNG_B64)


class FakeProvider:
    display_size = (800, 600)

    def __init__(self) -> None:
        self.calls = 0

    async def next_actions(self, screenshot_b64: str, history) -> ProviderResponse:
        self.calls += 1
        if self.calls == 1:
            return ProviderResponse(
                actions=[Click(10, 10)], done=False,
                assistant_text="step 1: click", model_flagged_risky=False,
            )
        return ProviderResponse(
            actions=[], done=True,
            assistant_text="GUI smoke done", model_flagged_risky=False,
        )


def find_window(app):
    for w in app.topLevelWidgets():
        if w.windowTitle() == "CUA":
            return w
    return None


def main() -> None:
    session = AgentSession(
        provider=FakeProvider(),
        executor=FakeExecutor(),
        gate=IrreversibilityGate(),
        bus=EventBus(),
        queue=InputQueue(),
        confirm_handler=auto_approve,
        max_steps=5,
    )

    app = QApplication.instance() or QApplication(sys.argv)
    result: dict = {}

    def drive() -> None:
        win = find_window(app)
        assert win is not None, "CUA window not found"
        line = win.findChild(QLineEdit)
        send = next(b for b in win.findChildren(QPushButton) if b.text() == "Gửi")
        line.setText(TASK)
        send.click()
        print("[drive] typed task and clicked send")

    def check() -> None:
        win = find_window(app)
        log = win.findChild(QTextEdit)
        result["log"] = log.toPlainText()
        result["actions"] = session.executor.actions
        result["calls"] = session.provider.calls
        app.quit()

    QTimer.singleShot(400, drive)
    QTimer.singleShot(2500, check)
    run_gui(session)  # blocks until app.quit()

    log = result.get("log", "")
    print("\n[log captured]\n" + log)
    print(f"\n[verify] provider.calls={result.get('calls')} "
          f"executor.actions={result.get('actions')}")

    assert TASK in log, "task request not shown in GUI log"
    assert "GUI smoke done" in log, "model text not shown in GUI log"
    assert result.get("actions"), "no action was executed via the GUI run loop"
    print("\n[OK] GUI smoke passed — window, event log, and run loop all wired")


if __name__ == "__main__":
    main()
