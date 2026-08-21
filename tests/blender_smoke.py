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
        "create_curved_wall", "set_target_wall", "add_projector", "aim_at_wall",
        "plan_array", "analyze", "clear_analysis", "copy_report",
    }
    actual_ops = {o for o in dir(bpy.ops.projection) if not o.startswith("_")}
    check(expected_ops <= actual_ops, f"all operators registered (missing {expected_ops - actual_ops})")

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
    check(len(wall.data.polygons) == 48, f"wall mesh has 48 faces (got {len(wall.data.polygons)})")

    middle_face = wall.data.polygons[len(wall.data.polygons) // 2]
    radial = mathutils.Vector((middle_face.center.x, middle_face.center.y, 0.0)).normalized()
    check(middle_face.normal.dot(-radial) > 0.99, "concave wall faces wind toward projectors")

    expected_arc = 8.0 * math.radians(90.0)
    from blender_projection_system import visualization as viz
    from blender_projection_system.core.errors import ProjectionError

    core_wall = viz.wall_from_object(wall)
    check(approx(core_wall.arc_length, expected_arc), f"arc length {core_wall.arc_length:.3f} m")

    wall.pj_wall.radius = 9.0
    old_mesh = wall.data
    old_mesh_name = old_mesh.name
    check(viz.sync_generated_wall_mesh(wall), "generated wall mesh resynchronises")
    radial = [math.hypot(v.co.x, v.co.y) for v in wall.data.vertices]
    check(all(approx(r, 9.0) for r in radial), "edited wall radius reaches the visible mesh")
    check(old_mesh_name not in bpy.data.meshes, "superseded generated wall mesh is removed")
    wall.pj_wall.radius = 8.0
    viz.sync_generated_wall_mesh(wall)

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
    check(report.horizontal_coverage > 0.99, f"arc fully covered ({report.horizontal_coverage:.3f})")
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
