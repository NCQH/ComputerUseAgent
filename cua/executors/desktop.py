"""DesktopExecutor: drives the sandbox container agent over HTTP."""
from __future__ import annotations

from cua.executors.desktop_translate import action_to_payload
from cua.models import Action, StepResult


class DesktopExecutor:
    def __init__(self, client, base_url: str = "http://localhost:8000",
                 display_size: tuple[int, int] = (1280, 800)) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.display_size = display_size

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def screenshot(self) -> str:
        resp = await self.client.get(self.base_url + "/screenshot")
        data = resp.json()
        if not data.get("ok", False):
            raise RuntimeError(f"screenshot failed: {data.get('error', 'unknown')}")
        return data.get("image", "")

    async def do(self, action: Action) -> StepResult:
        try:
            payload = action_to_payload(action)
            resp = await self.client.post(self.base_url + "/do", json=payload)
            data = resp.json()
            if not data.get("ok", False):
                return StepResult(success=False, error=str(data.get("error", "agent reported failure")))
            shot = await self.screenshot()
            return StepResult(success=True, screenshot_b64=shot)
        except Exception as exc:  # noqa: BLE001 — surfaced in StepResult
            return StepResult(success=False, error=str(exc))
