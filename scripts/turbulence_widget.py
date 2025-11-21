#!/usr/bin/env python3
# turbulence_widget.py
# GUI to configure constant/turbulenceProperties (laminar / RANS / LES).
# - Matches the Fusion-dark style via ui_theme.py 
# - Shows path of the target file INSIDE the case (not the template)
# - Preview window
# - Write button
# - Forbid empty 'delta' selection when LES is chosen
# - Text box for "application" (controlDict) + "Check" button
#   that performs a textual compatibility warning between solver and chosen turbulence model.
# - CURRENT PATCH (ONLY): (1) always operate inside case/ and write both turbulenceProperties
#                             and controlDict(application), ensuring full case structure from template.
#                         (2) redirect OS-level stderr (fd=2) to case/logs to silence Qt/GL spam.
#                         (3) Rebuild 0/* boundaryField strictly from mesh patches to avoid EOF
#                             and "Cannot find patchField entry" errors, while hard-fixing braces.
#                         (4) Apply fvSolution from a solver-specific template (SIMPLE/PIMPLE/PISO/POTENTIAL)
#                             and remove any existing processor*.

import sys
import os
import re
import shutil
import subprocess
from pathlib import Path
import argparse
from typing import Optional, List, Tuple, Dict

from PyQt5.QtWidgets import (  # type: ignore
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QComboBox, QCheckBox, QPushButton, QMessageBox, QDialog, QPlainTextEdit, QLineEdit
)
from PyQt5.QtCore import Qt  # type: ignore
from PyQt5.QtGui import QFontDatabase  # type: ignore

from ui_theme import set_qt_env, apply_fusion_dark, center_on_screen
import difflib

HEADER_BANNER = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | foam-extend: Open Source CFD                    |
|  \\\\    /   O peration     | Version:     4.0                                |
|   \\\\  /    A nd           | Web:         http://www.foam-extend.org         |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/"""
FOOTER_LINE = "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //"

# Footer generico tipo OpenFOAM 2412 (accetta // *** // con spazi vari)
_FOOTER_RE = re.compile(r'//(?:\s*\*+\s*)+//')

# ---------- unified pipeline exit banner ----------
def _pipeline_banner(ok: bool, where: str = "PIPELINE"):
    if ok:
        print(f"{where} COMPLETED SUCCESSFULLY!")
    else:
        print(f"{where} FAILED! SEE LOGS FOR DETAILS.")
# --------------------------------------------------

# Common RANS and LES lists (typical OpenFOAM models)
# Restrict RANS models to incompressible set 
RANS_MODELS = [
    "kEpsilon",
    "RNGkEpsilon",
    "kOmega",
    "kOmegaSST",
    "SpalartAllmaras",
]

LES_MODELS = [
    "Smagorinsky",
    "WALE",
    "dynamicKEqn",
    "kEqn",
]
# Common LES delta options
LES_DELTAS = [
    "cubeRootVol",
    "vanDriest",
    "Prandtl",
    "smooth",
]

# ---- mapping of required 0/ files by (sim_type, model) ----
MODEL_0_FILES = {
    # RANS
    ("RAS", "kEpsilon"):        ["k", "epsilon", "nut", "alphat"],
    ("RAS", "RNGkEpsilon"):     ["k", "epsilon", "nut", "alphat"],
    ("RAS", "kOmega"):          ["k", "omega",   "nut", "alphat"],
    ("RAS", "kOmegaSST"):       ["k", "omega",   "nut", "alphat"],
    ("RAS", "SpalartAllmaras"): ["nuTilda",      "nut", "alphat"],
    # LES (alphat is still needed if temperature is solved, via turbulent Prt)
    ("LES", "Smagorinsky"):     ["nut", "alphat"],
    ("LES", "WALE"):            ["nut", "alphat"],
    ("LES", "dynamicKEqn"):     ["k", "nut", "alphat"],
    ("LES", "kEqn"):            ["k", "nut", "alphat"],
}

def foam_header(object_name: str, location: str = "constant") -> str:
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

def ensure_header(text: str) -> str:
    """Ensure the standard FOAM header is present."""
    if "FoamFile" in text and "object" in text and "turbulenceProperties" in text:
        return text
    return foam_header("turbulenceProperties") + "\n" + text.strip("\n") + "\n"

# -------------------- paths (always work inside case/) --------------------
REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "templateCase"
CASE = REPO / "case"
MESH_DIR = REPO / "mesh"

LOGS = CASE / "logs"
LOGS.mkdir(parents=True, exist_ok=True)
LOG_STDERR = LOGS / "log_turbulence_gui_stderr.txt"
LOG_INFO = LOGS / "log_turbulence_gui.txt"

def _log_line(s: str):
    """Append informational lines to case/logs/log_turbulence_gui.txt."""
    try:
        with open(LOG_INFO, "a", encoding="utf-8") as f:
            f.write(s.rstrip() + "\n")
    except Exception:
        pass

def find_case_turbulence_path(_: Optional[Path]) -> Path:
    """Always point to case/constant/turbulenceProperties."""
    tp = CASE / "constant" / "turbulenceProperties"
    tp.parent.mkdir(parents=True, exist_ok=True)
    return tp

def parse_current(text: str):
    """Parse simulationType and its sub-keys (RAS/LES)."""
    sim = "laminar"
    rasModel = None
    lesModel = None
    delta = None
    turb_on = True
    printCoeffs = True

    m = re.search(r'^\s*simulationType\s+(\w+)\s*;\s*$', text, re.MULTILINE)
    if m:
        sim = m.group(1)

    if sim == "RAS":
        m2 = re.search(r'RASModel\s+(\w+)\s*;', text)
        if m2: rasModel = m2.group(1)
        turb_on = not re.search(r'^\s*turbulence\s+off\s*;\s*$', text, re.MULTILINE)
        printCoeffs = not re.search(r'^\s*printCoeffs\s+off\s*;\s*$', text, re.MULTILINE)
    elif sim == "LES":
        m3 = re.search(r'LESModel\s+(\w+)\s*;', text)
        if m3: lesModel = m3.group(1)
        m4 = re.search(r'^\s*delta\s+(\w+)\s*;\s*$', text, re.MULTILINE)
        if m4: delta = m4.group(1)
        turb_on = not re.search(r'^\s*turbulence\s+off\s*;$', text, re.MULTILINE)
        printCoeffs = not re.search(r'^\s*printCoeffs\s+off\s*;$', text, re.MULTILINE)

    return sim, rasModel, lesModel, delta, turb_on, printCoeffs

def render_text(sim: str, rasModel: Optional[str], lesModel: Optional[str],
                delta: Optional[str], turb_on: bool, printCoeffs: bool) -> str:
    lines = []
    lines.append(foam_header("turbulenceProperties"))
    lines.append("simulationType      " + (sim if sim else "laminar") + ";")
    lines.append("")
    if sim == "RAS":
        lines.append("RAS")
        lines.append("{")
        lines.append(f"    RASModel        {rasModel or 'kEpsilon'};")
        lines.append(f"    turbulence      {'on' if turb_on else 'off'};")
        lines.append(f"    printCoeffs     {'on' if printCoeffs else 'off'};")
        lines.append("}")
    elif sim == "LES":
        lines.append("LES")
        lines.append("{")
        lines.append(f"    LESModel        {lesModel or 'Smagorinsky'};")
        lines.append(f"    delta           {delta or 'cubeRootVol'};")
        lines.append(f"    turbulence      {'on' if turb_on else 'off'};")
        lines.append(f"    printCoeffs     {'on' if printCoeffs else 'off'};")
        lines.append("")
        lines.append("    dynamicKEqnCoeffs")
        lines.append("    {")
        lines.append("        filter      simple;")
        lines.append("    }")
        lines.append("")
        lines.append("    vanDriestCoeffs")
        lines.append("    {")
        lines.append("        delta           cubeRootVol;")
        lines.append("        kappa           0.41;")
        lines.append("        Aplus           26;")
        lines.append("        Cdelta          0.158;")
        lines.append("        calcInterval    1;")
        lines.append("    }")
        if delta == "smooth":
            lines.append("")
            lines.append("    smoothCoeffs")
            lines.append("    {")
            lines.append("        delta           cubeRootVol;")
            lines.append("        cubeRootVolCoeffs")
            lines.append("        {")
            lines.append("            deltaCoeff 1;")
            lines.append("        }")
            lines.append("        maxDeltaRatio    1.1;")
            lines.append("    }")
        elif delta == "Prandtl":
            lines.append("")
            lines.append("    PrandtlCoeffs")
            lines.append("    {")
            lines.append("        delta           cubeRootVol;")
            lines.append("        cubeRootVolCoeffs")
            lines.append("        {")
            lines.append("            deltaCoeff 1;")
            lines.append("        }")
            lines.append("        smoothCoeffs")
            lines.append("        {")
            lines.append("            delta           cubeRootVol;")
            lines.append("            cubeRootVolCoeffs")
            lines.append("            {")
            lines.append("                deltaCoeff 1;")
            lines.append("            }")
            lines.append("            maxDeltaRatio    1.1;")
            lines.append("        }")
            lines.append("        Cdelta          0.158;")
            lines.append("    }")
        lines.append("}")
    lines.append("")
    lines.append(FOOTER_LINE)
    return "\n".join(lines) + "\n"

def _show_preview(parent: QWidget, title: str, text: str):
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(860, 680)
    lay = QVBoxLayout(dlg)
    edit = QPlainTextEdit(dlg)
    edit.setReadOnly(True)
    edit.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
    edit.setPlainText(text)
    lay.addWidget(edit)
    btn = QPushButton("Continue")
    btn.clicked.connect(dlg.close)
    lay.addWidget(btn)
    return dlg


def _copy_missing(src_dir: Path, dst_dir: Path):
    for p in src_dir.iterdir():
        dp = dst_dir / p.name
        if p.is_dir():
            dp.mkdir(parents=True, exist_ok=True)
            _copy_missing(p, dp)
        else:
            if not dp.exists():
                shutil.copy2(p, dp)
                _log_line(f"Copied missing file {dp.relative_to(CASE)} from template.")

def _copy_mesh_surface_feature_extract():
    src = MESH_DIR / "surfaceFeatureExtractDict"
    dst = CASE / "system" / "surfaceFeatureExtractDict"
    try:
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                shutil.copy2(src, dst)
                _log_line("Copied system/surfaceFeatureExtractDict from mesh.")
    except Exception as e:
        _log_line(f"Could not copy surfaceFeatureExtractDict from mesh: {e}")


def _ensure_thermophysical_header():
    tpl = TEMPLATE / "constant" / "thermophysicalProperties"
    dst = CASE / "constant" / "thermophysicalProperties"
    try:
        if not dst.exists():
            
            if tpl.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(tpl, dst)
                _log_line("Copied thermophysicalProperties from template (missing).")
            return

        # If it exists but has no FoamFile header, replace with the proper template
        txt = dst.read_text(errors="ignore")
        if "FoamFile" not in txt or "object      thermophysicalProperties" not in txt:
            if tpl.is_file():
                shutil.copy2(tpl, dst)
                _log_line("Replaced thermophysicalProperties with template with header (header was missing).")
    except Exception as e:
        _log_line(f"Could not ensure thermophysicalProperties header: {e}")

def ensure_case_structure():
    print("[..] Preparing turbulence setup ...")
    if not CASE.exists():
        print("[..] Creating case/ from templateCase ...")
        shutil.copytree(TEMPLATE, CASE)
        print("[OK] case/ created.")
    else:
        (CASE / "0").mkdir(parents=True, exist_ok=True)
        (CASE / "constant").mkdir(parents=True, exist_ok=True)
        (CASE / "system").mkdir(parents=True, exist_ok=True)
        _copy_missing(TEMPLATE / "0", CASE / "0")
        _copy_missing(TEMPLATE / "constant", CASE / "constant")
        _copy_missing(TEMPLATE / "system", CASE / "system")
        print("[i] case/ exists. Ensured full structure and missing files from template.")
    _copy_mesh_surface_feature_extract()
    _ensure_thermophysical_header()
    try:
        foam_marker = CASE / "case.foam"
        if not foam_marker.exists():
            foam_marker.touch()
            _log_line("Created case.foam in case/ for ParaView.")
    except Exception as e:
        _log_line(f"Could not ensure case.foam: {e}")

def copy_needed_zero_files(sim_type: str, model: str):
    # SOLO file copiati da templateCase/0, niente creato “da zero”
    needed = MODEL_0_FILES.get((sim_type, model), [])
    zero_src = TEMPLATE / "0"
    zero_dst = CASE / "0"
    zero_dst.mkdir(parents=True, exist_ok=True)
    if not needed:
        return
    print(f"[..] Copying required 0/ templates")
    for name in needed:
        src = zero_src / name
        dst = zero_dst / name
        if not src.exists():
            _log_line(f"Missing template 0/{name} in templateCase. Skipped.")
            continue
        shutil.copy2(src, dst)
        _log_line(f"Copied 0/{name}")

def prune_unneeded_zero_files(sim_type: str, model: str):
    keep = set(MODEL_0_FILES.get((sim_type, model), []))
    
    keep.update({"U", "p", "T", "alphat"})
    zero_dir = CASE / "0"
    if not zero_dir.exists():
        return
    for pth in zero_dir.iterdir():
        if pth.is_file() and pth.name not in keep:
            if pth.name in {"k", "epsilon", "omega", "nuTilda", "nut"}:
                try:
                    pth.unlink()
                    _log_line(f"Removed 0/{pth.name}")
                except Exception as e:
                    _log_line(f"Could not remove 0/{pth.name}: {e}")

# ---- BC rules ----
_NO_VALUE_TYPES = {
    'cyclic', 'cyclicAMI', 'processor', 'symmetryPlane', 'empty', 'wedge', 'slip', 'zeroGradient'
}
_WALL_FUNCTION_TYPES = {
    'epsilonWallFunction', 'omegaWallFunction', 'kqRWallFunction', 'nutkWallFunction', 'nutUSpaldingWallFunction',
    
    'compressible::alphatWallFunction'
}
_FIXEDVALUE_DERIVED = {
    'fixedValue', 'movingWallVelocity'
}

def _value_line_for(field_name: str, bc_type: str) -> Optional[str]:
    t = bc_type.strip()
    if t in _NO_VALUE_TYPES:
        return None
    if t in _WALL_FUNCTION_TYPES:
        if field_name in ('k', 'epsilon', 'omega', 'nut', 'alphat'):
            return "value uniform 0;"
        return None
    if t in _FIXEDVALUE_DERIVED:
        if field_name == 'U':
            return "value uniform (0 0 0);"
        else:
            return "value uniform 0;"
    return None

# ---- insert/replace patch blocks ----
def _insert_patch_block(field_text: str, patch: str, bc_type: str, field_name: str) -> str:
    # NON crea una seconda boundaryField se già esiste
    bf = re.search(r'\bboundaryField\s*\{', field_text)
    val_line = _value_line_for(field_name, bc_type)

    if not bf:
        # Proviamo ad inserire boundaryField dopo internalField se esiste
        m_int = re.search(r'\binternalField\b[^\n]*;\s*\n', field_text)
        insert_pos = m_int.end() if m_int else len(field_text.rstrip()) 
        insertion = "\nboundaryField\n{\n"
        insertion += f"    {patch}\n"
        insertion += "    {\n"
        insertion += f"        type {bc_type};\n"
        if val_line:
            insertion += f"        {val_line}\n"
        insertion += "    }\n"
        insertion += "}\n"
        return field_text[:insert_pos] + insertion + field_text[insert_pos:]

    # boundaryField già presente: aggiungo solo la patch se manca
    i = field_text.find('{', bf.end()-1)
    depth, j = 1, i+1
    while j < len(field_text) and depth > 0:
        if field_text[j] == '{': depth += 1
        elif field_text[j] == '}': depth -= 1
        j += 1
    bf_start, bf_end = bf.start(), j
    bf_block = field_text[bf_start:bf_end]

    if re.search(rf'^\s*{re.escape(patch)}\s*\{{', bf_block, re.MULTILINE):
        return field_text

    new_patch = f"    {patch}\n    {{\n        type {bc_type};\n"
    if val_line:
        new_patch += f"        {val_line}\n"
    new_patch += "    }\n"
    bf_block2 = bf_block[:-1] + new_patch + bf_block[-1:]
    return field_text[:bf_start] + bf_block2 + field_text[bf_end:]

def _replace_patch_type(field_text: str, patch: str, bc_type: str, field_name: str) -> str:
    # NON viene più usato per cambiare type/value esistenti, ma lo lasciamo intatto
    m = re.search(r'\bboundaryField\s*\{', field_text)
    if not m:
        return field_text
    i = field_text.find('{', m.end()-1)
    depth, j = 1, i+1
    while j < len(field_text) and depth > 0:
        if field_text[j] == '{':
            depth += 1
        elif field_text[j] == '}':
            depth -= 1
        j += 1
    bf_start, bf_end = m.start(), j
    bf = field_text[bf_start:bf_end]

    pm = re.search(rf'^\s*{re.escape(patch)}\s*\{{(.*?)\}}', bf, re.MULTILINE | re.DOTALL)
    if not pm:
        return field_text

    inner = pm.group(1)

    if re.search(r'\btype\s+\w+[:]{0,2}\w*\s*;', inner):
        inner = re.sub(r'\btype\s+\w+[:]{0,2}\w*\s*;', f'type {bc_type};', inner, count=1)
    else:
        inner = f"type {bc_type};\n        " + inner

    desired = _value_line_for(field_name, bc_type)
    has_value = re.search(r'\bvalue\s+[^;]+;', inner) is not None

    if desired is None and has_value:
        inner = re.sub(r'\bvalue\s+[^;]+;\s*', '', inner)
    elif desired is not None:
        if has_value:
            inner = re.sub(r'\bvalue\s+[^;]+;', desired, inner, count=1)
        else:
            inner += f"\n        {desired}\n"

    new_patch_block = f"{patch}\n    {{{inner}}}"
    bf2 = bf[:pm.start()] + new_patch_block + bf[pm.end():]
    return field_text[:bf_start] + bf2 + field_text[bf_end:]


def _balance_all_braces(text: str) -> str:
    out = []
    depth = 0
    for ch in text:
        if ch == '{':
            depth += 1
            out.append(ch)
        elif ch == '}':
            if depth == 0:
                # graffa in eccesso (la butto)
                continue
            depth -= 1
            out.append(ch)
        else:
            out.append(ch)
    # se depth > 0, teniamo comunque le graffe aggiunte (bilanciamento globale);
    # verranno poi pulite da _dedup_trailing_closing_braces dove serve
    if depth > 0:
        out.append("\n" + "}\n" * depth)
    return "".join(out)

def _reformat_boundary_patches(s: str) -> str:
    m = re.search(r'\bboundaryField\s*\{', s)
    if not m:
        return s
    bf_kw_start = m.start()
    brace_start = s.find('{', m.end()-1)
    if brace_start == -1:
        return s

    depth, j = 1, brace_start + 1
    while j < len(s) and depth > 0:
        if s[j] == '{':
            depth += 1
        elif s[j] == '}':
            depth -= 1
        j += 1
    brace_end = j

    before = s[:brace_start+1]
    inner = s[brace_start+1:brace_end-1]
    after = s[brace_end-1:]

    new_inner = ""
    pos = 0
    patch_re = re.compile(r'\n\s*([A-Za-z0-9_.:-]+)\s*\{', re.MULTILINE)
    while True:
        mpatch = patch_re.search(inner, pos)
        if not mpatch:
            new_inner += inner[pos:]
            break

        new_inner += inner[pos:mpatch.start()]

        name = mpatch.group(1)
        start = mpatch.start()
        brace = inner.find('{', mpatch.start())
        if brace == -1:
            new_inner += inner[start:]
            break

        d2, q = 1, brace + 1
        while q < len(inner) and d2 > 0:
            if inner[q] == '{':
                d2 += 1
            elif inner[q] == '}':
                d2 -= 1
            q += 1
        patch_body = inner[brace+1:q-1]

        new_inner += f"\n    {name}\n"
        new_inner += "    {\n"
        body_stripped = patch_body.strip()
        if body_stripped:
            for line in body_stripped.splitlines():
                new_inner += "        " + line.strip() + "\n"
        new_inner += "    }\n"

        pos = q

    return before + new_inner + after

def _move_tail_patches_inside_boundaryField(s: str) -> str:
    m = re.search(r'\bboundaryField\s*\{', s)
    if not m:
        return s
    i = s.find('{', m.end()-1)
    if i == -1:
        return s
    depth, j = 1, i + 1
    while j < len(s) and depth > 0:
        if s[j] == '{':
            depth += 1
        elif s[j] == '}':
            depth -= 1
        j += 1
    bf_start, bf_end = m.start(), j
    tail = s[bf_end:]
    patch_re = re.compile(r'\n\s*([A-Za-z0-9_.:-]+)\s*\{', re.MULTILINE)
    idx = 0
    patches: List[str] = []
    cut_regions: List[Tuple[int, int]] = []
    while True:
        mm = patch_re.search(tail, idx)
        if not mm:
            break
        start = mm.start()
        brace = tail.find('{', start)
        if brace == -1:
            break
        d2, q = 1, brace + 1
        while q < len(tail) and d2 > 0:
            if tail[q] == '{':
                d2 += 1
            elif tail[q] == '}':
                d2 -= 1
            q += 1
        patch_start = start
        patch_end = q
        patches.append(tail[patch_start:patch_end])
        cut_regions.append((patch_start, patch_end))
        idx = q
    if not patches:
        return s
    new_tail_parts: List[str] = []
    last = 0
    for a, b in cut_regions:
        new_tail_parts.append(tail[last:a])
        last = b
    new_tail_parts.append(tail[last:])
    new_tail = "".join(new_tail_parts)
    bf_block = s[bf_start:bf_end]
    insert_text = "".join(patches)
    bf_block_new = bf_block[:-1] + insert_text + bf_block[-1:]
    return s[:bf_start] + bf_block_new + new_tail

def _normalize_footer(s: str) -> str:
    """
    Rimuove tutti i footer tipo // ...***... // dal corpo
    e, se ne ha trovati, ne mette UNO SOLO in fondo al file.
    Se il footer era sulla stessa linea di altro testo (es. 'bottom'),
    stacca il footer e lascia il resto intatto.
    """
    lines = s.splitlines()
    out_lines: List[str] = []
    seen_footer = False

    for line in lines:
        m = _FOOTER_RE.search(line)
        if not m:
            out_lines.append(line)
            continue

        seen_footer = True
        before = line[:m.start()].rstrip()
        after = line[m.end():].strip()

        if before:
            out_lines.append(before)
        if after:
            out_lines.append(after)

    if not seen_footer:
        return s

    body = "\n".join(l.rstrip() for l in out_lines).rstrip()
    body += "\n\n// ************************************************************************* //\n"
    return body

def _dedup_trailing_closing_braces(s: str) -> str:
    """
    Prima del footer:
    - NON tocca le graffe chiuse indentate (quelle delle patch).
    - Se ci sono più graffe chiuse a colonna 0 una sotto l'altra,
      ne lascia UNA sola (la chiusura di boundaryField).
    """
    m = _FOOTER_RE.search(s)
    if not m:
        return s

    before = s[:m.start()]
    footer_and_after = s[m.start():]

    # Togliamo whitespace finale, analizziamo riga per riga
    before_stripped = before.rstrip("\n")
    lines = before_stripped.splitlines()

    if not lines:
        return before_stripped + footer_and_after

    # Scorriamo dal fondo finché troviamo righe fatte solo di '}' + spazi
    closing_idxs: List[int] = []
    for idx in range(len(lines) - 1, -1, -1):
        if lines[idx].strip() == "":
            continue
        if re.fullmatch(r'\s*\}\s*', lines[idx]):
            closing_idxs.append(idx)
            continue
        # appena troviamo una riga che NON è solo '}', ci fermiamo
        break

    if len(closing_idxs) <= 1:
        # 0 o 1 graffa alla fine: non c'è nulla da deduplicare
        new_before = "\n".join(lines)
        return new_before + footer_and_after

    # closing_idxs è in ordine dal fondo verso l'alto, invertiamolo
    closing_idxs.reverse()  # ora è dalla riga più alta alla più bassa

    # Classifica: indentazione di ciascuna riga di sola '}'
    zero_indent_idxs: List[int] = []
    for idx in closing_idxs:
        m_indent = re.match(r'^(\s*)\}', lines[idx])
        indent_len = len(m_indent.group(1)) if m_indent else 0
        if indent_len == 0:
            zero_indent_idxs.append(idx)

    # Se ci sono più righe con '}' a colonna 0, teniamo SOLO l'ultima
    if len(zero_indent_idxs) > 1:
        keep = max(zero_indent_idxs)
        to_delete = {i for i in zero_indent_idxs if i != keep}
    else:
        to_delete = set()

    # NON tocchiamo le graffe indentate (patch): restano tutte
    new_lines: List[str] = []
    for i, line in enumerate(lines):
        if i in to_delete:
            continue
        new_lines.append(line)

    new_before = "\n".join(new_lines)
    return new_before + footer_and_after

def _fix_field_dictionary(s: str) -> str:
    """
    Fixer minimale:
    - aggiunge ; mancanti per dimensions, internalField, type, value
    - normalizza ';;'
    - rimuove linee '// }'
    - bilancia le graffe in modo conservativo
    - riformatta i blocchi delle patch boundaryField senza cambiare type/value
    - sposta le patch che stanno DOPO boundaryField dentro boundaryField
    - normalizza il footer in modo che appaia SOLO alla fine
    - deduplica eventuali graffe finali ridondanti a colonna 0
    """
    for pat in (
        r'(^|\n)(\s*dimensions\s+\[[^\]]+\])\s*(?=\n|$)',
        r'(^|\n)(\s*internalField\s+(?!nonuniform\b)[^;{}\n]+)\s*(?=\n|$)',
        r'(^|\n)(\s*type\s+\S+)\s*(?=[\n}])',
        r'(^|\n)(\s*value\s+(?!nonuniform\b)[^;{}\n]+)\s*(?=\n|$)',
    ):
        s = re.sub(pat, lambda m: f"{m.group(1)}{m.group(2)};", s, flags=re.MULTILINE)

    s = re.sub(r';\s*;+', ';', s)

    s = re.sub(r'^\s*;\s*$', '', s, flags=re.MULTILINE)

    def _strip_foamfile_in_boundary(txt: str) -> str:
        bf = re.search(r'\bboundaryField\s*\{', txt)
        if not bf:
            return txt
        i = txt.find('{', bf.end()-1)
        if i == -1:
            return txt
        depth, j = 1, i+1
        while j < len(txt) and depth > 0:
            if txt[j] == '{':
                depth += 1
            elif txt[j] == '}':
                depth -= 1
            j += 1
        bf_start, bf_end = bf.start(), j
        bf_block = txt[bf_start:bf_end]
        bf_block = re.sub(r'(^|\n)\s*FoamFile\s*\{(?:[^{}]|\{[^{}]*\})*?\}', '', bf_block, flags=re.DOTALL)
        return txt[:bf_start] + bf_block + txt[bf_end:]
    s = _strip_foamfile_in_boundary(s)

    s = re.sub(r'^\s*//\s*\}\s*$', '', s, flags=re.MULTILINE)

    s = _balance_all_braces(s)

    s = _reformat_boundary_patches(s)

    s = _move_tail_patches_inside_boundaryField(s)

    s = _normalize_footer(s)

    s = _dedup_trailing_closing_braces(s)

    return s

# ---- wall-function suggestions ----
WALL_FN_SUGGESTIONS = {
    ("RAS", "kEpsilon"):         {"k": "kqRWallFunction", "epsilon": "epsilonWallFunction", "nut": "nutkWallFunction", "alphat": "compressible::alphatWallFunction"},
    ("RAS", "RNGkEpsilon"):      {"k": "kqRWallFunction", "epsilon": "epsilonWallFunction", "nut": "nutkWallFunction", "alphat": "compressible::alphatWallFunction"},
    ("RAS", "kOmega"):           {"k": "kqRWallFunction", "omega": "omegaWallFunction",     "nut": "nutkWallFunction", "alphat": "compressible::alphatWallFunction"},
    ("RAS", "kOmegaSST"):        {"k": "kqRWallFunction", "omega": "omegaWallFunction",     "nut": "nutkWallFunction", "alphat": "compressible::alphatWallFunction"},
    ("RAS", "SpalartAllmaras"):  {"nuTilda": "zeroGradient", "nut": "nutUSpaldingWallFunction", "alphat": "compressible::alphatWallFunction"},
    ("LES", "Smagorinsky"):      {"nut": "nutkWallFunction", "alphat": "compressible::alphatWallFunction"},
    ("LES", "WALE"):             {"nut": "nutkWallFunction", "alphat": "compressible::alphatWallFunction"},
    ("LES", "dynamicKEqn"):      {"k": "kqRWallFunction",  "nut": "nutkWallFunction", "alphat": "compressible::alphatWallFunction"},
    ("LES", "kEqn"):             {"k": "kqRWallFunction",  "nut": "nutkWallFunction", "alphat": "compressible::alphatWallFunction"},
}

def _read_wall_patches(case_dir: Path) -> List[str]:
    bfile = case_dir / "constant" / "polyMesh" / "boundary"
    walls: List[str] = []
    try:
        txt = bfile.read_text(errors="ignore")
    except Exception:
        return walls
    for m in re.finditer(r'^\s*([A-Za-z0-9_\.:-]+)\s*\{[^}]*?\btype\s+wall\s*;\s*[^}]*?\}', txt, re.MULTILINE | re.DOTALL):
        walls.append(m.group(1))
    return walls

def _insert_patch_block_fixing(field_text: str, patch: str, bc_type: str, field_name: str) -> str:
    return _fix_field_dictionary(_insert_patch_block(field_text, patch, bc_type, field_name))

def _replace_patch_type_fixing(field_text: str, patch: str, bc_type: str, field_name: str) -> str:
    return _fix_field_dictionary(_replace_patch_type(field_text, patch, bc_type, field_name))

def apply_wall_bcs(sim_type: str, model: str, case_dir: Path):
    suggestions = WALL_FN_SUGGESTIONS.get((sim_type, model), {})
    if not suggestions:
        _log_line(f"No wall-function suggestions for ({sim_type}, model={model}).")
        return
    walls = _read_wall_patches(case_dir)
    if not walls:
        print("[i] No constant/polyMesh/boundary found or no wall patches.")
        return
    zero_dir = case_dir / "0"
    for field_name, bc_type in suggestions.items():
        fpath = zero_dir / field_name
        if not fpath.exists():
            continue
        try:
            txt = fpath.read_text(errors="ignore")
            for p in walls:
                if p not in _list_field_patch_names(txt):
                    txt = _insert_patch_block_fixing(txt, p, bc_type, field_name)
            txt = _fix_field_dictionary(txt)
            fpath.write_text(txt)
            _log_line(f"Checked walls for 0/{field_name}")
        except Exception as e:
            _log_line(f"Could not set wall BC for 0/{field_name}: {e}")


_PATCHTYPE_TO_FIELD = {
    'symmetryPlane': 'symmetryPlane',
    'symmetry': 'symmetry',
    'empty': 'empty',
    'wedge': 'wedge',
    'cyclic': 'cyclic',
    'cyclicAMI': 'cyclicAMI',
    'processor': 'processor',
}

_WALL_BC = {'k': 'kqRWallFunction', 'epsilon': 'epsilonWallFunction', 'omega': 'omegaWallFunction',
            'nut': 'nutkWallFunction', 'nuTilda': 'zeroGradient', 'alphat': 'compressible::alphatWallFunction'}

def _iter_mesh_patches(boundary_text: str):
    it = re.finditer(r'^\s*([A-Za-z0-9_.:-]+)\s*\{([^{}]*\{[^{}]*\}[^{}]*|[^{}])*?\}', boundary_text, flags=re.M|re.S)
    for m in it:
        name = m.group(1)
        body = m.group(0)
        tm = re.search(r'\btype\s+([A-Za-z0-9_:]+)\s*;', body)
        if not tm:
            continue
        ptype = tm.group(1)
        if name != "FoamFile":
            yield name, ptype

def _list_mesh_patches_with_types(case_dir: Path) -> List[Tuple[str, str]]:
    bpath = case_dir / "constant" / "polyMesh" / "boundary"
    if not bpath.exists():
        return []
    try:
        txt = bpath.read_text(errors="ignore")
    except Exception:
        return []
    return list(_iter_mesh_patches(txt))

def _auto_bc_for(field_name: str, patch_type: str) -> Tuple[str, Optional[str]]:
    if patch_type == 'wall':
        if field_name in _WALL_BC:
            bc = _WALL_BC[field_name]
            return bc, _value_line_for(field_name, bc)
        if field_name == 'U':
            return 'fixedValue', "value uniform (0 0 0);"
        return 'zeroGradient', None
    if patch_type in _PATCHTYPE_TO_FIELD:
        bc = _PATCHTYPE_TO_FIELD[patch_type]
        return bc, _value_line_for(field_name, bc)
    return 'zeroGradient', None

def _extract_existing_patch_blocks(field_text: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    s = _fix_field_dictionary(field_text)
    m = re.search(r'\bboundaryField\s*\{', s)
    if not m:
        return result
    i = s.find('{', m.end()-1)
    if i == -1:
        return result
    depth, j = 1, i+1
    while j < len(s) and depth > 0:
        if s[j] == '{':
            depth += 1
        elif s[j] == '}':
            depth -= 1
        j += 1
    bf = s[m.start():j]
    k = bf.find('{')
    if k == -1:
        return result
    pos = k + 1
    while pos < len(bf)-1:
        mm = re.search(r'\n\s*([A-Za-z0-9_.:-]+)\s*\{', bf[pos:])
        if not mm:
            break
        name = mm.group(1)
        start = pos + mm.start()
        brace = bf.find('{', start)
        depth2, q = 1, brace+1
        while q < len(bf) and depth2 > 0:
            if bf[q] == '{':
                depth2 += 1
            elif bf[q] == '}':
                depth2 -= 1
            q += 1
        inner = bf[brace+1:q-1]
        if name != "FoamFile":
            result[name] = inner
        pos = q
    return result

def _sanitize_inner_block(field_name: str, patch_type: str, inner: str) -> str:
    inner2 = _fix_field_dictionary(inner)
    
    if patch_type == 'wall':
        bc, val = _auto_bc_for(field_name, 'wall')
        if re.search(r'\btype\s+\w+[:]{0,2}\w*\s*;', inner2):
            inner2 = re.sub(r'\btype\s+\w+[:]{0,2}\w*\s*;', f'type {bc};', inner2, count=1)
        else:
            inner2 = f"type {bc};\n        " + inner2.strip()
        desired = _value_line_for(field_name, bc)
        has_value = re.search(r'\bvalue\s+[^;]+;', inner2) is not None
        if desired is None and has_value:
            inner2 = re.sub(r'\bvalue\s+[^;]+;\s*', '', inner2)
        elif desired is not None:
            if has_value:
                inner2 = re.sub(r'\bvalue\s+[^;]+;', desired, inner2, count=1)
            else:
                inner2 += f"\n        {desired}"
        return inner2.strip()
    
    if not re.search(r'\btype\s+\w+[:]{0,2}\w*\s*;', inner2):
        bc, val = _auto_bc_for(field_name, patch_type)
        inner2 = f"type {bc};\n        " + inner2.strip()
        if val and "value" not in inner2:
            inner2 += f"\n        {val}"
    return inner2.strip()

def rebuild_zero_fields_from_mesh(case_dir: Path):
    pairs = _list_mesh_patches_with_types(case_dir)
    if not pairs:
        _log_line("[rebuild] No boundary file found or empty; skipping rebuild.")
        return
    zdir = case_dir / "0"
    if not zdir.exists():
        return
    for f in sorted(p for p in zdir.iterdir() if p.is_file()):
        try:
            field_name = f.name
            txt = f.read_text(errors="ignore")
            s = _fix_field_dictionary(txt)
            existing_names = _list_field_patch_names(s)

            for pname, ptype in pairs:
                if pname not in existing_names:
                    bc, _val = _auto_bc_for(field_name, ptype)
                    s = _insert_patch_block_fixing(s, pname, bc, field_name)

            s = _fix_field_dictionary(s)
            f.write_text(s)
        except Exception as e:
            _log_line(f"[rebuild] Could not rebuild 0/{f.name}: {e}")
    _log_line("[rebuild] Completed rebuild of 0/* from mesh.")


def _list_mesh_patch_names(case_dir: Path) -> List[str]:
    bpath = case_dir / "constant" / "polyMesh" / "boundary"
    if not bpath.exists():
        return []
    try:
        txt = bpath.read_text(errors="ignore")
    except Exception:
        return []
    names = []
    for name, _ptype in _iter_mesh_patches(txt):
        names.append(name)
    return names

def _list_field_patch_names(field_text: str) -> List[str]:
    s = _fix_field_dictionary(field_text)
    m = re.search(r'\bboundaryField\s*\{', s)
    if not m:
        return []
    i = s.find('{', m.end()-1)
    if i == -1:
        return []
    depth, j = 1, i+1
    while j < len(s) and depth > 0:
        if s[j] == '{':
            depth += 1
        elif s[j] == '}':
            depth -= 1
        j += 1
    bf_block = s[m.start():j]
    names = []
    for mm in re.finditer(r'^\s*([A-Za-z0-9_.:-]+)\s*\{', bf_block, re.MULTILINE):
        nm = mm.group(1)
        if nm != "FoamFile":
            names.append(nm)
    return names

def check_zero_fields_against_boundary(case_dir: Path) -> None:
    mesh_patches = _list_mesh_patch_names(case_dir)
    if not mesh_patches:
        _log_line("[check] No boundary file found or empty; skipping 0/* patch consistency check.")
        return

    zdir = case_dir / "0"
    if not zdir.exists():
        _log_line("[check] No 0/ directory found; skipping 0/* patch consistency check.")
        return

    any_issue = False
    report_lines: List[str] = []
    for f in sorted(p for p in zdir.iterdir() if p.is_file()):
        try:
            txt = f.read_text(errors="ignore")
        except Exception:
            continue
        field_patches = _list_field_patch_names(txt)
        missing = [p for p in mesh_patches if p not in field_patches]
        extra = [p for p in field_patches if p not in mesh_patches]

        if missing or extra:
            any_issue = True
            report_lines.append(f"- 0/{f.name}:")
            if missing:
                report_lines.append(f"    missing from field: {', '.join(missing)}")
            if extra:
                report_lines.append(f"    not present in mesh: {', '.join(extra)}")

    if any_issue:
        msg = "Patch consistency check (0/* vs mesh) found issues:\n" + "\n".join(report_lines)
        _log_line("[check] " + msg.replace("\n", " | "))
        try:
            QMessageBox.warning(None, "0/ patches vs mesh", msg)
        except Exception:
            print("[!] " + msg)
    else:
        _log_line("[check] All 0/* fields contain all mesh patches.")
        try:
            QMessageBox.information(None, "0/ patches vs mesh", "All 0/* fields contain all mesh patches.")
        except Exception:
            print("[i] All 0/* fields contain all mesh patches.")

def _write_control_dict_application(solver: str):
    solver = (solver or "").strip()
    if not solver:
        return
    cdict = CASE / "system" / "controlDict"
    try:
        txt = cdict.read_text(errors="ignore")
    except Exception:
        return
    if re.search(r'^\s*application\s+\S+\s*;', txt, re.MULTILINE):
        txt = re.sub(r'^\s*application\s+\S+\s*;', f'application     {solver};', txt, flags=re.MULTILINE)
    else:
        txt = "application     %s;\n%s" % (solver, txt)
    cdict.write_text(txt)


def _read_application_from_controlDict(case_dir: Path) -> str:
    cdict = case_dir / "system" / "controlDict"
    app = ""
    try:
        if cdict.is_file():
            for line in cdict.read_text(errors="ignore").splitlines():
                m = re.match(r'^\s*application\s+(\S+)\s*;?', line)
                if m:
                    app = m.group(1).strip().rstrip(';')
                    break
    except Exception:
        pass
    return app

def _solver_family_from_application(app: str) -> str:
    a = (app or "").strip().lower()

    simple_set = {
        "simplefoam", "mrfsimplefoam", "srfsimplefoam",
        "chtmultiregionsimplefoam",
        "buoyantsimplefoam",
    }

    pimple_set = {
        "pimplefoam",
        "buoyantpimplefoam",
        "interfoam", "multiphaseinterfoam",
        "chtmultiregionfoam",
    }

    piso_set = {"icofoam", "pisofoam"}

    if a in simple_set or a.endswith("simplefoam"):
        return "SIMPLE"
    if a in pimple_set or a.endswith("pimplefoam") or a.endswith("interfoam"):
        return "PIMPLE"
    if a in piso_set or a.endswith("pisofoam") or a.endswith("icofoam"):
        return "PISO"
    
    if a == "potentialfoam":
        return "POTENTIAL"

    return "PIMPLE"

def _apply_fvsolution_template(case_dir: Path, template_root: Path, family: str) -> None:
    sys_dir = case_dir / "system"
    sys_dir.mkdir(parents=True, exist_ok=True)

    cand = [
        template_root / "system" / f"fvSolutionTemplate_{family}",
        template_root / "system" / "fvSolutionTemplate", 
    ]
    src: Optional[Path] = None
    for c in cand:
        if c.is_file():
            src = c
            break

    if not src:
        print(f"[i] No fvSolution template found for family '{family}'. Skipping copy.")
        _log_line(f"No fvSolution template found for family '{family}'.")
        return

    dst = sys_dir / "fvSolution"
    shutil.copy2(src, dst)
    print(f"[OK] Applied fvSolution template: {src.name} -> system/fvSolution")
    _log_line(f"Applied fvSolution template '{src.name}' to case/system/fvSolution")

# ----- helpers to optionally run the solver -----
def _read_solver_from_case_control_dict(case_dir: Path) -> str:
    solver = "simpleFoam"
    cdict = case_dir / "system" / "controlDict"
    try:
        if cdict.is_file():
            for line in cdict.read_text(errors="ignore").splitlines():
                m = re.match(r'^\s*application\s+(\S+)', line)
                if m:
                    solver = m.group(1).rstrip(';')
                    break
    except Exception:
        pass
    return solver

def _parse_number_of_subdomains_from_case(case_dir: Path) -> int:
    n = 1
    dpd = case_dir / "system" / "decomposeParDict"
    try:
        if dpd.is_file():
            txt = dpd.read_text(errors="ignore")
            m = re.search(r'^\s*numberOfSubdomains\s+(\d+)\s*;', txt, re.MULTILINE)
            if m:
                n = int(m.group(1))
    except Exception:
        pass
    return n

def _run_and_log(cmd: str, cwd: Path, log_file: str):
    logs_dir = cwd / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / log_file
    print(f"[..] Running in case: {cmd}")
    with open(log_path, "wb") as log:
        proc = subprocess.run(cmd, cwd=cwd, shell=True, stdout=log, stderr=log)
        proc.check_returncode()
    print(f"[OK] Completed: {cmd}")

def _sync_system_to_processors(case_dir: Path):
    src = case_dir / "system"
    if not src.is_dir():
        return
    procs = sorted(p for p in case_dir.glob("processor*") if p.is_dir())
    for p in procs:
        dst = p / "system"
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)


KNOWN_SOLVERS = [
    "simpleFoam",
    "pimpleFoam",
    "pisoFoam",
    "potentialFoam",
]

def _best_solver_suggestion(name: str) -> Optional[str]:
    name = (name or "").strip()
    if not name:
        return None
    if name in KNOWN_SOLVERS:
        return name
    cand = difflib.get_close_matches(name, KNOWN_SOLVERS, n=1, cutoff=0.72)
    return cand[0] if cand else None

def _solver_compat_warnings(solver: str, sim_type: str, model: str) -> List[str]:
    s = (solver or "").strip()
    warn: List[str] = []
    if not s:
        warn.append("Empty solver name. Enter the controlDict 'application' (e.g. simpleFoam, pimpleFoam, pisoFoam, potentialFoam).")
        return warn

    s_low = s.lower()
    is_simple   = (s_low == "simplefoam")
    is_pimple   = (s_low == "pimplefoam")
    is_piso     = (s_low == "pisofoam")
    is_potential= (s_low == "potentialfoam")

    if sim_type == "LES":
        if is_simple:
            warn.append("LES with a steady solver (simpleFoam) is usually inconsistent. Prefer a transient solver (pimpleFoam/pisoFoam).")
    elif sim_type == "laminar":
        if any([is_simple, is_pimple, is_piso]):
            warn.append("Laminar selected but a turbulence-capable solver entered. Ensure turbulence is off in the solver setup.")
    if model == "SpalartAllmaras" and is_piso:
        warn.append("Spalart–Allmaras with pisoFoam is OK but check intended unsteadiness and time resolution.")
    if is_potential and sim_type != "laminar":
        warn.append("potentialFoam solves a potential flow (irrotational) problem; turbulence models are typically not used.")
    return warn

def _safe_solver_compat_warnings(solver: str, sim_type: str, model: str) -> List[str]:
    try:
        return _solver_compat_warnings(solver, sim_type, model)
    except Exception as e:
        _log_line(f"[compat] internal error: {e}")
        return [f"Internal compatibility check error: {e}"]


class TurbulenceGui(QWidget):
    def __init__(self, target_file: Path):
        super().__init__()
        self.setWindowTitle("Turbulence: turbulenceProperties (laminar / RANS / LES)")
        self.resize(820, 560)
        self.tp_path = target_file

        self._loading = False

        root = QVBoxLayout(self)
        lab = QLabel(f"turbulenceProperties path: {self.tp_path}")
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(lab)

        box_sim = QGroupBox("Simulation type")
        gl = QGridLayout(box_sim)
        gl.addWidget(QLabel("simulationType:"), 0, 0)
        self.cmb_sim = QComboBox(); self.cmb_sim.addItems(["laminar", "RAS", "LES"])
        gl.addWidget(self.cmb_sim, 0, 1)
        root.addWidget(box_sim)

        box_rans = QGroupBox("RANS settings")
        rl = QGridLayout(box_rans)
        rl.addWidget(QLabel("RASModel:"), 0, 0)
        self.cmb_rans = QComboBox(); self.cmb_rans.addItems(RANS_MODELS)
        rl.addWidget(self.cmb_rans, 0, 1)
        self.chk_rans_turb = QCheckBox("turbulence = on"); self.chk_rans_turb.setChecked(True)
        rl.addWidget(self.chk_rans_turb, 1, 0, 1, 2)
        self.chk_rans_print = QCheckBox("printCoeffs = on"); self.chk_rans_print.setChecked(True)
        rl.addWidget(self.chk_rans_print, 2, 0, 1, 2)
        root.addWidget(box_rans)

        box_les = QGroupBox("LES settings")
        ll = QGridLayout(box_les)
        ll.addWidget(QLabel("LESModel:"), 0, 0)
        self.cmb_les = QComboBox(); self.cmb_les.addItems(LES_MODELS)
        ll.addWidget(self.cmb_les, 0, 1)
        ll.addWidget(QLabel("delta:"), 1, 0)
        self.cmb_delta = QComboBox(); self.cmb_delta.setEditable(False); self.cmb_delta.addItems(LES_DELTAS)
        ll.addWidget(self.cmb_delta, 1, 1)
        self.chk_les_turb = QCheckBox("turbulence = on"); self.chk_les_turb.setChecked(True)
        ll.addWidget(self.chk_les_turb, 2, 0, 1, 2)
        self.chk_les_print = QCheckBox("printCoeffs = on"); self.chk_les_print.setChecked(True)
        ll.addWidget(self.chk_les_print, 3, 0, 1, 2)
        root.addWidget(box_les)

        box_chk = QGroupBox("Solver compatibility check (manual)")
        cl = QGridLayout(box_chk)
        cl.addWidget(QLabel("application (controlDict):"), 0, 0)
        self.solver_edit = QLineEdit(); self.solver_edit.setPlaceholderText("Only: simpleFoam, pimpleFoam, pisoFoam, potentialFoam")
        cl.addWidget(self.solver_edit, 0, 1)
        root.addWidget(box_chk)

        row = QHBoxLayout()
        self.btn_preview = QPushButton("Preview")
        self.btn_write = QPushButton("Write")
        self.btn_close = QPushButton("Continue")
        row.addWidget(self.btn_close); row.addStretch(1)
        row.addWidget(self.btn_preview); row.addWidget(self.btn_write)
        root.addLayout(row)

        self.cmb_sim.currentTextChanged.connect(self._on_sim_change)
        self.btn_preview.clicked.connect(self.on_preview)
        self.btn_write.clicked.connect(self.on_write)
        self.btn_close.clicked.connect(self.close)

        self._loading = True
        self._load_current()
        self._on_sim_change(self.cmb_sim.currentText())
        self._loading = False

        center_on_screen(self)

    def _load_current(self):
        if self.tp_path.exists():
            txt = self.tp_path.read_text(errors="ignore")
            sim, rmod, lmod, delta, t_on, p_on = parse_current(txt)
            self.cmb_sim.setCurrentText(sim)
            if rmod and rmod in RANS_MODELS: self.cmb_rans.setCurrentText(rmod)
            if lmod and lmod in LES_MODELS: self.cmb_les.setCurrentText(lmod)
            if delta and delta in LES_DELTAS: self.cmb_delta.setCurrentText(delta)
            if sim == "RAS":
                self.chk_rans_turb.setChecked(t_on); self.chk_rans_print.setChecked(p_on)
            elif sim == "LES":
                self.chk_les_turb.setChecked(t_on); self.chk_les_print.setChecked(p_on)
        else:
            self.tp_path.parent.mkdir(parents=True, exist_ok=True)

    def _on_sim_change(self, sim: str):
        is_rans = (sim == "RAS"); is_les = (sim == "LES")
        for w in (self.cmb_rans, self.chk_rans_turb, self.chk_rans_print): w.setEnabled(is_rans)
        for w in (self.cmb_les, self.cmb_delta, self.chk_les_turb, self.chk_les_print): w.setEnabled(is_les)

    def _build_text(self) -> str:
        sim = self.cmb_sim.currentText()
        rasModel = self.cmb_rans.currentText()
        lesModel = self.cmb_les.currentText()
        delta = self.cmb_delta.currentText().strip() if self.cmb_delta.isEnabled() else None
        turb_on = self.chk_rans_turb.isChecked() if sim == "RAS" else self.chk_les_turb.isChecked()
        printCoeffs = self.chk_rans_print.isChecked() if sim == "RAS" else self.chk_les_print.isChecked()
        return render_text(sim, rasModel, lesModel, delta, turb_on, printCoeffs)

    def on_preview(self):
        text = self._build_text()
        dlg = _show_preview(self, "Preview: turbulenceProperties", text)
        dlg.show()

    def on_write(self):
        try:
            sim = self.cmb_sim.currentText()
            if sim == "LES":
                delta = self.cmb_delta.currentText().strip()
                if not delta:
                    QMessageBox.warning(self, "Missing delta", "LES requires a non-empty 'delta' selection.")
                    return

            model_name = self.cmb_rans.currentText() if sim == "RAS" else self.cmb_les.currentText() if sim == "LES" else ""
            solver = self.solver_edit.text().strip()

            if not solver:
                reply = QMessageBox.question(
                    self,
                    "Solver name empty",
                    "Solver name (application in controlDict) is empty.\nDo you want to go back and enter it?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    return
            else:
                warns = _safe_solver_compat_warnings(solver, sim, model_name)
                suggestion = _best_solver_suggestion(solver)

                if solver and solver not in KNOWN_SOLVERS:
                    if suggestion and suggestion != solver:
                        warns.insert(0, f"Unknown or unsupported solver '{solver}'. Did you mean '{suggestion}'?")
                    else:
                        warns.insert(0, f"Unknown or unsupported solver '{solver}'. Allowed: simpleFoam, pimpleFoam, pisoFoam, potentialFoam.")

                if warns:
                    msg = "Warnings:\n- " + "\n- ".join(warns) + "\n\nContinue anyway?"
                    reply = QMessageBox.question(
                        self,
                        "Solver compatibility / name check",
                        msg,
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    for w in warns:
                        _log_line(f"[compat] {w}")
                    if reply == QMessageBox.No:
                        return
                else:
                    _log_line("[compat] Solver name looks correct.")

            ensure_case_structure()
            self.tp_path = find_case_turbulence_path(self.tp_path)

            text = ensure_header(self._build_text())
            self.tp_path.write_text(text)
            print("[OK] turbulenceProperties written.")

            copy_needed_zero_files(sim, model_name)
            prune_unneeded_zero_files(sim, model_name)
            try:
                apply_wall_bcs(sim, model_name, CASE)
            except Exception as e:
                _log_line(f"Auto-apply wall BCs error: {e}")

            try:
                rebuild_zero_fields_from_mesh(CASE)
            except Exception as e:
                _log_line(f"rebuild_zero_fields_from_mesh error: {e}")

            try:
                zdir = CASE / "0"
                if zdir.exists():
                    for f in zdir.iterdir():
                        if f.is_file():
                            f.write_text(_fix_field_dictionary(f.read_text(errors="ignore")))
            except Exception as e:
                _log_line(f"final fix pass on 0/* failed: {e}")

            _write_control_dict_application(self.solver_edit.text())
            print("[OK] controlDict 'application' updated (if provided).")

            app = _read_application_from_controlDict(CASE)
            fam = _solver_family_from_application(app)
            _apply_fvsolution_template(CASE, TEMPLATE, fam)

            try:
                removed = 0
                for d in CASE.iterdir():
                    if d.is_dir() and d.name.startswith("processor"):
                        shutil.rmtree(d, ignore_errors=True)
                        removed += 1
                if removed:
                    _log_line(f"Removed {removed} existing processor* directories after fvSolution templating.")
            except Exception as e:
                print(f"[i] Could not remove existing processor* directories: {e}")

            print("[OK] Turbulence setup completed.")

            reply = QMessageBox.question(
                self,
                "Run solver now?",
                "Do you want to run the CFD solver now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                print("[i] User chose to run the solver now.")
                print("\n" + "="*60 + "\n==> 5. Running CFD solver" + "\n" + "="*60)

                self.close()
                QApplication.processEvents()

                proc = subprocess.run(
                    [sys.executable, str((REPO / "scripts" / "remote_run_helper.py").resolve()),
                     "--case", str(CASE.resolve())],
                    check=False
                )
                if proc.returncode == 200:
                    print("[i] Remote run selected. Skipping local solver launch.")
                    _pipeline_banner(True, "PIPELINE")
                    return

                try:
                    DECOMP_HELPER = (REPO / "scripts" / "decompose_widget.py").resolve()
                    if DECOMP_HELPER.exists():
                        print("[..] Opening decompose GUI to configure decomposeParDict ...")
                        subprocess.run(
                            [sys.executable, str(DECOMP_HELPER),
                             "--dict", str((CASE / "system" / "decomposeParDict").resolve())],
                            check=False
                        )
                        print("[OK] Decompose GUI closed.")
                    else:
                        print(f"[i] decompose_widget.py not found at: {DECOMP_HELPER} (skipping GUI).")
                except Exception as e:
                    print(f"[i] Could not open decompose GUI: {e} (skipping GUI).")

                try:
                    solver = _read_solver_from_case_control_dict(CASE)
                    nsub = _parse_number_of_subdomains_from_case(CASE)
                    print(f"[..] Preparing to run solver: {solver} ({'multi-cores' if nsub > 1 else 'single-core'})")
                    if nsub > 1:
                        proc_dirs = [p for p in CASE.iterdir() if p.is_dir() and p.name.startswith("processor")]
                        if proc_dirs:
                            print("[i] Cleaning existing 'processor*' directories before decomposePar ...")
                            for d in proc_dirs:
                                shutil.rmtree(d, ignore_errors=True)
                            _log_line("Removed existing processor* directories prior to decomposePar.")
                        _run_and_log('decomposePar', CASE, 'log_decomposePar_sim.txt')

                        try:
                            _sync_system_to_processors(CASE)
                        except Exception as e:
                            print(f"[i] Could not sync system to processors: {e}")

                        _run_and_log(f"mpirun -np {nsub} {solver} -parallel", CASE, 'log_solver.txt')

                        if solver == "potentialFoam":
                            _run_and_log('reconstructPar -withZero', CASE, 'log_reconstructSim.txt')
                        else:
                            _run_and_log('reconstructPar', CASE, 'log_reconstructSim.txt')

                    else:
                        _run_and_log(solver, CASE, 'log_solver.txt')
                    print("[OK] Solver run completed.")
                    _pipeline_banner(True, "PIPELINE")
                    return
                except subprocess.CalledProcessError as e:
                    print(f"[!] Solver run failed with return code {e.returncode}. See logs for details.")
                    _pipeline_banner(False, "PIPELINE")
                    return
                except Exception as e:
                    print(f"[!] Solver run failed: {e}")
                    _pipeline_banner(False, "PIPELINE")
                    return
            else:
                print("[i] User chose not to run the solver now.")
                self.close()
                _pipeline_banner(True, "PIPELINE")
                return

        except Exception as e:
            print(f"[!] Turbulence setup failed: {e}")
            _pipeline_banner(False, "PIPELINE")
            return

def _redirect_stderr_fd_to_log():
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        f = open(LOG_STDERR, "a")
        os.dup2(f.fileno(), 2)
    except Exception:
        pass

def main():
    _redirect_stderr_fd_to_log()

    ap = argparse.ArgumentParser(description="Turbulence GUI for turbulenceProperties (laminar / RANS / LES)")
    ap.add_argument("--file", help="Path to case/constant/turbulenceProperties", default=None)
    args = ap.parse_args()

    target = find_case_turbulence_path(Path(args.file).expanduser()) if args.file else find_case_turbulence_path(None)

    set_qt_env()
    app = QApplication(sys.argv)
    apply_fusion_dark(app)
    gui = TurbulenceGui(target)
    gui.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
