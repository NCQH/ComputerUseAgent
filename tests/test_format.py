from adaptivecua.ui.format import format_event
from adaptivecua.core.events import (
    StateChanged, StepCompleted, ScreenshotTaken, LogMessage, ConfirmRequested, ErrorOccurred,
)
from adaptivecua.models import Click, StepResult, ConfirmRequest


def test_state_change():
    assert format_event(StateChanged(state="RUNNING")) == "[state] RUNNING"


def test_step_success_and_failure():
    ok = StepCompleted(action=Click(1, 2), result=StepResult(success=True))
    bad = StepCompleted(action=Click(1, 2), result=StepResult(success=False, error="boom"))
    assert format_event(ok) == "[step] Click -> ok"
    assert format_event(bad) == "[step] Click -> FAIL: boom"


def test_screenshot_is_skipped():
    assert format_event(ScreenshotTaken(screenshot_b64="x")) is None


def test_log_message_passthrough():
    assert format_event(LogMessage(text="hello")) == "hello"


def test_confirm_request_line():
    action = Click(5, 5)
    req = ConfirmRequest(action=action, reason="denylist: submit")
    out = format_event(ConfirmRequested(request=req))
    assert out == f"[confirm] denylist: submit :: {action}"


def test_error_line():
    assert format_event(ErrorOccurred(message="api down")) == "[error] api down"


def test_unknown_event_returns_none():
    assert format_event(object()) is None
