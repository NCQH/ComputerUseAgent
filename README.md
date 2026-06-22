# ComputerUseAgent (CUA)

A Computer-Use Agent: it takes natural-language requests, drives a computer or a
browser to carry them out, lets you **inject new instructions in real time while
it works**, and **stops to ask before any irreversible action**.

It is provider-agnostic (Claude or OpenAI computer-use) and has two execution
backends — a **web** workflow (Playwright) and a **desktop** workflow (pyautogui
inside a Docker + VNC sandbox) — behind one clean interface.

## Highlights

- **Real-time steering.** Type a new instruction any time; the agent picks it up
  at the next step boundary (never mid-action) and resumes after it goes idle.
- **Two-layer safety gate.** A hard denylist *plus* the model's own risk flag force
  a confirmation prompt before irreversible actions. Default-deny: anything that
  isn't an explicit "yes" is rejected.
- **Multi-provider brain.** Claude (`computer_20250124`) and OpenAI
  (`computer_use_preview`) behind one `CUAProvider` interface — pick with a flag.
- **Two execution backends.** Web (Playwright) and Desktop (Docker + VNC sandbox)
  behind one `Executor` interface.
- **Two frontends, one core.** A CLI (prompt_toolkit) and a desktop GUI
  (PySide6) share the same `AgentSession`.
- **Offline-testable.** 118 tests run with no API key, browser, Docker, or GUI
  toolkit installed — every backend is injected and the pure logic is isolated.

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
│   └── openai.py     OpenAI computer use       (+ openai_translate.py)
├── executors/    The "hands": perform a neutral action, return a screenshot
│   ├── base.py       Executor interface
│   ├── web.py        Playwright                (+ web_translate.py)
│   └── desktop.py    Docker+VNC sandbox        (+ desktop_translate.py)
├── ui/           Frontends
│   ├── format.py     Pure event -> log line
│   ├── confirm.py    Confirmation handlers (default-deny)
│   ├── runner.py     SessionRunner — run-loop lifecycle + idle-restart
│   ├── cli.py        CLI shell (prompt_toolkit, lazy)
│   └── gui.py        GUI shell (PySide6 + qasync, lazy)
├── app.py        build_session — wires provider+executor+gate+bus+queue
├── config.py     build_provider / build_executor factories (lazy SDKs)
└── __main__.py   Entrypoint: python -m cua --ui ... --provider ... --executor ...
docker/desktop/   Sandbox image: Xvfb + x11vnc + pyautogui HTTP agent
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
  - Docker — desktop executor sandbox
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
pip install -e ".[desktop]"   # httpx (HTTP client for the sandbox)
pip install anthropic openai  # provider SDKs (choose what you use)
```

## Run the tests

```bash
python -m pytest -q          # 118 passed, fully offline
```

## Run the app

Set the API key for your chosen provider, then launch:

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # or OPENAI_API_KEY=sk-...

# CLI against the desktop sandbox (default ui=cli, executor=desktop, provider=claude)
python -m cua

# GUI against the desktop sandbox, with OpenAI
python -m cua --ui gui --provider openai --executor desktop

# custom virtual display size
python -m cua --executor desktop --width 1280 --height 800
```

Flags: `--ui {cli,gui}` · `--provider {claude,openai}` · `--executor {web,desktop}`
· `--width` · `--height`.

> The **desktop** executor needs the sandbox container running, and the **web**
> executor needs a launched Playwright page wired in by the caller. See
> [docs/RUNNING.md](docs/RUNNING.md) for the end-to-end smoke test.

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
