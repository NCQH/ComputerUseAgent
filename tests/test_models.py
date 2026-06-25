from dataclasses import FrozenInstanceError
import pytest
from adaptivecua.models import (
    Click, Type, Key, Scroll, Move, Drag, Screenshot, Wait,
    StepResult, ConfirmRequest, ProviderResponse,
)


def test_click_holds_coordinates_and_defaults_to_left_button():
    # Arrange / Act
    action = Click(x=10, y=20)
    # Assert
    assert action.x == 10
    assert action.y == 20
    assert action.button == "left"


def test_actions_are_immutable():
    action = Type(text="hello")
    with pytest.raises(FrozenInstanceError):
        action.text = "changed"  # type: ignore[misc]


def test_step_result_defaults():
    result = StepResult(success=True)
    assert result.success is True
    assert result.error is None
    assert result.screenshot_b64 is None


def test_provider_response_carries_actions_and_flags():
    resp = ProviderResponse(
        actions=[Click(1, 2), Wait(ms=100)],
        done=False,
        assistant_text="clicking the link",
        model_flagged_risky=True,
    )
    assert len(resp.actions) == 2
    assert resp.done is False
    assert resp.model_flagged_risky is True


def test_confirm_request_pairs_action_with_reason():
    req = ConfirmRequest(action=Key(combo="ctrl+shift+delete"), reason="destructive")
    assert isinstance(req.action, Key)
    assert req.reason == "destructive"
