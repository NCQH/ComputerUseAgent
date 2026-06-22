# CUA Executors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the two execution backends behind the Plan 1 `Executor` interface — a `WebExecutor` (Playwright) and a `DesktopExecutor` (pyautogui inside a Docker+VNC sandbox via a small in-container HTTP agent) — plus a `build_executor` factory.

**Architecture:** Mirror the Plan 2 provider split. Each backend has a PURE translation module (neutral `Action` → backend operation descriptor / HTTP payload) that is fully unit-tested offline, and a thin stateful executor shell that takes its I/O dependency by injection (a Playwright `page`, or an async HTTP client). The desktop sandbox's container agent exposes a pure `perform(payload, gui)` core so its dispatch logic is testable with a fake `gui` without pyautogui or Docker. No real browser, HTTP server, or Docker is required to run the test suite.

**Tech Stack:** Python 3.11+, asyncio, pytest, pytest-asyncio. Real backends use Playwright (web) and Docker + Xvfb + a VNC server + pyautogui (desktop) — all imported lazily so the suite runs offline.

## Global Constraints

- Python 3.11+; asyncio.
- Implements the existing `Executor` Protocol (`cua/executors/base.py`): `display_size: tuple[int,int]`, `async start() -> None`, `async screenshot() -> str` (base64 PNG), `async do(action: Action) -> StepResult`, `async close() -> None`.
- Translation modules are PURE: no Playwright / httpx / pyautogui / Docker imports, no network.
- Executor shells must NOT import their heavy backend at module top-level; the I/O dependency is injected. The whole test suite runs offline with fakes.
- `do()` never raises: it returns `StepResult(success=False, error=...)` on failure (errors surfaced, not swallowed).
- `screenshot()` returns a base64-encoded PNG string (`base64.b64encode(png_bytes).decode()`).
- Immutability: descriptor dataclasses `frozen=True`.
- Files focused, <400 lines, one responsibility each.
- pytest + pytest-asyncio, `asyncio_mode="auto"` (already configured).
- Package import root is `cua`.

---

## File Structure

- Create: `cua/executors/web_translate.py` — pure neutral `Action` → list of `WebOp` descriptors
- Create: `cua/executors/web.py` — `WebExecutor` (injected Playwright `page`)
- Create: `cua/executors/desktop_translate.py` — pure neutral `Action` → container JSON payload
- Create: `cua/executors/desktop.py` — `DesktopExecutor` (injected async HTTP client)
- Create: `docker/desktop/agent.py` — in-container HTTP agent; pure `perform(payload, gui)` + thin server bootstrap
- Create: `docker/desktop/Dockerfile`, `docker/desktop/entrypoint.sh` — sandbox image (infra; not unit-tested)
- Modify: `cua/config.py` — add `build_executor(name, ...)` factory
- Modify: `pyproject.toml` — add optional-dependency groups `web` and `desktop`
- Tests: `tests/test_web_translate.py`, `tests/test_web_executor.py`, `tests/test_desktop_translate.py`, `tests/test_desktop_agent.py`, `tests/test_desktop_executor.py`, `tests/test_executor_factory.py`

---

### Task 1: Web translation (pure)

**Files:**
- Create: `cua/executors/web_translate.py`
- Test: `tests/test_web_translate.py`

**Interfaces:**
- Consumes: `Action` and concrete action types from `cua.models`.
- Produces: frozen `WebOp(name: str, args: dict)`; `_WHEEL_STEP: int = 100`; `normalize_key(combo: str) -> str` (neutral combo → Playwright key string); `action_to_web_ops(action: Action) -> list[WebOp]`. `Screenshot` → `[]`. Unknown action → `ValueError`.

**Mapping (exact):**
- `Click(x,y,button)` → `[WebOp("mouse_click", {"x":x,"y":y,"button":button,"clicks":1})]`
- `DoubleClick(x,y,button)` → `[WebOp("mouse_click", {"x":x,"y":y,"button":button,"clicks":2})]`
- `TripleClick(x,y,button)` → `[WebOp("mouse_click", {"x":x,"y":y,"button":button,"clicks":3})]`
- `Move(x,y)` → `[WebOp("mouse_move", {"x":x,"y":y})]`
- `Type(text)` → `[WebOp("keyboard_type", {"text":text})]`
- `Key(combo)` → `[WebOp("keyboard_press", {"key": normalize_key(combo)})]`
- `Scroll(x,y,direction,amount)` → `[WebOp("mouse_move",{"x":x,"y":y}), WebOp("mouse_wheel", {"dx":dx,"dy":dy})]` where down→`dy=amount*_WHEEL_STEP`, up→`dy=-amount*_WHEEL_STEP`, right→`dx=amount*_WHEEL_STEP`, left→`dx=-amount*_WHEEL_STEP` (the other axis 0)
- `Drag(x1,y1,x2,y2)` → `[WebOp("mouse_move",{"x":x1,"y":y1}), WebOp("mouse_down",{"button":"left"}), WebOp("mouse_move",{"x":x2,"y":y2}), WebOp("mouse_up",{"button":"left"})]`
- `Wait(ms)` → `[WebOp("wait", {"ms":ms})]`
- `Screenshot()` → `[]`

`normalize_key`: split combo on `"+"`, map each segment case-insensitively via `_MODS`/`_KEYS`, join with `"+"`. `_MODS = {"ctrl":"Control","control":"Control","shift":"Shift","alt":"Alt","option":"Alt","meta":"Meta","cmd":"Meta","command":"Meta","super":"Meta","win":"Meta"}`. `_KEYS = {"enter":"Enter","return":"Enter","tab":"Tab","esc":"Escape","escape":"Escape","space":"Space","backspace":"Backspace","delete":"Delete","del":"Delete","up":"ArrowUp","down":"ArrowDown","left":"ArrowLeft","right":"ArrowRight","home":"Home","end":"End","pageup":"PageUp","pagedown":"PageDown"}`. A segment not in either map: if length 1 keep as-is (lowercased), else `.capitalize()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_translate.py
import pytest
from cua.executors.web_translate import WebOp, action_to_web_ops, normalize_key, _WHEEL_STEP
from cua.models import (
    Click, DoubleClick, TripleClick, Move, Type, Key, Scroll, Drag, Wait, Screenshot,
)


def test_click_maps_to_single_mouse_click():
    assert action_to_web_ops(Click(10, 20)) == [
        WebOp("mouse_click", {"x": 10, "y": 20, "button": "left", "clicks": 1})
    ]


def test_double_and_triple_click_set_click_count():
    assert action_to_web_ops(DoubleClick(1, 2))[0].args["clicks"] == 2
    assert action_to_web_ops(TripleClick(1, 2))[0].args["clicks"] == 3


def test_type_and_move():
    assert action_to_web_ops(Type("hi")) == [WebOp("keyboard_type", {"text": "hi"})]
    assert action_to_web_ops(Move(3, 4)) == [WebOp("mouse_move", {"x": 3, "y": 4})]


def test_key_is_normalized_to_playwright_format():
    assert action_to_web_ops(Key("ctrl+a")) == [WebOp("keyboard_press", {"key": "Control+a"})]
    assert normalize_key("ctrl+shift+enter") == "Control+Shift+Enter"
    assert normalize_key("escape") == "Escape"


def test_scroll_down_uses_positive_dy():
    ops = action_to_web_ops(Scroll(5, 6, "down", 3))
    assert ops[0] == WebOp("mouse_move", {"x": 5, "y": 6})
    assert ops[1] == WebOp("mouse_wheel", {"dx": 0, "dy": 3 * _WHEEL_STEP})


def test_scroll_left_uses_negative_dx():
    ops = action_to_web_ops(Scroll(0, 0, "left", 2))
    assert ops[1] == WebOp("mouse_wheel", {"dx": -2 * _WHEEL_STEP, "dy": 0})


def test_drag_expands_to_move_down_move_up():
    ops = action_to_web_ops(Drag(1, 2, 9, 8))
    assert ops == [
        WebOp("mouse_move", {"x": 1, "y": 2}),
        WebOp("mouse_down", {"button": "left"}),
        WebOp("mouse_move", {"x": 9, "y": 8}),
        WebOp("mouse_up", {"button": "left"}),
    ]


def test_wait_and_screenshot():
    assert action_to_web_ops(Wait(250)) == [WebOp("wait", {"ms": 250})]
    assert action_to_web_ops(Screenshot()) == []


def test_unknown_action_raises():
    class Weird:
        pass
    with pytest.raises(ValueError):
        action_to_web_ops(Weird())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_translate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cua.executors.web_translate'`.

- [ ] **Step 3: Write minimal implementation**

```python
# cua/executors/web_translate.py
"""Pure translation: neutral Action -> list of Playwright operation descriptors."""
from __future__ import annotations

from dataclasses import dataclass

from cua.models import (
    Action, Click, DoubleClick, TripleClick, Move, Type, Key, Scroll, Drag, Wait, Screenshot,
)

_WHEEL_STEP = 100

_MODS = {
    "ctrl": "Control", "control": "Control", "shift": "Shift", "alt": "Alt",
    "option": "Alt", "meta": "Meta", "cmd": "Meta", "command": "Meta",
    "super": "Meta", "win": "Meta",
}
_KEYS = {
    "enter": "Enter", "return": "Enter", "tab": "Tab", "esc": "Escape",
    "escape": "Escape", "space": "Space", "backspace": "Backspace",
    "delete": "Delete", "del": "Delete", "up": "ArrowUp", "down": "ArrowDown",
    "left": "ArrowLeft", "right": "ArrowRight", "home": "Home", "end": "End",
    "pageup": "PageUp", "pagedown": "PageDown",
}


@dataclass(frozen=True)
class WebOp:
    name: str
    args: dict


def normalize_key(combo: str) -> str:
    parts = []
    for seg in combo.split("+"):
        s = seg.strip().lower()
        if s in _MODS:
            parts.append(_MODS[s])
        elif s in _KEYS:
            parts.append(_KEYS[s])
        elif len(s) == 1:
            parts.append(s)
        else:
            parts.append(s.capitalize())
    return "+".join(parts)


def _scroll_delta(direction: str, amount: int) -> tuple[int, int]:
    step = amount * _WHEEL_STEP
    if direction == "down":
        return 0, step
    if direction == "up":
        return 0, -step
    if direction == "right":
        return step, 0
    if direction == "left":
        return -step, 0
    raise ValueError(f"unknown scroll direction: {direction}")


def action_to_web_ops(action: Action) -> list[WebOp]:
    if isinstance(action, TripleClick):
        return [WebOp("mouse_click", {"x": action.x, "y": action.y, "button": action.button, "clicks": 3})]
    if isinstance(action, DoubleClick):
        return [WebOp("mouse_click", {"x": action.x, "y": action.y, "button": action.button, "clicks": 2})]
    if isinstance(action, Click):
        return [WebOp("mouse_click", {"x": action.x, "y": action.y, "button": action.button, "clicks": 1})]
    if isinstance(action, Move):
        return [WebOp("mouse_move", {"x": action.x, "y": action.y})]
    if isinstance(action, Type):
        return [WebOp("keyboard_type", {"text": action.text})]
    if isinstance(action, Key):
        return [WebOp("keyboard_press", {"key": normalize_key(action.combo)})]
    if isinstance(action, Scroll):
        dx, dy = _scroll_delta(action.direction, action.amount)
        return [
            WebOp("mouse_move", {"x": action.x, "y": action.y}),
            WebOp("mouse_wheel", {"dx": dx, "dy": dy}),
        ]
    if isinstance(action, Drag):
        return [
            WebOp("mouse_move", {"x": action.x1, "y": action.y1}),
            WebOp("mouse_down", {"button": "left"}),
            WebOp("mouse_move", {"x": action.x2, "y": action.y2}),
            WebOp("mouse_up", {"button": "left"}),
        ]
    if isinstance(action, Wait):
        return [WebOp("wait", {"ms": action.ms})]
    if isinstance(action, Screenshot):
        return []
    raise ValueError(f"unknown action for web executor: {action!r}")
```

Note: `TripleClick`/`DoubleClick` are checked before `Click` only if they do not subclass `Click`. They are independent dataclasses (Plan 2 Task 1), so order does not matter, but the explicit order above is safe regardless.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_translate.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add cua/executors/web_translate.py tests/test_web_translate.py
git commit -m "feat: pure web (Playwright) action translation"
```

---

### Task 2: WebExecutor

**Files:**
- Create: `cua/executors/web.py`
- Test: `tests/test_web_executor.py`

**Interfaces:**
- Consumes: `action_to_web_ops`, `WebOp` from `cua.executors.web_translate`; `Action`, `StepResult` from `cua.models`.
- Produces: `WebExecutor(page, display_size: tuple[int,int] = (1280, 800))` implementing the `Executor` Protocol. `page` is an injected Playwright-`Page`-like object exposing `mouse.move/click/down/up/wheel`, `keyboard.type/press`, and `screenshot()` (async, returns PNG bytes). `start()`/`close()` are no-ops when `page` is injected (real browser launch is out of scope for the offline suite). `do()` dispatches each `WebOp`; on any exception returns `StepResult(success=False, error=str(e))`; on success returns `StepResult(success=True, screenshot_b64=<current screenshot>)`. `screenshot()` returns base64 PNG.

**Dispatch (WebOp.name → page call):** `mouse_move`→`await page.mouse.move(x,y)`; `mouse_click`→`await page.mouse.click(x,y,button=button,click_count=clicks)`; `mouse_down`→`await page.mouse.down(button=button)`; `mouse_up`→`await page.mouse.up(button=button)`; `mouse_wheel`→`await page.mouse.wheel(dx,dy)`; `keyboard_type`→`await page.keyboard.type(text)`; `keyboard_press`→`await page.keyboard.press(key)`; `wait`→`await asyncio.sleep(ms/1000)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_executor.py
import base64
from cua.executors.web import WebExecutor
from cua.models import Click, Type, Key, Drag, Screenshot


class FakeMouse:
    def __init__(self, calls): self._calls = calls
    async def move(self, x, y): self._calls.append(("move", x, y))
    async def click(self, x, y, button="left", click_count=1):
        self._calls.append(("click", x, y, button, click_count))
    async def down(self, button="left"): self._calls.append(("down", button))
    async def up(self, button="left"): self._calls.append(("up", button))
    async def wheel(self, dx, dy): self._calls.append(("wheel", dx, dy))


class FakeKeyboard:
    def __init__(self, calls): self._calls = calls
    async def type(self, text): self._calls.append(("type", text))
    async def press(self, key): self._calls.append(("press", key))


class FakePage:
    def __init__(self, fail=False):
        self.calls = []
        self.mouse = FakeMouse(self.calls)
        self.keyboard = FakeKeyboard(self.calls)
        self._fail = fail
    async def screenshot(self):
        if self._fail:
            raise RuntimeError("capture failed")
        return b"PNGBYTES"


async def test_click_dispatches_mouse_click_and_returns_screenshot():
    page = FakePage()
    ex = WebExecutor(page)
    result = await ex.do(Click(10, 20))
    assert ("click", 10, 20, "left", 1) in page.calls
    assert result.success is True
    assert result.screenshot_b64 == base64.b64encode(b"PNGBYTES").decode()


async def test_type_and_key_dispatch():
    page = FakePage()
    ex = WebExecutor(page)
    await ex.do(Type("hello"))
    await ex.do(Key("ctrl+a"))
    assert ("type", "hello") in page.calls
    assert ("press", "Control+a") in page.calls


async def test_drag_dispatches_full_sequence_in_order():
    page = FakePage()
    ex = WebExecutor(page)
    await ex.do(Drag(1, 2, 9, 8))
    assert page.calls == [
        ("move", 1, 2), ("down", "left"), ("move", 9, 8), ("up", "left"),
    ]


async def test_screenshot_action_is_noop_but_still_returns_image():
    page = FakePage()
    ex = WebExecutor(page)
    result = await ex.do(Screenshot())
    # no mouse/keyboard calls
    assert page.calls == []
    assert result.success is True


async def test_failure_returns_unsuccessful_step_result():
    page = FakePage(fail=True)
    ex = WebExecutor(page)
    result = await ex.do(Click(1, 1))
    assert result.success is False
    assert "capture failed" in (result.error or "")


async def test_screenshot_returns_base64():
    page = FakePage()
    ex = WebExecutor(page)
    shot = await ex.screenshot()
    assert shot == base64.b64encode(b"PNGBYTES").decode()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cua.executors.web'`.

- [ ] **Step 3: Write minimal implementation**

```python
# cua/executors/web.py
"""WebExecutor: drives a Playwright page from neutral actions."""
from __future__ import annotations

import asyncio
import base64

from cua.executors.web_translate import WebOp, action_to_web_ops
from cua.models import Action, StepResult


class WebExecutor:
    def __init__(self, page, display_size: tuple[int, int] = (1280, 800)) -> None:
        self.page = page
        self.display_size = display_size

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def screenshot(self) -> str:
        png = await self.page.screenshot()
        return base64.b64encode(png).decode()

    async def _dispatch(self, op: WebOp) -> None:
        a = op.args
        if op.name == "mouse_move":
            await self.page.mouse.move(a["x"], a["y"])
        elif op.name == "mouse_click":
            await self.page.mouse.click(a["x"], a["y"], button=a["button"], click_count=a["clicks"])
        elif op.name == "mouse_down":
            await self.page.mouse.down(button=a["button"])
        elif op.name == "mouse_up":
            await self.page.mouse.up(button=a["button"])
        elif op.name == "mouse_wheel":
            await self.page.mouse.wheel(a["dx"], a["dy"])
        elif op.name == "keyboard_type":
            await self.page.keyboard.type(a["text"])
        elif op.name == "keyboard_press":
            await self.page.keyboard.press(a["key"])
        elif op.name == "wait":
            await asyncio.sleep(a["ms"] / 1000)
        else:
            raise ValueError(f"unknown web op: {op.name}")

    async def do(self, action: Action) -> StepResult:
        try:
            for op in action_to_web_ops(action):
                await self._dispatch(op)
            shot = await self.screenshot()
            return StepResult(success=True, screenshot_b64=shot)
        except Exception as exc:  # noqa: BLE001 — surfaced in StepResult, not swallowed
            return StepResult(success=False, error=str(exc))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_executor.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add cua/executors/web.py tests/test_web_executor.py
git commit -m "feat: WebExecutor driving an injected Playwright page"
```

---

### Task 3: Desktop translation (pure)

**Files:**
- Create: `cua/executors/desktop_translate.py`
- Test: `tests/test_desktop_translate.py`

**Interfaces:**
- Consumes: action types from `cua.models`.
- Produces: `action_to_payload(action: Action) -> dict` mapping a neutral action to the JSON the in-container agent understands. `Screenshot` → `{"action": "screenshot"}`. Unknown → `ValueError`.

**Mapping (exact):**
- `Click(x,y,button)` → `{"action":"click","x":x,"y":y,"button":button,"clicks":1}`
- `DoubleClick(x,y,button)` → `{"action":"click","x":x,"y":y,"button":button,"clicks":2}`
- `TripleClick(x,y,button)` → `{"action":"click","x":x,"y":y,"button":button,"clicks":3}`
- `Move(x,y)` → `{"action":"move","x":x,"y":y}`
- `Type(text)` → `{"action":"type","text":text}`
- `Key(combo)` → `{"action":"hotkey","keys":[seg.strip().lower() for seg in combo.split("+")]}`
- `Scroll(x,y,direction,amount)` → `{"action":"scroll","x":x,"y":y,"direction":direction,"amount":amount}`
- `Drag(x1,y1,x2,y2)` → `{"action":"drag","x1":x1,"y1":y1,"x2":x2,"y2":y2}`
- `Wait(ms)` → `{"action":"wait","ms":ms}`
- `Screenshot()` → `{"action":"screenshot"}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_desktop_translate.py
import pytest
from cua.executors.desktop_translate import action_to_payload
from cua.models import (
    Click, DoubleClick, TripleClick, Move, Type, Key, Scroll, Drag, Wait, Screenshot,
)


def test_click_payload():
    assert action_to_payload(Click(10, 20, "right")) == {
        "action": "click", "x": 10, "y": 20, "button": "right", "clicks": 1
    }


def test_double_triple_click_counts():
    assert action_to_payload(DoubleClick(1, 1))["clicks"] == 2
    assert action_to_payload(TripleClick(1, 1))["clicks"] == 3


def test_key_splits_into_lowercase_segments():
    assert action_to_payload(Key("Ctrl+A")) == {"action": "hotkey", "keys": ["ctrl", "a"]}


def test_type_move_scroll_drag_wait_screenshot():
    assert action_to_payload(Type("hi")) == {"action": "type", "text": "hi"}
    assert action_to_payload(Move(2, 3)) == {"action": "move", "x": 2, "y": 3}
    assert action_to_payload(Scroll(1, 2, "down", 4)) == {
        "action": "scroll", "x": 1, "y": 2, "direction": "down", "amount": 4
    }
    assert action_to_payload(Drag(1, 2, 3, 4)) == {
        "action": "drag", "x1": 1, "y1": 2, "x2": 3, "y2": 4
    }
    assert action_to_payload(Wait(50)) == {"action": "wait", "ms": 50}
    assert action_to_payload(Screenshot()) == {"action": "screenshot"}


def test_unknown_action_raises():
    class Weird:
        pass
    with pytest.raises(ValueError):
        action_to_payload(Weird())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_desktop_translate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cua.executors.desktop_translate'`.

- [ ] **Step 3: Write minimal implementation**

```python
# cua/executors/desktop_translate.py
"""Pure translation: neutral Action -> container HTTP agent JSON payload."""
from __future__ import annotations

from cua.models import (
    Action, Click, DoubleClick, TripleClick, Move, Type, Key, Scroll, Drag, Wait, Screenshot,
)


def action_to_payload(action: Action) -> dict:
    if isinstance(action, TripleClick):
        return {"action": "click", "x": action.x, "y": action.y, "button": action.button, "clicks": 3}
    if isinstance(action, DoubleClick):
        return {"action": "click", "x": action.x, "y": action.y, "button": action.button, "clicks": 2}
    if isinstance(action, Click):
        return {"action": "click", "x": action.x, "y": action.y, "button": action.button, "clicks": 1}
    if isinstance(action, Move):
        return {"action": "move", "x": action.x, "y": action.y}
    if isinstance(action, Type):
        return {"action": "type", "text": action.text}
    if isinstance(action, Key):
        return {"action": "hotkey", "keys": [s.strip().lower() for s in action.combo.split("+")]}
    if isinstance(action, Scroll):
        return {"action": "scroll", "x": action.x, "y": action.y, "direction": action.direction, "amount": action.amount}
    if isinstance(action, Drag):
        return {"action": "drag", "x1": action.x1, "y1": action.y1, "x2": action.x2, "y2": action.y2}
    if isinstance(action, Wait):
        return {"action": "wait", "ms": action.ms}
    if isinstance(action, Screenshot):
        return {"action": "screenshot"}
    raise ValueError(f"unknown action for desktop executor: {action!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_desktop_translate.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add cua/executors/desktop_translate.py tests/test_desktop_translate.py
git commit -m "feat: pure desktop (container) action translation"
```

---

### Task 4: Container agent core + sandbox image

**Files:**
- Create: `docker/desktop/agent.py`
- Create: `docker/desktop/Dockerfile`
- Create: `docker/desktop/entrypoint.sh`
- Test: `tests/test_desktop_agent.py`

**Interfaces:**
- Consumes: nothing from `cua` (the agent runs inside the container, standalone).
- Produces: `perform(payload: dict, gui) -> dict` — pure dispatcher that calls a pyautogui-like `gui` and returns `{"ok": True}` (or `{"ok": True, "image": <b64>}` for screenshot). Unknown action → returns `{"ok": False, "error": ...}` (the agent must not crash on a bad payload). `gui` exposes: `moveTo(x,y)`, `click(x=,y=,button=,clicks=)`, `dragTo(x,y,button=)`, `typewrite(text)`, `hotkey(*keys)`, `scroll(amount)`/`hscroll(amount)`, `screenshot()` (returns PNG bytes), and `sleep`-free (the agent uses `time.sleep`). The HTTP server bootstrap imports `pyautogui` lazily and is NOT unit-tested.

**Dispatch in `perform`:** `click`→`gui.click(x=,y=,button=,clicks=)`; `move`→`gui.moveTo(x,y)`; `drag`→`gui.moveTo(x1,y1)` then `gui.dragTo(x2,y2,button="left")`; `type`→`gui.typewrite(text)`; `hotkey`→`gui.hotkey(*keys)`; `scroll`→ vertical uses `gui.scroll(±amount)` (down negative, up positive), horizontal uses `gui.hscroll(±amount)` (right positive, left negative); `wait`→`time.sleep(ms/1000)`; `screenshot`→`{"ok":True,"image": base64(gui.screenshot()-as-PNG-bytes)}`. For screenshot, assume `gui.screenshot()` returns PNG bytes directly (the fake does; the real wrapper converts the PIL image to PNG bytes before calling `perform`, or `perform` accepts bytes — keep `perform` expecting bytes from `gui.screenshot()`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_desktop_agent.py
import base64
import sys
import os

# agent.py lives in docker/desktop, not in the cua package — load it by path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "docker", "desktop"))
from agent import perform  # noqa: E402


class FakeGui:
    def __init__(self): self.calls = []
    def moveTo(self, x, y): self.calls.append(("moveTo", x, y))
    def click(self, x=None, y=None, button="left", clicks=1):
        self.calls.append(("click", x, y, button, clicks))
    def dragTo(self, x, y, button="left"): self.calls.append(("dragTo", x, y, button))
    def typewrite(self, text): self.calls.append(("typewrite", text))
    def hotkey(self, *keys): self.calls.append(("hotkey", keys))
    def scroll(self, amount): self.calls.append(("scroll", amount))
    def hscroll(self, amount): self.calls.append(("hscroll", amount))
    def screenshot(self): return b"PNGBYTES"


def test_click_dispatch():
    gui = FakeGui()
    out = perform({"action": "click", "x": 5, "y": 6, "button": "left", "clicks": 2}, gui)
    assert out == {"ok": True}
    assert ("click", 5, 6, "left", 2) in gui.calls


def test_drag_moves_then_drags():
    gui = FakeGui()
    perform({"action": "drag", "x1": 1, "y1": 2, "x2": 9, "y2": 8}, gui)
    assert gui.calls == [("moveTo", 1, 2), ("dragTo", 9, 8, "left")]


def test_hotkey_and_type():
    gui = FakeGui()
    perform({"action": "hotkey", "keys": ["ctrl", "a"]}, gui)
    perform({"action": "type", "text": "hi"}, gui)
    assert ("hotkey", ("ctrl", "a")) in gui.calls
    assert ("typewrite", "hi") in gui.calls


def test_scroll_directions():
    gui = FakeGui()
    perform({"action": "scroll", "x": 0, "y": 0, "direction": "down", "amount": 3}, gui)
    perform({"action": "scroll", "x": 0, "y": 0, "direction": "right", "amount": 2}, gui)
    assert ("scroll", -3) in gui.calls
    assert ("hscroll", 2) in gui.calls


def test_screenshot_returns_base64_image():
    gui = FakeGui()
    out = perform({"action": "screenshot"}, gui)
    assert out["ok"] is True
    assert out["image"] == base64.b64encode(b"PNGBYTES").decode()


def test_unknown_action_returns_error_not_raise():
    gui = FakeGui()
    out = perform({"action": "nope"}, gui)
    assert out["ok"] is False
    assert "error" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_desktop_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent'`.

- [ ] **Step 3: Write minimal implementation**

```python
# docker/desktop/agent.py
"""In-container HTTP agent: performs neutral-action payloads via pyautogui.

`perform` is pure (takes an injected pyautogui-like `gui`) so it is unit-tested
on the host without pyautogui. The HTTP server bootstrap at the bottom imports
pyautogui lazily and only runs when executed as a script inside the container.
"""
from __future__ import annotations

import base64
import time


def perform(payload: dict, gui) -> dict:
    try:
        action = payload.get("action")
        if action == "click":
            gui.click(x=payload["x"], y=payload["y"], button=payload.get("button", "left"),
                      clicks=payload.get("clicks", 1))
            return {"ok": True}
        if action == "move":
            gui.moveTo(payload["x"], payload["y"])
            return {"ok": True}
        if action == "drag":
            gui.moveTo(payload["x1"], payload["y1"])
            gui.dragTo(payload["x2"], payload["y2"], button="left")
            return {"ok": True}
        if action == "type":
            gui.typewrite(payload["text"])
            return {"ok": True}
        if action == "hotkey":
            gui.hotkey(*payload["keys"])
            return {"ok": True}
        if action == "scroll":
            amount = payload["amount"]
            direction = payload["direction"]
            if direction == "down":
                gui.scroll(-amount)
            elif direction == "up":
                gui.scroll(amount)
            elif direction == "right":
                gui.hscroll(amount)
            elif direction == "left":
                gui.hscroll(-amount)
            else:
                return {"ok": False, "error": f"bad scroll direction: {direction}"}
            return {"ok": True}
        if action == "wait":
            time.sleep(payload["ms"] / 1000)
            return {"ok": True}
        if action == "screenshot":
            png = gui.screenshot()
            return {"ok": True, "image": base64.b64encode(png).decode()}
        return {"ok": False, "error": f"unknown action: {action}"}
    except Exception as exc:  # noqa: BLE001 — return error to caller, never crash the agent
        return {"ok": False, "error": str(exc)}


def _make_real_gui():
    """Build a pyautogui-backed gui whose screenshot() returns PNG bytes."""
    import io
    import pyautogui  # imported lazily; only available inside the container

    class _Gui:
        def moveTo(self, x, y): pyautogui.moveTo(x, y)
        def click(self, x=None, y=None, button="left", clicks=1):
            pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        def dragTo(self, x, y, button="left"): pyautogui.dragTo(x, y, button=button)
        def typewrite(self, text): pyautogui.typewrite(text)
        def hotkey(self, *keys): pyautogui.hotkey(*keys)
        def scroll(self, amount): pyautogui.scroll(amount)
        def hscroll(self, amount): pyautogui.hscroll(amount)
        def screenshot(self):
            buf = io.BytesIO()
            pyautogui.screenshot().save(buf, format="PNG")
            return buf.getvalue()

    return _Gui()


def _run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    import json
    from http.server import BaseHTTPRequestHandler, HTTPServer

    gui = _make_real_gui()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path == "/screenshot":
                self._send(perform({"action": "screenshot"}, gui))
            else:
                self._send({"ok": False, "error": "not found"}, code=404)

        def do_POST(self):  # noqa: N802
            if self.path == "/do":
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
                self._send(perform(payload, gui))
            else:
                self._send({"ok": False, "error": "not found"}, code=404)

    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    _run_server()
```

```dockerfile
# docker/desktop/Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb x11vnc fluxbox scrot python3-tk python3-dev gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pyautogui pillow

WORKDIR /app
COPY agent.py /app/agent.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV DISPLAY=:99
EXPOSE 8000 5900

CMD ["/app/entrypoint.sh"]
```

```bash
# docker/desktop/entrypoint.sh
#!/usr/bin/env bash
set -e

Xvfb :99 -screen 0 1280x800x24 &
sleep 1
fluxbox >/dev/null 2>&1 &
x11vnc -display :99 -nopw -forever -shared -rfbport 5900 >/dev/null 2>&1 &

exec python /app/agent.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_desktop_agent.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add docker/desktop/agent.py docker/desktop/Dockerfile docker/desktop/entrypoint.sh tests/test_desktop_agent.py
git commit -m "feat: desktop sandbox container agent (pyautogui) + image"
```

---

### Task 5: DesktopExecutor

**Files:**
- Create: `cua/executors/desktop.py`
- Test: `tests/test_desktop_executor.py`

**Interfaces:**
- Consumes: `action_to_payload` from `cua.executors.desktop_translate`; `Action`, `StepResult` from `cua.models`.
- Produces: `DesktopExecutor(client, base_url: str = "http://localhost:8000", display_size: tuple[int,int] = (1280, 800))` implementing the `Executor` Protocol. `client` is an injected async HTTP client exposing `async post(url, json=...) -> Resp` and `async get(url) -> Resp`, where `Resp` has `.json()` (sync, returns dict) — matching httpx's response shape closely enough for the fake. `start()`/`close()` are no-ops when a client is injected (real container lifecycle via Docker is out of scope for the offline suite). `do()` posts the translated payload to `base_url+"/do"`; if the response dict has `ok=False` → `StepResult(success=False, error=resp["error"])`; on transport exception → `StepResult(success=False, error=str(e))`; else `StepResult(success=True, screenshot_b64=<screenshot()>)`. `screenshot()` GETs `base_url+"/screenshot"` and returns the response's `image` field (already base64).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_desktop_executor.py
from cua.executors.desktop import DesktopExecutor
from cua.models import Click, Type


class FakeResp:
    def __init__(self, data): self._data = data
    def json(self): return self._data


class FakeClient:
    def __init__(self, do_data=None, shot_data=None, raise_on_post=False):
        self.posts = []
        self.gets = []
        self._do_data = do_data or {"ok": True}
        self._shot_data = shot_data or {"ok": True, "image": "SHOT64"}
        self._raise_on_post = raise_on_post
    async def post(self, url, json=None):
        if self._raise_on_post:
            raise RuntimeError("connection refused")
        self.posts.append((url, json))
        return FakeResp(self._do_data)
    async def get(self, url):
        self.gets.append(url)
        return FakeResp(self._shot_data)


async def test_do_posts_translated_payload_and_returns_screenshot():
    client = FakeClient()
    ex = DesktopExecutor(client, base_url="http://host:8000")
    result = await ex.do(Click(3, 4))
    assert client.posts == [("http://host:8000/do",
                             {"action": "click", "x": 3, "y": 4, "button": "left", "clicks": 1})]
    assert result.success is True
    assert result.screenshot_b64 == "SHOT64"


async def test_agent_error_response_yields_failed_step():
    client = FakeClient(do_data={"ok": False, "error": "pyautogui blew up"})
    ex = DesktopExecutor(client)
    result = await ex.do(Type("x"))
    assert result.success is False
    assert "pyautogui blew up" in (result.error or "")


async def test_transport_exception_yields_failed_step():
    client = FakeClient(raise_on_post=True)
    ex = DesktopExecutor(client)
    result = await ex.do(Click(1, 1))
    assert result.success is False
    assert "connection refused" in (result.error or "")


async def test_screenshot_returns_image_field():
    client = FakeClient(shot_data={"ok": True, "image": "ABC123"})
    ex = DesktopExecutor(client)
    shot = await ex.screenshot()
    assert shot == "ABC123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_desktop_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cua.executors.desktop'`.

- [ ] **Step 3: Write minimal implementation**

```python
# cua/executors/desktop.py
"""DesktopExecutor: drives the sandbox container agent over HTTP."""
from __future__ import annotations

from cua.executors.desktop_translate import action_to_payload
from cua.models import Action, StepResult


class DesktopExecutor:
    def __init__(self, client, base_url: str = "http://localhost:8000",
                 display_size: tuple[int, int] = (1280, 800)) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.display_size = display_size

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def screenshot(self) -> str:
        resp = await self.client.get(self.base_url + "/screenshot")
        return resp.json().get("image", "")

    async def do(self, action: Action) -> StepResult:
        payload = action_to_payload(action)
        try:
            resp = await self.client.post(self.base_url + "/do", json=payload)
            data = resp.json()
            if not data.get("ok", False):
                return StepResult(success=False, error=str(data.get("error", "agent reported failure")))
            shot = await self.screenshot()
            return StepResult(success=True, screenshot_b64=shot)
        except Exception as exc:  # noqa: BLE001 — surfaced in StepResult
            return StepResult(success=False, error=str(exc))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_desktop_executor.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add cua/executors/desktop.py tests/test_desktop_executor.py
git commit -m "feat: DesktopExecutor driving the sandbox agent over HTTP"
```

---

### Task 6: Executor factory + optional deps

**Files:**
- Modify: `cua/config.py` (add `build_executor`)
- Modify: `pyproject.toml` (add optional-dependency groups)
- Test: `tests/test_executor_factory.py`

**Interfaces:**
- Consumes: `WebExecutor` (`cua.executors.web`), `DesktopExecutor` (`cua.executors.desktop`).
- Produces: `build_executor(name: str, *, page=None, client=None, display_size: tuple[int,int]=(1280,800)) -> Executor`. `name` (case-insensitive): `"web"` → `WebExecutor(page=page, display_size=...)`; `"desktop"` → `DesktopExecutor(client=client, display_size=...)`; unknown → `ValueError`. When `page`/`client` is provided it is injected directly (offline path). When `None`, the real backend (Playwright / httpx) is imported lazily — these lazy branches are NOT exercised by the offline tests.

**Important:** Do NOT add a top-level import of `playwright` or `httpx` in `cua/config.py`. Keep the existing top-level provider imports; add the executor imports (`from cua.executors.web import WebExecutor`, `from cua.executors.desktop import DesktopExecutor`) — those are pure and safe. Any Playwright/httpx construction goes inside the `page is None` / `client is None` branches.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_executor_factory.py
import pytest
from cua.config import build_executor
from cua.executors.web import WebExecutor
from cua.executors.desktop import DesktopExecutor


def test_build_web_with_injected_page():
    ex = build_executor("web", page=object(), display_size=(800, 600))
    assert isinstance(ex, WebExecutor)
    assert ex.display_size == (800, 600)


def test_build_desktop_case_insensitive_with_injected_client():
    ex = build_executor("DESKTOP", client=object())
    assert isinstance(ex, DesktopExecutor)


def test_unknown_executor_raises():
    with pytest.raises(ValueError):
        build_executor("hologram", page=object())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_executor_factory.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_executor'`.

- [ ] **Step 3: Write minimal implementation**

Append to `cua/config.py` (keep existing `build_provider` and imports; add these imports near the top with the other `cua.*` imports):

```python
from cua.executors.web import WebExecutor
from cua.executors.desktop import DesktopExecutor
```

Add the factory function:

```python
def build_executor(name, *, page=None, client=None, display_size=(1280, 800)):
    key = name.strip().lower()
    if key == "web":
        if page is None:
            from playwright.async_api import async_playwright  # lazy; container/host only
            raise RuntimeError(
                "build_executor('web') without an injected page requires launching "
                "Playwright; pass page=<playwright page> or launch it in the caller"
            )
        return WebExecutor(page=page, display_size=display_size)
    if key == "desktop":
        if client is None:
            import httpx  # lazy; only needed for the real HTTP client
            client = httpx.AsyncClient()
        return DesktopExecutor(client=client, display_size=display_size)
    raise ValueError(f"unknown executor: {name!r}")
```

Note: the `web`-without-page branch intentionally raises a clear error rather than guessing how the caller wants the browser launched (browser/context/page wiring is a UI-layer concern handled in Plan 4). The `import async_playwright` line documents the dependency; the offline tests always pass `page=`, so this branch is never taken in tests.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_executor_factory.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Add optional dependency groups + run full suite + commit**

Add to `pyproject.toml` under `[project]` (create the section if absent):

```toml
[project.optional-dependencies]
web = ["playwright>=1.40"]
desktop = ["httpx>=0.27"]
test = ["pytest>=8", "pytest-asyncio>=0.23"]
```

Run the full suite:

Run: `python -m pytest -q`
Expected: PASS (all prior tests plus the new executor tests green).

```bash
git add cua/config.py pyproject.toml tests/test_executor_factory.py
git commit -m "feat: executor factory and optional dependency groups"
```

---

## Self-Review

**1. Spec coverage (spec §5 — Executors):**
- `Executor` interface (`display_size`, `start/screenshot/do/close`) → both executors implement it (Tasks 2, 5). ✓
- WebExecutor via Playwright, DOM/pixel ops → Task 1 (translation) + Task 2 (dispatch). ✓
- DesktopExecutor via pyautogui in Docker+VNC, talking to an in-container HTTP agent (`/screenshot`, `/do`) instead of host pyautogui → Tasks 3 (translation), 4 (agent + Dockerfile + entrypoint with Xvfb/x11vnc), 5 (executor). ✓
- `display_size` provided for provider coordinate normalization → both default `(1280,800)`, configurable. ✓
- `do()` failures recorded as `StepResult(success=False, ...)` (executor self-heal contract from Plan 1) → Tasks 2, 5. ✓
- Factory selection (`web`/`desktop`) → Task 6. ✓
- Out of scope (deferred to Plan 4): real browser/context launch wiring, real Docker container lifecycle (`docker run`/stop) in `start()/close()`, VNC viewer surfacing to the UI. Intentionally not in this plan; `start()/close()` are no-ops on the injected/offline path.

**2. Placeholder scan:** No TBD/TODO. Every code step shows complete code; every test shows full assertions. The `web`-without-page branch raises an explicit, documented error rather than a placeholder. ✓

**3. Type consistency:** `Executor` shape (`display_size`, `start/screenshot/do/close`) matches Plan 1's `cua/executors/base.py` across Tasks 2/5/6. `StepResult(success, error, screenshot_b64)` used consistently. `WebOp(name, args)` defined in Task 1, consumed in Task 2. `action_to_web_ops`/`action_to_payload`/`perform`/`build_executor` names consistent between producing and consuming tasks. Fake-client `Resp.json()` is sync (matches httpx); `DesktopExecutor.screenshot` calls `resp.json().get("image")` consistently. ✓

> Note: real Playwright `page.screenshot()` returns bytes and `response.json()` in httpx is sync — the fakes match these shapes, so the offline-tested dispatch logic transfers to the real backends without signature changes.
