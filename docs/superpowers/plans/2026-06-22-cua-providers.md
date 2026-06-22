# CUA Providers Implementation Plan (Plan 2 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the two real `CUAProvider`s defined by the Plan 1 interface — `AnthropicProvider` (Claude computer use) and `OpenAIProvider` (OpenAI computer-use-preview) — plus a `build_provider` factory and config, so the agent loop can drive a real model. Translation logic is pure and unit-tested; the stateful provider classes are tested against injected fake SDK clients (no real API calls).

**Architecture:** Each provider implements `async def next_actions(self, screenshot_b64, history) -> ProviderResponse` (Plan 1). A provider holds an injected SDK client and maintains its own native conversation state across calls, bridging the neutral `History`/`Action` types to the vendor's computer-use tool protocol. Translation between neutral `Action`s and each vendor's action schema lives in pure helper modules so it can be exhaustively unit-tested.

**Tech Stack:** Python 3.11+, `anthropic` SDK (Messages API, computer use beta), `openai` SDK (Responses API), pytest + pytest-asyncio.

## Global Constraints

- Python 3.11+; asyncio. Builds on Plan 1 (`cua.models`, `cua.core.history`, `cua.providers.base`) — those exist and are committed on `master`.
- Anthropic: model **`claude-opus-4-8`**; computer use tool type **`computer_20250124`**, tool name `"computer"`; beta header **`computer-use-2025-01-24`** via `client.beta.messages.create(betas=[...])`; adaptive thinking (`thinking={"type": "adaptive"}`) — never `budget_tokens` (400 on Opus 4.8). Screenshots returned to the model as a `tool_result` whose content is an `image` block (`source: {type: "base64", media_type: "image/png", data: ...}`).
- OpenAI: model **`computer-use-preview`**; Responses API `client.responses.create(...)` with tool `{"type": "computer_use_preview", "display_width", "display_height", "environment"}` and `truncation="auto"`; screenshots returned as a `computer_call_output` item (`output: {type: "computer_screenshot", image_url: "data:image/png;base64,..."}`); `pending_safety_checks` echoed back as `acknowledged_safety_checks`.
- **Dependency injection for testability:** every provider takes its SDK client as a constructor argument. Tests inject a fake client; no test makes a real network call. API keys are read from env only in the `build_provider` factory, never hardcoded.
- `model_flagged_risky`: OpenAI maps from `pending_safety_checks` (non-empty → True). Anthropic has no equivalent field → `False` by default; the two-layer gate's denylist (Plan 1) remains the cross-provider safety net.
- Exact vendor tool/action field names below are correct as of this writing but MUST be verified against live docs at implementation time (WebFetch `https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use.md` and `https://platform.openai.com/docs/guides/tools-computer-use`). The pure translation helpers isolate any drift to one module per vendor.
- Immutability: new `Action` dataclasses are `frozen=True`. Files focused (<400 lines). Tests AAA; target ≥80%.

---

## File Structure

- Modify: `cua/models.py` — add `DoubleClick`, `TripleClick`; extend the `Action` union (Task 1)
- Create: `cua/providers/anthropic_translate.py` — pure neutral↔Claude action translation (Task 2)
- Create: `cua/providers/anthropic.py` — `AnthropicProvider` (Task 3)
- Create: `cua/providers/openai_translate.py` — pure neutral↔OpenAI action translation (Task 4)
- Create: `cua/providers/openai.py` — `OpenAIProvider` (Task 5)
- Create: `cua/config.py` — provider/model config + `build_provider` factory (Task 6)
- Test: `tests/test_models_clicks.py`, `tests/test_anthropic_translate.py`, `tests/test_anthropic_provider.py`, `tests/test_openai_translate.py`, `tests/test_openai_provider.py`, `tests/test_config.py`

---

### Task 1: Extend neutral Action vocabulary

**Files:**
- Modify: `cua/models.py`
- Test: `tests/test_models_clicks.py`

**Interfaces:**
- Consumes: existing `cua.models`.
- Produces: frozen `DoubleClick(x:int, y:int, button:str="left")`, `TripleClick(x:int, y:int, button:str="left")`; the `Action` union now also includes both. (Existing `Action` members unchanged — purely additive, so all Plan 1 tests still pass.)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models_clicks.py
import pytest
from dataclasses import FrozenInstanceError
from cua.models import DoubleClick, TripleClick


def test_double_click_defaults_to_left():
    a = DoubleClick(x=3, y=4)
    assert (a.x, a.y, a.button) == (3, 4, "left")


def test_triple_click_holds_button():
    a = TripleClick(x=1, y=2, button="right")
    assert a.button == "right"


def test_clicks_are_frozen():
    with pytest.raises(FrozenInstanceError):
        DoubleClick(1, 2).x = 9  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models_clicks.py -v`
Expected: FAIL — `ImportError: cannot import name 'DoubleClick'`.

- [ ] **Step 3: Write minimal implementation**

In `cua/models.py`, add after the `Click` dataclass:

```python
@dataclass(frozen=True)
class DoubleClick:
    x: int
    y: int
    button: str = "left"


@dataclass(frozen=True)
class TripleClick:
    x: int
    y: int
    button: str = "left"
```

And extend the `Action` union (add the two new members):

```python
Action = (
    Click | DoubleClick | TripleClick | Type | Key | Scroll | Move | Drag | Screenshot | Wait
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models_clicks.py tests/test_models.py -v`
Expected: PASS (new tests pass; Plan 1 model tests still pass).

- [ ] **Step 5: Commit**

```bash
git add cua/models.py tests/test_models_clicks.py
git commit -m "feat: add DoubleClick/TripleClick to neutral action vocabulary"
```

---

### Task 2: Anthropic translation helpers (pure)

**Files:**
- Create: `cua/providers/anthropic_translate.py`
- Test: `tests/test_anthropic_translate.py`

**Interfaces:**
- Consumes: `cua.models` action types.
- Produces:
  - `claude_action_to_neutral(input_dict: dict) -> Action` — maps a `computer_20250124` tool_use `input` to a neutral `Action`. Raises `ValueError` on unknown action.
  - `COMPUTER_TOOL(width: int, height: int) -> dict` — returns the tool definition dict `{"type": "computer_20250124", "name": "computer", "display_width_px": width, "display_height_px": height, "display_number": 1}`.

Mapping (Claude `action` → neutral): `left_click`→`Click(...,"left")`, `right_click`→`Click(...,"right")`, `middle_click`→`Click(...,"middle")`, `double_click`→`DoubleClick`, `triple_click`→`TripleClick`, `mouse_move`→`Move`, `left_click_drag`→`Drag(start→coordinate)`, `type`→`Type(text)`, `key`→`Key(text)`, `scroll`→`Scroll(coordinate, scroll_direction, scroll_amount)`, `screenshot`→`Screenshot()`, `wait`→`Wait(ms=int(duration*1000))`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_anthropic_translate.py
import pytest
from cua.providers.anthropic_translate import claude_action_to_neutral, COMPUTER_TOOL
from cua.models import (
    Click, DoubleClick, TripleClick, Move, Drag, Type, Key, Scroll, Screenshot, Wait,
)


def test_left_click():
    assert claude_action_to_neutral({"action": "left_click", "coordinate": [10, 20]}) == Click(10, 20, "left")


def test_right_and_middle_click():
    assert claude_action_to_neutral({"action": "right_click", "coordinate": [1, 2]}) == Click(1, 2, "right")
    assert claude_action_to_neutral({"action": "middle_click", "coordinate": [3, 4]}) == Click(3, 4, "middle")


def test_double_and_triple_click():
    assert claude_action_to_neutral({"action": "double_click", "coordinate": [5, 6]}) == DoubleClick(5, 6)
    assert claude_action_to_neutral({"action": "triple_click", "coordinate": [7, 8]}) == TripleClick(7, 8)


def test_move_and_drag():
    assert claude_action_to_neutral({"action": "mouse_move", "coordinate": [9, 9]}) == Move(9, 9)
    assert claude_action_to_neutral(
        {"action": "left_click_drag", "start_coordinate": [1, 1], "coordinate": [5, 5]}
    ) == Drag(1, 1, 5, 5)


def test_type_and_key():
    assert claude_action_to_neutral({"action": "type", "text": "hello"}) == Type("hello")
    assert claude_action_to_neutral({"action": "key", "text": "ctrl+a"}) == Key("ctrl+a")


def test_scroll():
    assert claude_action_to_neutral(
        {"action": "scroll", "coordinate": [2, 3], "scroll_direction": "down", "scroll_amount": 5}
    ) == Scroll(2, 3, "down", 5)


def test_screenshot_and_wait():
    assert claude_action_to_neutral({"action": "screenshot"}) == Screenshot()
    assert claude_action_to_neutral({"action": "wait", "duration": 2}) == Wait(ms=2000)


def test_unknown_action_raises():
    with pytest.raises(ValueError):
        claude_action_to_neutral({"action": "teleport"})


def test_computer_tool_definition():
    tool = COMPUTER_TOOL(1280, 800)
    assert tool["type"] == "computer_20250124"
    assert tool["name"] == "computer"
    assert tool["display_width_px"] == 1280
    assert tool["display_height_px"] == 800
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_anthropic_translate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cua.providers.anthropic_translate'`.

- [ ] **Step 3: Write minimal implementation**

```python
# cua/providers/anthropic_translate.py
"""Pure translation between Claude computer_20250124 actions and neutral Actions."""
from __future__ import annotations

from cua.models import (
    Action, Click, DoubleClick, TripleClick, Drag, Key, Move, Screenshot, Scroll, Type, Wait,
)

_CLICK_BUTTON = {"left_click": "left", "right_click": "right", "middle_click": "middle"}


def COMPUTER_TOOL(width: int, height: int) -> dict:
    return {
        "type": "computer_20250124",
        "name": "computer",
        "display_width_px": width,
        "display_height_px": height,
        "display_number": 1,
    }


def claude_action_to_neutral(input_dict: dict) -> Action:
    action = input_dict.get("action")
    coord = input_dict.get("coordinate")

    if action in _CLICK_BUTTON:
        return Click(coord[0], coord[1], _CLICK_BUTTON[action])
    if action == "double_click":
        return DoubleClick(coord[0], coord[1])
    if action == "triple_click":
        return TripleClick(coord[0], coord[1])
    if action == "mouse_move":
        return Move(coord[0], coord[1])
    if action == "left_click_drag":
        start = input_dict["start_coordinate"]
        return Drag(start[0], start[1], coord[0], coord[1])
    if action == "type":
        return Type(input_dict["text"])
    if action == "key":
        return Key(input_dict["text"])
    if action == "scroll":
        return Scroll(coord[0], coord[1], input_dict["scroll_direction"], input_dict["scroll_amount"])
    if action == "screenshot":
        return Screenshot()
    if action == "wait":
        return Wait(ms=int(float(input_dict.get("duration", 1)) * 1000))
    raise ValueError(f"Unknown Claude computer action: {action!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_anthropic_translate.py -v`
Expected: PASS (10 passed).

- [ ] **Step 5: Commit**

```bash
git add cua/providers/anthropic_translate.py tests/test_anthropic_translate.py
git commit -m "feat: pure Claude computer-use action translation"
```

---

### Task 3: AnthropicProvider

**Files:**
- Create: `cua/providers/anthropic.py`
- Test: `tests/test_anthropic_provider.py`

**Interfaces:**
- Consumes: `claude_action_to_neutral`, `COMPUTER_TOOL` (Task 2); `History`/entries (`cua.core.history`); `ProviderResponse` (`cua.models`); the `CUAProvider` protocol (`cua.providers.base`).
- Produces: `AnthropicProvider(client, model: str = "claude-opus-4-8", display_size=(1280, 800), system: str = DEFAULT_SYSTEM)`. Implements `async def next_actions(self, screenshot_b64, history) -> ProviderResponse`. The injected `client` must expose `client.beta.messages.create(...)` returning an object with `.content` (list of blocks: each block has `.type`, and for `type=="text"` a `.text`, for `type=="tool_use"` an `.id`/`.name`/`.input`) and `.stop_reason`.

**Behavior of `next_actions`:**
- Maintains `self._messages` (native), `self._seen_user_count`, `self._pending_tool_use_id`.
- Drain new `UserEntry` items in `history` beyond `self._seen_user_count` → collect their text.
- First call (no `_pending_tool_use_id`, messages empty): append a user message: content = `[{type:"text", text: <task text>}, {type:"image", source:{...screenshot...}}]`.
- Subsequent call: append a user message containing a `tool_result` for `self._pending_tool_use_id` whose content is `[{type:"image", source:{...screenshot...}}]`, plus any new user text as an extra `{type:"text"}` block in the same user message (steering).
- Call `client.beta.messages.create(model, max_tokens=4096, thinking={"type":"adaptive"}, tools=[COMPUTER_TOOL(w,h)], betas=["computer-use-2025-01-24"], system=self.system, messages=self._messages)`.
- Append the assistant response (`{"role":"assistant","content": <raw blocks as dicts>}`) to `self._messages`.
- Extract text blocks → `assistant_text`; extract the FIRST `tool_use` whose `name=="computer"` → translate its `input` to one neutral `Action`; set `self._pending_tool_use_id` to that block's id. `done = (stop_reason == "end_turn")` and no computer tool_use present. `model_flagged_risky=False`.
- Return `ProviderResponse(actions=[action] if action else [], done=done, assistant_text=assistant_text, model_flagged_risky=False)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_anthropic_provider.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_anthropic_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cua.providers.anthropic'`.

- [ ] **Step 3: Write minimal implementation**

```python
# cua/providers/anthropic.py
"""AnthropicProvider — drives Claude computer use to produce neutral actions."""
from __future__ import annotations

from cua.core.history import History, UserEntry
from cua.models import ProviderResponse
from cua.providers.anthropic_translate import COMPUTER_TOOL, claude_action_to_neutral

DEFAULT_SYSTEM = (
    "You are operating a computer to accomplish the user's tasks. "
    "Before any irreversible action (submitting forms, deleting, purchasing, sending), "
    "state clearly that it is irreversible. Take one action at a time."
)
BETA = "computer-use-2025-01-24"


def _image_block(screenshot_b64: str) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64},
    }


def _blocks_to_dicts(content) -> list[dict]:
    out: list[dict] = []
    for b in content:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


class AnthropicProvider:
    def __init__(self, client, model: str = "claude-opus-4-8",
                 display_size: tuple[int, int] = (1280, 800), system: str = DEFAULT_SYSTEM) -> None:
        self.client = client
        self.model = model
        self.display_size = display_size
        self.system = system
        self._messages: list[dict] = []
        self._seen_user_count = 0
        self._pending_tool_use_id: str | None = None

    def _drain_user_text(self, history: History) -> str:
        users = [e.text for e in history.entries() if isinstance(e, UserEntry)]
        new = users[self._seen_user_count:]
        self._seen_user_count = len(users)
        return "\n".join(new)

    async def next_actions(self, screenshot_b64: str, history: History) -> ProviderResponse:
        new_text = self._drain_user_text(history)

        if self._pending_tool_use_id is None:
            content: list[dict] = []
            if new_text:
                content.append({"type": "text", "text": new_text})
            content.append(_image_block(screenshot_b64))
            self._messages.append({"role": "user", "content": content})
        else:
            content = [{
                "type": "tool_result",
                "tool_use_id": self._pending_tool_use_id,
                "content": [_image_block(screenshot_b64)],
            }]
            if new_text:
                content.append({"type": "text", "text": f"Additional request: {new_text}"})
            self._messages.append({"role": "user", "content": content})

        w, h = self.display_size
        resp = self.client.beta.messages.create(
            model=self.model,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            tools=[COMPUTER_TOOL(w, h)],
            betas=[BETA],
            system=self.system,
            messages=self._messages,
        )

        self._messages.append({"role": "assistant", "content": _blocks_to_dicts(resp.content)})

        assistant_text = " ".join(b.text for b in resp.content if b.type == "text").strip()
        tool_use = next(
            (b for b in resp.content if b.type == "tool_use" and b.name == "computer"), None
        )
        if tool_use is not None:
            self._pending_tool_use_id = tool_use.id
            actions = [claude_action_to_neutral(tool_use.input)]
            done = False
        else:
            actions = []
            done = resp.stop_reason == "end_turn"

        return ProviderResponse(
            actions=actions, done=done, assistant_text=assistant_text, model_flagged_risky=False
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_anthropic_provider.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add cua/providers/anthropic.py tests/test_anthropic_provider.py
git commit -m "feat: AnthropicProvider driving Claude computer use"
```

---

### Task 4: OpenAI translation helpers (pure)

**Files:**
- Create: `cua/providers/openai_translate.py`
- Test: `tests/test_openai_translate.py`

**Interfaces:**
- Consumes: `cua.models` action types.
- Produces: `openai_action_to_neutral(action: dict) -> Action` mapping a Responses API `computer_call.action` to a neutral `Action`. Raises `ValueError` on unknown type.

Mapping (OpenAI `action.type` → neutral): `click`→`Click(x,y,button)` (button default `"left"`), `double_click`→`DoubleClick(x,y)`, `scroll`→`Scroll(x,y, direction-from-sign, amount)` where `scroll_y>0`→`"down"`, `<0`→`"up"`, else from `scroll_x` (`>0`→`"right"`, `<0`→`"left"`), amount = `abs(scroll_y) or abs(scroll_x)`, `type`→`Type(text)`, `keypress`→`Key("+".join(keys).lower())`, `wait`→`Wait(ms=1000)`, `screenshot`→`Screenshot()`, `move`→`Move(x,y)`, `drag`→`Drag(path[0].x, path[0].y, path[-1].x, path[-1].y)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_openai_translate.py
import pytest
from cua.providers.openai_translate import openai_action_to_neutral
from cua.models import Click, DoubleClick, Scroll, Type, Key, Wait, Screenshot, Move, Drag


def test_click_defaults_left():
    assert openai_action_to_neutral({"type": "click", "x": 10, "y": 20}) == Click(10, 20, "left")


def test_click_with_button():
    assert openai_action_to_neutral({"type": "click", "x": 1, "y": 2, "button": "right"}) == Click(1, 2, "right")


def test_double_click():
    assert openai_action_to_neutral({"type": "double_click", "x": 5, "y": 6}) == DoubleClick(5, 6)


def test_scroll_down_from_positive_scroll_y():
    assert openai_action_to_neutral(
        {"type": "scroll", "x": 2, "y": 3, "scroll_x": 0, "scroll_y": 4}
    ) == Scroll(2, 3, "down", 4)


def test_scroll_up_from_negative_scroll_y():
    assert openai_action_to_neutral(
        {"type": "scroll", "x": 2, "y": 3, "scroll_x": 0, "scroll_y": -7}
    ) == Scroll(2, 3, "up", 7)


def test_type_and_keypress():
    assert openai_action_to_neutral({"type": "type", "text": "hi"}) == Type("hi")
    assert openai_action_to_neutral({"type": "keypress", "keys": ["CTRL", "A"]}) == Key("ctrl+a")


def test_wait_and_screenshot_and_move():
    assert openai_action_to_neutral({"type": "wait"}) == Wait(ms=1000)
    assert openai_action_to_neutral({"type": "screenshot"}) == Screenshot()
    assert openai_action_to_neutral({"type": "move", "x": 9, "y": 8}) == Move(9, 8)


def test_drag_uses_path_endpoints():
    assert openai_action_to_neutral(
        {"type": "drag", "path": [{"x": 1, "y": 1}, {"x": 4, "y": 5}]}
    ) == Drag(1, 1, 4, 5)


def test_unknown_raises():
    with pytest.raises(ValueError):
        openai_action_to_neutral({"type": "nope"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_openai_translate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cua.providers.openai_translate'`.

- [ ] **Step 3: Write minimal implementation**

```python
# cua/providers/openai_translate.py
"""Pure translation between OpenAI computer-use actions and neutral Actions."""
from __future__ import annotations

from cua.models import (
    Action, Click, DoubleClick, Drag, Key, Move, Screenshot, Scroll, Type, Wait,
)


def _scroll_dir_amount(sx: int, sy: int) -> tuple[str, int]:
    if sy:
        return ("down" if sy > 0 else "up", abs(sy))
    return ("right" if sx > 0 else "left", abs(sx))


def openai_action_to_neutral(action: dict) -> Action:
    t = action.get("type")
    if t == "click":
        return Click(action["x"], action["y"], action.get("button", "left"))
    if t == "double_click":
        return DoubleClick(action["x"], action["y"])
    if t == "move":
        return Move(action["x"], action["y"])
    if t == "scroll":
        direction, amount = _scroll_dir_amount(action.get("scroll_x", 0), action.get("scroll_y", 0))
        return Scroll(action["x"], action["y"], direction, amount)
    if t == "type":
        return Type(action["text"])
    if t == "keypress":
        return Key("+".join(k.lower() for k in action["keys"]))
    if t == "wait":
        return Wait(ms=1000)
    if t == "screenshot":
        return Screenshot()
    if t == "drag":
        path = action["path"]
        return Drag(path[0]["x"], path[0]["y"], path[-1]["x"], path[-1]["y"])
    raise ValueError(f"Unknown OpenAI computer action: {t!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_openai_translate.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add cua/providers/openai_translate.py tests/test_openai_translate.py
git commit -m "feat: pure OpenAI computer-use action translation"
```

---

### Task 5: OpenAIProvider

**Files:**
- Create: `cua/providers/openai.py`
- Test: `tests/test_openai_provider.py`

**Interfaces:**
- Consumes: `openai_action_to_neutral` (Task 4); `History`/`UserEntry`; `ProviderResponse`.
- Produces: `OpenAIProvider(client, model: str = "computer-use-preview", display_size=(1280, 800), environment: str = "browser")`. Implements `async def next_actions(self, screenshot_b64, history) -> ProviderResponse`. Injected `client` exposes `client.responses.create(...)` returning an object with `.id` and `.output` (list of items; a `computer_call` item has `.type=="computer_call"`, `.call_id`, `.action` (dict), `.pending_safety_checks` (list); a `message`/text item has `.type=="message"` with `.content` items carrying `.text`).

**Behavior:**
- Maintains `self._previous_response_id`, `self._seen_user_count`, `self._pending_call_id`, `self._pending_safety_checks`.
- First call: `input=[{"role":"user","content":[{"type":"input_text","text": <task>}, {"type":"input_image","image_url": "data:image/png;base64,"+screenshot}]}]`; no `previous_response_id`.
- Subsequent call: `input=[{"type":"computer_call_output","call_id": self._pending_call_id, "acknowledged_safety_checks": self._pending_safety_checks, "output": {"type":"computer_screenshot","image_url": "data:image/png;base64,"+screenshot}}]` plus, if new user text, a user message item; pass `previous_response_id=self._previous_response_id`.
- Call `client.responses.create(model=..., tools=[{"type":"computer_use_preview","display_width":w,"display_height":h,"environment":self.environment}], truncation="auto", input=input, previous_response_id=...)`.
- Store `self._previous_response_id = resp.id`. Find first `computer_call` item → translate `.action`; store `self._pending_call_id` and `self._pending_safety_checks = [c for c in item.pending_safety_checks]`. `model_flagged_risky = bool(pending_safety_checks)`. `assistant_text` = concatenated text from any `message` items. `done` = no `computer_call` item present.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_openai_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cua.providers.openai'`.

- [ ] **Step 3: Write minimal implementation**

```python
# cua/providers/openai.py
"""OpenAIProvider — drives OpenAI computer-use-preview to produce neutral actions."""
from __future__ import annotations

from cua.core.history import History, UserEntry
from cua.models import ProviderResponse
from cua.providers.openai_translate import openai_action_to_neutral


def _data_url(screenshot_b64: str) -> str:
    return "data:image/png;base64," + screenshot_b64


def _text_from_output(output) -> str:
    parts: list[str] = []
    for item in output:
        if getattr(item, "type", None) == "message":
            for c in getattr(item, "content", []):
                text = getattr(c, "text", None)
                if text:
                    parts.append(text)
    return " ".join(parts).strip()


class OpenAIProvider:
    def __init__(self, client, model: str = "computer-use-preview",
                 display_size: tuple[int, int] = (1280, 800), environment: str = "browser") -> None:
        self.client = client
        self.model = model
        self.display_size = display_size
        self.environment = environment
        self._previous_response_id: str | None = None
        self._seen_user_count = 0
        self._pending_call_id: str | None = None
        self._pending_safety_checks: list = []

    def _drain_user_text(self, history: History) -> str:
        users = [e.text for e in history.entries() if isinstance(e, UserEntry)]
        new = users[self._seen_user_count:]
        self._seen_user_count = len(users)
        return "\n".join(new)

    def _tool(self) -> dict:
        w, h = self.display_size
        return {"type": "computer_use_preview", "display_width": w, "display_height": h,
                "environment": self.environment}

    async def next_actions(self, screenshot_b64: str, history: History) -> ProviderResponse:
        new_text = self._drain_user_text(history)

        if self._pending_call_id is None:
            content = []
            if new_text:
                content.append({"type": "input_text", "text": new_text})
            content.append({"type": "input_image", "image_url": _data_url(screenshot_b64)})
            input_items: list = [{"role": "user", "content": content}]
        else:
            input_items = [{
                "type": "computer_call_output",
                "call_id": self._pending_call_id,
                "acknowledged_safety_checks": self._pending_safety_checks,
                "output": {"type": "computer_screenshot", "image_url": _data_url(screenshot_b64)},
            }]
            if new_text:
                input_items.append({"role": "user", "content": [{"type": "input_text", "text": new_text}]})

        resp = self.client.responses.create(
            model=self.model,
            tools=[self._tool()],
            truncation="auto",
            input=input_items,
            previous_response_id=self._previous_response_id,
        )
        self._previous_response_id = resp.id

        call = next((i for i in resp.output if getattr(i, "type", None) == "computer_call"), None)
        assistant_text = _text_from_output(resp.output)

        if call is not None:
            self._pending_call_id = call.call_id
            self._pending_safety_checks = list(getattr(call, "pending_safety_checks", []) or [])
            actions = [openai_action_to_neutral(call.action)]
            done = False
            risky = bool(self._pending_safety_checks)
        else:
            actions = []
            done = True
            risky = False

        return ProviderResponse(
            actions=actions, done=done, assistant_text=assistant_text, model_flagged_risky=risky
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_openai_provider.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add cua/providers/openai.py tests/test_openai_provider.py
git commit -m "feat: OpenAIProvider driving computer-use-preview"
```

---

### Task 6: Config + provider factory

**Files:**
- Create: `cua/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `AnthropicProvider`, `OpenAIProvider`.
- Produces: `build_provider(name: str, *, client=None, display_size=(1280, 800)) -> CUAProvider`. `name` in `{"claude", "openai"}` (case-insensitive). When `client` is None, lazily constructs the real SDK client (`anthropic.Anthropic()` / `openai.OpenAI()`), reading keys from env. Raises `ValueError` for unknown names. Tests pass an explicit fake `client` to avoid importing SDKs / needing keys.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest
from cua.config import build_provider
from cua.providers.anthropic import AnthropicProvider
from cua.providers.openai import OpenAIProvider


def test_build_claude_with_injected_client():
    p = build_provider("claude", client=object(), display_size=(800, 600))
    assert isinstance(p, AnthropicProvider)
    assert p.display_size == (800, 600)


def test_build_openai_case_insensitive():
    p = build_provider("OpenAI", client=object())
    assert isinstance(p, OpenAIProvider)


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        build_provider("gemini", client=object())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cua.config'`.

- [ ] **Step 3: Write minimal implementation**

```python
# cua/config.py
"""Provider selection and lazy SDK-client construction."""
from __future__ import annotations

from cua.providers.anthropic import AnthropicProvider
from cua.providers.openai import OpenAIProvider


def build_provider(name: str, *, client=None, display_size: tuple[int, int] = (1280, 800)):
    key = name.strip().lower()
    if key == "claude":
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        return AnthropicProvider(client=client, display_size=display_size)
    if key == "openai":
        if client is None:
            import openai
            client = openai.OpenAI()
        return OpenAIProvider(client=client, display_size=display_size)
    raise ValueError(f"Unknown provider: {name!r} (expected 'claude' or 'openai')")
```

- [ ] **Step 4: Run test to verify it passes + full suite**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (3 passed).

Run: `python -m pytest -v`
Expected: PASS (all Plan 1 + Plan 2 tests green).

- [ ] **Step 5: Commit**

```bash
git add cua/config.py tests/test_config.py
git commit -m "feat: provider factory and config"
```

---

## Self-Review

**Spec coverage (Plan 2 scope = providers):**
- Multi-provider via `CUAProvider` interface → AnthropicProvider (Task 3) + OpenAIProvider (Task 5). ✓
- Neutral Action ↔ vendor translation, exhaustively unit-tested → Tasks 2 & 4. ✓
- `model_flagged_risky` from OpenAI `pending_safety_checks`; Anthropic defaults False with denylist as net → Task 5 / Task 3 + Global Constraints. ✓
- Real-time steering: new `UserEntry`s injected into the native conversation each call → Tasks 3 & 5 (`_drain_user_text`, tested). ✓
- Screenshot round-trip (tool_result image / computer_call_output) → Tasks 3 & 5 (tested). ✓
- DI for testability; no real API calls in tests → all provider/config tests use injected fakes. ✓
- Action vocabulary gap (DoubleClick/TripleClick) → Task 1 (additive, Plan 1 tests preserved). ✓
- Deferred to Plan 3/4: executors, UIs, the live wiring of AgentSession + provider + executor end-to-end.

**Placeholder scan:** No TBD/TODO; every code step is complete; every test asserts concrete behavior. ✓

**Type consistency:** `next_actions(screenshot_b64, history) -> ProviderResponse`, `ProviderResponse(actions, done, assistant_text, model_flagged_risky)`, `display_size` tuple, `claude_action_to_neutral`/`openai_action_to_neutral` names, `build_provider(name, *, client, display_size)` consistent across tasks and with Plan 1. ✓

> Caveat carried into implementation: vendor tool-type strings, beta header, action field names, and Responses-API item shapes must be confirmed against live docs (Global Constraints) — the pure translation modules localize any required change.
