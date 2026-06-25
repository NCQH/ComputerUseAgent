"""Unit tests for the Playwright browser launcher (fakes, no real browser)."""
from __future__ import annotations

from adaptivecua.executors.web_launch import BrowserSession


class FakePage:
    pass


class FakeBrowser:
    def __init__(self) -> None:
        self.closed = False
        self.new_page_kwargs = None

    async def new_page(self, **kwargs):
        self.new_page_kwargs = kwargs
        return FakePage()

    async def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, browser) -> None:
        self._browser = browser
        self.launch_kwargs = None

    async def launch(self, **kwargs):
        self.launch_kwargs = kwargs
        return self._browser


class FakePlaywright:
    def __init__(self, browser) -> None:
        self.chromium = FakeChromium(browser)
        self.stopped = False

    async def stop(self):
        self.stopped = True


class FakeAsyncPlaywright:
    """Stand-in for playwright.async_api.async_playwright (callable -> .start())."""
    def __init__(self, pw) -> None:
        self._pw = pw

    def __call__(self):
        return self

    async def start(self):
        return self._pw


async def test_browser_session_launches_sized_page_and_cleans_up():
    browser = FakeBrowser()
    pw = FakePlaywright(browser)
    apw = FakeAsyncPlaywright(pw)

    async with BrowserSession(display_size=(800, 600), headless=True,
                              async_playwright=apw) as page:
        assert isinstance(page, FakePage)

    assert pw.chromium.launch_kwargs == {"headless": True}
    assert browser.new_page_kwargs == {"viewport": {"width": 800, "height": 600}}
    assert browser.closed is True      # browser torn down on exit
    assert pw.stopped is True          # playwright stopped on exit


async def test_browser_session_headed_mode_passes_headless_false():
    browser = FakeBrowser()
    pw = FakePlaywright(browser)
    async with BrowserSession(headless=False,
                              async_playwright=FakeAsyncPlaywright(pw)):
        pass
    assert pw.chromium.launch_kwargs == {"headless": False}
