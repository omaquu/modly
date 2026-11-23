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
from .operations import _output_path, decimate_mesh
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
