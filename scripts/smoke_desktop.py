"""Live smoke test of the desktop executor path over a REAL HTTP socket.

Runs the real `docker/desktop/agent.py:perform` behind a real stdlib HTTP server,
then drives the real DesktopExecutor + a real httpx.AsyncClient against it.
No Docker, no display, no API key needed. pyautogui is replaced by a recording
fake gui (the real one needs an X display).
"""
import asyncio
import base64
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Load the real container agent module by path (it is not in the cua package).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "docker", "desktop"))
from agent import perform  # noqa: E402

import httpx  # noqa: E402
from cua.executors.desktop import DesktopExecutor  # noqa: E402
from cua.models import Move, Type, Click, Screenshot  # noqa: E402

GUI_CALLS = []


class FakeGui:
    def moveTo(self, x, y): GUI_CALLS.append(("moveTo", x, y))
    def click(self, x=None, y=None, button="left", clicks=1):
        GUI_CALLS.append(("click", x, y, button, clicks))
    def dragTo(self, x, y, button="left"): GUI_CALLS.append(("dragTo", x, y, button))
    def typewrite(self, text): GUI_CALLS.append(("typewrite", text))
    def hotkey(self, *keys): GUI_CALLS.append(("hotkey", keys))
    def scroll(self, amount): GUI_CALLS.append(("scroll", amount))
    def hscroll(self, amount): GUI_CALLS.append(("hscroll", amount))
    def screenshot(self): return b"\x89PNG\r\n\x1a\nFAKE"


GUI = FakeGui()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence default logging
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/screenshot":
            self._send(perform({"action": "screenshot"}, GUI))
        else:
            self._send({"ok": False, "error": "not found"}, code=404)

    def do_POST(self):
        if self.path == "/do":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            self._send(perform(payload, GUI))
        else:
            self._send({"ok": False, "error": "not found"}, code=404)


async def main():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[server] real agent.perform listening on 127.0.0.1:{port}")

    async with httpx.AsyncClient() as client:
        ex = DesktopExecutor(client, base_url=f"http://127.0.0.1:{port}")
        print(f"[executor] DesktopExecutor display_size={ex.display_size}")

        for action in [Move(100, 120), Type("hello"), Click(50, 60), Screenshot()]:
            result = await ex.do(action)
            shot = (result.screenshot_b64 or "")[:16]
            print(f"  do({type(action).__name__:11}) -> success={result.success} "
                  f"error={result.error} screenshot[:16]={shot!r}")

        only_shot = await ex.screenshot()
        print(f"[executor] screenshot() -> {only_shot!r}")

    server.shutdown()

    print("\n[verify] real gui calls recorded inside the agent:")
    for c in GUI_CALLS:
        print("   ", c)

    expected_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nFAKE").decode()
    assert only_shot == expected_b64, "screenshot base64 mismatch"
    assert ("moveTo", 100, 120) in GUI_CALLS
    assert ("typewrite", "hello") in GUI_CALLS
    assert ("click", 50, 60, "left", 1) in GUI_CALLS
    print("\n[OK] full desktop path worked over a real HTTP socket.")


if __name__ == "__main__":
    asyncio.run(main())
