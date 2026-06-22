# tests/test_desktop_agent.py
import base64
import sys
import os

# agent.py lives in docker/desktop, not in the cua package — load it by path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "docker", "desktop"))
from agent import perform  # noqa: E402


class FakeGui:
    def __init__(self): self.calls = []
    def moveTo(self, x, y): self.calls.append(("moveTo", x, y))
    def click(self, x=None, y=None, button="left", clicks=1):
        self.calls.append(("click", x, y, button, clicks))
    def dragTo(self, x, y, button="left"): self.calls.append(("dragTo", x, y, button))
    def typewrite(self, text): self.calls.append(("typewrite", text))
    def hotkey(self, *keys): self.calls.append(("hotkey", keys))
    def scroll(self, amount): self.calls.append(("scroll", amount))
    def hscroll(self, amount): self.calls.append(("hscroll", amount))
    def screenshot(self): return b"PNGBYTES"


def test_click_dispatch():
    gui = FakeGui()
    out = perform({"action": "click", "x": 5, "y": 6, "button": "left", "clicks": 2}, gui)
    assert out == {"ok": True}
    assert ("click", 5, 6, "left", 2) in gui.calls


def test_drag_moves_then_drags():
    gui = FakeGui()
    perform({"action": "drag", "x1": 1, "y1": 2, "x2": 9, "y2": 8}, gui)
    assert gui.calls == [("moveTo", 1, 2), ("dragTo", 9, 8, "left")]


def test_hotkey_and_type():
    gui = FakeGui()
    perform({"action": "hotkey", "keys": ["ctrl", "a"]}, gui)
    perform({"action": "type", "text": "hi"}, gui)
    assert ("hotkey", ("ctrl", "a")) in gui.calls
    assert ("typewrite", "hi") in gui.calls


def test_scroll_directions():
    gui = FakeGui()
    perform({"action": "scroll", "x": 0, "y": 0, "direction": "down", "amount": 3}, gui)
    perform({"action": "scroll", "x": 0, "y": 0, "direction": "right", "amount": 2}, gui)
    assert ("scroll", -3) in gui.calls
    assert ("hscroll", 2) in gui.calls


def test_screenshot_returns_base64_image():
    gui = FakeGui()
    out = perform({"action": "screenshot"}, gui)
    assert out["ok"] is True
    assert out["image"] == base64.b64encode(b"PNGBYTES").decode()


def test_unknown_action_returns_error_not_raise():
    gui = FakeGui()
    out = perform({"action": "nope"}, gui)
    assert out["ok"] is False
    assert "error" in out
