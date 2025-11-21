#!/usr/bin/env python3
# pyright: reportMissingImports=false
# orient_widget.py
# Interactive STL orientation & positioning:
# - Rotate around X/Y/Z or custom axis, ±90° quick buttons
# - Align longest principal axis to X/Y/Z
# - Embedded 3D Preview (uses preview3d.STLPreview)
# - Save oriented STL (creates new file)
# - Generate blockMeshDict using the oriented STL (calls generate_blockMeshDict.py)
#
# Dependencies: PyQt5, numpy, numpy-stl, matplotlib (via preview3d.py)
 

from pathlib import Path
import sys, math, subprocess, tempfile, os
THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import numpy as np  # type: ignore
from stl import mesh  # type: ignore

from PyQt5.QtWidgets import (  # type: ignore
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QGroupBox, QRadioButton, QDoubleSpinBox, QPushButton,
    QMessageBox, QFileDialog, QLineEdit
)
from PyQt5.QtCore import Qt  # type: ignore

QApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)

from ui_theme import set_qt_env, apply_fusion_dark, center_on_screen
from tempfile import NamedTemporaryFile


def rodrigues(axis_vec, angle_rad):
    k = np.asarray(axis_vec, dtype=float)
    n = np.linalg.norm(k)
    if n == 0:
        raise ValueError("Axis must be non-zero")
    k /= n
    kx, ky, kz = k
    K = np.array([[0, -kz, ky],
                  [kz, 0, -kx],
                  [-ky, kx, 0]], dtype=float)
    I = np.eye(3)
    return I + math.sin(angle_rad) * K + (1 - math.cos(angle_rad)) * (K @ K)


def load_vertices(stl_path: Path) -> np.ndarray:
    m = mesh.Mesh.from_file(str(stl_path))
    return m.vectors.reshape(-1, 3).copy()


def save_vertices_as_stl(in_path: Path, verts: np.ndarray, out_path: Path):
    """
    Save STL triangles using the original file as template into 'out_path'.
    """
    m = mesh.Mesh.from_file(str(in_path))
    m.vectors[:] = verts.reshape((-1, 3, 3))
    out = out_path
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        if out.exists():
            out.unlink()
    except Exception:
        pass
    m.save(str(out))
    return out


def pca_longest_axis(pts: np.ndarray) -> np.ndarray:
    P = pts - pts.mean(axis=0)
    _, _, Vt = np.linalg.svd(P, full_matrices=False)
    return Vt[0]


def rotation_from_a_to_b(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    s = np.linalg.norm(v)
    c = np.dot(a, b)
    if s == 0:
        return np.eye(3) if c > 0 else -np.eye(3)
    vx, vy, vz = v
    K = np.array([[0, -vz, vy], [vz, 0, -vx], [-vy, vx, 0]])
    R = np.eye(3) + K + K @ K * ((1 - c) / (s**2))
    return R


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


class OrientWidget(QWidget, SaveGateMixin):
    def __init__(self, stl_path: Path, generate_script: Path = None, template_path: Path = None, output_decomp: Path = None):
        super().__init__()
        self.stl_path = stl_path.resolve()
        self.generate_script = generate_script
        self.template_path = template_path
        self.output_decomp = output_decomp

        self._preview_proc: subprocess.Popen | None = None
        self._preview_tmp: Path | None = None

        self.setWindowTitle("STL Orientation & Positioning")
        self.resize(900, 680)

        self.case_dir = Path.cwd().resolve()
        self.tri_dir = (self.case_dir / "constant" / "triSurface")
        self.default_out_dir = self.tri_dir if self.tri_dir.exists() else self.stl_path.parent

        root = QVBoxLayout(self)

        info = QLabel(f"Input STL: {self.stl_path}")
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(info)

        g1 = QGroupBox("Rotation")
        gl = QGridLayout(g1)
        gl.setHorizontalSpacing(6)
        gl.setVerticalSpacing(6)

        self.rb_ax_x = QRadioButton("Axis X (1,0,0)")
        self.rb_ax_y = QRadioButton("Axis Y (0,1,0)")
        self.rb_ax_z = QRadioButton("Axis Z (0,0,1)")
        self.rb_ax_c = QRadioButton("Custom axis (vx, vy, vz)")
        self.rb_ax_x.setChecked(True)

        row_rad = QHBoxLayout()
        row_rad.setSpacing(8)
        row_rad.addWidget(self.rb_ax_x)
        row_rad.addWidget(self.rb_ax_y)
        row_rad.addWidget(self.rb_ax_z)
        row_rad.addWidget(self.rb_ax_c)
        row_rad.addStretch(1)
        gl.addLayout(row_rad, 0, 0, 1, 6)

        self.vx = QDoubleSpinBox(); self.vx.setRange(-1e6, 1e6); self.vx.setDecimals(6); self.vx.setValue(0.0)
        self.vy = QDoubleSpinBox(); self.vy.setRange(-1e6, 1e6); self.vy.setDecimals(6); self.vy.setValue(0.0)
        self.vz = QDoubleSpinBox(); self.vz.setRange(-1e6, 1e6); self.vz.setDecimals(6); self.vz.setValue(1.0)
        gl.addWidget(QLabel("vx:"), 1, 0); gl.addWidget(self.vx, 1, 1)
        gl.addWidget(QLabel("vy:"), 1, 2); gl.addWidget(self.vy, 1, 3)
        gl.addWidget(QLabel("vz:"), 1, 4); gl.addWidget(self.vz, 1, 5)

        self.angle = QDoubleSpinBox(); self.angle.setRange(-1e6, 1e6); self.angle.setDecimals(3); self.angle.setValue(0.0)
        gl.addWidget(QLabel("Angle (deg):"), 2, 0); gl.addWidget(self.angle, 2, 1)
        row_quick = QHBoxLayout()
        self.btn_p90 = QPushButton("+90°"); self.btn_m90 = QPushButton("-90°")
        row_quick.addWidget(self.btn_p90); row_quick.addWidget(self.btn_m90); row_quick.addStretch(1)
        gl.addLayout(row_quick, 2, 2, 1, 4)

        for col in (1, 3, 5):
            gl.setColumnStretch(col, 1)
        for w in (self.vx, self.vy, self.vz, self.angle):
            w.setMinimumWidth(110)

        root.addWidget(g1)

        g2 = QGroupBox("Align longest axis (PCA)")
        g2l = QHBoxLayout(g2)
        self.btn_align_x = QPushButton("Align → X")
        self.btn_align_y = QPushButton("Align → Y")
        self.btn_align_z = QPushButton("Align → Z")
        g2l.setSpacing(8)
        g2l.addWidget(self.btn_align_x); g2l.addWidget(self.btn_align_y); g2l.addWidget(self.btn_align_z); g2l.addStretch(1)
        root.addWidget(g2)

        paths = QHBoxLayout()
        self.out_edit = QLineEdit(str(self._suggest_out_path()))
        self.out_edit.setReadOnly(True)
        self.out_edit.setToolTip("Output path is fixed to <name_stl>_oriented.stl.")
        paths.addWidget(QLabel("Output STL:")); paths.addWidget(self.out_edit)
        root.addLayout(paths)

        row2 = QHBoxLayout()
        self.btn_preview = QPushButton("3D Preview")
        self.btn_apply = QPushButton("Apply & Save STL")
        self.btn_close = QPushButton("Continue")
        row2.addWidget(self.btn_close); row2.addStretch(1)
        row2.addWidget(self.btn_preview); row2.addWidget(self.btn_apply)
        root.addLayout(row2)

        self.btn_p90.clicked.connect(lambda: self.angle.setValue(self.angle.value() + 90.0))
        self.btn_m90.clicked.connect(lambda: self.angle.setValue(self.angle.value() - 90.0))
        self.btn_align_x.clicked.connect(lambda: self._align_to_axis(np.array([1, 0, 0])))
        self.btn_align_y.clicked.connect(lambda: self._align_to_axis(np.array([0, 1, 0])))
        self.btn_align_z.clicked.connect(lambda: self._align_to_axis(np.array([0, 0, 1])))
        self.btn_preview.clicked.connect(self._preview)
        self.btn_apply.clicked.connect(self._apply_and_save)
        self.btn_close.clicked.connect(self.close)

        
        self._init_save_gate([
            self.rb_ax_x, self.rb_ax_y, self.rb_ax_z, self.rb_ax_c,
            self.vx, self.vy, self.vz, self.angle,
            self.btn_p90, self.btn_m90, self.btn_align_x, self.btn_align_y, self.btn_align_z
        ])

        center_on_screen(self)

    def _axis_vector(self):
        if self.rb_ax_x.isChecked(): return np.array([1.0, 0.0, 0.0])
        if self.rb_ax_y.isChecked(): return np.array([0.0, 1.0, 0.0])
        if self.rb_ax_z.isChecked(): return np.array([0.0, 0.0, 1.0])
        return np.array([self.vx.value(), self.vy.value(), self.vz.value()])

    def _suggest_out_path(self):
        stem = self.stl_path.stem + "_oriented" + self.stl_path.suffix
        return (self.default_out_dir / stem)

    def _transform_points(self, pts: np.ndarray) -> np.ndarray:
        P = pts.copy()
        pivot = P.mean(axis=0)
        P -= pivot
        ang = math.radians(float(self.angle.value()))
        if abs(ang) > 1e-15:
            R = rodrigues(self._axis_vector(), ang)
            P = P @ R.T
        P += pivot
        return P

    def _align_to_axis(self, target_axis: np.ndarray):
        try:
            pts = load_vertices(self.stl_path)
        except Exception as e:
            QMessageBox.critical(self, "STL error", str(e))
            return
        a = pca_longest_axis(pts)
        R = rotation_from_a_to_b(a, target_axis)
        tr = np.clip((np.trace(R) - 1) / 2, -1, 1)
        angle = math.degrees(math.acos(tr))
        rx = R[2, 1] - R[1, 2]; ry = R[0, 2] - R[2, 0]; rz = R[1, 0] - R[0, 1]
        axis = np.array([rx, ry, rz]); n = np.linalg.norm(axis)
        if n < 1e-14:
            axis = target_axis
        else:
            axis /= n
        self.rb_ax_c.setChecked(True)
        self.vx.setValue(float(axis[0])); self.vy.setValue(float(axis[1])); self.vz.setValue(float(axis[2]))
        self.angle.setValue(float(angle))
        QMessageBox.information(self, "Align",
                                "Filled rotation controls to align the longest STL axis to the chosen axis.\n"
                                "You can Preview or Apply now.")

    def _preview(self):
        self._kill_preview()
        try:
            pts = load_vertices(self.stl_path)
            P2 = self._transform_points(pts)
            tmp = Path(NamedTemporaryFile(prefix="stl_preview_", suffix=".stl", delete=False).name)
            out = save_vertices_as_stl(self.stl_path, P2, tmp)
            self._preview_tmp = out
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return
        try:
            env = os.environ.copy()
            env.update({
                "QT_QPA_PLATFORM": "xcb",
                "QT_OPENGL": "software",
                "LIBGL_ALWAYS_SOFTWARE": "1",
                "QT_XCB_GL_INTEGRATION": "none",
                "MPLBACKEND": "Qt5Agg",
                "QT_LOGGING_RULES": "qt.qpa.*=false",
            })
            title = f"3D Preview — {self.stl_path.name}"
            self._preview_proc = subprocess.Popen(
                [sys.executable, str(THIS_DIR / "preview3d.py"), "--stl", str(out), "--title", title],
                cwd=self.case_dir,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            QMessageBox.information(
                self, "Preview unavailable",
                "Could not launch the external 3D preview process.\n\n"
                f"Details: {e}\n"
                "Make sure 'matplotlib' is installed."
            )

    def _kill_preview(self):
        try:
            if self._preview_proc and (self._preview_proc.poll() is None):
                self._preview_proc.terminate()
        except Exception:
            pass
        self._preview_proc = None
        if self._preview_tmp and self._preview_tmp.exists():
            try:
                self._preview_tmp.unlink()
            except Exception:
                pass
        self._preview_tmp = None

    def closeEvent(self, event):
        self._kill_preview()
        return super().closeEvent(event)

    def _apply_and_save(self):
        try:
            pts = load_vertices(self.stl_path)
            P2 = self._transform_points(pts)
            out = save_vertices_as_stl(self.stl_path, P2, Path(self.out_edit.text()).expanduser().resolve())
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return
        QMessageBox.information(self, "Saved", f"Oriented STL written:\n{out}")
        self.markSaved()


def main():
    import argparse
    ap = argparse.ArgumentParser(description="STL orientation widget")
    ap.add_argument("--stl", required=True, help="Path to input STL")
    ap.add_argument("--gen", dest="generate_script", help="Path to generate_blockMeshDict.py", default=None)
    ap.add_argument("--tpl", dest="template_path", help="Path to template blockMeshDict", default=None)
    ap.add_argument("--outbm", dest="output_bm", help="Path to write blockMeshDict", default=None)
    args = ap.parse_args()

    stl = Path(args.stl).expanduser().resolve()
    if not stl.exists():
        print(f"Missing STL: {stl}", file=sys.stderr)
        sys.exit(2)

    set_qt_env()
    app = QApplication(sys.argv)
    apply_fusion_dark(app)

    w = OrientWidget(
        stl_path=stl,
        generate_script=(Path(args.generate_script).expanduser().resolve() if args.generate_script else None),
        template_path=(Path(args.template_path).expanduser().resolve() if args.template_path else None) if args.template_path else None,
        output_decomp=(Path(args.output_bm).expanduser().resolve() if args.output_bm else None)
    )
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
