"""Pure projection mathematics for the Blender Projection Planner.

Nothing in this package imports ``bpy``. That is deliberate and enforced by
``tests/test_addon_contract.py``: it means every formula here runs and is tested
under plain CPython, and the Blender layer stays a thin adapter over it.

Units are SI throughout - metres, radians, lumens, lux, candela - and angles
are radians unless a name ends in ``_deg``.
"""

from __future__ import annotations

from .array import (
    MODE_LEVEL,
    MODE_TILT,
    MOUNT_MODES,
    ArrayPlan,
    ProjectorPlacement,
    arc_centers,
    arc_width_per_projector,
    format_placement,
    plan_array,
    plan_projector,
)
from .coverage import (
    BlendZone,
    CoverageCell,
    CoverageReport,
    Interval,
    analyze_coverage,
    compute_blend_zones,
    format_report,
)
from .errors import ProjectionError
from .footprint import Footprint, FootprintSample, compute_footprint
from .photometry import (
    ASSUMPTIONS,
    BrightnessReport,
    axial_intensity,
    frustum_solid_angle,
    illuminance_at,
    luminance_nits,
    nits_to_foot_lamberts,
    summarize_brightness,
)
from .pose import Pose, level_pose, look_at
from .surfaces import CylindricalWall, SurfaceHit
from .throw import (
    ImageSize,
    ProjectorSpec,
    ThrowReport,
    describe_throw,
    half_angles,
    image_height_from_width,
    image_size,
    image_width_from_distance,
    shift_from_half_image_percent,
    throw_distance_from_width,
    throw_ratio_from,
)

__all__ = [
    "ASSUMPTIONS",
    "ArrayPlan",
    "BlendZone",
    "CoverageCell",
    "BrightnessReport",
    "CoverageReport",
    "CylindricalWall",
    "Footprint",
    "FootprintSample",
    "ImageSize",
    "Interval",
    "MODE_LEVEL",
    "MODE_TILT",
    "MOUNT_MODES",
    "Pose",
    "ProjectionError",
    "ProjectorPlacement",
    "ProjectorSpec",
    "SurfaceHit",
    "ThrowReport",
    "analyze_coverage",
    "arc_centers",
    "arc_width_per_projector",
    "axial_intensity",
    "compute_blend_zones",
    "compute_footprint",
    "describe_throw",
    "format_placement",
    "format_report",
    "frustum_solid_angle",
    "half_angles",
    "illuminance_at",
    "image_height_from_width",
    "image_size",
    "image_width_from_distance",
    "level_pose",
    "look_at",
    "luminance_nits",
    "nits_to_foot_lamberts",
    "plan_array",
    "plan_projector",
    "shift_from_half_image_percent",
    "summarize_brightness",
    "throw_distance_from_width",
    "throw_ratio_from",
]
