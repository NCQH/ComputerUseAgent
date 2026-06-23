import pytest
from cua.__main__ import parse_args


def test_defaults():
    ns = parse_args([])
    assert ns.ui == "cli"
    assert ns.provider == "claude"
    assert ns.executor == "local"
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


def test_browser_and_dom_providers_accepted():
    assert parse_args(["--provider", "browser"]).provider == "browser"
    assert parse_args(["--provider", "dom"]).provider == "dom"


def test_local_and_host_executors_accepted():
    assert parse_args(["--executor", "local"]).executor == "local"
    assert parse_args(["--executor", "host"]).executor == "host"


def test_runtime_guard_flags_default():
    ns = parse_args([])
    assert ns.retries == 2            # transient-failure resilience on by default
    assert ns.max_runtime is None     # wall-clock budget off unless asked
    assert ns.max_repeated is None    # stuck-loop guard off unless asked


def test_runtime_guard_flags_override():
    ns = parse_args(["--retries", "0", "--max-runtime", "120", "--max-repeated", "5"])
    assert ns.retries == 0
    assert ns.max_runtime == 120.0
    assert ns.max_repeated == 5


def test_headed_flag_defaults_false_and_can_be_set():
    assert parse_args([]).headed is False
    assert parse_args(["--headed"]).headed is True
