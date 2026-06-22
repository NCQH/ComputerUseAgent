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
            self._pending_call_id = None
            actions = []
            done = True
            risky = False

        return ProviderResponse(
            actions=actions, done=done, assistant_text=assistant_text, model_flagged_risky=risky
        )
