"""Executor interface: capture a screen and perform one neutral action."""
from __future__ import annotations

from typing import Protocol

from adaptivecua.models import Action, StepResult


class Executor(Protocol):
    display_size: tuple[int, int]

    async def start(self) -> None: ...
    async def screenshot(self) -> str: ...
    async def do(self, action: Action) -> StepResult: ...
    async def close(self) -> None: ...
