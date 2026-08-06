"""Brightness and illuminance estimates.

Stated assumptions
------------------
These are first-order engineering estimates, not a photometric simulation.
Every function here assumes:

1. **Uniform intensity across the frustum.** Real projectors fall off toward
   the corners; ANSI 9-point uniformity of 70-90% is typical, so corner
   illuminance is optimistic here by roughly that margin.
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
from collections.abc import Iterable
from dataclasses import dataclass

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
    """Luminous intensity in candela (lm/sr) under the uniformity assumption."""
    omega = frustum_solid_angle(spec)
    if omega <= 0.0:
        raise ProjectionError("degenerate frustum: solid angle is zero")
    return spec.lumens / omega


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
    """Flux spread evenly over a flat image: ``E = lumens / area``.

    This is the number an AV designer computes by hand, and it is the *mean*
    illuminance across a flat screen. It is not the on-axis value - see
    :func:`center_to_mean_ratio`.
    """
    require_positive("image area", image_area)
    return spec.lumens / image_area


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


#: The assumption list surfaced in the UI and reports, kept short on purpose.
ASSUMPTIONS: list[str] = [
    "uniform intensity across the frustum (real corner falloff not modelled)",
    "rated lumens delivered in full (no lamp ageing or eco-mode derate)",
    "Lambertian screen at the stated gain",
    "no ambient light and no inter-reflection",
    "overlapping projectors add linearly (no blend-processor ramp)",
]


def summarize_brightness(
    lux_values: Iterable[float],
    screen_gain: float = 1.0,
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
        assumptions=list(ASSUMPTIONS),
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
    return out
