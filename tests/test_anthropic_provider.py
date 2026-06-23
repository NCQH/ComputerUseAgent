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


async def test_thinking_blocks_preserved_in_history():
    # First response has a thinking block followed by a computer tool_use
    r1 = _Resp(
        content=[
            _Block(type="thinking", thinking="reasoning...", signature="sig"),
            _Block(type="tool_use", id="tu_1", name="computer",
                   input={"action": "left_click", "coordinate": [5, 5]}),
        ],
        stop_reason="tool_use",
    )
    # Second response is a done response
    r2 = _Resp([_Block(type="text", text="all done")], "end_turn")
    client = FakeClient([r1, r2])
    provider = AnthropicProvider(client=client, display_size=(1280, 800))
    h = History()
    h.add_user("do something")

    await provider.next_actions("img1", h)
    await provider.next_actions("img2", h)

    # The second call's messages must include the prior assistant turn
    # with the thinking block preserved
    second_call_messages = client.beta.messages.calls[1]["messages"]
    # Find the assistant turn that was appended after the first response
    assistant_turns = [m for m in second_call_messages if m["role"] == "assistant"]
    assert assistant_turns, "No assistant turn found in second call messages"
    assistant_content = assistant_turns[-1]["content"]
    thinking_dicts = [b for b in assistant_content if b.get("type") == "thinking"]
    assert thinking_dicts, "thinking block was dropped from assistant turn"
    assert thinking_dicts[0] == {"type": "thinking", "thinking": "reasoning...", "signature": "sig"}


def _user_has_image(msg) -> bool:
    for b in msg["content"]:
        if b.get("type") == "image":
            return True
        if b.get("type") == "tool_result":
            if any(c.get("type") == "image" for c in b.get("content", [])):
                return True
    return False


async def test_old_screenshots_pruned_to_cap_context_growth():
    """Old screenshots dominate token cost. With image_retention=1 only the most
    recent user turn keeps its image; older ones become a text placeholder, while
    the tool_use/tool_result pairing stays intact."""
    r1 = _Resp([_Block(type="tool_use", id="tu_1", name="computer",
                       input={"action": "left_click", "coordinate": [1, 1]})], "tool_use")
    r2 = _Resp([_Block(type="tool_use", id="tu_2", name="computer",
                       input={"action": "left_click", "coordinate": [2, 2]})], "tool_use")
    r3 = _Resp([_Block(type="text", text="done")], "end_turn")
    client = FakeClient([r1, r2, r3])
    provider = AnthropicProvider(client=client, display_size=(1280, 800), image_retention=1)
    h = History()
    h.add_user("go")
    await provider.next_actions("img1", h)
    await provider.next_actions("img2", h)
    await provider.next_actions("img3", h)

    msgs = client.beta.messages.calls[2]["messages"]
    user_msgs = [m for m in msgs if m["role"] == "user"]
    assert _user_has_image(user_msgs[-1]) is True          # newest keeps its image
    assert all(not _user_has_image(m) for m in user_msgs[:-1])  # older pruned
    # the tool_result structure (id pairing) survives pruning
    pruned_tool_results = [
        b for b in user_msgs[1]["content"] if b.get("type") == "tool_result"
    ]
    assert pruned_tool_results and pruned_tool_results[0]["tool_use_id"] == "tu_1"
    # a placeholder marks where an image was dropped
    assert any(b.get("type") == "text" and "omitted" in b.get("text", "")
               for b in user_msgs[0]["content"])


async def test_image_retention_defaults_keep_recent_images():
    """Default retention must not strip images within a short run (regression guard
    for the existing two-step tests)."""
    r1 = _Resp([_Block(type="tool_use", id="tu_1", name="computer",
                       input={"action": "left_click", "coordinate": [1, 1]})], "tool_use")
    r2 = _Resp([_Block(type="text", text="done")], "end_turn")
    client = FakeClient([r1, r2])
    provider = AnthropicProvider(client=client, display_size=(1280, 800))
    h = History()
    h.add_user("go")
    await provider.next_actions("img1", h)
    await provider.next_actions("img2", h)
    user_msgs = [m for m in client.beta.messages.calls[1]["messages"] if m["role"] == "user"]
    assert all(_user_has_image(m) for m in user_msgs)


async def test_pending_id_reset_when_done():
    r1 = _Resp(
        content=[
            _Block(type="tool_use", id="tu_1", name="computer",
                   input={"action": "left_click", "coordinate": [1, 1]}),
        ],
        stop_reason="tool_use",
    )
    r2 = _Resp([_Block(type="text", text="finished")], "end_turn")
    client = FakeClient([r1, r2])
    provider = AnthropicProvider(client=client, display_size=(1280, 800))
    h = History()
    h.add_user("task")

    await provider.next_actions("img1", h)
    assert provider._pending_tool_use_id == "tu_1"

    await provider.next_actions("img2", h)
    assert provider._pending_tool_use_id is None
