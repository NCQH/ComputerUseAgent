"""Live REAL-DESKTOP smoke test of the LocalExecutor "hands".

Drives the actual host desktop via pyautogui (no model, no sandbox): open Notepad,
type a line, save it to a temp file, verify the file on disk, then close Notepad.
This is the deterministic confidence check that the neutral-action -> pyautogui ->
real Windows path works end to end. The model-driven version lives in
smoke_local_agent.py.

WARNING: this moves your real mouse/keyboard. Don't touch input while it runs.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time

from adaptivecua.executors.local import LocalExecutor
from adaptivecua.models import Key, Type

OUT = os.path.join(tempfile.gettempdir(), "cua_real_test.txt")
TEXT = "Hello from CUA real-flow test"


async def step(ex: LocalExecutor, action, pause: float) -> None:
    result = await ex.do(action)
    print(f"  do({action!r}) -> success={result.success} error={result.error}")
    time.sleep(pause)  # give the OS/app time to react before the next action


async def main() -> None:
    if os.path.exists(OUT):
        os.remove(OUT)

    ex = LocalExecutor()
    await ex.start()
    print(f"[executor] LocalExecutor display_size={ex.display_size}")
    print("[run] starting in 2s — keep your hands off the keyboard/mouse")
    time.sleep(2)

    # Open Notepad via the Run dialog (Win+R -> "notepad" -> Enter).
    await step(ex, Key("win+r"), 1.2)
    await step(ex, Type("notepad"), 0.4)
    await step(ex, Key("enter"), 1.8)

    # Type the content.
    await step(ex, Type(TEXT), 0.6)

    # Save: Ctrl+S, type the absolute path, Enter (overwrite prompt handled below).
    await step(ex, Key("ctrl+s"), 1.2)
    await step(ex, Type(OUT), 0.5)
    await step(ex, Key("enter"), 1.5)
    await step(ex, Key("alt+y"), 0.8)  # accept overwrite if prompted; harmless otherwise

    # Close Notepad.
    await step(ex, Key("alt+f4"), 1.0)

    # Verify on disk.
    exists = os.path.exists(OUT)
    content = ""
    if exists:
        with open(OUT, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    print(f"\n[verify] file exists={exists} path={OUT}")
    print(f"[verify] content={content!r}")

    assert exists, f"expected file was not created: {OUT}"
    assert TEXT in content, f"expected text not in saved file: {content!r}"
    print("\n[OK] REAL-FLOW (open Notepad -> type -> save -> close) PASSED")


if __name__ == "__main__":
    asyncio.run(main())
