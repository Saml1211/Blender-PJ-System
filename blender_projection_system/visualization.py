"""Scene construction and analysis visualisation.

Every mesh here is generated from :mod:`blender_projection_system.core` output
and lives in a dedicated collection. v0.1 drove a Geometry Nodes cone through
drivers, which silently produced nothing when a socket name changed between
Blender versions; building explicit meshes is boring, deterministic and easy
to verify.

Nothing in this module registers Blender classes - it is called by the
operators in :mod:`blender_projection_system.operators`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import bpy
from mathutils import Matrix, Vector

from .core.array import ProjectorPlacement
from .core.errors import ProjectionError
from .core.footprint import Footprint, footprint_corners_world
from .core.surfaces import CylindricalWall
from .core.vectors import length as vec_length
from .core.vectors import sub as sub_vec

COLLECTION_TARGETS = "PJ Targets"
COLLECTION_PROJECTORS = "PJ Projectors"
COLLECTION_ANALYSIS = "PJ Analysis"
OWNER_ID = "projection_planner"
OWNER_KEY = "pj_owner"
ROLE_KEY = "pj_collection_role"
MATERIAL_ROLE_KEY = "pj_material_role"

#: Footprint outlines are pushed this far off the wall so they do not z-fight.
SURFACE_OFFSET = 0.01

#: Safety ceiling for any one wall-hugging ribbon. Very large but otherwise
#: valid radii must not turn one click into millions of Blender mesh elements.
MAX_BAND_SEGMENTS = 4096

#: Distinct colours cycled across projectors in the analysis overlay.
PALETTE: tuple[tuple[float, float, float, float], ...] = (
    (0.95, 0.26, 0.21, 1.0),
    (0.26, 0.65, 0.96, 1.0),
    (0.30, 0.85, 0.39, 1.0),
    (0.99, 0.75, 0.18, 1.0),
    (0.72, 0.40, 0.93, 1.0),
    (0.15, 0.85, 0.83, 1.0),
)


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


def get_collection(context, name: str) -> bpy.types.Collection:
    """Fetch or create an add-on-owned top-level collection.

    A user collection with the preferred display name is never adopted.
    """
    coll = next(
        (
            candidate
            for candidate in context.scene.collection.children
            if candidate.get(OWNER_KEY) == OWNER_ID and candidate.get(ROLE_KEY) == name
        ),
        None,
    )
    if coll is None:
        preferred = name if bpy.data.collections.get(name) is None else f"{name} (Projection Planner)"
        coll = bpy.data.collections.new(preferred)
        coll[OWNER_KEY] = OWNER_ID
        coll[ROLE_KEY] = name
    if coll.name not in context.scene.collection.children:
        context.scene.collection.children.link(coll)
    return coll


def link_only_to(obj: bpy.types.Object, coll: bpy.types.Collection) -> None:
    """Make ``coll`` the object's sole collection."""
    for existing in list(obj.users_collection):
        if existing is not coll:
            existing.objects.unlink(obj)
    if obj.name not in coll.objects:
        coll.objects.link(obj)


def clear_collection(context, name: str) -> int:
    """Delete owned objects from this scene's owned collection only."""
    coll = next(
        (
            candidate
            for candidate in context.scene.collection.children
            if candidate.get(OWNER_KEY) == OWNER_ID and candidate.get(ROLE_KEY) == name
        ),
        None,
    )
    if coll is None:
        return 0
    removed = 0
    for obj in list(coll.objects):
        if obj.get(OWNER_KEY) != OWNER_ID:
            continue
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        removed += 1
        if isinstance(data, bpy.types.Mesh) and data.users == 0:
            bpy.data.meshes.remove(data)
    return removed


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------


def _owned_material(
    name: str,
    role: str,
    colour: tuple[float, float, float, float],
) -> bpy.types.Material:
    """Fetch or create a material without adopting a same-named user asset."""
    mat = next(
        (
            candidate
            for candidate in bpy.data.materials
            if candidate.get(OWNER_KEY) == OWNER_ID
            and candidate.get(MATERIAL_ROLE_KEY) == role
        ),
        None,
    )
    if mat is None:
        preferred = name if bpy.data.materials.get(name) is None else f"{name} (Projection Planner)"
        mat = bpy.data.materials.new(preferred)
        mat[OWNER_KEY] = OWNER_ID
        mat[MATERIAL_ROLE_KEY] = role
        mat.use_nodes = False
    mat.diffuse_color = colour
    mat.roughness = 1.0
    return mat


def get_overlay_material(index: int) -> bpy.types.Material:
    """A flat emission-tinted viewport material for analysis overlays."""
    palette_index = index % len(PALETTE)
    return _owned_material(
        f"PJ_Overlay_{palette_index}",
        f"overlay:{palette_index}",
        PALETTE[palette_index],
    )


# ---------------------------------------------------------------------------
# Wall geometry
# ---------------------------------------------------------------------------


def wall_from_object(obj: bpy.types.Object) -> CylindricalWall:
    """Rebuild the pure-math wall description from a tagged Blender object."""
    world_basis = obj.matrix_world.to_3x3()
    if any(
        abs(world_basis[row][column] - (1.0 if row == column else 0.0)) > 1e-6
        for row in range(3)
        for column in range(3)
    ):
        raise ProjectionError(
            f"'{obj.name}' has rotation, scale or shear in its world transform; "
            "remove inherited transforms and use Ctrl+A before analysis"
        )
    props = obj.pj_wall
    loc = obj.matrix_world.translation
    return CylindricalWall(
        base_center=(loc.x, loc.y, loc.z),
        radius=props.radius,
        height=props.height,
        angle_start=math.radians(props.arc_start_deg),
        angle_end=math.radians(props.arc_end_deg),
        concave=props.concave,
        name=obj.name,
    )


def sync_generated_wall_mesh(obj: bpy.types.Object) -> bool:
    """Rebuild a generated wall mesh after its editable parameters change."""
    if not obj.get("pj_generated_wall") or obj.get(OWNER_KEY) != OWNER_ID:
        return False
    wall = wall_from_object(obj)
    old_mesh = obj.data
    obj.data = build_wall_mesh(wall, obj.pj_wall.segments)
    if isinstance(old_mesh, bpy.types.Mesh) and old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)
    return True


def build_wall_mesh(wall: CylindricalWall, segments: int) -> bpy.types.Mesh:
    """A quad strip following the arc, with vertices local to the base centre."""
    mesh = bpy.data.meshes.new(f"{wall.name}_mesh")
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []

    step = wall.arc_length / segments
    for i in range(segments + 1):
        bottom = wall.point_at(i * step, 0.0)
        top = wall.point_at(i * step, wall.height)
        # Local coordinates: subtract the base centre so the object transform
        # can move the whole wall without invalidating the parameters.
        verts.append((bottom[0] - wall.base_center[0], bottom[1] - wall.base_center[1], 0.0))
        verts.append((top[0] - wall.base_center[0], top[1] - wall.base_center[1], wall.height))

    for i in range(segments):
        a, b = 2 * i, 2 * i + 1
        c, d = 2 * (i + 1), 2 * (i + 1) + 1
        # Wind so the face normal points at the projectors on a concave wall.
        faces.append((a, b, d, c) if wall.concave else (a, c, d, b))

    mesh.from_pydata(verts, [], faces)
    mesh.update()
    mesh.validate()
    return mesh


# ---------------------------------------------------------------------------
# Projector objects
# ---------------------------------------------------------------------------


def pose_matrix(position: Sequence[float], basis_columns) -> Matrix:
    """World matrix from a core :class:`~.core.pose.Pose`.

    Blender cameras look down local ``-Z``, which is exactly the core's
    convention, so the local axes map across directly.
    """
    x_axis, y_axis, z_axis = basis_columns
    rot = Matrix(
        (
            (x_axis[0], y_axis[0], z_axis[0]),
            (x_axis[1], y_axis[1], z_axis[1]),
            (x_axis[2], y_axis[2], z_axis[2]),
        )
    )
    return Matrix.Translation(Vector(position)) @ rot.to_4x4()


def configure_camera(obj: bpy.types.Object, spec, throw_distance: float) -> None:
    """Match the camera's optics to the projector spec.

    Blender expresses both lens shifts as a fraction of the *larger* sensor
    dimension, so the vertical shift is divided by the aspect ratio.
    """
    cam = obj.data
    from .core.throw import half_angles

    th, _ = half_angles(spec)
    cam.type = "PERSP"
    cam.sensor_fit = "HORIZONTAL"
    cam.angle_x = 2.0 * th
    cam.shift_x = spec.lens_shift_h
    cam.shift_y = spec.lens_shift_v / spec.aspect
    cam.display_size = 0.35
    cam.show_limits = True
    cam.clip_start = 0.05
    cam.clip_end = max(10.0, throw_distance * 2.0)


def apply_spec_to_object(obj: bpy.types.Object, spec, mode: str) -> None:
    """Write a core :class:`ProjectorSpec` back onto a projector object."""
    p = obj.pj_projector
    p.is_projector = True
    p.throw_ratio = spec.throw_ratio
    p.aspect_w = spec.aspect_w
    p.aspect_h = spec.aspect_h
    p.lumens = spec.lumens
    p.lens_shift_v = spec.lens_shift_v
    p.lens_shift_h = spec.lens_shift_h
    p.max_lens_shift_v = spec.max_lens_shift_v
    p.max_lens_shift_h = spec.max_lens_shift_h
    p.throw_ratio_min = spec.throw_ratio_min
    p.throw_ratio_max = spec.throw_ratio_max
    p.mount_mode = mode


def spec_from_object(obj: bpy.types.Object):
    """Read a core :class:`ProjectorSpec` out of a projector object."""
    from .core.throw import ProjectorSpec

    p = obj.pj_projector
    return ProjectorSpec(
        throw_ratio=p.throw_ratio,
        aspect_w=p.aspect_w,
        aspect_h=p.aspect_h,
        lumens=p.lumens,
        lens_shift_v=p.lens_shift_v,
        lens_shift_h=p.lens_shift_h,
        max_lens_shift_v=p.max_lens_shift_v,
        max_lens_shift_h=p.max_lens_shift_h,
        throw_ratio_min=p.throw_ratio_min,
        throw_ratio_max=p.throw_ratio_max,
        label=obj.name,
    )


def store_placement_results(obj: bpy.types.Object, placement: ProjectorPlacement) -> None:
    p = obj.pj_projector
    p.calc_throw_distance = placement.throw_distance
    p.calc_image_width = placement.image_width
    p.calc_image_height = placement.image_height
    p.calc_arc_span = placement.arc_span
    if placement.footprint is not None:
        p.calc_hit_ratio = placement.footprint.hit_ratio
        p.calc_max_incidence_deg = math.degrees(placement.footprint.max_incidence)
    p.has_result = True


def store_footprint_results(obj: bpy.types.Object, footprint: Footprint, gain: float) -> None:
    p = obj.pj_projector
    p.calc_throw_distance = footprint.center_distance
    p.calc_arc_span = footprint.arc_span
    p.calc_hit_ratio = footprint.hit_ratio
    p.calc_max_incidence_deg = math.degrees(footprint.max_incidence)
    p.calc_mean_nits = 0.0
    p.calc_image_width = 0.0
    p.calc_image_height = 0.0
    if footprint.hits():
        p.calc_mean_nits = footprint.brightness(gain).mean_nits
    from .core.throw import image_size

    if footprint.center_distance > 0.0:
        size = image_size(footprint.center_distance, footprint.spec)
        p.calc_image_width = size.width
        p.calc_image_height = size.height
    p.has_result = True


# ---------------------------------------------------------------------------
# Analysis overlays
# ---------------------------------------------------------------------------


def _offset_from_wall(point, wall: CylindricalWall, s: float):
    """Nudge a surface point off the wall along its normal to avoid z-fighting."""
    n = wall.normal_at_s(s)
    return (
        point[0] + n[0] * SURFACE_OFFSET,
        point[1] + n[1] * SURFACE_OFFSET,
        point[2] + n[2] * SURFACE_OFFSET,
    )


def build_footprint_object(
    context,
    footprint: Footprint,
    wall: CylindricalWall,
    index: int,
) -> bpy.types.Object | None:
    """A filled quad grid of where one projector's image lands on the wall.

    Built from the full sample grid rather than a single n-gon around the
    perimeter: an outline that wraps a cylinder is badly non-planar, and
    Blender's tessellation of such an n-gon collapses it to slivers. A quad
    per grid cell is planar enough to shade correctly, and it also drops
    cleanly to a partial mesh when part of the image misses the wall.
    """
    n = footprint.grid
    hits = [s.hit for s in footprint.samples]
    if sum(h is not None for h in hits) < 4:
        return None

    # One vertex per sampled hit; missed samples get no vertex and any quad
    # touching them is skipped.
    index_of: dict[int, int] = {}
    verts: list[tuple[float, float, float]] = []
    for i, hit in enumerate(hits):
        if hit is None:
            continue
        index_of[i] = len(verts)
        verts.append(_offset_from_wall(hit.point, wall, hit.s))

    faces: list[tuple[int, int, int, int]] = []
    for row in range(n - 1):
        for col in range(n - 1):
            corners = (
                row * n + col,
                row * n + col + 1,
                (row + 1) * n + col + 1,
                (row + 1) * n + col,
            )
            if all(c in index_of for c in corners):
                faces.append(tuple(index_of[c] for c in corners))

    if not faces:
        return None

    mesh = bpy.data.meshes.new(f"{footprint.name}_footprint")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    mesh.validate()

    obj = bpy.data.objects.new(f"PJ_Footprint_{footprint.name}", mesh)
    obj[OWNER_KEY] = OWNER_ID
    obj.data.materials.append(get_overlay_material(index))
    obj.color = PALETTE[index % len(PALETTE)]
    obj.show_wire = False
    link_only_to(obj, get_collection(context, COLLECTION_ANALYSIS))
    return obj


def build_frustum_object(
    context,
    footprint: Footprint,
    index: int,
) -> bpy.types.Object | None:
    """The light cone: lens to the four image corners, plus the corner loop.

    Corners come from the frustum itself at the axial throw distance rather
    than from where rays landed, so the cone still draws all four edges when
    part of the image overshoots the wall.
    """
    from .core.throw import frustum_corners_local

    distance = footprint.center_distance
    if distance <= 0.0:
        landed = footprint_corners_world(footprint)
        if len(landed) < 2:
            return None
        distance = max(
            vec_length(sub_vec(c, footprint.pose.origin)) for c in landed
        )

    pose = footprint.pose
    corners = [
        pose.local_to_world_point(c)
        for c in frustum_corners_local(distance, footprint.spec)
    ]

    origin = pose.origin
    verts = [origin] + corners
    edges = [(0, i + 1) for i in range(len(corners))]
    for i in range(len(corners)):
        edges.append((i + 1, (i + 1) % len(corners) + 1))

    mesh = bpy.data.meshes.new(f"{footprint.name}_frustum")
    mesh.from_pydata(verts, edges, [])
    mesh.update()

    obj = bpy.data.objects.new(f"PJ_Frustum_{footprint.name}", mesh)
    obj[OWNER_KEY] = OWNER_ID
    obj.color = PALETTE[index % len(PALETTE)]
    obj.display_type = "WIRE"
    obj.hide_render = True
    link_only_to(obj, get_collection(context, COLLECTION_ANALYSIS))
    return obj


def _band_geometry(
    wall: CylindricalWall,
    spans: Iterable[tuple[float, float, float, float]],
    offset_scale: float = 1.0,
    max_segment: float = 0.25,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int, int]]]:
    """Quad strips hugging the wall over the given arc ranges.

    Subdivided so no single quad spans enough arc to be visibly non-planar,
    which is what makes a band read as a curved ribbon rather than a chord.
    """
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    for start, end, z_start, z_end in spans:
        width = end - start
        if width <= 0.0 or z_end <= z_start:
            continue
        steps = min(MAX_BAND_SEGMENTS, max(1, int(math.ceil(width / max_segment))))
        base = len(verts)
        for i in range(steps + 1):
            s = start + width * i / steps
            n = wall.normal_at_s(s)
            for z in (z_start, z_end):
                p = wall.point_at(s, z)
                verts.append(
                    (
                        p[0] + n[0] * SURFACE_OFFSET * offset_scale,
                        p[1] + n[1] * SURFACE_OFFSET * offset_scale,
                        p[2],
                    )
                )
        for i in range(steps):
            a = base + 2 * i
            faces.append((a, a + 1, a + 3, a + 2))
    return verts, faces


def build_gap_object(
    context,
    wall: CylindricalWall,
    gaps: Iterable,
) -> bpy.types.Object | None:
    """One band per uncovered arc range, so dark zones are obvious."""
    verts, faces = _band_geometry(
        wall,
        [(g.start, g.end, 0.0, wall.height) for g in gaps if g.length > 0.0],
        offset_scale=1.0,
    )
    if not faces:
        return None

    mesh = bpy.data.meshes.new("PJ_Gaps_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    mesh.validate()

    obj = bpy.data.objects.new("PJ_Gaps", mesh)
    obj[OWNER_KEY] = OWNER_ID
    mat = _owned_material("PJ_Gap", "gap", (0.05, 0.05, 0.05, 1.0))
    obj.data.materials.append(mat)
    obj.color = (0.05, 0.05, 0.05, 1.0)
    link_only_to(obj, get_collection(context, COLLECTION_ANALYSIS))
    return obj


def build_blend_object(
    context,
    wall: CylindricalWall,
    blend_zones: Iterable,
) -> bpy.types.Object | None:
    """A band per blend zone, offset slightly further out than the footprints."""
    verts, faces = _band_geometry(
        wall,
        [
            (cell.s_start, cell.s_end, cell.z_start, cell.z_end)
            for zone in blend_zones
            for cell in zone.cells
        ],
        offset_scale=2.5,
    )
    if not faces:
        return None

    mesh = bpy.data.meshes.new("PJ_BlendZones_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    mesh.validate()

    obj = bpy.data.objects.new("PJ_BlendZones", mesh)
    obj[OWNER_KEY] = OWNER_ID
    mat = _owned_material("PJ_Blend", "blend", (1.0, 1.0, 1.0, 1.0))
    obj.data.materials.append(mat)
    obj.color = (1.0, 1.0, 1.0, 1.0)
    obj.show_wire = True
    link_only_to(obj, get_collection(context, COLLECTION_ANALYSIS))
    return obj
