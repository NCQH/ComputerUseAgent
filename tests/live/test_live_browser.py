"""LIVE browser end-to-end: real OpenAI vision model drives a real Chromium page.

Gated behind CUA_LIVE=1 + an OpenAI key so the default offline suite stays green.
Run with:  CUA_LIVE=1 PYTHONUTF8=1 python -m pytest tests/live/test_live_browser.py -s

The agent must look at a screenshot, find the big yellow button, and click it; we
assert on the resulting DOM, not on any intermediate coordinate.
"""
from __future__ import annotations

import os

import pytest

from adaptivecua.env import load_dotenv

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.environ.get("CUA_LIVE") or not os.environ.get("OPENAI_API_KEY"),
    reason="live test: set CUA_LIVE=1 and OPENAI_API_KEY",
)

PAGE_HTML = """
<!doctype html><html><head><title>start</title>
<style>
 html,body{margin:0;height:100%;font-family:sans-serif;background:#0b3d91;}
 #b{position:absolute;top:18%;left:8%;width:84%;height:56%;font-size:72px;
    background:#ffcc00;color:#000;border:10px solid #000;cursor:pointer;}
 #status{position:absolute;bottom:6%;left:6%;font-size:44px;color:#fff;}
</style></head>
<body>
 <button id="b" onclick="document.getElementById('status').innerText='CLICKED';
   document.title='CLICKED';">PRESS ME</button>
 <div id="status">WAITING</div>
</body></html>
"""

TASK = "There is a large yellow button labelled 'PRESS ME'. Click it exactly once."
SIZE = (800, 600)


async def _approve(_req):
    return True


async def test_agent_clicks_button_in_real_browser():
    from adaptivecua.app import build_session
    from adaptivecua.executors.web_launch import BrowserSession

    async with BrowserSession(display_size=SIZE, headless=True) as page:
        await page.set_content(PAGE_HTML)

        session = build_session(
            "generic", "web",
            confirm_handler=_approve,
            page=page,
            display_size=SIZE,
            max_steps=6,
            max_runtime_seconds=120,
            max_repeated_actions=4,
        )
        logs: list[str] = []
        from adaptivecua.core.events import LogMessage
        session.bus.subscribe(
            lambda e: logs.append(e.text) if isinstance(e, LogMessage) else None)

        await session.submit(TASK)
        await session.run()

        status = await page.inner_text("#status")
        print("\n[live-browser] final #status =", status)
        print("[live-browser] log tail:", logs[-6:])

    assert status == "CLICKED", f"agent did not click the button (status={status!r})"
