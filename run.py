#!/usr/bin/env python3
"""
Launcher popup: choose between
- Mesh pipeline (mesh_pipeline_gui.py)
- Turbulence setup (turbulence_widget.py)

Opens a small Yes/No style dialog using PyQt5; falls back to console if GUI fails.
"""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SCRIPTS   = REPO_ROOT / "scripts"

def ask_choice_popup(title: str, question: str, yes_label="Mesh pipeline", no_label="Turbulence setup") -> bool:
    """Return True if user chooses 'yes_label' (mesh pipeline), False if 'no_label' (turbulence setup)."""
    code = r"""
import sys
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt
QApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)
app = QApplication(sys.argv)
box = QMessageBox()
box.setWindowTitle(%r)
box.setText(%r)
yes = box.addButton(%r, QMessageBox.YesRole)
no  = box.addButton(%r, QMessageBox.NoRole)
box.setDefaultButton(yes)
box.exec_()
print("YES" if box.clickedButton() is yes else "NO")
""" % (title, question, yes_label, no_label)

    
    env1 = dict(os.environ,
                QT_QPA_PLATFORM='wayland',
                QT_OPENGL='software',
                LIBGL_ALWAYS_SOFTWARE='1',
                QT_LOGGING_RULES='qt.qpa.*=false')
    try:
        p = subprocess.run(['python3', '-c', code], cwd=REPO_ROOT, env=env1,
                           capture_output=True, text=True)
        out = (p.stdout or "").strip()
    except Exception:
        out = ""

    if out not in ("YES", "NO"):
        env2 = dict(os.environ,
                    QT_QPA_PLATFORM='xcb',
                    QT_OPENGL='software',
                    QT_XCB_GL_INTEGRATION='none',
                    LIBGL_ALWAYS_SOFTWARE='1',
                    QT_LOGGING_RULES='qt.qpa.*=false')
        try:
            p2 = subprocess.run(['python3', '-c', code], cwd=REPO_ROOT, env=env2,
                                capture_output=True, text=True)
            out = (p2.stdout or "").strip()
        except Exception:
            out = ""

    if out in ("YES", "NO"):
        return out == "YES"

    # Console fallback
    ans = input(f"{title}: {question}\n[Y] {yes_label} / [N] {no_label} [Y/n]: ").strip().lower()
    return ans in ("", "y", "yes")

def main():
    title = "Choose pipeline"
    question = ("What do you want to open?\n"
                "• Mesh pipeline (blockMesh/snappyHexMesh GUIs)\n"
                "• Turbulence setup (RANS/LES model dialog)")

    choose_mesh = ask_choice_popup(title, question)

    if choose_mesh:
        print("[..] Launching mesh pipeline GUI…")
        
        cmd = ["python3", str(SCRIPTS / "mesh_pipeline_gui.py")]
    else:
        print("[..] Launching turbulence setup…")
        cmd = ["python3", str(SCRIPTS / "turbulence_widget.py")]

    subprocess.run(cmd, cwd=REPO_ROOT, check=True)

if __name__ == "__main__":
    main()
