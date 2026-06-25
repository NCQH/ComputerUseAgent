"""Non-blocking input queue for real-time user steering."""
from __future__ import annotations

import asyncio


class InputQueue:
    def __init__(self) -> None:
        self._q: asyncio.Queue[str] = asyncio.Queue()

    async def submit(self, text: str) -> None:
        await self._q.put(text)

    def drain(self) -> list[str]:
        items: list[str] = []
        while not self._q.empty():
            items.append(self._q.get_nowait())
        return items

    def is_empty(self) -> bool:
        return self._q.empty()
