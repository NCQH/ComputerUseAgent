import pytest
from cua.providers.vision.actions import ACTION_SCHEMA, parse_action
from cua.models import Click, DoubleClick, Type, Key, Scroll, Move, Drag, Wait, Screenshot

MARKS = {0: (20, 20), 1: (60, 70)}
GRID = {5: (320, 240)}
SIZE = (1280, 800)


def _p(obj):
    return parse_action(obj, marks=MARKS, grid_centers=GRID, display_size=SIZE)


def test_schema_is_json_schema_object():
    assert ACTION_SCHEMA["type"] == "object"
    assert "action" in ACTION_SCHEMA["properties"]


def test_click_via_mark():
    a = _p({"action": "click", "target": {"type": "mark", "id": 1}})
    assert a == Click(60, 70)


def test_click_via_grid_cell():
    a = _p({"action": "click", "target": {"type": "grid", "cell": 5}})
    assert a == Click(320, 240)


def test_click_via_point():
    a = _p({"action": "click", "target": {"type": "point", "x": 11, "y": 22}})
    assert a == Click(11, 22)


def test_type_and_key_need_no_target():
    assert _p({"action": "type", "text": "hi"}) == Type("hi")
    assert _p({"action": "key", "combo": "ctrl+a"}) == Key("ctrl+a")


def test_scroll_and_drag():
    s = _p({"action": "scroll", "target": {"type": "point", "x": 5, "y": 6},
            "direction": "down", "amount": 3})
    assert s == Scroll(5, 6, "down", 3)
    d = _p({"action": "drag", "target": {"type": "point", "x": 1, "y": 2},
            "end_target": {"type": "point", "x": 9, "y": 8}})
    assert d == Drag(1, 2, 9, 8)


def test_wait_screenshot_none():
    assert _p({"action": "wait", "ms": 250}) == Wait(250)
    assert _p({"action": "screenshot"}) == Screenshot()
    assert _p({"action": "none"}) is None


def test_unknown_action_raises():
    with pytest.raises(ValueError):
        _p({"action": "teleport"})


def test_out_of_range_mark_raises():
    with pytest.raises(ValueError):
        _p({"action": "click", "target": {"type": "mark", "id": 99}})
