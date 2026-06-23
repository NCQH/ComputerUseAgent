import pytest
from cua.__main__ import parse_args


def test_defaults():
    ns = parse_args([])
    assert ns.ui == "cli"
    assert ns.provider == "claude"
    assert ns.executor == "desktop"
    assert ns.width == 1280
    assert ns.height == 800


def test_overrides():
    ns = parse_args(["--ui", "gui", "--provider", "openai", "--executor", "web",
                     "--width", "800", "--height", "600"])
    assert ns.ui == "gui"
    assert ns.provider == "openai"
    assert ns.executor == "web"
    assert ns.width == 800
    assert ns.height == 600


def test_invalid_ui_rejected():
    with pytest.raises(SystemExit):
        parse_args(["--ui", "hologram"])


def test_generic_and_vision_providers_accepted():
    assert parse_args(["--provider", "generic"]).provider == "generic"
    assert parse_args(["--provider", "vision"]).provider == "vision"


def test_local_and_host_executors_accepted():
    assert parse_args(["--executor", "local"]).executor == "local"
    assert parse_args(["--executor", "host"]).executor == "host"
