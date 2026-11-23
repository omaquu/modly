"""Built-in mesh operation definitions."""

from .agent_format import format_fixes, format_inspection, format_preset, format_repair
from .inspection import inspect_mesh, suggest_fixes
from .operations import decimate_mesh, repair_mesh, smooth_mesh
from .presets import prepare_for_game, prepare_for_printing, prepare_for_web, restore_texture, splat_to_mesh, tune_splat
from .repair import auto_repair_mesh
from .transforms import auto_orient, drop_to_ground, normalize_scale, recenter, set_real_scale
from .types import AgentTool, MeshOp


REPAIR_PARAMS = (
    {
        "id": "remove_duplicates",
        "label": "Remove Duplicates",
        "type": "boolean",
        "default": True,
        "tooltip": "Remove duplicate vertices and faces.",
    },
    {
        "id": "remove_degenerate",
        "label": "Remove Degenerate Faces",
        "type": "boolean",
        "default": True,
        "tooltip": "Remove zero-area faces and collapsed edges.",
    },
    {
        "id": "fix_non_manifold",
        "label": "Fix Non-Manifold",
        "type": "boolean",
        "default": True,
        "tooltip": "Detach faces causing non-manifold edges.",
    },
    {
        "id": "fill_holes",
        "label": "Fill Holes",
        "type": "boolean",
        "default": True,
        "tooltip": (
            "Fill simple boundary holes. Structural holes from AI generation "
            "may not be fillable in post-processing."
        ),
    },
    {
        "id": "max_hole_size",
        "label": "Max Hole Size",
        "type": "int",
        "default": 2000,
        "min": 10,
        "max": 10000,
        "tooltip": (
            "Maximum number of boundary edges of a hole to be filled. "
            "Increase if large holes remain open."
        ),
    },
)

DECIMATE_PARAMS = (
    {
        "id": "target_faces",
        "label": "Target Triangles",
        "type": "int",
        "default": 10000,
        "min": 100,
        "max": 1000000,
        "tooltip": "Target number of triangles after simplification.",
    },
)

SMOOTH_PARAMS = (
    {
        "id": "iterations",
        "label": "Iterations",
        "type": "int",
        "default": 5,
        "min": 1,
        "max": 50,
        "tooltip": (
            "Number of smoothing passes. More iterations = smoother result "
            "but may lose fine details."
        ),
    },
    {
        "id": "lambda_",
        "label": "Smoothing Strength",
        "type": "float",
        "default": 0.5,
        "min": 0.1,
        "max": 1.0,
        "step": 0.05,
        "tooltip": (
            "Controls how far each vertex moves toward its neighbours per "
            "iteration. Lower = more conservative."
        ),
    },
    {
        "id": "mode",
        "label": "Mode",
        "type": "select",
        "default": "taubin",
        "options": [
            {"value": "taubin", "label": "Taubin (volume-preserving)"},
            {"value": "laplacian", "label": "Laplacian (stronger, may shrink)"},
        ],
        "tooltip": (
            "Taubin alternates positive/negative steps to prevent mesh "
            "shrinkage. Laplacian is simpler but tends to shrink the mesh over "
            "many iterations."
        ),
    },
)


INSPECT_PARAMS = (
    {
        "id": "check_self_intersections",
        "label": "Check Self-Intersections",
        "type": "boolean",
        "default": True,
        "tooltip": (
            "Detect intersecting faces. The slowest check on very dense meshes."
        ),
    },
)


NORMALIZE_SCALE_PARAMS = (
    {
        "id": "size",
        "label": "Size",
        "type": "float",
        "default": 1.0,
        "min": 0.001,
        "max": 100000.0,
        "step": 0.1,
        "tooltip": "Target size of the measured dimension, in the chosen unit.",
    },
    {
        "id": "unit",
        "label": "Unit",
        "type": "select",
        "default": "units",
        "options": [
            {"value": "units", "label": "Model units (no real size)"},
            {"value": "m", "label": "Metres"},
            {"value": "cm", "label": "Centimetres"},
            {"value": "mm", "label": "Millimetres"},
        ],
        "tooltip": (
            "glTF stores metres: 20 cm is written as 0.2 units. A real unit also "
            "marks the mesh as real-sized, for the Print page and exports."
        ),
    },
    {
        "id": "dimension",
        "label": "Dimension",
        "type": "select",
        "default": "longest",
        "options": [
            {"value": "longest", "label": "Longest side"},
            {"value": "x", "label": "Width (X)"},
            {"value": "y", "label": "Height (Y)"},
            {"value": "z", "label": "Depth (Z)"},
        ],
        "tooltip": "Which bounding-box dimension is set to the target size.",
    },
)


SET_REAL_SCALE_PARAMS = (
    {
        "id": "size",
        "label": "Real Size",
        "type": "float",
        "default": 10.0,
        "min": 0.001,
        "max": 100000.0,
        "step": 0.1,
        "tooltip": "How big the measured dimension really is, in the chosen unit.",
    },
    {
        "id": "unit",
        "label": "Unit",
        "type": "select",
        "default": "cm",
        "options": [
            {"value": "mm", "label": "Millimetres"},
            {"value": "cm", "label": "Centimetres"},
            {"value": "m", "label": "Metres"},
        ],
        "tooltip": "Unit of the real size.",
    },
    {
        "id": "dimension",
        "label": "Dimension",
        "type": "select",
        "default": "longest",
        "options": [
            {"value": "longest", "label": "Longest side"},
            {"value": "x", "label": "Width (X)"},
            {"value": "y", "label": "Height (Y)"},
            {"value": "z", "label": "Depth (Z)"},
        ],
        "tooltip": "Which bounding-box dimension has the real size.",
    },
)


REPAIR_MESH_PARAMS = (
    {
        "id": "fill_holes",
        "label": "Fill Holes",
        "type": "boolean",
        "default": True,
        "tooltip": (
            "Close every hole, whatever its size. Turn off for meshes that are "
            "meant to stay open, such as terrain: only flipped faces are then "
            "fixed, since removing bad faces would open new holes."
        ),
    },
    {
        "id": "preserve_textures",
        "label": "Preserve Textures",
        "type": "boolean",
        "default": True,
        "tooltip": "Preserve and transfer original UVs and textures onto the repaired mesh.",
    },
)

RESTORE_TEXTURE_PARAMS = (
    {
        "id": "source_mesh",
        "label": "Source Mesh (Textured)",
        "type": "string",
        "default": "",
        "tooltip": "Path to original textured model (.glb). Leave blank to auto-detect pre-repair mesh in the same folder.",
    },
)


DIMENSION_PARAM = {
    "id": "dimension",
    "label": "Dimension",
    "type": "select",
    "default": "longest",
    "options": [
        {"value": "longest", "label": "Longest side"},
        {"value": "x", "label": "Width (X)"},
        {"value": "y", "label": "Height (Y)"},
        {"value": "z", "label": "Depth (Z)"},
    ],
    "tooltip": "Which bounding-box dimension is set to the target size.",
}


PREPARE_FOR_PRINTING_PARAMS = (
    {
        "id": "size_mm",
        "label": "Size (mm)",
        "type": "float",
        "default": 100.0,
        "min": 1.0,
        "max": 10000.0,
        "step": 1.0,
        "tooltip": "Printed size of the chosen dimension, in millimetres.",
    },
    DIMENSION_PARAM,
)

PREPARE_FOR_GAME_PARAMS = (
    {
        "id": "target_faces",
        "label": "Poly Budget",
        "type": "int",
        "default": 20000,
        "min": 100,
        "max": 1000000,
        "tooltip": "Maximum number of triangles the game asset may keep.",
    },
    {
        "id": "size_m",
        "label": "Size (m)",
        "type": "float",
        "default": 1.0,
        "min": 0.01,
        "max": 1000.0,
        "step": 0.1,
        "tooltip": "In-game size of the chosen dimension, in metres.",
    },
    DIMENSION_PARAM,
)

PREPARE_FOR_WEB_PARAMS = (
    {
        "id": "target_faces",
        "label": "Poly Budget",
        "type": "int",
        "default": 5000,
        "min": 100,
        "max": 200000,
        "tooltip": "Maximum number of triangles: fewer means a lighter download.",
    },
)

SPLAT_TO_MESH_PARAMS = (
    {
        "id": "mesh_detail",
        "label": "Mesh Detail",
        "type": "select",
        "default": 10,
        "options": [
            {"value": 10, "label": "Ultra (10 - best quality)"},
            {"value": 9, "label": "High (9)"},
            {"value": 8, "label": "Medium (8)"},
            {"value": 7, "label": "Low (7)"},
        ],
        "tooltip": "Voxel grid resolution for surface extraction. 10 gives maximum geometric fidelity.",
    },
    {
        "id": "texture",
        "label": "Texture",
        "type": "select",
        "default": "Baked 4K",
        "options": [
            {"value": "Baked 4K", "label": "Baked 4K (4096×4096)"},
            {"value": "Baked 2K", "label": "Baked 2K (2048×2048)"},
            {"value": "Baked 1K", "label": "Baked 1K (1024×1024)"},
            {"value": "Auto", "label": "Auto"},
            {"value": "Vertex colors", "label": "Vertex Colors (no texture file)"},
        ],
        "tooltip": "Baked UV texture resolution. Baked 4K prevents pixelation.",
    },
    {
        "id": "mesh_smoothing",
        "label": "Mesh Smoothing",
        "type": "select",
        "default": "Medium",
        "options": [
            {"value": "None", "label": "None"},
            {"value": "Light", "label": "Light"},
            {"value": "Medium", "label": "Medium"},
            {"value": "Strong", "label": "Strong"},
        ],
        "tooltip": "Taubin smoothing strength to remove volume extraction noise while preserving volume.",
    },
    {
        "id": "color_mode",
        "label": "Color Mode",
        "type": "select",
        "default": "Refined",
        "options": [
            {"value": "Refined", "label": "Refined (+render supervision)"},
            {"value": "Vivid", "label": "Vivid (boosted saturation)"},
            {"value": "Direct", "label": "Direct"},
        ],
        "tooltip": "Refined optimizes colors by rendering the mesh against original Gaussians.",
    },
)

TUNE_SPLAT_PARAMS = (
    {
        "id": "target_gaussians",
        "label": "Target Gaussians",
        "type": "select",
        "default": "262k",
        "options": [
            {"value": "500k", "label": "500k (High fidelity)"},
            {"value": "262k", "label": "262k (Balanced - recommended)"},
            {"value": "131k", "label": "131k (Light)"},
            {"value": "65k", "label": "65k (Ultra light / fast)"},
        ],
        "tooltip": "Target number of Gaussians to keep. Downsamples large 1M+ models to reduce VRAM and file size.",
    },
    {
        "id": "min_opacity",
        "label": "Min Opacity",
        "type": "float",
        "default": 0.05,
        "min": 0.01,
        "max": 0.5,
        "step": 0.01,
        "tooltip": "Removes low-opacity floating noise before downsampling.",
    },
)

DIMENSION_HINT = "Which side gets the size: longest, x (width), y (height) or z (depth)."


BUILTIN_MESH_OPS = (
    MeshOp(
        id="repair",
        label="Repair Mesh",
        params_schema=REPAIR_PARAMS,
        fn=repair_mesh,
        category="repair",
    ),
    MeshOp(
        id="repair_mesh",
        label="Repair Mesh (auto)",
        params_schema=REPAIR_MESH_PARAMS,
        fn=auto_repair_mesh,
        category="repair",
        agent=AgentTool(
            description=(
                "Repair a mesh automatically: fill holes, fix non-manifold edges, degenerate "
                "faces and flipped normals, re-checking until it is closed and manifold. "
                "Writes a new mesh without textures; does nothing if the mesh is already sound."
            ),
            params={
                "fill_holes": (
                    "Close holes. Set false only for meshes meant to stay open, "
                    "like terrain: then only flipped faces are fixed."
                ),
            },
            format_result=format_repair,
        ),
    ),
    MeshOp(
        id="decimate",
        label="Optimize Mesh",
        params_schema=DECIMATE_PARAMS,
        fn=decimate_mesh,
        category="optimization",
        agent=AgentTool(
            description="Reduce the polygon count of a mesh using quadric edge collapse.",
            params={"target_faces": "Target number of triangles after decimation."},
            required=("target_faces",),
        ),
    ),
    MeshOp(
        id="smooth",
        label="Smooth Mesh",
        params_schema=SMOOTH_PARAMS,
        fn=smooth_mesh,
        category="optimization",
        agent=AgentTool(
            description="Smooth the surface of a mesh (volume-preserving Taubin smoothing).",
            params={"iterations": "Number of smoothing passes. More = smoother but loses detail."},
            required=("iterations",),
        ),
    ),
    MeshOp(
        id="inspect_mesh",
        label="Inspect Mesh",
        params_schema=INSPECT_PARAMS,
        fn=inspect_mesh,
        category="analysis",
        agent=AgentTool(
            description=(
                "Diagnose a mesh without modifying it: watertight, manifold, holes, "
                "self-intersections, disconnected parts, dimensions, volume, UVs/normals, "
                "and whether it is 3D-printable."
            ),
            format_result=format_inspection,
        ),
    ),
    MeshOp(
        id="suggest_fixes",
        label="Suggest Fixes",
        params_schema=INSPECT_PARAMS,
        fn=suggest_fixes,
        category="analysis",
        agent=AgentTool(
            description=(
                "Inspect a mesh and list the operations (with parameters) that would fix "
                "its problems. Does not modify the mesh."
            ),
            format_result=format_fixes,
        ),
    ),
    MeshOp(
        id="recenter",
        label="Recenter",
        params_schema=(),
        fn=recenter,
        category="transform",
    ),
    MeshOp(
        id="drop_to_ground",
        label="Drop to Ground",
        params_schema=(),
        fn=drop_to_ground,
        category="transform",
    ),
    MeshOp(
        id="auto_orient",
        label="Lay Flat",
        params_schema=(),
        fn=auto_orient,
        category="transform",
    ),
    MeshOp(
        id="normalize_scale",
        label="Normalize Scale",
        params_schema=NORMALIZE_SCALE_PARAMS,
        fn=normalize_scale,
        category="transform",
    ),
    MeshOp(
        id="set_real_scale",
        label="Set Real Size",
        params_schema=SET_REAL_SCALE_PARAMS,
        fn=set_real_scale,
        category="transform",
        agent=AgentTool(
            description=(
                "Declare how big the object really is (\"this is 30 cm tall\"): rescales the "
                "mesh to that size and marks it calibrated, so the Print page and STL "
                "exports use its real size."
            ),
            params={
                "size": "Real size of `dimension`, in `unit`.",
                "unit": "mm, cm or m.",
                "dimension": DIMENSION_HINT,
            },
            required=("size", "unit"),
            format_result=format_preset,
        ),
    ),
    MeshOp(
        id="prepare_for_printing",
        label="Prepare for 3D Printing",
        params_schema=PREPARE_FOR_PRINTING_PARAMS,
        fn=prepare_for_printing,
        category="presets",
        agent=AgentTool(
            description=(
                "Make a mesh ready for 3D printing in one call: repair it until it is "
                "watertight and manifold, lay it flat, scale it in millimetres and rest it "
                "on the build plate. Writes a new mesh without textures."
            ),
            params={
                "size_mm": "Printed size of `dimension`, in millimetres.",
                "dimension": DIMENSION_HINT,
            },
            format_result=format_preset,
        ),
    ),
    MeshOp(
        id="prepare_for_game",
        label="Prepare for Game",
        params_schema=PREPARE_FOR_GAME_PARAMS,
        fn=prepare_for_game,
        category="presets",
        agent=AgentTool(
            description=(
                "Make a mesh ready for a game engine in one call: decimate it to a "
                "triangle budget, scale it in metres and recompute its normals."
            ),
            params={
                "target_faces": "Triangle budget of the game asset.",
                "size_m": "In-game size of `dimension`, in metres.",
                "dimension": DIMENSION_HINT,
            },
            format_result=format_preset,
        ),
    ),
    MeshOp(
        id="prepare_for_web",
        label="Prepare for Web",
        params_schema=PREPARE_FOR_WEB_PARAMS,
        fn=prepare_for_web,
        category="presets",
        agent=AgentTool(
            description=(
                "Make a mesh light enough for the web in one call: decimate it "
                "aggressively and recompute its normals. Keeps its textures and size."
            ),
            params={"target_faces": "Triangle budget; lower means a lighter download."},
            format_result=format_preset,
        ),
    ),
    MeshOp(
        id="splat_to_mesh",
        label="Turn Splat to Mesh",
        params_schema=SPLAT_TO_MESH_PARAMS,
        fn=splat_to_mesh,
        category="presets",
        agent=AgentTool(
            description=(
                "Convert a Gaussian Splat (.ply or .splat) into a high-detail textured 3D mesh (GLB)."
            ),
            params={
                "mesh_detail": "Reconstruction resolution (10 for Ultra / best quality).",
                "texture": "Texture resolution (Baked 4K, Baked 2K, Baked 1K, Auto, Vertex colors).",
                "mesh_smoothing": "Taubin smoothing: None, Light, Medium, Strong.",
                "color_mode": "Refined, Vivid, Direct.",
            },
            format_result=format_preset,
        ),
    ),
    MeshOp(
        id="tune_splat",
        label="Tune Splat (Optimize)",
        params_schema=TUNE_SPLAT_PARAMS,
        fn=tune_splat,
        category="presets",
        agent=AgentTool(
            description=(
                "Downsample and prune a Gaussian Splat (.ply or .splat) to reduce file size and VRAM."
            ),
            params={
                "target_gaussians": "Target gaussian count (500k, 262k, 131k, 65k).",
                "min_opacity": "Minimum opacity threshold to prune floaters.",
            },
            format_result=format_preset,
        ),
    ),
    MeshOp(
        id="restore_texture",
        label="Restore Texture (Transfer)",
        params_schema=RESTORE_TEXTURE_PARAMS,
        fn=restore_texture,
        category="presets",
        agent=AgentTool(
            description=(
                "Restore textures from the original model onto a repaired or untextured mesh via spatial UV transfer."
            ),
            params={
                "source_mesh": "Optional path to the source textured model (.glb). Auto-detected if omitted.",
            },
            format_result=format_preset,
        ),
    ),
)
