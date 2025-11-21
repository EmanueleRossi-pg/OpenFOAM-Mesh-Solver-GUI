# mesh_snapshot.py
# trace generated using paraview version 5.13.3
# import paraview
# paraview.compatibility.major = 5
# paraview.compatibility.minor = 13

# NOTE: If you see GUI windows/flashes while this script runs,
# that's on-screen rendering. Run offscreen/headless instead, e.g.:
#   pvbatch src/scripts/mesh_snapshot.py
# or:
#   pvpython --force-offscreen-rendering src/scripts/mesh_snapshot.py
# (pvbatch uses offscreen by default; pvpython is on-screen unless forced.)

from pathlib import Path
import os
import contextlib

# ---- ParaView simple API -----------------------------------------------------
from paraview.simple import *  # type: ignore
# disable automatic camera reset on 'Show'
paraview.simple._DisableFirstRenderCameraReset()  # type: ignore

# ---------------- PATHS (relative to this file) -----------------
# This file is in:    <repo>/src/scripts/mesh_snapshot.py
# read:               <repo>/src/case/case.foam
# and save to:        <repo>/src/case/snapshots/*.png
_THIS = Path(__file__).resolve()
_SRC  = _THIS.parent.parent              # .../src
_CASE = _SRC / "case"                    # .../src/case   
_SNAP = _CASE / "snapshots"              # .../src/case/snapshots
_SNAP.mkdir(parents=True, exist_ok=True) 
_FOAM = str((_CASE / "case.foam").resolve())
_IMG1 = str((_SNAP / "mesh_picture.png").resolve())
_IMG2 = str((_SNAP / "mesh_picture_zoom.png").resolve())
# -----------------------------------------------------------------

# Utility: quiet context to suppress stdout/stderr (keeps the terminal clean)
@contextlib.contextmanager
def quiet():
    with open(os.devnull, "w") as _dn, \
         contextlib.redirect_stdout(_dn), \
         contextlib.redirect_stderr(_dn):
        yield

# get active view
renderView1 = GetActiveViewOrCreate('RenderView')  # type: ignore
renderView1.ResetActiveCameraToPositiveY()

# light gray background to avoid white-on-white mesh
renderView1.Background = [0.95, 0.95, 0.95]

# reset view to fit data
renderView1.ResetCamera(False, 0.9)

# initial camera placement
renderView1.CameraPosition = [0.0, -6.6921304299024635, 0.0]
renderView1.CameraFocalPoint = [0.0, 1e-20, 0.0]
renderView1.CameraViewUp = [0.0, 0.0, 1.0]
renderView1.CameraParallelScale = 1.7320508075688772

# ---------------- READ CASE ----------------
casefoam = OpenFOAMReader(registrationName='case.foam', FileName=_FOAM)  # type: ignore
casefoam.SkipZeroTime = 1
casefoam.CaseType = 'Reconstructed Case'
casefoam.LabelSize = '32-bit'
casefoam.ScalarSize = '64-bit (DP)'
casefoam.Createcelltopointfiltereddata = 1
casefoam.Adddimensionalunitstoarraynames = 0
casefoam.MeshRegions = ['internalMesh']
casefoam.CellArrays = []
casefoam.PointArrays = []
casefoam.LagrangianArrays = []
casefoam.Cachemesh = 1
casefoam.WeightPointDataByCellSize = 0
casefoam.ListtimestepsaccordingtocontrolDict = 0
casefoam.Lagrangianpositionswithoutextradata = 1
casefoam.Readzones = 0
casefoam.Copydatatocellzones = 0

# show axes grid 
renderView1.AxesGrid.Visibility = 1

# align animation scene to data timesteps
scene = GetAnimationScene()  # type: ignore
scene.UpdateAnimationUsingDataTimeSteps()

# if timesteps exist, move to the first one
try:
    ts = casefoam.TimestepValues
    if ts and len(ts) > 0:
        SetActiveSource(casefoam) # type: ignore
        animationScene1 = GetAnimationScene() # type: ignore
        animationScene1.AnimationTime = ts[0]
except Exception:
    pass

# show data in view
casefoamDisplay = Show(casefoam, renderView1, 'UnstructuredGridRepresentation')  # type: ignore

# ---- display properties ----
casefoamDisplay.Selection = None
casefoamDisplay.Representation = 'Surface'
casefoamDisplay.ColorArrayName = [None, '']
casefoamDisplay.LookupTable = None
casefoamDisplay.MapScalars = 1
casefoamDisplay.MultiComponentsMapping = 0
casefoamDisplay.InterpolateScalarsBeforeMapping = 1
casefoamDisplay.UseNanColorForMissingArrays = 0
casefoamDisplay.Opacity = 1.0
casefoamDisplay.PointSize = 2.0
casefoamDisplay.LineWidth = 1.0
casefoamDisplay.RenderLinesAsTubes = 0
casefoamDisplay.RenderPointsAsSpheres = 0
casefoamDisplay.DisableLighting = 0
casefoamDisplay.Diffuse = 1.0
casefoamDisplay.Interpolation = 'Gouraud'
casefoamDisplay.Specular = 0.0
casefoamDisplay.SpecularColor = [1.0, 1.0, 1.0]
casefoamDisplay.SpecularPower = 100.0
casefoamDisplay.Luminosity = 0.0
casefoamDisplay.Ambient = 0.0
casefoamDisplay.Roughness = 0.3
casefoamDisplay.Metallic = 0.0
casefoamDisplay.EdgeTint = [1.0, 1.0, 1.0]
casefoamDisplay.Anisotropy = 0.0
casefoamDisplay.AnisotropyRotation = 0.0
casefoamDisplay.BaseIOR = 1.5
casefoamDisplay.CoatStrength = 0.0
casefoamDisplay.CoatIOR = 2.0
casefoamDisplay.CoatRoughness = 0.0
casefoamDisplay.CoatColor = [1.0, 1.0, 1.0]
casefoamDisplay.SelectNormalArray = 'None'
casefoamDisplay.SelectTangentArray = 'None'
casefoamDisplay.ComputePointNormals = 0
casefoamDisplay.Splitting = 1
casefoamDisplay.FeatureAngle = 30.0
casefoamDisplay.SelectTCoordArray = 'None'
casefoamDisplay.Texture = None
casefoamDisplay.RepeatTextures = 1
casefoamDisplay.InterpolateTextures = 0
casefoamDisplay.SeamlessU = 0
casefoamDisplay.SeamlessV = 0
casefoamDisplay.UseMipmapTextures = 0
casefoamDisplay.ShowTexturesOnBackface = 1
casefoamDisplay.BaseColorTexture = None
casefoamDisplay.NormalTexture = None
casefoamDisplay.NormalScale = 1.0
casefoamDisplay.CoatNormalTexture = None
casefoamDisplay.CoatNormalScale = 1.0
casefoamDisplay.MaterialTexture = None
casefoamDisplay.OcclusionStrength = 1.0
casefoamDisplay.AnisotropyTexture = None
casefoamDisplay.EmissiveTexture = None
casefoamDisplay.EmissiveFactor = [1.0, 1.0, 1.0]
casefoamDisplay.TextureTransform = 'Transform2'
casefoamDisplay.EdgeOpacity = 1.0
casefoamDisplay.BackfaceRepresentation = 'Follow Frontface'
casefoamDisplay.BackfaceAmbientColor = [1.0, 1.0, 1.0]
casefoamDisplay.BackfaceOpacity = 1.0
casefoamDisplay.Translation = [0.0, 0.0, 0.0]
casefoamDisplay.Scale = [1.0, 1.0, 1.0]
casefoamDisplay.Orientation = [0.0, 0.0, 0.0]
casefoamDisplay.Origin = [0.0, 0.0, 0.0]
casefoamDisplay.CoordinateShiftScaleMethod = 'Always Auto Shift Scale'
casefoamDisplay.Pickable = 1
casefoamDisplay.Triangulate = 0
casefoamDisplay.UseShaderReplacements = 0
casefoamDisplay.ShaderReplacements = ''
casefoamDisplay.NonlinearSubdivisionLevel = 1
casefoamDisplay.MatchBoundariesIgnoringCellOrder = 0
casefoamDisplay.UseDataPartitions = 0
casefoamDisplay.OSPRayUseScaleArray = 'All Approximate'
casefoamDisplay.OSPRayScaleArray = ''
casefoamDisplay.OSPRayScaleFunction = 'Piecewise Function'
casefoamDisplay.OSPRayMaterial = 'None'
casefoamDisplay.Assembly = 'Hierarchy'
casefoamDisplay.SelectedBlockSelectors = ['']
casefoamDisplay.BlockSelectors = ['/']
casefoamDisplay.BlockColors = []
casefoamDisplay.BlockColorArrayNames = []
casefoamDisplay.BlockLookupTables = []
casefoamDisplay.BlockUseSeparateColorMaps = []
casefoamDisplay.BlockMapScalars = []
casefoamDisplay.BlockInterpolateScalarsBeforeMappings = []
casefoamDisplay.BlockOpacities = []
casefoamDisplay.BlockMapScalarsGUI = 1
casefoamDisplay.BlockInterpolateScalarsBeforeMappingsGUI = 1
casefoamDisplay.BlockOpacitiesGUI = 1.0
casefoamDisplay.Orient = 0
casefoamDisplay.OrientationMode = 'Direction'
casefoamDisplay.SelectOrientationVectors = 'None'
casefoamDisplay.Scaling = 0
casefoamDisplay.ScaleMode = 'No Data Scaling Off'
casefoamDisplay.ScaleFactor = 5.195312404632569
casefoamDisplay.SelectScaleArray = 'None'
casefoamDisplay.GlyphType = 'Arrow'
casefoamDisplay.UseGlyphTable = 0
casefoamDisplay.GlyphTableIndexArray = 'None'
casefoamDisplay.UseCompositeGlyphTable = 0
casefoamDisplay.UseGlyphCullingAndLOD = 0
casefoamDisplay.LODValues = []
casefoamDisplay.ColorByLODIndex = 0
casefoamDisplay.GaussianRadius = 0.2597656202316284
casefoamDisplay.ShaderPreset = 'Sphere'
casefoamDisplay.CustomTriangleScale = 3
casefoamDisplay.CustomShader = """ // gaussian blur example
//VTK::Color::Impl
float dist2 = dot(offsetVCVSOutput.xy,offsetVCVSOutput.xy);
float gaussian = exp(-0.5*dist2);
opacity = opacity*gaussian;
"""
casefoamDisplay.Emissive = 0
casefoamDisplay.ScaleByArray = 0
casefoamDisplay.SetScaleArray = [None, '']
casefoamDisplay.ScaleArrayComponent = 0
casefoamDisplay.UseScaleFunction = 1
casefoamDisplay.ScaleTransferFunction = 'Piecewise Function'
casefoamDisplay.OpacityByArray = 0
casefoamDisplay.OpacityArray = [None, '']
casefoamDisplay.OpacityArrayComponent = 0
casefoamDisplay.OpacityTransferFunction = 'Piecewise Function'
casefoamDisplay.DataAxesGrid = 'Grid Axes Representation'
casefoamDisplay.PolarAxes = 'Polar Axes Representation'
casefoamDisplay.ScalarOpacityFunction = None
casefoamDisplay.ScalarOpacityUnitDistance = 0.5835877276188735
casefoamDisplay.UseSeparateOpacityArray = 0
casefoamDisplay.OpacityArrayName = ['FIELD', 'CasePath']
casefoamDisplay.OpacityComponent = 0
casefoamDisplay.SelectMapper = 'Projected tetra'
casefoamDisplay.SamplingDimensions = [128, 128, 128]
casefoamDisplay.UseFloatingPointFrameBuffer = 1
casefoamDisplay.SelectInputVectors = [None, '']
casefoamDisplay.NumberOfSteps = 40
casefoamDisplay.StepSize = 0.25
casefoamDisplay.NormalizeVectors = 1
casefoamDisplay.EnhancedLIC = 1
casefoamDisplay.ColorMode = 'Blend'
casefoamDisplay.LICIntensity = 0.8
casefoamDisplay.MapModeBias = 0.0
casefoamDisplay.EnhanceContrast = 'Off'
casefoamDisplay.LowLICContrastEnhancementFactor = 0.0
casefoamDisplay.HighLICContrastEnhancementFactor = 0.0
casefoamDisplay.LowColorContrastEnhancementFactor = 0.0
casefoamDisplay.HighColorContrastEnhancementFactor = 0.0
casefoamDisplay.AntiAlias = 0
casefoamDisplay.MaskOnSurface = 1
casefoamDisplay.MaskThreshold = 0.0
casefoamDisplay.MaskIntensity = 0.0
casefoamDisplay.MaskColor = [0.5, 0.5, 0.5]
casefoamDisplay.GenerateNoiseTexture = 0
casefoamDisplay.NoiseType = 'Gaussian'
casefoamDisplay.NoiseTextureSize = 128
casefoamDisplay.NoiseGrainSize = 2
casefoamDisplay.MinNoiseValue = 0.0
casefoamDisplay.MaxNoiseValue = 0.8
casefoamDisplay.NumberOfNoiseLevels = 1024
casefoamDisplay.ImpulseNoiseProbability = 1.0
casefoamDisplay.ImpulseNoiseBackgroundValue = 0.0
casefoamDisplay.NoiseGeneratorSeed = 1
casefoamDisplay.CompositeStrategy = 'AUTO'
casefoamDisplay.UseLICForLOD = 0
casefoamDisplay.WriteLog = ''

# reset view to fit data and update
renderView1.ResetCamera(False, 0.9)
materialLibrary1 = GetMaterialLibrary()  # type: ignore
renderView1.Update()

# camera placement 
renderView1.CameraPosition = [16.406250476837158, -112.05934030372487, 0.0]
renderView1.CameraFocalPoint = [16.406250476837158, 0.0, 0.0]
renderView1.CameraViewUp = [0.0, 0.0, 1.0]
renderView1.CameraParallelScale = 29.003091452228485

renderView1.ResetActiveCameraToPositiveY()
renderView1.ResetCamera(False, 0.9)

renderView1.CameraPosition = [16.406250476837158, -112.05934030372487, 0.0]
renderView1.CameraFocalPoint = [16.406250476837158, 0.0, 0.0]
renderView1.CameraViewUp = [0.0, 0.0, 1.0]
renderView1.CameraParallelScale = 29.003091452228485

# ---------------- SLICE ----------------
slice1 = Slice(registrationName='Slice1', Input=casefoam)  # type: ignore
slice1.SliceType = 'Plane'
slice1.HyperTreeGridSlicer = 'Plane'
slice1.UseDual = 0
slice1.Crinkleslice = 0
slice1.Triangulatetheslice = 1
slice1.SliceOffsetValues = [0.0]
slice1.PointMergeMethod = 'Uniform Binning'

slice1.SliceType.Origin = [16.406250476837158, 0.0, 0.0]
slice1.SliceType.Normal = [1.0, 0.0, 0.0]
slice1.SliceType.Offset = 0.0

slice1.HyperTreeGridSlicer.Origin = [16.406250476837158, 0.0, 0.0]
slice1.HyperTreeGridSlicer.Normal = [1.0, 0.0, 0.0]
slice1.HyperTreeGridSlicer.Offset = 0.0

slice1.PointMergeMethod.Divisions = [50, 50, 50]
slice1.PointMergeMethod.Numberofpointsperbucket = 8

# hide interactive widget (GUI)
HideInteractiveWidgets(proxy=slice1.SliceType)  # type: ignore

# cut in Y 
slice1.SliceType.Origin = [16.406250476837158, 0.03, 0.0]
slice1.SliceType.Normal = [0.0, 1.0, 0.0]

slice1Display = Show(slice1, renderView1, 'GeometryRepresentation')  # type: ignore
slice1Display.Representation = 'Surface'
slice1Display.SetRepresentationType('Surface With Edges')

# hide full geometry, show only the slice
Hide(casefoam, renderView1)  # type: ignore
renderView1.Update()

# small camera moves 
renderView1.CameraPosition = [16.442213117255264, -52.27650927312165, -3.236637637629254]
renderView1.CameraFocalPoint = [16.442213117255264, 0.0, -3.236637637629254]
renderView1.CameraViewUp = [0.0, 0.0, 1.0]
renderView1.CameraParallelScale = 29.003091452228485

layout1 = GetLayout()  # type: ignore
layout1.SetSize(1546, 779)

# ---------------- CAPTURES ----------------
# explicit render 
with quiet():
    RenderAllViews() # type: ignore
    SaveScreenshot( # type: ignore
        filename=_IMG1,
        viewOrLayout=renderView1,
        location=16,
        ImageResolution=[1546, 779],
        FontScaling='Scale fonts proportionally',
        OverrideColorPalette='',
        StereoMode='No change',
        TransparentBackground=0,
        SaveInBackground=0,
        EmbedParaViewState=0,
        CompressionLevel='5',
        MetaData=['Application', 'ParaView'],
    )

# “zoom” steps 
renderView1.CameraPosition = [7.9190673381649015, -35.70555923305896, -2.445459548430992]
renderView1.CameraFocalPoint = [7.9190673381649015, 0.0, -2.445459548430992]
renderView1.CameraPosition = [4.078419490872305, -13.76603875763453, -0.7816409864269787]
renderView1.CameraFocalPoint = [4.078419490872305, 0.0, -0.7816409864269787]
renderView1.CameraPosition = [1.980912571752786, -9.402389698541441, -0.0772543344838571]
renderView1.CameraFocalPoint = [1.980912571752786, 0.0, -0.0772543344838571]
layout1.SetSize(1546, 779)

with quiet():
    RenderAllViews() # type: ignore
    SaveScreenshot( # type: ignore
        filename=_IMG2,
        viewOrLayout=renderView1,
        location=16,
        ImageResolution=[1546, 779],
        FontScaling='Scale fonts proportionally',
        OverrideColorPalette='',
        StereoMode='No change',
        TransparentBackground=0,
        SaveInBackground=0,
        EmbedParaViewState=0,
        CompressionLevel='5',
        MetaData=['Application', 'ParaView'],
    )

# ------- final state -------
layout1.SetSize(1546, 779)
renderView1.CameraPosition = [1.980912571752786, -9.402389698541441, -0.0772543344838571]
renderView1.CameraFocalPoint = [1.980912571752786, 0.0, -0.0772543344838571]
renderView1.CameraViewUp = [0.0, 0.0, 1.0]
renderView1.CameraParallelScale = 29.003091452228485
# RenderAllViews()
