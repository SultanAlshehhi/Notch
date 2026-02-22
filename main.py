"""
main.py — Entry point for the Notch teleprompter.

  ┌─────────────────────────────────────────────────────────────┐
  │  NOTCH  —  Local, offline teleprompter for your webcam.     │
  │  Reads your voice, scrolls your script.  No cloud. Ever.   │
  └─────────────────────────────────────────────────────────────┘

Usage:
    python main.py

Keyboard shortcuts (while the overlay is focused):
    Space   — Toggle Voice / Manual mode
    +  / =  — Increase font size
    -       — Decrease font size
    R       — Reset scroll to beginning
    Esc     — Close
"""

import sys
import os

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt


def main():
    print("[Notch] Starting...", flush=True)
    # ── High-DPI scaling (Windows 10/11) ─────────────────────────────
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Notch")
    app.setStyle("Fusion")

    # ── Default font ─────────────────────────────────────────────────
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # ── Launch the overlay ───────────────────────────────────────────
    from ui_overlay import NotchOverlay

    print("[Notch] Creating overlay...", flush=True)
    overlay = NotchOverlay()
    print("[Notch] Overlay created, showing...", flush=True)
    overlay.show()
    print("[Notch] Running (load a script and speak in Notch mode)", flush=True)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
