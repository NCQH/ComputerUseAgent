# tests/test_runner.py
import asyncio
from cua.ui.runner import SessionRunner


class OneShotSession:
    """run() returns immediately; each call counts."""
    def __init__(self):
        self.submitted = []
        self.runs = 0
    async def submit(self, text):
        self.submitted.append(text)
    async def run(self):
        self.runs += 1


class BlockingSession:
    """run() blocks on an event so we can observe a long-running agent."""
    def __init__(self, release):
        self.release = release
        self.submitted = []
        self.runs = 0
    async def submit(self, text):
        self.submitted.append(text)
    async def run(self):
        self.runs += 1
        await self.release.wait()


async def test_first_submit_starts_a_run():
    s = OneShotSession()
    r = SessionRunner(s)
    await r.submit("hi")
    await r.aclose()
    assert s.submitted == ["hi"]
    assert s.runs == 1


async def test_submit_after_idle_starts_a_new_run():
    s = OneShotSession()
    r = SessionRunner(s)
    await r.submit("a")
    await r.aclose()
    await r.submit("b")
    await r.aclose()
    assert s.runs == 2
    assert s.submitted == ["a", "b"]


async def test_submit_while_running_does_not_start_second_run():
    release = asyncio.Event()
    s = BlockingSession(release)
    r = SessionRunner(s)
    await r.submit("a")          # starts the (blocking) run
    await asyncio.sleep(0)        # let the run task start
    await r.submit("b")          # run still active → must NOT start a 2nd run
    assert r.is_running is True
    assert s.runs == 1
    assert s.submitted == ["a", "b"]
    release.set()
    await r.aclose()
    assert s.runs == 1
