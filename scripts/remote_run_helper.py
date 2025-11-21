#!/usr/bin/env python3
# remote_run_helper.py
# Popup to choose Local vs Remote run and (if remote) generate + optionally launch:
#   - sync_case.sh  (rsync to remote)
#   - run_remote.sh (SSH direct run)
#   - run.slurm     (SLURM job)
# Rules:
# - Read solver from system/controlDict: application <solver>;
# - Read NP from system/decomposeParDict: numberOfSubdomains <N>;

import sys, os, re, subprocess
from pathlib import Path
from typing import Tuple, Optional

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,  # type: ignore
                             QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton,
                             QMessageBox, QGroupBox, QRadioButton)
from PyQt5.QtCore import Qt  # type: ignore

# --- use the shared dark theme + centering ---
try:
    from ui_theme import set_qt_env, apply_fusion_dark, center_on_screen
except Exception:
    
    def set_qt_env(): pass
    def apply_fusion_dark(app): pass
    def center_on_screen(w): pass

# ---------- helpers ----------

def read_application(case_dir: Path) -> str:
    cd = case_dir / "system" / "controlDict"
    solver = "simpleFoam"
    try:
        for ln in cd.read_text(errors="ignore").splitlines():
            m = re.match(r'^\s*application\s+(\S+)', ln)
            if m:
                solver = m.group(1).rstrip(';')
                break
    except Exception:
        pass
    return solver

def read_np(case_dir: Path) -> int:
    dpd = case_dir / "system" / "decomposeParDict"
    n = 1
    try:
        txt = dpd.read_text(errors="ignore")
        m = re.search(r'^\s*numberOfSubdomains\s+(\d+)\s*;', txt, re.MULTILINE)
        if m:
            n = max(1, int(m.group(1)))
    except Exception:
        pass
    return n

def ensure_decompose_extras(case_dir: Path) -> None:
    
    dpd = case_dir / "system" / "decomposeParDict"
    if not dpd.exists():
        return
    txt = dpd.read_text(errors="ignore")

    changed = False
    if not re.search(r'^\s*distributed\s+\S+;\s*$', txt, re.MULTILINE):
        txt = txt.rstrip() + "\n\ndistributed     no;\n"
        changed = True
    if not re.search(r'^\s*roots\s*\([^)]*\)\s*;\s*$', txt, re.MULTILINE):
        txt = txt.rstrip() + "\nroots           ();\n"
        changed = True

    if changed:
        dpd.write_text(txt)

def write_sync_script(case_dir: Path, remote: str, remote_path: str) -> Path:
    sh = case_dir / "sync_case.sh"
    sh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'rsync -azP "{case_dir}/" "{remote}:{remote_path}/"\n'
    )
    sh.chmod(0o755)
    return sh

def write_run_remote_sh(case_dir: Path, solver: str) -> Path:
    np = read_np(case_dir)
    sh = case_dir / "run_remote.sh"
    sh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "module load OpenFOAM 2>/dev/null || true\n"
        "source ${WM_PROJECT_DIR:-/etc}/bashrc 2>/dev/null || true\n"
        "echo \"[i] Running decomposePar\"\n"
        "decomposePar\n"
        "echo \"[i] Launching solver\"\n"
        f"mpirun -np {np} {solver} -parallel\n"
        "echo \"[i] Reconstructing\"\n"
        "reconstructPar\n"
    )
    sh.chmod(0o755)
    return sh

def write_run_slurm(case_dir: Path, solver: str) -> Path:
    np = read_np(case_dir)
    sl = case_dir / "run.slurm"
    sl.write_text(
        "#!/usr/bin/env bash\n"
        "#SBATCH -J of_case\n"
        "#SBATCH -t 02:00:00\n"
        f"#SBATCH -n {np}\n"
        "#SBATCH -N 1\n"
        "#SBATCH -o logs/slurm.%j.out\n"
        "#SBATCH -e logs/slurm.%j.err\n\n"
        "module load OpenFOAM 2>/dev/null || true\n"
        "source ${WM_PROJECT_DIR:-/etc}/bashrc 2>/dev/null || true\n"
        "set -euo pipefail\n"
        "mkdir -p logs\n"
        "decomposePar\n"
        f"srun {solver} -parallel\n"
        "reconstructPar\n"
    )
    sl.chmod(0o755)
    return sl

def run_ssh_command(remote: str, cmd: str) -> int:
    print(f"[..] ssh {remote} {cmd}")
    return subprocess.call(["ssh", remote, cmd])

# ---------- GUI ----------

class RemoteRunPopup(QWidget):
    def __init__(self, case_dir: Path):
        super().__init__()
        self.case_dir = case_dir
        self.setWindowTitle("Run locally or remotely")
        self.resize(640, 320)

        v = QVBoxLayout(self)

        # Local vs Remote
        sel = QGroupBox("Run location")
        hl = QHBoxLayout(sel)
        self.rb_local = QRadioButton("Local")
        self.rb_remote = QRadioButton("Remote (SSH/SLURM)")
        self.rb_remote.setChecked(True)
        hl.addWidget(self.rb_local)
        hl.addWidget(self.rb_remote)
        hl.addStretch(1)
        v.addWidget(sel)

        # Remote settings
        box = QGroupBox("Remote settings")
        gl = QGridLayout(box)

        gl.addWidget(QLabel("user@host:"), 0, 0)
        self.ed_remote = QLineEdit()
        self.ed_remote.setPlaceholderText("username@hostname (es. alice@hpc.cluster.edu)")
        gl.addWidget(self.ed_remote, 0, 1)

        gl.addWidget(QLabel("Remote case path:"), 1, 0)
        self.ed_rpath = QLineEdit()
        self.ed_rpath.setPlaceholderText("/percorso/remoto/della/case (es. /home/alice/runs/myCase)")
        gl.addWidget(self.ed_rpath, 1, 1)

        gl.addWidget(QLabel("Scheduler:"), 2, 0)
        self.cmb_sched = QComboBox()
        self.cmb_sched.addItems(["SSH (no scheduler)", "SLURM"])
        gl.addWidget(self.cmb_sched, 2, 1)

        self.chk_exec = QCheckBox("Also execute the remote run now")
        self.chk_exec.setChecked(False)
        gl.addWidget(self.chk_exec, 3, 0, 1, 2)

        v.addWidget(box)

        # Bottom row
        row = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_ok = QPushButton("OK")
        row.addWidget(self.btn_cancel); row.addStretch(1); row.addWidget(self.btn_ok)
        v.addLayout(row)

        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_ok.clicked.connect(self.on_ok)

        # Prefill from case
        self._prefill()

    def _prefill(self):
        
        self.ed_remote.setText("")
        self.ed_rpath.setText("/home/alice/runs/myCase")

    def _on_cancel(self):
        # Exit with an explicit non-success code on cancel
        print("REMOTE_HELPER:CANCEL")
        QApplication.instance().exit(1)

    def on_ok(self):
        if self.rb_local.isChecked():
            # Exit with code 0 meaning "local run"
            print("REMOTE_HELPER:LOCAL")
            QApplication.instance().exit(0)
            return

        remote = self.ed_remote.text().strip()
        rpath  = self.ed_rpath.text().strip()
        if not remote or not rpath:
            QMessageBox.warning(self, "Missing fields", "Please fill user@host and remote case path.")
            return

        # Ensure minimal keys in decomposeParDict 
        ensure_decompose_extras(self.case_dir)

        solver = read_application(self.case_dir)

        # Write scripts into case/
        self.case_dir.joinpath("logs").mkdir(parents=True, exist_ok=True)
        write_sync_script(self.case_dir, remote, rpath)
        write_run_remote_sh(self.case_dir, solver)
        write_run_slurm(self.case_dir, solver)

        # Optionally execute sync + remote launch
        if self.chk_exec.isChecked():
            # Sync
            sync_cmd = f"bash -lc 'mkdir -p {rpath}'"
            rc = run_ssh_command(remote, sync_cmd)
            if rc != 0:
                QMessageBox.critical(self, "SSH error", "Could not create remote path.")
                return
            # local rsync
            try:
                subprocess.check_call([str(self.case_dir / "sync_case.sh")])
            except subprocess.CalledProcessError as e:
                QMessageBox.critical(self, "rsync error", f"rsync failed (exit {e.returncode}).")
                return

            # Launch
            if self.cmb_sched.currentText().startswith("SLURM"):
                cmd = f"cd {rpath} && sbatch run.slurm"
            else:
                cmd = f"bash -lc 'cd {rpath} && bash run_remote.sh'"
            rc = run_ssh_command(remote, cmd)
            if rc != 0:
                QMessageBox.critical(self, "Remote launch error", "Remote launch failed.")
                return

            QMessageBox.information(self, "Done", "Remote sync and launch completed.")
        else:
            QMessageBox.information(
                self, "Scripts generated",
                "Generated:\n- sync_case.sh\n- run_remote.sh\n- run.slurm\n\n"
                "You can sync and launch them later."
            )

        print("REMOTE_HELPER:REMOTE")
        # Exit with special code 200 to signal "remote selected/launched"
        QApplication.instance().exit(200)

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Remote run helper")
    ap.add_argument("--case", required=True, help="Path to the case directory")
    args = ap.parse_args()

    case_dir = Path(args.case).resolve()
    if not case_dir.exists():
        print("Case path does not exist", file=sys.stderr)
        sys.exit(2)

   
    set_qt_env()
    app = QApplication(sys.argv)
    apply_fusion_dark(app)  
    w = RemoteRunPopup(case_dir)
    center_on_screen(w)
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
