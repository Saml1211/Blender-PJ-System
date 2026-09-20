"""Tests for the angle-aware gain profile family (SMPTE RP 94 idealisations).

Increment C: replaces the scalar Lambertian gain assumption with a
``gain(viewing_angle)`` profile family — Lambertian (today's scalar model),
peaked (lobe on the screen normal), retroflective (lobe toward the projector).

The parametric curves are idealisations, not measured vendor data: the RP 94
medium-confidence disclaimer must surface with every derived number (ADR 0002).
"""

from __future__ import annotations

import math

import pytest

from blender_projection_system.core import photometry as ph
from blender_projection_system.core.coverage import analyze_coverage, format_report
from blender_projection_system.core.discas import audit_viewers
from blender_projection_system.core.errors import ProjectionError
from blender_projection_system.core.footprint import compute_footprint
from blender_projection_system.core.gain import (
    GAIN_CITATION,
    GAIN_PROFILE_DISCLAIMER,
    RP94_FLAT_WALL_MAX_PEAK,
    GainModel,
    GainProfile,
    assumptions_for_gain_profile,
    factor_at,
    flat_wall_gain_warning,
    gain_at,
    gain_model_label,
    lobe_axis,
    viewing_angle_deg,
)
from blender_projection_system.core.pose import look_at
from blender_projection_system.core.report_export import report_to_dict
from blender_projection_system.core.surfaces import CylindricalWall, PlanarWall
from blender_projection_system.core.throw import ProjectorSpec

# -- curve shape -------------------------------------------------------------


def test_lambertian_is_constant_at_every_angle():
    profile = GainProfile.lambertian(1.5)
    assert profile.kind is GainModel.LAMBERTIAN
    for angle in (0.0, 15.0, 45.0, 89.0, 120.0):
        assert gain_at(profile, angle) == pytest.approx(1.5)
        assert factor_at(profile, angle) == pytest.approx(1.0)


def test_peaked_curve_hits_half_the_peak_exactly_at_the_half_gain_angle():
    profile = GainProfile.peaked(peak_gain=2.0, half_gain_angle_deg=30.0, off_axis_gain=0.6)
    assert gain_at(profile, 0.0) == pytest.approx(2.0)
    assert gain_at(profile, 30.0) == pytest.approx(1.0)  # peak / 2, by construction
    assert gain_at(profile, 89.0) == pytest.approx(0.6)
    assert factor_at(profile, 30.0) == pytest.approx(0.5)
    assert factor_at(profile, 0.0) == pytest.approx(1.0)


def test_peaked_curve_is_monotonic_and_bounded():
    profile = GainProfile.peaked(2.0, 25.0, 0.5)
    values = [gain_at(profile, a) for a in range(0, 91, 5)]
    assert values == sorted(values, reverse=True)
    assert values[0] == pytest.approx(2.0)
    assert values[-1] == pytest.approx(0.5)


def test_peaked_curve_is_symmetric_about_the_lobe_axis():
    profile = GainProfile.peaked(2.0, 30.0, 0.6)
    assert gain_at(profile, -30.0) == pytest.approx(gain_at(profile, 30.0))
    assert gain_at(profile, -75.0) == pytest.approx(gain_at(profile, 75.0))


def test_angles_beyond_quadrant_clamp_to_the_floor():
    profile = GainProfile.peaked(2.0, 30.0, 0.6)
    assert gain_at(profile, 90.0) == pytest.approx(0.6)
    assert gain_at(profile, 170.0) == pytest.approx(0.6)


def test_retroflective_shares_the_peaked_curve_shape():
    retro = GainProfile.retroflective(2.5, 20.0, 0.4)
    assert retro.kind is GainModel.RETROFLECTIVE
    assert gain_at(retro, 0.0) == pytest.approx(2.5)
    assert gain_at(retro, 20.0) == pytest.approx(1.25)
    assert gain_at(retro, 90.0) == pytest.approx(0.4)


# -- parameter validation (loud, ADR 0002) ------------------------------------


@pytest.mark.parametrize(
    ("peak", "half", "floor"),
    [
        (1.4, 30.0, 1.0),  # floor above half the peak: half-gain unreachable
        (2.0, 30.0, 1.0),
        (2.0, 30.0, 0.0),
        (2.0, 30.0, -0.5),
        (2.0, 0.0, 0.5),
        (2.0, 90.0, 0.5),
        (2.0, 120.0, 0.5),
        (0.0, 30.0, 0.5),
        (-2.0, 30.0, 0.5),
    ],
)
def test_peaked_rejects_invalid_parameters(peak, half, floor):
    with pytest.raises(ProjectionError):
        GainProfile.peaked(peak, half, floor)


@pytest.mark.parametrize(
    ("peak", "half", "floor"),
    [
        (2.0, 30.0, 1.5),
        (2.0, 30.0, 0.0),
        (2.0, -10.0, 0.5),
        (2.0, 95.0, 0.5),
    ],
)
def test_retroflective_rejects_invalid_parameters(peak, half, floor):
    with pytest.raises(ProjectionError):
        GainProfile.retroflective(peak, half, floor)


@pytest.mark.parametrize("gain", [0.0, -1.0])
def test_lambertian_rejects_non_positive_gain(gain):
    with pytest.raises(ProjectionError):
        GainProfile.lambertian(gain)


def test_rejection_message_names_the_half_gain_convention():
    with pytest.raises(ProjectionError, match="half-gain"):
        GainProfile.peaked(1.4, 30.0, 1.0)


# -- lobe axis geometry -------------------------------------------------------


def test_peaked_lobe_axis_is_the_surface_normal():
    profile = GainProfile.peaked(2.0, 30.0, 0.6)
    axis = lobe_axis(profile, (0.0, 0.0, 1.5), (0.0, 1.0, 0.0), (0.0, -5.0, 3.0))
    assert axis == pytest.approx((0.0, 1.0, 0.0))


def test_retroflective_lobe_axis_points_at_the_projector():
    profile = GainProfile.retroflective(2.0, 30.0, 0.6)
    # (0,-5,3) normalized: norm = sqrt(34).
    axis = lobe_axis(profile, (0.0, 0.0, 1.5), (0.0, 1.0, 0.0), (0.0, -5.0, 4.5))
    assert axis == pytest.approx((0.0, -5.0 / math.sqrt(34.0), 3.0 / math.sqrt(34.0)))


def test_retroflective_requires_the_projector_origin():
    profile = GainProfile.retroflective(2.0, 30.0, 0.6)
    with pytest.raises(ProjectionError, match="projector"):
        lobe_axis(profile, (0.0, 0.0, 1.5), (0.0, 1.0, 0.0), None)


def test_lambertian_has_no_lobe_axis():
    assert lobe_axis(GainProfile.lambertian(1.0), (0, 0, 0), (0, 1, 0), None) is None


def test_viewing_angle_measures_off_the_lobe_axis():
    axis = (0.0, 0.0, 1.0)
    assert viewing_angle_deg((0.0, 0.0, 5.0), (0.0, 0.0, 0.0), axis) == pytest.approx(0.0)
    assert viewing_angle_deg((1.0, 0.0, 1.0), (0.0, 0.0, 0.0), axis) == pytest.approx(45.0)
    assert viewing_angle_deg((0.0, -2.0, 0.0), (0.0, 0.0, 0.0), axis) == pytest.approx(90.0)


# -- RP 94 warnings -----------------------------------------------------------


def test_flat_wall_warning_fires_above_13_peak_on_a_planar_wall():
    profile = GainProfile.peaked(2.0, 30.0, 0.6)
    wall = PlanarWall(base_center=(0.0, 0.0, 0.0), width=6.0, height=3.0, facing=(0.0, 1.0, 0.0))
    warning = flat_wall_gain_warning(profile, wall)
    assert warning is not None
    assert "RP 94" in warning
    assert "1.3" in warning
    assert "not modelled" in warning


def test_flat_wall_warning_silent_on_a_curved_wall():
    profile = GainProfile.peaked(2.0, 30.0, 0.6)
    wall = CylindricalWall(
        base_center=(0.0, 0.0, 0.0),
        radius=8.0,
        height=3.0,
        angle_start=math.radians(-45.0),
        angle_end=math.radians(45.0),
    )
    assert flat_wall_gain_warning(profile, wall) is None


def test_flat_wall_warning_silent_below_the_rp94_threshold():
    profile = GainProfile.peaked(1.2, 30.0, 0.5)
    wall = PlanarWall(base_center=(0.0, 0.0, 0.0), width=6.0, height=3.0, facing=(0.0, 1.0, 0.0))
    assert flat_wall_gain_warning(profile, wall) is None


def test_rp94_threshold_constant():
    assert RP94_FLAT_WALL_MAX_PEAK == pytest.approx(1.3)


# -- assumptions and disclaimer (ADR 0002 medium-confidence flag) --------------


def test_profile_assumption_line_carries_rp94_and_medium_confidence():
    profile = GainProfile.peaked(2.0, 30.0, 0.6)
    line = assumptions_for_gain_profile(profile)
    assert "RP 94" in line
    assert "2.00" in line
    assert "30" in line
    assert "medium confidence" in line.lower()
    assert GAIN_CITATION in line


def test_retroflective_assumption_line_names_the_lobe_reference():
    profile = GainProfile.retroflective(2.0, 30.0, 0.6)
    line = assumptions_for_gain_profile(profile)
    assert "retroflective" in line.lower()
    assert "projector" in line.lower()


def test_gain_profile_disclaimer_is_loud():
    text = GAIN_PROFILE_DISCLAIMER.lower()
    assert "medium confidence" in text
    assert "ideal" in text
    assert "not" in text and "measured" in text


def test_blend_assumptions_replace_the_gain_line_for_a_profile():
    profile = GainProfile.peaked(2.0, 30.0, 0.6)
    lines = ph.assumptions_for_blend_model(ph.BlendModel.RAW, gain_profile=profile)
    assert not any("Lambertian screen at the stated gain" in a for a in lines)
    assert any("RP 94" in a for a in lines)


def test_blend_assumptions_keep_the_scalar_line_without_a_profile():
    lines = ph.assumptions_for_blend_model(ph.BlendModel.RAW)
    assert any("Lambertian screen at the stated gain" in a for a in lines)


def test_lambertian_profile_keeps_the_scalar_line():
    lines = ph.assumptions_for_blend_model(
        ph.BlendModel.RAW, gain_profile=GainProfile.lambertian(1.5)
    )
    assert any("Lambertian screen at the stated gain" in a for a in lines)


def test_gain_model_label():
    assert gain_model_label(GainModel.LAMBERTIAN) == "Lambertian"
    assert gain_model_label(GainModel.PEAKED) == "Peaked"
    assert gain_model_label(GainModel.RETROFLECTIVE) == "Retroflective"


# -- DISCAS off-axis correction -----------------------------------------------


def _viewers():
    # Normal is (0, -1, 0): OnAxis sits on it; AtHalfGain sits exactly on the
    # 30° cone boundary (atan(10·tan30° / 10) = 30°); FarSide sits at 53.1°.
    return [
        ("OnAxis", (0.0, -10.0, 1.5)),
        ("AtHalfGain", (10.0 * math.tan(math.radians(30.0)), -10.0, 1.5)),
        ("FarSide", (8.0, -6.0, 1.5)),
    ]


def test_audit_without_profile_reports_no_viewing_angle_falloff():
    # Corrected Lambertian behaviour: luminance is view-independent. The old
    # `mean · cos θ` falloff was physically wrong and is replaced here
    # deliberately (increment C).
    report = audit_viewers(
        viewers=_viewers(),
        screen_center=(0.0, 0.0, 1.5),
        screen_normal=(0.0, -1.0, 0.0),
        image_height=2.5,
        mean_screen_nits=200.0,
    )
    for viewer in report.viewers:
        assert viewer.perceived_nits == pytest.approx(200.0)


def test_audit_with_peaked_profile_applies_the_gain_curve():
    profile = GainProfile.peaked(2.0, 30.0, 0.6)
    report = audit_viewers(
        viewers=_viewers(),
        screen_center=(0.0, 0.0, 1.5),
        screen_normal=(0.0, -1.0, 0.0),
        image_height=2.5,
        mean_screen_nits=200.0,
        gain_profile=profile,
    )
    by_name = {v.name: v for v in report.viewers}
    assert by_name["OnAxis"].perceived_nits == pytest.approx(200.0)
    # 30° off the normal is exactly the half-gain angle: half the on-axis value.
    assert by_name["AtHalfGain"].perceived_nits == pytest.approx(100.0)
    assert by_name["FarSide"].perceived_nits < 100.0


def test_audit_with_retroflective_profile_aims_the_lobe_at_the_projector():
    profile = GainProfile.retroflective(2.0, 30.0, 0.6)
    # Place the projector along the AtHalfGain viewer's direction from the
    # screen centre, so the lobe follows the source rather than the normal:
    # centre + 10·(0.5, −0.866, 0) = (5.0, −8.66, 1.5).
    projector = (5.0, -10.0 * math.sqrt(3.0) / 2.0, 1.5)
    report = audit_viewers(
        viewers=_viewers(),
        screen_center=(0.0, 0.0, 1.5),
        screen_normal=(0.0, -1.0, 0.0),
        image_height=2.5,
        mean_screen_nits=200.0,
        gain_profile=profile,
        projector_origin=projector,
    )
    by_name = {v.name: v for v in report.viewers}
    # The viewer on the projector's bearing sits on the lobe axis; the viewer
    # on the *normal* is now 30° off it and sees only half.
    assert by_name["AtHalfGain"].perceived_nits == pytest.approx(200.0)
    assert by_name["OnAxis"].perceived_nits == pytest.approx(100.0)


def test_audit_retroflective_without_projector_origin_raises():
    profile = GainProfile.retroflective(2.0, 30.0, 0.6)
    with pytest.raises(ProjectionError, match="projector"):
        audit_viewers(
            viewers=_viewers(),
            screen_center=(0.0, 0.0, 1.5),
            screen_normal=(0.0, -1.0, 0.0),
            image_height=2.5,
            mean_screen_nits=200.0,
            gain_profile=profile,
        )


def test_audit_lambertian_profile_matches_the_scalar_case():
    report = audit_viewers(
        viewers=_viewers(),
        screen_center=(0.0, 0.0, 1.5),
        screen_normal=(0.0, -1.0, 0.0),
        image_height=2.5,
        mean_screen_nits=200.0,
        gain_profile=GainProfile.lambertian(2.0),
    )
    for viewer in report.viewers:
        assert viewer.perceived_nits == pytest.approx(200.0)


# -- coverage integration ------------------------------------------------------


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


def test_analysis_accepts_a_peaked_profile_and_records_it(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    profile = GainProfile.peaked(2.0, 30.0, 0.6)
    report = analyze_coverage([fp], curved_wall, grid_s=40, grid_z=12, gain_profile=profile)

    assert report.gain_profile is profile
    assert report.brightness is not None
    assert report.brightness.screen_gain == pytest.approx(2.0)
    assert any("RP 94" in a for a in report.brightness.assumptions)
    assert not any("no half-gain" in w for w in report.warnings)


def test_analysis_scalar_path_is_unchanged_when_no_profile(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    report = analyze_coverage([fp], curved_wall, grid_s=40, grid_z=12, screen_gain=1.5)

    assert report.gain_profile is None
    assert report.brightness.screen_gain == pytest.approx(1.5)
    assert any("Lambertian screen at the stated gain" in a for a in report.brightness.assumptions)


def test_analysis_warns_on_flat_wall_high_gain():
    wall = PlanarWall(base_center=(0.0, 0.0, 0.0), width=6.0, height=3.0, facing=(0.0, 1.0, 0.0))
    spec = ProjectorSpec(throw_ratio=1.5)
    target = wall.point_at(wall.width * 0.5, 1.5)
    # The facing normal points at the projectors: stand on that side.
    origin = (
        target[0] + wall.facing[0] * 4.0,
        target[1] + wall.facing[1] * 4.0,
        target[2],
    )
    fp = compute_footprint(look_at(origin, target), spec, wall, samples=9, name="P1")
    profile = GainProfile.peaked(2.0, 30.0, 0.6)
    report = analyze_coverage([fp], wall, grid_s=40, grid_z=12, gain_profile=profile)

    assert fp.hit_ratio > 0.0
    assert any("RP 94" in w and "flat wall" in w for w in report.warnings)


def test_analysis_flags_viewers_outside_the_half_gain_cone(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    profile = GainProfile.peaked(2.0, 20.0, 0.6)
    mid_s = curved_wall.arc_length / 2
    center = curved_wall.point_at(mid_s, 1.5)
    normal = curved_wall.normal_at_s(mid_s)
    far = (
        center[0] + normal[0] * 10.0 + 12.0,  # well outside a 20-degree cone
        center[1] + normal[1] * 10.0,
        center[2],
    )
    near = (
        center[0] + normal[0] * 10.0,
        center[1] + normal[1] * 10.0,
        center[2],
    )
    report = analyze_coverage(
        [fp],
        curved_wall,
        grid_s=40,
        grid_z=12,
        gain_profile=profile,
        viewers=[("Near", near), ("Far", far)],
    )
    assert report.discas is not None
    assert any("half-gain cone" in w and "Far" in w for w in report.warnings)
    assert not any("half-gain cone" in w and "Near" in w for w in report.warnings)


def test_format_report_carries_the_gain_profile_line(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    profile = GainProfile.peaked(2.0, 30.0, 0.6)
    report = analyze_coverage([fp], curved_wall, grid_s=40, grid_z=12, gain_profile=profile)
    lines = format_report(report)
    joined = "\n".join(lines)
    assert "Gain profile" in joined
    assert "Peaked" in joined
    assert "RP 94" in joined
    assert "medium confidence" in joined.lower()


def test_report_export_carries_the_gain_profile_block(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    profile = GainProfile.peaked(2.0, 30.0, 0.6)
    report = analyze_coverage([fp], curved_wall, grid_s=40, grid_z=12, gain_profile=profile)
    data = report_to_dict(report)
    block = data["gain_profile"]
    assert block["kind"] == "peaked"
    assert block["peak_gain"] == pytest.approx(2.0)
    assert block["half_gain_angle_deg"] == pytest.approx(30.0)
    assert block["off_axis_gain"] == pytest.approx(0.6)
    assert "medium confidence" in block["disclaimer"].lower()


def test_report_export_omits_gain_block_without_a_profile(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(curved_wall, curved_wall.arc_length / 2, 4.0, spec, "P1")
    report = analyze_coverage([fp], curved_wall, grid_s=40, grid_z=12)
    assert "gain_profile" not in report_to_dict(report)
