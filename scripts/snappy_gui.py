#!/usr/bin/env python3
# Minimal editor for the top-level booleans in snappyHexMeshDict:
# castellatedMesh, snap, addLayers. Autoloads from CASE/system/snappyHexMeshDict.

import sys
import re
from pathlib import Path

from PyQt5.QtWidgets import (  # type: ignore
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QCheckBox, QPushButton, QMessageBox
)
from PyQt5.QtCore import Qt  # type: ignore

from ui_theme import set_qt_env, apply_fusion_dark, center_on_screen

# Default checkboxes state
DEFAULTS = dict(castellated=True, snap=True, layers=True)

def _set_bool_line(text: str, key: str, value: bool) -> str:
    """
    Replace exactly one line:
        <key> true;
    or    <key> false;
    anchored at start of line.
    """
    pat = re.compile(rf"(^\s*{key}\s+)(true|false)(\s*;)", flags=re.MULTILINE)
    if pat.search(text):
        return pat.sub(rf"\1{'true' if value else 'false'}\3", text, count=1)
    
    pat2 = re.compile(rf"(^\s*{key}\s+)(true|false)(\s*)$", flags=re.MULTILINE)
    if pat2.search(text):
        return pat2.sub(rf"\1{'true' if value else 'false'};", text, count=1)
    
    return text

class SnappyGui(QWidget):
    """
    Minimal editor for snappyHexMeshDict: castellatedMesh, snap, addLayers.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SnappyHexMeshDict Editor")
        self.resize(560, 420)

        self.case_dir = Path.cwd()
        self.dict_path = self.case_dir / "system" / "snappyHexMeshDict"
        self.current_text = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        self.gb_cast, self.cb_cast = self._make_section(
            "Castellated",
            "Enable castellatedMesh",
            "Cuts the base mesh by the STL surface and generates cells around the geometry.",
            "Primary phase that creates topology by 'casting' the mesh with the surface."
        )
        self.gb_snap, self.cb_snap = self._make_section(
            "Snap",
            "Enable snap",
            "Moves mesh vertices onto the STL surface to improve accuracy.",
            "Vertex snapping onto the surface (usually recommended)."
        )
        self.gb_layers, self.cb_layers = self._make_section(
            "Layers",
            "Enable addLayers",
            "Inflates layers along the surface for boundary-layer resolution.",
            "Requires valid addLayersControls; can increase cell count."
        )

        root.addWidget(self.gb_cast)
        root.addWidget(self.gb_snap)
        root.addWidget(self.gb_layers)

        self.status_lbl = QLabel("")
        root.addWidget(self.status_lbl)

        btn_row = QHBoxLayout()
        self.btn_reset = QPushButton("Reset to defaults")
        self.btn_apply = QPushButton("Apply")  
        self.btn_close = QPushButton("Continue") 
        btn_row.addWidget(self.btn_close)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_reset)
        btn_row.addWidget(self.btn_apply)
        root.addLayout(btn_row)

        self.btn_reset.setToolTip("Restore the default choices (castellated=ON, snap=ON, layers=ON).")
        self.btn_apply.setToolTip("Write changes to snappyHexMeshDict.")

        self.btn_reset.clicked.connect(self._reset_defaults)
        self.btn_apply.clicked.connect(self._apply_without_closing)  
        self.btn_close.clicked.connect(self.close)  

        center_on_screen(self)
        self._reset_defaults()
        self._load_from_case()

    def _make_section(self, title: str, chk_text: str, desc: str, tip: str):
        box = QGroupBox(title)
        lay = QVBoxLayout(box)
        chk = QCheckBox(chk_text)
        chk.setToolTip(tip)
        lbl = QLabel(desc)
        lbl.setWordWrap(True)
        lbl.setObjectName("hint")
        lay.addWidget(chk)
        lay.addWidget(lbl)
        return box, chk

    def _reset_defaults(self):
        self.cb_cast.setChecked(DEFAULTS["castellated"])
        self.cb_snap.setChecked(DEFAULTS["snap"])
        self.cb_layers.setChecked(DEFAULTS["layers"])

    def _load_from_case(self):
        if not self.dict_path.exists():
            QMessageBox.critical(self, "Error", f"snappyHexMeshDict not found:\n{self.dict_path}")
            return
        self.current_text = self.dict_path.read_text()
        def get_bool(key: str, fallback: bool) -> bool:
            m = re.search(rf"^\s*{key}\s+(true|false)\s*;", self.current_text, flags=re.MULTILINE)
            return (m.group(1) == "true") if m else fallback
        self.cb_cast.setChecked(get_bool("castellatedMesh", self.cb_cast.isChecked()))
        self.cb_snap.setChecked(get_bool("snap", self.cb_snap.isChecked()))
        self.cb_layers.setChecked(get_bool("addLayers", self.cb_layers.isChecked()))
        self.status_lbl.setText(f"Loaded: {self.dict_path}")

    def _apply_without_closing(self):
        if not self.current_text:
            QMessageBox.warning(self, "Warning", "Nothing to save — file not loaded.")
            return
        text = self.current_text
        text = _set_bool_line(text, "castellatedMesh", self.cb_cast.isChecked())
        text = _set_bool_line(text, "snap", self.cb_snap.isChecked())
        text = _set_bool_line(text, "addLayers", self.cb_layers.isChecked())
        self.dict_path.write_text(text)
        # Update in-memory copy so repeated Apply starts from latest content
        self.current_text = text
        QMessageBox.information(self, "Saved", f"Updated:\n{self.dict_path}")
        

if __name__ == "__main__":
    set_qt_env()
    app = QApplication(sys.argv)
    apply_fusion_dark(app)
    gui = SnappyGui()
    gui.show()
    sys.exit(app.exec_())
