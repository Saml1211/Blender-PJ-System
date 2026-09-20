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
        obj and obj.type == "MESH" and not (getattr(obj, "pj_wall", None) and obj.pj_wall.is_wall)
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
# Hardware spec library pickers (increment #2)
# ---------------------------------------------------------------------------

#: Models imported from a user CSV during this Blender session. They overlay
#: the bundled rows by (manufacturer, model) key. Deliberately not persisted:
#: a saved .blend silently referring to a missing CSV would misreport
#: hardware, so re-importing after reopening is the honest path.
_SESSION_MODELS: list = []


def set_session_library(models) -> None:
    """Replace the session spec-library overlay with ``models``."""
    _SESSION_MODELS.clear()
    _SESSION_MODELS.extend(models)


def session_library():
    """The bundled library overlaid with any user-imported session rows.

    User rows win on (manufacturer, model) so a corrected CSV can replace a
    bundled entry without editing the add-on.
    """
    from .core.specs import SpecLibrary, load_builtin_library

    try:
        builtin = load_builtin_library()
    except Exception:
        builtin = SpecLibrary(models=[])
    merged = {(m.manufacturer.lower(), m.model.lower()): m for m in builtin.models}
    for entry in _SESSION_MODELS:
        merged[(entry.manufacturer.lower(), entry.model.lower())] = entry
    return SpecLibrary(models=list(merged.values()))


def _spec_manufacturer_items(self, context):
    lib = session_library()
    return [(m, m, f"Projectors from {m}", i) for i, m in enumerate(lib.all_manufacturers())]


def _spec_model_items(self, context):
    lib = session_library()
    mfr = getattr(self, "spec_manufacturer", "")
    models = lib.models_for_manufacturer(mfr)
    if not models and lib.models:
        models = lib.models_for_manufacturer(lib.all_manufacturers()[0])
    return [
        (m.model, m.model, f"{m.lumens:.0f} lm, {m.aspect_w}:{m.aspect_h}", i)
        for i, m in enumerate(models)
    ]


def _spec_lens_items(self, context):
    lib = session_library()
    mfr = getattr(self, "spec_manufacturer", "")
    model_name = getattr(self, "spec_model", "")
    model = lib.get_model(mfr, model_name)
    if model is None and lib.models:
        model = lib.models[0]
    lenses = model.lenses if model else ()
    return [
        (
            lens.model,
            lens.model,
            f"TR {lens.throw_ratio_min:.2f}-{lens.throw_ratio_max:.2f}:1",
            i,
        )
        for i, lens in enumerate(lenses)
    ]


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

    # -- provenance metadata from the spec library (core/specs.py) ---------
    # Written by apply_spec_to_object; describes the *stated* hardware only
    # and never alters a calculation (ADR 0002).
    manufacturer: StringProperty(name="Manufacturer", default="")
    model: StringProperty(name="Model", default="")
    lens_model: StringProperty(name="Lens", default="")
    native_contrast: FloatProperty(
        name="Native Contrast",
        description="Native (not dynamic) contrast ratio of the projector body",
        default=2000.0,
        min=1.0,
    )
    lens_transmission: FloatProperty(
        name="Lens Transmission",
        description="Fraction of projector light the fitted lens delivers",
        default=1.0,
        min=0.01,
        max=1.0,
        precision=3,
    )
    source_url: StringProperty(name="Source URL", default="")
    verified: BoolProperty(
        name="Verified Spec",
        description="Numbers transcribed from the cited source, not measured",
        default=False,
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
    calc_occluded_ratio: FloatProperty(name="Occluded Ratio", default=0.0, min=0.0, max=1.0)
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
    max_lens_shift_h: FloatProperty(
        name="Max Horizontal Shift", default=0.15, min=0.0, max=2.0, update=_update_array
    )
    throw_ratio_min: FloatProperty(
        name="Lens Min TR",
        description="Shortest throw ratio the fitted lens supports (0 to skip the check)",
        default=0.0,
        min=0.0,
        precision=3,
    )
    throw_ratio_max: FloatProperty(
        name="Lens Max TR",
        description="Longest throw ratio the fitted lens supports (0 to skip the check)",
        default=0.0,
        min=0.0,
        precision=3,
    )

    # -- hardware spec library pickers and applied provenance ---------------
    spec_manufacturer: EnumProperty(name="Manufacturer", items=_spec_manufacturer_items)
    spec_model: EnumProperty(name="Model", items=_spec_model_items)
    spec_lens: EnumProperty(name="Lens", items=_spec_lens_items)
    manufacturer: StringProperty(name="Manufacturer", default="")
    model: StringProperty(name="Model", default="")
    lens_model: StringProperty(name="Lens", default="")
    native_contrast: FloatProperty(default=2000.0, min=1.0)
    lens_transmission: FloatProperty(default=1.0, min=0.01, max=1.0, precision=3)
    source_url: StringProperty(default="")
    verified: BoolProperty(default=False)

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
                "Across each overlap one image ramps down while the other ramps up "
                "with linear weighting (gamma = 1.0)",
            ),
            (
                "GAMMA_RAMP",
                "Gamma blend ramp",
                "Complementary soft-edge ramps shaped with a custom gamma exponent "
                "(Dataton WATCHOUT convention)",
            ),
        ],
        default="RAW",
        update=_update_analysis,
    )
    blend_gamma: FloatProperty(
        name="Blend Gamma",
        description=(
            "Soft-edge blend gamma exponent (default 1.0 per Dataton WATCHOUT convention; "
            "range 0.5 to 1.5). Shapes the transition to compensate for optical/display response"
        ),
        default=1.0,
        min=0.5,
        max=1.5,
        precision=2,
        update=_update_analysis,
    )
    use_derate_chain: BoolProperty(
        name="Lumens Derate Chain",
        description=(
            "Apply explicit derates to rated projector lumens: ISO/IEC 21118 production limit, "
            "picture mode factor, lamp/laser aging, and fitted lens transmission"
        ),
        default=True,
        update=_update_analysis,
    )
    derate_production_tolerance: FloatProperty(
        name="Production Limit",
        description="Manufacturing variance lower limit factor (default 0.80 per ISO/IEC 21118:2012 §4.1/§6.1)",
        default=0.80,
        min=0.50,
        max=1.00,
        precision=2,
        update=_update_analysis,
    )
    derate_picture_mode: FloatProperty(
        name="Picture Mode",
        description="Calibrated/standard picture mode factor vs uncalibrated boost mode (default 0.85)",
        default=0.85,
        min=0.10,
        max=1.00,
        precision=2,
        update=_update_analysis,
    )
    derate_aging: FloatProperty(
        name="Aging Factor",
        description="Lamp or laser aging degradation factor at service point / end of life (default 0.80)",
        default=0.80,
        min=0.10,
        max=1.00,
        precision=2,
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
    gain_model: EnumProperty(
        name="Gain Model",
        description=(
            "Screen gain model per SMPTE RP 94 idealisations. Lambertian is the "
            "scalar model (constant gain at every angle); peaked and retroflective "
            "shape the gain with a half-gain angle and an off-axis floor. "
            "Parametric idealisations at medium confidence - vendor gain-curve "
            "charts not consulted"
        ),
        items=[
            (
                "LAMBERTIAN",
                "Lambertian (scalar)",
                "Constant gain at every viewing angle - the scalar model",
            ),
            (
                "PEAKED",
                "Peaked (specular lobe)",
                "Lobe centred on the screen normal: peak gain on-axis, half-gain "
                "angle and off-axis floor shape the falloff",
            ),
            (
                "RETROFLECTIVE",
                "Retroflective (toward source)",
                "Lobe centred on the direction toward the projector - glass-beaded "
                "screens return light to the source",
            ),
        ],
        default="LAMBERTIAN",
        update=_update_analysis,
    )
    gain_half_angle_deg: FloatProperty(
        name="Half-Gain Angle",
        description=(
            "Viewing angle (deg) at which gain has fallen to half its peak - the "
            "datasheet number integrators quote. Used by the peaked and "
            "retroflective models only"
        ),
        default=30.0,
        min=1.0,
        max=89.0,
        precision=1,
        update=_update_analysis,
    )
    gain_off_axis: FloatProperty(
        name="Off-Axis Floor Gain",
        description=(
            "Gain far off the lobe axis; must sit below half the peak for a "
            "half-gain angle to exist. Used by the peaked and retroflective "
            "models only"
        ),
        default=0.6,
        min=0.01,
        max=2.49,
        precision=2,
        update=_update_analysis,
    )
    ambient_lux: FloatProperty(
        name="Ambient Illuminance",
        description="Ambient illuminance at the screen surface (lux) from room lighting/survey. 0 = dark room",
        default=0.0,
        min=0.0,
        max=5000.0,
        precision=1,
        update=_update_analysis,
    )
    iscr_category: EnumProperty(
        name="AVIXA ISCR Target",
        description=(
            "Reference application category per ANSI/AVIXA V201.01:2021 (ISCR). "
            "Disclaimer: this tool does not certify compliance; numeric tiers not reproduced"
        ),
        items=[
            ("NONE", "None", "No category reference target selected"),
            ("PASSIVE_VIEWING", "Passive Viewing", "Information viewing / casual displays"),
            ("BASIC_DECISION_MAKING", "Basic Decision Making", "Presentations, classrooms, business documents"),
            (
                "ANALYTICAL_DECISION_MAKING",
                "Analytical Decision Making",
                "Fine detail, engineering drawings, spreadsheets",
            ),
            (
                "FULL_MOTION_VIDEO",
                "Full Motion Video",
                "Video content requiring shadow and gradient detail",
            ),
        ],
        default="NONE",
        update=_update_analysis,
    )
    target_contrast_ratio: FloatProperty(
        name="Target Contrast Ratio",
        description="Optional target effective contrast ratio (e.g. 15.0 for 15:1). 0 = no numeric target check",
        default=0.0,
        min=0.0,
        max=10000.0,
        precision=1,
        update=_update_analysis,
    )
    enable_nine_point: BoolProperty(
        name="ANSI/IEC 9-Point",
        description="Sample light output and uniformity in ANSI/IEC 9-zone vocabulary",
        default=True,
        update=_update_analysis,
    )
    enable_discas: BoolProperty(
        name="DISCAS Viewer Audit",
        description="Run ANSI/INFOCOMM V202.01 (DISCAS) farthest and closest viewer checks",
        default=False,
        update=_update_analysis,
    )
    discas_element_height_pct: FloatProperty(
        name="% Element Height",
        description="Percentage element height for BDM legibility (standard text default: 3.0%)",
        default=3.0,
        min=0.5,
        max=10.0,
        precision=1,
        update=_update_analysis,
    )
    discas_vertical_resolution: IntProperty(
        name="Vertical Resolution",
        description="Display vertical pixel resolution for ADM acuity limit",
        default=1080,
        min=480,
        max=8640,
        update=_update_analysis,
    )
    farthest_viewer_distance: FloatProperty(
        name="Farthest Viewer Distance",
        description="Distance (m) to farthest viewer for quick DISCAS audit (0 = scene objects only)",
        default=0.0,
        min=0.0,
        max=200.0,
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
