"""Sidebar panels for the Projection Planner.

Panels are laid out in workflow order: target, projectors, analysis, report.
Every operator the add-on registers is reachable from here - a static test in
``tests/test_addon_contract.py`` enforces both directions of that.
"""

from __future__ import annotations

import bpy
from bpy.types import Panel

from . import visualization as viz
from .core.errors import ProjectionError
from .core.photometry import luminance_nits, nominal_screen_illuminance
from .core.throw import ImageSize, ProjectorSpec, aspect_ratio, image_height_from_width

CATEGORY = "Projection"


def _projector_objects(context):
    return [obj for obj in context.scene.objects if obj.pj_projector.is_projector]


class _Base(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY


class PJ_PT_target(_Base):
    """Step 1: define the surface being projected onto."""

    bl_label = "1. Projection Target"
    bl_idname = "PJ_PT_target"

    def draw(self, context):
        layout = self.layout
        pj = context.scene.pj

        col = layout.column(align=True)
        col.operator("projection.create_curved_wall", icon="MESH_CYLINDER")
        col.operator("projection.set_target_wall", icon="EYEDROPPER")

        layout.prop(pj, "target_wall")

        wall_obj = pj.target_wall
        if wall_obj is None:
            box = layout.box()
            box.label(text="No target wall selected", icon="INFO")
            box.label(text="Create one to begin planning.")
            return

        props = wall_obj.pj_wall
        box = layout.box()
        box.label(text=wall_obj.name, icon="MESH_CYLINDER")
        col = box.column(align=True)
        col.prop(props, "radius")
        col.prop(props, "height")
        row = col.row(align=True)
        row.prop(props, "arc_start_deg", text="Arc Start")
        row.prop(props, "arc_end_deg", text="End")
        col.prop(props, "concave")

        try:
            arc_length = viz.wall_from_object(wall_obj).arc_length
        except ProjectionError as exc:
            box.label(text=str(exc), icon="ERROR")
            return
        info = box.column(align=True)
        info.label(text=f"Arc length: {arc_length:.2f} m")
        info.label(text=f"Surface area: {arc_length * props.height:.1f} m2")
        info.label(text="Mesh updates on the next plan or analysis.", icon="INFO")


class PJ_PT_projectors(_Base):
    """Step 2: place projectors, individually or as a planned array."""

    bl_label = "2. Projectors"
    bl_idname = "PJ_PT_projectors"

    def draw(self, context):
        layout = self.layout
        pj = context.scene.pj

        box = layout.box()
        box.label(text="Lens & Output", icon="CAMERA_DATA")
        col = box.column(align=True)
        col.prop(pj, "throw_ratio")
        row = col.row(align=True)
        row.prop(pj, "aspect_w", text="Aspect")
        row.label(text=":")
        row.prop(pj, "aspect_h", text="")
        col.prop(pj, "lumens")
        col.prop(pj, "max_lens_shift_v")

        box = layout.box()
        box.label(text="Mounting", icon="CON_TRACKTO")
        col = box.column(align=True)
        col.prop(pj, "mount_mode", text="")
        col.prop(pj, "mount_height")
        col.prop(pj, "image_center_height")

        box = layout.box()
        box.label(text="Array Layout", icon="MOD_ARRAY")
        col = box.column(align=True)
        col.prop(pj, "projector_count")
        col.prop(pj, "overlap")
        col.separator()
        col.operator("projection.plan_array", icon="MOD_ARRAY")

        col = layout.column(align=True)
        col.operator("projection.add_projector", icon="ADD")
        col.operator("projection.aim_at_wall", icon="TRACKER")

        count = len(_projector_objects(context))
        layout.label(text=f"{count} projector(s) in scene", icon="OUTLINER_OB_CAMERA")


class PJ_PT_selected_projector(_Base):
    """Per-projector detail for whatever is active."""

    bl_label = "Selected Projector"
    bl_idname = "PJ_PT_selected_projector"
    bl_parent_id = "PJ_PT_projectors"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.pj_projector.is_projector

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        p = obj.pj_projector

        layout.label(text=obj.name, icon="CAMERA_DATA")
        col = layout.column(align=True)
        col.prop(p, "throw_ratio")
        row = col.row(align=True)
        row.prop(p, "throw_ratio_min", text="Lens TR Min")
        row.prop(p, "throw_ratio_max", text="Max")
        row = col.row(align=True)
        row.prop(p, "aspect_w", text="Aspect")
        row.label(text=":")
        row.prop(p, "aspect_h", text="")
        col.prop(p, "lumens")

        box = layout.box()
        box.label(text="Lens Shift (fraction of image size)")
        col = box.column(align=True)
        col.prop(p, "lens_shift_v")
        col.prop(p, "lens_shift_h")
        row = col.row(align=True)
        row.prop(p, "max_lens_shift_v", text="Limit V")
        row.prop(p, "max_lens_shift_h", text="H")
        if abs(p.lens_shift_v) > p.max_lens_shift_v:
            box.label(text="Vertical shift exceeds the lens limit", icon="ERROR")
        if abs(p.lens_shift_h) > p.max_lens_shift_h:
            box.label(text="Horizontal shift exceeds the lens limit", icon="ERROR")

        if not p.has_result:
            layout.label(text="Run Calculate Coverage for results", icon="INFO")
            return

        box = layout.box()
        box.label(text="Calculated", icon="DRIVER")
        col = box.column(align=True)
        col.enabled = False
        col.prop(p, "calc_throw_distance")
        col.prop(p, "calc_image_width")
        col.prop(p, "calc_image_height")
        col.prop(p, "calc_arc_span")
        box.label(text=f"On surface: {p.calc_hit_ratio * 100:.0f}%")
        box.label(text=f"Worst incidence: {p.calc_max_incidence_deg:.1f} deg")
        if p.calc_mean_nits > 0.0:
            box.label(text=f"Mean luminance: {p.calc_mean_nits:.0f} nits")


class PJ_PT_analysis(_Base):
    """Step 3: run the calculation and control the overlay."""

    bl_label = "3. Analysis"
    bl_idname = "PJ_PT_analysis"

    def draw(self, context):
        layout = self.layout
        pj = context.scene.pj

        col = layout.column(align=True)
        col.scale_y = 1.4
        col.operator("projection.analyze", icon="SHADERFX")

        col = layout.column(align=True)
        col.operator("projection.clear_analysis", icon="TRASH")

        box = layout.box()
        box.label(text="Settings", icon="PREFERENCES")
        col = box.column(align=True)
        col.prop(pj, "samples")
        row = col.row(align=True)
        row.prop(pj, "grid_s", text="Grid Arc")
        row.prop(pj, "grid_z", text="Height")
        col.prop(pj, "screen_gain")
        col.prop(pj, "draw_frustums")


class PJ_PT_report(_Base):
    """Step 4: read what the calculation actually found."""

    bl_label = "4. Report"
    bl_idname = "PJ_PT_report"

    def draw(self, context):
        layout = self.layout
        pj = context.scene.pj

        if not pj.has_report:
            layout.label(text="No results yet", icon="INFO")
            layout.label(text="Run Calculate Coverage.")
            return

        layout.operator("projection.copy_report", icon="COPYDOWN")

        info = layout.box()
        warn = None
        for entry in pj.report_lines:
            if entry.kind == "WARNING":
                if warn is None:
                    warn = layout.box()
                    warn.label(text="Warnings", icon="ERROR")
                warn.label(text=entry.text)
            else:
                info.label(text=entry.text)


class PJ_PT_calculator(_Base):
    """A standalone throw calculator, independent of the scene."""

    bl_label = "Lens Calculator"
    bl_idname = "PJ_PT_calculator"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        pj = context.scene.pj

        layout.label(text="Edit any two; the third follows.")
        col = layout.column(align=True)
        col.prop(pj, "calc_distance")
        col.prop(pj, "calc_width")
        col.prop(pj, "calc_throw_ratio")

        if pj.aspect_h > 0 and pj.calc_width > 0:
            aspect = aspect_ratio(pj.aspect_w, pj.aspect_h)
            height = image_height_from_width(pj.calc_width, aspect)
            image = ImageSize(pj.calc_width, height)
            box = layout.box()
            box.label(text=f"Image height: {height:.3f} m")
            box.label(
                text=f"Diagonal: {image.diagonal:.3f} m ({image.diagonal * 39.3701:.0f} in)"
            )
            if pj.lumens > 0:
                spec = ProjectorSpec(
                    throw_ratio=pj.calc_throw_ratio,
                    aspect_w=pj.aspect_w,
                    aspect_h=pj.aspect_h,
                    lumens=pj.lumens,
                )
                lux = nominal_screen_illuminance(spec, image.area)
                box.label(text=f"Mean illuminance: {lux:.0f} lux")
                box.label(
                    text=f"Mean luminance: {luminance_nits(lux, pj.screen_gain):.0f} nits"
                )
            box.label(text="Flat screen, no ambient light.", icon="INFO")


_CLASSES = (
    PJ_PT_target,
    PJ_PT_projectors,
    PJ_PT_selected_projector,
    PJ_PT_analysis,
    PJ_PT_report,
    PJ_PT_calculator,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
