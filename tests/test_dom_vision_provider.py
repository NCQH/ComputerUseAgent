"""Unit tests for DomVisionProvider (DOM Set-of-Marks), fakes only."""
import json

import pytest

pytest.importorskip("PIL")

from PIL import Image

from adaptivecua.core.history import History
from adaptivecua.models import Click, Type
from adaptivecua.providers.browser.provider import DomVisionProvider
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


class FakePage:
    def __init__(self, raw): self._raw = raw

    async def evaluate(self, js):
        return self._raw


DOM = [
    {"x": 100, "y": 50, "width": 200, "height": 60, "tag": "button", "role": "", "type": "", "text": "Submit"},
    {"x": 100, "y": 150, "width": 300, "height": 40, "tag": "input", "role": "", "type": "text", "text": "Search"},
]


async def test_dom_provider_clicks_element_by_mark_index():
    reply = json.dumps({"reasoning": "click submit", "done": False,
                        "action": "click", "target": {"type": "mark", "id": 0}})
    client = FakeClient(reply)
    provider = DomVisionProvider(client, page=FakePage(DOM), display_size=(800, 600), use_grid=False)
    resp = await provider.next_actions(_screenshot_b64(), History())
    assert resp.actions == [Click(200, 80)]    # centre of element 0's box (100,50,300,110)
    assert resp.done is False
    assert resp.assistant_text == "click submit"
    assert client.chat.completions.calls[0]["response_format"]["type"] == "json_schema"


async def test_dom_provider_sends_indexed_element_list_to_model():
    reply = json.dumps({"action": "none", "done": True})
    client = FakeClient(reply)
    provider = DomVisionProvider(client, page=FakePage(DOM), display_size=(800, 600), use_grid=False)
    await provider.next_actions(_screenshot_b64(), History())
    sent = json.dumps(client.chat.completions.calls[0]["messages"])
    assert "[0]" in sent and "Submit" in sent
    assert "[1]" in sent and "Search" in sent


async def test_dom_provider_type_needs_no_target():
    reply = json.dumps({"action": "type", "text": "hi", "done": False})
    provider = DomVisionProvider(FakeClient(reply), page=FakePage(DOM), display_size=(800, 600), use_grid=False)
    resp = await provider.next_actions(_screenshot_b64(), History())
    assert resp.actions == [Type("hi")]


async def test_dom_extraction_failure_degrades_to_point_target():
    class BoomPage:
        async def evaluate(self, js):
            raise RuntimeError("execution context was destroyed")

    reply = json.dumps({"action": "click", "done": False,
                        "target": {"type": "point", "x": 10, "y": 10}})
    provider = DomVisionProvider(FakeClient(reply), page=BoomPage(), display_size=(800, 600), use_grid=False)
    resp = await provider.next_actions(_screenshot_b64(), History())
    assert resp.actions == [Click(10, 10)]
    assert "screenshot error" not in resp.assistant_text


async def test_dom_provider_malformed_reply_does_not_raise():
    provider = DomVisionProvider(FakeClient("not json"), page=FakePage(DOM), display_size=(800, 600))
    resp = await provider.next_actions(_screenshot_b64(), History())
    assert resp.actions == []
    assert "parse error" in resp.assistant_text
