#!/usr/bin/env python3
# layers_widget.py
# GUI to configure addLayers and write addLayersControls{} in snappyHexMeshDict.

import sys, re, argparse, os
from pathlib import Path
from typing import Dict, Tuple, List, Optional, Any

from PyQt5.QtWidgets import ( # type: ignore
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QSpinBox, QDoubleSpinBox, QPushButton, QCheckBox, QGroupBox, QMessageBox,
    QDialog, QDialogButtonBox, QTextEdit
)
from PyQt5.QtCore import Qt # type: ignore
from PyQt5.QtGui import QFont  # type: ignore

# Shared theme utilities
from ui_theme import set_qt_env, apply_fusion_dark, center_on_screen

def detect_repo_root(cli_root: Optional[Path]) -> Path:
    if cli_root and cli_root.exists():
        return cli_root.resolve()
    env = os.environ.get("MESHGUI_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        if p.exists():
            return p
    start = Path(__file__).resolve().parent
    for cand in [start, *start.parents]:
        if (cand / "mesh").is_dir() and (cand / "templateCase").is_dir():
            return cand
    return Path.cwd().resolve()

# (used only as fallback when NOT in the case/)
def fallback_snappy_path(repo_root: Path) -> Path:
    return (repo_root / "mesh" / "snappyHexMeshDict").resolve()

HEADER_BANNER = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2406                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/"""
FOOTER_LINE = "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //"

def foam_header(object_name: str, location: str = "system") -> str:
    return (
        f"{HEADER_BANNER}\n"
        "FoamFile\n"
        "{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        "    class       dictionary;\n"
        f"    location    \"{location}\";\n"
        f"    object      {object_name};\n"
        "}\n"
        f"{FOOTER_LINE}\n"
    )

def ensure_header(text: str, object_name: str) -> str:
    if "FoamFile" in text and "object" in text:
        return text
    return foam_header(object_name) + "\n" + text.lstrip()

def find_block_span(text: str, key: str) -> Tuple[int, int]:
    pat = re.compile(r'(^|\s)'+re.escape(key)+r'\s*\{', re.MULTILINE)
    m = pat.search(text)
    if not m: return (-1, -1)
    i = text.find('{', m.end()-1)
    if i < 0: return (-1, -1)
    depth, j = 1, i+1
    while j < len(text) and depth > 0:
        c = text[j]
        if c == '{': depth += 1
        elif c == '}': depth -= 1
        j += 1
    return (m.start(), j)

def upsert_boolean_switch(text: str, key: str, value: bool) -> str:
    m = re.search(rf'^\s*{re.escape(key)}\s+(true|false)\s*;\s*$', text, re.MULTILINE)
    if m:
        return text[:m.start()] + re.sub(r'(true|false)', 'true' if value else 'false', text[m.start():m.end()], 1) + text[m.end():]
    anchor = re.search(r'^\s*(castellatedMesh|snap|addLayers)\s+(true|false)\s*;\s*$', text, re.MULTILINE)
    ins = f"\n{key:16s} {'true' if value else 'false'};\n"
    if anchor:
        pos = anchor.end()
        return text[:pos] + ins + text[pos:]
    return ins + text

def render_addLayersControls(g_layers: int,
                             g_expansion: Optional[float],
                             g_finalThick: Optional[float],
                             g_minThickness: Optional[float],
                             g_featureAngle: Optional[float],
                             g_nGrow: Optional[int],
                             relative_sizes: bool) -> str:
    lines: List[str] = []
    lines += ["addLayersControls", "{"]
    lines += ["    // Layer addition controls (relative, fractions of local cell size)"]
    lines += [f"    relativeSizes       {'true' if relative_sizes else 'false'};"]
    if g_expansion       is not None: lines += [f"    expansionRatio      {float(g_expansion)};"]
    if g_finalThick      is not None: lines += [f"    finalLayerThickness {float(g_finalThick)};"]
    if g_minThickness    is not None: lines += [f"    minThickness        {float(g_minThickness)};"]
    if g_featureAngle    is not None: lines += [f"    featureAngle        {float(g_featureAngle)};"]
    if g_nGrow           is not None: lines += [f"    nGrow               {int(g_nGrow)};"]
    lines += [f"    maxFaceThicknessRatio 0.5;"]
    lines += [f"    nSmoothSurfaceNormals 1;"]
    lines += [f"    nSmoothThickness    10;"]
    lines += [f"    maxThicknessToMedialRatio 0.3;"]
    lines += [f"    nSmoothNormals      3;"]
    lines += [f"    nLayerIter          50;"]
    lines += [f"    nRelaxedIter        20;"]
    lines += [f"    nBufferCellsNoExtrude 0;"]
    lines += ["",
              "    layers",
              "    {",
              '        "(placeholder).*"',
              "        {",
              f"            nSurfaceLayers {int(g_layers)};",
              "        }",
              "    }",
              "    // Optional: expansionRatio, minThickness, featureAngle, nGrow, etc.",
              "    slipFeatureAngle 30;",
              "    nRelaxIter 3;",
              "    minMedialAxisAngle 90;"
              ]
    lines += ["}"]
    return "\n".join(lines) + "\n"

class SaveGateMixin:
    
    def _init_save_gate(self, edit_widgets):
        try:
            self.btn_close.setEnabled(True) 
        except Exception:
            pass
        

    def markSaved(self):
        # No-op, kept for API compatibility.
        try:
            self.btn_close.setEnabled(True)
        except Exception:
            pass

class LayersGui(QWidget, SaveGateMixin):
    def __init__(self, dict_path: Path):
        super().__init__()
        self.dict_path = dict_path
        self.setWindowTitle("Layers: nSurfaceLayers + advanced options")
        self.resize(900, 520)

        root = QVBoxLayout(self)
        info = QLabel(f"snappyHexMeshDict: {self.dict_path}")
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(info)

        gbox = QGroupBox("Global settings")
        gl = QGridLayout(gbox)

        self.chk_enable = QCheckBox("Enable layers (addLayers=true)")
        self.chk_enable.setChecked(True)
        gl.addWidget(self.chk_enable, 0, 0, 1, 3)

        gl.addWidget(QLabel("relativeSizes:"), 1, 0)
        self.btn_relative = QPushButton("true")
        self.btn_relative.setCheckable(True)
        self.btn_relative.setChecked(True)
        self.btn_relative.setToolTip("Toggle relativeSizes between true/false.")
        self.btn_relative.clicked.connect(self._toggle_relative)
        self.btn_help = QPushButton("?")
        self.btn_help.setFixedWidth(24)
        self.btn_help.setToolTip(
            "relativeSizes=true: layer thicknesses are specified as fractions of the local cell size\n"
            "relativeSizes=false: layer thicknesses are taken as absolute (physical) lengths.\n"
            "Choose true to scale with local mesh, false for fixed thickness."
        )
        row_rel = QHBoxLayout()
        row_rel.addWidget(self.btn_relative)
        row_rel.addWidget(self.btn_help)
        row_rel.addStretch(1)
        gl.addLayout(row_rel, 1, 1)

        gl.addWidget(QLabel("Global nSurfaceLayers:"), 2, 0)
        self.spin_global = QSpinBox(); self.spin_global.setRange(0, 50); self.spin_global.setValue(3)
        self.spin_global.setToolTip("Number of layers to use in the template section below.")
        gl.addWidget(self.spin_global, 2, 1)

        gl.addWidget(QLabel("Global expansionRatio:"), 3, 0)
        self.d_expansion = QDoubleSpinBox(); self.d_expansion.setDecimals(3); self.d_expansion.setRange(1.0, 10.0); self.d_expansion.setSingleStep(0.05); self.d_expansion.setValue(1.20)
        gl.addWidget(self.d_expansion, 3, 1)

        gl.addWidget(QLabel("finalLayerThickness:"), 4, 0)
        self.d_finalThick = QDoubleSpinBox(); self.d_finalThick.setDecimals(3); self.d_finalThick.setRange(0.0, 1e6); self.d_finalThick.setSingleStep(0.01); self.d_finalThick.setValue(0.30)
        gl.addWidget(self.d_finalThick, 4, 1)

        gl.addWidget(QLabel("minThickness:"), 5, 0)
        self.d_minTh = QDoubleSpinBox(); self.d_minTh.setDecimals(3); self.d_minTh.setRange(0.0, 1e6); self.d_minTh.setSingleStep(0.01); self.d_minTh.setValue(0.10)
        gl.addWidget(self.d_minTh, 5, 1)

        gl.addWidget(QLabel("featureAngle (deg):"), 6, 0)
        self.d_featAng = QDoubleSpinBox(); self.d_featAng.setDecimals(1); self.d_featAng.setRange(0.0, 180.0); self.d_featAng.setSingleStep(1.0); self.d_featAng.setValue(150.0)
        gl.addWidget(self.d_featAng, 6, 1)

        gl.addWidget(QLabel("nGrow:"), 7, 0)
        self.spin_nGrow = QSpinBox(); self.spin_nGrow.setRange(0, 10); self.spin_nGrow.setValue(0)
        gl.addWidget(self.spin_nGrow, 7, 1)

        root.addWidget(gbox)

        row = QHBoxLayout()
        self.btn_save = QPushButton("Write addLayersControls to dict")
        self.btn_reset = QPushButton("Reset to suggested")
        self.btn_preview = QPushButton("Preview") 
        self.btn_close = QPushButton("Continue")
        row.addWidget(self.btn_close); row.addStretch(1)
        row.addWidget(self.btn_reset); row.addWidget(self.btn_preview); row.addWidget(self.btn_save)
        root.addLayout(row)

        self.btn_save.clicked.connect(self.on_save)
        self.btn_reset.clicked.connect(self.on_reset)
        self.btn_preview.clicked.connect(self.on_preview)  
        self.btn_close.clicked.connect(self.close)

        
        self._init_save_gate([self.chk_enable, self.btn_relative, self.spin_global, self.d_expansion,
                              self.d_finalThick, self.d_minTh, self.d_featAng, self.spin_nGrow])

        center_on_screen(self)

    def _toggle_relative(self):
        is_checked = self.btn_relative.isChecked()
        self.btn_relative.setText("true" if is_checked else "false")

    def on_reset(self):
        self.chk_enable.setChecked(True)
        self.btn_relative.setChecked(True)
        self.btn_relative.setText("true")
        self.spin_global.setValue(3)
        self.d_expansion.setValue(1.20)
        self.d_finalThick.setValue(0.30)
        self.d_minTh.setValue(0.10)
        self.d_featAng.setValue(150.0)
        self.spin_nGrow.setValue(0)

    def _build_block_text(self, base_text: str) -> str:
        # Build the addLayersControls block string using current GUI values
        block = render_addLayersControls(
            g_layers=self.spin_global.value(),
            g_expansion=(self.d_expansion.value()),
            g_finalThick=(self.d_finalThick.value()),
            g_minThickness=(self.d_minTh.value()),
            g_featureAngle=(self.d_featAng.value()),
            g_nGrow=(self.spin_nGrow.value()),
            relative_sizes=self.btn_relative.isChecked()
        )
        
        token = '"(placeholder).*"'
        m = re.search(r'"\(([^"]+)\)\.\*"', base_text)
        if m and m.group(1) and m.group(1) != "placeholder":
            token = f'"({m.group(1)}).*"'
        else:
            m2 = re.search(r'^\s*name\s+([A-Za-z0-9_.-]+)\s*;\s*$', base_text, re.MULTILINE)
            if m2:
                token = f'"({m2.group(1)}).*"'
        block = block.replace('"(placeholder).*"', token)
        return block

    def on_preview(self):
        
        base = self.dict_path.read_text(errors="ignore") if self.dict_path.exists() else ""
        block = self._build_block_text(base)

        
        dlg = QDialog(self)
        dlg.setWindowTitle("Preview — addLayersControls")
        dlg.resize(800, 500)
        v = QVBoxLayout(dlg)
        lbl = QLabel("This is the addLayersControls section that would be written:")
        v.addWidget(lbl)
        te = QTextEdit()
        te.setReadOnly(True)
        f = QFont("Monospace"); f.setStyleHint(QFont.TypeWriter)
        te.setFont(f)
        te.setPlainText(block)
        v.addWidget(te)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(dlg.accept)
        v.addWidget(bb)
        dlg.exec_()

    def on_save(self):
        text = self.dict_path.read_text(errors="ignore") if self.dict_path.exists() else ""
        text = ensure_header(text, "snappyHexMeshDict")
        text = upsert_boolean_switch(text, "addLayers", self.chk_enable.isChecked())

        block = self._build_block_text(text)

        i0, i1 = find_block_span(text, "addLayersControls")
        new_text = text[:i0] + block + text[i1:] if i0 >= 0 else text.rstrip() + ("\n\n" if text else "") + block

        def _normalize_glued_sections(s: str) -> str:
            s = re.sub(r'\}\s*;\s*(?=(snapControls|addLayersControls|meshQualityControls)\b)', '};\n\n', s)
            s = re.sub(r';\s*(?=(snapControls|addLayersControls|meshQualityControls)\b)', '\n', s)
            return s
        new_text = _normalize_glued_sections(new_text)

        new_text = re.sub(r'(^\s*mergeTolerance\s+[^\s;]+)\s*;?\s*$',
                          r'\1;',
                          new_text, flags=re.MULTILINE)

        self.dict_path.parent.mkdir(parents=True, exist_ok=True)
        self.dict_path.write_text(new_text)
        QMessageBox.information(self, "Done", f"addLayersControls written to:\n{self.dict_path}")
        self.markSaved()

def main():
    ap = argparse.ArgumentParser(description="Layers GUI: nSurfaceLayers + advanced options (snappyHexMeshDict)")
    ap.add_argument("--root", help="Project root (contains 'mesh' and 'templateCase')", default=None)
    ap.add_argument("--dict", dest="dict_path", help="Path to snappyHexMeshDict (overrides --root)", default=None)
    args = ap.parse_args()

    if args.dict_path:
        dict_path = Path(args.dict_path).expanduser().resolve()
    else:
        dict_path = (Path.cwd() / "system" / "snappyHexMeshDict").resolve()
        if not (Path.cwd() / "system").exists() and not dict_path.parent.exists():
            cli_root = Path(args.root).expanduser().resolve() if args.root else None
            repo_root = detect_repo_root(cli_root)
            dict_path = fallback_snappy_path(repo_root)

    set_qt_env()
    app = QApplication(sys.argv)
    apply_fusion_dark(app)

    gui = LayersGui(dict_path)
    if not dict_path.exists():
        QMessageBox.information(gui, "Target file not found",
                                f"snappyHexMeshDict not found:\n{dict_path}\n\n"
                                "The file will be created on Save with a standard OpenFOAM header.")
    center_on_screen(gui)
    gui.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
