# docker/desktop/agent.py
"""In-container HTTP agent: performs neutral-action payloads via pyautogui.

`perform` is pure (takes an injected pyautogui-like `gui`) so it is unit-tested
on the host without pyautogui. The HTTP server bootstrap at the bottom imports
pyautogui lazily and only runs when executed as a script inside the container.
"""
from __future__ import annotations

import base64
import time


def perform(payload: dict, gui) -> dict:
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
    except Exception as exc:  # noqa: BLE001 — return error to caller, never crash the agent
        return {"ok": False, "error": str(exc)}


def _make_real_gui():
    """Build a pyautogui-backed gui whose screenshot() returns PNG bytes."""
    import os
    import subprocess
    import tempfile
    import pyautogui  # imported lazily; only available inside the container

    class _Gui:
        def moveTo(self, x, y): pyautogui.moveTo(x, y)
        def click(self, x=None, y=None, button="left", clicks=1):
            pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        def dragTo(self, x, y, button="left"): pyautogui.dragTo(x, y, button=button)
        def typewrite(self, text): pyautogui.typewrite(text)
        def hotkey(self, *keys): pyautogui.hotkey(*keys)
        def scroll(self, amount): pyautogui.scroll(amount)
        def hscroll(self, amount): pyautogui.hscroll(amount)

        def screenshot(self):
            # Use scrot directly: pyautogui's pyscreeze backend requires
            # gnome-screenshot on Linux, which is heavy and unreliable headless.
            # scrot captures the Xvfb display cleanly and is already installed.
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            try:
                subprocess.run(["scrot", "-o", path], check=True)
                with open(path, "rb") as f:
                    return f.read()
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass

    return _Gui()


def _run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    import json
    from http.server import BaseHTTPRequestHandler, HTTPServer

    gui = _make_real_gui()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path == "/screenshot":
                self._send(perform({"action": "screenshot"}, gui))
            else:
                self._send({"ok": False, "error": "not found"}, code=404)

        def do_POST(self):  # noqa: N802
            if self.path == "/do":
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
                self._send(perform(payload, gui))
            else:
                self._send({"ok": False, "error": "not found"}, code=404)

    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    _run_server()
