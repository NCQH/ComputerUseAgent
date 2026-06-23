# ComputerUseAgent (CUA)

A Computer-Use Agent: it takes natural-language requests, drives a computer or a
browser to carry them out, lets you **inject new instructions in real time while
it works**, and **stops to ask before any irreversible action**.

It is provider-agnostic (Claude computer-use, OpenAI computer-use, or any vision
chat model via Set-of-Marks) and has two execution backends — a **web** workflow
(Playwright) and a **local** workflow (pyautogui on the real host desktop) — behind
one clean interface.

## Highlights

- **Real-time steering.** Type a new instruction any time; the agent picks it up
  at the next step boundary (never mid-action) and resumes after it goes idle.
- **Two-layer safety gate.** A hard denylist *plus* the model's own risk flag force
  a confirmation prompt before irreversible actions. Default-deny: anything that
  isn't an explicit "yes" is rejected.
- **Multi-provider brain.** Claude (`computer_20250124`), OpenAI
  (`computer_use_preview`), a **generic vision** provider (OCR/grid Set-of-Marks
  on any vision chat model), and a **DOM browser** provider that reads the page's
  interactive elements straight from the DOM and lets the model pick by index
  (the browser_use technique) — behind one `CUAProvider` interface, pick with a flag.
- **Two execution backends.** Web (Playwright) and Local (real host desktop via
  pyautogui) behind one `Executor` interface.
- **Two frontends, one core.** A CLI (prompt_toolkit) and a desktop GUI
  (PySide6) share the same `AgentSession`.
- **Offline-testable.** 181 tests run with no API key, browser, or GUI toolkit
  installed — every backend is injected and the pure logic is isolated.

## Architecture

```
cua/
├── core/         Agent loop + steering + safety (provider/executor/UI-agnostic)
│   ├── session.py    AgentSession — the async orchestration loop
│   ├── queue.py      InputQueue — non-blocking real-time steering
│   ├── events.py     EventBus + event types
│   ├── history.py    Conversation/action history fed to the model
│   └── safety.py     IrreversibilityGate — denylist + model risk flag
├── providers/    The "brain": screenshot + history -> neutral actions
│   ├── base.py       CUAProvider interface
│   ├── anthropic.py  Claude computer use      (+ anthropic_translate.py)
│   ├── openai.py     OpenAI computer use       (+ openai_translate.py)
│   ├── vision/       GenericVisionProvider — OCR/grid Set-of-Marks, any vision model
│   └── browser/      DomVisionProvider — DOM Set-of-Marks (browser_use-style)
├── executors/    The "hands": perform a neutral action, return a screenshot
│   ├── base.py          Executor interface
│   ├── web.py           Playwright            (+ web_translate.py, web_launch.py)
│   └── local.py         Real host desktop via pyautogui (+ action_payload.py)
├── ui/           Frontends
│   ├── format.py     Pure event -> log line
│   ├── confirm.py    Confirmation handlers (default-deny)
│   ├── runner.py     SessionRunner — run-loop lifecycle + idle-restart
│   ├── cli.py        CLI shell (prompt_toolkit, lazy)
│   └── gui.py        GUI shell (PySide6 + qasync, lazy)
├── app.py        build_session — wires provider+executor+gate+bus+queue
├── config.py     build_provider / build_executor factories (lazy SDKs)
└── __main__.py   Entrypoint: python -m cua --ui ... --provider ... --executor ...
```

**Neutral action vocabulary** (`cua/models.py`) is the contract between brain and
hands: `Click`, `DoubleClick`, `TripleClick`, `Move`, `Type`, `Key`, `Scroll`,
`Drag`, `Wait`, `Screenshot`. Each provider translates the vendor format to it;
each executor translates it to the backend API. Swap either side independently.

## Requirements

- Python **3.11+**
- Optional, per backend/frontend (installed via extras below):
  - `anthropic` and/or `openai` — the model provider SDK
  - `playwright` — web executor
  - `pyautogui`, `Pillow` — local (real host desktop) executor
  - `prompt_toolkit`, `PySide6`, `qasync` — UIs

## Install

```bash
git clone https://github.com/NCQH/ComputerUseAgent.git
cd ComputerUseAgent
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate

# core only (enough to run the test suite)
pip install -e .

# with extras you actually need:
pip install -e ".[test]"      # pytest + pytest-asyncio
pip install -e ".[ui]"        # prompt_toolkit + PySide6 + qasync
pip install -e ".[web]"       # playwright   (then: playwright install chromium)
pip install -e ".[local]"     # pyautogui + Pillow (real host desktop)
pip install -e ".[vision]"    # generic vision provider (openai + Pillow + pytesseract)
pip install anthropic openai  # provider SDKs (choose what you use)
```

## Run the tests

```bash
python -m pytest -q          # 181 passed, 2 skipped (live), fully offline
```

## Run the app

Provide the API key for your chosen provider. Either export it, or copy
`.env.example` to `.env` and fill it in (`.env` is gitignored; real environment
variables take priority over it):

```bash
cp .env.example .env && $EDITOR .env     # ANTHROPIC_API_KEY / OPENAI_API_KEY
# or just:
export ANTHROPIC_API_KEY=sk-ant-...      # or OPENAI_API_KEY=sk-...

# CLI on the real host desktop (default ui=cli, executor=local, provider=claude)
python -m cua

# DOM Set-of-Marks (browser_use-style) driving a headless browser
python -m cua --provider browser --executor web

# generic vision model, show the browser window, cap a runaway run
python -m cua --provider generic --executor web --headed --max-runtime 120
```

Flags: `--ui {cli,gui}` · `--provider {claude,openai,generic,vision,browser,dom}` ·
`--executor {web,local,host}` · `--width` · `--height` · `--headed` ·
`--retries` · `--max-runtime` · `--max-repeated`.

> `--provider browser` reads the DOM and so requires `--executor web`.

> The **local** executor drives your real desktop — watch it, and keep a hand near
> the corner-abort. `--executor web` self-launches a headless Chromium page. See
> [docs/RUNNING.md](docs/RUNNING.md) for the end-to-end guide.

## How steering and safety work

- **Steering:** you `submit()` a request at any time; it lands in an `asyncio`
  queue. The agent loop drains the queue at the top of each step, so new
  instructions merge in between actions, never interrupting one. When the agent
  finishes and goes idle, the next submission restarts the loop.
- **Safety:** before every action, `IrreversibilityGate` checks a denylist
  (submit / delete / buy / pay / send / … and destructive key combos) and the
  provider's own risk flag. A hit pauses the session in `WAITING_CONFIRM` and
  asks you; rejection skips the action and tells the model to change course.

## License

See the repository for license terms.
