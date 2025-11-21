README – GUI pipelines for OpenFOAM cases
========================================

Overview
--------

This project provides a set of Python/Qt GUIs that wrap a typical
OpenFOAM® workflow for incompressible cases starting from an STL
geometry. The goal is to automate the repetitive parts of case
preparation while keeping all OpenFOAM dictionaries fully transparent
and editable.

The system is organized around two main pipelines:

- **Mesh pipeline**
  - Import and orientation of an STL geometry.
  - Background mesh generation (`blockMesh`).
  - Feature extraction (`surfaceFeatureExtract`).
  - `snappyHexMesh` configuration (castellation, snap, layers).
  - Mesh quality presets + `checkMesh`.
  - Optional ParaView mesh snapshots.

- **Turbulence / solver pipeline**
  - Selection of simulation type (laminar / RANS / LES).
  - Choice of turbulence model and compatible solver.
  - Automatic update of `turbulenceProperties`, `controlDict`,
    and fields in `0/`.
  - Optional multi-core and remote run helper.

The working `case/` directory is **created at runtime** by the pipeline
(from `templateCase/`) and will contain `0/`, `constant/` (with
`polyMesh`, `triSurface`), `system/`, and a `logs/` folder.


Requirements
------------

- **OS**
  - GNU/Linux (tested with an OpenFOAM v2412-style layout).

- **OpenFOAM** (ESI/OpenCFD-style installation) providing at least:
  - Mesh tools: `blockMesh`, `surfaceFeatureExtract`, `snappyHexMesh`,
    `checkMesh`.
  - Incompressible solvers: `simpleFoam`, `pimpleFoam`, `pisoFoam`,
    `icoFoam`, `potentialFoam`.
  - Standard utilities for parallel runs (`decomposePar`,
    `reconstructPar`).

- **Python**
  - Python 3.8 or newer.
  - Required packages (installed via `requirements.txt`):
    - PyQt (Qt GUI bindings, e.g. PyQt5).
    - NumPy.
    - Matplotlib (used via the non-interactive Agg backend).
    - Any additional packages listed in `requirements.txt`.

- **ParaView** (optional, for screenshots)
  - `pvpython` available in `PATH` for scripted mesh snapshots.

- **MPI** (optional, for multi-core runs)
  - An `mpirun` provider (e.g. OpenMPI) if you intend to run in
    parallel (`-parallel`).


Installation
------------

1. Make sure OpenFOAM is installed and its environment is sourced
   (e.g. `source /opt/openfoam/.../etc/bashrc`).

2. Clone or copy this repository.

3. (Optional) Create and activate a Python virtual environment:

   ```bash
   cd path/to/project
   python3 -m venv venv
   source venv/bin/activate

Install Python dependencies:    pip install -r requirements.txt

(Optional) Add ParaView’s pvpython to your PATH if you want
automatic mesh snapshots.

Project structure

Top-level layout (simplified):

run.py
Launcher script (small GUI) that lets you choose:

Mesh pipeline (full meshing workflow).

Turbulence setup (focus on turbulence/solver and fields).

clear_all.py
Resets the project to a clean state (removes case/, logs, and
some temporary artifacts) after asking for confirmation.

requirements.txt
Python dependencies.

inputSTL/
Contains the input STL geometry.

In the demo case: monkey.stl.

The pipeline expects one STL in this folder.

mesh/
Base OpenFOAM dictionaries for mesh generation:

snappyHexMeshDict

surfaceFeatureExtractDict
These are copied into case/system/ and updated by the GUIs.

scripts/
Main Python modules implementing the pipelines and GUIs:

mesh_pipeline_gui.py

snappy_gui.py

orient_widget.py

snap_widget.py

layers_widget.py

decompose_widget.py

turbulence_widget.py

remote_run_helper.py

preview3d.py, mesh_snapshot.py

log_monitor.py

case_structure.py

quality_presets.py

sanity_check.py

ui_theme.py

templateCase/
Template OpenFOAM case used as a base for all runs:

0/ (initial fields: p, U, turbulence variables).

constant/ (e.g. transportProperties,
turbulenceProperties).

system/

blockMeshDict

snappyHexMeshDict

decomposeParDict

fvSchemes, fvSolution

fvSolutionTemplate_PISO, _PIMPLE, _SIMPLE,
_POTENTIAL

controlDict

meshQualityDict

The pipeline copies templateCase/ to a working case/ directory and
then updates the files according to GUI choices and mesh / run results.

Quick start

Put exactly one STL file into inputSTL/ (for example,
monkey.stl).

Open a terminal, activate your virtual environment, and run:     source venv/bin/activate        
python3 run.py


In the launcher window, choose:

“Mesh pipeline” to go through the full meshing workflow.

“Turbulence setup” to focus on turbulence/solver only.

For the mesh pipeline:

Optionally use the STL orientation GUI to rotate/translate
the geometry and save <name>_oriented.stl. The pipeline will
update dicts to reference the oriented STL.

Step through the GUIs for:

snappyHexMesh main options.

Snap controls.

Layers controls.

Quality presets.

Decomposition (decomposeParDict) if you want multi-core.

The pipeline then runs:

blockMesh

surfaceFeatureExtract

snappyHexMesh (single- or multi-core)

checkMesh

If pvpython is available, mesh snapshots (PNG) are created.

After meshing, you are asked whether to run a solver:

The code reads system/controlDict:application.

Runs single-core or multi-core according to
system/decomposeParDict.

If multi-core:

decomposePar

mpirun -np N <solver> -parallel

reconstructPar at the end.

All logs go to case/logs/.
The case can be opened in ParaView using case/case.foam.

Detailed mesh pipeline

1) Case preparation

Ensure case/ exists; if not, create it from templateCase/.

Copy the STL from inputSTL/ into case/constant/triSurface/.

Create case/case.foam (convenience file for ParaView).

Sanity-check headers (e.g. constant/thermophysicalProperties).

2) STL orientation (optional)

Launch orient_widget.py:

Interactive rotate/translate of the STL.

Save an oriented file: <name>_oriented.stl.

Update:

snappyHexMeshDict to reference the oriented STL.

surfaceFeatureExtractDict similarly.

Optionally adjust locationInMesh based on domain extents.

Use the 3D preview to verify orientation vs. the domain.

3) Background mesh and feature extraction

Run blockMesh to build the background grid.

Run surfaceFeatureExtract to capture edges/creases in the STL
used by snapping and refinement.

4) snappyHexMesh configuration and run

Open the main snappy_gui.py editor:

Enable/disable castellatedMesh, snap, addLayers.

Change defaults; use “Reset to defaults” to return to a safe base.

Open supporting GUIs as needed:

snap_widget.py for snapControls:

Tolerances.

Iteration counts.

Smoothing options.

layers_widget.py for addLayersControls:

relativeSizes.

Number of surface layers.

expansionRatio.

finalLayerThickness and minThickness.

quality_presets.py:

Select mesh-quality presets that update both
meshQualityControls in snappyHexMeshDict and
meshQualityDict for checkMesh.

decompose_widget.py:

Choose decomposition method (e.g. scotch).

Number of subdomains and optional parameters.

Before multi-core meshing:

Rebuild 0/* patch fields to match mesh patches.

Sync system/ into processor*/system if needed.

Run snappyHexMesh:

Single-core: snappyHexMesh -overwrite.

Multi-core:

decomposePar

mpirun -np N snappyHexMesh -overwrite -parallel

reconstructParMesh (if used) or equivalent steps.

After meshing:

Re-sync 0/* so boundaryField entries match the final mesh.

5) Mesh quality

Run checkMesh -allGeometry -allTopology.

Inspect results in case/logs/.

If quality is unsatisfactory, reopen:

Snap/Layers/Quality GUIs.

Adjust parameters and re-run snappy + checkMesh.

6) Mesh snapshots (optional)

If pvpython is found in PATH, run mesh_snapshot.py:

Generates PNG snapshots of the mesh (e.g. slices, wireframe).

7) Solver run (incompressible)

Optionally start the solver directly from the pipeline.

Reads system/controlDict:application to determine which solver.

Single-core:

<solver> directly in case/.

Multi-core:

decomposePar

mpirun -np N <solver> -parallel

reconstructPar to gather results back into case/.

The pipeline applies standard OpenFOAM practices for time stepping:

For example, using adjustable time step and limiting the Courant
number (maxCo) for stability.

Turbulence / solver GUI

scripts/turbulence_widget.py provides a dedicated GUI to set up
turbulence models and the solver:

Simulation type

Laminar, RANS, or LES (incompressible focus).

Writes simulationType in constant/turbulenceProperties.

Turbulence model

Choose from supported RANS or LES models (e.g. kOmegaSST,
kEpsilon, SpalartAllmaras if configured).

Writes RASModel or LESModel in turbulenceProperties.

Solver selection

Text field for system/controlDict:application.

A “Check” button provides hints about consistent model/solver
pairings (informational only).

Field handling

Rebuilds 0/* patch lists from constant/polyMesh/boundary.

Ensures fields contain entries for all patches with reasonable
defaults.

Keeps syntax correct (braces, semicolons, headers).

fvSolution templating

Reads application and maps to a solver family
(SIMPLE / PISO / PIMPLE / potential).

Copies the corresponding template (e.g.
fvSolutionTemplate_PIMPLE) into case/system/fvSolution.

Removes stale processor* directories when appropriate to
prevent multi-core inconsistencies.

This GUI can be run independently from the mesh pipeline (via
run.py) to tweak turbulence and solver settings even after meshing.

Other helper scripts

case_structure.py

Creates and updates the case/ directory from templateCase/.

Ensures a predictable layout for the pipelines.

orient_widget.py

STL viewer and transformer (rotate/translate).

Saves an oriented STL for use by the meshing pipeline.

snappy_gui.py, snap_widget.py, layers_widget.py

Editors for different sections of system/snappyHexMeshDict.

quality_presets.py

Applies predefined quality profiles to both snappyHexMesh and
checkMesh dictionaries.

sanity_check.py

Light sanity checks on snappy settings and geometry.

log_monitor.py

Tails log_snappyHexMesh.txt:

Shows warnings/errors count.

Optional auto-scroll.

Button to open the log in an external editor.

mesh_snapshot.py

Uses pvpython to create mesh screenshots (PNG) from the case.

remote_run_helper.py

Helper to generate commands/scripts for remote runs via SSH/SLURM.

Lets you choose between local and remote execution.

Handles user@host and remote path configuration.

Returns a special status so the pipeline can skip local solver runs
if the user prefers remote execution.

ui_theme.py

Centralizes visual styling for the GUIs (colors, fonts, etc.).

Parallel runs (multi-core)

When you configure system/decomposeParDict via the GUI, the pipeline
can use multi-core execution both for meshing and for the solver:

Clean up any stale processor*/ directories.

Run decomposePar.

Sync system/ into each processor*/system.

Launch:

mpirun -np N snappyHexMesh -overwrite -parallel and/or

mpirun -np N <solver> -parallel.

Run reconstructPar or the appropriate reconstruction command to
gather results back into case/.

This follows the standard OpenFOAM domain decomposition and
reconstruction workflow.

Outputs

After running the pipelines, you can expect:

case/0/
Initial / latest fields for p, U, turbulence variables, etc.

case/constant/

polyMesh/ (final mesh).

triSurface/ (STL).

Physical properties (transportProperties,
turbulenceProperties, …).

case/system/

Updated dictionaries (blockMeshDict, snappyHexMeshDict,
fvSchemes, fvSolution, decomposeParDict, controlDict,
meshQualityDict, …).

case/constant/polyMesh.base/

Backup of the background mesh (useful to speed up re-runs after
changing snappy settings).

case/logs/

Logs for:

blockMesh

surfaceFeatureExtract

snappyHexMesh

checkMesh

Solver runs

GUI tools (Qt / GL warnings redirected here).

case/*.png

Mesh snapshots (if pvpython is available).

case/<time directories>/

Solver output fields for each saved time step.

case/case.foam

Convenience file to open the case directly in ParaView.

License and notes

This project glues together Python scripts and standard OpenFOAM /
ParaView tools.

OpenFOAM® and ParaView® are trademarks of their respective owners and
are licensed separately.

The license for this code base is defined by your project (fill in
or adjust this section as appropriate for your distribution).
