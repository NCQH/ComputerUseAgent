import pytest
from cua.executors.action_payload import action_to_payload
from cua.models import (
    Click, DoubleClick, TripleClick, Move, Type, Key, Scroll, Drag, Wait, Screenshot,
)


def test_click_payload():
    assert action_to_payload(Click(10, 20, "right")) == {
        "action": "click", "x": 10, "y": 20, "button": "right", "clicks": 1
    }


def test_double_triple_click_counts():
    assert action_to_payload(DoubleClick(1, 1))["clicks"] == 2
    assert action_to_payload(TripleClick(1, 1))["clicks"] == 3


def test_key_splits_into_lowercase_segments():
    assert action_to_payload(Key("Ctrl+A")) == {"action": "hotkey", "keys": ["ctrl", "a"]}


def test_type_move_scroll_drag_wait_screenshot():
    assert action_to_payload(Type("hi")) == {"action": "type", "text": "hi"}
    assert action_to_payload(Move(2, 3)) == {"action": "move", "x": 2, "y": 3}
    assert action_to_payload(Scroll(1, 2, "down", 4)) == {
        "action": "scroll", "x": 1, "y": 2, "direction": "down", "amount": 4
    }
    assert action_to_payload(Drag(1, 2, 3, 4)) == {
        "action": "drag", "x1": 1, "y1": 2, "x2": 3, "y2": 4
    }
    assert action_to_payload(Wait(50)) == {"action": "wait", "ms": 50}
    assert action_to_payload(Screenshot()) == {"action": "screenshot"}


def test_unknown_action_raises():
    class Weird:
        pass
    with pytest.raises(ValueError):
        action_to_payload(Weird())
