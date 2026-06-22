"""WebExecutor: drives a Playwright page from neutral actions."""
from __future__ import annotations

import asyncio
import base64

from cua.executors.web_translate import WebOp, action_to_web_ops
from cua.models import Action, StepResult


class WebExecutor:
    def __init__(self, page, display_size: tuple[int, int] = (1280, 800)) -> None:
        self.page = page
        self.display_size = display_size

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def screenshot(self) -> str:
        png = await self.page.screenshot()
        return base64.b64encode(png).decode()

    async def _dispatch(self, op: WebOp) -> None:
        a = op.args
        if op.name == "mouse_move":
            await self.page.mouse.move(a["x"], a["y"])
        elif op.name == "mouse_click":
            await self.page.mouse.click(a["x"], a["y"], button=a["button"], click_count=a["clicks"])
        elif op.name == "mouse_down":
            await self.page.mouse.down(button=a["button"])
        elif op.name == "mouse_up":
            await self.page.mouse.up(button=a["button"])
        elif op.name == "mouse_wheel":
            await self.page.mouse.wheel(a["dx"], a["dy"])
        elif op.name == "keyboard_type":
            await self.page.keyboard.type(a["text"])
        elif op.name == "keyboard_press":
            await self.page.keyboard.press(a["key"])
        elif op.name == "wait":
            await asyncio.sleep(a["ms"] / 1000)
        else:
            raise ValueError(f"unknown web op: {op.name}")

    async def do(self, action: Action) -> StepResult:
        try:
            for op in action_to_web_ops(action):
                await self._dispatch(op)
            shot = await self.screenshot()
            return StepResult(success=True, screenshot_b64=shot)
        except Exception as exc:  # noqa: BLE001 — surfaced in StepResult, not swallowed
            return StepResult(success=False, error=str(exc))
