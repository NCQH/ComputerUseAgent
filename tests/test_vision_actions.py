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


def _objects(schema):
    """Yield every object-typed (sub)schema, recursing into properties."""
    t = schema.get("type")
    if t == "object" or (isinstance(t, list) and "object" in t):
        yield schema
        for sub in schema.get("properties", {}).values():
            yield from _objects(sub)


def test_schema_is_openai_strict_compliant():
    """OpenAI strict mode requires every object's `required` to list EVERY key in
    `properties` and `additionalProperties` to be False. The 400 we hit came from
    `target` only requiring `type`."""
    for obj in _objects(ACTION_SCHEMA):
        assert obj.get("additionalProperties") is False
        assert set(obj["required"]) == set(obj["properties"]), obj["properties"].keys()


def test_parses_strict_shape_with_null_unused_fields():
    """Strict mode returns ALL keys, nulling the unused ones; the parser must
    treat null like absent and not crash or pass None into actions."""
    click = _p({"reasoning": "go", "done": False, "action": "click",
                "target": {"type": "point", "id": None, "cell": None, "x": 11, "y": 22},
                "end_target": None, "text": None, "combo": None,
                "direction": None, "amount": None, "ms": None})
    assert click == Click(11, 22)

    typ = _p({"reasoning": None, "done": False, "action": "type",
              "target": None, "end_target": None, "text": "hello", "combo": None,
              "direction": None, "amount": None, "ms": None})
    assert typ == Type("hello")

    scroll = _p({"action": "scroll", "target": {"type": "point", "x": 5, "y": 6},
                 "direction": None, "amount": None})  # nulls -> sane defaults
    assert scroll == Scroll(5, 6, "down", 3)

    wait = _p({"action": "wait", "ms": None})
    assert wait == Wait(1000)
