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
        modifier for modifier in wall.modifiers if modifier.get(viz.OWNER_KEY) == viz.OWNER_ID
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

    # -- 2e. controls converge cameras, overlays and reports automatically --
    print("\n[2e] all dependent scene state updates live")
    import blender_projection_system.scene_sync as live

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
    check(live.pending_scope(scene) is not None, "property edits queue a live refresh")
    check(live.flush_scene_sync(scene), "queued live refresh succeeds")

    live_projectors = sorted(
        (obj for obj in scene.objects if obj.get("pj_object_role") == live.ARRAY_OBJECT_ROLE),
        key=lambda obj: obj.name,
    )
    check(len(live_projectors) == 3, "target controls create the live three-projector array")
    live_ids = [obj.as_pointer() for obj in live_projectors]
    analysis_collection = viz.get_collection(scene, viz.COLLECTION_ANALYSIS)
    check(len(analysis_collection.objects) > 0, "live refresh creates analysis overlays")
    check(scene.pj.has_report, "live refresh creates the report")

    pj.projector_count = 2
    pj.overlap = 0.20
    pj.mount_height = 3.4
    check(live.pending_scope(scene) == live.SyncScope.ARRAY, "array edit queues array scope")
    check(live.flush_scene_sync(scene), "live array edit converges")
    live_projectors = sorted(
        (obj for obj in scene.objects if obj.get("pj_object_role") == live.ARRAY_OBJECT_ROLE),
        key=lambda obj: obj.name,
    )
    check(len(live_projectors) == 2, "live count edit removes one owned camera")
    check(live_projectors[0].as_pointer() in live_ids, "live replan reuses camera objects")
    check(
        all(approx(obj.matrix_world.translation.z, 3.4) for obj in live_projectors),
        "live mount-height edit moves every owned camera",
    )

    pj.blend_model = "LINEAR_RAMP"
    check(
        live.pending_scope(scene) == live.SyncScope.ANALYSIS,
        "analysis edit queues analysis scope only",
    )
    check(live.flush_scene_sync(scene), "live blend-model edit converges")
    report_text = "\n".join(entry.text for entry in scene.pj.report_lines).lower()
    check("linear" in report_text, "live report reflects the selected blend model")

    first_projector = live_projectors[0]
    before_nits = first_projector.pj_projector.calc_mean_nits
    first_projector.pj_projector.lumens = 3500.0
    check(live.flush_scene_sync(scene), "individual projector edit refreshes analysis")
    check(
        first_projector.pj_projector.calc_mean_nits < before_nits,
        "individual lumens edit updates computed brightness",
    )

    live_wall = scene.pj.target_wall
    if live_wall is None:
        check(False, "live target wall remains available")
        return
    camera_state = [tuple(tuple(row) for row in obj.matrix_world) for obj in live_projectors]
    overlay_state = sorted(obj.as_pointer() for obj in analysis_collection.objects)
    live_wall.pj_wall.arc_end_deg = live_wall.pj_wall.arc_start_deg
    check(not live.flush_scene_sync(scene), "invalid live edit is rejected")
    check(bool(scene.pj.live_error), "invalid live edit exposes an error")
    check(
        camera_state == [tuple(tuple(row) for row in obj.matrix_world) for obj in live_projectors],
        "invalid live edit preserves the last valid cameras",
    )
    check(
        overlay_state == sorted(obj.as_pointer() for obj in analysis_collection.objects),
        "invalid live edit preserves the last valid overlays",
    )
    live_wall.pj_wall.arc_end_deg = 45.0
    pj.projector_count = 3
    pj.overlap = 0.15
    pj.mount_height = 3.2
    pj.blend_model = "RAW"
    check(live.flush_scene_sync(scene), "next valid edit resumes live updates")
    check(not scene.pj.live_error, "successful live refresh clears the error")

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

    # -- 4b. occlusion: a real obstacle in the light path -------------------
    # A slab perpendicular to the projectors' aim at x=5 intercepts every ray
    # from every projector (they sit near x=2, the wall surface reaches x=8
    # at the arc centre and x=5.66 at its ends), so the expected answer is
    # exact: nothing is lit and every projector is fully occluded. The slab
    # carries a non-uniform scale on purpose, which also proves the caster
    # honours the full world matrix rather than translation alone.
    print("\n[4b] occlusion & line of sight")
    import blender_projection_system.scene_sync as live_sync

    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(5.0, 0.0, 2.0))
    obstacle = bpy.context.active_object
    obstacle.name = "PJ_SmokePillar"
    obstacle.scale = (0.2, 8.0, 3.0)
    bpy.context.view_layer.update()

    check(
        viz.build_occlusion_caster(scene) is None,
        "no caster is built while the obstacle list is empty",
    )

    # Every property the new UI block draws must exist on the property groups:
    # a typo there only fails when a user opens the sidebar.
    for prop_name in (
        "occluders",
        "occluder_index",
        "occluder_collection",
        "show_occlusion_overlay",
    ):
        check(hasattr(scene.pj, prop_name), f"scene exposes {prop_name}")
    for prop_name in ("calc_occluded_cells", "calc_occluded_ratio"):
        check(
            all(hasattr(o.pj_projector, prop_name) for o in projectors),
            f"projector exposes {prop_name}",
        )

    # The target wall must be refused: it would shadow its own samples.
    wall_obj_for_poll = scene.pj.target_wall
    if wall_obj_for_poll is None:
        check(False, "target wall remains available for the refusal check")
        return
    for obj in list(bpy.context.selected_objects):
        obj.select_set(False)
    wall_obj_for_poll.select_set(True)
    bpy.context.view_layer.objects.active = wall_obj_for_poll
    check(
        bpy.ops.projection.add_occluder() == {"CANCELLED"},
        "the target wall is refused as an obstacle",
    )
    check(len(scene.pj.occluders) == 0, "refused wall left the obstacle list empty")

    for obj in list(bpy.context.selected_objects):
        obj.select_set(False)
    obstacle.select_set(True)
    bpy.context.view_layer.objects.active = obstacle
    check(bpy.ops.projection.add_occluder() == {"FINISHED"}, "add_occluder finished")
    check(len(scene.pj.occluders) == 1, "obstacle recorded in the list")
    check(
        scene.pj.occluders[0].object is obstacle,
        "obstacle entry points at the selected object",
    )
    check(viz.build_occlusion_caster(scene) is not None, "a BVH caster is built")

    check(live_sync.flush_scene_sync(scene), "occlusion edit converges live")
    occluded_lines = [e.text for e in scene.pj.report_lines]
    occluded_text = "\n".join(occluded_lines)
    check(
        "occluded by an obstacle" in occluded_text,
        "occlusion is reported loudly, not silently dropped",
    )
    check(
        any(t.startswith("Occlusion:") for t in occluded_lines),
        "report carries an occlusion section",
    )
    occluded_coverage_line = next(t for t in occluded_lines if t.startswith("Coverage:"))
    occluded_coverage = float(occluded_coverage_line.split()[1].rstrip("%")) / 100.0
    check(
        occluded_coverage == 0.0 and operator_coverage > 0.0,
        f"a slab across every ray darkens the wall ({occluded_coverage:.3f} "
        f"from {operator_coverage:.3f})",
    )
    check(
        all(approx(o.pj_projector.calc_occluded_ratio, 1.0) for o in projectors),
        "every projector reports a fully occluded image",
    )
    check(
        all(o.pj_projector.calc_occluded_cells > 0 for o in projectors),
        "occluded cell counts are written back onto each projector",
    )
    occlusion_overlay = viz.get_collection(bpy.context, viz.COLLECTION_ANALYSIS)
    shadows = [o for o in occlusion_overlay.objects if o.name == "PJ_Occlusion"]
    check(len(shadows) == 1, "shadow overlay geometry was built")
    if shadows:
        check(
            len(shadows[0].data.polygons) > 0,
            "shadow overlay has drawable faces",
        )

    # Hiding the obstacle must clear the occlusion result again.
    scene.pj.show_occlusion_overlay = False
    check(live_sync.flush_scene_sync(scene), "overlay toggle converges")
    check(
        not any(o.name == "PJ_Occlusion" for o in occlusion_overlay.objects),
        "shadow overlay disappears when it is switched off",
    )
    scene.pj.show_occlusion_overlay = True

    check(bpy.ops.projection.clear_occluders() == {"FINISHED"}, "clear_occluders finished")
    check(len(scene.pj.occluders) == 0, "obstacle list is empty again")
    check(live_sync.flush_scene_sync(scene), "clearing obstacles converges")
    restored_text = "\n".join(e.text for e in scene.pj.report_lines)
    check(
        "occluded by an obstacle" not in restored_text,
        "occlusion warning clears with the obstacle",
    )
    check(
        all(approx(o.pj_projector.calc_occluded_cells, 0) for o in projectors),
        "per-projector occlusion counts reset",
    )
    check(
        all(
            approx(o.pj_projector.calc_occluded_ratio, 0.0)
            for o in projectors
        ),
        "per-projector occlusion ratios reset",
    )

    # The obstacle did not disturb the projectors or the wall.
    check(
        obstacle.name in bpy.data.objects,
        "clearing obstacles does not delete user geometry",
    )
    bpy.data.objects.remove(obstacle, do_unlink=True)

    from blender_projection_system.core.pose import look_at  # noqa: F811

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

    # -- 4c. projector & lens spec library (increment #2) -----------------
    print("\n[4c] projector & lens library")
    # Verify properties exist on scene and projectors
    for prop_name in (
        "spec_manufacturer",
        "spec_model",
        "spec_lens",
        "manufacturer",
        "model",
        "lens_model",
        "native_contrast",
        "lens_transmission",
        "source_url",
        "verified",
    ):
        check(hasattr(scene.pj, prop_name), f"scene exposes {prop_name}")
    for prop_name in (
        "manufacturer",
        "model",
        "lens_model",
        "native_contrast",
        "lens_transmission",
        "source_url",
        "verified",
    ):
        check(
            all(hasattr(o.pj_projector, prop_name) for o in projectors),
            f"projector exposes {prop_name}",
        )

    # Apply a known curated spec from the library
    scene.pj.spec_manufacturer = "Panasonic"
    scene.pj.spec_model = "PT-REQ12"
    scene.pj.spec_lens = "ET-DLE150"
    check(bpy.ops.projection.apply_preset_spec() == {"FINISHED"}, "apply_preset_spec finished")
    check(approx(scene.pj.lumens, 12000.0), "rated lumens updated to 12000 lm")
    check(scene.pj.aspect_w == 16 and scene.pj.aspect_h == 10, "native aspect updated to 16:10")
    check(approx(scene.pj.throw_ratio_min, 1.30), "lens minimum TR updated to 1.30")
    check(approx(scene.pj.throw_ratio_max, 1.89), "lens maximum TR updated to 1.89")
    check(scene.pj.verified is True, "preset flags verified status")
    check(bool(scene.pj.source_url), "preset cites source URL")

    # Live sync converges with new spec
    check(live_sync.flush_scene_sync(scene), "preset application converges live")
    check(
        all(o.pj_projector.model == "PT-REQ12" for o in projectors),
        "array projectors inherit applied model spec",
    )
    check(
        all(o.pj_projector.lens_model == "ET-DLE150" for o in projectors),
        "array projectors inherit applied lens model",
    )

    # Out-of-range throw ratio warns rather than silently clamping (ADR 0002)
    scene.pj.throw_ratio = 1.0  # below lens min 1.30
    check(live_sync.flush_scene_sync(scene), "out-of-range TR edit converges live")
    report_text_out_of_range = "\n".join(e.text for e in scene.pj.report_lines)
    check(
        "throw ratio" in report_text_out_of_range.lower() and "outside" in report_text_out_of_range.lower(),
        "out-of-range throw ratio produces loud warning in report",
    )

    # -- 4d. lumens derate chain & blend gamma (increment #3a) -----------
    print("\n[4d] lumens derate chain & blend gamma")
    for prop_name in (
        "blend_gamma",
        "use_derate_chain",
        "derate_production_tolerance",
        "derate_picture_mode",
        "derate_aging",
    ):
        check(hasattr(scene.pj, prop_name), f"scene exposes {prop_name}")

    scene.pj.blend_model = "GAMMA_RAMP"
    scene.pj.blend_gamma = 1.25
    check(live_sync.flush_scene_sync(scene), "gamma blend ramp converges live")
    report_text_gamma = "\n".join(e.text for e in scene.pj.report_lines)
    check("gamma-ramp blend model" in report_text_gamma, "report records gamma blend model")
    check("Bands (rated / typical / worst-case):" in report_text_gamma, "report displays derate bands")

    # -- 4e. ambient effective contrast (increment #3b) -------------------
    print("\n[4e] ambient effective contrast")
    for prop_name in ("ambient_lux", "iscr_category", "target_contrast_ratio"):
        check(hasattr(scene.pj, prop_name), f"scene exposes {prop_name}")

    scene.pj.ambient_lux = 50.0
    scene.pj.iscr_category = "BASIC_DECISION_MAKING"
    scene.pj.target_contrast_ratio = 15.0
    check(live_sync.flush_scene_sync(scene), "ambient contrast edit converges live")
    report_text_contrast = "\n".join(e.text for e in scene.pj.report_lines)
    check("Effective contrast" in report_text_contrast, "report displays effective contrast")
    check("Basic Decision Making" in report_text_contrast, "report displays ISCR category target")
    check("ANSI/AVIXA V201.01:2021" in report_text_contrast, "report carries ISCR disclaimer")

    # -- 4f. ANSI/IEC 9-point vocabulary output (increment #3c) -----------
    print("\n[4f] ANSI/IEC 9-point vocabulary output")
    check(hasattr(scene.pj, "enable_nine_point"), "scene exposes enable_nine_point")
    scene.pj.enable_nine_point = True
    check(live_sync.flush_scene_sync(scene), "nine-point sync converges live")
    report_text_nine = "\n".join(e.text for e in scene.pj.report_lines)
    check("ANSI/IEC 9-point output:" in report_text_nine, "report displays 9-point output")
    check("corner-to-center" in report_text_nine, "report displays corner-to-center uniformity")
    check(
        "Model output in ANSI/IEC vocabulary" in report_text_nine,
        "report carries ANSI/IEC disclaimer",
    )

    # -- 4g. structured handoff export (increment #4) ---------------------
    print("\n[4g] structured handoff export")
    import json
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp_dir:
        json_path = str(Path(tmp_dir) / "test_export.json")
        res_json = bpy.ops.projection.export_analysis(filepath=json_path, export_format="JSON")
        check(res_json == {"FINISHED"}, "export_analysis JSON finished")
        check(Path(json_path).exists(), "JSON export file exists on disk")
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        check(data["schema_version"] == 1, "exported JSON schema version is 1")
        check("wall" in data and "coverage" in data, "exported JSON has wall and coverage blocks")
        check(len(data.get("rigging_schedule", [])) == 3, "exported JSON has 3 rigging entries")

        csv_path = str(Path(tmp_dir) / "test_export.csv")
        res_csv = bpy.ops.projection.export_analysis(filepath=csv_path, export_format="CSV")
        check(res_csv == {"FINISHED"}, "export_analysis CSV finished")
        check(Path(csv_path).exists(), "CSV export file exists on disk")
        csv_content = Path(csv_path).read_text(encoding="utf-8")
        check("Wall,Name" in csv_content, "exported CSV has summary metrics")
        check("--- RIGGING SCHEDULE ---" in csv_content, "exported CSV has rigging table")

    # -- 4h. DISCAS viewer audit (increment #5) ---------------------------
    print("\n[4h] DISCAS viewer audit")
    for prop_name in (
        "enable_discas",
        "discas_element_height_pct",
        "discas_vertical_resolution",
        "farthest_viewer_distance",
    ):
        check(hasattr(scene.pj, prop_name), f"scene exposes {prop_name}")

    scene.pj.enable_discas = True
    scene.pj.farthest_viewer_distance = 12.0
    scene.pj.discas_element_height_pct = 3.0
    check(live_sync.flush_scene_sync(scene), "DISCAS sync converges live")
    report_text_discas = "\n".join(e.text for e in scene.pj.report_lines)
    check("DISCAS Viewer Audit" in report_text_discas, "report displays DISCAS section")
    check("ANSI/INFOCOMM V202.01" in report_text_discas, "report carries DISCAS disclaimer")
    check("Farthest" in report_text_discas, "report lists evaluated farthest viewer")

    # -- 4i. warp grid export (increment #4 phase 2) -----------------------
    print("\n[4i] warp grid export")
    with tempfile.TemporaryDirectory() as tmp_dir:
        warp_json = str(Path(tmp_dir) / "test_warp.json")
        res_warp = bpy.ops.projection.export_warp(
            filepath=warp_json, export_format="JSON", resolution=8
        )
        check(res_warp == {"FINISHED"}, "export_warp JSON finished")
        check(Path(warp_json).exists(), "warp JSON export file exists on disk")
        warp_data = json.loads(Path(warp_json).read_text(encoding="utf-8"))
        check(warp_data["schema_version"] == 1, "warp JSON schema version is 1")
        check(
            "design-phase" in warp_data["disclaimer"].lower(),
            "warp JSON carries the design-phase disclaimer",
        )
        check(len(warp_data["projectors"]) == 3, "warp JSON has one grid per projector")
        warp_entry = warp_data["projectors"][0]
        check(
            warp_entry["columns"] == 8 and warp_entry["rows"] == 8,
            "warp grid resolution honoured",
        )
        check(len(warp_entry["valid"]) == 64, "warp grid validity array matches resolution")
        check(any(warp_entry["valid"]), "warp grid has illuminated vertices")

        warp_obj_path = str(Path(tmp_dir) / "test_warp.obj")
        res_warp_obj = bpy.ops.projection.export_warp(
            filepath=warp_obj_path, export_format="OBJ", resolution=8
        )
        check(res_warp_obj == {"FINISHED"}, "export_warp OBJ finished")
        check(Path(warp_obj_path).exists(), "warp OBJ export file exists on disk")
        warp_obj_content = Path(warp_obj_path).read_text(encoding="utf-8")
        check(
            "design-phase" in warp_obj_content.lower(),
            "warp OBJ carries the design-phase note",
        )
        check(
            sum(1 for line in warp_obj_content.splitlines() if line.startswith("o ")) == 3,
            "warp OBJ has one object per projector",
        )
        check(
            sum(1 for line in warp_obj_content.splitlines() if line.startswith("f ")) > 0,
            "warp OBJ has faces",
        )

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
    check(
        user_analysis.name in bpy.data.collections and len(user_analysis.objects) == 1,
        "same-named user collection remains untouched after clearing",
    )
    check(user_obj.name in bpy.data.objects, "user analysis object survives clearing")
    check(other_obj.name in bpy.data.objects, "another scene's owned analysis survives clearing")
    check(
        len([o for o in scene.objects if o.pj_projector.is_projector]) == 3,
        "clearing the analysis leaves the projectors alone",
    )
    check(scene.pj.target_wall is not None, "clearing the analysis leaves the wall alone")

    import blender_projection_system.procedural_geometry as pg

    groups_before = [
        group
        for group in bpy.data.node_groups
        if group.get(viz.OWNER_KEY) == viz.OWNER_ID and group.get("pj_node_role") == pg.NODE_ROLE
    ]
    live_wall_name = live_wall.name
    live.request_scene_sync(scene, live.SyncScope.ANALYSIS, delay=60.0)
    check(live.timer_registered(), "live timer is registered before teardown")
    pjs.unregister()
    check(not live.timer_registered(), "unregister cancels the live timer")
    pjs.unregister()
    check(not hasattr(bpy.types.Scene, "pj"), "Scene.pj removed on unregister")

    pjs.register()
    check(hasattr(bpy.types.Scene, "pj"), "Scene.pj restores after reload")
    reloaded_wall = bpy.data.objects.get(live_wall_name)
    if reloaded_wall is None:
        check(False, "procedural wall survives add-on reload")
        return
    check(pg.is_procedural_wall(reloaded_wall), "procedural wall survives add-on reload")
    groups_after = [
        group
        for group in bpy.data.node_groups
        if group.get(viz.OWNER_KEY) == viz.OWNER_ID and group.get("pj_node_role") == pg.NODE_ROLE
    ]
    check(len(groups_after) == len(groups_before) == 1, "reload does not duplicate node groups")
    owned_modifiers = [
        modifier
        for modifier in reloaded_wall.modifiers
        if modifier.node_group is not None
        and modifier.node_group.get("pj_node_role") == pg.NODE_ROLE
    ]
    check(len(owned_modifiers) == 1, "reload does not duplicate wall modifiers")
    pjs.unregister()


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
