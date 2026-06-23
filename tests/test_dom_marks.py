"""Unit tests for DOM interactive-element extraction (browser_use Set-of-Marks)."""
from __future__ import annotations

from cua.providers.browser.dom_marks import (
    Element, boxes_of, describe, parse_elements,
)


def _raw(**kw):
    base = {"x": 0, "y": 0, "width": 10, "height": 10, "tag": "button",
            "role": "", "type": "", "text": ""}
    base.update(kw)
    return base


def test_parse_elements_assigns_sequential_indices_and_boxes():
    raw = [
        _raw(x=10, y=20, width=100, height=30, tag="button", text="Submit"),
        _raw(x=0, y=0, width=0, height=0, tag="div", text="skip"),       # zero-size dropped
        _raw(x=5, y=5, width=50, height=20, tag="input", type="text", text="Search"),
    ]
    els = parse_elements(raw, display_size=(800, 600))
    assert [e.index for e in els] == [0, 1]
    assert (els[0].x0, els[0].y0, els[0].x1, els[0].y1) == (10, 20, 110, 50)
    assert els[0].tag == "button" and els[0].text == "Submit"
    assert els[1].tag == "input" and els[1].type == "text"


def test_boxes_of_matches_element_order():
    els = parse_elements([
        _raw(x=10, y=20, width=100, height=30, text="a"),
        _raw(x=5, y=5, width=50, height=20, text="b"),
    ], display_size=(800, 600))
    assert boxes_of(els) == [(10, 20, 110, 50), (5, 5, 55, 25)]


def test_describe_lists_indexed_labels_with_tag_and_text():
    els = parse_elements([
        _raw(tag="button", text="Submit"),
        _raw(tag="input", type="text", text="Search"),
    ], display_size=(800, 600))
    text = describe(els)
    assert "[0]" in text and "button" in text and "Submit" in text
    assert "[1]" in text and "input" in text and "Search" in text


def test_parse_elements_clamps_box_to_display():
    els = parse_elements([_raw(x=790, y=10, width=100, height=20, text="edge")],
                         display_size=(800, 600))
    assert els[0].x1 == 800


def test_parse_elements_caps_count():
    raw = [_raw(x=i, y=0, width=5, height=5, tag="a", text=f"L{i}") for i in range(100)]
    els = parse_elements(raw, display_size=(800, 600), max_elements=10)
    assert len(els) == 10


def test_describe_empty_is_explicit():
    assert "no interactive" in describe([]).lower()
