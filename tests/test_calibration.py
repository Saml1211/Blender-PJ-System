"""Tests for the measured-vs-predicted calibration loop (increment D).

The user records on-site lux readings at known wall positions; core fits a
scalar correction factor, the analysis applies it, and the residual stays
visible in every report. Never claims the photometry is verified (ADR 0002).
"""

from __future__ import annotations

import math

import pytest

from blender_projection_system.core.calibration import (
    CALIBRATION_DISCLAIMER,
    MIN_READINGS,
    CalibrationFit,
    CalibrationReading,
    fit_calibration,
)
from blender_projection_system.core.coverage import (
    analyze_coverage,
    format_report,
    predict_illuminance_at,
)
from blender_projection_system.core.errors import ProjectionError
from blender_projection_system.core.footprint import compute_footprint
from blender_projection_system.core.photometry import illuminance_at
from blender_projection_system.core.pose import look_at
from blender_projection_system.core.report_export import report_to_dict
from blender_projection_system.core.surfaces import CylindricalWall, PlanarWall
from blender_projection_system.core.throw import ProjectorSpec

# -- fit arithmetic -----------------------------------------------------------


def _readings():
    return [
        CalibrationReading("A", 1.0, 1.5, 110.0),
        CalibrationReading("B", 2.0, 1.5, 220.0),
        CalibrationReading("C", 3.0, 1.5, 330.0),
    ]


def _pairs(measured=(110.0, 220.0, 330.0), predicted=(100.0, 200.0, 300.0)):
    readings = _readings()
    adjusted = [CalibrationReading(r.label, r.s, r.z, m) for r, m in zip(readings, measured, strict=False)]
    return list(zip(adjusted, predicted, strict=True))


def test_factor_is_the_ratio_of_means():
    fit = fit_calibration(_pairs())
    assert fit.factor == pytest.approx(660.0 / 600.0)
    assert fit.factor == pytest.approx(1.1)
    assert fit.reading_count == 3


def test_perfect_readings_give_zero_dispersion_and_zero_residual():
    fit = fit_calibration(_pairs())
    assert fit.mean_ratio == pytest.approx(1.1)
    assert fit.ratio_std == pytest.approx(0.0, abs=1e-9)
    assert fit.ratio_cv == pytest.approx(0.0, abs=1e-9)
    assert fit.min_ratio == pytest.approx(1.1)
    assert fit.max_ratio == pytest.approx(1.1)
    assert fit.worst_residual_pct == pytest.approx(0.0, abs=1e-9)


def test_dispersion_statistics_are_exact():
    fit = fit_calibration(_pairs(measured=(100.0, 200.0, 450.0), predicted=(100.0, 200.0, 300.0)))
    # factor = 750 / 600 = 1.25; ratios 1.0, 1.0, 1.5
    assert fit.factor == pytest.approx(1.25)
    assert fit.mean_ratio == pytest.approx(3.5 / 3.0)
    assert fit.ratio_std == pytest.approx(0.235702, rel=1e-5)
    assert fit.ratio_cv == pytest.approx(0.235702 / 1.1666667, rel=1e-5)
    assert fit.min_ratio == pytest.approx(1.0)
    assert fit.max_ratio == pytest.approx(1.5)
    # residuals vs the fitted model: -25, -50, +75 over 100/200/300 model totals
    assert fit.worst_residual_pct == pytest.approx(0.25)


def test_apply_scales_projected_illuminance():
    fit = fit_calibration(_pairs())
    assert fit.apply(100.0) == pytest.approx(110.0)


def test_ambient_is_part_of_the_model_the_meter_reads():
    # predicted 100 projected + 20 ambient = 120 model total; measured 120 -> factor 1.0
    fit = fit_calibration(_pairs(measured=(120.0, 220.0, 320.0)), ambient_lux=20.0)
    assert fit.factor == pytest.approx(1.0)
    assert fit.ambient_lux == pytest.approx(20.0)


def test_fit_keeps_the_samples_for_the_visible_residual():
    fit = fit_calibration(_pairs())
    assert len(fit.samples) == 3
    for (reading, predicted), _sample in zip(_pairs(), fit.samples, strict=True):
        assert reading.label == _sample[0].label
        assert predicted == pytest.approx(_sample[1])


def test_calibration_disclaimer_refuses_verified_language():
    text = CALIBRATION_DISCLAIMER.lower()
    assert "not" in text
    assert "verif" in text
    assert "scalar" in text


# -- exclusions and the >=3 floor ---------------------------------------------


def test_zero_prediction_is_excluded_with_a_reason():
    pairs = _pairs() + [(CalibrationReading("Dark", 4.0, 0.1, 50.0), 0.0)]
    fit = fit_calibration(pairs)
    assert fit.reading_count == 3
    assert len(fit.excluded) == 1
    excluded_reading, reason = fit.excluded[0]
    assert excluded_reading.label == "Dark"
    assert "predicted" in reason.lower()


def test_non_positive_measured_is_excluded_with_a_reason():
    # A fourth pair keeps the remaining three above the >=3 usable floor.
    pairs = _pairs() + [(CalibrationReading("D", 4.0, 1.5, 0.0), 400.0)]
    fit = fit_calibration(pairs)
    assert fit.reading_count == 3
    assert len(fit.excluded) == 1
    excluded_reading, reason = fit.excluded[0]
    assert excluded_reading.label == "D"
    assert "measured" in reason.lower()


def test_fewer_than_three_usable_readings_is_rejected():
    with pytest.raises(ProjectionError, match="3"):
        fit_calibration(_pairs()[:2])


def test_min_readings_constant_matches_the_spec_floor():
    assert MIN_READINGS == 3


def test_rejection_message_names_the_running_uncalibrated_outcome():
    with pytest.raises(ProjectionError, match="uncalibrated|usable"):
        fit_calibration(_pairs()[:1])


def test_reading_rejects_non_finite_position():
    with pytest.raises(ProjectionError):
        CalibrationReading("X", float("nan"), 1.5, 100.0)
    with pytest.raises(ProjectionError):
        CalibrationReading("X", 1.0, float("inf"), 100.0)
    with pytest.raises(ProjectionError):
        CalibrationReading("X", 1.0, 1.5, float("nan"))


def test_fit_is_a_frozen_dataclass_with_defaults():
    fit = fit_calibration(_pairs())
    assert isinstance(fit, CalibrationFit)
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        fit.factor = 2.0  # type: ignore[misc]


# -- prediction at a wall position ---------------------------------------------


@pytest.fixture
def curved_wall() -> CylindricalWall:
    return CylindricalWall(
        base_center=(0.0, 0.0, 0.0),
        radius=8.0,
        height=3.0,
        angle_start=math.radians(-45.0),
        angle_end=math.radians(45.0),
    )


def _projector_at(wall, arc_center, standoff, spec, name, z=None):
    z = wall.height / 2 if z is None else z
    target = wall.point_at(arc_center, z)
    normal = wall.normal_at_s(arc_center)
    origin = (target[0] + normal[0] * standoff, target[1] + normal[1] * standoff, z)
    return compute_footprint(look_at(origin, target), spec, wall, samples=9, name=name)


def test_prediction_matches_the_per_cell_illuminance_formula(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    s = curved_wall.arc_length / 2
    z = 1.5
    predicted = predict_illuminance_at([fp], curved_wall, s, z)
    assert predicted > 0.0
    # The prediction must be the raster's own per-cell computation: distance
    # and incidence from the lens to the sample point, through illuminance_at.
    point = curved_wall.point_at(s, z)
    normal = curved_wall.normal_at_s(s)
    to_lens = (
        fp.pose.origin[0] - point[0],
        fp.pose.origin[1] - point[1],
        fp.pose.origin[2] - point[2],
    )
    d = math.sqrt(sum(c * c for c in to_lens))
    unit = (to_lens[0] / d, to_lens[1] / d, to_lens[2] / d)
    incidence = math.acos(
        max(-1.0, min(1.0, unit[0] * normal[0] + unit[1] * normal[1] + unit[2] * normal[2]))
    )
    expected = illuminance_at(fp.spec, d, incidence)
    assert predicted == pytest.approx(expected, rel=1e-6)


def test_prediction_is_zero_off_the_image(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    # The far edge of the wall is outside the single image.
    predicted = predict_illuminance_at([fp], curved_wall, curved_wall.arc_length - 0.01, 0.1)
    assert predicted == pytest.approx(0.0)


def test_prediction_rejects_positions_outside_the_wall(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    with pytest.raises(ProjectionError, match="outside the wall"):
        predict_illuminance_at([fp], curved_wall, curved_wall.arc_length + 1.0, 1.5)
    with pytest.raises(ProjectionError, match="outside the wall"):
        predict_illuminance_at([fp], curved_wall, 1.0, curved_wall.height + 1.0)


def test_prediction_respects_occlusion(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    s = curved_wall.arc_length / 2
    clear = predict_illuminance_at([fp], curved_wall, s, 1.5)
    blocked = predict_illuminance_at(
        [fp], curved_wall, s, 1.5, occlusion_caster=lambda origin, direction, reach: True
    )
    assert clear > 0.0
    assert blocked == pytest.approx(0.0)


# -- analysis integration -------------------------------------------------------


def test_analysis_applies_the_fit_and_keeps_the_residual(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    raw = analyze_coverage([fp], curved_wall, grid_s=40, grid_z=12)
    assert raw.brightness is not None
    # The 1.25-factor fixture: measured (100, 200, 450) over predicted (100, 200, 300).
    fit = fit_calibration(_pairs(measured=(100.0, 200.0, 450.0), predicted=(100.0, 200.0, 300.0)))
    assert fit.factor == pytest.approx(1.25)
    corrected = analyze_coverage([fp], curved_wall, grid_s=40, grid_z=12, calibration=fit)
    assert corrected.calibration is fit
    assert corrected.brightness.mean_lux == pytest.approx(raw.brightness.mean_lux * fit.factor)
    assert corrected.brightness.min_lux == pytest.approx(raw.brightness.min_lux * fit.factor)
    assert corrected.brightness.mean_nits == pytest.approx(raw.brightness.mean_nits * fit.factor)


def test_analysis_without_calibration_is_unchanged(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    report = analyze_coverage([fp], curved_wall, grid_s=40, grid_z=12)
    assert report.calibration is None
    lines = format_report(report)
    assert not any("Calibration:" in line for line in lines)


def test_format_report_carries_the_calibration_block(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    fit = fit_calibration(_pairs(measured=(100.0, 200.0, 450.0), predicted=(100.0, 200.0, 300.0)))
    report = analyze_coverage([fp], curved_wall, grid_s=40, grid_z=12, calibration=fit)
    lines = format_report(report)
    joined = "\n".join(lines)
    assert "Calibration: predictions scaled by" in joined
    assert "Residual:" in joined
    assert "A" in joined and "B" in joined and "C" in joined
    assert "worst residual" in joined
    assert "not" in joined  # disclaimer rides with the block


def test_format_report_lists_excluded_readings(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    pairs = _pairs() + [(CalibrationReading("Dark", 4.0, 0.1, 50.0), 0.0)]
    fit = fit_calibration(pairs)
    report = analyze_coverage([fp], curved_wall, grid_s=40, grid_z=12, calibration=fit)
    joined = "\n".join(format_report(report))
    assert "Excluded 'Dark'" in joined


def test_export_carries_the_calibration_block(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    fit = fit_calibration(_pairs())
    report = analyze_coverage([fp], curved_wall, grid_s=40, grid_z=12, calibration=fit)
    data = report_to_dict(report)
    block = data["calibration"]
    assert block["factor"] == pytest.approx(1.1)
    assert block["reading_count"] == 3
    assert len(block["samples"]) == 3
    assert "verif" in block["disclaimer"].lower() or "calibration" in block["disclaimer"].lower()


def test_export_omits_calibration_without_a_fit(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    report = analyze_coverage([fp], curved_wall, grid_s=40, grid_z=12)
    assert "calibration" not in report_to_dict(report)


def test_calibration_on_a_flat_wall_round_trip():
    wall = PlanarWall(base_center=(0.0, 0.0, 0.0), width=6.0, height=3.0, facing=(0.0, 1.0, 0.0))
    spec = ProjectorSpec(throw_ratio=1.5)
    target = wall.point_at(wall.width * 0.5, 1.5)
    origin = (target[0] + wall.facing[0] * 4.0, target[1] + wall.facing[1] * 4.0, target[2])
    fp = compute_footprint(look_at(origin, target), spec, wall, samples=9, name="P1")
    # D = 4 m at TR 1.5 -> image width 2.67 m centred at s = 3.0 on this
    # 6 m wall (point_at maps s to x = s - width/2). Keep readings inside
    # the lit band: s in [1.67, 4.33].
    s_mid = wall.width * 0.5
    predicted_mid = predict_illuminance_at([fp], wall, s_mid, 1.5)
    assert predicted_mid > 0.0
    # Symmetric readings with a uniform +20% meter bias.
    readings = [
        CalibrationReading("L", s_mid - 0.3, 1.5, 0.0),
        CalibrationReading("M", s_mid, 1.5, 0.0),
        CalibrationReading("R", s_mid + 0.3, 1.5, 0.0),
    ]
    pairs = []
    for reading in readings:
        predicted = predict_illuminance_at([fp], wall, reading.s, reading.z)
        assert predicted > 0.0
        # The meter reads +20% above the model at every position.
        measured = CalibrationReading(reading.label, reading.s, reading.z, predicted * 1.2)
        pairs.append((measured, predicted))
    fit = fit_calibration(pairs)
    assert fit.factor == pytest.approx(1.2, rel=1e-6)
    assert fit.worst_residual_pct == pytest.approx(0.0, abs=1e-6)
