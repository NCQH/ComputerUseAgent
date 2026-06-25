"""AnthropicProvider — drives Claude computer use to produce neutral actions."""
from __future__ import annotations

import asyncio

from adaptivecua.core.history import History, UserEntry
from adaptivecua.models import ProviderResponse
from adaptivecua.providers.anthropic_translate import COMPUTER_TOOL, claude_action_to_neutral

IMAGE_PLACEHOLDER_TEXT = "[older screenshot omitted to save context]"

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


def _strip_images(msg: dict) -> dict:
    """Return a copy of a user message with image blocks swapped for a text
    placeholder, including images nested inside tool_result content."""
    placeholder = {"type": "text", "text": IMAGE_PLACEHOLDER_TEXT}
    new_content: list[dict] = []
    for b in msg["content"]:
        if b.get("type") == "image":
            new_content.append(dict(placeholder))
        elif b.get("type") == "tool_result":
            inner = [dict(placeholder) if c.get("type") == "image" else c
                     for c in b.get("content", [])]
            new_block = dict(b)
            new_block["content"] = inner
            new_content.append(new_block)
        else:
            new_content.append(b)
    new_msg = dict(msg)
    new_msg["content"] = new_content
    return new_msg


def _blocks_to_dicts(content) -> list[dict]:
    out: list[dict] = []
    for b in content:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        elif b.type == "thinking":
            out.append({
                "type": "thinking",
                "thinking": getattr(b, "thinking", None),
                "signature": getattr(b, "signature", None),
            })
        elif b.type == "redacted_thinking":
            out.append({"type": "redacted_thinking", "data": getattr(b, "data", None)})
    return out


class AnthropicProvider:
    def __init__(self, client, model: str = "claude-opus-4-8",
                 display_size: tuple[int, int] = (1280, 800), system: str = DEFAULT_SYSTEM,
                 image_retention: int | None = 3) -> None:
        self.client = client
        self.model = model
        self.display_size = display_size
        self.system = system
        # Old screenshots dominate token cost. Keep images only for the last
        # `image_retention` user turns; older ones become a text placeholder so the
        # context stops growing without breaking tool_use/tool_result pairing.
        # None disables pruning.
        self.image_retention = image_retention
        self._messages: list[dict] = []
        self._seen_user_count = 0
        self._pending_tool_use_id: str | None = None

    def _prune_old_images(self) -> None:
        """Replace image blocks in all but the most recent `image_retention` user
        turns with a text placeholder. Pairing (tool_use_id) is preserved."""
        if self.image_retention is None:
            return
        user_idxs = [i for i, m in enumerate(self._messages) if m["role"] == "user"]
        keep = set(user_idxs[-self.image_retention:])
        for i in user_idxs:
            if i not in keep:
                self._messages[i] = _strip_images(self._messages[i])

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

        self._prune_old_images()

        w, h = self.display_size
        # Off the event loop: the SDK call is synchronous and can stall on a slow
        # network; running it inline would freeze the UI and block Stop/Ctrl-C.
        resp = await asyncio.to_thread(
            lambda: self.client.beta.messages.create(
                model=self.model,
                max_tokens=4096,
                thinking={"type": "adaptive"},
                tools=[COMPUTER_TOOL(w, h)],
                betas=[BETA],
                system=self.system,
                messages=list(self._messages),
            )
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
            self._pending_tool_use_id = None
            actions = []
            done = resp.stop_reason == "end_turn"

        return ProviderResponse(
            actions=actions, done=done, assistant_text=assistant_text, model_flagged_risky=False
        )
