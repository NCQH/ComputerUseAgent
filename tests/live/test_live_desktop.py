"""LIVE desktop end-to-end: real OpenAI vision model drives the REAL host desktop.

Gated behind CUA_LIVE=1 + an OpenAI key. Launches a controlled always-on-top
button window in a subprocess, then drives the real mouse via LocalExecutor to
click it. Verifies a sentinel file the button writes on click — a deterministic
outcome that avoids OS-app quirks.

WARNING: this moves your real mouse and shows a large window. Don't touch input.

Run with:
  CUA_LIVE=1 PYTHONUTF8=1 python -m pytest tests/live/test_live_desktop.py -s
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import time

import pytest

from cua.env import load_dotenv

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.environ.get("CUA_LIVE") or not os.environ.get("OPENAI_API_KEY"),
    reason="live test: set CUA_LIVE=1 and OPENAI_API_KEY",
)

TASK = "There is a large green button labelled 'CLICK ME' in the middle of the screen. Click it once."


async def _approve(_req):
    return True


def _screen_size() -> tuple[int, int]:
    import pyautogui
    w, h = pyautogui.size()
    return int(w), int(h)


async def test_agent_clicks_real_desktop_button():
    from cua.app import build_session
    from cua.core.events import LogMessage

    sentinel = os.path.join(tempfile.mkdtemp(prefix="cua_live_"), "clicked.txt")
    ready = sentinel + ".ready"
    target = os.path.join(os.path.dirname(__file__), "_desktop_target.py")

    proc = subprocess.Popen([sys.executable, target, sentinel])
    try:
        # Wait until the window is up before driving the mouse.
        for _ in range(100):
            if os.path.exists(ready):
                break
            time.sleep(0.1)
        assert os.path.exists(ready), "target window did not come up"
        time.sleep(0.8)  # let it paint/raise

        size = _screen_size()
        session = build_session(
            "generic", "local",
            confirm_handler=_approve,
            display_size=size,
            max_steps=6,
            max_runtime_seconds=120,
            max_repeated_actions=4,
        )
        logs: list[str] = []
        session.bus.subscribe(
            lambda e: logs.append(e.text) if isinstance(e, LogMessage) else None)

        await session.submit(TASK)
        await session.run()

        # The click is handled on the target's Qt loop; give it a moment to land.
        for _ in range(30):
            if os.path.exists(sentinel):
                break
            await asyncio.sleep(0.1)

        clicked = os.path.exists(sentinel)
        print("\n[live-desktop] screen size =", size, "| sentinel present =", clicked)
        print("[live-desktop] log tail:", logs[-6:])
        assert clicked, "agent did not click the real-desktop button"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
