#!/usr/bin/env python3
# snappyHexMesh Log Monitor — live tail + counters 

import sys, re, io, os, time
from pathlib import Path
from typing import Optional, TextIO

from PyQt5.QtWidgets import (  # type: ignore
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QCheckBox, QFrame
)
from PyQt5.QtCore import Qt, QTimer  # type: ignore


try:
    from ui_theme import set_qt_env, apply_fusion_dark, center_on_screen   # type: ignore
except Exception:
    def set_qt_env(): pass
    def apply_fusion_dark(app): pass
    def center_on_screen(w): pass

# Warnings/Errors
RX_WARNING = re.compile(r'(?im)^\s*(FOAM\s+Warning|Warning:)\b')
RX_ERROR   = re.compile(r'(?im)^\s*(FOAM\s+FATAL\s+ERROR|Segmentation fault|Floating point exception)\b')


class LogTail:
    def __init__(self, path: Path):
        self.path = path
        self.fp: Optional[TextIO] = None
        self.pos = 0

    def open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fp = open(self.path, "a+", buffering=1, encoding="utf-8", errors="ignore")
        self.fp.seek(0, io.SEEK_END)
        self.pos = self.fp.tell()

    def read_new(self) -> str:
        if not self.fp:
            return ""
        self.fp.seek(self.pos)
        data = self.fp.read()
        self.pos = self.fp.tell()
        return data

    def close(self):
        try:
            if self.fp: self.fp.close()
        except Exception:
            pass
        self.fp = None


class Monitor(QWidget):
    def __init__(self, log_path: Path, dict_path: Optional[Path]):  # dict_path kept for compatibility (unused)
        super().__init__()
        self.log_path = log_path

        self.tail = LogTail(self.log_path)
        self.warning_count = 0
        self.error_count = 0

        self.setWindowTitle("snappyHexMesh Log Monitor")
        self.resize(980, 600)

        # Header row: "Log: <path>   [Open log...]   [Auto-scroll]"
        hdr = QHBoxLayout()
        lab = QLabel("Log:")
        self.lab_path = QLabel(str(self.log_path))
        self.lab_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        hdr.addWidget(lab)
        hdr.addWidget(self.lab_path, 1)
        self.chk_autoscroll = QCheckBox("Auto-scroll")
        self.chk_autoscroll.setChecked(True)
        self.btn_open = QPushButton("Open log…")
        self.btn_open.clicked.connect(self.open_external)
        hdr.addWidget(self.chk_autoscroll)
        hdr.addWidget(self.btn_open)

        # Counters
        counters = QHBoxLayout()
        self.lab_warn = QLabel("Warnings: 0")
        self.lab_err  = QLabel("Errors: 0")
        self.lab_warn.setStyleSheet("color:#e1c542; font-weight:600;")
        self.lab_err.setStyleSheet("color:#d73a49; font-weight:700;")
        counters.addWidget(self.lab_warn); counters.addWidget(self.lab_err); counters.addStretch(1)

        # Log view
        self.view = QPlainTextEdit(readOnly=True)
        self.view.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)

        root = QVBoxLayout(self)
        root.addLayout(hdr)
        root.addLayout(counters)
        root.addWidget(self.view, 1)

        # Start tail
        self.tail.open()
        self.timer = QTimer(self)
        self.timer.setInterval(200)   # 5 Hz
        self.timer.timeout.connect(self.on_tick)
        self.timer.start()
        center_on_screen(self)

    # --- helpers ---
    def open_external(self):
        
        try:
            import subprocess
            subprocess.Popen(["xdg-open", str(self.log_path)])
        except Exception:
            pass

    def _append_text(self, txt: str):
        if not txt:
            return
        self.view.appendPlainText(txt)
        if self.chk_autoscroll.isChecked():
            self.view.moveCursor(self.view.textCursor().End)

    def _bump_counts(self, chunk: str):
        self.warning_count += len(RX_WARNING.findall(chunk))
        self.error_count   += len(RX_ERROR.findall(chunk))
        self.lab_warn.setText(f"Warnings: {self.warning_count}")
        self.lab_err.setText(f"Errors: {self.error_count}")

    # --- timer ---
    def on_tick(self):
        chunk = self.tail.read_new()
        if not chunk:
            return
        self._append_text(chunk)
        self._bump_counts(chunk)


def main():
    set_qt_env()
    app = QApplication(sys.argv)
    apply_fusion_dark(app)

    # Defaults: log at case/logs/log_snappyHexMesh.txt, dict at case/system/snappyHexMeshDict 
    case_dir = Path.cwd() / "case"
    log_path = case_dir / "logs" / "log_snappyHexMesh.txt"
    dict_path: Optional[Path] = case_dir / "system" / "snappyHexMeshDict"

    # Allow overriding via argv[1] (log) and argv[2] 
    if len(sys.argv) > 1:
        log_path = Path(sys.argv[1]).expanduser()
    if len(sys.argv) > 2:
        dict_path = Path(sys.argv[2]).expanduser()

    w = Monitor(log_path, dict_path)
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
