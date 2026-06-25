"""Provider interface: screenshot + history -> neutral actions."""
from __future__ import annotations

from typing import Protocol

from adaptivecua.core.history import History
from adaptivecua.models import ProviderResponse


class CUAProvider(Protocol):
    display_size: tuple[int, int]

    async def next_actions(
        self, screenshot_b64: str, history: History
    ) -> ProviderResponse: ...
