# tests/test_vision_provider.py
import json
import pytest
pytest.importorskip("PIL")

from PIL import Image
from cua.providers.vision.imaging import encode
from cua.providers.vision.provider import GenericVisionProvider
from cua.core.history import History
from cua.models import Click, Type


def _screenshot_b64(w=200, h=120):
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


def _fake_ocr(_img):
    # one element "Submit" near (40..100, 20..40) -> centre (70, 30)
    return {"text": ["Submit"], "conf": ["95"], "left": [40], "top": [20],
            "width": [60], "height": [20]}


async def test_click_via_mark_from_model_reply():
    reply = json.dumps({"reasoning": "click submit", "done": False,
                        "action": "click", "target": {"type": "mark", "id": 0}})
    client = FakeClient(reply)
    provider = GenericVisionProvider(client, ocr=_fake_ocr, use_grid=False, zoom=False)
    resp = await provider.next_actions(_screenshot_b64(), History())
    assert resp.actions == [Click(70, 30)]    # centre of the OCR box
    assert resp.done is False
    assert resp.assistant_text == "click submit"
    # structured output was requested
    kwargs = client.chat.completions.calls[0]
    assert kwargs["response_format"]["type"] == "json_schema"


async def test_type_action_needs_no_target():
    reply = json.dumps({"action": "type", "text": "hello", "done": False})
    provider = GenericVisionProvider(FakeClient(reply), ocr=_fake_ocr, use_grid=False, zoom=False)
    resp = await provider.next_actions(_screenshot_b64(), History())
    assert resp.actions == [Type("hello")]


async def test_done_with_no_action():
    reply = json.dumps({"action": "none", "done": True, "reasoning": "finished"})
    provider = GenericVisionProvider(FakeClient(reply), ocr=_fake_ocr, use_grid=False, zoom=False)
    resp = await provider.next_actions(_screenshot_b64(), History())
    assert resp.actions == []
    assert resp.done is True


async def test_malformed_reply_does_not_raise():
    provider = GenericVisionProvider(FakeClient("not json"), ocr=_fake_ocr, use_grid=False, zoom=False)
    resp = await provider.next_actions(_screenshot_b64(), History())
    assert resp.actions == []
    assert "parse error" in resp.assistant_text


async def test_malformed_target_does_not_raise():
    # a "point" target missing x/y would raise KeyError in parse_action;
    # next_actions must still return a safe response, not raise.
    reply = json.dumps({"action": "click", "target": {"type": "point"}})
    provider = GenericVisionProvider(FakeClient(reply), ocr=_fake_ocr, use_grid=False, zoom=False)
    resp = await provider.next_actions(_screenshot_b64(), History())
    assert resp.actions == []
    assert "bad action" in resp.assistant_text


async def test_history_summary_is_sent_to_model():
    reply = json.dumps({"action": "none", "done": True})
    client = FakeClient(reply)
    provider = GenericVisionProvider(client, ocr=_fake_ocr, use_grid=False, zoom=False)
    h = History()
    h.add_user("open the menu")
    await provider.next_actions(_screenshot_b64(), h)
    sent = json.dumps(client.chat.completions.calls[0]["messages"])
    assert "open the menu" in sent


async def test_ocr_failure_degrades_to_grid_not_screenshot_error():
    """A missing tesseract binary (OCR backend raises) must NOT fail the whole
    step. Marks are skipped; the grid/point path still yields an action."""
    def boom_ocr(_img):
        raise RuntimeError("tesseract is not installed or it's not in your PATH")

    reply = json.dumps({"action": "click", "done": False,
                        "target": {"type": "point", "x": 10, "y": 10}})
    provider = GenericVisionProvider(FakeClient(reply), ocr=boom_ocr,
                                     use_marks=True, use_grid=True, zoom=False)
    resp = await provider.next_actions(_screenshot_b64(), History())
    assert resp.actions == [Click(10, 10)]
    assert "screenshot error" not in resp.assistant_text


async def test_targeting_hint_tells_model_when_marks_absent():
    """When OCR yields no marks, the prompt must say so, so the model uses
    grid/point instead of inventing mark ids."""
    def empty_ocr(_img):
        return {"text": [], "conf": [], "left": [], "top": [], "width": [], "height": []}

    reply = json.dumps({"action": "none", "done": True})
    client = FakeClient(reply)
    provider = GenericVisionProvider(client, ocr=empty_ocr, use_grid=True, zoom=False)
    await provider.next_actions(_screenshot_b64(), History())
    sent = json.dumps(client.chat.completions.calls[0]["messages"])
    assert "NO marks available" in sent
    assert "grid available" in sent


async def test_corrupt_screenshot_does_not_raise():
    reply = json.dumps({"action": "none", "done": False, "reasoning": "ok"})
    client = FakeClient(reply)
    provider = GenericVisionProvider(client, ocr=_fake_ocr, use_grid=False, zoom=False)
    resp = await provider.next_actions("@@@not-base64@@@", History())
    assert isinstance(resp, __import__("cua.models", fromlist=["ProviderResponse"]).ProviderResponse)
    assert resp.actions == []
    assert resp.assistant_text  # non-empty
