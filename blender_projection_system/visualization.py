"""Scene construction and analysis visualisation.

Projection results and overlays are generated from
:mod:`blender_projection_system.core` output and live in dedicated owned
collections. Generated target walls use the versioned Geometry Nodes adapter
in :mod:`blender_projection_system.procedural_geometry`; imported targets keep
their user-owned modifier stacks.

Nothing in this module registers Blender classes - it is called by the
operators in :mod:`blender_projection_system.operators`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from .core.array import ProjectorPlacement
from .core.errors import ProjectionError
from .core.footprint import Footprint, footprint_corners_world
from .core.mesh_surface import MeshHit, MeshRayCast, MeshSurface
from .core.occlusion import OcclusionCaster
from .core.surfaces import CylindricalWall, PlanarWall, Surface
from .core.vectors import length as vec_length
from .core.vectors import sub as sub_vec
from .scene_ids import MATERIAL_ROLE_KEY, OWNER_ID, OWNER_KEY, ROLE_KEY

COLLECTION_TARGETS = "PJ Targets"
COLLECTION_PROJECTORS = "PJ Projectors"
COLLECTION_ANALYSIS = "PJ Analysis"

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


def _scene_from(context_or_scene) -> bpy.types.Scene:
    return (
        context_or_scene
        if isinstance(context_or_scene, bpy.types.Scene)
        else context_or_scene.scene
    )


def get_collection(context_or_scene, name: str) -> bpy.types.Collection:
    """Fetch or create an add-on-owned top-level collection.

    Accepting either a context or a scene lets timer-driven synchronization use
    the direct data API without depending on whichever editor has focus. A user
    collection with the preferred display name is never adopted.
    """
    scene = _scene_from(context_or_scene)
    coll = next(
        (
            candidate
            for candidate in scene.collection.children
            if candidate.get(OWNER_KEY) == OWNER_ID and candidate.get(ROLE_KEY) == name
        ),
        None,
    )
    if coll is None:
        preferred = (
            name if bpy.data.collections.get(name) is None else f"{name} (Projection Planner)"
        )
        coll = bpy.data.collections.new(preferred)
        coll[OWNER_KEY] = OWNER_ID
        coll[ROLE_KEY] = name
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    return coll


def link_only_to(obj: bpy.types.Object, coll: bpy.types.Collection) -> None:
    """Make ``coll`` the object's sole collection."""
    for existing in list(obj.users_collection):
        if existing is not coll:
            existing.objects.unlink(obj)
    if obj.name not in coll.objects:
        coll.objects.link(obj)


def clear_collection(context_or_scene, name: str) -> int:
    """Delete owned objects from this scene's owned collection only."""
    scene = _scene_from(context_or_scene)
    coll = next(
        (
            candidate
            for candidate in scene.collection.children
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
            if candidate.get(OWNER_KEY) == OWNER_ID and candidate.get(MATERIAL_ROLE_KEY) == role
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


#: Cap on triangles fed to the BVH so a monster import fails loudly
#: instead of stalling the analysis silently.
MAX_MESH_TRIS = 500_000


def _bvh_caster(bvh: BVHTree) -> MeshRayCast:
    """Wrap ``BVHTree.ray_cast`` into the core :class:`MeshRayCast` shape."""

    def cast(origin, direction, max_distance):
        hit = bvh.ray_cast(Vector(origin), Vector(direction), max_distance)
        if hit[0] is None:
            return None
        location, normal, _index, distance = hit
        return MeshHit(
            point=(location.x, location.y, location.z),
            distance=distance,
            face_normal=(normal.x, normal.y, normal.z),
        )

    return cast


def _occluder_objects(scene: bpy.types.Scene) -> list[bpy.types.Object]:
    """Mesh objects the user listed (or collected) as obstacles, filtered hard.

    Excluded on purpose: the target wall and any other object tagged as a wall
    (it would shadow its own samples), projectors, add-on-owned generated
    objects, hidden objects, and non-meshes. The analysis is only honest if
    what remains is genuinely user geometry standing in the light path.
    """
    pj = scene.pj
    wall = pj.target_wall
    candidates: list[bpy.types.Object] = []
    candidates.extend(item.object for item in pj.occluders if item.object is not None)
    collection = pj.occluder_collection
    if collection is not None:
        candidates.extend(collection.objects)

    seen: set[int] = set()
    out: list[bpy.types.Object] = []
    for obj in candidates:
        if obj is None:
            continue
        pointer = obj.as_pointer()
        if pointer in seen:
            continue
        seen.add(pointer)
        if obj is wall:
            continue
        if obj.type != "MESH":
            continue
        if getattr(obj, "pj_wall", None) and obj.pj_wall.is_wall:
            continue
        if getattr(obj, "pj_projector", None) and obj.pj_projector.is_projector:
            continue
        if obj.get(OWNER_KEY) == OWNER_ID:
            continue
        if obj.hide_viewport or obj.hide_get():
            continue
        out.append(obj)
    return out


def build_occlusion_caster(scene: bpy.types.Scene) -> OcclusionCaster | None:
    """BVH over every selected obstacle, injected into the coverage analysis.

    The same dependency-inversion pattern as ADR 0004's mesh target: the BVH
    is built here (bpy-only) and the bpy-free ``core`` only ever sees the
    callable. Returns ``None`` when the user has selected no usable obstacle,
    which makes the analysis behave exactly as it did before #1.
    """
    objects = _occluder_objects(scene)
    if not objects:
        return None

    depsgraph = bpy.context.evaluated_depsgraph_get()
    world_vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    for obj in objects:
        eval_obj = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        try:
            if len(mesh.polygons) == 0:
                continue
            mesh.calc_loop_triangles()
            offset = len(world_vertices)
            matrix = eval_obj.matrix_world
            for vertex in mesh.vertices:
                world = matrix @ vertex.co
                world_vertices.append((world.x, world.y, world.z))
            triangles.extend(
                (tri.vertices[0] + offset, tri.vertices[1] + offset, tri.vertices[2] + offset)
                for tri in mesh.loop_triangles
            )
        finally:
            eval_obj.to_mesh_clear()

    if not triangles:
        return None
    if len(triangles) > MAX_MESH_TRIS:
        raise ProjectionError(
            f"obstacles total {len(triangles)} triangles (limit {MAX_MESH_TRIS}); "
            "decimate them before running the occlusion check"
        )
    bvh = BVHTree.FromPolygons(world_vertices, triangles, all_triangles=True)

    def cast(origin, direction, max_distance) -> bool:
        if max_distance <= 0.0:
            return False
        return bvh.ray_cast(Vector(origin), Vector(direction), max_distance)[0] is not None

    return cast


def _mesh_wall_from_object(obj: bpy.types.Object) -> MeshSurface:
    """Rebuild an imported-mesh target, injecting its BVH as the caster.

    Uses the depsgraph-evaluated mesh so modifier stacks (subdivision,
    arrays, displacement, …) apply — the mesh you see in the viewport is
    the surface you get. The evaluated mesh is released again before the
    surface is returned.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    try:
        if len(mesh.polygons) == 0:
            raise ProjectionError(f"'{obj.name}' has no faces; nothing to project onto")
        mesh.calc_loop_triangles()
        tris = [tuple(lt.vertices) for lt in mesh.loop_triangles]
        vertices = [(v.co.x, v.co.y, v.co.z) for v in mesh.vertices]
    finally:
        eval_obj.to_mesh_clear()
    if not tris:
        raise ProjectionError(f"'{obj.name}' could not be triangulated for ray casting")
    if len(tris) > MAX_MESH_TRIS:
        raise ProjectionError(
            f"'{obj.name}' has {len(tris)} triangles (limit {MAX_MESH_TRIS}); "
            "decimate the mesh before using it as a projection target"
        )

    translation = obj.matrix_world.translation
    world_vertices = [
        (x + translation.x, y + translation.y, z + translation.z) for x, y, z in vertices
    ]
    bvh = BVHTree.FromPolygons(world_vertices, tris, all_triangles=True)
    return MeshSurface.from_triangles(
        world_vertices,
        tris,
        caster=_bvh_caster(bvh),
        name=obj.name,
    )


def wall_from_object(obj: bpy.types.Object) -> Surface:
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
    if getattr(props, "kind", "CYLINDER") == "FLAT":
        yaw = math.radians(props.yaw_deg)
        return PlanarWall(
            base_center=(loc.x, loc.y, loc.z),
            width=props.width,
            height=props.height,
            facing=(-math.cos(yaw), -math.sin(yaw), 0.0),
            name=obj.name,
        )
    if getattr(props, "kind", "CYLINDER") == "MESH":
        return _mesh_wall_from_object(obj)
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
    """Ensure a generated wall has the current driven Geometry Nodes adapter.

    Kept under its historical name for scripting compatibility. The mesh
    datablock is no longer replaced: drivers keep the evaluated geometry in
    sync with ``obj.pj_wall``.
    """
    if not obj.get("pj_generated_wall") or obj.get(OWNER_KEY) != OWNER_ID:
        return False
    from .procedural_geometry import ensure_wall_modifier

    ensure_wall_modifier(obj)
    return True


def build_wall_mesh(wall: Surface, segments: int) -> bpy.types.Mesh:
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
        # Wind so the face normal points at the projectors.
        faces.append((a, b, d, c) if wall.normal_faces_projectors else (a, c, d, b))

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


def _offset_from_wall(point, wall: Surface, s: float):
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
    wall: Surface,
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
    # hits holds only SurfaceHit objects and None, so counting Nones gives the
    # miss count without an identity comparison.
    if len(hits) - hits.count(None) < 4:
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
                i0, i1, i2, i3 = (index_of[c] for c in corners)
                faces.append((i0, i1, i2, i3))

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
        distance = max(vec_length(sub_vec(c, footprint.pose.origin)) for c in landed)

    pose = footprint.pose
    corners = [
        pose.local_to_world_point(c) for c in frustum_corners_local(distance, footprint.spec)
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
    wall: Surface,
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
        steps = min(MAX_BAND_SEGMENTS, max(1, math.ceil(width / max_segment)))
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
    wall: Surface,
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
    wall: Surface,
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


def build_occlusion_object(
    context,
    wall: Surface,
    shadowed_cells: Iterable,
) -> bpy.types.Object | None:
    """A red band per cell that occlusion leaves dark.

    Only *fully shadowed* cells are drawn - cells where a projector is
    blocked but another still lights the spot are reported in the text and
    left to the footprint overlays, because painting them would overstate
    how much light the wall actually loses.
    """
    verts, faces = _band_geometry(
        wall,
        [(cell.s_start, cell.s_end, cell.z_start, cell.z_end) for cell in shadowed_cells],
        offset_scale=2.0,
    )
    if not faces:
        return None

    mesh = bpy.data.meshes.new("PJ_Occlusion_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    mesh.validate()

    obj = bpy.data.objects.new("PJ_Occlusion", mesh)
    obj[OWNER_KEY] = OWNER_ID
    mat = _owned_material("PJ_Occlusion", "occlusion", (0.9, 0.15, 0.15, 0.85))
    obj.data.materials.append(mat)
    obj.color = (0.9, 0.15, 0.15, 1.0)
    link_only_to(obj, get_collection(context, COLLECTION_ANALYSIS))
    return obj
