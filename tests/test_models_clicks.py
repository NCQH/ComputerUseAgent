import pytest
from dataclasses import FrozenInstanceError
from adaptivecua.models import DoubleClick, TripleClick


def test_double_click_defaults_to_left():
    a = DoubleClick(x=3, y=4)
    assert (a.x, a.y, a.button) == (3, 4, "left")


def test_triple_click_holds_button():
    a = TripleClick(x=1, y=2, button="right")
    assert a.button == "right"


def test_clicks_are_frozen():
    with pytest.raises(FrozenInstanceError):
        DoubleClick(1, 2).x = 9  # type: ignore[misc]
