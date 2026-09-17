"""Brightness and illuminance estimates.

Stated assumptions
------------------
These are first-order engineering estimates, not a photometric simulation.
Every function here assumes:

1. **Uniform intensity across the frustum.** Real projectors fall off toward
   the corners; a 70-90% corner/minimum-to-reference uniformity result means a
   roughly 10-30% shortfall that this estimate does not model.
2. **Rated lumens are delivered.** No lamp/laser ageing, no eco mode, no
   colour-mode derate. Divide ``lumens`` yourself to model those.
3. **A Lambertian screen** of the given gain, so luminance is
   ``E * gain / pi``. Real gain is angle-dependent; high-gain screens only
   deliver their rated gain near the specular direction.
4. **No ambient light and no inter-reflection.** Contrast in a real room will
   be worse. There is deliberately no "ambient light AI" in this package.
5. **No atmospheric loss, no lens vignetting, no optical throw-away.**

Overlapping projectors are treated as simply additive in illuminance, which is
correct for incoherent sources. Edge blending is *not* modelled optically: the
blend metrics elsewhere in this package describe geometry, not the soft-edge
ramp a blending processor would apply.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum

from .errors import ProjectionError, require_positive
from .throw import ProjectorSpec

#: Conversion constants.
LUX_PER_FOOTCANDLE = 10.763910416709722
NITS_PER_FOOTLAMBERT = 3.4262590996

#: SMPTE ST 196 recommends roughly 55 nits (16 fL) for cinema white.
CINEMA_WHITE_NITS = 55.0
#: Common presentation-room target band, in nits.
PRESENTATION_NITS_MIN = 100.0
PRESENTATION_NITS_MAX = 500.0


def frustum_solid_angle(spec: ProjectorSpec) -> float:
    """Exact solid angle of the possibly shifted rectangular frustum."""
    x0 = (-0.5 + spec.lens_shift_h) / spec.throw_ratio
    x1 = (0.5 + spec.lens_shift_h) / spec.throw_ratio
    y0 = (-0.5 + spec.lens_shift_v) / (spec.throw_ratio * spec.aspect)
    y1 = (0.5 + spec.lens_shift_v) / (spec.throw_ratio * spec.aspect)

    def corner(x: float, y: float) -> float:
        return math.atan2(x * y, math.sqrt(1.0 + x * x + y * y))

    return abs(corner(x1, y1) - corner(x0, y1) - corner(x1, y0) + corner(x0, y0))


def axial_intensity(spec: ProjectorSpec) -> float:
    """Luminous intensity in candela (lm/sr) under the uniformity assumption.

    Applies fitted lens transmission factor (ProjectorSpec.lens_transmission)
    if specified.
    """
    omega = frustum_solid_angle(spec)
    if omega <= 0.0:
        raise ProjectionError("degenerate frustum: solid angle is zero")
    transmission = getattr(spec, "lens_transmission", 1.0)
    return (spec.lumens * transmission) / omega


def illuminance_at(spec: ProjectorSpec, distance: float, incidence: float = 0.0) -> float:
    """Illuminance in lux at a surface point.

    ``E = I * cos(incidence) / d^2``. Incidence at or beyond 90 degrees means
    the surface faces away from the projector and returns zero.
    """
    require_positive("distance", distance)
    cos_i = math.cos(incidence)
    if cos_i <= 0.0:
        return 0.0
    return axial_intensity(spec) * cos_i / (distance * distance)


def nominal_screen_illuminance(spec: ProjectorSpec, image_area: float) -> float:
    """Flux spread evenly over a flat image: ``E = (lumens * transmission) / area``.

    This is the number an AV designer computes by hand, and it is the *mean*
    illuminance across a flat screen. It is not the on-axis value - see
    :func:`center_to_mean_ratio`.
    """
    require_positive("image area", image_area)
    transmission = getattr(spec, "lens_transmission", 1.0)
    return (spec.lumens * transmission) / image_area


def center_to_mean_ratio(spec: ProjectorSpec) -> float:
    """How much brighter the image centre is than the flat-screen average.

    Even with perfectly uniform intensity per steradian, a flat screen is
    brighter in the middle: the corners are further away and struck obliquely.
    The ratio is ``4*tan(theta_h)*tan(theta_v) / Omega`` and tends to 1 as the
    lens gets longer. A 1.2:1 lens is about 11% hot in the centre; a 4:1 lens
    about 1%.

    This is *geometry only* - it is on top of whatever optical non-uniformity
    the projector itself has, which this package does not model.
    """
    omega = frustum_solid_angle(spec)
    if omega <= 0.0:
        raise ProjectionError("degenerate frustum: solid angle is zero")
    image_area_at_unit_distance = 1.0 / (spec.throw_ratio**2 * spec.aspect)
    return image_area_at_unit_distance / omega


def luminance_nits(illuminance: float, screen_gain: float = 1.0) -> float:
    """Lambertian screen luminance in cd/m^2 from illuminance in lux."""
    require_positive("screen gain", screen_gain)
    if not math.isfinite(illuminance):
        raise ProjectionError(f"illuminance must be finite, got {illuminance}")
    if illuminance < 0.0:
        raise ProjectionError(f"illuminance must not be negative, got {illuminance}")
    return illuminance * screen_gain / math.pi


def nits_to_foot_lamberts(nits: float) -> float:
    return nits / NITS_PER_FOOTLAMBERT


def lux_to_foot_candles(lux: float) -> float:
    return lux / LUX_PER_FOOTCANDLE


@dataclass(frozen=True)
class DerateChain:
    """Explicit derate chain for projector luminous flux.

    Replaces 'full rated lumens assumed' with audit-proof margin statements
    covering manufacturing variance, picture mode calibration, lamp/laser aging,
    and lens transmission efficiency.

    References:
        - ISO/IEC 21118:2012 §4.1 / §6.1: Spec-sheet light output is production average;
          production lower limit is >= 80% of rated value.
        - Dataton WATCHOUT / AVIXA installation practice: calibrated color modes
          typically deliver 10-25% less flux than raw dynamic boost; lamp/laser
          aging factor represents flux at service replacement / end-of-life point.
    """

    production_tolerance: float = 0.80
    """Manufacturing variance lower limit factor (default 0.80 per ISO/IEC 21118:2012)."""

    picture_mode_factor: float = 0.85
    """Calibrated/standard picture mode factor vs uncalibrated boost mode (default 0.85)."""

    aging_factor: float = 0.80
    """Lamp or laser aging factor at service point / end of life (default 0.80)."""

    lens_transmission: float = 1.0
    """Optical transmission factor of the lens (default 1.0, from ProjectorSpec)."""

    def __post_init__(self) -> None:
        require_positive("production tolerance", self.production_tolerance)
        require_positive("picture mode factor", self.picture_mode_factor)
        require_positive("aging factor", self.aging_factor)
        require_positive("lens transmission", self.lens_transmission)
        if any(
            not math.isfinite(x)
            for x in (
                self.production_tolerance,
                self.picture_mode_factor,
                self.aging_factor,
                self.lens_transmission,
            )
        ):
            raise ProjectionError("derate factors must be finite")

    @property
    def rated_multiplier(self) -> float:
        """Rated baseline multiplier (fitted lens transmission applied)."""
        return self.lens_transmission

    @property
    def typical_multiplier(self) -> float:
        """Typical condition multiplier (nominal production, calibrated mode, mid-life aging, lens)."""
        mid_aging = 0.5 * (1.0 + self.aging_factor)
        return self.lens_transmission * self.picture_mode_factor * mid_aging

    @property
    def worst_case_multiplier(self) -> float:
        """Worst-case lower bound multiplier (lower tolerance, calibrated mode, full aging, lens)."""
        return (
            self.lens_transmission
            * self.production_tolerance
            * self.picture_mode_factor
            * self.aging_factor
        )

    @property
    def operational_typical_factor(self) -> float:
        """Operational derate factor (picture mode * mid-life aging)."""
        return self.picture_mode_factor * 0.5 * (1.0 + self.aging_factor)

    @property
    def operational_worst_case_factor(self) -> float:
        """Operational worst-case derate factor (production * picture mode * aging)."""
        return self.production_tolerance * self.picture_mode_factor * self.aging_factor

    def effective_lumens(self, rated_lumens: float, condition: str = "typical") -> float:
        """Derated lumens for the given condition ('rated', 'typical', 'worst_case')."""
        require_positive("rated lumens", rated_lumens)
        if condition == "rated":
            return rated_lumens * self.rated_multiplier
        elif condition == "typical":
            return rated_lumens * self.typical_multiplier
        elif condition in ("worst_case", "worst"):
            return rated_lumens * self.worst_case_multiplier
        raise ProjectionError(f"unknown derate condition: {condition!r}")


@dataclass(frozen=True)
class BrightnessBand:
    """Luminance and illuminance statistics for one operating condition."""

    condition: str
    derate_factor: float
    min_lux: float
    max_lux: float
    mean_lux: float
    min_nits: float
    max_nits: float
    mean_nits: float
    mean_foot_lamberts: float


@dataclass(frozen=True)
class BrightnessReport:
    """Illuminance statistics over a set of sampled surface points."""

    sample_count: int
    min_lux: float
    max_lux: float
    mean_lux: float
    min_nits: float
    max_nits: float
    mean_nits: float
    mean_foot_lamberts: float
    uniformity: float
    """Min/max illuminance ratio; 1.0 is perfectly even."""
    screen_gain: float
    assumptions: list[str]

    # -- derate bands (Increment #3a) --------------------------------------
    derate_chain: DerateChain | None = None
    rated_band: BrightnessBand | None = None
    typical_band: BrightnessBand | None = None
    worst_case_band: BrightnessBand | None = None


#: The assumption list surfaced in the UI and reports, kept short on purpose.
ASSUMPTIONS: list[str] = [
    "uniform intensity across the frustum (real corner falloff not modelled)",
    "rated lumens delivered in full (no lamp ageing or eco-mode derate)",
    "Lambertian screen at the stated gain",
    "no ambient light and no inter-reflection",
    "overlapping projectors add linearly (no blend-processor ramp)",
]

#: Assumption line that replaces the additive one when a blend ramp is applied.
_LINEAR_RAMP_ASSUMPTION = (
    "blend zones modelled with complementary linear luminance ramps "
    "(real processors often use gamma-shaped curves; check yours)"
)


class ISCRCategory(str, Enum):
    """Reference application categories per ANSI/AVIXA V201.01:2021 (ISCR).

    Disclaimer: This tool structures metrics according to the standard's
    vocabulary but does not certify compliance. Numeric tiers are not reproduced.
    """

    NONE = "none"
    PASSIVE_VIEWING = "passive_viewing"
    BASIC_DECISION_MAKING = "basic_decision_making"
    ANALYTICAL_DECISION_MAKING = "analytical_decision_making"
    FULL_MOTION_VIDEO = "full_motion_video"


ISCR_CATEGORY_LABELS: dict[ISCRCategory, str] = {
    ISCRCategory.NONE: "None",
    ISCRCategory.PASSIVE_VIEWING: "Passive Viewing",
    ISCRCategory.BASIC_DECISION_MAKING: "Basic Decision Making",
    ISCRCategory.ANALYTICAL_DECISION_MAKING: "Analytical Decision Making",
    ISCRCategory.FULL_MOTION_VIDEO: "Full Motion Video",
}

ISCR_DISCLAIMER = (
    "Structure per ANSI/AVIXA V201.01:2021; this tool does not certify compliance; "
    "numeric tiers not reproduced."
)


def veiling_luminance_nits(ambient_lux: float, screen_gain: float = 1.0) -> float:
    """Reflected ambient luminance (veiling luminance) in nits from ambient lux.

    Assumes a Lambertian screen surface of the given gain:
    ``L_amb = ambient_lux * screen_gain / pi``.
    """
    require_positive("screen gain", screen_gain)
    if not math.isfinite(ambient_lux) or ambient_lux < 0.0:
        raise ProjectionError("ambient illuminance must be finite and non-negative")
    return ambient_lux * screen_gain / math.pi


def effective_contrast_ratio(
    white_lux: float,
    black_lux: float,
    ambient_lux: float,
) -> float:
    """Effective on-screen contrast ratio under ambient illuminance.

    ``CR = (E_white + E_amb) / (E_black + E_amb)``.

    Equivalent in luminance (nits) since the screen gain factor cancels out:
    ``(L_white + L_amb) / (L_black + L_amb)``.
    """
    if white_lux < 0.0 or black_lux < 0.0 or ambient_lux < 0.0:
        raise ProjectionError("illuminance values must be non-negative")
    denom = black_lux + ambient_lux
    if denom <= 0.0:
        if white_lux <= 0.0:
            return 1.0
        return float("inf")
    return (white_lux + ambient_lux) / denom


@dataclass(frozen=True)
class ContrastReport:
    """On-screen effective contrast analysis across sampled wall cells."""

    ambient_lux: float
    screen_gain: float
    veiling_nits: float
    min_contrast: float
    max_contrast: float
    mean_contrast: float
    target_category: ISCRCategory = ISCRCategory.NONE
    user_target_ratio: float = 0.0
    meets_user_target: bool | None = None
    assumptions: list[str] = field(default_factory=list)
    disclaimer: str = ISCR_DISCLAIMER


def summarize_contrast(
    contrast_values: Iterable[float],
    ambient_lux: float,
    screen_gain: float = 1.0,
    target_category: ISCRCategory = ISCRCategory.NONE,
    user_target_ratio: float = 0.0,
    assumptions: Sequence[str] | None = None,
) -> ContrastReport:
    values = [v for v in contrast_values if math.isfinite(v)]
    if not values:
        raise ProjectionError("no contrast samples to summarise")
    lo, hi = min(values), max(values)
    mean = sum(values) / len(values)
    veiling = veiling_luminance_nits(ambient_lux, screen_gain)

    meets_target = None
    if user_target_ratio > 0.0:
        meets_target = lo >= user_target_ratio

    if assumptions is None:
        assumptions = [
            "uniform ambient illuminance across screen (real directional ambient light not modelled)",
            "native projector contrast used (not dynamic contrast); no inter-reflection modelled",
            "Lambertian screen reflectance at the stated screen gain",
        ]

    return ContrastReport(
        ambient_lux=ambient_lux,
        screen_gain=screen_gain,
        veiling_nits=veiling,
        min_contrast=lo,
        max_contrast=hi,
        mean_contrast=mean,
        target_category=target_category,
        user_target_ratio=user_target_ratio,
        meets_user_target=meets_target,
        assumptions=list(assumptions),
        disclaimer=ISCR_DISCLAIMER,
    )


ANSI_IEC_DISCLAIMER = (
    "Model output in ANSI/IEC vocabulary; calculated from geometric simulation, "
    "not physical laboratory measurement."
)


@dataclass(frozen=True)
class NinePointSample:
    """One of the nine ANSI/IEC 61947-1 measurement sample points."""

    position_label: str
    normalized_u: float
    normalized_v: float
    s: float
    z: float
    lux: float
    nits: float
    foot_lamberts: float


@dataclass(frozen=True)
class NinePointReport:
    """Light output and uniformity evaluated in ANSI/IEC 9-point vocabulary.

    References:
        - IEC 61947-1:2002 / ANSI IT7.228: 3x3 equal zone centers for measuring
          projector light output and center-to-corner uniformity.

    Disclaimer:
        Model output in ANSI/IEC vocabulary; calculated from geometric simulation,
        not physical laboratory measurement.
    """

    points: tuple[NinePointSample, ...]
    average_lux: float
    average_nits: float
    average_foot_lamberts: float
    center_lux: float
    center_nits: float
    center_foot_lamberts: float
    lit_area: float
    light_output_lumens: float
    """9-point average illuminance * lit area."""
    corner_to_center_ratio: float
    """Min corner illuminance / center illuminance (datasheet metric)."""
    corner_average_to_center_ratio: float
    """Average of 4 corners / center illuminance."""
    nine_point_uniformity: float
    """Min / max among the 9 sample points."""
    disclaimer: str = ANSI_IEC_DISCLAIMER


class BlendModel(str, Enum):
    """How overlapping projectors' illuminance is combined.

    ``RAW`` is simple addition - two images fully stacked means twice the
    light, which is what happens with no blending processor in the chain.
    ``LINEAR_RAMP`` models complementary linear ramps (gamma=1.0).
    ``GAMMA_RAMP`` models gamma-shaped soft-edge ramps (custom exponent,
    default 1.0, range 0.5-1.5) per Dataton WATCHOUT convention.
    """

    RAW = "raw"
    LINEAR_RAMP = "linear_ramp"
    GAMMA_RAMP = "gamma_ramp"


def assumptions_for_blend_model(
    model: BlendModel,
    gamma: float = 1.0,
    derate_chain: DerateChain | None = None,
) -> list[str]:
    """The assumption lines that apply to a given blend model and derate chain."""
    base: list[str] = []
    for a in ASSUMPTIONS:
        if a.startswith("rated lumens"):
            if derate_chain is not None:
                base.append(
                    f"lumens derate chain applied: ISO/IEC 21118 lower limit {derate_chain.production_tolerance * 100:.0f}%, "
                    f"picture mode {derate_chain.picture_mode_factor * 100:.0f}%, "
                    f"aging {derate_chain.aging_factor * 100:.0f}%, "
                    f"lens transmission {derate_chain.lens_transmission * 100:.0f}%"
                )
            else:
                base.append(a)
        elif a.startswith("overlapping"):
            if model is BlendModel.LINEAR_RAMP:
                base.append(_LINEAR_RAMP_ASSUMPTION)
            elif model is BlendModel.GAMMA_RAMP:
                base.append(
                    f"blend zones modelled with gamma-shaped ramps (gamma={gamma:.2f}; "
                    "Dataton WATCHOUT convention; on-site validation required)"
                )
            else:
                base.append(a)
        else:
            base.append(a)
    return base


def linear_ramp_weight(
    s: float,
    zone_start: float,
    zone_end: float,
    *,
    side: str,
    gamma: float = 1.0,
) -> float:
    """Weight a blending processor applies to one image at arc position ``s``.

    Across the zone ``[zone_start, zone_end]`` the *left* projector ramps
    from full output to zero while the *right* one ramps from zero to full.
    Outside the zone weights clamp to 1.0 / 0.0 respectively.

    When ``gamma == 1.0`` (linear ramp), the pair's weights sum to 1.0.
    When ``gamma != 1.0``, a gamma curve (per Dataton WATCHOUT soft-edge gamma
    convention, range 0.5-1.5) is applied to shape the transition or compensate
    for display/EOTF non-linearity.

    Raises :class:`ProjectionError` for a zero-width zone or non-positive gamma.
    """
    width = zone_end - zone_start
    if width <= 0.0:
        raise ProjectionError("blend zone must have positive width")
    if gamma <= 0.0:
        raise ProjectionError(f"blend gamma must be positive, got {gamma}")
    fraction = (s - zone_start) / width
    fraction = min(1.0, max(0.0, fraction))
    linear = (1.0 - fraction) if side == "left" else fraction
    if gamma == 1.0:
        return linear
    return linear**gamma


gamma_ramp_weight = linear_ramp_weight


def blend_ramp_luminance_error(gamma: float) -> float:
    """Theoretical mid-zone luminance error fraction: 2^(1 - gamma) - 1.0."""
    require_positive("gamma", gamma)
    return (2.0 ** (1.0 - gamma)) - 1.0


def overlap_guidance(fraction: float) -> str:
    """Industry guidance on blend overlap percentage.

    Guidance per Dataton WATCHOUT / AVIXA best practice:
    - 10-20% of image width is recommended for smooth soft-edge blending.
    - <5% is hard to blend and prone to visible seams from vibration/thermal drift.
    - 5-10% is tight.
    - >20% is generous but consumes redundant projector resolution.
    """
    if fraction < 0.05:
        return "<5% overlap is difficult to blend seamlessly on-site; optical alignment drift will be visible"
    if fraction < 0.10:
        return "<10% overlap is tight; 10-20% overlap is recommended for soft-edge blending"
    if fraction <= 0.20:
        return "10-20% overlap matches recommended industry practice for soft-edge blending"
    return ">20% overlap is generous; ensures smooth blending but reduces total array canvas width"


BLEND_CALIBRATION_CHECKLIST: tuple[str, ...] = (
    "Grayscale-ramp validation at 25%, 50%, 75%, and 100% white test patterns",
    "Verify soft-edge gamma matches screen reflectance and optical overlap",
    "Optical or processor black-level matching / black-lift (not simulated by this tool)",
    "Color gamut matching and white point calibration across adjacent units",
)


def summarize_brightness(
    lux_values: Iterable[float],
    screen_gain: float = 1.0,
    assumptions: Sequence[str] | None = None,
    derate_chain: DerateChain | None = None,
) -> BrightnessReport:
    values = [v for v in lux_values]
    if not values:
        raise ProjectionError("no illuminance samples to summarise")
    require_positive("screen gain", screen_gain)
    if any(not math.isfinite(v) or v < 0.0 for v in values):
        raise ProjectionError("illuminance samples must be finite and non-negative")
    lo, hi = min(values), max(values)
    mean = sum(values) / len(values)
    uniformity = (lo / hi) if hi > 0.0 else 0.0

    rated_band: BrightnessBand | None = None
    typical_band: BrightnessBand | None = None
    worst_case_band: BrightnessBand | None = None

    if derate_chain is not None:

        def make_band(condition: str, factor: float) -> BrightnessBand:
            b_min_lux = lo * factor
            b_max_lux = hi * factor
            b_mean_lux = mean * factor
            b_min_nits = luminance_nits(b_min_lux, screen_gain)
            b_max_nits = luminance_nits(b_max_lux, screen_gain)
            b_mean_nits = luminance_nits(b_mean_lux, screen_gain)
            return BrightnessBand(
                condition=condition,
                derate_factor=factor,
                min_lux=b_min_lux,
                max_lux=b_max_lux,
                mean_lux=b_mean_lux,
                min_nits=b_min_nits,
                max_nits=b_max_nits,
                mean_nits=b_mean_nits,
                mean_foot_lamberts=nits_to_foot_lamberts(b_mean_nits),
            )

        rated_band = make_band("rated", 1.0)
        typical_band = make_band("typical", derate_chain.operational_typical_factor)
        worst_case_band = make_band("worst_case", derate_chain.operational_worst_case_factor)

    if assumptions is None:
        assumptions = assumptions_for_blend_model(BlendModel.RAW, derate_chain=derate_chain)

    return BrightnessReport(
        sample_count=len(values),
        min_lux=lo,
        max_lux=hi,
        mean_lux=mean,
        min_nits=luminance_nits(lo, screen_gain),
        max_nits=luminance_nits(hi, screen_gain),
        mean_nits=luminance_nits(mean, screen_gain),
        mean_foot_lamberts=nits_to_foot_lamberts(luminance_nits(mean, screen_gain)),
        uniformity=uniformity,
        screen_gain=screen_gain,
        assumptions=list(assumptions),
        derate_chain=derate_chain,
        rated_band=rated_band,
        typical_band=typical_band,
        worst_case_band=worst_case_band,
    )


def brightness_warnings(report: BrightnessReport) -> list[str]:
    """Plain-language flags on a brightness result."""
    out: list[str] = []
    if report.mean_nits < CINEMA_WHITE_NITS:
        out.append(
            f"mean {report.mean_nits:.0f} nits is below the ~{CINEMA_WHITE_NITS:.0f} "
            "nit cinema-white reference; expect a dim image in anything but a dark room"
        )
    elif report.mean_nits < PRESENTATION_NITS_MIN:
        out.append(
            f"mean {report.mean_nits:.0f} nits suits a darkened room only; "
            f"presentation spaces usually target {PRESENTATION_NITS_MIN:.0f}-"
            f"{PRESENTATION_NITS_MAX:.0f} nits"
        )
    if report.uniformity < 0.5 and report.sample_count > 1:
        out.append(
            f"illuminance uniformity {report.uniformity:.2f} (min/max) is poor; "
            "check incidence angles and overlap balance"
        )
    if (
        report.worst_case_band
        and report.worst_case_band.mean_nits < CINEMA_WHITE_NITS
        and report.mean_nits >= CINEMA_WHITE_NITS
    ):
        out.append(
            f"worst-case derated luminance ({report.worst_case_band.mean_nits:.0f} nits) "
            f"falls below cinema-white reference ({CINEMA_WHITE_NITS:.0f} nits) under "
            "production tolerance and aging"
        )
    return out
