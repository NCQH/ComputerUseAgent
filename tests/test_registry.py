"""SPEC-5 registry: decorator registration, dispatch, clear unknown-name error."""
import pytest

from adaptivecua.registry import PROVIDERS, EXECUTORS, Registry


def test_register_and_create_by_name():
    reg = Registry("widget")

    @reg.register("foo")
    def _make(*, display_size=None):
        return ("foo", display_size)

    assert reg.create("foo", display_size=(1, 2)) == ("foo", (1, 2))


def test_register_multiple_aliases():
    reg = Registry("widget")

    @reg.register("a", "b")
    def _make(**kw):
        return "made"

    assert reg.create("a") == "made"
    assert reg.create("B") == "made"        # case-insensitive
    assert reg.names() == {"a", "b"}


def test_unknown_name_lists_registered():
    reg = Registry("provider")
    reg.register("claude")(lambda **kw: None)
    with pytest.raises(ValueError) as exc:
        reg.create("gemini")
    assert "gemini" in str(exc.value)
    assert "claude" in str(exc.value)        # error names what *is* registered


def test_builtins_are_registered():
    assert {"claude", "openai", "generic", "vision", "browser", "dom", "a11y", "uia"} <= PROVIDERS.names()
    assert {"web", "local", "host"} <= EXECUTORS.names()
