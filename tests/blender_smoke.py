"""Headless smoke test: drive the real add-on inside a real Blender.

Run by CI as::

    blender -b --factory-startup --python-exit-code 1 --python tests/blender_smoke.py

pytest cannot import ``bpy``, so everything in this file is the part of the
add-on the unit tests structurally cannot reach: registration against a live
RNA system, operator execution, and the geometry that lands in the scene.

Any assertion failure raises, and ``--python-exit-code 1`` turns that into a
non-zero exit so the CI job actually fails. A script that only printed would
pass regardless, which is what the previous "simulated" CI job did.
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import replace

import bpy
import mathutils

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    """Record a failure instead of aborting, so one run reports everything."""
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        FAILURES.append(message)


def approx(a: float, b: float, tol: float = 1e-3) -> bool:
    return abs(a - b) <= tol


def evaluated_mesh_snapshot(obj):
    """Copy evaluated vertices and face geometry, then release the temp mesh."""
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        vertices = [tuple(vertex.co) for vertex in mesh.vertices]
        polygons = [(tuple(face.center), tuple(face.normal)) for face in mesh.polygons]
        return vertices, polygons
    finally:
        evaluated.to_mesh_clear()


def main() -> None:
    import blender_projection_system as pjs

    print(f"Blender {bpy.app.version_string}, Python {sys.version.split()[0]}")
    print(f"Add-on {pjs.bl_info['name']} {pjs.bl_info['version']}")

    # -- 1. registration is repeatable ------------------------------------
    print("\n[1] register / unregister cycles")
    pjs.register()
    pjs.register()
    check(hasattr(bpy.types.Scene, "pj"), "direct double-register is idempotent")
    for _ in range(3):
        pjs.unregister()
        pjs.register()
    check(hasattr(bpy.types.Scene, "pj"), "Scene.pj survives repeated cycles")
    check(hasattr(bpy.types.Object, "pj_wall"), "Object.pj_wall registered")
    check(hasattr(bpy.types.Object, "pj_projector"), "Object.pj_projector registered")

    expected_ops = {
        "create_curved_wall",
        "create_flat_wall",
        "set_target_wall",
        "add_projector",
        "aim_at_wall",
        "plan_array",
        "analyze",
        "clear_analysis",
        "copy_report",
    }
    actual_ops = {o for o in dir(bpy.ops.projection) if not o.startswith("_")}
    check(
        expected_ops <= actual_ops,
        f"all operators registered (missing {expected_ops - actual_ops})",
    )

    # -- 2. build the target ----------------------------------------------
    print("\n[2] create a curved wall")
    result = bpy.ops.projection.create_curved_wall(
        radius=8.0, height=3.0, arc_deg=90.0, segments=48
    )
    check(result == {"FINISHED"}, "create_curved_wall finished")

    scene = bpy.context.scene
    wall = scene.pj.target_wall
    check(wall is not None, "target wall was set on the scene")
    check(wall.pj_wall.is_wall, "wall object is tagged as a projection wall")
    wall_vertices, wall_polygons = evaluated_mesh_snapshot(wall)
    check(
        len(wall_polygons) == 48,
        f"evaluated wall mesh has 48 faces (got {len(wall_polygons)})",
    )

    middle_center, middle_normal = wall_polygons[len(wall_polygons) // 2]
    radial = mathutils.Vector((middle_center[0], middle_center[1], 0.0)).normalized()
    check(
        mathutils.Vector(middle_normal).dot(-radial) > 0.99,
        "concave wall faces wind toward projectors",
    )

    expected_arc = 8.0 * math.radians(90.0)
    from blender_projection_system import visualization as viz
    from blender_projection_system.core.errors import ProjectionError

    core_wall = viz.wall_from_object(wall)
    check(approx(core_wall.arc_length, expected_arc), f"arc length {core_wall.arc_length:.3f} m")

    wall.pj_wall.radius = 9.0
    stable_mesh = wall.data
    bpy.context.view_layer.update()
    wall_vertices, _wall_polygons = evaluated_mesh_snapshot(wall)
    radial = [math.hypot(x, y) for x, y, _z in wall_vertices]
    check(all(approx(r, 9.0) for r in radial), "edited radius updates Geometry Nodes live")
    check(wall.data is stable_mesh, "live wall edits preserve the mesh datablock")
    check(viz.sync_generated_wall_mesh(wall), "procedural wall migration is idempotent")
    check(viz.sync_generated_wall_mesh(wall), "repeated procedural wall migration succeeds")
    owned_modifiers = [
        modifier
        for modifier in wall.modifiers
        if modifier.get(viz.OWNER_KEY) == viz.OWNER_ID
    ]
    check(len(owned_modifiers) == 1, "one owned Geometry Nodes modifier is attached")

    wall.pj_wall.height = 4.0
    wall.pj_wall.arc_start_deg = -30.0
    wall.pj_wall.arc_end_deg = 60.0
    wall.pj_wall.segments = 12
    wall.pj_wall.concave = False
    bpy.context.view_layer.update()
    wall_vertices, wall_polygons = evaluated_mesh_snapshot(wall)
    z_values = [z for _x, _y, z in wall_vertices]
    angles = [math.degrees(math.atan2(y, x)) for x, y, _z in wall_vertices]
    check(approx(max(z_values) - min(z_values), 4.0), "edited curved height updates live")
    check(
        approx(min(angles), -30.0) and approx(max(angles), 60.0),
        "edited arc limits update live",
    )
    check(len(wall_polygons) == 12, "edited curved segments update live")
    middle_center, middle_normal = wall_polygons[len(wall_polygons) // 2]
    radial = mathutils.Vector((middle_center[0], middle_center[1], 0.0)).normalized()
    check(
        mathutils.Vector(middle_normal).dot(radial) > 0.99,
        "convex curved-wall normals update live",
    )

    wall.pj_wall.radius = 8.0
    wall.pj_wall.height = 3.0
    wall.pj_wall.arc_start_deg = -45.0
    wall.pj_wall.arc_end_deg = 45.0
    wall.pj_wall.segments = 48
    wall.pj_wall.concave = True
    bpy.context.view_layer.update()

    parent = bpy.data.objects.new("Transformed_Wall_Parent", None)
    scene.collection.objects.link(parent)
    original_matrix = wall.matrix_world.copy()
    wall.parent = parent
    parent.rotation_euler.z = math.radians(10.0)
    bpy.context.view_layer.update()
    try:
        viz.wall_from_object(wall)
    except ProjectionError as exc:
        check(
            "world transform" in str(exc),
            f"inherited wall rotation is rejected ({exc})",
        )
    else:
        check(False, "inherited wall rotation is rejected")
    wall.parent = None
    wall.matrix_world = original_matrix
    bpy.data.objects.remove(parent, do_unlink=True)

    scene.pj.target_wall = None
    bpy.context.view_layer.objects.active = wall
    wall.select_set(True)
    check(bpy.ops.projection.set_target_wall() == {"FINISHED"}, "set_target_wall finished")

    # Manual LEVEL mounting must stay horizontal and use lens shift.
    scene.cursor.location = (4.0, 0.0, 3.2)
    scene.pj.mount_mode = "LEVEL"
    scene.pj.image_center_height = 1.5
    check(bpy.ops.projection.add_projector() == {"FINISHED"}, "manual projector added")
    manual = bpy.context.active_object
    forward = -(manual.matrix_world.to_quaternion() @ mathutils.Vector((0.0, 0.0, 1.0)))
    check(abs(forward.z) < 1e-6, "manual LEVEL projector optical axis is horizontal")
    check(abs(manual.pj_projector.lens_shift_v) > 1e-6, "manual LEVEL aim uses lens shift")
    manual_data = manual.data
    bpy.data.objects.remove(manual, do_unlink=True)
    bpy.data.cameras.remove(manual_data)

    # -- 2b. a flat wall is a first-class surface --------------------------
    print("\n[2b] create a flat wall")
    result = bpy.ops.projection.create_flat_wall(width=4.0, height=2.5, yaw_deg=0.0, segments=24)
    check(result == {"FINISHED"}, "create_flat_wall finished")
    flat_obj = scene.pj.target_wall
    if flat_obj is None:
        check(False, "flat wall became the analysis target")
        return
    check(flat_obj.pj_wall.kind == "FLAT", "flat wall tagged kind FLAT")
    flat_vertices, flat_polygons = evaluated_mesh_snapshot(flat_obj)
    check(
        len(flat_polygons) == 24,
        f"evaluated flat wall mesh has 24 faces (got {len(flat_polygons)})",
    )
    from blender_projection_system.core.surfaces import PlanarWall

    flat_core = viz.wall_from_object(flat_obj)
    check(isinstance(flat_core, PlanarWall), "wall_from_object rebuilds a PlanarWall")
    check(approx(flat_core.arc_length, 4.0), f"flat wall width {flat_core.arc_length:.3f} m")
    _mid_center, mid_normal = flat_polygons[len(flat_polygons) // 2]
    check(
        mathutils.Vector(mid_normal).dot(mathutils.Vector((-1.0, 0.0, 0.0))) > 0.99,
        "flat wall winds toward projectors",
    )
    flat_mesh_data = flat_obj.data
    flat_obj.pj_wall.width = 6.0
    flat_obj.pj_wall.yaw_deg = 30.0
    flat_obj.pj_wall.height = 3.5
    flat_obj.pj_wall.segments = 12
    bpy.context.view_layer.update()
    flat_vertices, flat_polygons = evaluated_mesh_snapshot(flat_obj)
    yaw = math.radians(30.0)
    tangent = mathutils.Vector((-math.sin(yaw), math.cos(yaw), 0.0))
    along = [mathutils.Vector(vertex).dot(tangent) for vertex in flat_vertices]
    check(approx(max(along) - min(along), 6.0), "flat width and yaw update live")
    _mid_center, mid_normal = flat_polygons[len(flat_polygons) // 2]
    expected_normal = mathutils.Vector((-math.cos(yaw), -math.sin(yaw), 0.0))
    check(mathutils.Vector(mid_normal).dot(expected_normal) > 0.99, "flat live yaw rotates normals")
    z_values = [z for _x, _y, z in flat_vertices]
    check(approx(max(z_values) - min(z_values), 3.5), "flat height updates live")
    check(len(flat_polygons) == 12, "flat segments update live")
    check(flat_obj.data is flat_mesh_data, "flat live edits preserve the mesh datablock")
    check(
        wall.modifiers[0].node_group is flat_obj.modifiers[0].node_group,
        "generated walls share one owned node group",
    )
    flat_obj.pj_wall.width = 4.0
    flat_obj.pj_wall.yaw_deg = 0.0
    flat_obj.pj_wall.height = 2.5
    flat_obj.pj_wall.segments = 24
    bpy.context.view_layer.update()
    # A projector aimed from -X lands on the planar surface end to end.
    # Mount near the image-centre height so LEVEL mode needs only modest
    # vertical lens shift (~43%) instead of pushing the image off the wall.
    pj = scene.pj
    pj.throw_ratio = 1.2
    pj.mount_mode = "LEVEL"
    pj.mount_height = 1.6
    pj.image_center_height = 1.25
    scene.cursor.location = (-3.5, 0.0, 1.6)
    check(bpy.ops.projection.add_projector() == {"FINISHED"}, "projector added against flat wall")
    flat_projector = bpy.context.active_object
    # add_projector aims but does not run analysis, so calc_hit_ratio is not
    # populated yet; derive the footprint directly from the aimed object's
    # world matrix using the same Pose convention as the analyze operator.
    from blender_projection_system.core.footprint import compute_footprint as _cfp
    from blender_projection_system.core.pose import Pose as _Pose

    basis = flat_projector.matrix_world.to_quaternion().to_matrix()
    col_x, col_y, col_z = basis.col[0], basis.col[1], basis.col[2]
    origin = flat_projector.matrix_world.translation
    pose = _Pose(
        origin=(origin.x, origin.y, origin.z),
        right=(col_x.x, col_x.y, col_x.z),
        up=(col_y.x, col_y.y, col_y.z),
        forward=(-col_z.x, -col_z.y, -col_z.z),
    )
    fp_flat = _cfp(pose, viz.spec_from_object(flat_projector), flat_core)
    check(fp_flat.hit_ratio == 1.0, "image lands fully on the flat wall")
    for o in (flat_projector,):
        cam_data = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if isinstance(cam_data, bpy.types.Camera) and cam_data.users == 0:
            bpy.data.cameras.remove(cam_data)

    # -- 2c. an imported mesh becomes a MESH-kind target --------------------
    print("\n[2c] an arbitrary mesh can be set as the target")
    # Remove the [2b] flat wall so the mesh takes over its position: at
    # x=0 the 3.5 m throw keeps the whole 16:9 image on a 2.5 m wall
    # (the same physics that let [2b] pass).
    for old_obj in list(bpy.data.objects):
        if old_obj.get("pj_generated_wall"):
            old_mesh = old_obj.data
            bpy.data.objects.remove(old_obj, do_unlink=True)
            if isinstance(old_mesh, bpy.types.Mesh) and old_mesh.users == 0:
                bpy.data.meshes.remove(old_mesh)
    ys = (-2.0, 0.0, 2.0)
    zs = (0.0, 1.25, 2.5)
    verts = [(0.0, y, z) for z in zs for y in ys]
    faces = []
    stride = len(ys)
    for iz in range(len(zs) - 1):
        for iy in range(len(ys) - 1):
            a = iz * stride + iy
            # Wound CCW seen from -X so face normals point at projectors.
            faces.append((a, a + stride, a + stride + 1, a + 1))
    mesh_data = bpy.data.meshes.new("ImportedWall")
    mesh_data.from_pydata(verts, [], faces)
    mesh_obj = bpy.data.objects.new("ImportedWall", mesh_data)
    scene.collection.objects.link(mesh_obj)
    mesh_obj.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()

    bpy.ops.object.select_all(action="DESELECT")
    mesh_obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_obj
    check(
        bpy.ops.projection.set_target_wall() == {"FINISHED"},
        "imported mesh accepted by set_target_wall",
    )
    check(scene.pj.target_wall is mesh_obj, "mesh became the analysis target")
    check(
        mesh_obj.pj_wall.kind == "MESH",
        "untagged mesh auto-tagged kind MESH",
    )
    from blender_projection_system.core.mesh_surface import MeshSurface as _MeshSurface

    core_mesh = viz.wall_from_object(mesh_obj)
    check(isinstance(core_mesh, _MeshSurface), "wall_from_object rebuilds a MeshSurface")
    check(approx(core_mesh.arc_length, 4.0), f"mesh width {core_mesh.arc_length:.3f} m")
    check(approx(core_mesh.height, 2.5), f"mesh height {core_mesh.height:.3f} m")

    pj.throw_ratio = 1.2
    pj.mount_mode = "LEVEL"
    pj.mount_height = 1.6
    pj.image_center_height = 1.25
    scene.cursor.location = (-3.5, 0.0, 1.6)
    check(bpy.ops.projection.add_projector() == {"FINISHED"}, "projector added against mesh")
    mesh_projector = bpy.context.active_object
    basis = mesh_projector.matrix_world.to_quaternion().to_matrix()
    col_x, col_y, col_z = basis.col[0], basis.col[1], basis.col[2]
    origin = mesh_projector.matrix_world.translation
    pose = _Pose(
        origin=(origin.x, origin.y, origin.z),
        right=(col_x.x, col_x.y, col_x.z),
        up=(col_y.x, col_y.y, col_y.z),
        forward=(-col_z.x, -col_z.y, -col_z.z),
    )
    fp_mesh = _cfp(pose, viz.spec_from_object(mesh_projector), core_mesh)
    check(fp_mesh.hit_ratio == 1.0, "image lands fully on the imported mesh")

    cam_data = mesh_projector.data
    bpy.data.objects.remove(mesh_projector, do_unlink=True)
    if isinstance(cam_data, bpy.types.Camera) and cam_data.users == 0:
        bpy.data.cameras.remove(cam_data)
    bpy.data.objects.remove(mesh_obj, do_unlink=True)
    if mesh_data.users == 0:
        bpy.data.meshes.remove(mesh_data)
    scene.pj.target_wall = None

    # -- 2d. modifier stacks on a mesh target are applied --------------------
    print("\n[2d] modifiers on a mesh target are applied")
    # Same 4 m × 2.5 m quad as [2c], but an Array modifier duplicates it
    # 4 m along +Y: the evaluated mesh is 8 m wide, the base mesh is not.
    mod_mesh_data = bpy.data.meshes.new("ArrayWall")
    mod_mesh_data.from_pydata(verts, [], faces)
    mod_obj = bpy.data.objects.new("ArrayWall", mod_mesh_data)
    scene.collection.objects.link(mod_obj)
    mod_obj.location = (0.0, 0.0, 0.0)
    array_mod = mod_obj.modifiers.new("Duplicate", "ARRAY")
    array_mod.count = 2
    array_mod.use_relative_offset = False
    array_mod.use_constant_offset = True
    array_mod.constant_offset_displace = (0.0, 4.0, 0.0)
    bpy.context.view_layer.update()
    mod_obj.pj_wall.kind = "MESH"
    core_mod = viz.wall_from_object(mod_obj)
    check(isinstance(core_mod, _MeshSurface), "modified mesh rebuilds a MeshSurface")
    check(
        approx(core_mod.arc_length, 8.0),
        f"array-applied width {core_mod.arc_length:.3f} m (base mesh is 4 m)",
    )
    check(approx(core_mod.height, 2.5), f"array-applied height {core_mod.height:.3f} m")
    bpy.data.objects.remove(mod_obj, do_unlink=True)
    if mod_mesh_data.users == 0:
        bpy.data.meshes.remove(mod_mesh_data)

    # Restore the curved wall so the array-planning sections run as before.
    result = bpy.ops.projection.create_curved_wall(
        radius=8.0, height=3.0, arc_deg=90.0, segments=48
    )
    check(result == {"FINISHED"}, "curved wall restored after flat-wall checks")

    # -- 3. plan a three-projector array -----------------------------------
    print("\n[3] plan a 3-projector ceiling array")
    pj = scene.pj
    pj.throw_ratio = 1.2
    pj.aspect_w, pj.aspect_h = 16, 9
    pj.lumens = 7000.0
    pj.max_lens_shift_v = 0.6
    pj.mount_mode = "LEVEL"
    pj.mount_height = 3.2
    pj.image_center_height = 1.65
    pj.projector_count = 3
    pj.overlap = 0.15
    pj.samples = 9

    check(bpy.ops.projection.plan_array() == {"FINISHED"}, "plan_array finished")

    projectors = [o for o in scene.objects if o.pj_projector.is_projector]

    original_spec = viz.spec_from_object(projectors[0])
    ranged_spec = replace(original_spec, throw_ratio_min=0.8, throw_ratio_max=1.6)
    viz.apply_spec_to_object(projectors[0], ranged_spec, projectors[0].pj_projector.mount_mode)
    round_trip_spec = viz.spec_from_object(projectors[0])
    check(
        approx(round_trip_spec.throw_ratio_min, 0.8)
        and approx(round_trip_spec.throw_ratio_max, 1.6),
        "projector lens range survives the Blender object round trip",
    )
    check(len(projectors) == 3, f"three projectors created (got {len(projectors)})")
    check(all(o.type == "CAMERA" for o in projectors), "projectors are camera objects")
    check(
        all(approx(o.matrix_world.translation.z, 3.2) for o in projectors),
        "every projector hangs at the 3.2 m mount height",
    )
    check(
        all(o.pj_projector.calc_throw_distance > 0.0 for o in projectors),
        "throw distance computed for every projector",
    )
    check(
        all(abs(o.pj_projector.lens_shift_v) <= 0.6 + 1e-6 for o in projectors),
        "required lens shift is within the configured lens limit",
    )
    for o in sorted(projectors, key=lambda o: o.name):
        p = o.pj_projector
        loc = o.matrix_world.translation
        print(
            f"       {o.name}: pos=({loc.x:+.3f}, {loc.y:+.3f}, {loc.z:.3f}) "
            f"throw={p.calc_throw_distance:.3f} m image={p.calc_image_width:.3f}x"
            f"{p.calc_image_height:.3f} m shift={p.lens_shift_v * 100:+.1f}%"
        )

    # A user object that merely carries similarly named flags is not ours to delete.
    projector_coll = viz.get_collection(bpy.context, viz.COLLECTION_PROJECTORS)
    impostor_data = bpy.data.cameras.new("User_Flagged_Camera")
    impostor = bpy.data.objects.new("User_Flagged_Projector", impostor_data)
    impostor.pj_projector.is_projector = True
    impostor["pj_generated"] = True
    projector_coll.objects.link(impostor)
    check(bpy.ops.projection.plan_array() == {"FINISHED"}, "array replacement finished")
    check(impostor.name in bpy.data.objects, "array replacement preserves unowned flagged objects")
    bpy.data.objects.remove(impostor, do_unlink=True)
    bpy.data.cameras.remove(impostor_data)
    projectors = [o for o in scene.objects if o.pj_projector.is_projector]

    for obj in projectors:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = projectors[0]
    check(bpy.ops.projection.aim_at_wall() == {"FINISHED"}, "aim_at_wall finished")

    # -- 4. analyse coverage ------------------------------------------------
    print("\n[4] calculate coverage")
    user_analysis = bpy.data.collections.new("PJ Analysis")
    scene.collection.children.link(user_analysis)
    user_mesh = bpy.data.meshes.new("User_Analysis_Mesh")
    user_obj = bpy.data.objects.new("User_Analysis_Object", user_mesh)
    user_analysis.objects.link(user_obj)
    user_blend_material = bpy.data.materials.new("PJ_Blend")
    user_blend_material.diffuse_color = (0.8, 0.1, 0.2, 1.0)
    projectors[0].scale = (2.0, 1.0, 0.5)
    check(bpy.ops.projection.analyze(visualize=True) == {"FINISHED"}, "analyze finished")
    projectors[0].scale = (1.0, 1.0, 1.0)
    check(scene.pj.has_report, "a report was produced")

    lines = [e.text for e in scene.pj.report_lines]
    check(any("Coverage:" in t for t in lines), "report states coverage")
    check(any("blend" in t for t in lines), "report lists blend zones")
    check(
        any("assumptions" in t.lower() for t in lines),
        "report carries its photometric assumptions",
    )
    coverage_line = next(t for t in lines if t.startswith("Coverage:"))
    operator_coverage = float(coverage_line.split()[1].rstrip("%")) / 100.0

    analysis = viz.get_collection(bpy.context, viz.COLLECTION_ANALYSIS)
    check(analysis is not None, "PJ Analysis collection exists")
    check(user_obj.name in bpy.data.objects, "same-named user collection content survives analysis")
    if analysis is not None:
        footprints = [o for o in analysis.objects if o.name.startswith("PJ_Footprint")]
        check(len(footprints) == 3, f"one footprint mesh per projector (got {len(footprints)})")
        check(
            all(len(o.data.polygons) > 1 for o in footprints),
            "footprints are quad grids, not a single degenerate n-gon",
        )
        blends = [o for o in analysis.objects if o.name == "PJ_BlendZones"]
        check(len(blends) == 1, "blend-zone geometry was built")
        if blends:
            blend_z = [v.co.z for v in blends[0].data.vertices]
            check(min(blend_z) > 0.05, "blend geometry excludes the unlit lower wall strip")
            check(
                blends[0].data.materials[0] is not user_blend_material,
                "same-named user material is not adopted",
            )
    check(
        all(
            approx(actual, expected)
            for actual, expected in zip(
                user_blend_material.diffuse_color, (0.8, 0.1, 0.2, 1.0), strict=True
            )
        ),
        "same-named user material is not mutated",
    )
    check(bpy.ops.projection.copy_report() == {"FINISHED"}, "copy_report finished")

    from blender_projection_system.core.surfaces import CylindricalWall

    huge_wall = CylindricalWall(radius=1_000_000.0, height=3.0, angle_start=0.0, angle_end=1.0)
    _, bounded_faces = viz._band_geometry(
        huge_wall, [(0.0, huge_wall.arc_length, 0.0, huge_wall.height)]
    )
    check(
        len(bounded_faces) == viz.MAX_BAND_SEGMENTS,
        "wall-band tessellation has a hard resource ceiling",
    )

    # Re-run the core maths directly and require the same answer, so a silent
    # divergence between the Blender layer and core/ cannot pass.
    # Private adapter coupling is intentional here: the smoke test verifies the
    # same Blender-matrix conversion used by the operator layer.
    from blender_projection_system.core.coverage import analyze_coverage
    from blender_projection_system.core.footprint import compute_footprint
    from blender_projection_system.operators import _pose_from_matrix

    poses = []
    for o in sorted(projectors, key=lambda o: o.name):
        m = o.matrix_world
        poses.append(
            (
                _pose_from_matrix(m),
                viz.spec_from_object(o),
                o.name,
            )
        )
    fps = [compute_footprint(p, s, core_wall, samples=9, name=n) for p, s, n in poses]
    report = analyze_coverage(fps, core_wall, grid_s=pj.grid_s, grid_z=pj.grid_z)
    check(
        approx(report.covered_fraction, operator_coverage, tol=0.0006),
        "operator coverage matches a direct production-core calculation",
    )
    check(
        report.horizontal_coverage > 0.99, f"arc fully covered ({report.horizontal_coverage:.3f})"
    )
    check(report.gaps == [], f"no dark bands (got {len(report.gaps)})")
    check(len(report.blend_zones) == 2, f"two blend zones (got {len(report.blend_zones)})")
    check(report.max_overlap_count == 2, f"no triple overlap (max {report.max_overlap_count})")

    # A no-hit reanalysis must not retain photometry or image dimensions from
    # the previous successful calculation, and it must not invent assumptions.
    from blender_projection_system.core.pose import look_at

    original_matrices = [o.matrix_world.copy() for o in projectors]
    for o in projectors:
        loc = tuple(o.matrix_world.translation)
        away = look_at(loc, (loc[0] - 1.0, loc[1], loc[2]))
        o.matrix_world = viz.pose_matrix(away.origin, away.basis_columns())
    check(
        bpy.ops.projection.analyze(visualize=False) == {"FINISHED"},
        "no-hit reanalysis finishes",
    )
    dark_lines = [e.text for e in scene.pj.report_lines]
    check(
        not any(t.startswith("Brightness assumptions:") for t in dark_lines),
        "no-hit report omits empty brightness assumptions",
    )
    check(
        any(t.startswith("Horizontal coverage: 0.0%") for t in dark_lines),
        "no-hit report states zero horizontal coverage",
    )
    check(
        all(
            o.pj_projector.calc_mean_nits == 0.0
            and o.pj_projector.calc_image_width == 0.0
            and o.pj_projector.calc_image_height == 0.0
            for o in projectors
        ),
        "no-hit reanalysis clears stale projector results",
    )
    for o, matrix in zip(projectors, original_matrices, strict=True):
        o.matrix_world = matrix

    # -- 5. teardown is clean ----------------------------------------------
    print("\n[5] clear analysis and unregister")
    other_scene = bpy.data.scenes.new("Other Projection Scene")
    bpy.context.window.scene = other_scene
    other_analysis = viz.get_collection(bpy.context, viz.COLLECTION_ANALYSIS)
    other_mesh = bpy.data.meshes.new("Other_Analysis_Mesh")
    other_obj = bpy.data.objects.new("Other_Analysis_Object", other_mesh)
    other_obj[viz.OWNER_KEY] = viz.OWNER_ID
    other_analysis.objects.link(other_obj)
    bpy.context.window.scene = scene
    check(bpy.ops.projection.clear_analysis() == {"FINISHED"}, "clear_analysis finished")
    leftover = bpy.data.collections.get("PJ Analysis")
    check(
        leftover is not None and len(leftover.objects) == 1,
        "same-named user collection remains untouched after clearing",
    )
    check(user_obj.name in bpy.data.objects, "user analysis object survives clearing")
    check(other_obj.name in bpy.data.objects, "another scene's owned analysis survives clearing")
    check(
        len([o for o in scene.objects if o.pj_projector.is_projector]) == 3,
        "clearing the analysis leaves the projectors alone",
    )
    check(scene.pj.target_wall is not None, "clearing the analysis leaves the wall alone")

    pjs.unregister()
    pjs.unregister()
    check(not hasattr(bpy.types.Scene, "pj"), "Scene.pj removed on unregister")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        FAILURES.append("uncaught exception (see traceback above)")

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"SMOKE TEST FAILED: {len(FAILURES)} check(s)")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("SMOKE TEST PASSED")
    sys.exit(0)
