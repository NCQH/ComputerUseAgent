"""Pure translation: neutral Action -> flat dict payload consumed by LocalExecutor."""
from __future__ import annotations

from cua.models import (
    Action, Click, DoubleClick, TripleClick, Move, Type, Key, Scroll, Drag, Wait, Screenshot,
)


def action_to_payload(action: Action) -> dict:
    if isinstance(action, TripleClick):
        return {"action": "click", "x": action.x, "y": action.y, "button": action.button, "clicks": 3}
    if isinstance(action, DoubleClick):
        return {"action": "click", "x": action.x, "y": action.y, "button": action.button, "clicks": 2}
    if isinstance(action, Click):
        return {"action": "click", "x": action.x, "y": action.y, "button": action.button, "clicks": 1}
    if isinstance(action, Move):
        return {"action": "move", "x": action.x, "y": action.y}
    if isinstance(action, Type):
        return {"action": "type", "text": action.text}
    if isinstance(action, Key):
        return {"action": "hotkey", "keys": [s.strip().lower() for s in action.combo.split("+")]}
    if isinstance(action, Scroll):
        return {"action": "scroll", "x": action.x, "y": action.y, "direction": action.direction, "amount": action.amount}
    if isinstance(action, Drag):
        return {"action": "drag", "x1": action.x1, "y1": action.y1, "x2": action.x2, "y2": action.y2}
    if isinstance(action, Wait):
        return {"action": "wait", "ms": action.ms}
    if isinstance(action, Screenshot):
        return {"action": "screenshot"}
    raise ValueError(f"unknown action for desktop executor: {action!r}")
