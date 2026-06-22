# tests/test_openai_provider.py
from cua.providers.openai import OpenAIProvider
from cua.core.history import History
from cua.models import Click


class _Item:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.__dict__.setdefault("pending_safety_checks", [])


class _Resp:
    def __init__(self, id, output):
        self.id = id
        self.output = output


class FakeResponses:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.responses = FakeResponses(responses)


async def test_first_call_returns_click_and_sets_previous_id():
    resp = _Resp("resp_1", [
        _Item(type="computer_call", call_id="call_1",
              action={"type": "click", "x": 10, "y": 20}, pending_safety_checks=[]),
    ])
    client = FakeClient([resp])
    provider = OpenAIProvider(client=client, display_size=(1280, 800))
    h = History(); h.add_user("do it")

    out = await provider.next_actions("c2NyZWVu", h)

    assert out.actions == [Click(10, 20, "left")]
    assert out.done is False
    assert out.model_flagged_risky is False
    call = client.responses.calls[0]
    assert call["tools"][0]["type"] == "computer_use_preview"
    assert "previous_response_id" not in call or call["previous_response_id"] is None


async def test_pending_safety_check_sets_risky_flag():
    resp = _Resp("resp_1", [
        _Item(type="computer_call", call_id="call_1",
              action={"type": "click", "x": 1, "y": 1},
              pending_safety_checks=[{"id": "sc_1", "code": "malicious", "message": "?"}]),
    ])
    client = FakeClient([resp])
    provider = OpenAIProvider(client=client)
    h = History(); h.add_user("go")
    out = await provider.next_actions("img", h)
    assert out.model_flagged_risky is True


async def test_second_call_sends_computer_call_output_with_screenshot():
    r1 = _Resp("resp_1", [_Item(type="computer_call", call_id="call_1",
                                action={"type": "click", "x": 1, "y": 1})])
    r2 = _Resp("resp_2", [_Item(type="message", content=[_Item(type="output_text", text="all done")])])
    client = FakeClient([r1, r2])
    provider = OpenAIProvider(client=client)
    h = History(); h.add_user("go")
    await provider.next_actions("img1", h)
    out2 = await provider.next_actions("img2", h)

    assert out2.done is True
    assert out2.assistant_text == "all done"
    second = client.responses.calls[1]
    assert second["previous_response_id"] == "resp_1"
    out_item = second["input"][0]
    assert out_item["type"] == "computer_call_output"
    assert out_item["call_id"] == "call_1"
    assert out_item["output"]["type"] == "computer_screenshot"


async def test_pending_call_id_reset_when_done():
    """After a done response (no computer_call), _pending_call_id must be None.

    If it is not reset, a subsequent task on the same provider instance would
    incorrectly enter the subsequent-call branch and send a stale
    computer_call_output against an already-finished response.
    """
    r1 = _Resp("resp_1", [_Item(type="computer_call", call_id="call_42",
                                action={"type": "click", "x": 5, "y": 5})])
    r2 = _Resp("resp_2", [_Item(type="message", content=[_Item(type="output_text", text="done")])])
    client = FakeClient([r1, r2])
    provider = OpenAIProvider(client=client)
    h = History(); h.add_user("start")

    # First call: sets _pending_call_id to "call_42"
    await provider.next_actions("img1", h)
    assert provider._pending_call_id == "call_42"

    # Second call: no computer_call in response → done=True, must reset _pending_call_id
    out = await provider.next_actions("img2", h)
    assert out.done is True
    assert provider._pending_call_id is None
