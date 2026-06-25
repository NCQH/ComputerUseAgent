"""Unit tests for A11yVisionProvider (desktop a11y Set-of-Marks), fakes only.

Mirrors test_dom_vision_provider — same Set-of-Marks contract, but elements come
from an injected a11y backend instead of a Playwright page."""
import json

import pytest

pytest.importorskip("PIL")

from PIL import Image

from adaptivecua.core.history import History
from adaptivecua.models import Click, Type
from adaptivecua.providers.a11y.provider import A11yVisionProvider
from adaptivecua.providers.a11y.uia_backend import NullBackend
from adaptivecua.providers.vision.imaging import encode


def _screenshot_b64(w=800, h=600):
    return encode(Image.new("RGB", (w, h), (255, 255, 255)))


class FakeMessage:
    def __init__(self, content): self.content = content


class FakeChoice:
    def __init__(self, content): self.message = FakeMessage(content)


class FakeCompletion:
    def __init__(self, content): self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeCompletion(self._replies[min(len(self.calls) - 1, len(self._replies) - 1)])


class FakeChat:
    def __init__(self, replies): self.completions = FakeCompletions(replies)


class FakeClient:
    def __init__(self, *replies): self.chat = FakeChat(replies)


class FakeBackend:
    """Returns canned UIA-shaped records (same dict shape as the DOM backend)."""
    def __init__(self, raw): self._raw = raw

    def elements(self, display_size):
        return self._raw


class BoomBackend:
    def elements(self, display_size):
        raise RuntimeError("UIA COM error")


TREE = [
    {"x": 100, "y": 50, "width": 200, "height": 60, "tag": "button", "role": "", "type": "", "text": "OK"},
    {"x": 100, "y": 150, "width": 300, "height": 40, "tag": "edit", "role": "", "type": "", "text": "Name"},
]


async def test_a11y_provider_clicks_control_by_mark_index():
    reply = json.dumps({"reasoning": "click ok", "done": False,
                        "action": "click", "target": {"type": "mark", "id": 0}})
    client = FakeClient(reply)
    provider = A11yVisionProvider(client, backend=FakeBackend(TREE),
                                  display_size=(800, 600), use_grid=False)
    resp = await provider.next_actions(_screenshot_b64(), History())
    assert resp.actions == [Click(200, 80)]    # centre of mark 0's box (100,50,300,110)
    assert resp.done is False
    assert resp.assistant_text == "click ok"


async def test_a11y_provider_sends_indexed_control_list_to_model():
    reply = json.dumps({"action": "none", "done": True})
    client = FakeClient(reply)
    provider = A11yVisionProvider(client, backend=FakeBackend(TREE),
                                  display_size=(800, 600), use_grid=False)
    await provider.next_actions(_screenshot_b64(), History())
    sent = json.dumps(client.chat.completions.calls[0]["messages"])
    assert "[0]" in sent and "OK" in sent
    assert "[1]" in sent and "Name" in sent
    assert "desktop application" in sent.lower()   # desktop system prompt, not browser


async def test_a11y_backend_failure_degrades_to_point_target():
    reply = json.dumps({"action": "click", "done": False,
                        "target": {"type": "point", "x": 10, "y": 10}})
    provider = A11yVisionProvider(FakeClient(reply), backend=BoomBackend(),
                                  display_size=(800, 600), use_grid=False)
    resp = await provider.next_actions(_screenshot_b64(), History())
    assert resp.actions == [Click(10, 10)]         # no crash; grid/point still works
    assert "screenshot error" not in resp.assistant_text


async def test_a11y_provider_defaults_to_null_backend():
    """No backend -> NullBackend -> empty element list -> grid/point fallback."""
    reply = json.dumps({"action": "click", "done": False,
                        "target": {"type": "point", "x": 5, "y": 5}})
    provider = A11yVisionProvider(FakeClient(reply), display_size=(800, 600), use_grid=False)
    assert isinstance(provider.backend, NullBackend)
    resp = await provider.next_actions(_screenshot_b64(), History())
    assert resp.actions == [Click(5, 5)]


async def test_a11y_provider_malformed_reply_does_not_raise():
    provider = A11yVisionProvider(FakeClient("not json"), backend=FakeBackend(TREE),
                                  display_size=(800, 600))
    resp = await provider.next_actions(_screenshot_b64(), History())
    assert resp.actions == []
    assert "parse error" in resp.assistant_text
