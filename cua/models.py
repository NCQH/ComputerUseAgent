"""Neutral, provider-agnostic action and result types."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Click:
    x: int
    y: int
    button: str = "left"


@dataclass(frozen=True)
class Type:
    text: str


@dataclass(frozen=True)
class Key:
    combo: str  # e.g. "ctrl+a", "enter", "ctrl+shift+delete"


@dataclass(frozen=True)
class Scroll:
    x: int
    y: int
    direction: str  # "up" | "down" | "left" | "right"
    amount: int


@dataclass(frozen=True)
class Move:
    x: int
    y: int


@dataclass(frozen=True)
class Drag:
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass(frozen=True)
class Screenshot:
    pass


@dataclass(frozen=True)
class Wait:
    ms: int


Action = Click | Type | Key | Scroll | Move | Drag | Screenshot | Wait


@dataclass(frozen=True)
class StepResult:
    success: bool
    error: str | None = None
    screenshot_b64: str | None = None


@dataclass(frozen=True)
class ConfirmRequest:
    action: Action
    reason: str


@dataclass(frozen=True)
class ProviderResponse:
    actions: list[Action]
    done: bool
    assistant_text: str
    model_flagged_risky: bool
