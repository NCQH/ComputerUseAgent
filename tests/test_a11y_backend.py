"""Unit tests for the UIA backend: graceful degrade + record mapping (no real UIA)."""
from adaptivecua.providers.a11y.uia_backend import NullBackend, UiaBackend, _short_type


def test_short_type_strips_control_suffix():
    assert _short_type("ButtonControl") == "button"
    assert _short_type("ListItemControl") == "listitem"
    assert _short_type("") == ""


def test_null_backend_returns_empty():
    assert NullBackend().elements((1280, 800)) == []


def test_uia_backend_degrades_when_lib_absent(monkeypatch):
    """No `uiautomation` importable -> empty list, never raises."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "uiautomation":
            raise ImportError("no uiautomation on this host")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert UiaBackend().elements((1280, 800)) == []


# --- record mapping against a fake `auto` module ----------------------------

class _Rect:
    def __init__(self, left, top, w, h):
        self.left, self.top = left, top
        self._w, self._h = w, h
        self.right, self.bottom = left + w, top + h

    def width(self): return self._w
    def height(self): return self._h


class _Control:
    def __init__(self, type_name, name, rect, children=None):
        self.ControlTypeName = type_name
        self.Name = name
        self.BoundingRectangle = rect
        self._children = children or []

    def GetChildren(self): return self._children


def test_walk_maps_interactive_controls_and_skips_others():
    backend = UiaBackend()
    button = _Control("ButtonControl", "OK", _Rect(10, 20, 100, 30))
    label = _Control("TextControl", "just a label", _Rect(0, 0, 50, 10))  # not interactive
    edit = _Control("EditControl", "Name", _Rect(10, 60, 200, 25))
    root = _Control("WindowControl", "App", _Rect(0, 0, 800, 600),
                    children=[button, label, edit])

    class FakeAuto:
        @staticmethod
        def GetForegroundControl(): return root

    out = backend._walk(FakeAuto, (800, 600))
    assert out == [
        {"x": 10, "y": 20, "width": 100, "height": 30, "tag": "button",
         "role": "", "type": "", "text": "OK"},
        {"x": 10, "y": 60, "width": 200, "height": 25, "tag": "edit",
         "role": "", "type": "", "text": "Name"},
    ]


def test_walk_returns_empty_when_no_foreground_window():
    class FakeAuto:
        @staticmethod
        def GetForegroundControl(): return None

    assert UiaBackend()._walk(FakeAuto, (800, 600)) == []
