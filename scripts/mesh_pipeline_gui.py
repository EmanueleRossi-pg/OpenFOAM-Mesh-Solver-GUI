#!/usr/bin/env python3
"""
Single-case OpenFOAM Meshing & Simulation Pipeline in Python
- All dictionary edits are handled via GUI tools (no terminal prompts).
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
import argparse
import sys  # needed for sys.executable (for helper invocations)

# -----------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------
REPO_ROOT     = Path(__file__).resolve().parent.parent
SCRIPT_DIR    = REPO_ROOT / 'scripts'
INPUT_DIR     = REPO_ROOT / 'inputSTL'
MESH_TMPL     = REPO_ROOT / 'mesh'
SCRIPTS       = REPO_ROOT / 'scripts'
TEMPLATE_CASE = REPO_ROOT / 'templateCase'
CASE          = REPO_ROOT / 'case'

# --- keep Qt/GL noise out of the terminal ---
CASE_LOGS = CASE / 'logs'
CASE_LOGS.mkdir(parents=True, exist_ok=True)

# 1) Silence Qt platform/plugin chatter
os.environ.setdefault('QT_LOGGING_RULES', 'qt.qpa.*=false;qt.glx.*=false')
os.environ.setdefault('QT_OPENGL', 'software')
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')

# 2) Redirect the OS-level stderr 
try:
    _fd2 = open(CASE_LOGS / 'log_pipeline_stderr.txt', 'a')
    os.dup2(_fd2.fileno(), 2)
except Exception:
    pass

IMPORT_SCRIPT   = SCRIPTS / 'import_geometry.py'
BMD_SCRIPT      = SCRIPTS / 'generate_blockMeshDict.py'
CASE_SCRIPT     = SCRIPTS / 'case_structure.py'
SNAPSHOT_SCRIPT = SCRIPTS / 'mesh_snapshot.py'     
REMOTE_HELPER   = SCRIPTS / 'remote_run_helper.py'  

# ---------- terminal icons ----------
START_ICON = "[..]"
DONE_ICON  = "[OK]"
INFO_ICON  = "[i]"
WARN_ICON  = "[!]"
ERR_ICON   = "[x]"
# ------------------------------------------------

# --- unified pipeline exit banner (SUCCESS / FAILURE) ---
def _pipeline_banner(ok: bool, where: str = "PIPELINE"):
    """
    Print a single, all-caps banner depending on success or failure.
    Use ok=True only when the whole pipeline actually finished successfully.
    """
    if ok:
        print(f"{where} COMPLETED SUCCESSFULLY!")
    else:
        print(f"{where} FAILED! SEE LOGS FOR DETAILS.")
# ---------------------------------------------------------

# -----------------------------------------------------------------
# CLI ARGUMENTS
# -----------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(description="OpenFOAM meshing & simulation pipeline")
    ap.add_argument(
        "--with-orient",
        action="store_true",
        help="Open the STL orientation GUI (orient_widget.py). Disabled by default."
    )
    return ap.parse_args()

# -----------------------------------------------------------------
# UTILS
# -----------------------------------------------------------------
def print_section(title: str):
    print(f"\n{'='*60}\n==> {title}\n{'='*60}")

def run_and_log(cmd: str, cwd: Path, log_file: str, display_cmd: str | None = None):
    """Run a shell command and write stdout/stderr to CASE/logs/<log_file>.
    If display_cmd is provided, print that instead of the actual command (for cleaner logs)."""
    logs_dir = cwd / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / log_file
    shown = display_cmd if display_cmd is not None else cmd
    print(f"{START_ICON} Running in {cwd.name}: {shown}")
    with open(log_path, 'wb') as log:
        proc = subprocess.run(cmd, cwd=cwd, shell=True, stdout=log, stderr=log)
        proc.check_returncode()
    print(f"{DONE_ICON} Completed: {shown}")

def _checkmesh_ok(log_path: Path) -> bool:
    try:
        txt = log_path.read_text(errors="ignore")
    except Exception:
        return False
    if re.search(r"\bMesh\s+OK\b", txt):
        return True
    if re.search(r"\bFailed\b", txt, re.IGNORECASE):
        return False
    return False

def ask_yes_no_popup(title: str, message: str, env_gui: dict) -> bool:
    
    code = r"""
import sys
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt
QApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)
app = QApplication(sys.argv)
box = QMessageBox()
box.setWindowTitle(%r)
box.setText(%r)
box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
box.setDefaultButton(QMessageBox.Yes)
ret = box.exec_()
print("YES" if ret == QMessageBox.Yes else "NO")
""" % (title, message)

    # 1) attempt with provided env (Wayland)
    try:
        p = subprocess.run(['python3', '-c', code], cwd=CASE, env=env_gui,
                           capture_output=True, text=True)
        out = (p.stdout or "").strip()
    except Exception:
        out = ""

    if out not in ("YES", "NO"):
        # 2) retry with XCB fallback (software GL)
        env2 = dict(env_gui,
                    QT_QPA_PLATFORM='xcb',
                    QT_OPENGL='software',
                    QT_XCB_GL_INTEGRATION='none',
                    LIBGL_ALWAYS_SOFTWARE='1',
                    QT_LOGGING_RULES='qt.qpa.*=false')
        try:
            p2 = subprocess.run(['python3', '-c', code], cwd=CASE, env=env2,
                                capture_output=True, text=True)
            out = (p2.stdout or "").strip()
        except Exception:
            out = ""

    if out in ("YES", "NO"):
        return out == "YES"

    # 3) console fallback
    ans = input(f"{title}: {message} [y/N]: ").strip().lower()
    return ans == 'y'

def parse_number_of_subdomains(decompose_dict: Path) -> int:
    """Return numberOfSubdomains from decomposeParDict, or 1 if not found."""
    try:
        txt = decompose_dict.read_text(errors="ignore")
    except Exception:
        return 1
    m = re.search(r'^\s*numberOfSubdomains\s+(\d+)\s*;', txt, re.MULTILINE)
    return int(m.group(1)) if m else 1

def clean_for_snappy_retry(case_dir: Path):
    """
    Clean products from a previous snappy run but KEEP the base blockMesh.
    - Keep constant/polyMesh (background mesh) to avoid rerunning blockMesh.
    - Remove processor* directories and numeric time directories.
    """
    for p in case_dir.glob('processor*'):
        shutil.rmtree(p, ignore_errors=True)
    for tdir in case_dir.iterdir():
        if tdir.is_dir() and tdir.name not in ('0', 'constant', 'system'):
            if re.fullmatch(r'\d+(\.\d+)?', tdir.name):
                shutil.rmtree(tdir, ignore_errors=True)

# --- sync 0/* with boundary patches  ----------------
import re as _re_for_sync
from pathlib import Path as _Path_for_sync

_PATCHTYPE_TO_FIELD = {
    'symmetryPlane': 'symmetryPlane',
    'symmetry': 'symmetry',
    'empty': 'empty',
    'wedge': 'wedge',
    'cyclic': 'cyclic',
    'cyclicAMI': 'cyclicAMI',
}

_WALL_BC = {'k':'kqRWallFunction','epsilon':'epsilonWallFunction','omega':'omegaWallFunction',
            'nut':'nutkWallFunction','nuTilda':'zeroGradient'}

def _iter_patches(boundary_text: str):
    for m in _re_for_sync.finditer(r'^\s*([A-Za-z0-9_.:-]+)\s*\{([^}]*)\}', boundary_text, flags=_re_for_sync.M|_re_for_sync.S):
        name = m.group(1)
        body = m.group(2)
        tm = _re_for_sync.search(r'\btype\s+([A-Za-z0-9_]+)\s*;', body)
        ptype = tm.group(1) if tm else 'patch'
        yield name, ptype

def _ensure_patch_block(field_text: str, patch: str, bc_type: str) -> str:
    m = _re_for_sync.search(r'\bboundaryField\s*\{', field_text)
    if not m:
        return field_text.rstrip()+f"\nboundaryField\n{{\n    {patch}\n    {{\n        type {bc_type};\n        value uniform 0;\n    }}\n}}\n"
    i = field_text.find('{', m.end()-1); depth=1; j=i+1
    while j < len(field_text) and depth>0:
        depth += (field_text[j]=='{') - (field_text[j]=='}'); j+=1
    bf_start, bf_end = m.start(), j
    bf = field_text[bf_start:bf_end]
    if _re_for_sync.search(rf'^\s*{_re_for_sync.escape(patch)}\s*\{{', bf, flags=_re_for_sync.M):
        return field_text  
    bf2 = bf[:-1]+f"    {patch}\n    {{\n        type {bc_type};\n        value uniform 0;\n    }}\n"+bf[-1:]
    return field_text[:bf_start]+bf2+field_text[bf_end:]

def sync_zero_fields_with_boundary(case_dir: _Path_for_sync):
    bpath = case_dir/'constant'/'polyMesh'/'boundary'
    if not bpath.exists():
        return
    btxt = bpath.read_text(errors='ignore')
    patches = list(_iter_patches(btxt))
    zdir = case_dir/'0'
    if not zdir.exists():
        return
    for f in zdir.iterdir():
        if not f.is_file():
            continue
        try:
            s = f.read_text(errors='ignore')
            for pname, ptype in patches:
                if ptype == 'wall' and f.name in _WALL_BC:
                    bc = _WALL_BC[f.name]
                else:
                    bc = _PATCHTYPE_TO_FIELD.get(ptype, 'zeroGradient')
                s = _ensure_patch_block(s, pname, bc)
            f.write_text(s)
        except Exception:
            pass
# ---------------------------------------------------------------------------

# --- read current phase flags from snappyHexMeshDict -------------------
def _read_phase_flags(snappy_file: Path) -> dict:
    """
    Return {'castellated': bool, 'snap': bool, 'layers': bool}
    by reading top-level booleans from snappyHexMeshDict.
    """
    flags = {'castellated': True, 'snap': True, 'layers': True}
    try:
        txt = snappy_file.read_text(errors="ignore")
    except Exception:
        return flags
    def _get(key: str, default: bool) -> bool:
        m = re.search(rf'^\s*{key}\s+(true|false)\s*;', txt, flags=re.MULTILINE)
        return (m.group(1) == 'true') if m else default
    flags['castellated'] = _get('castellatedMesh', flags['castellated'])
    flags['snap']        = _get('snap',            flags['snap'])
    flags['layers']      = _get('addLayers',       flags['layers'])
    return flags
# ---------------------------------------------------------------------------

# --------- sync + normalization helpers for system dictionaries -----------
def _normalize_text_file(path: Path):
    """Strip UTF-8 BOM and convert CRLF to LF."""
    try:
        data = path.read_bytes()
    except Exception:
        return
    if data.startswith(b'\xef\xbb\xbf'):
        data = data[3:]
    data = data.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
    try:
        text = data.decode('utf-8', errors='strict')
    except Exception:
        path.write_bytes(data)
        return
    path.write_text(text, encoding='utf-8')

def normalize_root_system_files(case_dir: Path):
    targets = [case_dir/'system'/'fvSolution',
               case_dir/'system'/'fvSchemes',
               case_dir/'system'/'controlDict']
    for f in targets:
        if f.is_file():
            _normalize_text_file(f)
    

def normalize_processor_system_files(case_dir: Path):
    for f in case_dir.glob('processor*/system/fvSolution'):
        if f.is_file():
            _normalize_text_file(f)
    

def sync_system_to_processors(case_dir: Path):
    """
    Ensure every processor*/system has an exact copy of the root system/.
    """
    src = case_dir / 'system'
    if not src.is_dir():
        print(f"{WARN_ICON} No 'system' directory at case root; skipping sync.")
        return
    procs = sorted(p for p in case_dir.glob('processor*') if p.is_dir())
    if not procs:
        print(f"{INFO_ICON} No processor* directories found; skipping sync.")
        return
    for p in procs:
        dst = p / 'system'
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)
    

def clean_parallel_env(case_dir: Path):
    """Remove processor* and numeric time directories in the case root."""
    removed = 0
    for p in case_dir.glob('processor*'):
        shutil.rmtree(p, ignore_errors=True); removed += 1
    for tdir in case_dir.iterdir():
        if tdir.is_dir() and tdir.name not in ('0', 'constant', 'system'):
            if re.fullmatch(r'\d+(\.\d+)?', tdir.name):
                shutil.rmtree(tdir, ignore_errors=True); removed += 1
    if removed:
        print(f"{DONE_ICON} Cleaned previous multi-core/time artifacts ({removed} directories).")
    else:
        print(f"{INFO_ICON} No previous multi-core/time directories to clean.")
# ---------------------------------------------------------------------------

# -----------------------------------------------------------------
# MAIN PIPELINE
# -----------------------------------------------------------------
def main():
    try:
        args = parse_args()
        os.chdir(SCRIPT_DIR)

        # Detect a single STL in inputSTL
        stl_files = list(INPUT_DIR.glob('*.stl'))
        if not stl_files:
            print(f"{ERR_ICON} No .stl files found in {INPUT_DIR}")
            _pipeline_banner(False, "MESH PIPELINE")
            return
        if len(stl_files) > 1:
            print(f"{WARN_ICON} Multiple .stl files found, using first: {stl_files[0].name}")
        INPUT_STL = stl_files[0]

        # 1) Prepare case directory (clean/create)
        print_section("1. Preparing case directory")
        if CASE.exists():
            print(f"{INFO_ICON} 'case' directory already exists. Keeping it.")
        else:
            CASE.mkdir(parents=True, exist_ok=True)
            print(f"{DONE_ICON} Case directory created.")

        (CASE / 'logs').mkdir(parents=True, exist_ok=True)

        # 2) Generate case structure
        print_section(f"2. Generating case structure for {INPUT_STL.name}")
        if (CASE / 'system').exists() and (CASE / '0').exists() and (CASE / 'constant').exists():
            print(f"{INFO_ICON} case/ structure already present. Skipping case_structure.py.")
            ready_line = None
        else:
            
            cs = subprocess.run(
                ['python3', str(CASE_SCRIPT)],
                check=True, capture_output=True, text=True
            )
            ready_line = None
            if cs.stdout:
                for line in cs.stdout.splitlines():
                    if "case ready" in line:
                        ready_line = line.replace(" case ready from ", " case ready for ")
                        
                    else:
                        print(line)
            if cs.stderr:
                print(cs.stderr, end="")
            print(f"{DONE_ICON} Case structure generated for {INPUT_STL.name}")

        foamfile = CASE / f"{CASE.name}.foam"
        if not foamfile.exists():
            foamfile.touch()
            print(f"{DONE_ICON} Created foam file: {foamfile.name}")

        # Copy STL into case/constant/triSurface
        tri_surf = CASE / 'constant' / 'triSurface'
        tri_surf.mkdir(parents=True, exist_ok=True)
        case_stl = tri_surf / INPUT_STL.name
        if case_stl.resolve() != INPUT_STL.resolve():
            shutil.copy2(INPUT_STL, case_stl)
            print(f"{DONE_ICON} Copied STL into case triSurface: {case_stl.name}")

        
        try:
            if ready_line:
                print(ready_line)
        except NameError:
            pass

        # -------------------- ORIENTATION / POSITIONING GUI --------------------
        print_section("2b. STL orientation")
        env_gui_wayland = dict(os.environ,
            QT_QPA_PLATFORM='wayland',
            QT_OPENGL='software',
            LIBGL_ALWAYS_SOFTWARE='1',
            QT_LOGGING_RULES='qt.qpa.*=false'
        )
        env_gui_xcb = dict(os.environ,
            QT_QPA_PLATFORM='xcb',
            QT_OPENGL='software',
            QT_XCB_GL_INTEGRATION='egl',
            LIBGL_ALWAYS_SOFTWARE='1',
            QT_LOGGING_RULES='qt.qpa.*=false'
        )

        run_orient = args.with_orient or ask_yes_no_popup(
            "STL orientation",
            "Do you want to open the STL orientation GUI (orient_widget.py) before blockMesh?",
            env_gui_wayland
        )

        if run_orient:
            tpl_candidates = [
                (MESH_TMPL / 'blockMeshDict'),
                (TEMPLATE_CASE / 'system' / 'blockMeshDict'),
            ]
            tpl_bmd = next((p for p in tpl_candidates if p.exists()), None)
            cmd = ['python3', str(SCRIPTS / 'orient_widget.py'),
                   '--stl', str(case_stl)]
            log_ow = CASE / 'logs' / 'log_orient_widget.txt'
            log_ow.parent.mkdir(parents=True, exist_ok=True)
            with open(log_ow, 'wb') as lg:
                try:
                    subprocess.run(cmd, cwd=CASE, env=env_gui_wayland, stdout=lg, stderr=lg, check=True)
                    print(f"{DONE_ICON} Orientation completed.")
                except Exception:
                    subprocess.run(cmd, cwd=CASE, env=env_gui_xcb, stdout=lg, stderr=lg, check=True)
                    print(f"{DONE_ICON} Orientation completed.")
        else:
            print(f"{INFO_ICON} Skipping STL orientation GUI (user choice). Using default/template blockMeshDict.")

        # Update dicts if oriented STL present (and recompute locationInMesh)
        tri_surf = CASE / 'constant' / 'triSurface'
        base = (case_stl.stem)
        oriented_stl = tri_surf / f"{base}_oriented.stl"
        if oriented_stl.exists():
            snappy = CASE / 'system' / 'snappyHexMeshDict'
            sfe    = CASE / 'system' / 'surfaceFeatureExtractDict'
            try:
                def _swap(txt: str) -> str:
                    txt = txt.replace(f"{base}.stl",  f"{base}_oriented.stl")
                    txt = txt.replace(f"{base}.eMesh", f"{base}_oriented.eMesh")
                    return txt
                if snappy.exists():
                    snappy.write_text(_swap(snappy.read_text()))
                if sfe.exists():
                    sfe.write_text(_swap(sfe.read_text()))
                print(f"{DONE_ICON} Updated dicts to use oriented STL/eMesh.")
            except Exception as e:
                print(f"{WARN_ICON} Could not update dicts to oriented STL: {e}")
            try:
                bmd = (CASE / 'system' / 'blockMeshDict').read_text(errors="ignore")
                def _get(pat: str):
                    m = re.search(pat, bmd, re.MULTILINE | re.IGNORECASE)
                    return float(m.group(1)) if m else None
                xmin = _get(r'^\s*xmin\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*;')
                xmax = _get(r'^\s*xmax\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*;')
                ymin = _get(r'^\s*ymin\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*;')
                ymax = _get(r'^\s*ymax\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*;')
                zmin = _get(r'^\s*zmin\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*;')
                zmax = _get(r'^\s*zmax\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*;')
                if None in (xmin, xmax, ymin, ymax, zmin, zmax):
                    raise ValueError("Could not parse domain bounds from blockMeshDict")
                lx, ly, lz = (xmax-xmin), (ymax-ymin), (zmax-zmin)
                px, py, pz = xmin+0.8*lx, ymin+0.8*ly, zmin+0.8*lz
                snappy_txt = snappy.read_text(errors="ignore")
                snappy_txt = re.sub(
                    r'^\s*locationInMesh\s*\([^)]*\)\s*;\s*$',
                    f'    locationInMesh ({px:.6f} {py:.6f} {pz:.6f});',
                    snappy_txt, flags=re.MULTILINE
                )
                if 'locationInMesh' not in snappy_txt:
                    snappy_txt = re.sub(
                        r'(^\s*castellatedMeshControls\s*\{)',
                        r'\1\n    locationInMesh (%.6f %.6f %.6f);' % (px, py, pz),
                        snappy_txt, count=1, flags=re.MULTILINE
                    )
                snappy.write_text(snappy_txt)
            except Exception as e:
                print(f"{WARN_ICON} Could not recompute locationInMesh from oriented STL: {e}")
        else:
            print(f"{INFO_ICON} No oriented STL found; keeping original STL in dicts.")

        # 3) blockMesh & surfaceFeatureExtract (run once — base mesh)
        print_section("3. Running blockMesh & surfaceFeatureExtract")
        run_and_log('blockMesh', CASE, 'log_blockMesh.txt')

        # Save base mesh
        shutil.copytree(CASE/'constant'/'polyMesh', CASE/'constant'/'polyMesh.base', dirs_exist_ok=True)

        run_and_log('surfaceFeatureExtract', CASE, 'log_surfaceFeatureExtract.txt')

        # After polyMesh exists, sync 0/* with boundary once here
        sync_zero_fields_with_boundary(CASE)

        # GUI configuration phase (before snappyHexMesh)
        env_gui2 = dict(os.environ,
            QT_QPA_PLATFORM='xcb',
            QT_OPENGL='software',
            QT_XCB_GL_INTEGRATION='egl',
            LIBGL_ALWAYS_SOFTWARE='1',
            QT_LOGGING_RULES='qt.qpa.*=false'
        )
        env = dict(env_gui2)

        def run_gui(script, cwd=CASE):
            """Launch a Qt helper; log to CASE/logs/."""
            logs_dir = cwd / 'logs'
            logs_dir.mkdir(parents=True, exist_ok=True)
            log_file = logs_dir / f"log_{Path(script).stem}.txt"
            with open(log_file, 'wb') as log:
                subprocess.run(
                    ['python3', str(SCRIPTS / script)],
                    cwd=cwd,
                    env=env_gui2,
                    stdout=log,
                    stderr=log,
                    check=True
                )

        # ---------- helper to (re)start the live log monitor for snappy ----------
        monitor = None
        def start_snappy_monitor():
            nonlocal monitor
            try:
                if monitor and monitor.poll() is None:
                    monitor.terminate()
            except Exception:
                pass
            log_path = CASE / 'logs' / 'log_snappyHexMesh.txt'
            try:
                (CASE / 'logs').mkdir(parents=True, exist_ok=True)
                open(log_path, 'w').close()
            except Exception:
                pass
            monitor = subprocess.Popen(
                ['python3', str(SCRIPTS / 'log_monitor.py'),
                 str(log_path),
                 str(CASE / 'system' / 'snappyHexMeshDict')],
                cwd=CASE,
                env=env_gui2,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        # ---------------------------------------------------------------------

        # Open GUIs to edit dictionaries
        run_gui('snappy_gui.py')

        snappy_dict_path = CASE / 'system' / 'snappyHexMeshDict'
        phase_flags = _read_phase_flags(snappy_dict_path)

        run_gui('sanity_check.py')
        run_gui('quality_presets.py')

        if phase_flags.get('snap', True):
            run_gui('snap_widget.py')
        if phase_flags.get('layers', True):
            run_gui('layers_widget.py')

        run_gui('decompose_widget.py')

        decompose_dict = CASE / 'system' / 'decomposeParDict'
        nsub = parse_number_of_subdomains(decompose_dict)
        run_parallel = nsub > 1

        attempt_idx = 1

        def run_snappy_once():
            nonlocal attempt_idx
            start_snappy_monitor()
            title = "4. Running snappyHexMesh" if attempt_idx == 1 else f"4.{attempt_idx-1} Running snappyHexMesh"
            print_section(title)

            if run_parallel:
                print(f"{INFO_ICON} Multi-core mode detected (numberOfSubdomains={nsub})")

                # ensure 0/* matches boundary just before decomposePar
                sync_zero_fields_with_boundary(CASE)

                # Clean and normalize, then create processors
                clean_parallel_env(CASE)
                normalize_root_system_files(CASE)

                run_and_log('decomposePar', CASE, 'log_decomposePar.txt')

                # sync root system → processor*/system, then normalize
                sync_system_to_processors(CASE)
                normalize_processor_system_files(CASE)

                run_and_log(
                    f"mpirun -np {nsub} snappyHexMesh -dict system/snappyHexMeshDict -parallel -overwrite",
                    CASE, 'log_snappyHexMesh.txt'
                )
                run_and_log('reconstructParMesh -constant', CASE, 'log_reconstructParMesh.txt')
                for procdir in CASE.glob('processor*'):
                    shutil.rmtree(procdir, ignore_errors=True)
            else:
                print(f"{INFO_ICON} Single-core mode detected")
                run_and_log('snappyHexMesh -dict system/snappyHexMeshDict -overwrite', CASE, 'log_snappyHexMesh.txt')

            # after (re)building mesh, re-sync fields with boundary
            sync_zero_fields_with_boundary(CASE)

            print(f"{DONE_ICON} snappyHexMesh completed ({'multi-core' if run_parallel else 'single-core'})")

        # --- snappy run (with retries on quality issues) ---
        while True:
            clean_for_snappy_retry(CASE)
            shutil.rmtree(CASE/'constant'/'polyMesh', ignore_errors=True)
            shutil.copytree(CASE/'constant'/'polyMesh.base', CASE/'constant'/'polyMesh')
            run_snappy_once()
            run_and_log('checkMesh -allGeometry -allTopology', CASE, 'log_checkMesh.txt')
            log_cm = CASE / 'logs' / 'log_checkMesh.txt'
            if _checkmesh_ok(log_cm):
                break
            want_reopen = ask_yes_no_popup(
                "checkMesh: issues detected",
                "checkMesh reported mesh quality issues.\nDo you want to reopen Quality / Snap / Layers GUIs now?",
                env_gui2
            )
            if not want_reopen:
                break
            run_gui('snappy_gui.py')
            phase_flags = _read_phase_flags(snappy_dict_path)
            run_gui('quality_presets.py')
            if phase_flags.get('snap', True):
                run_gui('snap_widget.py')
            if phase_flags.get('layers', True):
                run_gui('layers_widget.py')
            print(f"{DONE_ICON} Windows reopened. Apply changes and re-run snappyHexMesh.")
            attempt_idx += 1

        # -------------------- 4b. Mesh snapshots (ParaView) --------------------
        print_section("4b. Creating mesh snapshots (ParaView)")
        try:
            if monitor and monitor.poll() is None:
                monitor.terminate()
        except Exception:
            pass

        def _find_pvpython() -> str | None:
            p = shutil.which('pvpython')
            if p:
                return p
            cand = Path('/opt/paraview-5.13.3/bin/pvpython')
            if cand.exists() and os.access(cand, os.X_OK):
                return str(cand)
            return None

        try:
            pv = _find_pvpython()
            if pv:
                pv_env = dict(os.environ)
                pv_env['QT_LOGGING_RULES'] = 'qt.qpa.*=false;qt.glx.*=false'
                pv_env['QT_OPENGL'] = 'software'
                pv_env['LIBGL_ALWAYS_SOFTWARE'] = '1'
                with open(CASE/'logs'/'log_mesh_snapshots.txt', 'wb') as log:
                    subprocess.run([pv, str(SNAPSHOT_SCRIPT)], cwd=CASE,
                                   env=pv_env, stdout=log, stderr=log, check=True)
                print(f"{DONE_ICON} Mesh snapshots saved (pvpython).")
            else:
                print(f"{WARN_ICON} pvpython not found; falling back to python3.")
                run_and_log(
                    cmd=f'python3 "{SNAPSHOT_SCRIPT}"',
                    cwd=CASE,
                    log_file='log_mesh_snapshots.txt'
                )
                print(f"{DONE_ICON} Mesh snapshots attempted (python3 fallback).")
        except Exception as e:
            print(f"{WARN_ICON} Could not create mesh snapshots: {e}")

        _pipeline_banner(True, "MESH PIPELINE")
        return

    except subprocess.CalledProcessError as e:
        print(f"{ERR_ICON} A command failed with return code {e.returncode}. See logs for details.")
        _pipeline_banner(False, "MESH PIPELINE")
    except Exception as e:
        print(f"{ERR_ICON} Pipeline failed: {e}")
        _pipeline_banner(False, "MESH PIPELINE")

if __name__ == '__main__':
    main()
