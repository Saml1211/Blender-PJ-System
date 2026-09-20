"""Measured-vs-predicted calibration loop.

Increment D: the user records a handful of on-site lux readings (from a
handheld meter) against known wall positions; this module fits a **scalar
correction factor**, the coverage analysis applies it to every prediction,
and the residual stays visible in every report. No tool in the category
closes the design→as-built loop; this one does, honestly.

Fit model
---------
A lux meter on site reads the **total** illuminance at the surface:
projected light plus ambient. The model's prediction for what the meter
reads is therefore ``predicted_projected + ambient_lux`` (uniform ambient is
an already-stated assumption). With zero ambient the fit reduces to the
plain ``measured / predicted`` ratio.

The factor is the ratio of means, ``Σ measured / Σ model_total`` — the
standard flux-weighted scalar-gain fit. Per-reading ratios give the
dispersion statistics that are always reported, never acted on: garbage
readings in are *visible*, not laundered.

ADR 0001: pure Python, no bpy. ADR 0002: the disclaimer refuses
"verified"/"calibrated" language by construction — a scalar fit from three
handheld readings is a correction, not a certification.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .errors import ProjectionError, require_finite

#: Minimum usable readings for a fit (the increment spec's own floor).
MIN_READINGS = 3

CALIBRATION_DISCLAIMER = (
    "Scalar correction factor fitted from on-site lux readings; residual "
    "dispersion is reported above and is expected. The photometry remains a "
    "first-order estimate - this is not calibration certification and does "
    "not verify the predictions."
)


@dataclass(frozen=True)
class CalibrationReading:
    """One on-site lux reading at a known wall position.

    ``(s, z)`` uses the same wall coordinates every report already prints:
    ``s`` is the arc distance from the wall's left edge, ``z`` the height
    above its base.
    """

    label: str
    s: float
    z: float
    measured_lux: float

    def __post_init__(self) -> None:
        require_finite("reading arc position", self.s)
        require_finite("reading height", self.z)
        require_finite("measured lux", self.measured_lux)
        if self.measured_lux < 0.0:
            raise ProjectionError(f"measured lux must not be negative, got {self.measured_lux}")


@dataclass(frozen=True)
class CalibrationFit:
    """A fitted scalar correction with its residual statistics attached.

    ``factor`` scales projected illuminance; ambient illuminance does not
    scale, which keeps the effective-contrast recomputation physically
    correct. ``samples`` keeps the (reading, predicted-projected) pairs so
    every report can show the residual directly.
    """

    factor: float
    reading_count: int
    readings_used: tuple[CalibrationReading, ...]
    excluded: tuple[tuple[CalibrationReading, str], ...] = ()
    samples: tuple[tuple[CalibrationReading, float], ...] = ()
    mean_ratio: float = 0.0
    ratio_std: float = 0.0
    ratio_cv: float = 0.0
    min_ratio: float = 0.0
    max_ratio: float = 0.0
    worst_residual_pct: float = 0.0
    ambient_lux: float = 0.0
    disclaimer: str = CALIBRATION_DISCLAIMER

    def apply(self, projected_lux: float) -> float:
        """Scale a projected illuminance by the fitted factor."""
        return projected_lux * self.factor


def fit_calibration(
    pairs: Sequence[tuple[CalibrationReading, float]],
    ambient_lux: float = 0.0,
    min_readings: int = MIN_READINGS,
) -> CalibrationFit:
    """Fit a scalar correction from (reading, predicted-projected-lux) pairs.

    Raises :class:`ProjectionError` when fewer than ``min_readings`` usable
    readings remain after exclusions — the loud, spec-mandated floor. Readings
    are excluded (with a stated reason each) when their prediction is zero
    (unlit or fully occluded position), their measured value is non-positive,
    or either value is non-finite.
    """
    require_finite("ambient lux", ambient_lux)
    if ambient_lux < 0.0:
        raise ProjectionError(f"ambient lux must not be negative, got {ambient_lux}")

    used: list[tuple[CalibrationReading, float, float]] = []
    excluded: list[tuple[CalibrationReading, str]] = []
    for reading, predicted in pairs:
        if not math.isfinite(predicted):
            excluded.append((reading, "predicted illuminance is not a finite number"))
            continue
        if predicted <= 0.0:
            excluded.append(
                (reading, "predicted illuminance is zero (unlit or occluded position)")
            )
            continue
        if reading.measured_lux <= 0.0:
            excluded.append((reading, "measured lux must be positive"))
            continue
        model_total = predicted + ambient_lux
        used.append((reading, predicted, model_total))

    if len(used) < min_readings:
        raise ProjectionError(
            f"calibration needs at least {min_readings} usable readings with a "
            f"positive prediction, got {len(used)} - running uncalibrated"
        )

    sum_measured = sum(r.measured_lux for r, _p, _t in used)
    sum_model = sum(model for _r, _p, model in used)
    factor = sum_measured / sum_model

    ratios = [r.measured_lux / model for r, _p, model in used]
    mean_ratio = sum(ratios) / len(ratios)
    ratio_std = math.sqrt(sum((v - mean_ratio) ** 2 for v in ratios) / len(ratios))
    ratio_cv = (ratio_std / mean_ratio) if mean_ratio > 0.0 else 0.0

    worst = 0.0
    for reading, _predicted, model in used:
        residual = reading.measured_lux - factor * model
        worst = max(worst, abs(residual) / model)

    return CalibrationFit(
        factor=factor,
        reading_count=len(used),
        readings_used=tuple(r for r, _p, _t in used),
        excluded=tuple(excluded),
        samples=tuple((reading, predicted) for reading, predicted, _t in used),
        mean_ratio=mean_ratio,
        ratio_std=ratio_std,
        ratio_cv=ratio_cv,
        min_ratio=min(ratios),
        max_ratio=max(ratios),
        worst_residual_pct=worst,
        ambient_lux=ambient_lux,
    )
