"""Operators implementing the curved-wall planning workflow.

The flow is: create a wall, generate or place projectors, analyse, read the
report. Every operator is non-destructive with respect to user geometry - the
only thing ever deleted is the add-on's own ``PJ Analysis`` collection.

All arithmetic is delegated to :mod:`blender_projection_system.core`. These
classes handle scene I/O, collection hygiene and turning
:class:`~.core.errors.ProjectionError` into a readable operator report.
"""

from __future__ import annotations

import math
from dataclasses import replace

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty
from bpy.types import Operator

from . import visualization as viz
from .core.array import MODE_LEVEL, MODE_TILT, format_placement, plan_array
from .core.coverage import analyze_coverage, format_report
from .core.errors import ProjectionError
from .core.footprint import compute_footprint
from .core.photometry import brightness_warnings
from .core.pose import level_pose, look_at
from .core.surfaces import CylindricalWall
from .core.throw import ProjectorSpec, describe_throw, image_size, required_lens_shift_v

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _set_report(scene, lines: list[str], warnings: list[str]) -> None:
    """Replace the stored report shown in the sidebar."""
    pj = scene.pj
    pj.report_lines.clear()
    for line in lines:
        entry = pj.report_lines.add()
        entry.text = line
        entry.kind = "INFO"
    for warning in warnings:
        entry = pj.report_lines.add()
        entry.text = warning
        entry.kind = "WARNING"
    pj.has_report = True


def _resolve_wall(context) -> bpy.types.Object | None:
    """The scene's target wall, falling back to the active object if it is one."""
    pj = context.scene.pj
    if pj.target_wall and pj.target_wall.pj_wall.is_wall:
        return pj.target_wall
    active = context.active_object
    if active is not None and active.pj_wall.is_wall:
        return active
    return None


def _wall_for_operation(obj: bpy.types.Object) -> CylindricalWall:
    """Synchronise an add-on wall's mesh, then return its core geometry."""
    viz.sync_generated_wall_mesh(obj)
    return viz.wall_from_object(obj)


def _manual_pose_and_spec(position, target, spec: ProjectorSpec, mode: str):
    """Aim a manually placed projector while respecting its mount mode."""
    origin = tuple(position)
    if mode == MODE_LEVEL:
        horizontal = math.hypot(target[0] - origin[0], target[1] - origin[1])
        if horizontal <= 1e-6:
            raise ProjectionError("projector must be horizontally separated from its aim point")
        pose = level_pose(origin, (target[0] - origin[0], target[1] - origin[1], 0.0))
        height = image_size(horizontal, spec).height
        aimed_spec = replace(
            spec,
            lens_shift_h=0.0,
            lens_shift_v=required_lens_shift_v(target[2] - origin[2], height),
        )
        return pose, aimed_spec, horizontal
    if mode == MODE_TILT:
        pose = look_at(origin, target)
        distance = math.dist(origin, target)
        return pose, replace(spec, lens_shift_h=0.0, lens_shift_v=0.0), distance
    raise ProjectionError(f"unknown mount mode {mode!r}")


def _scene_spec(scene) -> ProjectorSpec:
    pj = scene.pj
    return ProjectorSpec(
        throw_ratio=pj.throw_ratio,
        aspect_w=pj.aspect_w,
        aspect_h=pj.aspect_h,
        lumens=pj.lumens,
        max_lens_shift_v=pj.max_lens_shift_v,
    )


def _projectors_in_scene(context) -> list[bpy.types.Object]:
    return [
        obj
        for obj in context.scene.objects
        if obj.pj_projector.is_projector and obj.visible_get() is not False
    ]


# ---------------------------------------------------------------------------
# Target creation
# ---------------------------------------------------------------------------


class PJ_OT_create_curved_wall(Operator):
    """Create a cylindrical projection wall and set it as the analysis target"""

    bl_idname = "projection.create_curved_wall"
    bl_label = "Create Curved Wall"
    bl_options = {"REGISTER", "UNDO"}

    radius: FloatProperty(
        name="Radius", default=8.0, min=0.05, soft_max=100.0, unit="LENGTH",
        description="Radius of curvature. Larger is flatter",
    )
    height: FloatProperty(
        name="Height", default=3.0, min=0.05, soft_max=30.0, unit="LENGTH"
    )
    arc_deg: FloatProperty(
        name="Arc", default=90.0, min=1.0, max=350.0,
        description="Angular sweep of the wall in degrees, centred on +X",
    )
    segments: IntProperty(name="Segments", default=48, min=2, max=512)
    concave: BoolProperty(
        name="Concave",
        default=True,
        description="Projectors sit inside the arc, which is the usual case",
    )
    base_height: FloatProperty(
        name="Base Height", default=0.0, soft_min=-10.0, soft_max=10.0, unit="LENGTH",
        description="Height of the bottom edge of the wall",
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=360)

    def execute(self, context):
        try:
            wall = CylindricalWall(
                base_center=(0.0, 0.0, self.base_height),
                radius=self.radius,
                height=self.height,
                angle_start=math.radians(-self.arc_deg / 2.0),
                angle_end=math.radians(self.arc_deg / 2.0),
                concave=self.concave,
                name="PJ_CurvedWall",
            )
        except ProjectionError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        mesh = viz.build_wall_mesh(wall, self.segments)
        obj = bpy.data.objects.new("PJ_CurvedWall", mesh)
        obj[viz.OWNER_KEY] = viz.OWNER_ID
        obj["pj_generated_wall"] = True
        obj.location = (0.0, 0.0, self.base_height)

        props = obj.pj_wall
        props.is_wall = True
        props.radius = self.radius
        props.height = self.height
        props.arc_start_deg = -self.arc_deg / 2.0
        props.arc_end_deg = self.arc_deg / 2.0
        props.segments = self.segments
        props.concave = self.concave

        viz.link_only_to(obj, viz.get_collection(context, viz.COLLECTION_TARGETS))
        context.scene.pj.target_wall = obj

        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj

        self.report(
            {"INFO"},
            f"Created {wall.arc_length:.2f} m x {self.height:.2f} m curved wall "
            f"(R={self.radius:.2f} m, {self.arc_deg:.0f} deg)",
        )
        return {"FINISHED"}


class PJ_OT_set_target_wall(Operator):
    """Use the active object as the projection target"""

    bl_idname = "projection.set_target_wall"
    bl_label = "Set as Target Wall"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        if not obj.pj_wall.is_wall:
            self.report(
                {"ERROR"},
                f"'{obj.name}' is not a projection wall. Use Create Curved Wall, or set "
                "its Is Projection Wall flag and fill in radius, height and arc.",
            )
            return {"CANCELLED"}
        context.scene.pj.target_wall = obj
        self.report({"INFO"}, f"Target wall set to '{obj.name}'")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Projectors
# ---------------------------------------------------------------------------


class PJ_OT_add_projector(Operator):
    """Add a single projector at the 3D cursor, aimed at the target wall"""

    bl_idname = "projection.add_projector"
    bl_label = "Add Projector"
    bl_options = {"REGISTER", "UNDO"}

    use_mount_height: BoolProperty(
        name="Snap to Mount Height",
        default=True,
        description="Place the projector at the scene's mount height instead of the cursor Z",
    )

    def execute(self, context):
        scene = context.scene
        pj = scene.pj
        cursor = context.scene.cursor.location
        z = pj.mount_height if self.use_mount_height else cursor.z

        cam_data = bpy.data.cameras.new("PJ_Projector")
        obj = bpy.data.objects.new("PJ_Projector", cam_data)
        obj.location = (cursor.x, cursor.y, z)

        spec = _scene_spec(scene)
        viz.apply_spec_to_object(obj, spec, pj.mount_mode)
        viz.configure_camera(obj, spec, 6.0)
        viz.link_only_to(obj, viz.get_collection(context, viz.COLLECTION_PROJECTORS))

        wall_obj = _resolve_wall(context)
        if wall_obj is not None:
            try:
                wall = _wall_for_operation(wall_obj)
            except ProjectionError as exc:
                bpy.data.objects.remove(obj, do_unlink=True)
                if cam_data.users == 0:
                    bpy.data.cameras.remove(cam_data)
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            target = wall.point_at(wall.arc_length / 2, pj.image_center_height)
            try:
                pose, spec, distance = _manual_pose_and_spec(
                    obj.location, target, spec, pj.mount_mode
                )
            except ProjectionError as exc:
                bpy.data.objects.remove(obj, do_unlink=True)
                if cam_data.users == 0:
                    bpy.data.cameras.remove(cam_data)
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            obj.matrix_world = viz.pose_matrix(pose.origin, pose.basis_columns())
            viz.apply_spec_to_object(obj, spec, pj.mount_mode)
            viz.configure_camera(obj, spec, distance)

        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj

        note = "" if wall_obj else " (no target wall set, so it is not aimed)"
        self.report({"INFO"}, f"Added '{obj.name}'{note}")
        return {"FINISHED"}


class PJ_OT_aim_at_wall(Operator):
    """Aim the selected projectors at a point on the target wall"""

    bl_idname = "projection.aim_at_wall"
    bl_label = "Aim at Wall"
    bl_options = {"REGISTER", "UNDO"}

    arc_fraction: FloatProperty(
        name="Arc Position",
        default=0.5,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
        description="Where along the wall arc to aim, 0 at one end and 1 at the other",
    )
    spread: BoolProperty(
        name="Spread Selection",
        default=True,
        description="Distribute multiple selected projectors evenly along the arc",
    )

    @classmethod
    def poll(cls, context):
        return any(obj.pj_projector.is_projector for obj in context.selected_objects)

    def execute(self, context):
        wall_obj = _resolve_wall(context)
        if wall_obj is None:
            self.report({"ERROR"}, "No target wall set. Create one or use Set as Target Wall.")
            return {"CANCELLED"}

        try:
            wall = _wall_for_operation(wall_obj)
        except ProjectionError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        z = context.scene.pj.image_center_height
        projectors = [o for o in context.selected_objects if o.pj_projector.is_projector]
        projectors.sort(
            key=lambda o: (
                wall.project_point(tuple(o.matrix_world.translation)).s
                if wall.project_point(tuple(o.matrix_world.translation)) is not None
                else wall.arc_length * 0.5
            )
        )

        for i, obj in enumerate(projectors):
            if self.spread and len(projectors) > 1:
                fraction = (i + 0.5) / len(projectors)
            else:
                fraction = self.arc_fraction
            target = wall.point_at(wall.arc_length * fraction, z)
            try:
                spec = viz.spec_from_object(obj)
                pose, spec, distance = _manual_pose_and_spec(
                    obj.matrix_world.translation,
                    target,
                    spec,
                    obj.pj_projector.mount_mode,
                )
            except ProjectionError as exc:
                self.report({"ERROR"}, f"{obj.name}: {exc}")
                return {"CANCELLED"}
            obj.matrix_world = viz.pose_matrix(pose.origin, pose.basis_columns())
            viz.apply_spec_to_object(obj, spec, obj.pj_projector.mount_mode)
            viz.configure_camera(obj, spec, distance)

        self.report({"INFO"}, f"Aimed {len(projectors)} projector(s) at '{wall_obj.name}'")
        return {"FINISHED"}


class PJ_OT_plan_array(Operator):
    """Generate a projector array across the target wall with the set overlap"""

    bl_idname = "projection.plan_array"
    bl_label = "Plan Projector Array"
    bl_options = {"REGISTER", "UNDO"}

    replace_existing: BoolProperty(
        name="Replace Existing",
        default=True,
        description="Remove previously generated array projectors before planning",
    )

    @classmethod
    def poll(cls, context):
        return _resolve_wall(context) is not None

    def execute(self, context):
        scene = context.scene
        pj = scene.pj
        wall_obj = _resolve_wall(context)
        if wall_obj is None:
            self.report({"ERROR"}, "No target wall set. Create one first.")
            return {"CANCELLED"}

        try:
            wall = _wall_for_operation(wall_obj)
        except ProjectionError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        try:
            plan = plan_array(
                wall,
                _scene_spec(scene),
                count=pj.projector_count,
                overlap_fraction=pj.overlap,
                mount_height=pj.mount_height,
                image_center_height=pj.image_center_height,
                mode=pj.mount_mode,
                samples=pj.samples,
                name_prefix="PJ",
            )
        except ProjectionError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        coll = viz.get_collection(context, viz.COLLECTION_PROJECTORS)
        if self.replace_existing:
            for obj in list(coll.objects):
                if (
                    obj.pj_projector.is_projector
                    and obj.get("pj_generated")
                    and obj.get(viz.OWNER_KEY) == viz.OWNER_ID
                ):
                    data = obj.data
                    bpy.data.objects.remove(obj, do_unlink=True)
                    if isinstance(data, bpy.types.Camera) and data.users == 0:
                        bpy.data.cameras.remove(data)

        created = []
        for placement in plan.placements:
            cam_data = bpy.data.cameras.new(placement.name)
            obj = bpy.data.objects.new(placement.name, cam_data)
            obj[viz.OWNER_KEY] = viz.OWNER_ID
            obj["pj_generated"] = True
            obj.matrix_world = viz.pose_matrix(
                placement.position, placement.pose.basis_columns()
            )
            viz.apply_spec_to_object(obj, placement.spec, placement.mode)
            viz.configure_camera(obj, placement.spec, placement.throw_distance)
            viz.store_placement_results(obj, placement)
            viz.link_only_to(obj, coll)
            created.append(obj)

        warnings = list(plan.warnings)
        for placement in plan.placements:
            warnings.extend(placement.warnings)

        lines = [
            f"Planned {len(created)} projector(s) on '{wall_obj.name}'",
            f"Target image width per projector: {plan.target_arc_width:.2f} m of arc "
            f"at {pj.overlap * 100:.0f}% overlap",
            f"Mount height {pj.mount_height:.2f} m, image centre {pj.image_center_height:.2f} m "
            "above wall base, "
            f"mode {pj.mount_mode}",
        ]
        for placement in plan.placements:
            lines.extend(format_placement(placement))
        _set_report(scene, lines, warnings)

        bpy.ops.object.select_all(action="DESELECT")
        for obj in created:
            obj.select_set(True)
        if created:
            context.view_layer.objects.active = created[0]

        level = {"WARNING"} if warnings else {"INFO"}
        self.report(
            level,
            f"Planned {len(created)} projector(s); {len(warnings)} warning(s). "
            "See the Report panel.",
        )
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


class PJ_OT_analyze(Operator):
    """Cast every projector onto the target wall and report coverage"""

    bl_idname = "projection.analyze"
    bl_label = "Calculate Coverage"
    bl_options = {"REGISTER", "UNDO"}

    visualize: BoolProperty(
        name="Build Visualisation",
        default=True,
        description="Create footprint, blend and gap overlays in the PJ Analysis collection",
    )

    @classmethod
    def poll(cls, context):
        return _resolve_wall(context) is not None

    def execute(self, context):
        scene = context.scene
        pj = scene.pj
        wall_obj = _resolve_wall(context)
        if wall_obj is None:
            self.report({"ERROR"}, "No target wall set. Create one first.")
            return {"CANCELLED"}

        projectors = _projectors_in_scene(context)
        if not projectors:
            self.report(
                {"ERROR"},
                "No projectors in the scene. Use Add Projector or Plan Projector Array.",
            )
            return {"CANCELLED"}

        try:
            wall = _wall_for_operation(wall_obj)
        except ProjectionError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        footprints = []
        warnings: list[str] = []

        for obj in projectors:
            spec = viz.spec_from_object(obj)
            matrix = obj.matrix_world
            # Blender cameras look down -Z, matching the core pose convention.
            pose = _pose_from_matrix(matrix)
            try:
                fp = compute_footprint(pose, spec, wall, samples=pj.samples, name=obj.name)
            except ProjectionError as exc:
                self.report({"ERROR"}, f"{obj.name}: {exc}")
                return {"CANCELLED"}
            footprints.append(fp)
            viz.store_footprint_results(obj, fp, pj.screen_gain)
            warnings.extend(fp.warnings)
            warnings.extend(describe_throw(max(fp.center_distance, 1e-3), spec).warnings)

        report = analyze_coverage(
            footprints, wall, grid_s=pj.grid_s, grid_z=pj.grid_z, screen_gain=pj.screen_gain
        )
        warnings.extend(report.warnings)
        if report.brightness is not None:
            warnings.extend(brightness_warnings(report.brightness))

        lines = format_report(report)
        lines.append("Projector mounting and throw:")
        for obj in sorted(projectors, key=lambda candidate: candidate.name):
            props = obj.pj_projector
            location = obj.matrix_world.translation
            lines.append(
                f"  {obj.name}: mount x={location.x:+.2f} y={location.y:+.2f} "
                f"z={location.z:.2f} m; throw {props.calc_throw_distance:.2f} m; "
                f"image {props.calc_image_width:.2f} x {props.calc_image_height:.2f} m; "
                f"shift V={props.lens_shift_v * 100:+.1f}% H={props.lens_shift_h * 100:+.1f}%"
            )
        lines.append("Brightness assumptions: " + "; ".join(
            report.brightness.assumptions if report.brightness else []
        ))
        _set_report(scene, lines, warnings)

        if self.visualize:
            viz.clear_collection(context, viz.COLLECTION_ANALYSIS)
            for i, fp in enumerate(footprints):
                viz.build_footprint_object(context, fp, wall, i)
                if pj.draw_frustums:
                    viz.build_frustum_object(context, fp, i)
            viz.build_gap_object(context, wall, report.gaps)
            viz.build_blend_object(context, wall, report.blend_zones)

        level = {"WARNING"} if warnings else {"INFO"}
        self.report(
            level,
            f"Coverage {report.covered_fraction * 100:.1f}% of wall area, "
            f"{report.horizontal_coverage * 100:.1f}% of the arc; "
            f"{len(report.gaps)} gap(s), {len(report.blend_zones)} blend zone(s)",
        )
        return {"FINISHED"}


def _pose_from_matrix(matrix):
    """Build a core :class:`Pose` from a Blender world matrix.

    Local +X is right, +Y is up and -Z is the optical axis, so ``forward`` is
    the negated third column.
    """
    from .core.pose import Pose

    basis = matrix.to_quaternion().to_matrix()
    origin = matrix.translation
    col_x = basis.col[0]
    col_y = basis.col[1]
    col_z = basis.col[2]
    return Pose(
        origin=(origin.x, origin.y, origin.z),
        right=(col_x.x, col_x.y, col_x.z),
        up=(col_y.x, col_y.y, col_y.z),
        forward=(-col_z.x, -col_z.y, -col_z.z),
    )


class PJ_OT_clear_analysis(Operator):
    """Delete the generated analysis overlays"""

    bl_idname = "projection.clear_analysis"
    bl_label = "Clear Analysis"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        removed = viz.clear_collection(context, viz.COLLECTION_ANALYSIS)
        context.scene.pj.report_lines.clear()
        context.scene.pj.has_report = False
        self.report({"INFO"}, f"Removed {removed} analysis object(s)")
        return {"FINISHED"}


class PJ_OT_copy_report(Operator):
    """Copy the last report to the clipboard and print it to the console"""

    bl_idname = "projection.copy_report"
    bl_label = "Copy Report"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.scene.pj.has_report

    def execute(self, context):
        text = "\n".join(entry.text for entry in context.scene.pj.report_lines)
        context.window_manager.clipboard = text
        print("\n=== Projection Planner report ===")
        print(text)
        print("=================================\n")
        self.report({"INFO"}, "Report copied to clipboard and printed to the console")
        return {"FINISHED"}


_CLASSES = (
    PJ_OT_create_curved_wall,
    PJ_OT_set_target_wall,
    PJ_OT_add_projector,
    PJ_OT_aim_at_wall,
    PJ_OT_plan_array,
    PJ_OT_analyze,
    PJ_OT_clear_analysis,
    PJ_OT_copy_report,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
