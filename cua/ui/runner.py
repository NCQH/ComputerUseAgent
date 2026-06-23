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

    async def stop(self) -> None:
        """Stop a running session. Sets the graceful flag, then hard-cancels the
        task so a stop takes effect even while a blocking API call is mid-flight
        (which is what makes the UI appear frozen)."""
        self.session.request_stop()
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def aclose(self) -> None:
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
