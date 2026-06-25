"""TrajectoryRecorder: an EventBus subscriber that persists a per-session run.

With no sandbox, a recorded trajectory is the post-hoc record of *what the agent
actually did* — the replay/eval input and the debug log. Purely additive: it only
subscribes to events the bus already publishes, so core logic is untouched.

Layout (reuses the shared `.cua/` runtime dir, gitignored — same root as SPEC-4 audit):
  .cua/runs/<session>/trajectory.jsonl   one row per completed step
  .cua/runs/<session>/NNN.png            screenshots, referenced by path to keep JSONL small

OQ-3a: one screenshot per step (simplest faithful record). OQ-3b: one run dir per
session under `.cua/`. OQ-3c: replay viewer deferred — JSONL only for v1.
"""
from __future__ import annotations

import base64
import binascii
import json
import time
from pathlib import Path
from typing import Callable

from adaptivecua.core.events import (
    ConfirmRequested,
    ErrorOccurred,
    Event,
    LogMessage,
    ScreenshotTaken,
    StepCompleted,
)
from adaptivecua.models import Action, StepResult


def _action_to_dict(action: Action) -> dict:
    data: dict = {"type": type(action).__name__}
    data.update(vars(action))
    return data


def _result_to_dict(result: StepResult) -> dict:
    # Drop the inline screenshot_b64 — the image is saved as a file and referenced.
    return {"success": result.success, "error": result.error}


class TrajectoryRecorder:
    """Subscribe `on_event` to an EventBus to record the session."""

    def __init__(self, run_dir: str | Path, clock: Callable[[], float] = time.time) -> None:
        self._dir = Path(run_dir)
        self._traj = self._dir / "trajectory.jsonl"
        self._clock = clock
        self._step = 0
        self._shot_idx = 0
        self._last_shot_ref: str | None = None
        self.counters = {"steps": 0, "confirms": 0, "blocks": 0, "errors": 0}

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)  # lazy: only on first write

    def on_event(self, event: Event) -> None:
        if isinstance(event, ScreenshotTaken):
            self._save_screenshot(event.screenshot_b64)
        elif isinstance(event, StepCompleted):
            self._record_step(event.action, event.result)
        elif isinstance(event, ConfirmRequested):
            self.counters["confirms"] += 1
        elif isinstance(event, ErrorOccurred):
            self.counters["errors"] += 1
        elif isinstance(event, LogMessage) and event.text.startswith("BLOCKED"):
            self.counters["blocks"] += 1

    def _save_screenshot(self, b64: str) -> None:
        if not b64:
            return
        name = f"{self._shot_idx:03d}.png"
        try:
            data = base64.b64decode(b64, validate=True)
            self._ensure_dir()
            (self._dir / name).write_bytes(data)
        except (binascii.Error, ValueError, OSError):
            return  # not real image bytes (or unwritable) — skip, never break the run
        self._last_shot_ref = name
        self._shot_idx += 1

    def _record_step(self, action: Action, result: StepResult) -> None:
        row = {
            "step": self._step,
            "ts": self._clock(),
            "screenshot_ref": self._last_shot_ref,
            "action": _action_to_dict(action),
            "result": _result_to_dict(result),
        }
        self._ensure_dir()
        with self._traj.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._step += 1
        self.counters["steps"] += 1

    def summary(self) -> dict:
        """Aggregate counters for the session (steps, confirms, blocks, errors)."""
        return dict(self.counters)
