"""SPEC-3 trajectory recorder: bus subscriber persists steps + screenshots."""
import base64
import json

from cua.core.events import (
    ConfirmRequested,
    ErrorOccurred,
    LogMessage,
    ScreenshotTaken,
    StepCompleted,
)
from cua.models import Click, ConfirmRequest, StepResult, Type
from cua.telemetry.recorder import TrajectoryRecorder

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfakebytes").decode()


def _rows(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").strip().splitlines()]


def test_records_step_referencing_last_screenshot(tmp_path):
    rec = TrajectoryRecorder(tmp_path / "run", clock=lambda: 1.0)
    rec.on_event(ScreenshotTaken(screenshot_b64=PNG))
    rec.on_event(StepCompleted(action=Click(3, 4), result=StepResult(success=True)))

    traj = tmp_path / "run" / "trajectory.jsonl"
    rows = _rows(traj)
    assert len(rows) == 1
    assert rows[0]["step"] == 0
    assert rows[0]["ts"] == 1.0
    assert rows[0]["screenshot_ref"] == "000.png"
    assert rows[0]["action"] == {"type": "Click", "x": 3, "y": 4, "button": "left"}
    assert rows[0]["result"] == {"success": True, "error": None}
    assert (tmp_path / "run" / "000.png").read_bytes().startswith(b"\x89PNG")


def test_step_increments_and_result_excludes_inline_image(tmp_path):
    rec = TrajectoryRecorder(tmp_path / "run", clock=lambda: 2.0)
    rec.on_event(ScreenshotTaken(screenshot_b64=PNG))
    rec.on_event(StepCompleted(Click(1, 1), StepResult(success=True, screenshot_b64=PNG)))
    rec.on_event(ScreenshotTaken(screenshot_b64=PNG))
    rec.on_event(StepCompleted(Type("hi"), StepResult(success=False, error="boom")))

    rows = _rows(tmp_path / "run" / "trajectory.jsonl")
    assert [r["step"] for r in rows] == [0, 1]
    assert rows[0]["screenshot_ref"] == "000.png"
    assert rows[1]["screenshot_ref"] == "001.png"
    assert "screenshot_b64" not in rows[1]["result"]      # image not duplicated inline
    assert rows[1]["result"] == {"success": False, "error": "boom"}


def test_invalid_screenshot_bytes_are_skipped_not_crashing(tmp_path):
    rec = TrajectoryRecorder(tmp_path / "run")
    rec.on_event(ScreenshotTaken(screenshot_b64="fake-screenshot"))   # not valid b64
    rec.on_event(StepCompleted(Click(1, 1), StepResult(success=True)))
    rows = _rows(tmp_path / "run" / "trajectory.jsonl")
    assert rows[0]["screenshot_ref"] is None                          # no image, still recorded
    assert not list((tmp_path / "run").glob("*.png"))


def test_counters_aggregate_events(tmp_path):
    rec = TrajectoryRecorder(tmp_path / "run")
    rec.on_event(ScreenshotTaken(screenshot_b64=PNG))
    rec.on_event(StepCompleted(Click(1, 1), StepResult(success=True)))
    rec.on_event(ConfirmRequested(request=ConfirmRequest(Click(1, 1), "why")))
    rec.on_event(LogMessage(text="BLOCKED by destructive_key: nope"))
    rec.on_event(ErrorOccurred(message="api down"))
    rec.on_event(LogMessage(text="[model] just thinking"))            # not a block

    assert rec.summary() == {"steps": 1, "confirms": 1, "blocks": 1, "errors": 1}
