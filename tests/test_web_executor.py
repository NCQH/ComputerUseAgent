import base64
from adaptivecua.executors.web import WebExecutor
from adaptivecua.models import Click, Type, Key, Drag, Screenshot


class FakeMouse:
    def __init__(self, calls): self._calls = calls
    async def move(self, x, y): self._calls.append(("move", x, y))
    async def click(self, x, y, button="left", click_count=1):
        self._calls.append(("click", x, y, button, click_count))
    async def down(self, button="left"): self._calls.append(("down", button))
    async def up(self, button="left"): self._calls.append(("up", button))
    async def wheel(self, dx, dy): self._calls.append(("wheel", dx, dy))


class FakeKeyboard:
    def __init__(self, calls): self._calls = calls
    async def type(self, text): self._calls.append(("type", text))
    async def press(self, key): self._calls.append(("press", key))


class FakePage:
    def __init__(self, fail=False):
        self.calls = []
        self.mouse = FakeMouse(self.calls)
        self.keyboard = FakeKeyboard(self.calls)
        self._fail = fail
    async def screenshot(self):
        if self._fail:
            raise RuntimeError("capture failed")
        return b"PNGBYTES"


async def test_click_dispatches_mouse_click_and_returns_screenshot():
    page = FakePage()
    ex = WebExecutor(page)
    result = await ex.do(Click(10, 20))
    assert ("click", 10, 20, "left", 1) in page.calls
    assert result.success is True
    assert result.screenshot_b64 == base64.b64encode(b"PNGBYTES").decode()


async def test_type_and_key_dispatch():
    page = FakePage()
    ex = WebExecutor(page)
    await ex.do(Type("hello"))
    await ex.do(Key("ctrl+a"))
    assert ("type", "hello") in page.calls
    assert ("press", "Control+a") in page.calls


async def test_drag_dispatches_full_sequence_in_order():
    page = FakePage()
    ex = WebExecutor(page)
    await ex.do(Drag(1, 2, 9, 8))
    assert page.calls == [
        ("move", 1, 2), ("down", "left"), ("move", 9, 8), ("up", "left"),
    ]


async def test_screenshot_action_is_noop_but_still_returns_image():
    page = FakePage()
    ex = WebExecutor(page)
    result = await ex.do(Screenshot())
    # no mouse/keyboard calls
    assert page.calls == []
    assert result.success is True


async def test_failure_returns_unsuccessful_step_result():
    page = FakePage(fail=True)
    ex = WebExecutor(page)
    result = await ex.do(Click(1, 1))
    assert result.success is False
    assert "capture failed" in (result.error or "")


async def test_screenshot_returns_base64():
    page = FakePage()
    ex = WebExecutor(page)
    shot = await ex.screenshot()
    assert shot == base64.b64encode(b"PNGBYTES").decode()
