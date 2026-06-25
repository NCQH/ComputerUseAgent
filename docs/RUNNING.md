# Running CUA end-to-end (smoke test)

The test suite is fully offline. To exercise a real turn you need (1) a provider
API key, and (2) a live executor backend. This guide walks both backends.

## 0. Prerequisites

```bash
pip install -e ".[ui]"
pip install anthropic openai           # whichever provider you'll use
export ANTHROPIC_API_KEY=sk-ant-...     # or OPENAI_API_KEY=sk-...
```

---

## A. Local backend (REAL host desktop) ⚠️ — default

`--executor local` (alias `host`, and the default) drives the machine you are
sitting at, directly, via pyautogui — **no sandbox**. The agent's clicks and
keystrokes land on your real screen, windows, and files.

```bash
pip install -e ".[local,vision]"      # pyautogui + Pillow (+ the vision provider)
python -m adaptivecua --ui cli --provider generic --executor local
```

- The executor adopts your real screen resolution automatically and screenshots
  the real display each step.
- The `IrreversibilityGate` is the **only** guard here: denylisted targets,
  destructive key combos, and model-flagged steps still prompt for `y/n`
  confirmation, but ordinary actions execute immediately on your machine.
- pyautogui FAILSAFE is **on** by default: fling the mouse into a screen corner to
  abort a run. Pass `failsafe=False` to `LocalExecutor` for unattended runs.
- Set-of-Marks needs the tesseract binary (`winget install UB-Mannheim.TesseractOCR`).
  Without it the provider degrades to grid/point targeting automatically.
- Runaway guards: `--max-runtime <seconds>` and `--max-repeated <N>` stop a stuck
  or looping agent; `--retries <N>` retries transient provider errors (default 2).

> Use `local` only when you actually want the agent to operate your real desktop,
> and watch it. Keep a hand near the corner-abort.

---

## B. Web backend (Playwright)

`--executor web` launches its own headless Chromium page (via `BrowserSession`),
so no launcher script is needed:

```bash
pip install -e ".[web]" && playwright install chromium
python -m adaptivecua --ui cli --provider browser --executor web        # DOM Set-of-Marks (recommended)
python -m adaptivecua --ui cli --provider generic --executor web        # OCR/grid vision
python -m adaptivecua --ui cli --provider browser --executor web --headed  # show the window
```

`--provider browser` (DomVisionProvider) reads the page's interactive elements
straight from the DOM, numbers them, and lets the model pick by index — the
browser_use technique. It is far more reliable on real pages than the pixel/OCR
vision path, and falls back to grid/point when an element isn't in the DOM. It
requires `--executor web`.

> Security: element labels are read from the page and fed to the model, so page
> content can attempt prompt injection (e.g. a button text that tells the model
> what to do). Irreversible actions still pass through the `IrreversibilityGate`
> and prompt for confirmation, so treat untrusted sites with the same caution as
> any browser-automation agent.

Type a request like `search for "anthropic" and click the first result`. The
browser is a separate context, so it won't disturb your own browsing. (`--executor
web` is CLI-only for now.)

To drive an existing page or start at a specific URL, wire it yourself with an
injected page:

```python
# run_web.py
import asyncio
from adaptivecua.app import build_session
from adaptivecua.executors.web_launch import BrowserSession
from adaptivecua.ui.cli import run_cli
from adaptivecua.ui.confirm import make_cli_confirm_handler


async def ask() -> str:
    return await asyncio.get_running_loop().run_in_executor(None, input)


async def main() -> None:
    async with BrowserSession(display_size=(1280, 800), headless=False) as page:
        await page.goto("https://example.com")
        session = build_session(
            "generic", "web",
            confirm_handler=make_cli_confirm_handler(print, ask),
            page=page,
            display_size=(1280, 800),
        )
        await run_cli(session)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## What "a turn" looks like

1. You submit a request → it enters the `InputQueue`.
2. The loop drains the queue, takes a screenshot, and asks the provider for the
   next action(s).
3. Each action passes the `IrreversibilityGate`; risky ones prompt you.
4. The executor performs the action; a fresh screenshot feeds the next step.
5. You can submit more instructions at any time — they merge in at the next step.
6. When the provider signals done and the queue is empty, the session goes idle;
   your next submission resumes it.

## Troubleshooting

- **`RuntimeError: build_executor('web') without an injected page ...`** — only
  happens if you call `build_session(..., "web")` yourself without a page; use
  `--executor web` (which self-launches) or a launcher like `run_web.py` above.
- **Provider auth errors** — confirm the right env var
  (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) is exported in the same shell.
- **No `computer-use-preview` access** — use `--provider generic` (drives a normal
  vision chat model via Set-of-Marks) instead of `--provider openai`.
