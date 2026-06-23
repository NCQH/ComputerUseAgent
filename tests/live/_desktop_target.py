"""Controlled desktop click target for the live desktop test.

Shows a large, high-contrast, always-on-top button. On click it writes a sentinel
file (argv[1]) so the test can verify the agent actually hit it — a deterministic
target that avoids the quirks of real OS apps (e.g. Notepad session restore).
Writes '<sentinel>.ready' once shown so the test knows when to start driving.

Usage: python _desktop_target.py <sentinel_path>
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QPushButton

WIDTH, HEIGHT = 1000, 700


def main() -> None:
    sentinel = sys.argv[1]
    app = QApplication(sys.argv)

    button = QPushButton("CLICK ME")
    button.setStyleSheet(
        "background:#22aa22;color:white;font-size:96px;font-weight:bold;"
        "border:14px solid black;")
    button.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
    button.resize(WIDTH, HEIGHT)
    geo = app.primaryScreen().geometry()
    button.move((geo.width() - WIDTH) // 2, (geo.height() - HEIGHT) // 2)

    def on_click() -> None:
        with open(sentinel, "w", encoding="utf-8") as fh:
            fh.write("clicked")
        button.setText("CLICKED")

    button.clicked.connect(on_click)
    button.show()
    button.activateWindow()
    button.raise_()

    def mark_ready() -> None:
        with open(sentinel + ".ready", "w", encoding="utf-8") as fh:
            fh.write("ready")

    QTimer.singleShot(300, mark_ready)
    app.exec()


if __name__ == "__main__":
    main()
