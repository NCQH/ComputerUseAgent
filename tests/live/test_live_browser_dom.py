"""LIVE: the DOM Set-of-Marks (browser_use-style) provider drives a real browser.

Proves DomVisionProvider: it reads the page's interactive elements from the DOM,
the model picks one by mark id, and the click lands — asserted via the DOM.

Run:  CUA_LIVE=1 PYTHONUTF8=1 python -m pytest tests/live/test_live_browser_dom.py -s
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

# A few plain buttons so the model must pick the RIGHT one by its DOM label,
# not just "the big obvious thing".
PAGE_HTML = """
<!doctype html><html><head><title>start</title>
<style>
 body{font-family:sans-serif;background:#eee;padding:24px;}
 button{display:block;width:320px;height:64px;font-size:28px;margin:14px 0;}
 #status{font-size:32px;margin-top:24px;}
</style></head>
<body>
 <button onclick="document.getElementById('status').innerText='WRONG-A'">Cancel</button>
 <button id="go" onclick="document.getElementById('status').innerText='CLICKED';
   document.title='CLICKED';">Save changes</button>
 <button onclick="document.getElementById('status').innerText='WRONG-B'">Delete</button>
 <div id="status">WAITING</div>
</body></html>
"""

TASK = "Click the button that saves changes (labelled 'Save changes')."
SIZE = (800, 600)


async def _approve(_req):
    return True


async def test_dom_provider_clicks_correct_button_by_mark():
    from adaptivecua.app import build_session
    from adaptivecua.core.events import LogMessage
    from adaptivecua.executors.web_launch import BrowserSession

    async with BrowserSession(display_size=SIZE, headless=True) as page:
        await page.set_content(PAGE_HTML)

        session = build_session(
            "browser", "web",
            confirm_handler=_approve,
            page=page,
            display_size=SIZE,
            max_steps=6,
            max_runtime_seconds=120,
            max_repeated_actions=4,
        )
        logs: list[str] = []
        session.bus.subscribe(
            lambda e: logs.append(e.text) if isinstance(e, LogMessage) else None)

        await session.submit(TASK)
        await session.run()

        status = await page.inner_text("#status")
        print("\n[live-dom] final #status =", status)
        print("[live-dom] log tail:", logs[-6:])

    assert status == "CLICKED", f"DOM provider clicked the wrong/no button (status={status!r})"
