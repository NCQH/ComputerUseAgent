"""In-memory fakes for testing the core without API or Docker."""
from __future__ import annotations

from adaptivecua.core.history import History
from adaptivecua.models import Action, ProviderResponse, StepResult


class FakeProvider:
    display_size: tuple[int, int] = (1280, 800)

    def __init__(self, responses: list[ProviderResponse]) -> None:
        self._responses = list(responses)
        self._i = 0
        self.seen_history_lengths: list[int] = []

    async def next_actions(self, screenshot_b64: str, history: History) -> ProviderResponse:
        self.seen_history_lengths.append(len(history.entries()))
        if self._i < len(self._responses):
            resp = self._responses[self._i]
            self._i += 1
            return resp
        return ProviderResponse([], done=True, assistant_text="done", model_flagged_risky=False)


class FakeExecutor:
    display_size: tuple[int, int] = (1280, 800)

    def __init__(self, screenshots: list[str] | None = None, fail_on: type | None = None) -> None:
        self._screenshots = list(screenshots) if screenshots else []
        self._shot_i = 0
        self._fail_on = fail_on
        self.performed: list[Action] = []
        self.started = False
        self.closed = False

    async def start(self) -> None:
        self.started = True

    async def screenshot(self) -> str:
        if self._screenshots:
            shot = self._screenshots[self._shot_i % len(self._screenshots)]
            self._shot_i += 1
            return shot
        return "fake-screenshot"

    async def do(self, action: Action) -> StepResult:
        self.performed.append(action)
        if self._fail_on is not None and isinstance(action, self._fail_on):
            return StepResult(success=False, error=f"fake failure on {type(action).__name__}")
        return StepResult(success=True, screenshot_b64="fake-screenshot")

    async def close(self) -> None:
        self.closed = True
