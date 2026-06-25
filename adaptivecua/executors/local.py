"""LocalExecutor: drives the REAL host desktop via pyautogui, in-process.

The "hands" act on the machine you are sitting at. There is NO sandbox here — the
IrreversibilityGate in the session is the only guard, so destructive actions are
still gated for confirmation but ordinary clicks/typing land on your real screen.

`apply_payload` is a pure dispatch (takes an injected pyautogui-like `gui`) so it
is unit-tested on any host without pyautogui. pyautogui/Pillow are imported lazily
by _make_host_gui(), only when a real executor is constructed, so the test suite
runs without them.
"""
from __future__ import annotations

import asyncio
import base64
import time

from adaptivecua.core.safety import SafetyContext
from adaptivecua.executors.action_payload import action_to_payload
from adaptivecua.models import Action, StepResult


def apply_payload(payload: dict, gui) -> dict:
    """Map one neutral-action payload onto a pyautogui-like gui. Never raises."""
    try:
        action = payload.get("action")
        if action == "click":
            gui.click(x=payload["x"], y=payload["y"], button=payload.get("button", "left"),
                      clicks=payload.get("clicks", 1))
            return {"ok": True}
        if action == "move":
            gui.moveTo(payload["x"], payload["y"])
            return {"ok": True}
        if action == "drag":
            gui.moveTo(payload["x1"], payload["y1"])
            gui.dragTo(payload["x2"], payload["y2"], button="left")
            return {"ok": True}
        if action == "type":
            gui.typewrite(payload["text"])
            return {"ok": True}
        if action == "hotkey":
            gui.hotkey(*payload["keys"])
            return {"ok": True}
        if action == "scroll":
            amount = payload["amount"]
            direction = payload["direction"]
            if direction == "down":
                gui.scroll(-amount)
            elif direction == "up":
                gui.scroll(amount)
            elif direction == "right":
                gui.hscroll(amount)
            elif direction == "left":
                gui.hscroll(-amount)
            else:
                return {"ok": False, "error": f"bad scroll direction: {direction}"}
            return {"ok": True}
        if action == "wait":
            time.sleep(payload["ms"] / 1000)
            return {"ok": True}
        if action == "screenshot":
            png = gui.screenshot()
            return {"ok": True, "image": base64.b64encode(png).decode()}
        return {"ok": False, "error": f"unknown action: {action}"}
    except Exception as exc:  # noqa: BLE001 — surfaced to caller, never crash
        return {"ok": False, "error": str(exc)}


class LocalExecutor:
    def __init__(self, gui=None, display_size: tuple[int, int] = (1280, 800),
                 failsafe: bool = True) -> None:
        self._gui = gui
        self.display_size = display_size
        # On an unsandboxed real desktop the pyautogui corner-fling abort is the
        # user's only physical kill switch, so it is ON by default.
        self.failsafe = failsafe

    def _ensure_gui(self) -> None:
        if self._gui is None:
            self._gui = _make_host_gui(failsafe=self.failsafe)
        # Adopt the real screen size; on the host that is the source of truth for
        # the coordinate space pyautogui acts in.
        try:
            self.display_size = self._gui.size()
        except Exception:  # noqa: BLE001 — keep the configured fallback
            pass

    async def start(self) -> None:
        await asyncio.to_thread(self._ensure_gui)

    async def close(self) -> None:
        return None

    async def context(self) -> SafetyContext:
        """Active-surface context for the safety gate: the focused window title.
        Lazy `pygetwindow`; absent dep or failure -> None title (graceful, same
        pattern as OCR). Gated behind the `[local]` extra."""
        title = await asyncio.to_thread(_active_window_title)
        return SafetyContext("local", active_title=title)

    async def screenshot(self) -> str:
        if self._gui is None:
            await asyncio.to_thread(self._ensure_gui)
        out = await asyncio.to_thread(apply_payload, {"action": "screenshot"}, self._gui)
        if not out.get("ok", False):
            raise RuntimeError(f"screenshot failed: {out.get('error', 'unknown')}")
        return out.get("image", "")

    async def do(self, action: Action) -> StepResult:
        try:
            if self._gui is None:
                await asyncio.to_thread(self._ensure_gui)
            payload = action_to_payload(action)
            out = await asyncio.to_thread(apply_payload, payload, self._gui)
            if not out.get("ok", False):
                return StepResult(success=False, error=str(out.get("error", "gui failure")))
            shot = await self.screenshot()
            return StepResult(success=True, screenshot_b64=shot)
        except Exception as exc:  # noqa: BLE001 — surfaced in StepResult
            return StepResult(success=False, error=str(exc))


def _active_window_title() -> str | None:
    """Focused-window title via pygetwindow; None if unavailable. Never raises."""
    try:
        import pygetwindow  # lazy; part of the [local] extra
        win = pygetwindow.getActiveWindow()
        if win is None:
            return None
        return getattr(win, "title", None) or None
    except Exception:  # noqa: BLE001 — degrade to no title, never break the run
        return None


def _make_host_gui(failsafe: bool = True):
    """Build a pyautogui-backed gui whose screenshot() returns PNG bytes."""
    import io

    import pyautogui  # lazy; real host dependency

    # FAILSAFE ON (default): flinging the mouse into a screen corner aborts the
    # run — the emergency stop for an unsandboxed real-desktop agent. Callers can
    # opt out (failsafe=False) for unattended runs where a stray corner-hit
    # should not kill the task.
    pyautogui.FAILSAFE = failsafe

    class _HostGui:
        def moveTo(self, x, y): pyautogui.moveTo(x, y)

        def click(self, x=None, y=None, button="left", clicks=1):
            pyautogui.click(x=x, y=y, button=button, clicks=clicks)

        def dragTo(self, x, y, button="left"): pyautogui.dragTo(x, y, button=button)

        def typewrite(self, text): pyautogui.write(text)

        def hotkey(self, *keys): pyautogui.hotkey(*keys)

        def scroll(self, amount): pyautogui.scroll(amount)

        def hscroll(self, amount): pyautogui.hscroll(amount)

        def size(self):
            w, h = pyautogui.size()
            return (int(w), int(h))

        def screenshot(self):
            img = pyautogui.screenshot()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

    return _HostGui()
