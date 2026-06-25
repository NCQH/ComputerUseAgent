"""Conversation + action history fed to providers."""
from __future__ import annotations

from dataclasses import dataclass

from adaptivecua.models import Action, StepResult


@dataclass(frozen=True)
class UserEntry:
    text: str


@dataclass(frozen=True)
class AssistantEntry:
    text: str


@dataclass(frozen=True)
class ActionEntry:
    action: Action
    result: StepResult


@dataclass(frozen=True)
class ErrorEntry:
    message: str


HistoryEntry = UserEntry | AssistantEntry | ActionEntry | ErrorEntry


class History:
    def __init__(self) -> None:
        self._entries: list[HistoryEntry] = []

    def add_user(self, text: str) -> None:
        self._entries.append(UserEntry(text=text))

    def add_assistant(self, text: str) -> None:
        self._entries.append(AssistantEntry(text=text))

    def add_action_result(self, action: Action, result: StepResult) -> None:
        self._entries.append(ActionEntry(action=action, result=result))

    def add_error(self, message: str) -> None:
        self._entries.append(ErrorEntry(message=message))

    def entries(self) -> list[HistoryEntry]:
        return list(self._entries)
