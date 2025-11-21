#!/usr/bin/env python3
# Minimal diff viewer.
# Shows a read-only diff between CURRENT and PROPOSED texts.
# Intended to be invoked from other tools.

import sys
from difflib import unified_diff

from PyQt5.QtWidgets import ( # type: ignore
    QApplication, QWidget, QVBoxLayout, QPlainTextEdit, QPushButton, QHBoxLayout, QLabel, QDialog
)
from PyQt5.QtGui import QFont # type: ignore
from PyQt5.QtCore import Qt # type: ignore

from ui_theme import set_qt_env, apply_fusion_dark, center_on_screen

# --- keep strong references to avoid GC when the main app is already running ---
_OPEN_WINDOWS = []

class DiffWindow(QWidget):
    def __init__(self, old_text: str, new_text: str, title: str = "Preview changes"):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(900, 600)

        diff_lines = list(unified_diff(
            old_text.splitlines(keepends=False),
            new_text.splitlines(keepends=False),
            fromfile="CURRENT",
            tofile="PROPOSED",
            lineterm=""
        ))

        info = QLabel("Unified diff. Lines prefixed by '+' were added, '-' removed.")
        info.setStyleSheet("color:#666;")

        view = QPlainTextEdit()
        view.setReadOnly(True)
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.TypeWriter)
        view.setFont(mono)
        view.setPlainText("\n".join(diff_lines))

        btn_close = QPushButton("Continue")
        btn_close.clicked.connect(self.close)

        root = QVBoxLayout(self)
        root.addWidget(info)
        root.addWidget(view)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_close)
        root.addLayout(row)

class TextWindow(QWidget):
    
    def __init__(self, text: str, title: str = "Preview"):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(900, 600)

        info = QLabel("Read-only preview of the proposed file content.")
        info.setStyleSheet("color:#666;")

        view = QPlainTextEdit()
        view.setReadOnly(True)
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.TypeWriter)
        view.setFont(mono)
        view.setPlainText(text)

        btn_close = QPushButton("Continue")
        btn_close.clicked.connect(self.close)

        root = QVBoxLayout(self)
        root.addWidget(info)
        root.addWidget(view)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_close)
        root.addLayout(row)

def _show_and_pin_window(w: QWidget):
    """Show window, center it, raise it, and keep a global ref to prevent GC."""
    center_on_screen(w)
    w.show()
    # bring to front
    w.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    w.show()  # re-apply flags
    w.raise_()
    w.activateWindow()
    # keep strong ref
    _OPEN_WINDOWS.append(w)
    # when closed, drop the ref
    def _on_close():
        try:
            _OPEN_WINDOWS.remove(w)
        except ValueError:
            pass
    w.destroyed.connect(lambda _=None: _on_close())

def show_diff_dialog(old_text: str, new_text: str, title: str = "Preview changes"):
    app = QApplication.instance()
    created = False
    if app is None:
        set_qt_env()  # ensure platform/env before QApplication
        # --- ONLY CHANGE: force software OpenGL before creating QApplication ---
        QApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)
        app = QApplication(sys.argv)
        apply_fusion_dark(app)
        created = True
    w = DiffWindow(old_text, new_text, title=title)
    _show_and_pin_window(w)
    if created:
        app.exec_()

# simple text preview 
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QPushButton # type: ignore

def show_text_dialog(text: str, title: str = "Preview") -> QDialog:
    dlg = QDialog()
    dlg.setWindowTitle(title)
    lay = QVBoxLayout(dlg)
    edit = QPlainTextEdit()
    edit.setReadOnly(True)
    edit.setPlainText(text)
    lay.addWidget(edit)
    btn = QPushButton("Continue")
    btn.clicked.connect(dlg.close)
    lay.addWidget(btn)
    dlg.resize(800, 600)
    dlg.show()
    return dlg

if __name__ == "__main__":
    # Simple smoke tests
    set_qt_env()  # ensure platform/env before QApplication
    # --- force software OpenGL before creating QApplication ---
    QApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)
    app = QApplication(sys.argv)
    apply_fusion_dark(app)
    a = "line1\nline2\nline3\n"
    b = "line1\nline2-mod\nline3\n+extra\n"
    # show_diff_dialog(a, b, "Preview changes")
    show_text_dialog(b, "Preview (proposed)")
