"""Pure rendering of bus events into one-line log strings (UI-agnostic)."""
from __future__ import annotations

from adaptivecua.core.events import (
    StateChanged, StepCompleted, ScreenshotTaken, LogMessage, ConfirmRequested, ErrorOccurred,
)


def format_event(event) -> str | None:
    if isinstance(event, StateChanged):
        return f"[state] {event.state}"
    if isinstance(event, StepCompleted):
        name = type(event.action).__name__
        if event.result.success:
            return f"[step] {name} -> ok"
        return f"[step] {name} -> FAIL: {event.result.error}"
    if isinstance(event, ScreenshotTaken):
        return None
    if isinstance(event, LogMessage):
        return event.text
    if isinstance(event, ConfirmRequested):
        return f"[confirm] {event.request.reason} :: {event.request.action}"
    if isinstance(event, ErrorOccurred):
        return f"[error] {event.message}"
    return None
