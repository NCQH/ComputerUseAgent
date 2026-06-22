"""Owns the agent run-loop lifecycle so UIs can submit and resume cleanly."""
from __future__ import annotations

import asyncio


class SessionRunner:
    def __init__(self, session) -> None:
        self.session = session
        self._task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def submit(self, text: str) -> None:
        await self.session.submit(text)
        if not self.is_running:
            self._task = asyncio.create_task(self.session.run())

    async def aclose(self) -> None:
        if self._task is not None:
            await self._task
            self._task = None
