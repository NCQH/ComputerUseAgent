"""Wiring tests for the DOM browser provider (build_provider / build_session)."""
import pytest

from adaptivecua.app import build_session
from adaptivecua.config import build_provider


async def _confirm(_req):
    return True


def test_build_browser_provider_needs_page():
    with pytest.raises(RuntimeError):
        build_provider("browser", client=object(), page=None)


def test_build_browser_provider_with_page():
    from adaptivecua.providers.browser.provider import DomVisionProvider
    page = object()
    p = build_provider("browser", client=object(), page=page, display_size=(800, 600))
    assert isinstance(p, DomVisionProvider)
    assert p.page is page
    assert p.display_size == (800, 600)


def test_build_session_browser_provider_shares_page_with_web_executor():
    from adaptivecua.providers.browser.provider import DomVisionProvider
    from adaptivecua.executors.web import WebExecutor
    page = object()
    session = build_session(
        "browser", "web",
        confirm_handler=_confirm,
        provider_client=object(),
        page=page,
        display_size=(800, 600),
    )
    assert isinstance(session.provider, DomVisionProvider)
    assert isinstance(session.executor, WebExecutor)
    assert session.provider.page is page          # provider drives the same page
    assert session.executor.page is page
