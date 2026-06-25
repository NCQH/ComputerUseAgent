"""Append-only JSONL audit sink for gated actions.

With no sandbox to roll back, this log is the only forensic record of what the agent
was allowed / asked-about / refused / ran. Shared `.cua/` runtime dir (gitignored);
SPEC-3 trajectory recording reuses the same per-session directory.

`AuditSink` writes one JSON line per gated action. `NullAuditSink` is the test/no-op
default, injected like `clock`/`sleep` already are in the session.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Protocol

from adaptivecua.core.safety import PolicyResult, SafetyContext
from adaptivecua.models import Action, Type

REDACTED = "«redacted»"


def _action_to_dict(action: Action, redact_text: bool) -> dict:
    data: dict = {"type": type(action).__name__}
    data.update(vars(action))
    # Never let a typed secret land in plaintext on a sensitive surface.
    if redact_text and isinstance(action, Type):
        data["text"] = REDACTED
    return data


class AuditRecorder(Protocol):
    def record(
        self,
        action: Action,
        result: PolicyResult,
        ctx: SafetyContext | None,
        approved: bool | None,
        *,
        redact_text: bool = False,
    ) -> None:
        ...


class AuditSink:
    def __init__(self, path: str | Path, clock: Callable[[], float] = time.time) -> None:
        self._path = Path(path)
        self._clock = clock

    def record(
        self,
        action: Action,
        result: PolicyResult,
        ctx: SafetyContext | None,
        approved: bool | None,
        *,
        redact_text: bool = False,
    ) -> None:
        entry = {
            "ts": self._clock(),
            "executor": ctx.executor if ctx else None,
            "action": _action_to_dict(action, redact_text),
            "verdict": result.verdict.value,
            "policy": result.policy,
            "reason": result.reason,
            "ctx": (
                {"active_title": ctx.active_title, "url": ctx.url} if ctx else None
            ),
            "approved": approved,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)  # lazy: only on first write
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class NullAuditSink:
    def record(self, *args, **kwargs) -> None:
        return None
