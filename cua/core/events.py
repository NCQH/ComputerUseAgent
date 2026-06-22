"""Event bus and event types published by the agent core."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from cua.models import Action, ConfirmRequest, StepResult


@dataclass(frozen=True)
class StateChanged:
    state: str


@dataclass(frozen=True)
class StepCompleted:
    action: Action
    result: StepResult


@dataclass(frozen=True)
class ScreenshotTaken:
    screenshot_b64: str


@dataclass(frozen=True)
class LogMessage:
    text: str


@dataclass(frozen=True)
class ConfirmRequested:
    request: ConfirmRequest


@dataclass(frozen=True)
class ErrorOccurred:
    message: str


Event = (
    StateChanged
    | StepCompleted
    | ScreenshotTaken
    | LogMessage
    | ConfirmRequested
    | ErrorOccurred
)


class EventBus:
    def __init__(self) -> None:
        self._handlers: list[Callable[[Event], None]] = []

    def subscribe(self, handler: Callable[[Event], None]) -> None:
        self._handlers.append(handler)

    def publish(self, event: Event) -> None:
        for handler in self._handlers:
            try:
                handler(event)
            except Exception:
                # A faulty subscriber must not break the agent loop or peers.
                pass
