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

## A. Desktop backend (Docker + VNC sandbox)

The agent drives a virtual screen inside a container, so it never fights your
real mouse/keyboard. You watch over VNC.

### 1. Build the sandbox image

```bash
docker build -t cua-desktop docker/desktop
```

The image (`docker/desktop/Dockerfile`) runs Xvfb (virtual display), x11vnc
(remote view on 5900), fluxbox, and the HTTP agent (`agent.py`) on port 8000.

### 2. Run the container

```bash
docker run --rm -p 8000:8000 -p 5900:5900 cua-desktop
```

- `8000` — the agent's HTTP API (`GET /screenshot`, `POST /do`) that
  `DesktopExecutor` talks to.
- `5900` — VNC. Connect any VNC viewer to `localhost:5900` (no password — this
  is a local dev sandbox only) to watch the agent work.

### 3. Verify the agent API by hand (optional)

```bash
curl http://localhost:8000/screenshot      # -> {"ok": true, "image": "<base64 png>"}
curl -X POST http://localhost:8000/do \
     -H 'Content-Type: application/json' \
     -d '{"action":"move","x":100,"y":100}'   # -> {"ok": true}
```

### 4. Launch CUA against it

`build_executor("desktop")` builds an `httpx.AsyncClient` pointed at
`http://localhost:8000` by default.

```bash
python -m cua --ui cli --provider claude --executor desktop
```

Then type a request, e.g. `mở terminal và gõ "hello"`. Watch it happen in the
VNC viewer. When the agent reaches something irreversible (a denylisted button,
a destructive key combo, or a model-flagged step) the CLI prints a confirmation
prompt — answer `y` to allow, anything else to reject.

> Need a non-default container host/port? `DesktopExecutor(client, base_url=...)`
> accepts a custom URL; wire it via a small script calling `build_session(...)`
> with an injected `http_client` if you containerize remotely.

---

## A2. Local backend (REAL host desktop) ⚠️

`--executor local` (alias `host`) drives the machine you are sitting at, directly,
via pyautogui — **no sandbox**. The agent's clicks and keystrokes land on your real
screen, windows, and files.

```bash
pip install -e ".[local,vision]"      # pyautogui + Pillow (+ the vision provider)
python -m cua --ui cli --provider generic --executor local
```

- The executor adopts your real screen resolution automatically and screenshots
  the real display each step.
- The `IrreversibilityGate` is the **only** guard here: denylisted targets,
  destructive key combos, and model-flagged steps still prompt for `y/n`
  confirmation, but ordinary actions execute immediately on your machine.
- Set-of-Marks needs the tesseract binary (`winget install UB-Mannheim.TesseractOCR`).
  Without it the provider degrades to grid/point targeting automatically.

> Safety: prefer the Docker sandbox (section A) for experimentation. Use `local`
> only when you actually want the agent to operate your real desktop, and watch it.

---

## B. Web backend (Playwright)

The web executor drives a Playwright `page`. `build_executor("web", page=None)`
deliberately refuses to guess how you want the browser launched, so wire the
page yourself in a tiny launcher script:

```python
# run_web.py
import asyncio
from playwright.async_api import async_playwright
from cua.app import build_session
from cua.ui.cli import run_cli
from cua.ui.confirm import make_cli_confirm_handler


async def ask() -> str:
    return await asyncio.get_running_loop().run_in_executor(None, input)


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.goto("https://example.com")

        session = build_session(
            "claude", "web",
            confirm_handler=make_cli_confirm_handler(print, ask),
            page=page,
            display_size=(1280, 800),
        )
        await run_cli(session)


if __name__ == "__main__":
    asyncio.run(main())
```

```bash
pip install -e ".[web]" && playwright install chromium
python run_web.py
```

Type a request like `search for "anthropic" and click the first result`. The
browser is a separate context, so it won't disturb your own browsing.

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

- **`RuntimeError: build_executor('web') without an injected page ...`** — expected;
  use a launcher script like `run_web.py` above to pass a real `page`.
- **Desktop: connection refused** — the container isn't up or port 8000 isn't
  mapped. Re-check the `docker run -p 8000:8000` step. `DesktopExecutor.do`
  surfaces this as a failed `StepResult`, not a crash.
- **Blank VNC** — give Xvfb a second to start; reconnect the viewer.
- **Provider auth errors** — confirm the right env var
  (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) is exported in the same shell.
