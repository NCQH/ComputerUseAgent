# cua/providers/vision/provider.py
"""GenericVisionProvider: drive any vision+chat model as a computer-use agent."""
from __future__ import annotations

import json

from cua.core.history import ActionEntry, ErrorEntry, History, UserEntry
from cua.models import ProviderResponse
from cua.providers.vision import actions as _actions
from cua.providers.vision import imaging as _imaging
from cua.providers.vision import ocr as _ocr

_SYSTEM = (
    "You control a computer by looking at a screenshot and choosing ONE action. "
    "Interactive elements are boxed and numbered (marks); a labelled coordinate grid "
    "is also overlaid. Prefer referencing a mark id, else a grid cell, else a point. "
    "First verify whether your previous action (see history) had the intended effect; "
    "if it did not, correct course. Reply ONLY with the JSON action object."
)


class GenericVisionProvider:
    def __init__(self, client, model: str = "gpt-5.4-mini",
                 display_size: tuple[int, int] = (1280, 800), ocr=None,
                 use_marks: bool = True, use_grid: bool = True,
                 grid_cols: int = 12, grid_rows: int = 8, zoom: bool = True) -> None:
        self.client = client
        self.model = model
        self.display_size = display_size
        self.ocr = ocr
        self.use_marks = use_marks
        self.use_grid = use_grid
        self.grid_cols = grid_cols
        self.grid_rows = grid_rows
        self.zoom = zoom

    def _summarize_history(self, history: History) -> str:
        lines = []
        for entry in history.entries()[-3:]:
            if isinstance(entry, UserEntry):
                lines.append(f"user: {entry.text}")
            elif isinstance(entry, ActionEntry):
                ok = "ok" if entry.result.success else f"FAIL: {entry.result.error}"
                lines.append(f"did {type(entry.action).__name__} -> {ok}")
            elif isinstance(entry, ErrorEntry):
                lines.append(f"error: {entry.message}")
        return "\n".join(lines) if lines else "(no prior steps)"

    def _annotate(self, screenshot_b64: str):
        img = _imaging.decode(screenshot_b64)
        marks: dict[int, tuple[int, int]] = {}
        grid: dict[int, tuple[int, int]] = {}
        if self.use_marks:
            boxes = _ocr.detect_text_boxes(img, ocr=self.ocr)
            img, marks = _imaging.annotate_marks(img, boxes)
        if self.use_grid:
            img, grid = _imaging.overlay_grid(img, self.grid_cols, self.grid_rows)
        return _imaging.encode(img), marks, grid

    def _call(self, annotated_b64: str, history_text: str):
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": f"History:\n{history_text}\nChoose the next action."},
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
        annotated_b64, marks, grid = self._annotate(screenshot_b64)
        try:
            content = self._call(annotated_b64, self._summarize_history(history))
            obj = json.loads(content)
        except Exception as exc:  # noqa: BLE001 — surfaced, never raised
            return ProviderResponse([], done=False, assistant_text=f"parse error: {exc}",
                                    model_flagged_risky=False)
        try:
            action = _actions.parse_action(
                obj, marks=marks, grid_centers=grid, display_size=self.display_size)
        except ValueError as exc:
            return ProviderResponse([], done=False, assistant_text=f"bad action: {exc}",
                                    model_flagged_risky=False)
        return ProviderResponse(
            [action] if action is not None else [],
            done=bool(obj.get("done", False)),
            assistant_text=obj.get("reasoning", ""),
            model_flagged_risky=False,
        )
