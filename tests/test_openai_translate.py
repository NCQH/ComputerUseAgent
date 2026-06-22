import pytest
from cua.providers.openai_translate import openai_action_to_neutral
from cua.models import Click, DoubleClick, Scroll, Type, Key, Wait, Screenshot, Move, Drag


def test_click_defaults_left():
    assert openai_action_to_neutral({"type": "click", "x": 10, "y": 20}) == Click(10, 20, "left")


def test_click_with_button():
    assert openai_action_to_neutral({"type": "click", "x": 1, "y": 2, "button": "right"}) == Click(1, 2, "right")


def test_double_click():
    assert openai_action_to_neutral({"type": "double_click", "x": 5, "y": 6}) == DoubleClick(5, 6)


def test_scroll_down_from_positive_scroll_y():
    assert openai_action_to_neutral(
        {"type": "scroll", "x": 2, "y": 3, "scroll_x": 0, "scroll_y": 4}
    ) == Scroll(2, 3, "down", 4)


def test_scroll_up_from_negative_scroll_y():
    assert openai_action_to_neutral(
        {"type": "scroll", "x": 2, "y": 3, "scroll_x": 0, "scroll_y": -7}
    ) == Scroll(2, 3, "up", 7)


def test_type_and_keypress():
    assert openai_action_to_neutral({"type": "type", "text": "hi"}) == Type("hi")
    assert openai_action_to_neutral({"type": "keypress", "keys": ["CTRL", "A"]}) == Key("ctrl+a")


def test_wait_and_screenshot_and_move():
    assert openai_action_to_neutral({"type": "wait"}) == Wait(ms=1000)
    assert openai_action_to_neutral({"type": "screenshot"}) == Screenshot()
    assert openai_action_to_neutral({"type": "move", "x": 9, "y": 8}) == Move(9, 8)


def test_drag_uses_path_endpoints():
    assert openai_action_to_neutral(
        {"type": "drag", "path": [{"x": 1, "y": 1}, {"x": 4, "y": 5}]}
    ) == Drag(1, 1, 4, 5)


def test_unknown_raises():
    with pytest.raises(ValueError):
        openai_action_to_neutral({"type": "nope"})
