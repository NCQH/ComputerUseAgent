from adaptivecua.core.safety import IrreversibilityGate
from adaptivecua.models import Click, Type, Key, Move


def test_model_flag_forces_confirmation():
    gate = IrreversibilityGate()
    needs, reason = gate.needs_confirmation(Move(1, 1), "harmless move", model_flagged=True)
    assert needs is True
    assert "model" in reason.lower()


def test_denylist_keyword_in_description_requires_confirm():
    gate = IrreversibilityGate()
    needs, reason = gate.needs_confirmation(
        Click(5, 5), "click the Submit button", model_flagged=False
    )
    assert needs is True
    assert "submit" in reason.lower()


def test_denylist_keyword_in_typed_text_requires_confirm():
    gate = IrreversibilityGate()
    needs, _ = gate.needs_confirmation(
        Type(text="please delete everything"), "", model_flagged=False
    )
    assert needs is True


def test_destructive_key_combo_requires_confirm():
    gate = IrreversibilityGate()
    needs, _ = gate.needs_confirmation(
        Key(combo="ctrl+shift+delete"), "", model_flagged=False
    )
    assert needs is True


def test_safe_action_passes():
    gate = IrreversibilityGate()
    needs, reason = gate.needs_confirmation(
        Click(5, 5), "click the search box", model_flagged=False
    )
    assert needs is False
    assert reason == ""


def test_substring_of_denylist_word_does_not_false_positive():
    """'confirmations' contains 'confirm' but is not the destructive verb."""
    gate = IrreversibilityGate()
    needs, _ = gate.needs_confirmation(
        Type(text="I read 12 confirmations today"), "", model_flagged=False
    )
    assert needs is False


def test_whole_word_denylist_keyword_still_triggers():
    gate = IrreversibilityGate()
    needs, reason = gate.needs_confirmation(
        Type(text="please confirm the order"), "", model_flagged=False
    )
    assert needs is True
    assert "confirm" in reason.lower()


def test_multiword_vietnamese_keyword_triggers_on_word_boundary():
    gate = IrreversibilityGate()
    needs, _ = gate.needs_confirmation(
        Click(1, 1), "nhấn nút thanh toán ngay", model_flagged=False
    )
    assert needs is True


def test_custom_denylist_overrides_default():
    gate = IrreversibilityGate(denylist=["frobnicate"])
    # default keyword no longer triggers
    needs_default, _ = gate.needs_confirmation(Click(1, 1), "submit form", model_flagged=False)
    assert needs_default is False
    # custom keyword triggers
    needs_custom, _ = gate.needs_confirmation(Click(1, 1), "frobnicate now", model_flagged=False)
    assert needs_custom is True
