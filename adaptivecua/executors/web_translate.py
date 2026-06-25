"""Pure translation: neutral Action -> list of Playwright operation descriptors."""
from __future__ import annotations

from dataclasses import dataclass

from adaptivecua.models import (
    Action, Click, DoubleClick, TripleClick, Move, Type, Key, Scroll, Drag, Wait, Screenshot,
)

_WHEEL_STEP = 100

_MODS = {
    "ctrl": "Control", "control": "Control", "shift": "Shift", "alt": "Alt",
    "option": "Alt", "meta": "Meta", "cmd": "Meta", "command": "Meta",
    "super": "Meta", "win": "Meta",
}
_KEYS = {
    "enter": "Enter", "return": "Enter", "tab": "Tab", "esc": "Escape",
    "escape": "Escape", "space": "Space", "backspace": "Backspace",
    "delete": "Delete", "del": "Delete", "up": "ArrowUp", "down": "ArrowDown",
    "left": "ArrowLeft", "right": "ArrowRight", "home": "Home", "end": "End",
    "pageup": "PageUp", "pagedown": "PageDown",
}


@dataclass(frozen=True)
class WebOp:
    name: str
    args: dict


def normalize_key(combo: str) -> str:
    parts = []
    for seg in combo.split("+"):
        s = seg.strip().lower()
        if s in _MODS:
            parts.append(_MODS[s])
        elif s in _KEYS:
            parts.append(_KEYS[s])
        elif len(s) == 1:
            parts.append(s)
        else:
            parts.append(s.capitalize())
    return "+".join(parts)


def _scroll_delta(direction: str, amount: int) -> tuple[int, int]:
    step = amount * _WHEEL_STEP
    if direction == "down":
        return 0, step
    if direction == "up":
        return 0, -step
    if direction == "right":
        return step, 0
    if direction == "left":
        return -step, 0
    raise ValueError(f"unknown scroll direction: {direction}")


def action_to_web_ops(action: Action) -> list[WebOp]:
    if isinstance(action, TripleClick):
        return [WebOp("mouse_click", {"x": action.x, "y": action.y, "button": action.button, "clicks": 3})]
    if isinstance(action, DoubleClick):
        return [WebOp("mouse_click", {"x": action.x, "y": action.y, "button": action.button, "clicks": 2})]
    if isinstance(action, Click):
        return [WebOp("mouse_click", {"x": action.x, "y": action.y, "button": action.button, "clicks": 1})]
    if isinstance(action, Move):
        return [WebOp("mouse_move", {"x": action.x, "y": action.y})]
    if isinstance(action, Type):
        return [WebOp("keyboard_type", {"text": action.text})]
    if isinstance(action, Key):
        return [WebOp("keyboard_press", {"key": normalize_key(action.combo)})]
    if isinstance(action, Scroll):
        dx, dy = _scroll_delta(action.direction, action.amount)
        return [
            WebOp("mouse_move", {"x": action.x, "y": action.y}),
            WebOp("mouse_wheel", {"dx": dx, "dy": dy}),
        ]
    if isinstance(action, Drag):
        return [
            WebOp("mouse_move", {"x": action.x1, "y": action.y1}),
            WebOp("mouse_down", {"button": "left"}),
            WebOp("mouse_move", {"x": action.x2, "y": action.y2}),
            WebOp("mouse_up", {"button": "left"}),
        ]
    if isinstance(action, Wait):
        return [WebOp("wait", {"ms": action.ms})]
    if isinstance(action, Screenshot):
        return []
    raise ValueError(f"unknown action for web executor: {action!r}")
