"""Structured-output schema + parser: model reply -> neutral Action."""
from __future__ import annotations

from cua.models import (
    Action, Click, DoubleClick, Type, Key, Scroll, Move, Drag, Wait, Screenshot,
)

_TARGET_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["mark", "grid", "point"]},
        "id": {"type": "integer"},
        "cell": {"type": "integer"},
        "x": {"type": "integer"},
        "y": {"type": "integer"},
    },
    "required": ["type"],
    "additionalProperties": False,
}

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "done": {"type": "boolean"},
        "action": {
            "type": "string",
            "enum": ["click", "double_click", "type", "key", "scroll",
                     "move", "drag", "wait", "screenshot", "none"],
        },
        "target": _TARGET_SCHEMA,
        "end_target": _TARGET_SCHEMA,
        "text": {"type": "string"},
        "combo": {"type": "string"},
        "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
        "amount": {"type": "integer"},
        "ms": {"type": "integer"},
    },
    "required": ["action"],
    "additionalProperties": False,
}


def _resolve(target, marks, grid_centers):
    if not target:
        return None
    kind = target.get("type")
    if kind == "mark":
        i = target.get("id")
        if i not in marks:
            raise ValueError(f"mark id out of range: {i}")
        return marks[i]
    if kind == "grid":
        c = target.get("cell")
        if c not in grid_centers:
            raise ValueError(f"grid cell out of range: {c}")
        return grid_centers[c]
    if kind == "point":
        return int(target["x"]), int(target["y"])
    raise ValueError(f"unknown target type: {kind}")


def parse_action(obj, *, marks, grid_centers, display_size) -> Action | None:
    action = obj.get("action")
    if action == "none":
        return None
    if action == "screenshot":
        return Screenshot()
    if action == "wait":
        return Wait(ms=int(obj.get("ms", 1000)))
    if action == "type":
        return Type(text=obj.get("text", ""))
    if action == "key":
        return Key(combo=obj.get("combo", ""))

    point = _resolve(obj.get("target"), marks, grid_centers)
    if action == "click":
        if point is None:
            return None
        return Click(point[0], point[1])
    if action == "double_click":
        if point is None:
            return None
        return DoubleClick(point[0], point[1])
    if action == "move":
        if point is None:
            return None
        return Move(point[0], point[1])
    if action == "scroll":
        if point is None:
            return None
        return Scroll(point[0], point[1], obj.get("direction", "down"), int(obj.get("amount", 3)))
    if action == "drag":
        end = _resolve(obj.get("end_target"), marks, grid_centers)
        if point is None or end is None:
            return None
        return Drag(point[0], point[1], end[0], end[1])
    raise ValueError(f"unknown action: {action}")
