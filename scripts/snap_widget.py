#!/usr/bin/env python3
# snap_widget.py
# GUI to edit snapControls inside snappyHexMeshDict.

import os, sys, re, argparse
from pathlib import Path
from typing import Optional, Tuple, List

from PyQt5.QtWidgets import ( # type: ignore
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton, QMessageBox,
    QSpacerItem, QSizePolicy  
)
from PyQt5.QtCore import Qt # type: ignore

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

def default_snappy_path(repo_root: Path) -> Path:
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

def find_block_span(text: str, key: str) -> Tuple[int,int]:
    pat = re.compile(r'(^|\s)'+re.escape(key)+r'\s*\{', re.MULTILINE)
    m = pat.search(text)
    if not m: return (-1,-1)
    i = text.find('{', m.end()-1)
    if i < 0: return (-1,-1)
    depth, j = 1, i+1
    while j < len(text) and depth > 0:
        if text[j] == '{': depth += 1
        elif text[j] == '}': depth -= 1
        j += 1
    return (m.start(), j)


def _find_all_block_spans(text: str, key: str) -> List[Tuple[int,int]]:
    spans: List[Tuple[int,int]] = []
    pat = re.compile(r'(^|\s)'+re.escape(key)+r'\s*\{', re.MULTILINE)
    idx = 0
    while True:
        m = pat.search(text, idx)
        if not m: break
        i = text.find('{', m.end()-1)
        if i < 0: break
        depth, j = 1, i+1
        while j < len(text) and depth > 0:
            if text[j] == '{': depth += 1
            elif text[j] == '}': depth -= 1
            j += 1
        if j < len(text) and text[j:j+1] == ';':
            j += 1
        spans.append((m.start(), j))
        idx = j
    return spans

def _normalize_glued_sections(text: str) -> str:
    for key in ("snapControls", "addLayersControls", "meshQualityControls"):
        text = re.sub(r'\}\s*'+re.escape(key)+r'\b', r'};\n\n'+key, text)
    text = re.sub(r';\s*;\s*', ';\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


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

def parse_snap_controls(text: str):
    i0,i1 = find_block_span(text, "snapControls")
    vals = {
        "nSmoothPatch": None, "tolerance": None, "nSolveIter": None, "nRelaxIter": None,
        "implicitFeatureSnap": None, "explicitFeatureSnap": None, "multiRegionFeatureSnap": None
    }
    if i0 < 0: return vals, (-1,-1)
    blk = text[i0:i1]
    def read_int(name):
        m = re.search(rf'^\s*{name}\s+(\d+)\s*;\s*$', blk, re.MULTILINE)
        return int(m.group(1)) if m else None
    def read_float(name):
        m = re.search(rf'^\s*{name}\s+([0-9.eE+-]+)\s*;\s*$', blk, re.MULTILINE)
        return float(m.group(1)) if m else None
    def read_bool(name):
        m = re.search(rf'^\s*{name}\s+(true|false)\s*;\s*$', blk, re.MULTILINE)
        return (m.group(1) == "true") if m else None
    vals["nSmoothPatch"] = read_int("nSmoothPatch")
    vals["tolerance"]    = read_float("tolerance")
    vals["nSolveIter"]   = read_int("nSolveIter")
    vals["nRelaxIter"]   = read_int("nRelaxIter")
    vals["implicitFeatureSnap"]   = read_bool("implicitFeatureSnap")
    vals["explicitFeatureSnap"]   = read_bool("explicitFeatureSnap")
    vals["multiRegionFeatureSnap"] = read_bool("multiRegionFeatureSnap")
    return vals, (i0,i1)

def render_snap_controls(cfg) -> str:
    nSmoothPatch = int(cfg.get("nSmoothPatch") or 3)
    tolerance    = float(cfg.get("tolerance") or 2.0)
    nSolveIter   = int(cfg.get("nSolveIter") or 30)
    nRelaxIter   = int(cfg.get("nRelaxIter") or 5)
    implicitF    = bool(cfg.get("implicitFeatureSnap") if cfg.get("implicitFeatureSnap") is not None else True)
    explicitF    = bool(cfg.get("explicitFeatureSnap") if cfg.get("explicitFeatureSnap") is not None else False)
    multiF       = bool(cfg.get("multiRegionFeatureSnap") if cfg.get("multiRegionFeatureSnap") is not None else False)
    lines = []
    lines += ["snapControls", "{"]
    lines += [f"    nSmoothPatch        {nSmoothPatch};"]
    lines += [f"    tolerance           {tolerance};"]
    lines += [f"    nSolveIter          {nSolveIter};"]
    lines += [f"    nRelaxIter          {nRelaxIter};", ""]
    lines += ["    // Feature snapping"]
    lines += [f"    implicitFeatureSnap  {'true' if implicitF else 'false'};"]
    lines += [f"    explicitFeatureSnap  {'true' if explicitF else 'false'};"]
    lines += [f"    multiRegionFeatureSnap {'true' if multiF else 'false'};"]
    lines += ["}"]
    return "\n".join(lines) + "\n"

class SnapGui(QWidget):
    def __init__(self, dict_path: Path):
        super().__init__()
        self.dict_path = dict_path
        self.setWindowTitle("Snap controls (snappyHexMesh)")
        self.resize(620, 420)

        root = QVBoxLayout(self)
        info = QLabel(f"snappyHexMeshDict: {self.dict_path}")
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(info)

        box = QGroupBox("Main parameters")
        gl = QGridLayout(box)

        gl.addWidget(QLabel("nSmoothPatch:"), 0, 0)
        self.nSmoothPatch = QSpinBox(); self.nSmoothPatch.setRange(0, 200); self.nSmoothPatch.setValue(3)
        self.nSmoothPatch.setToolTip("Patch smoothing iterations. Typical 3–10.")
        gl.addWidget(self.nSmoothPatch, 0, 1)

        gl.addWidget(QLabel("tolerance:"), 1, 0)
        self.tolerance = QDoubleSpinBox(); self.tolerance.setDecimals(3); self.tolerance.setRange(0.0, 20.0); self.tolerance.setSingleStep(0.1); self.tolerance.setValue(2.0)
        self.tolerance.setToolTip("Max relative distance (× local edge length) to attract points. Typical 1.0–4.0.")
        gl.addWidget(self.tolerance, 1, 1)

        gl.addWidget(QLabel("nSolveIter:"), 2, 0)
        self.nSolveIter = QSpinBox(); self.nSolveIter.setRange(1, 2000); self.nSolveIter.setValue(30)
        self.nSolveIter.setToolTip("Mesh-displacement iterations. Higher = more robust but slower.")
        gl.addWidget(self.nSolveIter, 2, 1)

        gl.addWidget(QLabel("nRelaxIter:"), 3, 0)
        self.nRelaxIter = QSpinBox(); self.nRelaxIter.setRange(0, 200); self.nRelaxIter.setValue(5)
        self.nRelaxIter.setToolTip("Relaxation iterations to stabilize movement.")
        gl.addWidget(self.nRelaxIter, 3, 1)

        root.addWidget(box)

        fbox = QGroupBox("Feature snapping")
        fl = QGridLayout(fbox)
        self.chk_implicit = QCheckBox("implicitFeatureSnap"); self.chk_implicit.setChecked(True)
        self.chk_explicit = QCheckBox("explicitFeatureSnap"); self.chk_explicit.setChecked(False)
        self.chk_multi    = QCheckBox("multiRegionFeatureSnap"); self.chk_multi.setChecked(False)
        self.chk_implicit.setToolTip("Use implicit feature detection (no pre-extracted edges).")
        self.chk_explicit.setToolTip("Use explicit features (edges from surfaceFeatures/eMesh).")
        self.chk_multi.setToolTip("Capture edges between multiple surfaces/regions.")
        fl.addWidget(self.chk_implicit, 0, 0)
        fl.addWidget(self.chk_explicit, 0, 1)
        fl.addWidget(self.chk_multi,    1, 0)
        root.addWidget(fbox)

        row = QHBoxLayout()
        self.btn_load = QPushButton("Load existing")
        self.btn_preview = QPushButton("Preview block")
        self.btn_save = QPushButton("Write snapControls")
        self.btn_reset = QPushButton("Reset to suggested")
        self.btn_close = QPushButton("Continue")  # always enabled
        row.addWidget(self.btn_close); row.addStretch(1)
        row.addWidget(self.btn_reset); row.addWidget(self.btn_load); row.addWidget(self.btn_preview); row.addWidget(self.btn_save)
        root.addLayout(row)

        self.btn_load.clicked.connect(self.on_load)
        self.btn_preview.clicked.connect(self.on_preview)
        self.btn_save.clicked.connect(self.on_save)
        self.btn_reset.clicked.connect(self.on_reset)
        self.btn_close.clicked.connect(self.close)

        center_on_screen(self)

    def on_load(self):
        if not self.dict_path.exists():
            QMessageBox.information(self, "Missing file", f"snappyHexMeshDict not found:\n{self.dict_path}")
            return
        text = self.dict_path.read_text(errors="ignore")
        vals, _ = parse_snap_controls(text)
        if vals["nSmoothPatch"] is not None: self.nSmoothPatch.setValue(vals["nSmoothPatch"])
        if vals["tolerance"]    is not None: self.tolerance.setValue(vals["tolerance"])
        if vals["nSolveIter"]   is not None: self.nSolveIter.setValue(vals["nSolveIter"])
        if vals["nRelaxIter"]   is not None: self.nRelaxIter.setValue(vals["nRelaxIter"])
        if vals["implicitFeatureSnap"] is not None: self.chk_implicit.setChecked(vals["implicitFeatureSnap"])
        if vals["explicitFeatureSnap"] is not None: self.chk_explicit.setChecked(vals["explicitFeatureSnap"])
        if vals["multiRegionFeatureSnap"] is not None: self.chk_multi.setChecked(vals["multiRegionFeatureSnap"])

    def _gather(self):
        return {
            "nSmoothPatch": int(self.nSmoothPatch.value()),
            "tolerance": float(self.tolerance.value()),
            "nSolveIter": int(self.nSolveIter.value()),
            "nRelaxIter": int(self.nRelaxIter.value()),
            "implicitFeatureSnap": bool(self.chk_implicit.isChecked()),
            "explicitFeatureSnap": bool(self.chk_explicit.isChecked()),
            "multiRegionFeatureSnap": bool(self.chk_multi.isChecked())
        }

    def on_preview(self):
        txt = render_snap_controls(self._gather())

        msg = QMessageBox(self)
        msg.setWindowTitle("Preview: snapControls")
        msg.setTextInteractionFlags(Qt.TextSelectableByMouse)
        msg.setText(f"<pre>{txt}</pre>")

        lay = msg.layout()
        lay.addItem(QSpacerItem(900, 0, QSizePolicy.Minimum, QSizePolicy.Expanding),
                    lay.rowCount(), 0, 1, lay.columnCount())

        msg.exec_()

    def on_reset(self):
        self.nSmoothPatch.setValue(3)
        self.tolerance.setValue(2.0)
        self.nSolveIter.setValue(30)
        self.nRelaxIter.setValue(5)
        self.chk_implicit.setChecked(True)
        self.chk_explicit.setChecked(False)
        self.chk_multi.setChecked(False)

    def on_save(self):
        text = self.dict_path.read_text(errors="ignore") if self.dict_path.exists() else ""
        text = ensure_header(text, "snappyHexMeshDict")
        text = _normalize_glued_sections(text)

        cfg  = self._gather()
        block = render_snap_controls(cfg)

        spans = _find_all_block_spans(text, "snapControls")
        if spans:
            for (a,b) in reversed(spans[:-1]):
                text = text[:a] + text[b:]
            spans2 = _find_all_block_spans(text, "snapControls")
            a,b = spans2[-1]
            new_text = text[:a] + block + text[b:]
        else:
            sep = "\n\n" if text.strip() else ""
            new_text = text.rstrip() + sep + block

        new_text = _normalize_glued_sections(new_text)

        self.dict_path.parent.mkdir(parents=True, exist_ok=True)
        self.dict_path.write_text(new_text)
        QMessageBox.information(self, "Saved", f"'snapControls' written to:\n{self.dict_path}")

def main():
    ap = argparse.ArgumentParser(description="GUI for snappyHexMesh snapControls")
    ap.add_argument("--root", help="Project root (contains 'mesh' and 'templateCase')", default=None)
    ap.add_argument("--dict", dest="dict_path", help="Path to snappyHexMeshDict (overrides --root)", default=None)
    args = ap.parse_args()

    if args.dict_path:
        dict_path = Path(args.dict_path).expanduser().resolve()
    else:
        dict_path = (Path.cwd() / "system" / "snappyHexMeshDict").resolve()
        if not dict_path.parent.exists():
            cli_root = Path(args.root).expanduser().resolve() if args.root else None
            repo_root = detect_repo_root(cli_root)
            dict_path = default_snappy_path(repo_root)

    set_qt_env()
    app = QApplication(sys.argv)
    apply_fusion_dark(app)

    gui = SnapGui(dict_path)
    if not dict_path.exists():
        QMessageBox.information(gui, "Target file not found",
            f"snappyHexMeshDict not found:\n{dict_path}\n\n"
            "The file will be created on Save with a standard OpenFOAM header.")
    center_on_screen(gui)
    gui.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
