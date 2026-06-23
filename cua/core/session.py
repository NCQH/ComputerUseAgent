"""AgentSession: the async orchestration loop tying everything together."""
from __future__ import annotations

from enum import Enum
from typing import Awaitable, Callable

from cua.core.events import (
    ConfirmRequested,
    ErrorOccurred,
    EventBus,
    LogMessage,
    ScreenshotTaken,
    StateChanged,
    StepCompleted,
)
from cua.core.history import History
from cua.core.queue import InputQueue
from cua.core.safety import IrreversibilityGate
from cua.executors.base import Executor
from cua.models import ConfirmRequest
from cua.providers.base import CUAProvider


class SessionState(Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    WAITING_CONFIRM = "WAITING_CONFIRM"


class AgentSession:
    def __init__(
        self,
        provider: CUAProvider,
        executor: Executor,
        gate: IrreversibilityGate,
        bus: EventBus,
        queue: InputQueue,
        confirm_handler: Callable[[ConfirmRequest], Awaitable[bool]],
        max_steps: int = 50,
    ) -> None:
        self.provider = provider
        self.executor = executor
        self.gate = gate
        self.bus = bus
        self.queue = queue
        self.confirm_handler = confirm_handler
        self.max_steps = max_steps
        self.history = History()
        self.state = SessionState.IDLE
        self._stop = False

    async def submit(self, text: str) -> None:
        await self.queue.submit(text)

    def request_stop(self) -> None:
        """Ask the run loop to stop after the current action (graceful). For an
        immediate stop even mid-API-call, the runner also cancels the task."""
        self._stop = True

    def _set_state(self, state: SessionState) -> None:
        self.state = state
        self.bus.publish(StateChanged(state=state.value))

    async def run(self) -> None:
        self._stop = False
        self._set_state(SessionState.RUNNING)
        steps = 0
        try:
            while steps < self.max_steps:
                if self._stop:
                    self.bus.publish(LogMessage(text="Stopped by user."))
                    break
                for text in self.queue.drain():
                    self.history.add_user(text)
                    self.bus.publish(LogMessage(text=f"New request: {text}"))

                try:
                    screenshot = await self.executor.screenshot()
                except Exception as exc:  # noqa: BLE001 — surfaced, not swallowed
                    self.history.add_error(str(exc))
                    self.bus.publish(ErrorOccurred(message=str(exc)))
                    break

                self.bus.publish(ScreenshotTaken(screenshot_b64=screenshot))

                try:
                    resp = await self.provider.next_actions(screenshot, self.history)
                except Exception as exc:  # noqa: BLE001 — surfaced, not swallowed
                    self.history.add_error(str(exc))
                    self.bus.publish(ErrorOccurred(message=str(exc)))
                    break

                self.history.add_assistant(resp.assistant_text)

                # Surface the model's reasoning / error string. Without this a
                # provider that returns no actions (a parse/screenshot error, or
                # a plain "done") leaves the UI on a silent IDLE with no clue why.
                if resp.assistant_text:
                    self.bus.publish(LogMessage(text=f"[model] {resp.assistant_text}"))

                if resp.done and self.queue.is_empty():
                    break

                for action in resp.actions:
                    if self._stop:
                        break
                    needs, reason = self.gate.needs_confirmation(
                        action, resp.assistant_text, resp.model_flagged_risky
                    )
                    if needs:
                        request = ConfirmRequest(action=action, reason=reason)
                        self._set_state(SessionState.WAITING_CONFIRM)
                        self.bus.publish(ConfirmRequested(request=request))
                        approved = await self.confirm_handler(request)
                        self._set_state(SessionState.RUNNING)
                        if not approved:
                            self.history.add_error(f"User rejected: {action} ({reason})")
                            continue

                    result = await self.executor.do(action)
                    self.history.add_action_result(action, result)
                    self.bus.publish(StepCompleted(action=action, result=result))

                steps += 1
        finally:
            self._stop = False
            self._set_state(SessionState.IDLE)
