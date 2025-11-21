#!/usr/bin/env python3
# preview3d.py
# CPU-only STL preview using Matplotlib (Qt5Agg).
# - No OpenGL required (renders via Agg).
# - Simple interactive 3D view, you can rotate/zoom with the mouse.
#
# Deps: PyQt5, matplotlib, numpy, numpy-stl

import sys
from pathlib import Path
import numpy as np  # type: ignore
from stl import mesh  # type: ignore

from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QMessageBox  # type: ignore

# Matplotlib (Qt5Agg backend)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas  # type: ignore
from matplotlib.figure import Figure  # type: ignore
# 3D collection for triangle meshes
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # type: ignore

from ui_theme import set_qt_env, apply_fusion_dark, center_on_screen


def _triangles_from_stl(stl_path: Path):
    m = mesh.Mesh.from_file(str(stl_path))
    # m.vectors: (nTri, 3, 3)
    tris = m.vectors.copy()
    return tris


class _Matplot3DCanvas(FigureCanvas):
    def __init__(self):
        fig = Figure()
        super().__init__(fig)
        self.ax = fig.add_subplot(111, projection="3d")

        
        fig.patch.set_facecolor((45/255, 45/255, 48/255))
        self.ax.set_facecolor((37/255, 37/255, 38/255))
        self.ax.grid(True, linewidth=0.6, color=(0.35, 0.35, 0.35))  # slightly darker grid for contrast

        
        self.ax.set_box_aspect((3.0, 1.0, 1.0))
        # -------------------------------------------------------------------------------------

        self._last_limits = None

        # Scroll wheel zoom handler
        self.mpl_connect("scroll_event", self._on_scroll)

    def plot_tris(self, tris: np.ndarray):
        # tris: (n, 3, 3)
        poly = Poly3DCollection(tris, linewidths=0.4, alpha=0.95)
        # Higher contrast object vs grid
        poly.set_edgecolor((0.92, 0.92, 0.92))
        poly.set_facecolor((0.85, 0.85, 0.85))
        self.ax.add_collection3d(poly)

        
        mins = tris.reshape(-1, 3).min(axis=0)
        maxs = tris.reshape(-1, 3).max(axis=0)
        center = (mins + maxs) / 2.0
        span = (maxs - mins).max()
        if span <= 0:
            span = 1.0

        
        r_base = span * 1.8
        rx = r_base * 4.0   
        ry = r_base * 1.0
        rz = r_base * 1.0
        self.ax.set_xlim(center[0] - rx, center[0] + rx)
        self.ax.set_ylim(center[1] - ry, center[1] + ry)
        self.ax.set_zlim(center[2] - rz, center[2] + rz)

        self._remember_limits()

        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.set_zlabel("Z")
        self.draw()

    # --- Zoom with mouse (axis rescale automatically) ---
    def _on_scroll(self, event):
        step = 0.9 if event.button == 'up' else 1.1
        self._zoom(step)

    def _remember_limits(self):
        ax = self.ax
        self._last_limits = (
            ax.get_xlim3d(), ax.get_ylim3d(), ax.get_zlim3d()
        )

    def _zoom(self, factor):
        ax = self.ax
        (x0, x1), (y0, y1), (z0, z1) = ax.get_xlim3d(), ax.get_ylim3d(), ax.get_zlim3d()
        cx = 0.5 * (x0 + x1)
        cy = 0.5 * (y0 + y1)
        cz = 0.5 * (z0 + z1)

        rx = (x1 - x0) * 0.5 * factor
        ry = (y1 - y0) * 0.5 * factor
        rz = (z1 - z0) * 0.5 * factor

        ax.set_xlim3d(cx - rx, cx + rx)
        ax.set_ylim3d(cy - ry, cy + ry)
        ax.set_zlim3d(cz - rz, cz + rz)
        self.draw()


class STLPreview(QWidget):
    """
    Drop-in replacement class name for preview3d.STLPreview,
    implemented with Matplotlib (CPU-only).
    """
    def __init__(self, stl_path: Path, title: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title or "3D Preview (CPU)")
        self.resize(900, 640)

        self.canvas = _Matplot3DCanvas()
        lay = QVBoxLayout(self)
        lay.addWidget(self.canvas)

        try:
            tris = _triangles_from_stl(stl_path)
        except Exception as e:
            QMessageBox.critical(self, "STL error", str(e))
            return

        self.canvas.plot_tris(tris)
        center_on_screen(self)


def _main():
    import argparse
    ap = argparse.ArgumentParser(description="CPU-only 3D preview for STL (Matplotlib)")
    ap.add_argument("--stl", required=True, help="Path to STL file")
    ap.add_argument("--title", help="Custom window title", default=None)
    args = ap.parse_args()

    p = Path(args.stl).expanduser().resolve()
    if not p.exists():
        print(f"Missing file: {p}", file=sys.stderr)
        sys.exit(2)

    set_qt_env()
    # Force the Qt5Agg backend (CPU) if not already set
    import matplotlib  # type: ignore
    if matplotlib.get_backend().lower() != "qt5agg":
        matplotlib.use("Qt5Agg", force=True)

    app = QApplication(sys.argv)
    apply_fusion_dark(app)
    w = STLPreview(p, title=args.title)
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    _main()
