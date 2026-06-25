# tests/test_local_executor.py
import base64

from adaptivecua.executors.local import LocalExecutor, apply_payload
from adaptivecua.models import Click, DoubleClick, Type, Key, Scroll, Drag, Wait, Screenshot


class FakeGui:
    """Records pyautogui-style calls; screenshot returns deterministic PNG bytes."""
    def __init__(self, png=b"PNGBYTES", raise_on=None):
        self.calls = []
        self._png = png
        self._raise_on = raise_on

    def _maybe_raise(self, name):
        if self._raise_on == name:
            raise RuntimeError(f"{name} blew up")

    def moveTo(self, x, y): self.calls.append(("moveTo", x, y))
    def click(self, x=None, y=None, button="left", clicks=1):
        self._maybe_raise("click")
        self.calls.append(("click", x, y, button, clicks))
    def dragTo(self, x, y, button="left"): self.calls.append(("dragTo", x, y, button))
    def typewrite(self, text): self.calls.append(("typewrite", text))
    def hotkey(self, *keys): self.calls.append(("hotkey", keys))
    def scroll(self, amount): self.calls.append(("scroll", amount))
    def hscroll(self, amount): self.calls.append(("hscroll", amount))
    def size(self): return (1920, 1080)
    def screenshot(self): return self._png


def test_apply_payload_click_with_clicks_and_button():
    gui = FakeGui()
    assert apply_payload({"action": "click", "x": 3, "y": 4, "button": "right", "clicks": 2}, gui) == {"ok": True}
    assert gui.calls == [("click", 3, 4, "right", 2)]


def test_apply_payload_hotkey_and_scroll_directions():
    gui = FakeGui()
    apply_payload({"action": "hotkey", "keys": ["ctrl", "a"]}, gui)
    apply_payload({"action": "scroll", "x": 0, "y": 0, "direction": "down", "amount": 3}, gui)
    apply_payload({"action": "scroll", "x": 0, "y": 0, "direction": "left", "amount": 2}, gui)
    assert ("hotkey", ("ctrl", "a")) in gui.calls
    assert ("scroll", -3) in gui.calls       # down -> negative
    assert ("hscroll", -2) in gui.calls      # left -> negative hscroll


def test_apply_payload_screenshot_returns_base64():
    gui = FakeGui(png=b"\x89PNG-data")
    out = apply_payload({"action": "screenshot"}, gui)
    assert out["ok"] is True
    assert base64.b64decode(out["image"]) == b"\x89PNG-data"


def test_apply_payload_unknown_action_is_error_not_raise():
    out = apply_payload({"action": "teleport"}, FakeGui())
    assert out["ok"] is False and "teleport" in out["error"]


def test_apply_payload_gui_exception_becomes_error():
    out = apply_payload({"action": "click", "x": 1, "y": 1}, FakeGui(raise_on="click"))
    assert out["ok"] is False and "blew up" in out["error"]


async def test_do_performs_action_and_returns_screenshot():
    gui = FakeGui(png=b"SHOT")
    ex = LocalExecutor(gui=gui)
    result = await ex.do(Click(10, 20))
    assert ("click", 10, 20, "left", 1) in gui.calls
    assert result.success is True
    assert base64.b64decode(result.screenshot_b64) == b"SHOT"


async def test_do_double_click_translates_to_two_clicks():
    gui = FakeGui()
    ex = LocalExecutor(gui=gui)
    await ex.do(DoubleClick(5, 6))
    assert ("click", 5, 6, "left", 2) in gui.calls


async def test_do_drag_moves_then_drags():
    gui = FakeGui()
    ex = LocalExecutor(gui=gui)
    await ex.do(Drag(1, 2, 9, 8))
    assert ("moveTo", 1, 2) in gui.calls
    assert ("dragTo", 9, 8, "left") in gui.calls


async def test_do_failure_when_gui_raises_yields_failed_step():
    ex = LocalExecutor(gui=FakeGui(raise_on="click"))
    result = await ex.do(Click(1, 1))
    assert result.success is False
    assert "blew up" in (result.error or "")


async def test_do_unknown_action_does_not_raise():
    class Weird:
        pass
    gui = FakeGui()
    ex = LocalExecutor(gui=gui)
    result = await ex.do(Weird())
    assert result.success is False
    assert gui.calls == []  # never dispatched


async def test_screenshot_returns_base64_string():
    ex = LocalExecutor(gui=FakeGui(png=b"abc"))
    shot = await ex.screenshot()
    assert base64.b64decode(shot) == b"abc"


async def test_start_adopts_real_screen_size():
    ex = LocalExecutor(gui=FakeGui(), display_size=(800, 600))
    await ex.start()
    assert ex.display_size == (1920, 1080)  # from gui.size()


def test_local_executor_failsafe_on_by_default():
    """The corner-of-screen emergency abort is the only physical kill switch on an
    unsandboxed real-desktop run, so it must default ON."""
    assert LocalExecutor().failsafe is True
    assert LocalExecutor(failsafe=False).failsafe is False


def test_make_host_gui_sets_pyautogui_failsafe():
    import pyautogui
    from adaptivecua.executors.local import _make_host_gui

    pyautogui.FAILSAFE = False  # force a known-wrong state first
    _make_host_gui()             # default
    assert pyautogui.FAILSAFE is True

    _make_host_gui(failsafe=False)
    assert pyautogui.FAILSAFE is False
    pyautogui.FAILSAFE = True     # restore safe default for any later use
