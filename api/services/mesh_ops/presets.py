"""Intent-driven presets: one call chains the ops a common goal needs.

Each preset composes the registry's own op functions; intermediate files live
in a temporary directory, so the preset writes a single output mesh.
"""

import os
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Optional

from .geometry import merged_geometry, scene_meshes
from .operations import _mesh_libraries, _output_path, decimate_mesh
from .repair import auto_repair_mesh
from .transforms import DIMENSION_NAMES, UNIT_SCALE, _trimesh, apply_transforms
from .types import MeshOpContext, MeshOpExecutionError, MeshOpResult


def _find_splat_reconstructor() -> tuple[Path, Path]:
    """Find Python executable and extension dir with reconstruct_gaussian_to_glb."""
    user_modly = Path.home() / "Documents" / "Modly" / "extensions"
    for candidate_name in ("idol", "triposplat"):
        candidate = user_modly / candidate_name
        if candidate.is_dir():
            py = candidate / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            splat_py = candidate / "splat_mesh.py"
            if py.is_file() and splat_py.is_file():
                return py, candidate
    if user_modly.is_dir():
        for candidate in user_modly.iterdir():
            if candidate.is_dir():
                py = candidate / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
                splat_py = candidate / "splat_mesh.py"
                if py.is_file() and splat_py.is_file():
                    return py, candidate
    raise MeshOpExecutionError("No Gaussian Splat reconstruction extension found (requires idol or triposplat with venv).")


def _ensure_mesh_input(
    input_path: Path,
    scratch: Path,
    context: MeshOpContext,
) -> tuple[Path, Optional[dict[str, Any]]]:
    """If input is a Gaussian Splat (.ply or .splat), reconstruct it to a high-quality mesh first."""
    if input_path.suffix.lower() in (".ply", ".splat"):
        context.log("Input is a Gaussian Splat; reconstructing to mesh first…")
        context.progress(5, "Reconstructing splat to mesh…")
        splat_out = scratch / "splat_reconstructed.glb"
        py, ext_dir = _find_splat_reconstructor()
        cmd = [
            str(py),
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); from splat_mesh import reconstruct_gaussian_to_glb; reconstruct_gaussian_to_glb(sys.argv[2], sys.argv[3], mesh_detail=int(sys.argv[4]), mesh_smoothing=sys.argv[5], color_mode=sys.argv[6], texture=sys.argv[7])",
            str(ext_dir),
            str(input_path),
            str(splat_out),
            "10",       # mesh_detail 10 (Ultra)
            "Medium",   # mesh_smoothing
            "Refined",  # color_mode
            "Baked 4K", # texture
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            err = proc.stderr[-500:] if proc.stderr else (proc.stdout[-500:] if proc.stdout else "unknown error")
            raise MeshOpExecutionError(f"Failed to turn splat to mesh: {err}")
        if not splat_out.is_file():
            raise MeshOpExecutionError("Splat reconstruction did not produce an output mesh.")
        step = {
            "op": "splat_to_mesh",
            "summary": "Reconstructed high-fidelity mesh from Gaussian Splat (detail 10, Baked 4K).",
        }
        return splat_out, step
    return input_path, None


def splat_to_mesh(
    input_path: Path,
    params: Mapping[str, Any],
    context: MeshOpContext,
) -> MeshOpResult:
    """Turn a Gaussian Splat (.ply or .splat) into a high-fidelity textured 3D mesh."""
    output_path = _output_path(context, "splat-to-mesh")
    context.log("Preset: turn splat to mesh")
    context.progress(10, "Preparing reconstruction…")

    mesh_detail = int(params.get("mesh_detail", 10))
    mesh_smoothing = str(params.get("mesh_smoothing", "Medium"))
    color_mode = str(params.get("color_mode", "Refined"))
    texture = str(params.get("texture", "Baked 4K"))

    py, ext_dir = _find_splat_reconstructor()
    context.progress(25, "Reconstructing surface from Gaussians…")
    cmd = [
        str(py),
        "-c",
        "import sys; sys.path.insert(0, sys.argv[1]); from splat_mesh import reconstruct_gaussian_to_glb; reconstruct_gaussian_to_glb(sys.argv[2], sys.argv[3], mesh_detail=int(sys.argv[4]), mesh_smoothing=sys.argv[5], color_mode=sys.argv[6], texture=sys.argv[7])",
        str(ext_dir),
        str(input_path),
        str(output_path),
        str(mesh_detail),
        str(mesh_smoothing),
        str(color_mode),
        str(texture),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        err = proc.stderr[-500:] if proc.stderr else (proc.stdout[-500:] if proc.stdout else "unknown error")
        raise MeshOpExecutionError(f"Failed to turn splat to mesh: {err}")
    if not output_path.is_file():
        raise MeshOpExecutionError("Splat reconstruction did not produce an output mesh.")

    context.progress(95, "Measuring mesh…")
    face_count, dimensions = _measure(output_path)
    context.progress(100, "Done")
    return MeshOpResult(
        file_path=output_path,
        details={
            "steps": [
                {
                    "op": "splat_to_mesh",
                    "summary": f"Turned splat to mesh (detail {mesh_detail}, {mesh_smoothing} smoothing, {texture} texture, {face_count:,} faces).",
                }
            ],
            "face_count": face_count,
            "dimensions": dimensions,
        },
    )


def _stage(
    context: MeshOpContext,
    start: int,
    end: int,
    output_path: Optional[Path] = None,
) -> MeshOpContext:
    """A context for one step: its 0-100 progress maps onto start-end."""
    progress_cb = None
    if context.progress_cb is not None:
        def progress_cb(percent: int, label: str) -> None:
            context.progress(start + (end - start) * int(percent) // 100, label)

    return replace(context, output_path=output_path, progress_cb=progress_cb)


def _scratch(context: MeshOpContext) -> tempfile.TemporaryDirectory:
    """A scratch directory for intermediate files, under a temp_dir that may not exist yet."""
    Path(context.temp_dir).mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=str(context.temp_dir))


def _scale(size: float, unit: str, dimension: str) -> dict[str, Any]:
    return {"size": float(size), "unit": unit, "dimension": dimension}


def _arrange_steps(applied, requested: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    summaries = {
        "auto_orient": lambda _: "Laid flat on its widest side.",
        "recenter": lambda _: "Centred on the origin.",
        "drop_to_ground": lambda _: "Dropped onto the ground (lowest point at height 0).",
        "normalize_scale": lambda p: (
            f"Scaled the {DIMENSION_NAMES[p['dimension']]} to {p['size']:g} {p['unit']}."
        ),
    }
    return [
        {"op": step_id, **requested[step_id], "summary": summaries[step_id](requested[step_id])}
        for step_id in applied
    ]


def recompute_normals(input_path: Path, output_path: Path) -> Path:
    """Orient the faces outwards, then rewrite every vertex normal from them.

    UVs and materials are kept.

    Decimation moves vertices but keeps their old normals, and generated meshes
    often ship with none or with inverted ones; area-weighted normals derived
    from the faces are what game engines and web viewers shade with.
    """
    import numpy as np

    trimesh = _trimesh()
    loaded = trimesh.load(str(input_path))
    geometries = (
        loaded.geometry.values() if isinstance(loaded, trimesh.Scene) else [loaded]
    )
    for geometry in geometries:
        if not isinstance(geometry, trimesh.Trimesh) or not len(geometry.faces):
            continue
        # Make the winding consistent and outward first: normals derived from
        # inside-out faces would point inwards too.
        trimesh.repair.fix_normals(geometry, multibody=True)
        triangles = geometry.triangles
        face_normals = trimesh.util.unitize(
            np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        )
        geometry.vertex_normals = trimesh.geometry.mean_vertex_normals(
            len(geometry.vertices), geometry.faces, face_normals
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    loaded.export(str(output_path), include_normals=True)
    return output_path


def _measure(path: Path) -> tuple[int, list[float]]:
    trimesh = _trimesh()
    parts = scene_meshes(trimesh.load(str(path)), trimesh)
    if not parts:
        raise MeshOpExecutionError(f"preset: {path.name} contains no triangle mesh")
    world = merged_geometry(parts, trimesh, process=False)
    return int(len(world.faces)), [float(value) for value in world.extents]


def prepare_for_printing(
    input_path: Path,
    params: Mapping[str, Any],
    context: MeshOpContext,
) -> MeshOpResult:
    """Repair until watertight, lay flat, scale in millimetres, rest on the plate."""
    output_path = _output_path(context, "prepare-for-printing")
    with _scratch(context) as scratch_dir:
        scratch = Path(scratch_dir)
        context.log("Preset: prepare for printing")
        working_path, splat_step = _ensure_mesh_input(input_path, scratch, context)
        repaired = auto_repair_mesh(
            working_path,
            {"fill_holes": True},
            _stage(context, 0, 60, scratch / "repaired.glb"),
        )
        repair = dict(repaired.details)

        requested = {
            "auto_orient": {},
            "normalize_scale": _scale(params["size_mm"], "mm", params["dimension"]),
            "drop_to_ground": {},
        }
        arranged = apply_transforms(
            repaired.file_path or working_path,
            list(requested.items()),
            output_path,
            _stage(context, 60, 100),
        )

    face_count, dimensions = _measure(output_path)
    steps = [
        {
            "op": "repair_mesh",
            "summary": (
                f"Repaired in {repair['passes']} pass(es) ({', '.join(repair['steps'])})."
                if repair.get("repaired")
                else "Nothing to repair: the mesh was already closed and manifold."
            ),
            "repaired": bool(repair.get("repaired")),
            "passes": repair.get("passes", 0),
            "steps": list(repair.get("steps") or []),
        },
        *_arrange_steps(arranged.details["applied"], requested),
    ]
    if splat_step:
        steps.insert(0, splat_step)

    return MeshOpResult(
        file_path=output_path,
        details={
            "steps": steps,
            "watertight": bool(repair["after"]["is_watertight"]),
            "remaining_issues": list(repair.get("remaining_issues") or []),
            "face_count": face_count,
            "dimensions": dimensions,
            "dimensions_mm": [value / UNIT_SCALE["mm"] for value in dimensions],
            "textures_dropped": bool(repair.get("textures_dropped")),
        },
    )


def _decimate(input_path: Path, target_faces: int, scratch: Path, context: MeshOpContext):
    result = decimate_mesh(
        input_path,
        {"target_faces": int(target_faces)},
        _stage(context, 0, 60, scratch / "decimated.glb"),
    )
    faces = result.details.get("face_count")
    step = {
        "op": "decimate",
        "target_faces": int(target_faces),
        "face_count": faces,
        "summary": (
            f"Decimated to {faces:,} triangles (budget {int(target_faces):,})."
            if faces is not None
            else f"Decimated to a {int(target_faces):,}-triangle budget."
        ),
    }
    return result.file_path, step


NORMALS_STEP = {
    "op": "recompute_normals",
    "summary": "Recomputed smooth vertex normals from the faces.",
}


def _finish(output_path: Path, steps: list[dict[str, Any]]) -> MeshOpResult:
    face_count, dimensions = _measure(output_path)
    return MeshOpResult(
        file_path=output_path,
        details={"steps": steps, "face_count": face_count, "dimensions": dimensions},
    )


def prepare_for_game(
    input_path: Path,
    params: Mapping[str, Any],
    context: MeshOpContext,
) -> MeshOpResult:
    """Decimate to a poly budget, scale in metres, recompute the normals."""
    output_path = _output_path(context, "prepare-for-game")
    with _scratch(context) as scratch_dir:
        scratch = Path(scratch_dir)
        context.log("Preset: prepare for game")
        working_path, splat_step = _ensure_mesh_input(input_path, scratch, context)
        decimated, decimate_step = _decimate(working_path, params["target_faces"], scratch, context)

        requested = {"normalize_scale": _scale(params["size_m"], "m", params["dimension"])}
        scaled = apply_transforms(
            decimated, list(requested.items()), scratch / "scaled.glb", _stage(context, 60, 85)
        )
        context.progress(85, "Recomputing normals…")
        recompute_normals(scaled.file_path, output_path)
    context.progress(100, "Done")
    steps = [decimate_step, *_arrange_steps(scaled.details["applied"], requested), NORMALS_STEP]
    if splat_step:
        steps.insert(0, splat_step)
    return _finish(output_path, steps)


def prepare_for_web(
    input_path: Path,
    params: Mapping[str, Any],
    context: MeshOpContext,
) -> MeshOpResult:
    """Decimate aggressively for a light download, then recompute the normals."""
    output_path = _output_path(context, "prepare-for-web")
    with _scratch(context) as scratch_dir:
        scratch = Path(scratch_dir)
        context.log("Preset: prepare for web")
        working_path, splat_step = _ensure_mesh_input(input_path, scratch, context)
        decimated, decimate_step = _decimate(
            working_path, params["target_faces"], scratch, context
        )
        context.progress(80, "Recomputing normals…")
        recompute_normals(decimated, output_path)
    context.progress(100, "Done")
    steps = [decimate_step, NORMALS_STEP]
    if splat_step:
        steps.insert(0, splat_step)
    return _finish(output_path, steps)


def tune_splat(
    input_path: Path,
    params: Mapping[str, Any],
    context: MeshOpContext,
) -> MeshOpResult:
    """Downsample and prune a Gaussian Splat (.ply or .splat) to reduce VRAM and file size."""
    if input_path.suffix.lower() not in (".ply", ".splat"):
        raise MeshOpExecutionError(f"tune_splat requires a Gaussian Splat (.ply or .splat), got {input_path.name}")

    output_path = context.workspace_dir / "Workflows" / f"splat-tuned-{int(time.time() * 1000)}.ply"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if context.output_path is not None:
        output_path = Path(context.output_path)

    context.log("Preset: tune splat")
    context.progress(10, "Loading Gaussian Splat…")

    target_str = str(params.get("target_gaussians", "262k"))
    target_map = {
        "1M": 1048576,
        "500k": 524288,
        "262k": 262144,
        "131k": 131072,
        "65k": 65536,
    }
    target_count = target_map.get(target_str, 262144)
    min_opacity = float(params.get("min_opacity", 0.05))

    py, ext_dir = _find_splat_reconstructor()
    context.progress(25, f"Pruning floaters and downsampling to {target_str}…")

    cmd = [
        str(py),
        "-c",
        """
import sys, time, os, hashlib, json
from pathlib import Path
import numpy as np
from plyfile import PlyData, PlyElement

input_path = sys.argv[1]
output_path = sys.argv[2]
target_count = int(sys.argv[3])
min_opacity = float(sys.argv[4])
workspace_dir = sys.argv[5]

t0 = time.time()
ply = PlyData.read(input_path)
data = ply['vertex'].data
orig_count = len(data)

# 1. Opacity threshold
logit_thresh = np.log(min_opacity / (1.0 - min_opacity))
mask = data['opacity'] >= logit_thresh
filtered = data[mask]

# 2. Score and pick top K
if len(filtered) > target_count:
    scores = filtered['opacity'] + (filtered['scale_0'] + filtered['scale_1'] + filtered['scale_2']) * 0.333
    top_indices = np.argpartition(-scores, target_count)[:target_count]
    final_data = filtered[top_indices]
else:
    final_data = filtered

el = PlyElement.describe(final_data, 'vertex')
PlyData([el], text=False).write(output_path)
final_count = len(final_data)

# Auto-generate thumbnail for the tuned splat
try:
    sys.path.insert(0, sys.argv[6])
    from splat_mesh import load_splat_file
    from splatforge.render.splat import render_splats
    from splatforge.render.cameras import look_at_w2c
    from PIL import Image
    import torch

    g = load_splat_file(output_path, device='cuda')
    xyz = g['xyz'].cpu().numpy()
    lo, hi = xyz.min(0), xyz.max(0)
    center = (lo + hi) * 0.5
    diag = float(np.linalg.norm(hi - lo))
    eye = center + np.array([0, -diag * 1.5, diag * 0.2], dtype=np.float32)
    R, t = look_at_w2c(eye, center, up_world=(0, 0, 1))
    cam = {'R': torch.as_tensor(R, device='cuda'), 't': torch.as_tensor(t, device='cuda'), 'fx': 256.0, 'fy': 256.0, 'cx': 128.0, 'cy': 128.0, 'res': 256}
    rgb, alpha = render_splats(g['xyz'], g['opacity'], g['scale'], g['quat'], g['rgb'], cam)
    rgb_np = (rgb.cpu().numpy() * 255).astype(np.uint8)
    alpha_np = (alpha.cpu().numpy() * 255).astype(np.uint8)[:, :, None]
    img = Image.fromarray(np.concatenate([rgb_np, alpha_np], axis=2), mode='RGBA')
    canvas = Image.new('RGBA', (256, 256), (24, 24, 27, 255))
    canvas.paste(img, (0, 0), img)

    app_data = os.environ.get('APPDATA')
    if app_data:
        thumbs_dir = Path(app_data) / 'Modly' / 'thumbnails'
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        out_p = Path(output_path)
        rel_path = f"Workflows/{out_p.name}"
        key = hashlib.sha256(f"{os.path.abspath(workspace_dir)}\\n{rel_path}".encode('utf-8')).hexdigest()[:32]
        st = out_p.stat()
        alphabet = '0123456789abcdefghijklmnopqrstuvwxyz'
        def b36(n):
            if n == 0: return '0'
            r = []
            while n: r.append(alphabet[n%36]); n//=36
            return ''.join(reversed(r))
        v_str = f"{b36(int(st.st_mtime*1000))}-{b36(st.st_size)}-r1"
        canvas.save(str(thumbs_dir / f"{key}.{v_str}.webp"), 'WEBP', quality=90)
        (thumbs_dir / f"{key}.json").write_text(json.dumps({'workspaceDir': workspace_dir, 'workspacePath': rel_path}), encoding='utf-8')
except Exception as e:
    pass

print(f"DONE:{orig_count}:{final_count}")
""",
        str(input_path),
        str(output_path),
        str(target_count),
        str(min_opacity),
        str(context.workspace_dir),
        str(ext_dir),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        err = proc.stderr[-500:] if proc.stderr else proc.stdout[-500:]
        raise MeshOpExecutionError(f"Failed to tune splat: {err}")

    orig_c = 0
    final_c = 0
    for line in proc.stdout.splitlines():
        if line.startswith("DONE:"):
            parts = line.split(":")
            orig_c = int(parts[1])
            final_c = int(parts[2])

    reduction = ((orig_c - final_c) / max(orig_c, 1)) * 100
    context.progress(100, "Done")

    return MeshOpResult(
        file_path=output_path,
        details={
            "steps": [
                {
                    "op": "tune_splat",
                    "summary": f"Tuned splat from {orig_c:,} to {final_c:,} Gaussians ({reduction:.0f}% reduction, budget {target_str}).",
                }
            ],
            "original_count": orig_c,
            "final_count": final_c,
            "reduction_percent": round(reduction, 1),
        },
    )


def restore_texture(
    input_path: Path,
    params: Mapping[str, Any],
    context: MeshOpContext,
) -> MeshOpResult:
    """Transfer or re-project textures from the original model onto an untextured or repaired mesh."""
    output_path = _output_path(context, "restore-texture")
    context.log("Preset: restore texture")
    context.progress(10, "Locating source textured mesh…")

    source_path_str = str(params.get("source_mesh", "")).strip()
    source_path: Optional[Path] = None
    if source_path_str:
        candidate = Path(source_path_str)
        if candidate.is_file():
            source_path = candidate
        elif (context.workspace_dir / source_path_str).is_file():
            source_path = context.workspace_dir / source_path_str

    # Auto-detect source mesh if not provided:
    # 1. Strip suffix like _repair_mesh_... or _decimate_... to find original
    if not source_path:
        stem = input_path.stem
        for tag in ("_repair_mesh_", "_decimate_", "_prepare_", "_smooth_"):
            if tag in stem:
                base_stem = stem.split(tag)[0]
                parent_dir = input_path.parent
                candidates = sorted(list(parent_dir.glob(f"{base_stem}*.glb")), key=lambda p: p.stat().st_mtime, reverse=True)
                for c in candidates:
                    if c != input_path and "_repair_mesh_" not in c.name:
                        source_path = c
                        break
                if source_path:
                    break

    # 2. Check parent folder for matching base ID
    if not source_path and "_" in input_path.stem:
        parts = input_path.stem.split("_")
        prefix = f"{parts[0]}_{parts[1]}"
        for c in sorted(list(input_path.parent.glob(f"{prefix}*.glb")), key=lambda p: p.stat().st_mtime, reverse=True):
            if c != input_path and "_repair_mesh_" not in c.name:
                source_path = c
                break

    if not source_path or not source_path.is_file():
        raise MeshOpExecutionError("No source textured model found. Please specify the path in `source_mesh`.")

    context.log(f"Restoring textures from: {source_path.name}")
    context.progress(30, f"Loading geometry from {source_path.name}…")

    pymeshlab, trimesh = _mesh_libraries("restore_texture")
    from scipy.spatial import cKDTree
    import numpy as np

    orig_scene = trimesh.load(str(source_path), process=False)
    target_scene = trimesh.load(str(input_path), process=False)

    orig_parts = scene_meshes(orig_scene, trimesh)
    target_parts = scene_meshes(target_scene, trimesh)

    if not orig_parts or not target_parts:
        raise MeshOpExecutionError("Could not load meshes for texture restoration.")

    orig_geom, _ = orig_parts[0]
    target_geom, _ = target_parts[0]

    has_tex = hasattr(orig_geom, "visual") and hasattr(orig_geom.visual, "material") and hasattr(orig_geom.visual, "uv") and orig_geom.visual.uv is not None
    has_vc = hasattr(orig_geom, "visual") and hasattr(orig_geom.visual, "vertex_colors") and orig_geom.visual.vertex_colors is not None

    if not has_tex and not has_vc:
        raise MeshOpExecutionError(f"Source model {source_path.name} has neither textures nor vertex colors.")

    context.progress(60, "Transferring UV mapping and textures…")
    orig_verts = np.asarray(orig_geom.vertices, dtype=np.float64)
    target_verts = np.asarray(target_geom.vertices, dtype=np.float64)

    kdtree = cKDTree(orig_verts)
    _, idxs = kdtree.query(target_verts)

    if has_tex:
        orig_uvs = np.asarray(orig_geom.visual.uv, dtype=np.float32)
        new_uvs = orig_uvs[idxs]
        visual = trimesh.visual.TextureVisuals(uv=new_uvs, material=orig_geom.visual.material)
    else:
        orig_colors = np.asarray(orig_geom.visual.vertex_colors)
        new_colors = orig_colors[idxs]
        visual = trimesh.visual.ColorVisuals(mesh=None, vertex_colors=new_colors)

    restored = trimesh.Trimesh(
        vertices=target_geom.vertices,
        faces=target_geom.faces,
        visual=visual,
        process=False
    )

    context.progress(85, "Saving textured mesh…")
    restored.export(str(output_path))

    context.progress(95, "Measuring mesh…")
    face_count, dimensions = _measure(output_path)
    context.progress(100, "Done")

    return MeshOpResult(
        file_path=output_path,
        details={
            "steps": [
                {
                    "op": "restore_texture",
                    "summary": f"Restored textures from {source_path.name} onto {input_path.name} ({face_count:,} faces).",
                }
            ],
            "source_mesh": str(source_path),
            "face_count": face_count,
            "dimensions": dimensions,
        },
    )
