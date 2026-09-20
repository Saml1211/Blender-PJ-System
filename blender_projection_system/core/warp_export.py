"""Warp and corner-pin grid export toward media processors.

The grid describes, per projector, a lattice over the projector's
illuminated wall region with the image-space UV each lattice point
receives. Output space is the wall's ``(s, z)`` coordinates plus the world
point; input space is the projector image normalized to ``[0, 1]`` with
``(0, 0)`` at the image's top-left and ``v`` increasing downward.

These are design-phase geometric targets computed from the add-on's
projector and wall model — not a calibration substitute (ADR 0002).
Occlusion is deliberately not part of the mapping: occluders change what
gets illuminated, not where the processor's output geometry maps.

On a curved wall the four corner-pin points can never represent the
projected geometry — the mesh grid carries the truth; the corner pin is a
convenience for flat-wall workflows and is flagged incomplete whenever any
image corner misses the wall.

ADR 0001: Pure Python only, no bpy or mathutils.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .errors import ProjectionError
from .footprint import Footprint, footprint_corner_hits
from .surfaces import Surface

WARP_SCHEMA_VERSION = 1

DISCLAIMER = (
    "Design-phase geometric targets computed from the add-on's projector and "
    "wall model. Not a calibration substitute: on-site alignment, image "
    "mapping and blending remain calibration tasks. Occlusion is not modelled."
)

UV_CONVENTION = (
    "image uv normalized to [0, 1], (0, 0) at the image's top-left, "
    "v increasing downward"
)

_VERTEX_LAYOUT = (
    "vertices are row-major, top row first: [s_m, z_m, x_m, y_m, z_m]; "
    "s is the wall arc coordinate and may fall outside [0, arc_length_m] "
    "on wrapped walls (unwrapped for continuity)"
)


@dataclass(frozen=True)
class WarpVertex:
    """One lattice point: where it sits on the wall and what image uv hits it."""

    s: float
    z: float
    world: tuple[float, float, float]
    uv: tuple[float, float] | None
    valid: bool


@dataclass(frozen=True)
class WarpCorner:
    """One image corner that landed on the wall, with its normalized uv."""

    world: tuple[float, float, float]
    uv: tuple[float, float]


@dataclass(frozen=True)
class WarpGrid:
    """Per-projector warp lattice over the wall, plus its corner-pin points."""

    name: str
    columns: int
    rows: int
    vertices: tuple[WarpVertex, ...]
    corners: tuple[WarpCorner, ...]
    s_min: float
    s_max: float
    z_min: float
    z_max: float
    warnings: tuple[str, ...]


def build_warp_grid(fp: Footprint, resolution: int = 16) -> WarpGrid:
    """Sample a lattice over ``fp``'s illuminated extents and back-project it.

    Each lattice point maps through ``Surface.point_at`` to a world point and
    through ``Footprint.image_uv_of`` back into the projector's image. Points
    the image does not reach (outside ``[-0.5, 0.5]`` or behind the lens) are
    marked invalid and carry no uv.
    """
    if resolution < 2:
        raise ProjectionError(
            f"need at least 2 warp samples per axis, got {resolution}"
        )

    s_lo, s_hi = fp.s_min, fp.s_max
    z_lo, z_hi = fp.z_min, fp.z_max
    step_s = (s_hi - s_lo) / (resolution - 1)
    step_z = (z_hi - z_lo) / (resolution - 1)

    vertices: list[WarpVertex] = []
    for row in range(resolution):
        z = z_hi - row * step_z  # top row first
        for col in range(resolution):
            s = s_lo + col * step_s
            point = fp.wall.point_at(s, z)
            image_uv = fp.image_uv_of(point)
            uv: tuple[float, float] | None = None
            valid = False
            if image_uv is not None:
                u, v = image_uv
                # Lattice points may sit exactly on the image boundary (the
                # extents come from the footprint's own edge samples); allow
                # a float tolerance there, then clamp the emitted uv.
                limit = 0.5 + 1e-9
                if -limit <= u <= limit and -limit <= v <= limit:
                    uv = (
                        min(max(u + 0.5, 0.0), 1.0),
                        min(max(v + 0.5, 0.0), 1.0),
                    )
                    valid = True
            vertices.append(
                WarpVertex(
                    s=s,
                    z=z,
                    world=(float(point[0]), float(point[1]), float(point[2])),
                    uv=uv,
                    valid=valid,
                )
            )

    corners: list[WarpCorner] = []
    for (cu, cv), point in footprint_corner_hits(fp):
        corners.append(
            WarpCorner(
                world=(float(point[0]), float(point[1]), float(point[2])),
                uv=(cu + 0.5, cv + 0.5),
            )
        )

    warnings: list[str] = []
    if len(corners) < 4:
        warnings.append(
            f"{fp.name}: only {len(corners)} of 4 image corners land on "
            f"'{fp.wall.name}' - the corner pin is incomplete; use the mesh grid"
        )

    return WarpGrid(
        name=fp.name,
        columns=resolution,
        rows=resolution,
        vertices=tuple(vertices),
        corners=tuple(corners),
        s_min=s_lo,
        s_max=s_hi,
        z_min=z_lo,
        z_max=z_hi,
        warnings=tuple(warnings),
    )


def _round4(value: float) -> float:
    return round(value, 4)


def _round6(value: float) -> float:
    return round(value, 6)


def _grid_entry(grid: WarpGrid) -> dict[str, Any]:
    vertices: list[list[float]] = []
    uvs: list[list[float] | None] = []
    valids: list[bool] = []
    for v in grid.vertices:
        vertices.append(
            [
                _round4(v.s),
                _round4(v.z),
                _round4(v.world[0]),
                _round4(v.world[1]),
                _round4(v.world[2]),
            ]
        )
        uvs.append([_round6(v.uv[0]), _round6(v.uv[1])] if v.uv is not None else None)
        valids.append(v.valid)
    return {
        "name": grid.name,
        "columns": grid.columns,
        "rows": grid.rows,
        "vertices": vertices,
        "uv": uvs,
        "valid": valids,
        "corner_pin": {
            "corners": [
                [_round4(c.world[0]), _round4(c.world[1]), _round4(c.world[2])]
                for c in grid.corners
            ],
            "corner_uv": [[_round6(c.uv[0]), _round6(c.uv[1])] for c in grid.corners],
            "complete": len(grid.corners) == 4,
        },
        "warnings": list(grid.warnings),
    }


def export_warp_grids_to_json(
    wall: Surface,
    grids: Sequence[WarpGrid],
    generator: str,
    indent: int = 2,
) -> str:
    """Serialize per-projector warp grids as schema-versioned JSON."""
    payload: dict[str, Any] = {
        "schema_version": WARP_SCHEMA_VERSION,
        "generator": generator,
        "disclaimer": DISCLAIMER,
        "uv_convention": UV_CONVENTION,
        "units": {"space": "metres"},
        "wall": {
            "name": wall.name,
            "arc_length_m": _round4(wall.arc_length),
            "height_m": _round4(wall.height),
            "wraps_around": wall.wraps_around,
        },
        "layout": _VERTEX_LAYOUT,
        "projectors": [_grid_entry(grid) for grid in grids],
    }
    return json.dumps(payload, indent=indent)


def _obj_name(name: str) -> str:
    return name.replace(" ", "_")


def _valid_faces(grid: WarpGrid) -> list[tuple[int, int, int, int]]:
    """Grid cell indices whose four lattice corners are all valid, CCW from the front."""
    faces: list[tuple[int, int, int, int]] = []
    for row in range(grid.rows - 1):
        for col in range(grid.columns - 1):
            top_left = row * grid.columns + col
            top_right = top_left + 1
            bottom_left = top_left + grid.columns
            bottom_right = bottom_left + 1
            if all(
                grid.vertices[k].valid
                for k in (top_left, top_right, bottom_left, bottom_right)
            ):
                faces.append((top_left, bottom_left, bottom_right, top_right))
    return faces


def export_warp_meshes_to_obj(wall: Surface, grids: Sequence[WarpGrid]) -> str:
    """Serialize per-projector warp lattices as UV-mapped OBJ meshes.

    One ``o`` object per projector. Vertices are world-space metres on the
    wall; ``vt`` carries the normalized image uv remapped to the OBJ
    bottom-left, v-up convention. Faces are emitted only where all four
    lattice corners are valid; unused vertices are omitted.
    """
    lines = [
        "# Projection Planner warp mesh export",
        "# Design-phase geometric targets - not a calibration substitute.",
        "# Units: metres. vt is the normalized image uv in the OBJ",
        "# bottom-left, v-up convention (JSON export uses top-left, v down).",
        f"# {DISCLAIMER}",
        "",
    ]
    vertex_offset = 0
    for grid in grids:
        faces = _valid_faces(grid)
        used = sorted({k for face in faces for k in face})
        remap = {k: i + 1 for i, k in enumerate(used)}
        lines.append(f"o {_obj_name(grid.name)} warp")
        for k in used:
            v = grid.vertices[k]
            vertex_offset += 1
            lines.append(
                f"v {v.world[0]:.6f} {v.world[1]:.6f} {v.world[2]:.6f}"
            )
            u, vv = v.uv if v.uv is not None else (0.0, 0.0)
            lines.append(f"vt {u:.6f} {_round6(1.0 - vv):.6f}")
        for face in faces:
            a, b, c, d = (remap[k] for k in face)
            lines.append(f"f {a}/{a} {b}/{b} {c}/{c} {d}/{d}")
        lines.append("")
    return "\n".join(lines) + "\n"
