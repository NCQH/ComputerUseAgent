from cua.providers.anthropic import AnthropicProvider
from cua.core.history import History
from cua.models import Click


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Resp:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


class FakeBetaMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.beta = type("B", (), {"messages": FakeBetaMessages(responses)})()


async def test_first_call_emits_click_and_tracks_tool_use_id():
    resp = _Resp(
        content=[
            _Block(type="text", text="clicking the link"),
            _Block(type="tool_use", id="tu_1", name="computer",
                   input={"action": "left_click", "coordinate": [10, 20]}),
        ],
        stop_reason="tool_use",
    )
    client = FakeClient([resp])
    provider = AnthropicProvider(client=client, display_size=(1280, 800))
    h = History()
    h.add_user("open the menu")

    out = await provider.next_actions("c2NyZWVu", h)

    assert out.actions == [Click(10, 20, "left")]
    assert out.done is False
    assert out.assistant_text == "clicking the link"
    # the request carried the beta header and computer tool
    call = client.beta.messages.calls[0]
    assert "computer-use-2025-01-24" in call["betas"]
    assert call["tools"][0]["type"] == "computer_20250124"


async def test_second_call_sends_tool_result_with_screenshot():
    r1 = _Resp([_Block(type="tool_use", id="tu_1", name="computer",
                       input={"action": "left_click", "coordinate": [1, 1]})], "tool_use")
    r2 = _Resp([_Block(type="text", text="done")], "end_turn")
    client = FakeClient([r1, r2])
    provider = AnthropicProvider(client=client, display_size=(1280, 800))
    h = History()
    h.add_user("go")
    await provider.next_actions("img1", h)
    out2 = await provider.next_actions("img2", h)

    assert out2.done is True
    assert out2.actions == []
    # second request's last message is a tool_result referencing tu_1 with an image
    second_msgs = client.beta.messages.calls[1]["messages"]
    last = second_msgs[-1]
    tool_result = last["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "tu_1"
    assert tool_result["content"][0]["type"] == "image"


async def test_new_user_request_is_injected_as_steering_text():
    r1 = _Resp([_Block(type="tool_use", id="tu_1", name="computer",
                       input={"action": "left_click", "coordinate": [1, 1]})], "tool_use")
    r2 = _Resp([_Block(type="tool_use", id="tu_2", name="computer",
                       input={"action": "left_click", "coordinate": [2, 2]})], "tool_use")
    client = FakeClient([r1, r2])
    provider = AnthropicProvider(client=client, display_size=(1280, 800))
    h = History()
    h.add_user("first task")
    await provider.next_actions("img1", h)
    h.add_user("also do this")  # steering injected mid-run
    await provider.next_actions("img2", h)

    second_user_msg = client.beta.messages.calls[1]["messages"][-1]
    texts = [b for b in second_user_msg["content"] if b.get("type") == "text"]
    assert any("also do this" in b["text"] for b in texts)
