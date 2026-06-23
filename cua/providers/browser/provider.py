"""DomVisionProvider: browser_use-style DOM Set-of-Marks over any vision chat model.

Reads the page's interactive elements from the DOM (via dom_marks.INTERACTIVE_JS),
numbers them, overlays Set-of-Marks boxes on the screenshot, and gives the model
both the annotated image and the numbered element list. The model picks an element
by mark id — more reliable than guessing pixels. Falls back to grid/point targeting
when the DOM gives nothing (or the needed element isn't listed). Reuses the vision
package's image annotation, action schema, and parser.
"""
from __future__ import annotations

import asyncio
import json

from cua.core.history import History
from cua.models import ProviderResponse
from cua.providers.browser.dom_marks import (
    INTERACTIVE_JS, boxes_of, describe, parse_elements,
)
from cua.providers.vision import actions as _actions
from cua.providers.vision import imaging as _imaging
from cua.providers.vision.provider import _targeting_hint, summarize_history

_SYSTEM = (
    "You control a web browser by looking at a screenshot annotated with numbered "
    "boxes over the page's interactive elements, plus a list of those elements. "
    "Prefer targeting by mark id: set `target` to {\"type\":\"mark\",\"id\":N} using "
    "an [N] from the list. Use {\"type\":\"grid\",\"cell\":N} or "
    "{\"type\":\"point\",\"x\":X,\"y\":Y} ONLY when the element you need is not listed. "
    "Never invent a mark id that is not shown. First verify whether your previous "
    "action (see history) had the intended effect; if not, correct course. "
    "Reply ONLY with the JSON action object."
)


class DomVisionProvider:
    def __init__(self, client, page, model: str = "gpt-5.4-mini",
                 display_size: tuple[int, int] = (1280, 800), use_grid: bool = True,
                 grid_cols: int = 12, grid_rows: int = 8) -> None:
        self.client = client
        self.page = page
        self.model = model
        self.display_size = display_size
        self.use_grid = use_grid
        self.grid_cols = grid_cols
        self.grid_rows = grid_rows

    async def _elements(self):
        try:
            raw = await self.page.evaluate(INTERACTIVE_JS)
        except Exception:  # noqa: BLE001 — degrade to grid/point, never fail the step
            return []
        return parse_elements(raw or [], self.display_size)

    def _annotate(self, screenshot_b64: str, elements):
        img = _imaging.decode(screenshot_b64)
        img, marks = _imaging.annotate_marks(img, boxes_of(elements))
        grid: dict = {}
        if self.use_grid:
            img, grid = _imaging.overlay_grid(img, self.grid_cols, self.grid_rows)
        return _imaging.encode(img), marks, grid

    def _call(self, annotated_b64: str, element_list: str, history_text: str, targeting: str):
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": [
                {"type": "text",
                 "text": f"{targeting}\n{element_list}\nHistory:\n{history_text}\n"
                         "Choose the next action."},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{annotated_b64}"}},
            ]},
        ]
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": {
                "name": "action", "schema": _actions.ACTION_SCHEMA, "strict": True}},
        )
        return resp.choices[0].message.content

    async def next_actions(self, screenshot_b64: str, history: History) -> ProviderResponse:
        elements = await self._elements()
        try:
            annotated_b64, marks, grid = self._annotate(screenshot_b64, elements)
        except Exception as exc:  # noqa: BLE001 — surfaced, never raised
            return ProviderResponse([], done=False, assistant_text=f"screenshot error: {exc}",
                                    model_flagged_risky=False)
        try:
            content = await asyncio.to_thread(
                self._call, annotated_b64, describe(elements),
                summarize_history(history), _targeting_hint(marks, grid))
            obj = json.loads(content)
        except Exception as exc:  # noqa: BLE001 — surfaced, never raised
            return ProviderResponse([], done=False, assistant_text=f"parse error: {exc}",
                                    model_flagged_risky=False)
        try:
            action = _actions.parse_action(
                obj, marks=marks, grid_centers=grid, display_size=self.display_size)
        except (ValueError, KeyError, TypeError) as exc:
            return ProviderResponse([], done=False, assistant_text=f"bad action: {exc}",
                                    model_flagged_risky=False)
        return ProviderResponse(
            [action] if action is not None else [],
            done=bool(obj.get("done", False)),
            assistant_text=obj.get("reasoning", "") or "",
            model_flagged_risky=False,
        )
