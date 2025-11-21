#!/usr/bin/env python3
"""
sanity_check.py
GUI to run a sanity check on STL files under constant/triSurface:
- Lists *.stl files (supports multiple files).
- Runs `surfaceCheck` for each file and parses key metrics:
  open-edges, non-manifold edges, face count, bounding box.
- Shows: OK / Warning / Error with simple rules:
    Error   if open-edges > 0 or non-manifold > 0
    Warning if 0 errors but "warning" appears in the log
    OK      otherwise
- Saves logs under <case>/logs/surfaceCheck_<name>.log and provides "Open log".
- Uses dark Fusion palette and centers the window (via ui_theme.py).

Requires: PyQt5, Python 3; OpenFOAM utility `surfaceCheck` in PATH.
Docs: surfaceCheck manual & API (openfoam.com / cpp.openfoam.org).
"""

import os, sys, re, subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt5.QtWidgets import ( # type: ignore
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt, QTimer # type: ignore


from ui_theme import set_qt_env, apply_fusion_dark, center_on_screen

CASE_DIR = Path.cwd()
TRI_DIR  = CASE_DIR / "constant" / "triSurface"
LOG_DIR  = CASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

COLS = ["STL file", "Open-edges", "Non-manifold", "Faces", "BBox [xmin xmax; ymin ymax; zmin zmax]", "Verdict", "Log"]

OPEN_PATTERNS = [
    r"open\s+edges\s*[:=]\s*(\d+)",
    r"Number\s+of\s+open\s+edges\s*[:=]\s*(\d+)",
]
NONMAN_PATTERNS = [
    r"non[- ]?manifold\s+edges\s*[:=]\s*(\d+)",
    r"Number\s+of\s+non[- ]?manifold\s+edges\s*[:=]\s*(\d+)",
]
FACES_PATTERNS = [
    r"(faces|triangles)\s*[:=]\s*(\d+)"
]
BBOX_PATTERNS = [
    r"bbox\s*[:=]\s*\(\s*([\-0-9.eE+]+)\s+([\-0-9.eE+]+)\s+([\-0-9.eE+]+)\s*\)\s*-\s*\(\s*([\-0-9.eE+]+)\s+([\-0-9.eE+]+)\s+([\-0-9.eE+]+)\s*\)"
]

def run_surface_check(stl: Path, log_path: Path) -> str:
    cmd = ["surfaceCheck", str(stl)]
    try:
        out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        log_path.write_text(out.stdout or "")
        return out.stdout or ""
    except FileNotFoundError:
        return f"[ERROR] surfaceCheck not found in PATH.\n"
    except Exception as e:
        return f"[ERROR] Failed to run surfaceCheck: {e}\n"

def rex_first(text: str, patterns: List[str], group_idx: int = -1) -> Optional[str]:
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(group_idx if group_idx > 0 else (m.lastindex or 1))
    return None

def parse_metrics(log_txt: str) -> Tuple[int, int, Optional[int], Optional[str], bool]:
    open_edges = int(rex_first(log_txt, OPEN_PATTERNS) or 0)
    nonman     = int(rex_first(log_txt, NONMAN_PATTERNS) or 0)
    faces_s    = rex_first(log_txt, FACES_PATTERNS, 2) or rex_first(log_txt, FACES_PATTERNS, 1)
    faces      = int(faces_s) if faces_s and faces_s.isdigit() else None
    bbox_m     = re.search(BBOX_PATTERNS[0], log_txt, re.IGNORECASE)
    bbox       = None
    if bbox_m:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox_m.group(1,2,3,4,5,6)
        bbox = f"[{xmin} {xmax}; {ymin} {ymax}; {zmin} {zmax}]"
    has_warn   = bool(re.search(r"\bwarn(ing)?\b", log_txt, re.IGNORECASE))
    return open_edges, nonman, faces, bbox, has_warn

def verdict(open_e: int, nonman: int, has_warn: bool) -> str:
    if open_e > 0 or nonman > 0:
        return "Error"
    return "Warning" if has_warn else "OK"

class SanityGui(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sanity Check (surfaceCheck) — triSurface")
        self.resize(960, 520)

        root = QVBoxLayout(self)
        info = QLabel(f"Case: {CASE_DIR}\nSTL folder: {TRI_DIR}")
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(info)

        # Results table group
        g = QGroupBox("Results")
        gl = QVBoxLayout(g)
        self.tbl = QTableWidget(0, len(COLS))
        self.tbl.setHorizontalHeaderLabels(COLS)
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(COLS)-1):
            self.tbl.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.tbl.verticalHeader().setVisible(False)
        gl.addWidget(self.tbl)
        root.addWidget(g)

        
        btn_row = QHBoxLayout()
        self.btn_scan = QPushButton("Scan triSurface for STL")
        self.btn_add  = QPushButton("Add STL…")
        self.btn_run  = QPushButton("Run surfaceCheck")
        self.btn_close = QPushButton("Continue")
        btn_row.addWidget(self.btn_close)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_scan)
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_run)
        root.addLayout(btn_row)
        

        self.btn_scan.clicked.connect(self.on_scan)
        self.btn_add.clicked.connect(self.on_add)
        self.btn_run.clicked.connect(self.on_run)
        self.btn_close.clicked.connect(self.close)

        center_on_screen(self)
        QTimer.singleShot(100, self.on_scan)

    def on_scan(self):
        self.tbl.setRowCount(0)
        if not TRI_DIR.exists():
            QMessageBox.information(self, "Folder missing", f"Folder not found:\n{TRI_DIR}")
            return
        for stl in sorted(TRI_DIR.glob("*.stl")):
            self._add_row(stl)

    def on_add(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select STL", str(TRI_DIR), "STL files (*.stl);;All files (*)")
        if path:
            self._add_row(Path(path))

    def _add_row(self, stl: Path):
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        # Show only the basename in the table; full path in tooltip
        item = QTableWidgetItem(Path(stl).name)
        item.setToolTip(str(stl))
        self.tbl.setItem(r, 0, item)
        for c in range(1, len(COLS)-1):
            self.tbl.setItem(r, c, QTableWidgetItem(""))
        btn = QPushButton("Open log")
        btn.setEnabled(False)
        btn.clicked.connect(lambda _, row=r: self._open_log(row))
        self.tbl.setCellWidget(r, len(COLS)-1, btn)

    def _open_log(self, row: int):
        item = self.tbl.item(row, 0)
        if not item: return
        full_path = item.toolTip() or item.text()
        stl = Path(full_path)
        log_path = LOG_DIR / f"surfaceCheck_{stl.stem}.log"
        if not log_path.exists():
            QMessageBox.information(self, "Log not found", str(log_path))
            return
        os.system(f'xdg-open "{log_path}" >/dev/null 2>&1 &')

    def on_run(self):
        n = self.tbl.rowCount()
        if n == 0:
            QMessageBox.information(self, "No STL", "No STL files listed.")
            return
        for r in range(n):
            cell = self.tbl.item(r, 0)
            stl_path = cell.toolTip() or cell.text()
            stl = Path(stl_path)
            log_path = LOG_DIR / f"surfaceCheck_{stl.stem}.log"
            out = run_surface_check(stl, log_path)
            open_e, nonman, faces, bbox, has_warn = parse_metrics(out)
            self.tbl.setItem(r, 1, QTableWidgetItem(str(open_e)))
            self.tbl.setItem(r, 2, QTableWidgetItem(str(nonman)))
            self.tbl.setItem(r, 3, QTableWidgetItem(str(faces) if faces is not None else "—"))
            self.tbl.setItem(r, 4, QTableWidgetItem(bbox or "—"))
            ver = verdict(open_e, nonman, has_warn)
            itv = QTableWidgetItem(ver)
            color = {"OK":"#2aa198", "Warning":"#b58900", "Error":"#dc322f"}[ver]
            itv.setBackground(Qt.black)
            itv.setForeground(Qt.white)
            itv.setData(Qt.UserRole, ver)
            self.tbl.setItem(r, 5, itv)
            btn = self.tbl.cellWidget(r, len(COLS)-1)
            if isinstance(btn, QPushButton):
                btn.setEnabled(True)

def main():
    set_qt_env()  
    app = QApplication(sys.argv)
    apply_fusion_dark(app)
    w = SanityGui()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
