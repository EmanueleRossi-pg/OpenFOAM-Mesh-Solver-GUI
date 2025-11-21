#!/usr/bin/env python3
import os
import re
import argparse
from stl import mesh   # type: ignore

def compute_bounds(stl_path):
    """Read STL and return (xmin,xmax,ymin,ymax,zmin,zmax)."""
    m = mesh.Mesh.from_file(stl_path)
    pts = list(m.v0) + list(m.v1) + list(m.v2)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)

def main():
    parser = argparse.ArgumentParser(
        description="Generate blockMeshDict from STL bounds"
    )
    parser.add_argument("--template", required=True,
                        help="Path to template blockMeshDict")
    parser.add_argument("--stl", required=True,
                        help="Path to input STL file")
    parser.add_argument("--output", required=True,
                        help="Path to write new blockMeshDict")
    parser.add_argument("--cells", type=str, default="200 50 1",
                        help="Cell counts in X Y Z")
    args = parser.parse_args()

    # --- compute STL bounds and characteristic length D ---
    xmin, xmax, ymin, ymax, zmin, zmax = compute_bounds(args.stl)
    D = max(xmax - xmin, ymax - ymin, zmax - zmin)

    # --- save originals ---
    orig_xmin, orig_xmax = xmin, xmax
    orig_ymin, orig_ymax = ymin, ymax
    orig_zmin, orig_zmax = zmin, zmax

    # --- build domain box extents: X-axis oriented ---
    # upstream (negative X) = 3·D, downstream = 15·D, Y/Z = ±3·D
    xmin = orig_xmin - 3 * D
    xmax = orig_xmax + 15 * D
    ymin = orig_ymin - 3 * D
    ymax = orig_ymax + 3 * D
    zmin = orig_zmin - 3 * D
    zmax = orig_zmax + 3 * D

    # --- read template ---
    lines = open(args.template).read().splitlines()

    # --- regex patterns for parameters ---
    patterns = {
        "xmin": re.compile(r"^(\s*xmin\s+).+?;"),
        "xmax": re.compile(r"^(\s*xmax\s+).+?;"),
        "ymin": re.compile(r"^(\s*ymin\s+).+?;"),
        "ymax": re.compile(r"^(\s*ymax\s+).+?;"),
        "zmin": re.compile(r"^(\s*zmin\s+).+?;"),
        "zmax": re.compile(r"^(\s*zmax\s+).+?;"),
        "dx":   re.compile(r"^(\s*dx\s+).+?;"),
        "dy":   re.compile(r"^(\s*dy\s+).+?;"),
        "dz":   re.compile(r"^(\s*dz\s+).+?;"),
        # ---- ensure x/y/z cells use max(1, int(ceil(...))) ----
        "xcells": re.compile(r"^(\s*xcells\s+).+?;"),
        "ycells": re.compile(r"^(\s*ycells\s+).+?;"),
        "zcells": re.compile(r"^(\s*zcells\s+).+?;"),
    }

    # --- parse cell counts ---
    dx, dy, dz = map(float, args.cells.split())

    # --- map values for replacement ---
    values = {
        "xmin": xmin,
        "xmax": xmax,
        "ymin": ymin,
        "ymax": ymax,
        "zmin": zmin,
        "zmax": zmax,
        "dx": dx,
        "dy": dy,
        "dz": dz
    }

    # --- perform substitution ---
    out = []
    for line in lines:
        replaced = False
        for key, pat in patterns.items():
            if pat.match(line):
                if key in ("xcells", "ycells", "zcells"):
                    
                    if key == "xcells":
                        expr = 'max(1, int(ceil($lx/$dx)))'
                    elif key == "ycells":
                        expr = 'max(1, int(ceil($ly/$dy)))'
                    else:
                        expr = 'max(1, int(ceil($lz/$dz)))'
                    line = pat.sub(lambda m: m.group(1) + f'#calc "{expr}";', line)
                else:
                    line = pat.sub(lambda m: m.group(1) + f"{values[key]:.6f};", line)
                replaced = True
                break
        out.append(line)

    # --- write result ---
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        f.write("\n".join(out) + "\n")

    print("[OK] blockMeshDict generated successfully")

if __name__ == "__main__":
    main()
