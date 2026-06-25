"""Pure translation between Claude computer_20250124 actions and neutral Actions."""
from __future__ import annotations

from adaptivecua.models import (
    Action, Click, DoubleClick, TripleClick, Drag, Key, Move, Screenshot, Scroll, Type, Wait,
)

_CLICK_BUTTON = {"left_click": "left", "right_click": "right", "middle_click": "middle"}


def COMPUTER_TOOL(width: int, height: int) -> dict:
    return {
        "type": "computer_20250124",
        "name": "computer",
        "display_width_px": width,
        "display_height_px": height,
        "display_number": 1,
    }


def claude_action_to_neutral(input_dict: dict) -> Action:
    action = input_dict.get("action")
    coord = input_dict.get("coordinate")

    if action in _CLICK_BUTTON:
        return Click(coord[0], coord[1], _CLICK_BUTTON[action])
    if action == "double_click":
        return DoubleClick(coord[0], coord[1])
    if action == "triple_click":
        return TripleClick(coord[0], coord[1])
    if action == "mouse_move":
        return Move(coord[0], coord[1])
    if action == "left_click_drag":
        start = input_dict["start_coordinate"]
        return Drag(start[0], start[1], coord[0], coord[1])
    if action == "type":
        return Type(input_dict["text"])
    if action == "key":
        return Key(input_dict["text"])
    if action == "scroll":
        return Scroll(coord[0], coord[1], input_dict["scroll_direction"], input_dict["scroll_amount"])
    if action == "screenshot":
        return Screenshot()
    if action == "wait":
        return Wait(ms=int(float(input_dict.get("duration", 1)) * 1000))
    raise ValueError(f"Unknown Claude computer action: {action!r}")
