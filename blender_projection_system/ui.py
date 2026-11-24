"""Sidebar panels for the Projection Planner.

Panels are laid out in workflow order: target, projectors, analysis, report.
Every operator the add-on registers is reachable from here - a static test in
``tests/test_addon_contract.py`` enforces both directions of that.
"""

from __future__ import annotations

import bpy
from bpy.types import Panel, UIList

from . import properties
from . import visualization as viz
from .core.errors import ProjectionError
from .core.photometry import luminance_nits, nominal_screen_illuminance
from .core.pixels import (
    evaluate_scenario,
    fmt_mm,
    fmt_pitch,
    fmt_size,
    scenario_rows,
    shift_for_bottom_edge,
)
from .core.throw import ProjectorSpec, aspect_ratio, default_resolution

#: Saved scenarios shown side by side in the compare table at once.
COMPARE_COLUMNS = 4

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
        col.operator("projection.create_flat_wall", icon="MESH_PLANE")
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
        box.label(
            text=wall_obj.name, icon="MESH_PLANE" if props.kind == "FLAT" else "MESH_CYLINDER"
        )
        col = box.column(align=True)
        if props.kind == "FLAT":
            col.prop(props, "width")
            col.prop(props, "yaw_deg")
            col.prop(props, "height")
            col.prop(props, "segments")
        elif props.kind == "CYLINDER":
            col.prop(props, "radius")
            row = col.row(align=True)
            row.prop(props, "arc_start_deg", text="Arc Start")
            row.prop(props, "arc_end_deg", text="End")
            col.prop(props, "concave")
            col.prop(props, "height")
            col.prop(props, "segments")
        else:
            col.label(text="Imported evaluated mesh", icon="MODIFIER")

        try:
            surface = viz.wall_from_object(wall_obj)
        except ProjectionError as exc:
            box.label(text=str(exc), icon="ERROR")
            return
        info = box.column(align=True)
        info.label(text=f"Arc length: {fmt_mm(surface.arc_length)}")
        info.label(text=f"Surface area: {surface.area:.1f} m2")
        if props.kind != "MESH":
            info.label(text="Geometry updates live.", icon="DRIVER")


class PJ_PT_projectors(_Base):
    """Step 2: place projectors, individually or as a planned array."""

    bl_label = "2. Projectors"
    bl_idname = "PJ_PT_projectors"

    def draw(self, context):
        layout = self.layout
        pj = context.scene.pj

        box = layout.box()
        box.label(text="Hardware Library", icon="BOOK")
        col = box.column(align=True)
        col.prop(pj, "spec_manufacturer", text="Brand")
        col.prop(pj, "spec_model", text="Model")
        col.prop(pj, "spec_lens", text="Lens")
        row = col.row(align=True)
        row.operator("projection.apply_preset_spec", text="Apply Preset", icon="CHECKMARK")
        row.operator("projection.import_spec_csv", text="Import CSV", icon="IMPORT")
        if pj.throw_ratio_min > 0.0 and not (
            pj.throw_ratio_min <= pj.throw_ratio <= pj.throw_ratio_max
        ):
            warn_row = col.row()
            warn_row.alert = True
            warn_row.label(
                text=(
                    f"Throw ratio outside lens range "
                    f"[{pj.throw_ratio_min:.2f}, {pj.throw_ratio_max:.2f}]"
                ),
                icon="ERROR",
            )

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
        col.label(text="Array and coverage update automatically.", icon="DRIVER")
        col.operator("projection.plan_array", icon="FILE_REFRESH")

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
        row = col.row(align=True)
        row.prop(p, "res_x", text="Res")
        row.label(text="x")
        row.prop(p, "res_y", text="")
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

        if p.model:
            box = layout.box()
            box.label(
                text=f"Model: {p.manufacturer} {p.model} ({p.lens_model})",
                icon="CAMERA_DATA",
            )
            if p.verified:
                box.label(text="Verified manufacturer datasheet", icon="CHECKMARK")

        if not p.has_result:
            layout.label(text="Waiting for live analysis results", icon="INFO")
            return

        box = layout.box()
        box.label(text="Calculated", icon="DRIVER")
        col = box.column(align=True)
        col.enabled = False
        col.prop(p, "calc_throw_distance")
        col.prop(p, "calc_image_width")
        col.prop(p, "calc_image_height")
        col.prop(p, "calc_arc_span")
        res_x, res_y = (
            (p.res_x, p.res_y) if p.res_x > 0 and p.res_y > 0
            else default_resolution(p.aspect_w, p.aspect_h)
        )
        assumed = "" if p.res_x > 0 and p.res_y > 0 else " (assumed from aspect)"
        pix = box.column(align=True)
        pix.label(text=f"Native: {res_x} x {res_y} px{assumed}", icon="TEXTURE")
        pix.label(
            text=f"Image on target: {fmt_size(p.calc_image_width, p.calc_image_height)}"
        )
        if p.calc_pixel_pitch > 0.0:
            pix.label(
                text=f"Pitch: {fmt_pitch(p.calc_pixel_pitch)} mean, "
                f"{1.0 / p.calc_pixel_pitch:.0f} px/m"
            )
            pix.label(
                text=f"Local pitch: {fmt_pitch(p.calc_pixel_pitch_min)} to "
                f"{fmt_pitch(p.calc_pixel_pitch_max)}"
            )
        box.label(text=f"On surface: {p.calc_hit_ratio * 100:.0f}%")
        box.label(text=f"Worst incidence: {p.calc_max_incidence_deg:.1f} deg")
        if p.calc_mean_nits > 0.0:
            box.label(text=f"Mean luminance: {p.calc_mean_nits:.0f} nits")
        if p.calc_occluded_cells > 0:
            row = box.row()
            row.alert = True
            row.label(
                text=(
                    f"Occluded: {p.calc_occluded_cells} cells "
                    f"({p.calc_occluded_ratio * 100:.1f}%)"
                ),
                icon="ERROR",
            )


class PJ_PT_analysis(_Base):
    """Step 3: run the calculation and control the overlay."""

    bl_label = "3. Analysis"
    bl_idname = "PJ_PT_analysis"

    def draw(self, context):
        layout = self.layout
        pj = context.scene.pj

        if pj.live_error:
            error = layout.box()
            error.alert = True
            error.label(text="Live update paused on the last valid scene", icon="ERROR")
            error.label(text=pj.live_error)
        else:
            layout.label(text="Coverage is live", icon="DRIVER")

        col = layout.column(align=True)
        col.operator("projection.analyze", icon="FILE_REFRESH")
        col.operator("projection.clear_analysis", icon="TRASH")

        if pj.has_report and pj.canvas_projectors > 0:
            canvas = layout.box()
            canvas.label(text="Blended Canvas on Target", icon="TEXTURE")
            c_col = canvas.column(align=True)
            c_col.label(
                text=f"{pj.canvas_px_x} x {pj.canvas_px_y} px from "
                f"{pj.canvas_projectors} projector(s)"
            )
            if pj.canvas_width > 0.0:
                c_col.label(
                    text=f"Width {fmt_mm(pj.canvas_width)}, "
                    f"{pj.canvas_px_x / (pj.canvas_width * 1000.0):.3f} px/mm"
                )
            c_col.label(text=f"{pj.canvas_overlap_px} px inside blend zones")

        box = layout.box()
        box.label(text="Settings", icon="PREFERENCES")
        col = box.column(align=True)
        col.prop(pj, "samples")
        row = col.row(align=True)
        row.prop(pj, "grid_s", text="Grid Arc")
        row.prop(pj, "grid_z", text="Height")
        col.prop(pj, "screen_gain")
        col.prop(pj, "gain_model", text="Gain Model")
        if pj.gain_model != "LAMBERTIAN":
            g_col = col.column(align=True)
            g_col.prop(pj, "gain_half_angle_deg", text="Half-Gain Angle")
            g_col.prop(pj, "gain_off_axis", text="Off-Axis Floor")
            g_col.label(text="RP 94 parametric idealisation;", icon="INFO")
            g_col.label(text="medium confidence, not vendor-measured")
        col.prop(pj, "blend_model", text="Overlap")
        if pj.blend_model == "GAMMA_RAMP":
            col.prop(pj, "blend_gamma", text="Blend Gamma")
        col.prop(pj, "enable_nine_point")
        col.prop(pj, "draw_frustums")

        derate_box = box.box()
        derate_box.prop(pj, "use_derate_chain", text="Lumens Derate Chain")
        if pj.use_derate_chain:
            d_col = derate_box.column(align=True)
            d_col.prop(pj, "derate_production_tolerance", text="Prod. Limit (ISO 21118)")
            d_col.prop(pj, "derate_picture_mode", text="Picture Mode")
            d_col.prop(pj, "derate_aging", text="Aging Factor")

        contrast_box = box.box()
        contrast_box.label(text="Ambient Light & Contrast", icon="LIGHT")
        c_col = contrast_box.column(align=True)
        c_col.prop(pj, "ambient_lux", text="Ambient (lux)")
        c_col.prop(pj, "iscr_category", text="ISCR Category")
        if pj.iscr_category != "NONE":
            c_col.prop(pj, "target_contrast_ratio", text="Target Ratio (:1)")
            c_col.label(text="Structure per ANSI/AVIXA V201.01:2021;", icon="INFO")
            c_col.label(text="this tool does not certify compliance.")

        cal_box = box.box()
        cal_box.prop(pj, "enable_calibration", text="On-Site Calibration (>=3 readings)")
        if pj.enable_calibration:
            cal_col = cal_box.column(align=True)
            if len(pj.calibration_readings) > 0:
                cal_col.template_list(
                    "UI_UL_list",
                    "PJ_UL_readings",
                    pj,
                    "calibration_readings",
                    pj,
                    "calibration_index",
                    rows=min(len(pj.calibration_readings), 4),
                )
            else:
                cal_col.label(text="No readings recorded yet", icon="INFO")
            row = cal_col.row(align=True)
            row.operator("projection.add_reading_cursor", text="Add at Cursor", icon="ADD")
            row.operator("projection.remove_reading", text="Remove", icon="REMOVE")
            row.operator("projection.clear_readings", text="Clear", icon="TRASH")
            if 0 <= pj.calibration_index < len(pj.calibration_readings):
                item = pj.calibration_readings[pj.calibration_index]
                cal_col.prop(item, "label", text="Label")
                row = cal_col.row(align=True)
                row.prop(item, "s", text="Arc s")
                row.prop(item, "z", text="Height")
                cal_col.prop(item, "measured_lux", text="Measured (lux)")
            cal_col.label(text="s = arc from wall left edge, z = height above base", icon="INFO")
            cal_col.label(text="Report shows the fitted factor and residual.", icon="INFO")

        discas_box = box.box()
        discas_box.prop(pj, "enable_discas", text="DISCAS Viewer Audit (V202.01)")
        if pj.enable_discas:
            d_col = discas_box.column(align=True)
            d_col.prop(pj, "farthest_viewer_distance", text="Farthest Viewer")
            row = d_col.row(align=True)
            row.prop(pj, "discas_element_height_pct", text="BDM %EH")
            row.prop(pj, "discas_vertical_resolution", text="ADM V-Res")
            discas_box.label(text="Structure per ANSI/INFOCOMM V202.01", icon="INFO")

        box = layout.box()
        box.label(text="Obstacles / Occlusion", icon="SNAP_VOLUME")
        col = box.column(align=True)
        col.prop(pj, "occluder_collection", text="Collection")
        row = col.row(align=True)
        row.operator("projection.add_occluder", text="Add Selected", icon="ADD")
        row.operator("projection.remove_occluder", text="Remove", icon="REMOVE")
        row.operator("projection.clear_occluders", text="Clear", icon="TRASH")
        if len(pj.occluders) > 0:
            col.template_list(
                "UI_UL_list",
                "PJ_UL_occluders",
                pj,
                "occluders",
                pj,
                "occluder_index",
                rows=min(len(pj.occluders), 4),
            )
        else:
            col.label(text="No obstacles: every projector sees the wall", icon="INFO")
        col.prop(pj, "show_occlusion_overlay", text="Draw Shadows")


class PJ_PT_report(_Base):
    """Step 4: read what the calculation actually found."""

    bl_label = "4. Report"
    bl_idname = "PJ_PT_report"

    def draw(self, context):
        layout = self.layout
        pj = context.scene.pj

        if not pj.has_report:
            layout.label(text="Waiting for the live report", icon="INFO")
            return

        row = layout.row(align=True)
        row.operator("projection.copy_report", text="Copy Text", icon="COPYDOWN")
        row.operator("projection.export_analysis", text="Export JSON / CSV", icon="EXPORT")
        row = layout.row(align=True)
        row.operator(
            "projection.export_warp",
            text="Export Warp Grids",
            icon="MESH_GRID",
        )

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


class PJ_UL_scenarios(UIList):
    """Saved calculator scenarios, one compact line each."""

    bl_idname = "PJ_UL_scenarios"

    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _propname, _index):
        row = layout.row(align=True)
        row.prop(item, "name", text="", emboss=False)
        row.label(text=f"{item.res_x}x{item.res_y}  TR {item.throw_ratio:.2f}")


class PJ_PT_calculator(_Base):
    """Trial image size, pixel and placement scenarios without moving the rig."""

    bl_label = "Image & Pixel Calculator"
    bl_idname = "PJ_PT_calculator"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        pj = context.scene.pj

        res_x, res_y, res_label = properties.calculator_resolution(pj)
        tr_min, tr_max, _max_v, _max_h, lens_label = properties.calculator_lens(pj)

        box = layout.box()
        box.label(text="Signal", icon="TEXTURE")
        col = box.column(align=True)
        col.prop(pj, "calc_res_preset", text="")
        if pj.calc_res_preset == "CUSTOM":
            row = col.row(align=True)
            row.prop(pj, "calc_res_x", text="X")
            row.prop(pj, "calc_res_y", text="Y")
        col.label(text=f"{res_x} x {res_y} px, {aspect_ratio(res_x, res_y):.3f}:1 ({res_label})")
        lens_range = f"TR {tr_min:.2f}-{tr_max:.2f}:1" if tr_min > 0.0 else "no TR range"
        col.label(text=f"Lens: {lens_label}, {lens_range}")

        box = layout.box()
        box.label(text="Throw and Image (edit one, the rest follow)", icon="CAMERA_DATA")
        col = box.column(align=True)
        col.prop(pj, "calc_distance")
        col.prop(pj, "calc_throw_ratio")
        col.prop(pj, "calc_width")
        col.prop(pj, "calc_height")
        col.prop(pj, "calc_diagonal")

        box = layout.box()
        box.label(text="Height, Viewer and Array", icon="EMPTY_SINGLE_ARROW")
        col = box.column(align=True)
        col.prop(pj, "calc_lens_height")
        col.prop(pj, "calc_shift_v")
        col.prop(pj, "calc_check_target")
        if pj.calc_check_target:
            col.prop(pj, "calc_target_bottom")
            col.prop(pj, "calc_target_height")
        col.separator()
        col.prop(pj, "calc_viewing_distance")
        row = col.row(align=True)
        row.prop(pj, "calc_projector_count")
        row.prop(pj, "calc_overlap")

        try:
            inputs = properties.calculator_inputs(pj)
            result = evaluate_scenario(inputs)
        except ProjectionError as exc:
            layout.label(text=str(exc), icon="ERROR")
            return

        out = layout.box()
        out.label(text="Results", icon="DRIVER")
        o_col = out.column(align=True)
        img = result.image
        o_col.label(text=f"Image {fmt_size(img.width, img.height)}, diag {fmt_mm(img.diagonal)}")
        o_col.label(text=f"Pitch {fmt_pitch(result.pitch)}, {result.pixels_per_metre:.0f} px/m")
        o_col.label(
            text=f"Image AFF: bottom {fmt_mm(result.extent.bottom)}, top {fmt_mm(result.extent.top)}"
        )
        if pj.calc_check_target:
            shift = shift_for_bottom_edge(inputs.lens_height, img.height, inputs.target_bottom)
            o_col.label(text=f"Shift for screen bottom edge: {shift:+.3f}")
        o_col.label(text=f"1-arcmin (20/20) distance: {fmt_mm(result.one_arcminute_distance)}")
        if inputs.viewing_distance > 0.0:
            o_col.label(text=f"Viewer: {result.pixels_per_degree:.1f} px/deg")
        canvas = result.canvas
        if canvas.projectors > 1:
            o_col.label(
                text=f"Canvas {canvas.pixels_x} x {canvas.pixels_y} px, {fmt_mm(canvas.width)}, "
                f"{canvas.pixels_per_metre / 1000.0:.3f} px/mm"
            )
        if pj.lumens > 0:
            spec = ProjectorSpec(
                throw_ratio=img.throw_ratio,
                aspect_w=res_x,
                aspect_h=res_y,
                lumens=pj.lumens,
            )
            lux = nominal_screen_illuminance(spec, img.width * img.height)
            o_col.label(
                text=f"{lux:.0f} lux, {luminance_nits(lux, pj.screen_gain):.0f} nits "
                "(flat screen, no ambient)"
            )
        if result.warnings:
            warn = layout.box()
            warn.alert = True
            for text in result.warnings:
                warn.label(text=text, icon="ERROR")

        self._draw_scenarios(layout, pj)

    @staticmethod
    def _draw_scenarios(layout, pj):
        box = layout.box()
        box.label(text="Scenarios", icon="PRESET")
        row = box.row(align=True)
        row.prop(pj, "scenario_name", text="")
        row.operator("projection.save_scenario", text="Save", icon="ADD")
        if len(pj.scenarios) == 0:
            box.label(text="Save a scenario to compare it", icon="INFO")
            return
        box.template_list(
            "PJ_UL_scenarios",
            "",
            pj,
            "scenarios",
            pj,
            "scenario_index",
            rows=min(len(pj.scenarios), 4),
        )
        row = box.row(align=True)
        row.operator("projection.load_scenario", text="Load", icon="IMPORT")
        row.operator("projection.remove_scenario", text="Remove", icon="REMOVE")
        row.operator("projection.export_scenarios", text="CSV", icon="EXPORT")

        # Side by side: a window of saved scenarios around the active one.
        first = max(0, min(pj.scenario_index, len(pj.scenarios) - COMPARE_COLUMNS))
        shown = list(pj.scenarios)[first : first + COMPARE_COLUMNS]
        tables = []
        for item in shown:
            try:
                inputs = properties.scenario_inputs(item)
                tables.append(scenario_rows(inputs, evaluate_scenario(inputs)))
            except ProjectionError as exc:
                tables.append([("Error", str(exc))])
        compare = box.box()
        grid = compare.grid_flow(
            row_major=True, columns=len(shown) + 1, even_columns=False, align=True
        )
        grid.label(text="")
        for item in shown:
            grid.label(text=item.name)
        for index, (label, _value) in enumerate(tables[0]):
            if label == "Warnings":
                continue
            grid.label(text=label)
            for table in tables:
                grid.label(text=table[index][1] if index < len(table) else "")
        for item, table in zip(shown, tables, strict=True):
            warnings = dict(table).get("Warnings", "none")
            if warnings != "none":
                row = compare.row()
                row.alert = True
                row.label(text=f"{item.name}: {warnings}", icon="ERROR")


_CLASSES = (
    PJ_UL_scenarios,
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
