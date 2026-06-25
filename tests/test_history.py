from adaptivecua.core.history import (
    History, UserEntry, AssistantEntry, ActionEntry, ErrorEntry,
)
from adaptivecua.models import Click, StepResult


def test_entries_record_in_order():
    # Arrange
    h = History()
    # Act
    h.add_user("do thing")
    h.add_assistant("ok, clicking")
    h.add_action_result(Click(1, 2), StepResult(success=True))
    h.add_error("network down")
    # Assert
    entries = h.entries()
    assert entries == [
        UserEntry(text="do thing"),
        AssistantEntry(text="ok, clicking"),
        ActionEntry(action=Click(1, 2), result=StepResult(success=True)),
        ErrorEntry(message="network down"),
    ]


def test_entries_returns_copy_not_internal_list():
    h = History()
    h.add_user("x")
    snapshot = h.entries()
    snapshot.append(UserEntry(text="tampered"))
    assert h.entries() == [UserEntry(text="x")]
