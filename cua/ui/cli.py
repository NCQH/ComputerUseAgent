"""CLI frontend: prompt_toolkit input loop + event log. I/O shell (lazy import)."""
from __future__ import annotations

from cua.ui.format import format_event
from cua.ui.runner import SessionRunner


async def run_cli(session, runner=None) -> None:
    # Lazy import so the package + test suite do not require prompt_toolkit.
    from prompt_toolkit import PromptSession
    from prompt_toolkit.patch_stdout import patch_stdout

    runner = runner or SessionRunner(session)

    def on_event(event) -> None:
        line = format_event(event)
        if line is not None:
            print(line)

    session.bus.subscribe(on_event)

    pt = PromptSession()
    print("CUA CLI — gõ yêu cầu rồi Enter.")
    print("  • Ctrl-C: dừng tác vụ đang chạy (Ctrl-C khi rảnh hoặc Ctrl-D để thoát)")
    print("  • /stop : cũng dừng tác vụ đang chạy")
    with patch_stdout():
        while True:
            try:
                text = await pt.prompt_async("> ")
            except KeyboardInterrupt:
                # Ctrl-C stops a running task; when idle it exits.
                if runner.is_running:
                    print("⏹  Đang dừng…")
                    await runner.stop()
                    continue
                break
            except EOFError:
                break
            text = text.strip()
            if not text:
                continue
            if text.lower() in ("/stop", "/dung", "/dừng"):
                if runner.is_running:
                    print("⏹  Đang dừng…")
                    await runner.stop()
                else:
                    print("(không có tác vụ nào đang chạy)")
                continue
            await runner.submit(text)
    await runner.stop()
    await runner.aclose()
