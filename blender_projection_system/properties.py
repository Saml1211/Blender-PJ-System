"""Blender property definitions for the Projection Planner.

Everything lives in ``PropertyGroup``s attached to a single pointer per ID
type, so ``unregister`` has three attributes to delete rather than twenty
loose ``bpy.types.Object.pj_*`` entries. That is what makes enable / disable /
re-enable cycles reliable.

Numbers that describe *hardware* (throw ratio, lumens, lens shift limits) are
editable. Numbers that are a *consequence* of geometry (throw distance, image
size, coverage) are written by the analysis operator and shown read-only - the
v0.1 add-on let users type a throw distance that the scene then contradicted.
"""

from __future__ import annotations

import contextlib

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Object, PropertyGroup, Scene

from .core.array import MODE_LEVEL, MODE_TILT

# ---------------------------------------------------------------------------
# Update-callback re-entry guard
# ---------------------------------------------------------------------------

_guard_depth = 0


@contextlib.contextmanager
def _no_reentry():
    """Suppress nested property-update callbacks.

    A context manager rather than a bare module flag: v0.1 set a global to
    ``True``, and any exception in between left it stuck, silently disabling
    every later update for the rest of the session.
    """
    global _guard_depth
    _guard_depth += 1
    try:
        yield _guard_depth == 1
    finally:
        _guard_depth -= 1


MOUNT_MODE_ITEMS = [
    (
        MODE_LEVEL,
        "Level + Lens Shift",
        "Keep the optical axis horizontal and shift the lens down onto the wall. "
        "No keystone, even focus - needs enough lens shift range",
        0,
    ),
    (
        MODE_TILT,
        "Tilt to Target",
        "Tilt the projector to aim at the wall without lens shift. Feasible layouts "
        "introduce keystone that must be corrected electronically",
        1,
    ),
]


# ---------------------------------------------------------------------------
# Lens scratchpad (the only genuinely bidirectional pair)
# ---------------------------------------------------------------------------


def _update_calc_distance(self, context):
    with _no_reentry() as outermost:
        if not outermost:
            return
        if self.calc_throw_ratio > 0.0:
            self.calc_width = self.calc_distance / self.calc_throw_ratio


def _update_calc_width(self, context):
    with _no_reentry() as outermost:
        if not outermost:
            return
        if self.calc_width > 0.0:
            self.calc_throw_ratio = self.calc_distance / self.calc_width


def _update_calc_throw_ratio(self, context):
    with _no_reentry() as outermost:
        if not outermost:
            return
        if self.calc_throw_ratio > 0.0:
            self.calc_width = self.calc_distance / self.calc_throw_ratio


def _is_wall_object(self, obj):
    return bool(getattr(obj, "pj_wall", None) and obj.pj_wall.is_wall)


def _is_occluder_mesh(self, obj):
    """Poll for the obstacle picker: meshes that are not the target wall.

    The target wall is excluded here as well as in the operators because a
    wall (or anything tagged as one) included in its own occluder set would
    shadow every sample point on it - a silent, plausible-looking zero
    coverage result rather than an error (ADR 0002).
    """
    return bool(
        obj
        and obj.type == "MESH"
        and not (getattr(obj, "pj_wall", None) and obj.pj_wall.is_wall)
    )


def _request_scope(self, context, scope_name: str) -> None:
    from .scene_sync import SyncScope, request_scene_sync

    owner = self.id_data
    if isinstance(owner, Scene):
        scenes = (owner,)
    elif isinstance(owner, Object):
        scenes = tuple(owner.users_scene)
    elif context is not None and context.scene is not None:
        scenes = (context.scene,)
    else:
        scenes = ()
    scope = SyncScope[scope_name]
    for scene in scenes:
        request_scene_sync(scene, scope)


def _update_wall_geometry(self, context):
    """Tag the wall for node evaluation and queue every dependent result."""
    obj = self.id_data
    if isinstance(obj, Object):
        obj.update_tag(refresh={"OBJECT"})
    _request_scope(self, context, "WALL")


def _update_wall_kind(self, context):
    obj = self.id_data
    if isinstance(obj, Object):
        from .procedural_geometry import sync_wall_kind

        sync_wall_kind(obj)
    _update_wall_geometry(self, context)


def _update_array(self, context):
    _request_scope(self, context, "ARRAY")


def _update_analysis(self, context):
    _request_scope(self, context, "ANALYSIS")


def _update_projector(self, context):
    _request_scope(self, context, "ANALYSIS")


# ---------------------------------------------------------------------------
# Property groups
# ---------------------------------------------------------------------------


class PJ_PG_ReportLine(PropertyGroup):
    """One line of the last analysis report."""

    text: StringProperty(name="Text", default="")
    kind: EnumProperty(
        name="Kind",
        items=[
            ("INFO", "Info", "Informational line"),
            ("WARNING", "Warning", "Something needs attention"),
        ],
        default="INFO",
    )


class PJ_PG_Wall(PropertyGroup):
    """Parameters of a projection wall, stored on its object.

    ``base_center`` is the object's own location, so moving the empty/mesh in
    the viewport moves the analysis with it. Rotation is intentionally not
    honoured; the operators bake the wall geometry into the mesh at identity
    rotation. ``kind`` selects which parameter set applies.
    """

    is_wall: BoolProperty(
        name="Is Projection Wall",
        description="Marks this object as a projection target surface",
        default=False,
    )
    kind: EnumProperty(
        name="Kind",
        description="Geometry of this projection wall",
        items=[
            (
                "CYLINDER",
                "Curved",
                "Vertical-axis cylindrical wall segment",
            ),
            (
                "FLAT",
                "Flat",
                "Rectangular planar wall",
            ),
            (
                "MESH",
                "Mesh",
                "Imported mesh used as-is; must be mostly frontal to the "
                "projectors (folds, overhangs and domes are rejected)",
            ),
        ],
        default="CYLINDER",
        update=_update_wall_kind,
    )
    width: FloatProperty(
        name="Width",
        description="Width of a flat wall face along its length",
        default=4.0,
        min=0.01,
        soft_max=100.0,
        unit="LENGTH",
        update=_update_wall_geometry,
    )
    yaw_deg: FloatProperty(
        name="Facing Yaw",
        description=(
            "Rotation about Z for a flat wall; 0 means the face looks "
            "toward -X, i.e. projectors sit at negative X"
        ),
        default=0.0,
        min=-360.0,
        max=360.0,
        update=_update_wall_geometry,
    )
    radius: FloatProperty(
        name="Radius",
        description="Radius of the wall's curvature",
        default=8.0,
        min=0.01,
        soft_max=100.0,
        unit="LENGTH",
        update=_update_wall_geometry,
    )
    height: FloatProperty(
        name="Height",
        description="Height of the wall surface",
        default=3.0,
        min=0.01,
        soft_max=30.0,
        unit="LENGTH",
        update=_update_wall_geometry,
    )
    arc_start_deg: FloatProperty(
        name="Arc Start",
        description="Start of the wall arc, measured from +X counter-clockwise",
        default=-45.0,
        min=-360.0,
        max=360.0,
        update=_update_wall_geometry,
    )
    arc_end_deg: FloatProperty(
        name="Arc End",
        description="End of the wall arc, measured from +X counter-clockwise",
        default=45.0,
        min=-360.0,
        max=360.0,
        update=_update_wall_geometry,
    )
    segments: IntProperty(
        name="Segments",
        description="Mesh subdivisions around the arc",
        default=48,
        min=2,
        max=512,
        update=_update_wall_geometry,
    )
    concave: BoolProperty(
        name="Concave",
        description="Projectors sit inside the arc (the usual curved-wall case)",
        default=True,
        update=_update_wall_geometry,
    )


class PJ_PG_Projector(PropertyGroup):
    """Lens and mount data for one projector, plus read-only computed results."""

    is_projector: BoolProperty(
        name="Is Projector",
        description="Marks this object as a projector",
        default=False,
    )

    # -- hardware, editable ------------------------------------------------
    throw_ratio: FloatProperty(
        name="Throw Ratio",
        description="Throw distance divided by image width (D/W) for the fitted lens",
        default=1.2,
        min=0.1,
        soft_max=10.0,
        precision=3,
        update=_update_projector,
    )
    throw_ratio_min: FloatProperty(
        name="Lens Min TR",
        description="Shortest throw ratio the fitted lens supports (0 to skip the check)",
        default=0.0,
        min=0.0,
        precision=3,
        update=_update_projector,
    )
    throw_ratio_max: FloatProperty(
        name="Lens Max TR",
        description="Longest throw ratio the fitted lens supports (0 to skip the check)",
        default=0.0,
        min=0.0,
        precision=3,
        update=_update_projector,
    )
    aspect_w: IntProperty(name="Aspect W", default=16, min=1, max=256, update=_update_projector)
    aspect_h: IntProperty(name="Aspect H", default=9, min=1, max=256, update=_update_projector)
    lumens: FloatProperty(
        name="Lumens",
        description="Rated light output. Derate it yourself for eco mode or lamp age",
        default=7000.0,
        min=0.0,
        soft_max=50000.0,
        update=_update_projector,
    )
    lens_shift_v: FloatProperty(
        name="Vertical Lens Shift",
        description=(
            "Image centre offset from the optical axis, as a fraction of image "
            "height. 0.5 puts the axis on the image edge; datasheets calling that "
            "'100%' use twice these numbers"
        ),
        default=0.0,
        min=-2.0,
        max=2.0,
        precision=3,
        update=_update_projector,
    )
    lens_shift_h: FloatProperty(
        name="Horizontal Lens Shift",
        description="Image centre offset from the axis, as a fraction of image width",
        default=0.0,
        min=-2.0,
        max=2.0,
        precision=3,
        update=_update_projector,
    )
    max_lens_shift_v: FloatProperty(
        name="Max Vertical Shift",
        description="Vertical shift limit of the fitted lens, same units as above",
        default=0.5,
        min=0.0,
        max=2.0,
        precision=3,
        update=_update_projector,
    )
    max_lens_shift_h: FloatProperty(
        name="Max Horizontal Shift",
        default=0.15,
        min=0.0,
        max=2.0,
        precision=3,
        update=_update_projector,
    )
    mount_mode: EnumProperty(
        name="Mount Mode",
        items=MOUNT_MODE_ITEMS,
        default=MODE_LEVEL,
        update=_update_projector,
    )

    # -- computed, written by the analysis operator ------------------------
    calc_throw_distance: FloatProperty(name="Throw Distance", default=0.0, unit="LENGTH")
    calc_image_width: FloatProperty(name="Image Width", default=0.0, unit="LENGTH")
    calc_image_height: FloatProperty(name="Image Height", default=0.0, unit="LENGTH")
    calc_arc_span: FloatProperty(name="Arc Covered", default=0.0, unit="LENGTH")
    calc_hit_ratio: FloatProperty(name="On Surface", default=0.0, min=0.0, max=1.0)
    calc_max_incidence_deg: FloatProperty(name="Worst Incidence", default=0.0)
    calc_mean_nits: FloatProperty(name="Mean Luminance", default=0.0)
    calc_occluded_cells: IntProperty(name="Occluded Cells", default=0)
    calc_occluded_ratio: FloatProperty(
        name="Occluded Ratio", default=0.0, min=0.0, max=1.0
    )
    has_result: BoolProperty(name="Has Result", default=False)


class PJ_PG_Occluder(PropertyGroup):
    """One user-selected obstacle object standing in the light path."""

    name: StringProperty(name="Name", default="")
    object: PointerProperty(
        name="Object",
        description="Mesh object that can block projector light",
        type=Object,
        poll=_is_occluder_mesh,
        update=_update_analysis,
    )


class PJ_PG_Scene(PropertyGroup):
    """Scene-level planning inputs and the last report."""

    target_wall: PointerProperty(
        name="Target Wall",
        description="The surface the live array and analysis are planned against",
        type=Object,
        poll=_is_wall_object,
        update=_update_array,
    )

    projector_count: IntProperty(
        name="Projectors",
        description="How many projectors to spread across the wall",
        default=3,
        min=1,
        max=24,
        update=_update_array,
    )
    overlap: FloatProperty(
        name="Overlap",
        description="Fraction of each image shared with its neighbour for edge blending",
        default=0.15,
        min=0.0,
        max=0.6,
        precision=3,
        subtype="FACTOR",
        update=_update_array,
    )
    mount_height: FloatProperty(
        name="Mount Height",
        description="Height of the projector mounting point above the world origin",
        default=3.2,
        min=0.0,
        soft_max=30.0,
        unit="LENGTH",
        update=_update_array,
    )
    image_center_height: FloatProperty(
        name="Image Centre Above Wall Base",
        description="Local height above the wall's bottom edge for the image centres",
        default=1.5,
        min=0.0,
        soft_max=30.0,
        unit="LENGTH",
        update=_update_array,
    )
    mount_mode: EnumProperty(
        name="Mount Mode", items=MOUNT_MODE_ITEMS, default=MODE_LEVEL, update=_update_array
    )

    # -- the spec used when generating an array ----------------------------
    throw_ratio: FloatProperty(
        name="Throw Ratio",
        default=1.2,
        min=0.1,
        soft_max=10.0,
        precision=3,
        update=_update_array,
    )
    aspect_w: IntProperty(name="Aspect W", default=16, min=1, max=256, update=_update_array)
    aspect_h: IntProperty(name="Aspect H", default=9, min=1, max=256, update=_update_array)
    lumens: FloatProperty(
        name="Lumens", default=7000.0, min=0.0, soft_max=50000.0, update=_update_array
    )
    max_lens_shift_v: FloatProperty(
        name="Max Vertical Shift", default=0.5, min=0.0, max=2.0, update=_update_array
    )

    # -- analysis settings --------------------------------------------------
    samples: IntProperty(
        name="Footprint Samples",
        description="Rays cast per axis across each image. Higher is slower and more exact",
        default=9,
        min=3,
        max=41,
        update=_update_array,
    )
    grid_s: IntProperty(
        name="Coverage Grid (arc)",
        default=120,
        min=8,
        max=600,
        update=_update_analysis,
    )
    grid_z: IntProperty(
        name="Coverage Grid (height)",
        default=24,
        min=4,
        max=200,
        update=_update_analysis,
    )
    blend_model: EnumProperty(
        name="Blend Model",
        description=(
            "How overlapping projectors' light combines. Raw adds it all up "
            "(no processor in the chain); linear ramp models what an "
            "edge-blending processor does across each overlap"
        ),
        items=[
            (
                "RAW",
                "Raw (additive)",
                "Overlapping images simply add - correct when no blending processor is used",
            ),
            (
                "LINEAR_RAMP",
                "Linear blend ramp",
                "Across each overlap one image ramps down while the other ramps up, "
                "as an edge-blending processor would",
            ),
        ],
        default="RAW",
        update=_update_analysis,
    )
    screen_gain: FloatProperty(
        name="Screen Gain",
        description="Gain of the wall finish. 1.0 is a matte white Lambertian surface",
        default=1.0,
        min=0.05,
        max=5.0,
        precision=2,
        update=_update_analysis,
    )
    draw_frustums: BoolProperty(
        name="Draw Frustums",
        description="Include lens-to-corner edges in the analysis visualisation",
        default=True,
        update=_update_analysis,
    )

    # -- occlusion (obstacles in the light path) ----------------------------
    occluders: CollectionProperty(
        type=PJ_PG_Occluder,
        name="Obstacles",
        description="Mesh objects that may block projector light",
    )
    occluder_index: IntProperty(name="Active Obstacle Index", default=0)
    occluder_collection: PointerProperty(
        name="Obstacle Collection",
        description="Collection whose mesh objects are all treated as obstacles",
        type=bpy.types.Collection,
        update=_update_analysis,
    )
    show_occlusion_overlay: BoolProperty(
        name="Show Shadow Overlay",
        description="Draw red overlay where light is blocked by obstacles",
        default=True,
        update=_update_analysis,
    )

    # -- lens scratchpad ----------------------------------------------------
    calc_distance: FloatProperty(
        name="Distance",
        default=6.0,
        min=0.01,
        unit="LENGTH",
        precision=3,
        update=_update_calc_distance,
    )
    calc_width: FloatProperty(
        name="Image Width",
        default=5.0,
        min=0.01,
        unit="LENGTH",
        precision=3,
        update=_update_calc_width,
    )
    calc_throw_ratio: FloatProperty(
        name="Throw Ratio",
        default=1.2,
        min=0.01,
        precision=3,
        update=_update_calc_throw_ratio,
    )

    # -- last report --------------------------------------------------------
    report_lines: CollectionProperty(type=PJ_PG_ReportLine)
    has_report: BoolProperty(default=False)
    live_error: StringProperty(
        name="Live Update Error",
        description="Most recent automatic planning or analysis error",
        default="",
    )


_CLASSES = (
    PJ_PG_ReportLine,
    PJ_PG_Wall,
    PJ_PG_Occluder,
    PJ_PG_Projector,
    PJ_PG_Scene,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    Object.pj_wall = PointerProperty(type=PJ_PG_Wall)
    Object.pj_projector = PointerProperty(type=PJ_PG_Projector)
    Scene.pj = PointerProperty(type=PJ_PG_Scene)


def unregister():
    for attr, owner in (("pj_wall", Object), ("pj_projector", Object), ("pj", Scene)):
        if hasattr(owner, attr):
            delattr(owner, attr)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
