#!/usr/bin/env python3
# Quality presets GUI for OpenFOAM dictionaries.
# Writes:
#   1) snappyHexMeshDict (meshQualityControls)  [pre-run]
#   2) system/meshQualityDict                   [post-run: checkMesh -meshQuality]

import sys
import re
import argparse
import math
from pathlib import Path
from typing import Dict, Tuple, Optional

from PyQt5.QtWidgets import (  # type: ignore
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout,
    QLabel, QRadioButton, QPushButton, QCheckBox, QMessageBox, QDialog, QPlainTextEdit
)
from PyQt5.QtCore import Qt  # type: ignore
from PyQt5.QtGui import QFontDatabase  # type: ignore

from ui_theme import set_qt_env, apply_fusion_dark, center_on_screen

def detect_project_root(cli_root: Optional[Path]) -> Path:
    if cli_root and cli_root.exists():
        return cli_root.resolve()
    start = Path(__file__).resolve().parent
    for cand in [start, *start.parents]:
        if (cand / "mesh").is_dir() and (cand / "templateCase").is_dir():
            return cand
    return Path.cwd().resolve()

def snappy_path(root: Path) -> Path:
    return (root / "mesh" / "snappyHexMeshDict").resolve()

def mesh_quality_dict_path(root: Path) -> Path:
    return (root / "templateCase" / "system" / "meshQualityDict").resolve()

HEADER_BANNER = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2406                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/"""
FOOTER_LINE = "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //"""

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
        if text[j] == '{': depth += 1
        elif text[j] == '}': depth -= 1
        j += 1
    return (m.start(), j)

def render_mesh_quality_controls_with_include(vals: Dict[str, float]) -> str:
    override_keys = [
        "maxNonOrtho","maxBoundarySkewness","maxInternalSkewness","maxConcave",
        "minFlatness","minTetQuality","minVol","minArea","minTwist","minDeterminant",
        "minFaceWeight","minVolRatio","minTriangleTwist"
    ]
    lines = []
    lines.append("meshQualityControls")
    lines.append("{")
    lines.append('    #include "meshQualityDict"')
    relaxed = vals.get("relaxed.maxNonOrtho", vals.get("maxNonOrtho", 100))
    lines.append(f"    relaxed {{ maxNonOrtho {relaxed:g}; }}")
    if "nSmoothScale" in vals:
        lines.append(f"    nSmoothScale     {vals['nSmoothScale']:g};")
    if "errorReduction" in vals:
        lines.append(f"    errorReduction   {vals['errorReduction']:g};")
    for k in override_keys:
        if k in vals:
            lines.append(f"    {k:22s} {vals[k]:g};")
    lines.append("}")
    return "\n".join(lines) + "\n"

def make_mesh_quality_dict(vals: Dict[str, float]) -> str:
    body = []
    for k, v in vals.items():
        if v is None:
            continue
        body.append(f"{k:22s} {v:g};")
    return foam_header("meshQualityDict") + "\n" + "\n".join(body) + "\n"

def presets() -> Dict[str, Dict[str, float]]:
    stricter = dict(
        maxNonOrtho=60, maxBoundarySkewness=15, maxInternalSkewness=2, maxConcave=70,
        minFlatness=0.6, minTetQuality=-1e30, minVol=1e-14, minArea=-1,
        minTwist=0.10, minDeterminant=0.01, minFaceWeight=0.10, minVolRatio=0.05,
        minTriangleTwist=-1, nSmoothScale=4, errorReduction=0.7
    )
    balanced = dict(
        maxNonOrtho=65, maxBoundarySkewness=20, maxInternalSkewness=4, maxConcave=80,
        minFlatness=0.5, minTetQuality=-1e30, minVol=1e-13, minArea=-1,
        minTwist=0.05, minDeterminant=0.001, minFaceWeight=0.05, minVolRatio=0.01,
        minTriangleTwist=-1, nSmoothScale=4, errorReduction=0.75
    )
    more_perm = dict(
        maxNonOrtho=100,
        maxBoundarySkewness=40,
        maxInternalSkewness=40,
        maxConcave=80,
        minFlatness=0.4,
        minTetQuality=-1e30,
        minVol=-1e30,
        minArea=-1,
        minTwist=0.02,
        minDeterminant=0.001,
        minFaceWeight=0.05,
        minVolRatio=0.01,
        minTriangleTwist=-1,
        nSmoothScale=3,
        errorReduction=0.8
    )
    return {"Stricter limits": stricter, "Balanced": balanced, "More permissive": more_perm}

KEYS = [
    "maxNonOrtho","maxBoundarySkewness","maxInternalSkewness","maxConcave",
    "minFlatness","minTetQuality","minVol","minArea","minTwist","minDeterminant",
    "minFaceWeight","minVolRatio","minTriangleTwist","nSmoothScale","errorReduction"
]

def parse_meshQualityControls(text: str) -> Dict[str, float]:
    vals: Dict[str, float] = {}
    i0, i1 = find_block_span(text, "meshQualityControls")
    if i0 < 0:
        return vals
    blk = text[i0:i1]
    for k in KEYS:
        m = re.search(rf'^\s*{re.escape(k)}\s+([0-9.eE+-]+)\s*;\s*$', blk, re.MULTILINE)
        if m:
            try:
                vals[k] = float(m.group(1))
            except Exception:
                pass
    m = re.search(r"relaxed\s*\{[^}]*maxNonOrtho\s+([0-9.eE+-]+)\s*;\s*[^}]*\}", blk, re.DOTALL)
    if m:
        try:
            vals["relaxed.maxNonOrtho"] = float(m.group(1))
        except Exception:
            pass
    return vals

def parse_meshQualityDict(text: str) -> Dict[str, float]:
    vals: Dict[str, float] = {}
    for k in KEYS:
        m = re.search(rf'^\s*{re.escape(k)}\s+([0-9.eE+-]+)\s*;\s*$', text, re.MULTILINE)
        if m:
            try:
                vals[k] = float(m.group(1))
            except Exception:
                pass
    return vals

def compare_to_presets(current: Dict[str, float], tol_rel=1e-6, tol_abs=1e-12) -> Tuple[str, str]:
    if not current:
        return ("Unknown", "no-values")
    P = presets()
    best_name, best_kind = "Custom", "mismatch"
    for name, ref in P.items():
        same_all = True
        near_all = True
        for k, vref in ref.items():
            v = current.get(k, None)
            if v is None:
                same_all = False
                near_all = False
                break
            if v != vref:
                same_all = False
                if not math.isclose(v, vref, rel_tol=tol_rel, abs_tol=tol_abs):
                    near_all = False
                    break
        if same_all:
            return (name, "exact")
        if near_all and best_kind != "exact":
            best_name, best_kind = name, "near"
    return (best_name, best_kind)

def _show_text_preview(parent, title: str, text: str):
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(860, 680)
    lay = QVBoxLayout(dlg)

    edit = QPlainTextEdit(dlg)
    edit.setReadOnly(True)
    edit.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
    edit.setPlainText(text)
    lay.addWidget(edit)

    btn = QPushButton("Continue", dlg)
    btn.clicked.connect(dlg.close)
    lay.addWidget(btn)

    return dlg

def _normalize_glued_sections(text: str) -> str:
    for key in ("snapControls", "addLayersControls", "meshQualityControls"):
        text = re.sub(r'\}\s*'+re.escape(key)+r'\b', r'};\n\n'+key, text)
    text = re.sub(r';\s*;\s*', ';\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

class QualityGui(QWidget):
    def __init__(self, snappy_file: Path, meshq_file: Path):
        super().__init__()
        self.snappy_file = snappy_file
        self.meshq_file = meshq_file

        self.setWindowTitle("Quality presets (meshQualityControls + meshQualityDict)")
        self.resize(820, 500)

        self._preview_windows = []
        self.diff_available = self._try_prepare_diff_import()

        root = QVBoxLayout(self)
        lab_paths = QLabel(f"snappyHexMeshDict: {self.snappy_file}\nmeshQualityDict: {self.meshq_file}")
        lab_paths.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(lab_paths)

        self.badge = QLabel("Active preset: —")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setStyleSheet(
            "padding:6px 10px; border-radius:12px; "
            "border:1px solid #888; background:transparent; color:#ddd; font-weight:bold;"
        )
        root.addWidget(self.badge)

        grp = QGroupBox("Choose preset")
        gl = QGridLayout(grp)
        self.rb_strict = QRadioButton("Stricter limits")
        self.rb_bal    = QRadioButton("Balanced (typical)")
        self.rb_perm   = QRadioButton("More permissive")
        self.rb_bal.setChecked(True)
        gl.addWidget(self.rb_strict, 0, 0)
        gl.addWidget(self.rb_bal,    1, 0)
        gl.addWidget(self.rb_perm,   2, 0)
        note = QLabel("These thresholds mirror both pre-run (snappyHexMesh) and post-run (checkMesh).")
        note.setStyleSheet("color:#666;")
        gl.addWidget(note, 3, 0, 1, 2)
        root.addWidget(grp)

        opt = QGroupBox("Apply to")
        ol = QVBoxLayout(opt)
        self.chk_snappy = QCheckBox("Write to snappyHexMeshDict (meshQualityControls)")
        self.chk_meshq  = QCheckBox("Write to system/meshQualityDict")
        self.chk_snappy.setChecked(True)
        self.chk_meshq.setChecked(True)
        ol.addWidget(self.chk_snappy)
        ol.addWidget(self.chk_meshq)
        root.addWidget(opt)

        row = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh status")
        self.btn_preview = QPushButton("Preview diff")
        self.btn_apply   = QPushButton("Apply")
        self.btn_close   = QPushButton("Continue")
        if not self.diff_available:
            self.btn_preview.setEnabled(False)
            self.btn_preview.setToolTip("Place diff_preview.py in the same folder or add it to PYTHONPATH.")
        row.addWidget(self.btn_close); row.addStretch(1)
        row.addWidget(self.btn_refresh); row.addWidget(self.btn_preview); row.addWidget(self.btn_apply)
        root.addLayout(row)

        self.btn_refresh.clicked.connect(self.update_badge)
        self.btn_preview.clicked.connect(self.on_preview)
        self.btn_apply.clicked.connect(self.on_apply)
        self.btn_close.clicked.connect(self.close)

        missing = []
        if self.chk_snappy.isChecked() and not self.snappy_file.exists():
            missing.append(str(self.snappy_file))
        if self.chk_meshq.isChecked() and not self.meshq_file.exists():
            missing.append(str(self.meshq_file))
        if missing:
            QMessageBox.information(self, "Target not found",
                "Some target files are missing:\n- " + "\n- ".join(missing) +
                "\n\nThey will be created on Apply with a standard OpenFOAM header.")

        self.update_badge()
        center_on_screen(self)

        

    def _try_prepare_diff_import(self) -> bool:
        try:
            import diff_preview  # noqa: F401
            return True
        except Exception:
            here = Path(__file__).resolve().parent
            if str(here) not in sys.path:
                sys.path.insert(0, str(here))
            try:
                import diff_preview  # noqa: F401
                return True
            except Exception:
                QMessageBox.warning(self, "Diff preview unavailable",
                    "Cannot import diff_preview.py.\n\n"
                    "Place diff_preview.py in the same folder as this script or add it to PYTHONPATH.")
                return False

    def _current_preset_vals(self) -> Dict[str, float]:
        p = presets()
        if self.rb_strict.isChecked():
            return p["Stricter limits"]
        if self.rb_perm.isChecked():
            return p["More permissive"]
        return p["Balanced"]

    def _build_new_snappy_text(self, old: str) -> str:
        old = ensure_header(old, "snappyHexMeshDict")
        vals = self._current_preset_vals()
        block = render_mesh_quality_controls_with_include(vals)
        txt = old
        while True:
            i0, i1 = find_block_span(txt, "meshQualityControls")
            if i0 < 0:
                break
            txt = txt[:i0] + txt[i1:]
        txt = txt.rstrip()
        if txt:
            txt += "\n\n" + block
        else:
            txt = block
        txt = _normalize_glued_sections(txt)
        return txt

    def _build_new_meshq_text(self, old: str) -> str:
        vals = self._current_preset_vals()
        if old.strip():
            text = old
            for k, v in vals.items():
                pat = re.compile(r'^\s*' + re.escape(k) + r'\s+.*?;\s*$', re.MULTILINE)
                if pat.search(text):
                    text = pat.sub(f"{k:22s} {v:g};", text)
                else:
                    text = text.rstrip() + f"\n{k:22s} {v:g};\n"
            return ensure_header(text, "meshQualityDict")
        else:
            return make_mesh_quality_dict(vals)

    def _read_current_values(self) -> Tuple[Dict[str, float], Dict[str, float]]:
        s_vals: Dict[str, float] = {}
        m_vals: Dict[str, float] = {}
        if self.snappy_file.exists():
            s_txt = self.snappy_file.read_text(errors="ignore")
            s_vals = parse_meshQualityControls(s_txt)
        if self.meshq_file.exists():
            m_txt = self.meshq_file.read_text(errors="ignore")
            m_vals = parse_meshQualityDict(m_txt)
        return s_vals, m_vals

    def _badge_style(self, kind: str) -> str:
        if kind == "exact":
            return ("border:1px solid #34d058; color:#34d058; "
                    "padding:6px 10px; border-radius:12px; font-weight:bold; background:transparent;")
        if kind == "near":
            return ("border:1px solid #e1c542; color:#e1c542; "
                    "padding:6px 10px; border-radius:12px; font-weight:bold; background:transparent;")
        if kind == "mismatch":
            return ("border:1px solid #d73a49; color:#d73a49; "
                    "padding:6px 10px; border-radius:12px; font-weight:bold; background:transparent;")
        return ("border:1px solid #888; color:#ddd; "
                "padding:6px 10px; border-radius:12px; font-weight:bold; background:transparent;")

    def update_badge(self):
        s_vals, m_vals = self._read_current_values()
        name_s, kind_s = compare_to_presets(s_vals)
        name_m, kind_m = compare_to_presets(m_vals)
        if name_s == "Unknown" and name_m == "Unknown":
            txt = "Active preset: —"
            style_kind = "mismatch"
        elif name_s == "Custom" and name_m == "Custom":
            txt = "Active preset: Custom"
            style_kind = "mismatch"
        elif name_s == "Unknown":
            txt = f"Active preset: {name_m} ({kind_m}, from meshQualityDict)"
            style_kind = kind_m
        elif name_m == "Unknown":
            txt = f"Active preset: {name_s} ({kind_s}, from snappyHexMeshDict)"
            style_kind = kind_s
        else:
            if name_s == name_m and kind_s == kind_m and name_s not in ("Custom", "Unknown"):
                txt = f"Active preset: {name_s} ({kind_s}, both files)"
                style_kind = kind_s
            else:
                txt = f"Active preset: Mixed (snappy={name_s}/{kind_s}, meshQ={name_m}/{kind_m})"
                style_kind = "mismatch"
        self.badge.setText(txt)
        self.badge.setStyleSheet(self._badge_style(style_kind))

    def on_preview(self):
        w1 = w2 = None

        
        if self.chk_snappy.isChecked():
            old = self.snappy_file.read_text(errors="ignore") if self.snappy_file.exists() else ""
            new_full = self._build_new_snappy_text(old)
            i0, i1 = find_block_span(new_full, "meshQualityControls")
            if i0 >= 0:
                new_block = new_full[i0:i1].strip()
            else:
                new_block = render_mesh_quality_controls_with_include(self._current_preset_vals()).strip()
            w1 = _show_text_preview(self, "Preview: snappyHexMeshDict (meshQualityControls)", new_block)
            w1.show()

        if self.chk_meshq.isChecked():
            old = self.meshq_file.read_text(errors="ignore") if self.meshq_file.exists() else ""
            new = self._build_new_meshq_text(old)
            w2 = _show_text_preview(self, "Preview: meshQualityDict (checkMesh)", new)
            w2.show()
        if w1 and w2 and hasattr(w1, "frameGeometry") and hasattr(w2, "frameGeometry"):
            scr = QApplication.primaryScreen().availableGeometry()
            cx, cy = scr.center().x(), scr.center().y()
            g1 = w1.frameGeometry()
            g2 = w2.frameGeometry()
            gap = 20
            w1.move(int(cx - g1.width() - gap/2), int(cy - g1.height()/2))
            w2.move(int(cx + gap/2),             int(cy - g2.height()/2))

    def on_apply(self):
        if not (self.chk_snappy.isChecked() and self.chk_meshq.isChecked()):
            ret = QMessageBox.question(
                self, "Apply to a single file?",
                ("You are applying the preset to a single target.\n\n"
                 "Do you want to proceed?"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if ret != QMessageBox.Yes:
                return
        did_any = False
        if self.chk_snappy.isChecked():
            old = self.snappy_file.read_text(errors="ignore") if self.snappy_file.exists() else ""
            new = self._build_new_snappy_text(old)
            self.snappy_file.parent.mkdir(parents=True, exist_ok=True)
            self.snappy_file.write_text(new)
            did_any = True
        if self.chk_meshq.isChecked():
            old = self.meshq_file.read_text(errors="ignore") if self.meshq_file.exists() else ""
            new = self._build_new_meshq_text(old)
            self.meshq_file.parent.mkdir(parents=True, exist_ok=True)
            self.meshq_file.write_text(new)
            did_any = True
        if did_any:
            QMessageBox.information(self, "Done", "Quality presets applied.")
            self.update_badge()
        else:
            QMessageBox.information(self, "Nothing done", "Select at least one target to apply.")

def main():
    ap = argparse.ArgumentParser(description="Quality presets (snappyHexMesh meshQualityControls + system/meshQualityDict)")
    ap.add_argument("--root", help="Project root (contains 'mesh' and 'templateCase')", default=None)
    ap.add_argument("--snappy", help="Path to snappyHexMeshDict", default=None)
    ap.add_argument("--meshq", help="Path to meshQualityDict", default=None)
    args = ap.parse_args()

    if args.snappy:
        snappy = Path(args.snappy).expanduser().resolve()
    else:
        case_snappy = (Path.cwd() / "case" / "system" / "snappyHexMeshDict").resolve()
        if case_snappy.exists():
            snappy = case_snappy
        else:
            snappy = (Path.cwd() / "system" / "snappyHexMeshDict").resolve()
            if not snappy.parent.exists():
                root = detect_project_root(Path(args.root).expanduser().resolve() if args.root else None)
                snappy = snappy_path(root)

    if args.meshq:
        meshq = Path(args.meshq).expanduser().resolve()
    else:
        case_meshq = (Path.cwd() / "case" / "system" / "meshQualityDict").resolve()
        if case_meshq.exists():
            meshq = case_meshq
        else:
            meshq = (Path.cwd() / "system" / "meshQualityDict").resolve()
            if not meshq.parent.exists():
                root = detect_project_root(Path(args.root).expanduser().resolve() if args.root else None)
                meshq = mesh_quality_dict_path(root)

    set_qt_env()
    app = QApplication(sys.argv)
    apply_fusion_dark(app)
    gui = QualityGui(snappy, meshq)
    gui.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
