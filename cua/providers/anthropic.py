"""AnthropicProvider — drives Claude computer use to produce neutral actions."""
from __future__ import annotations

import asyncio

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
