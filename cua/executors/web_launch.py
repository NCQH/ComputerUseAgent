"""Launch a Playwright Chromium page for the web executor.

The web executor needs an already-launched Playwright page injected. This async
context manager owns that lifecycle so the CLI/GUI entrypoint (and live tests) can
get a sized page without each caller re-deriving the launch/teardown dance.
`async_playwright` is injectable so the wiring is unit-tested without a real browser.
"""
from __future__ import annotations


def _default_async_playwright():
    # Imported lazily so the package + offline test suite do not require Playwright.
    from playwright.async_api import async_playwright
    return async_playwright


class BrowserSession:
    def __init__(self, display_size: tuple[int, int] = (1280, 800), headless: bool = True,
                 async_playwright=None) -> None:
        self._display_size = display_size
        self._headless = headless
        self._async_playwright = async_playwright or _default_async_playwright()
        self._pw = None
        self._browser = None
        self.page = None

    async def __aenter__(self):
        width, height = self._display_size
        self._pw = await self._async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self._headless)
        self.page = await self._browser.new_page(
            viewport={"width": width, "height": height})
        return self.page

    async def __aexit__(self, *exc) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()
