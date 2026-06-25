import pytest
from adaptivecua.executors.web_translate import WebOp, action_to_web_ops, normalize_key, _WHEEL_STEP
from adaptivecua.models import (
    Click, DoubleClick, TripleClick, Move, Type, Key, Scroll, Drag, Wait, Screenshot,
)


def test_click_maps_to_single_mouse_click():
    assert action_to_web_ops(Click(10, 20)) == [
        WebOp("mouse_click", {"x": 10, "y": 20, "button": "left", "clicks": 1})
    ]


def test_double_and_triple_click_set_click_count():
    assert action_to_web_ops(DoubleClick(1, 2))[0].args["clicks"] == 2
    assert action_to_web_ops(TripleClick(1, 2))[0].args["clicks"] == 3


def test_type_and_move():
    assert action_to_web_ops(Type("hi")) == [WebOp("keyboard_type", {"text": "hi"})]
    assert action_to_web_ops(Move(3, 4)) == [WebOp("mouse_move", {"x": 3, "y": 4})]


def test_key_is_normalized_to_playwright_format():
    assert action_to_web_ops(Key("ctrl+a")) == [WebOp("keyboard_press", {"key": "Control+a"})]
    assert normalize_key("ctrl+shift+enter") == "Control+Shift+Enter"
    assert normalize_key("escape") == "Escape"


def test_scroll_down_uses_positive_dy():
    ops = action_to_web_ops(Scroll(5, 6, "down", 3))
    assert ops[0] == WebOp("mouse_move", {"x": 5, "y": 6})
    assert ops[1] == WebOp("mouse_wheel", {"dx": 0, "dy": 3 * _WHEEL_STEP})


def test_scroll_left_uses_negative_dx():
    ops = action_to_web_ops(Scroll(0, 0, "left", 2))
    assert ops[1] == WebOp("mouse_wheel", {"dx": -2 * _WHEEL_STEP, "dy": 0})


def test_drag_expands_to_move_down_move_up():
    ops = action_to_web_ops(Drag(1, 2, 9, 8))
    assert ops == [
        WebOp("mouse_move", {"x": 1, "y": 2}),
        WebOp("mouse_down", {"button": "left"}),
        WebOp("mouse_move", {"x": 9, "y": 8}),
        WebOp("mouse_up", {"button": "left"}),
    ]


def test_wait_and_screenshot():
    assert action_to_web_ops(Wait(250)) == [WebOp("wait", {"ms": 250})]
    assert action_to_web_ops(Screenshot()) == []


def test_unknown_action_raises():
    class Weird:
        pass
    with pytest.raises(ValueError):
        action_to_web_ops(Weird())
