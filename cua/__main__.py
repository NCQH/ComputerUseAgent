"""CLI/GUI entrypoint: select UI, provider, executor and launch."""
from __future__ import annotations

import argparse

from cua.app import build_session
from cua.ui.confirm import auto_approve


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="cua", description="Computer-Use Agent")
    parser.add_argument("--ui", choices=["cli", "gui"], default="cli")
    parser.add_argument("--provider", choices=["claude", "openai"], default="claude")
    parser.add_argument("--executor", choices=["web", "desktop"], default="desktop")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    display_size = (args.width, args.height)

    # Real clients/page/container are constructed lazily by the factories when
    # no injected client is passed. The web executor needs a launched Playwright
    # page; for the desktop executor the factory builds an httpx client.
    session = build_session(
        args.provider,
        args.executor,
        confirm_handler=auto_approve,  # replaced by the UI's interactive handler below
        display_size=display_size,
    )

    if args.ui == "gui":
        from cua.ui.gui import run_gui
        run_gui(session)
    else:
        import asyncio
        from cua.ui.cli import run_cli
        from cua.ui.confirm import make_cli_confirm_handler

        # Bind the confirm handler to stdin so prompts share the terminal.
        async def ask() -> str:
            return await asyncio.get_event_loop().run_in_executor(None, input)

        session.confirm_handler = make_cli_confirm_handler(print, ask)
        asyncio.run(run_cli(session))


if __name__ == "__main__":
    main()
