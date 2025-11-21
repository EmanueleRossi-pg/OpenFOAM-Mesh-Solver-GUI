#!/usr/bin/env python3
import os
import shutil
import subprocess
import argparse
import re
import math
from generate_blockMeshDict import compute_bounds   # type: ignore

# === PARSE ARGUMENTS ===
parser = argparse.ArgumentParser(
    description="Generate single case structure and mesh dicts with dynamic snappy refinement"
)
parser.add_argument("--subdomains", type=int, default=4,
                    help="Number of subdomains for parallel decomposition")
args = parser.parse_args()
nSub = args.subdomains

# === BASE PATHS ===
script_dir    = os.path.dirname(os.path.abspath(__file__))
src_dir       = os.path.dirname(script_dir)
template_case = os.path.join(src_dir, "templateCase")
stl_folder    = os.path.join(src_dir, "inputSTL")
case_dir      = os.path.join(src_dir, "case")  # Single-case directory

# Template files
snappy_tmpl   = os.path.join(src_dir, "mesh", "snappyHexMeshDict")
surface_tmpl  = os.path.join(src_dir, "mesh", "surfaceFeatureExtractDict")
block_tmpl    = os.path.join(script_dir, "generate_blockMeshDict.py")

# Ensure single case directory fresh
if os.path.isdir(case_dir):
    shutil.rmtree(case_dir)
shutil.copytree(template_case, case_dir)

# Load templates
with open(snappy_tmpl) as f:
    snappy_template = f.read()
with open(surface_tmpl) as f:
    surface_template = f.read()

# Helper to read blockMesh bounds
def read_block_bounds(bmd_path):
    data = open(bmd_path).read()
    xs = re.search(r"xmin\s+([\-\d\.]+);.*xmax\s+([\-\d\.]+);", data, re.S)
    ys = re.search(r"ymin\s+([\-\d\.]+);.*ymax\s+([\-\d\.]+);", data, re.S)
    zs = re.search(r"zmin\s+([\-\d\.]+);.*zmax\s+([\-\d\.]+);", data, re.S)
    return (float(xs.group(1)), float(xs.group(2)),
            float(ys.group(1)), float(ys.group(2)),
            float(zs.group(1)), float(zs.group(2)))

# Detect single STL file
stl_files = [f for f in os.listdir(stl_folder) if f.lower().endswith('.stl')]
if not stl_files:
    raise FileNotFoundError(f"No STL found in {stl_folder}")
fname = stl_files[0]
stl_name = os.path.splitext(fname)[0]
print(f"--> Generating case from {fname}")

# 1.5) Rename patch names in all 0/field files (U, p, nut, nuTilda)
for field in ["U", "p", "nuTilda", "nut"]:
    f0 = os.path.join(case_dir, "0", field)
    if not os.path.isfile(f0):
        continue
    text = open(f0).read()
    text = re.sub(r"\bplaceholder\b", stl_name, text)
    text = re.sub(r"\bcylinderGroup\b", stl_name + "Group", text)
    text = re.sub(r"\bcylinder\b", stl_name, text)
    open(f0, "w").write(text)

# 2) Patch decomposeParDict
dp = os.path.join(case_dir, "system", "decomposeParDict")
with open(dp) as f:
    lines = f.read().splitlines()
with open(dp, "w") as f:
    for L in lines:
        if L.strip().startswith("numberOfSubdomains"):
            f.write(f"numberOfSubdomains {nSub};\n")
        else:
            f.write(L + "\n")

# 3) Copy STL
tri_dir = os.path.join(case_dir, "constant", "triSurface")
os.makedirs(tri_dir, exist_ok=True)
stl_dst = os.path.join(tri_dir, fname)
shutil.copy(os.path.join(stl_folder, fname), stl_dst)

# 4) Generate blockMeshDict (based on the *original* STL bounds)
bmd_out = os.path.join(case_dir, "system", "blockMeshDict")
subprocess.run([
    "python3", block_tmpl,
    "--template", os.path.join(template_case, "system", "blockMeshDict"),
    "--stl", stl_dst,
    "--output", bmd_out,
    "--cells", "0.35 0.35 1"
], check=True)

# 5) Prepare snappyHexMeshDict
snappy_path = os.path.join(case_dir, "system", "snappyHexMeshDict")

# === prefer original STL until *_oriented.stl exists; then switch to oriented ===
base_noext = os.path.splitext(fname)[0]
oriented_stl_path = os.path.join(tri_dir, f"{base_noext}_oriented.stl")

if os.path.exists(oriented_stl_path):
    geom_stl_name  = f"{base_noext}_oriented.stl"
    geom_emesh_name = f"{base_noext}_oriented.eMesh"
else:
    geom_stl_name  = f"{base_noext}.stl"
    geom_emesh_name = f"{base_noext}.eMesh"

# Compute refinementBox from the *original* STL bounds (box stays fixed)
xmin_m, xmax_m, ymin_m, ymax_m, zmin_m, zmax_m = read_block_bounds(bmd_out)
stl_xmin, stl_xmax, stl_ymin, stl_ymax, stl_zmin, stl_zmax = compute_bounds(stl_dst)

# Initial locationInMesh from original bounds (will be recomputed on oriented later in mesh_pipeline_gui.py)
loc_str = f"    locationInMesh ({stl_xmax + (xmax_m-stl_xmax)/2:.6f} {stl_ymax + (ymax_m-stl_ymax)/2:.6f} {stl_zmax + (zmax_m-stl_zmax)/2:.6f});"

# refinementBox: keep the existing recipe (padding in min; mix with domain max on x as before)
M2 = 2
ref_min = f"        min ({stl_xmin-M2:.6f} {stl_ymin-M2:.6f} {stl_zmin-M2:.6f});"
ref_max = f"        max ({xmax_m:.6f} {stl_ymax+M2:.6f} {stl_zmax+M2:.6f});"

sdict = snappy_template.replace("placeholder", stl_name)
sdict = sdict.replace("cylinder.stl", geom_stl_name).replace("cylinder.eMesh", geom_emesh_name)

out = []
inject = False
in_ref = False
for L in sdict.splitlines():
    s = L.strip()
    if s == "castellatedMeshControls":
        out.append(L)
        inject = True
        continue
    if inject and s == "{":
        out.append(L)
        out.append(loc_str)
        inject = False
        continue
    if s.startswith("refinementBox"):
        in_ref = True
        out.append(L)
        continue
    if in_ref and s.startswith("min ("):
        out.append(ref_min)
        continue
    if in_ref and s.startswith("max ("):
        out.append(ref_max)
        in_ref = False
        continue
    out.append(L)

# --- fix section boundaries and remove duplicate blocks before writing ---
txt = "\n".join(out)

# 1) Ensure a clean newline boundary when a block closes and the next begins
#    e.g. '};addLayersControls' -> '};\n\naddLayersControls'
txt = re.sub(r'\}\s*;\s*(?=(snapControls|addLayersControls|meshQualityControls)\b)', '};\n\n', txt)

# 2) Also ensure each of these blocks starts on its own line if preceded by stray semicolons
txt = re.sub(r';\s*(?=(snapControls|addLayersControls|meshQualityControls)\b)', '\n', txt)

# 3) De-duplicate blocks: keep the first full block for each key and drop the rest
def _drop_duplicates(full_text: str, key: str) -> str:
    # find all block spans "key { ... }"
    pat_start = re.compile(r'(^|\s)'+re.escape(key)+r'\s*\{', re.MULTILINE)
    spans = []
    pos = 0
    while True:
        m = pat_start.search(full_text, pos)
        if not m:
            break
        i = full_text.find('{', m.end()-1)
        if i < 0:
            break
        depth, j = 1, i+1
        while j < len(full_text) and depth > 0:
            c = full_text[j]
            if c == '{': depth += 1
            elif c == '}': depth -= 1
            j += 1
        spans.append((m.start(), j))
        pos = j
    if len(spans) <= 1:
        return full_text
    # keep the first, remove the rest
    keep0 = spans[0]
    pieces = [full_text[:keep0[1]]]
    last = keep0[1]
    for a,b in spans[1:]:
        pieces.append(full_text[last:a])
        last = b
    pieces.append(full_text[last:])
    return "".join(pieces)

for key in ("snapControls", "addLayersControls", "meshQualityControls"):
    txt = _drop_duplicates(txt, key)

open(snappy_path, "w").write(txt + "\n")

# 6) surfaceFeatureExtractDict: also use the oriented STL name
surf = surface_template.replace("cylinder.stl", geom_stl_name)
open(os.path.join(case_dir, "system", "surfaceFeatureExtractDict"), "w").write(surf)

print(f"✔ case ready from {fname}")
