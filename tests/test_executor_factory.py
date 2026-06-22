import pytest
from cua.config import build_executor
from cua.executors.web import WebExecutor
from cua.executors.desktop import DesktopExecutor


def test_build_web_with_injected_page():
    ex = build_executor("web", page=object(), display_size=(800, 600))
    assert isinstance(ex, WebExecutor)
    assert ex.display_size == (800, 600)


def test_build_desktop_case_insensitive_with_injected_client():
    ex = build_executor("DESKTOP", client=object())
    assert isinstance(ex, DesktopExecutor)


def test_unknown_executor_raises():
    with pytest.raises(ValueError):
        build_executor("hologram", page=object())
