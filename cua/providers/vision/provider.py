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
    "To point at something set `target`: {\"type\":\"mark\",\"id\":N} for a visible "
    "numbered box, {\"type\":\"grid\",\"cell\":N} for a numbered grid cell, or "
    "{\"type\":\"point\",\"x\":X,\"y\":Y} for raw pixels. Use ONLY targeting aids "
    "listed as available below — never invent a mark id that is not shown. "
    "First verify whether your previous action (see history) had the intended effect; "
    "if it did not, correct course. Reply ONLY with the JSON action object."
)


def _targeting_hint(marks: dict, grid: dict) -> str:
    """Describe exactly which targeting aids are present this step, so the model
    does not hallucinate mark ids when OCR/marks are unavailable."""
    parts = []
    if marks:
        ids = sorted(marks)
        parts.append(f"marks available: ids {ids[0]}..{ids[-1]}")
    else:
        parts.append("NO marks available - do not use target type 'mark'")
    if grid:
        parts.append(f"grid available: cells 0..{max(grid)}")
    else:
        parts.append("no grid")
    parts.append("point (pixel x,y) always available")
    return "Targeting aids — " + "; ".join(parts) + "."


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
        self._ocr_unavailable = False

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
        if self.use_marks and not self._ocr_unavailable:
            try:
                boxes = _ocr.detect_text_boxes(img, ocr=self.ocr)
                img, marks = _imaging.annotate_marks(img, boxes)
            except Exception:  # noqa: BLE001
                # OCR backend unavailable (e.g. tesseract binary not on PATH).
                # Degrade to grid/point targeting instead of failing the step,
                # and stop retrying OCR on every subsequent screenshot.
                self._ocr_unavailable = True
                marks = {}
        if self.use_grid:
            img, grid = _imaging.overlay_grid(img, self.grid_cols, self.grid_rows)
        return _imaging.encode(img), marks, grid

    def _call(self, annotated_b64: str, history_text: str, targeting: str):
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": [
                {"type": "text",
                 "text": f"{targeting}\nHistory:\n{history_text}\nChoose the next action."},
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
        try:
            annotated_b64, marks, grid = self._annotate(screenshot_b64)
        except Exception as exc:  # noqa: BLE001 — surfaced, never raised
            return ProviderResponse([], done=False, assistant_text=f"screenshot error: {exc}",
                                    model_flagged_risky=False)
        try:
            content = self._call(annotated_b64, self._summarize_history(history),
                                  _targeting_hint(marks, grid))
            obj = json.loads(content)
        except Exception as exc:  # noqa: BLE001 — surfaced, never raised
            return ProviderResponse([], done=False, assistant_text=f"parse error: {exc}",
                                    model_flagged_risky=False)
        try:
            action = _actions.parse_action(
                obj, marks=marks, grid_centers=grid, display_size=self.display_size)
        except (ValueError, KeyError, TypeError) as exc:
            # KeyError/TypeError can arise from a malformed target (e.g. a "point"
            # missing x/y) that slipped past the schema — still never raise.
            return ProviderResponse([], done=False, assistant_text=f"bad action: {exc}",
                                    model_flagged_risky=False)
        return ProviderResponse(
            [action] if action is not None else [],
            done=bool(obj.get("done", False)),
            assistant_text=obj.get("reasoning", ""),
            model_flagged_risky=False,
        )
