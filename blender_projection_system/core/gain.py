"""Angle-aware gain profiles for front projection screens.

Increment C: replaces the scalar Lambertian gain assumption with a
``gain(viewing_angle)`` profile family. SMPTE RP 94-2000, *Gain Determination
of Front Projection Screens*, is the primary source for the vocabulary
(half-gain angle) and the flat-wall guidance (>~1.3 peak gain).

Three parameterisations, all idealisations:

1. **Lambertian** — the scalar model used until now: one gain value at every
   viewing angle. A matte screen; luminance is view-independent.
2. **Peaked** — a specular lobe centred on the screen normal, parameterised by
   the *peak gain* (the on-axis value), the *half-gain angle* (the datasheet
   number integrators quote: the angle at which gain has fallen to half the
   peak) and an *off-axis floor gain* (the asymptotic value far off axis).
3. **Retroflective** — the same curve, but the lobe is centred on the
   direction from the screen point toward the projector: glass-beaded screens
   return light preferentially to the source.

The curve between the three parameters is a cosine-power idealisation::

    gain(θ) = floor + (peak − floor) · cos(θ)^n

with the exponent ``n`` fitted at construction so that ``gain(θ_half)`` equals
exactly half the peak. These are three-parameter models fitted to no measured
vendor data (see the medium-confidence disclaimer below) — they capture the
*shape* an integrator expects, not a particular screen's measurement.

ADR 0001: pure Python, no bpy. ADR 0002: every idealisation is stated loudly,
never presented as calibrated data.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from .errors import ProjectionError, require_finite, require_positive
from .surfaces import Surface
from .vectors import Vec3, dot, normalize, sub

#: Primary standard for screen gain determination and vocabulary.
GAIN_CITATION = "SMPTE RP 94-2000, Gain Determination of Front Projection Screens"

#: Screens above this peak gain are recommended on curved surfaces (RP 94
#: context; the increments register cites the same threshold). Flagged, never
#: modelled — this add-on does not simulate screen curvature.
RP94_FLAT_WALL_MAX_PEAK = 1.3

#: ADR 0002 loud flag for the parametric family: fitted to no vendor data.
GAIN_PROFILE_DISCLAIMER = (
    "Angle-dependent gain curves are three-parameter parametric idealisations at "
    "medium confidence — vendor gain-curve charts were not consulted; they capture "
    "an indicative shape, not a measured screen. On-site gain verification is "
    "always required."
)


class GainModel(str, Enum):
    """Which idealised reflectance family the screen follows."""

    LAMBERTIAN = "lambertian"
    PEAKED = "peaked"
    RETROFLECTIVE = "retroflective"


_GAIN_MODEL_LABELS: dict[GainModel, str] = {
    GainModel.LAMBERTIAN: "Lambertian",
    GainModel.PEAKED: "Peaked",
    GainModel.RETROFLECTIVE: "Retroflective",
}


def gain_model_label(model: GainModel) -> str:
    """Human-readable label for a gain model, used in reports and UI."""
    return _GAIN_MODEL_LABELS[model]


@dataclass(frozen=True)
class GainProfile:
    """One screen-gain parameterisation.

    ``peak_gain`` is the on-axis gain — the same number the scalar model
    called ``screen_gain``. For a Lambertian profile the other parameters are
    meaningless and ignored. For peaked/retroflective profiles the curve is a
    cosine-power lobe fitted so that ``gain(half_gain_angle_deg)`` equals
    exactly ``peak_gain / 2``, asymptotic to ``off_axis_gain``.
    """

    kind: GainModel
    peak_gain: float
    half_gain_angle_deg: float = 0.0
    off_axis_gain: float = 0.0
    #: Fitted cosine-power exponent; derived, not a user input.
    falloff_exponent: float = field(init=False, repr=False, compare=False, default=0.0)

    def __post_init__(self) -> None:
        require_finite("peak gain", self.peak_gain)
        require_positive("peak gain", self.peak_gain)
        if self.kind is GainModel.LAMBERTIAN:
            return
        require_finite("off-axis gain", self.off_axis_gain)
        require_finite("half-gain angle", self.half_gain_angle_deg)
        if not 0.0 < self.off_axis_gain < self.peak_gain / 2.0:
            raise ProjectionError(
                f"off-axis gain must be positive and below half the peak "
                f"({self.peak_gain / 2:.2f}) for a half-gain angle to exist, got "
                f"{self.off_axis_gain:.2f}"
            )
        if not 0.0 < self.half_gain_angle_deg < 90.0:
            raise ProjectionError(
                "half-gain angle must lie strictly between 0 and 90 degrees, got "
                f"{self.half_gain_angle_deg}"
            )
        ratio = (self.peak_gain / 2.0 - self.off_axis_gain) / (
            self.peak_gain - self.off_axis_gain
        )
        exponent = math.log(ratio) / math.log(math.cos(math.radians(self.half_gain_angle_deg)))
        object.__setattr__(self, "falloff_exponent", exponent)

    # -- constructors ---------------------------------------------------------

    @classmethod
    def lambertian(cls, gain: float) -> GainProfile:
        """The scalar model used before this increment: constant gain."""
        return cls(GainModel.LAMBERTIAN, peak_gain=gain)

    @classmethod
    def peaked(cls, peak_gain: float, half_gain_angle_deg: float, off_axis_gain: float) -> GainProfile:
        """Specular lobe centred on the screen normal."""
        return cls(
            GainModel.PEAKED,
            peak_gain=peak_gain,
            half_gain_angle_deg=half_gain_angle_deg,
            off_axis_gain=off_axis_gain,
        )

    @classmethod
    def retroflective(cls, peak_gain: float, half_gain_angle_deg: float, off_axis_gain: float) -> GainProfile:
        """Lobe centred on the direction toward the projector."""
        return cls(
            GainModel.RETROFLECTIVE,
            peak_gain=peak_gain,
            half_gain_angle_deg=half_gain_angle_deg,
            off_axis_gain=off_axis_gain,
        )

    @property
    def is_angular(self) -> bool:
        """Whether luminance depends on the viewing angle."""
        return self.kind is not GainModel.LAMBERTIAN


def gain_at(profile: GainProfile, angle_deg: float) -> float:
    """Gain at ``angle_deg`` from the profile's lobe axis.

    Lambertian profiles ignore the angle. Negative angles use the symmetric
    lobe (``|θ|``); angles at or beyond 90 degrees clamp to the off-axis floor.
    """
    if profile.kind is GainModel.LAMBERTIAN:
        return profile.peak_gain
    magnitude = abs(angle_deg)
    if magnitude >= 90.0:
        return profile.off_axis_gain
    shape = math.cos(math.radians(magnitude)) ** profile.falloff_exponent
    return profile.off_axis_gain + (profile.peak_gain - profile.off_axis_gain) * shape


def factor_at(profile: GainProfile, angle_deg: float) -> float:
    """Gain relative to the on-axis peak: 1.0 at 0°, ``floor/peak`` far off axis."""
    if profile.kind is GainModel.LAMBERTIAN:
        return 1.0
    return gain_at(profile, angle_deg) / profile.peak_gain


def lobe_axis(
    profile: GainProfile,
    surface_point: Vec3,
    surface_normal: Vec3,
    projector_origin: Vec3 | None,
) -> Vec3 | None:
    """Direction the profile's lobe is centred on, from ``surface_point``.

    Peaked lobes sit on the surface normal; retroflective lobes point at the
    projector (glass-beaded screens return light to the source) and therefore
    require the projector position — refusing loudly rather than guessing.
    Lambertian profiles have no lobe.
    """
    if profile.kind is GainModel.LAMBERTIAN:
        return None
    if profile.kind is GainModel.PEAKED:
        return normalize(surface_normal)
    if projector_origin is None:
        raise ProjectionError(
            "a retroflective gain profile needs the projector position to aim "
            "its lobe; none was supplied"
        )
    return normalize(sub(projector_origin, surface_point))


def viewing_angle_deg(viewer_point: Vec3, surface_point: Vec3, lobe_axis_dir: Vec3) -> float:
    """Angle in degrees between the viewer and the lobe axis, seen from the screen."""
    to_viewer = normalize(sub(viewer_point, surface_point))
    cosine = max(-1.0, min(1.0, dot(to_viewer, lobe_axis_dir)))
    return math.degrees(math.acos(cosine))


def assumptions_for_gain_profile(profile: GainProfile) -> str:
    """The assumption-line replacement describing an active gain profile.

    ADR 0002: the line states the model, the citation and the medium-confidence
    status of the parametric curve in one breath, because it rides with every
    derived luminance number.
    """
    if profile.kind is GainModel.LAMBERTIAN:
        return "Lambertian screen at the stated gain"
    text = (
        f"{gain_model_label(profile.kind).lower()} gain profile, {GAIN_CITATION} "
        f"idealistion: peak {profile.peak_gain:.2f}, half-gain at "
        f"{profile.half_gain_angle_deg:.0f} deg, off-axis floor "
        f"{profile.off_axis_gain:.2f}"
    )
    if profile.kind is GainModel.RETROFLECTIVE:
        text += "; lobe referenced toward the projector array centre"
    return text + "; parametric idealisation at medium confidence (vendor gain-curve charts not consulted)"


def flat_wall_gain_warning(profile: GainProfile, wall: Surface) -> str | None:
    """RP 94-derived flag for high peak gain on a flat wall.

    Fires only when the peak exceeds ~1.3 **and** the wall is flat
    (``curvature_radius is None`` per the ADR 0003 hook). Curvature itself is
    flagged, never modelled.
    """
    if profile.peak_gain <= RP94_FLAT_WALL_MAX_PEAK:
        return None
    if wall.curvature_radius is not None:
        return None
    return (
        f"peak gain {profile.peak_gain:.2f} on a flat wall exceeds ~"
        f"{RP94_FLAT_WALL_MAX_PEAK}: per {GAIN_CITATION} guidance, screens above "
        f"{RP94_FLAT_WALL_MAX_PEAK} gain are recommended on curved surfaces; "
        "curvature is flagged here, not modelled"
    )


def half_gain_cone_warnings(
    profile: GainProfile,
    viewers: Sequence,
) -> list[str]:
    """RP 94-derived flags for viewers sitting outside the half-gain cone.

    ``viewers`` are :class:`~.discas.ViewerResult` rows from the per-seat audit.
    Lambertian profiles have no cone and warn about nothing.
    """
    if not profile.is_angular:
        return []
    out: list[str] = []
    for viewer in viewers:
        if viewer.off_axis_deg > profile.half_gain_angle_deg:
            out.append(
                f"viewer '{viewer.name}' at {viewer.off_axis_deg:.1f} deg off-axis sits "
                f"outside the {profile.half_gain_angle_deg:.0f} deg half-gain cone; it "
                f"sees {viewer.perceived_nits:.0f} nits where an on-axis viewer sees "
                "the full gain"
            )
    return out
