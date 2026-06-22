# tests/test_desktop_executor.py
from cua.executors.desktop import DesktopExecutor
from cua.models import Click, Type


class FakeResp:
    def __init__(self, data): self._data = data
    def json(self): return self._data


class FakeClient:
    def __init__(self, do_data=None, shot_data=None, raise_on_post=False):
        self.posts = []
        self.gets = []
        self._do_data = do_data or {"ok": True}
        self._shot_data = shot_data or {"ok": True, "image": "SHOT64"}
        self._raise_on_post = raise_on_post
    async def post(self, url, json=None):
        if self._raise_on_post:
            raise RuntimeError("connection refused")
        self.posts.append((url, json))
        return FakeResp(self._do_data)
    async def get(self, url):
        self.gets.append(url)
        return FakeResp(self._shot_data)


async def test_do_posts_translated_payload_and_returns_screenshot():
    client = FakeClient()
    ex = DesktopExecutor(client, base_url="http://host:8000")
    result = await ex.do(Click(3, 4))
    assert client.posts == [("http://host:8000/do",
                             {"action": "click", "x": 3, "y": 4, "button": "left", "clicks": 1})]
    assert result.success is True
    assert result.screenshot_b64 == "SHOT64"


async def test_agent_error_response_yields_failed_step():
    client = FakeClient(do_data={"ok": False, "error": "pyautogui blew up"})
    ex = DesktopExecutor(client)
    result = await ex.do(Type("x"))
    assert result.success is False
    assert "pyautogui blew up" in (result.error or "")


async def test_transport_exception_yields_failed_step():
    client = FakeClient(raise_on_post=True)
    ex = DesktopExecutor(client)
    result = await ex.do(Click(1, 1))
    assert result.success is False
    assert "connection refused" in (result.error or "")


async def test_screenshot_returns_image_field():
    client = FakeClient(shot_data={"ok": True, "image": "ABC123"})
    ex = DesktopExecutor(client)
    shot = await ex.screenshot()
    assert shot == "ABC123"


async def test_unknown_action_yields_failed_step_not_raise():
    # action_to_payload rejects an unknown action type; do() must not raise.
    class Weird:
        pass
    client = FakeClient()
    ex = DesktopExecutor(client)
    result = await ex.do(Weird())
    assert result.success is False
    assert (result.error or "") != ""
    assert client.posts == []  # never reached the POST
