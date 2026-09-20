"""ANSI/INFOCOMM V202.01 (DISCAS) Display Image Size calculations.

Implements the standard's formulas for:
- Basic Decision Making (BDM): font legibility at 10 arcminutes.
- Analytical Decision Making (ADM): 1 arcminute visual acuity per pixel limit.
- Maximum and minimum viewing distances.
- Per-seat viewer off-axis angles and perceived luminance.

ADR 0001: Pure Python only, no bpy or mathutils.
ADR 0002: Disclose formulas, warn loudly, never claim human certification.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .errors import ProjectionError, require_positive
from .gain import GainModel, GainProfile, factor_at, lobe_axis, viewing_angle_deg
from .vectors import Vec3, distance, dot, normalize, sub

ARCMINUTE_RAD = math.radians(1.0 / 60.0)
TEN_ARCMINUTES_RAD = math.radians(10.0 / 60.0)

DISCAS_DISCLAIMER = (
    "Calculated per ANSI/INFOCOMM V202.01 (DISCAS) geometric equations; "
    "evaluates mathematical sizing limits, does not certify human vision."
)


def bdm_max_viewing_distance(image_height: float, element_height_percent: float = 3.0) -> float:
    """Maximum viewing distance for Basic Decision Making (BDM) per DISCAS.

    Formula:
        ``D_max = (H * %EH / 100) / tan(10 arcminutes)``
    """
    require_positive("image height", image_height)
    require_positive("element height percent", element_height_percent)
    elem_height = image_height * (element_height_percent / 100.0)
    return elem_height / math.tan(TEN_ARCMINUTES_RAD)


def adm_max_viewing_distance(image_height: float, vertical_resolution: int = 1080) -> float:
    """Maximum viewing distance for Analytical Decision Making (ADM) per DISCAS.

    Formula:
        ``D_max = (H / V_res) / tan(1 arcminute)``
    """
    require_positive("image height", image_height)
    if vertical_resolution < 1:
        raise ProjectionError("vertical resolution must be at least 1")
    pixel_height = image_height / vertical_resolution
    return pixel_height / math.tan(ARCMINUTE_RAD)


def closest_viewer_min_distance(image_height: float) -> float:
    """Recommended minimum viewing distance per DISCAS (H * 1.0)."""
    require_positive("image height", image_height)
    return image_height * 1.0


@dataclass(frozen=True)
class ViewerResult:
    """Audit metrics for one viewer position."""

    name: str
    location: Vec3
    distance: float
    off_axis_deg: float
    perceived_nits: float
    bdm_pass: bool
    adm_pass: bool
    closest_pass: bool
    off_axis_pass: bool


@dataclass(frozen=True)
class DiscasReport:
    """Complete DISCAS display image size audit."""

    image_height: float
    vertical_resolution: int
    element_height_pct: float
    bdm_max_distance: float
    adm_max_distance: float
    min_distance: float
    viewers: tuple[ViewerResult, ...]
    farthest_distance: float
    worst_off_axis_deg: float
    bdm_conforms: bool
    adm_conforms: bool
    disclaimer: str = DISCAS_DISCLAIMER


def audit_viewers(
    viewers: Sequence[tuple[str, Vec3]],
    screen_center: Vec3,
    screen_normal: Vec3,
    image_height: float,
    mean_screen_nits: float = 150.0,
    vertical_resolution: int = 1080,
    element_height_pct: float = 3.0,
    max_off_axis_deg: float = 45.0,
    gain_profile: GainProfile | None = None,
    projector_origin: Vec3 | None = None,
) -> DiscasReport:
    """Evaluate a set of viewer positions against DISCAS criteria.

    ``gain_profile`` optionally applies an angle-aware gain model
    (SMPTE RP 94 idealisations, see :mod:`.gain`) to the per-seat perceived
    luminance. Without one, perceived luminance is view-independent — the
    honest Lambertian behaviour. Before increment C this function applied a
    ``mean · cos θ`` falloff, which is *not* Lambertian behaviour (a Lambertian
    screen has no viewing-angle falloff) and was corrected deliberately.
    A retroflective profile aims its lobe at ``projector_origin`` and raises
    :class:`ProjectionError` when that position is not supplied.
    """
    require_positive("image height", image_height)
    d_max_bdm = bdm_max_viewing_distance(image_height, element_height_pct)
    d_max_adm = adm_max_viewing_distance(image_height, vertical_resolution)
    d_min = closest_viewer_min_distance(image_height)

    results: list[ViewerResult] = []
    norm = normalize(screen_normal)

    for name, loc in viewers:
        to_viewer = sub(loc, screen_center)
        dist = distance(loc, screen_center)
        if dist > 1e-6:
            v_dir = normalize(to_viewer)
            cos_theta = max(-1.0, min(1.0, dot(v_dir, norm)))
            angle_deg = math.degrees(math.acos(cos_theta))
        else:
            angle_deg = 0.0
            cos_theta = 1.0

        # Off-axis perceived luminance. No profile (or a Lambertian one):
        # view-independent — luminance is luminance. Peaked: the gain curve
        # falls off with the angle from the screen normal. Retroflective: the
        # lobe aims at the projector, so the angle is measured from that axis.
        if gain_profile is None or gain_profile.kind is GainModel.LAMBERTIAN:
            factor = 1.0
        elif gain_profile.kind is GainModel.PEAKED:
            factor = factor_at(gain_profile, angle_deg)
        else:
            axis = lobe_axis(gain_profile, screen_center, norm, projector_origin)
            factor = factor_at(gain_profile, viewing_angle_deg(loc, screen_center, axis))
        perceived = max(0.0, mean_screen_nits * factor)
        bdm_pass = dist <= d_max_bdm
        adm_pass = dist <= d_max_adm
        closest_pass = dist >= d_min
        off_axis_pass = angle_deg <= max_off_axis_deg

        results.append(
            ViewerResult(
                name=name,
                location=loc,
                distance=dist,
                off_axis_deg=angle_deg,
                perceived_nits=perceived,
                bdm_pass=bdm_pass,
                adm_pass=adm_pass,
                closest_pass=closest_pass,
                off_axis_pass=off_axis_pass,
            )
        )

    farthest = max((r.distance for r in results), default=0.0)
    worst_off_axis = max((r.off_axis_deg for r in results), default=0.0)
    bdm_conforms = all(r.bdm_pass for r in results) if results else True
    adm_conforms = all(r.adm_pass for r in results) if results else True

    return DiscasReport(
        image_height=image_height,
        vertical_resolution=vertical_resolution,
        element_height_pct=element_height_pct,
        bdm_max_distance=d_max_bdm,
        adm_max_distance=d_max_adm,
        min_distance=d_min,
        viewers=tuple(results),
        farthest_distance=farthest,
        worst_off_axis_deg=worst_off_axis,
        bdm_conforms=bdm_conforms,
        adm_conforms=adm_conforms,
    )
