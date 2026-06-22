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
