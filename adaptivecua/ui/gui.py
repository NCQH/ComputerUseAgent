# cua/ui/gui.py
"""GUI frontend: PySide6 window + qasync event loop. I/O shell (lazy import)."""
from __future__ import annotations

from adaptivecua.ui.format import format_event
from adaptivecua.ui.runner import SessionRunner


def run_gui(session, build_confirm_handler=None) -> None:
    # Lazy imports so the package + test suite do not require PySide6/qasync.
    import asyncio
    import sys
    import qasync
    from PySide6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
        QPushButton, QMessageBox,
    )

    app = QApplication.instance() or QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = QWidget()
    window.setWindowTitle("CUA")
    layout = QVBoxLayout(window)
    log = QTextEdit()
    log.setReadOnly(True)
    layout.addWidget(log)
    row = QHBoxLayout()
    box = QLineEdit()
    send = QPushButton("Gửi")
    stop = QPushButton("⏹ Dừng")
    stop.setEnabled(False)
    row.addWidget(box)
    row.addWidget(send)
    row.addWidget(stop)
    layout.addLayout(row)

    from adaptivecua.core.events import StateChanged

    def on_event(event) -> None:
        line = format_event(event)
        if line is not None:
            log.append(line)
        # Enable Stop only while a task is actually running.
        if isinstance(event, StateChanged):
            running = event.state == "RUNNING"
            stop.setEnabled(running)

    session.bus.subscribe(on_event)

    # Confirm handler bound to a modal dialog (used if the entrypoint did not
    # supply one). build_confirm_handler(window) lets the entrypoint customize it.
    if build_confirm_handler is not None:
        session.confirm_handler = build_confirm_handler(window)
    else:
        async def _confirm(request) -> bool:
            answer = QMessageBox.question(
                window, "Xác nhận", f"{request.reason}\n\n{request.action}\n\nCho phép?",
            )
            return answer == QMessageBox.StandardButton.Yes
        session.confirm_handler = _confirm

    runner = SessionRunner(session)

    def submit_text() -> None:
        text = box.text().strip()
        if text:
            box.clear()
            asyncio.ensure_future(runner.submit(text))

    def stop_run() -> None:
        log.append("⏹  Đang dừng…")
        asyncio.ensure_future(runner.stop())

    send.clicked.connect(submit_text)
    box.returnPressed.connect(submit_text)
    stop.clicked.connect(stop_run)

    window.resize(900, 600)
    window.show()
    with loop:
        loop.run_forever()
