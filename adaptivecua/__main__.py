"""CLI/GUI entrypoint: select UI, provider, executor and launch."""
from __future__ import annotations

import argparse

from adaptivecua.app import build_session
from adaptivecua.env import load_dotenv
from adaptivecua.ui.confirm import auto_approve


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="adaptivecua", description="Computer-Use Agent")
    parser.add_argument("--ui", choices=["cli", "gui"], default="cli")
    parser.add_argument("--provider",
                        choices=["claude", "openai", "generic", "vision", "browser", "dom",
                                 "a11y", "uia"],
                        default="claude")
    parser.add_argument("--executor", choices=["web", "local", "host"],
                        default="local")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--retries", type=int, default=2,
                        help="retry transient provider errors N times (0 = fail fast)")
    parser.add_argument("--max-runtime", type=float, default=None,
                        help="wall-clock budget in seconds (off by default)")
    parser.add_argument("--max-repeated", type=int, default=None,
                        help="stop after the same action repeats N times (off by default)")
    parser.add_argument("--headed", action="store_true",
                        help="show the browser window for --executor web (default headless)")
    return parser.parse_args(argv)


def _build(args, page=None):
    return build_session(
        args.provider,
        args.executor,
        confirm_handler=auto_approve,  # replaced by the UI's interactive handler below
        page=page,
        display_size=(args.width, args.height),
        provider_retries=args.retries,
        max_runtime_seconds=args.max_runtime,
        max_repeated_actions=args.max_repeated,
    )


async def _run_cli(session) -> None:
    import asyncio

    from adaptivecua.ui.cli import run_cli
    from adaptivecua.ui.confirm import make_cli_confirm_handler

    # Bind the confirm handler to stdin so prompts share the terminal.
    async def ask() -> str:
        return await asyncio.get_running_loop().run_in_executor(None, input)

    session.confirm_handler = make_cli_confirm_handler(print, ask)
    await run_cli(session)


def main(argv=None) -> None:
    # Load .env (if present) so ANTHROPIC_API_KEY / OPENAI_API_KEY are available
    # to the lazily-constructed provider SDK clients. Real env vars take priority.
    load_dotenv()
    args = parse_args(argv)
    is_web = args.executor.strip().lower() == "web"

    if args.provider.strip().lower() in ("browser", "dom") and not is_web:
        raise SystemExit("--provider browser/dom reads the DOM and requires --executor web")

    if args.provider.strip().lower() in ("a11y", "uia") and is_web:
        raise SystemExit("--provider a11y reads the desktop accessibility tree and requires "
                         "--executor local")

    if args.headed and not is_web:
        import sys
        print("[warn] --headed only affects --executor web; ignoring it here", file=sys.stderr)

    # The web executor needs a launched Playwright page, so it owns an async
    # browser lifecycle; the desktop/local executors build their backend lazily.
    if is_web:
        import asyncio

        from adaptivecua.executors.web_launch import BrowserSession

        if args.ui == "gui":
            raise SystemExit("--executor web is currently CLI-only; use --ui cli")

        async def _web_cli() -> None:
            async with BrowserSession(display_size=(args.width, args.height),
                                      headless=not args.headed) as page:
                await _run_cli(_build(args, page=page))

        asyncio.run(_web_cli())
        return

    session = _build(args)
    if args.ui == "gui":
        from adaptivecua.ui.gui import run_gui
        run_gui(session)
    else:
        import asyncio
        asyncio.run(_run_cli(session))


if __name__ == "__main__":
    main()
