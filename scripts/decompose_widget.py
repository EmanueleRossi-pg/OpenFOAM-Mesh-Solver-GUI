#!/usr/bin/env python3
# decompose_widget.py
# GUI to configure system/decomposeParDict:
# method = simple | hierarchical | scotch, with live validation nx*ny*nz == numberOfSubdomains.

import sys, re, argparse, os
from pathlib import Path
from typing import Optional

from PyQt5.QtWidgets import ( # type: ignore
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton, QMessageBox,
    QSpacerItem, QSizePolicy  
)
from PyQt5.QtCore import Qt # type: ignore

# Shared theme utilities
from ui_theme import set_qt_env, apply_fusion_dark, center_on_screen

ORDER_OPTIONS = ["xyz","xzy","yxz","yzx","zxy","zyx"]

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

def default_decompose_path(repo_root: Path) -> Path:
    return (repo_root / "templateCase" / "system" / "decomposeParDict").resolve()

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

def parse_existing_dict(text: str):
    out = {"numberOfSubdomains": None, "method": None, "nxyz": None, "delta": None, "order": None}
    m = re.search(r'^\s*numberOfSubdomains\s+(\d+)\s*;', text, re.MULTILINE)
    if m: out["numberOfSubdomains"] = int(m.group(1))
    m = re.search(r'^\s*method\s+(\S+)\s*;', text, re.MULTILINE)
    if m: out["method"] = m.group(1)

    def block_span(key: str):
        pat = re.compile(r'(^|\s)'+re.escape(key)+r'\s*\{', re.MULTILINE)
        mm = pat.search(text)
        if not mm: return (-1,-1)
        i = text.find('{', mm.end()-1)
        depth, j = 1, i+1
        while j < len(text) and depth > 0:
            if text[j] == '{': depth += 1
            elif text[j] == '}': depth -= 1
            j += 1
        return (mm.start(), j)

    for key in ("simpleCoeffs","hierarchicalCoeffs"):
        i0,i1 = block_span(key)
        if i0 >= 0:
            blk = text[i0:i1]
            n = re.search(r'^\s*n\s*\(\s*(\d+)\s+(\d+)\s+(\d+)\s*\)\s*;', blk, re.MULTILINE)
            if n: out["nxyz"] = (int(n.group(1)), int(n.group(2)), int(n.group(3)))
            d = re.search(r'^\s*delta\s+([0-9.eE+-]+)\s*;', blk, re.MULTILINE)
            if d: out["delta"] = float(d.group(1))
            o = re.search(r'^\s*order\s+([a-zA-Z]{3})\s*;', blk, re.MULTILINE)
            if o: out["order"] = o.group(1)
            break
    return out

def build_decompose_dict(np_tot: int, method: str, nxyz=None, delta=None, order=None) -> str:
    lines = []
    lines += [
        foam_header("decomposeParDict"),
        f"numberOfSubdomains {int(np_tot)};",
        f"method              {method};",
        ""
    ]
    if method == "simple":
        nx,ny,nz = nxyz or (1,1,1)
        lines += ["simpleCoeffs", "{",
                  f"    n               ({nx} {ny} {nz});    // nx*ny*nz must equal numberOfSubdomains",
                  f"    delta           {float(delta) if delta is not None else 0.001};",
                  "}"]
    elif method == "hierarchical":
        nx,ny,nz = nxyz or (1,1,1)
        lines += ["hierarchicalCoeffs", "{",
                  f"    n               ({nx} {ny} {nz});",
                  f"    delta           {float(delta) if delta is not None else 0.001};",
                  f"    order           {order or 'xyz'};",
                  "}"]
    elif method == "scotch":
        lines += ["// scotch: automatic graph partitioning; no n/delta/order required."]
    lines.append("")
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

class DecomposeGui(QWidget, SaveGateMixin):
    def __init__(self, dict_path: Path):
        super().__init__()
        self.dict_path = dict_path

        self.setWindowTitle("Decompose (multi-core): simple / hierarchical / scotch")
        self.resize(680, 420)

        root = QVBoxLayout(self)
        info = QLabel(f"decomposeParDict: {self.dict_path}")
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(info)

        gbox = QGroupBox("General")
        gl = QGridLayout(gbox)
        gl.addWidget(QLabel("numberOfSubdomains (MPI processes):"), 0, 0)
        self.spin_np = QSpinBox(); self.spin_np.setRange(1, 131072); self.spin_np.setValue(8)
        gl.addWidget(self.spin_np, 0, 1)
        root.addWidget(gbox)

        mbox = QGroupBox("Method & coefficients")
        ml = QGridLayout(mbox)
        ml.addWidget(QLabel("method:"), 0, 0)
        self.cb_method = QComboBox(); self.cb_method.addItems(["simple","hierarchical","scotch"])
        ml.addWidget(self.cb_method, 0, 1)

        self.nx = QSpinBox(); self.nx.setRange(1, 8192); self.nx.setValue(2)
        self.ny = QSpinBox(); self.ny.setRange(1, 8192); self.ny.setValue(2)
        self.nz = QSpinBox(); self.nz.setRange(1, 8192); self.nz.setValue(2)
        ml.addWidget(QLabel("n (nx ny nz):"), 1, 0)
        row_n = QHBoxLayout(); row_n.addWidget(self.nx); row_n.addWidget(self.ny); row_n.addWidget(self.nz)
        ml.addLayout(row_n, 1, 1)

        self.delta = QDoubleSpinBox(); self.delta.setDecimals(6); self.delta.setRange(0.0, 1.0); self.delta.setValue(0.001)
        ml.addWidget(QLabel("delta:"), 2, 0); ml.addWidget(self.delta, 2, 1)

        self.cb_order = QComboBox(); self.cb_order.addItems(ORDER_OPTIONS)
        ml.addWidget(QLabel("order (hierarchical):"), 3, 0); ml.addWidget(self.cb_order, 3, 1)

        self.lbl_status = QLabel("")
        ml.addWidget(self.lbl_status, 4, 0, 1, 2)
        root.addWidget(mbox)

        row = QHBoxLayout()
        self.btn_load = QPushButton("Load existing")
        self.btn_preview = QPushButton("Preview file")
        self.btn_save = QPushButton("Save decomposeParDict")
        self.btn_close = QPushButton("Continue")
        row.addWidget(self.btn_close); row.addStretch(1)
        row.addWidget(self.btn_load); row.addWidget(self.btn_preview); row.addWidget(self.btn_save)
        root.addLayout(row)

        self.cb_method.currentTextChanged.connect(self.update_visibility)
        for w in (self.nx, self.ny, self.nz, self.spin_np):
            w.valueChanged.connect(self.validate_product)
        self.btn_load.clicked.connect(self.on_load)
        self.btn_preview.clicked.connect(self.on_preview)
        self.btn_save.clicked.connect(self.on_save)
        self.btn_close.clicked.connect(self.close)

        
        self._init_save_gate([self.spin_np, self.cb_method, self.nx, self.ny, self.nz, self.delta, self.cb_order])

        self.update_visibility()
        self.validate_product()
        center_on_screen(self)

    def update_visibility(self):
        m = self.cb_method.currentText()
        show = (m in ("simple","hierarchical"))
        self.nx.setEnabled(show); self.ny.setEnabled(show); self.nz.setEnabled(show)
        self.delta.setEnabled(show)
        self.cb_order.setEnabled(m == "hierarchical")
        if m == "scotch":
            self.lbl_status.setStyleSheet("color:#93a1a1;")
            self.lbl_status.setText("scotch: automatic graph partitioning (no n/delta/order).")
        self.validate_product()

    def validate_product(self):
        m = self.cb_method.currentText()
        if m in ("simple","hierarchical"):
            prod = self.nx.value()*self.ny.value()*self.nz.value()
            np_tot = self.spin_np.value()
            ok = (prod == np_tot)
            color = "#859900" if ok else "#b58900"
            self.lbl_status.setStyleSheet(f"color:{color};")
            self.lbl_status.setText(f"Check: nx*ny*nz = {prod}  vs numberOfSubdomains = {np_tot}")
        else:
            self.lbl_status.setStyleSheet("color:#93a1a1;")
            self.lbl_status.setText("Note: only numberOfSubdomains is required.")

    def on_load(self):
        if not self.dict_path.exists():
            QMessageBox.information(self, "Missing file", f"decomposeParDict not found:\n{self.dict_path}")
            return
        text = self.dict_path.read_text(errors="ignore")
        parsed = parse_existing_dict(text)
        if parsed["numberOfSubdomains"]:
            self.spin_np.setValue(parsed["numberOfSubdomains"])
        if parsed["method"]:
            idx = self.cb_method.findText(parsed["method"])
            if idx >= 0: self.cb_method.setCurrentIndex(idx)
        if parsed["nxyz"]:
            nx,ny,nz = parsed["nxyz"]; self.nx.setValue(nx); self.ny.setValue(ny); self.nz.setValue(nz)
        if parsed["delta"] is not None:
            self.delta.setValue(parsed["delta"])
        if parsed["order"]:
            idx = self.cb_order.findText(parsed["order"])
            if idx >= 0: self.cb_order.setCurrentIndex(idx)
        self.update_visibility(); self.validate_product()

    def _gather(self):
        m = self.cb_method.currentText()
        np_tot = self.spin_np.value()
        if m in ("simple","hierarchical"):
            nxyz = (self.nx.value(), self.ny.value(), self.nz.value())
            return np_tot, m, nxyz, float(self.delta.value()), (self.cb_order.currentText() if m == "hierarchical" else None)
        return np_tot, m, None, None, None

    def on_preview(self):
        np_tot, m, nxyz, delta, order = self._gather()
        txt = build_decompose_dict(np_tot, m, nxyz, delta, order)

        msg = QMessageBox(self)
        msg.setWindowTitle("Preview")
        msg.setTextInteractionFlags(Qt.TextSelectableByMouse)
        msg.setText(f"<pre>{txt}</pre>")

        lay = msg.layout()
        lay.addItem(QSpacerItem(900, 0, QSizePolicy.Minimum, QSizePolicy.Expanding),
                    lay.rowCount(), 0, 1, lay.columnCount())

        msg.exec_()

    def on_save(self):
        np_tot, m, nxyz, delta, order = self._gather()
        if m in ("simple","hierarchical"):
            prod = nxyz[0]*nxyz[1]*nxyz[2]
            if prod != np_tot:
                QMessageBox.warning(self, "Validation", f"nx*ny*nz = {prod} must equal numberOfSubdomains = {np_tot}.")
                return
        txt = build_decompose_dict(np_tot, m, nxyz, delta, order)
        if self.dict_path.exists():
            t0 = self.dict_path.read_text(errors="ignore")
            if "FoamFile" not in t0:
                txt = ensure_header(txt, "decomposeParDict")
        self.dict_path.parent.mkdir(parents=True, exist_ok=True)
        self.dict_path.write_text(txt)
        QMessageBox.information(self, "Saved", f"decomposeParDict written to:\n{self.dict_path}")
        self.markSaved()

def main():
    ap = argparse.ArgumentParser(description="GUI for decomposeParDict (multi-core)")
    ap.add_argument("--root", help="Project root (contains 'mesh' and 'templateCase')", default=None)
    ap.add_argument("--dict", dest="dict_path", help="Path to system/decomposeParDict (overrides --root)", default=None)
    args = ap.parse_args()

    if args.dict_path:
        dict_path = Path(args.dict_path).expanduser().resolve()
    else:
        dict_path = (Path.cwd() / "system" / "decomposeParDict").resolve()
        if not (Path.cwd() / "system").exists() and not dict_path.parent.exists():
            cli_root = Path(args.root).expanduser().resolve() if args.root else None
            repo_root = detect_repo_root(cli_root)
            dict_path = default_decompose_path(repo_root)

    set_qt_env()
    app = QApplication(sys.argv)
    apply_fusion_dark(app)

    gui = DecomposeGui(dict_path)
    if not dict_path.exists():
        QMessageBox.information(gui, "Target file not found",
                                f"decomposeParDict not found:\n{dict_path}\n\n"
                                "The file will be created on Save with a standard OpenFOAM header.")
    center_on_screen(gui)
    gui.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
