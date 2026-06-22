import pytest
from cua.providers.anthropic_translate import claude_action_to_neutral, COMPUTER_TOOL
from cua.models import (
    Click, DoubleClick, TripleClick, Move, Drag, Type, Key, Scroll, Screenshot, Wait,
)


def test_left_click():
    assert claude_action_to_neutral({"action": "left_click", "coordinate": [10, 20]}) == Click(10, 20, "left")


def test_right_and_middle_click():
    assert claude_action_to_neutral({"action": "right_click", "coordinate": [1, 2]}) == Click(1, 2, "right")
    assert claude_action_to_neutral({"action": "middle_click", "coordinate": [3, 4]}) == Click(3, 4, "middle")


def test_double_and_triple_click():
    assert claude_action_to_neutral({"action": "double_click", "coordinate": [5, 6]}) == DoubleClick(5, 6)
    assert claude_action_to_neutral({"action": "triple_click", "coordinate": [7, 8]}) == TripleClick(7, 8)


def test_move_and_drag():
    assert claude_action_to_neutral({"action": "mouse_move", "coordinate": [9, 9]}) == Move(9, 9)
    assert claude_action_to_neutral(
        {"action": "left_click_drag", "start_coordinate": [1, 1], "coordinate": [5, 5]}
    ) == Drag(1, 1, 5, 5)


def test_type_and_key():
    assert claude_action_to_neutral({"action": "type", "text": "hello"}) == Type("hello")
    assert claude_action_to_neutral({"action": "key", "text": "ctrl+a"}) == Key("ctrl+a")


def test_scroll():
    assert claude_action_to_neutral(
        {"action": "scroll", "coordinate": [2, 3], "scroll_direction": "down", "scroll_amount": 5}
    ) == Scroll(2, 3, "down", 5)


def test_screenshot_and_wait():
    assert claude_action_to_neutral({"action": "screenshot"}) == Screenshot()
    assert claude_action_to_neutral({"action": "wait", "duration": 2}) == Wait(ms=2000)


def test_unknown_action_raises():
    with pytest.raises(ValueError):
        claude_action_to_neutral({"action": "teleport"})


def test_computer_tool_definition():
    tool = COMPUTER_TOOL(1280, 800)
    assert tool["type"] == "computer_20250124"
    assert tool["name"] == "computer"
    assert tool["display_width_px"] == 1280
    assert tool["display_height_px"] == 800
