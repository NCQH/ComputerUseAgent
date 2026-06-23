"""AgentSession: the async orchestration loop tying everything together."""
from __future__ import annotations

import asyncio
import time
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
        max_runtime_seconds: float | None = None,
        max_repeated_actions: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        provider_retries: int = 0,
        retry_backoff_base: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.provider = provider
        self.executor = executor
        self.gate = gate
        self.bus = bus
        self.queue = queue
        self.confirm_handler = confirm_handler
        self.max_steps = max_steps
        # Runaway guards (None = off): a wall-clock budget and a stuck-loop guard
        # that stops when the same action repeats too many times in a row.
        self.max_runtime_seconds = max_runtime_seconds
        self.max_repeated_actions = max_repeated_actions
        self.clock = clock
        # Transient provider failures (network/5xx) are retried with exponential
        # backoff before being surfaced. 0 = no retry (fail fast, as before).
        self.provider_retries = provider_retries
        self.retry_backoff_base = retry_backoff_base
        self.sleep = sleep
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

    async def _next_actions_with_retry(self, screenshot: str):
        """Call the provider, retrying transient failures with exponential backoff.
        Re-raises the last exception once retries are exhausted."""
        attempt = 0
        while True:
            try:
                return await self.provider.next_actions(screenshot, self.history)
            except Exception as exc:  # noqa: BLE001 — retried, then re-raised
                if attempt >= self.provider_retries:
                    raise
                delay = self.retry_backoff_base * (2 ** attempt)
                self.bus.publish(LogMessage(
                    text=f"Provider error ({exc}); retrying in {delay:.1f}s "
                         f"[{attempt + 1}/{self.provider_retries}]"))
                await self.sleep(delay)
                attempt += 1

    async def run(self) -> None:
        self._stop = False
        self._set_state(SessionState.RUNNING)
        steps = 0
        started_at = self.clock()
        last_action = None
        repeat_count = 0
        stuck = False
        try:
            while steps < self.max_steps:
                if self._stop:
                    self.bus.publish(LogMessage(text="Stopped by user."))
                    break
                if (self.max_runtime_seconds is not None
                        and self.clock() - started_at > self.max_runtime_seconds):
                    self.bus.publish(LogMessage(
                        text=f"Stopped: exceeded time budget of {self.max_runtime_seconds}s."))
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
                    resp = await self._next_actions_with_retry(screenshot)
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

                    if action == last_action:
                        repeat_count += 1
                    else:
                        last_action, repeat_count = action, 1
                    if (self.max_repeated_actions is not None
                            and repeat_count >= self.max_repeated_actions):
                        self.bus.publish(LogMessage(
                            text=f"Stopped: same action repeated {repeat_count} times "
                                 f"({action}) — likely stuck."))
                        stuck = True
                        break

                if stuck:
                    break

                steps += 1
        finally:
            self._stop = False
            self._set_state(SessionState.IDLE)
