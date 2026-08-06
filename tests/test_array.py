"""Tests for the ceiling-mounted projector array planner."""

from __future__ import annotations

import math

import pytest

from blender_projection_system.core.array import (
    MODE_LEVEL,
    MODE_TILT,
    arc_centers,
    arc_width_per_projector,
    format_placement,
    plan_array,
    plan_projector,
    solve_standoff,
)
from blender_projection_system.core.coverage import analyze_coverage
from blender_projection_system.core.errors import ProjectionError
from blender_projection_system.core.surfaces import CylindricalWall
from blender_projection_system.core.throw import ProjectorSpec
from blender_projection_system.core.vectors import distance as vec_distance


@pytest.fixture
def wall() -> CylindricalWall:
    """A realistic curved feature wall: 8 m radius, 90 degrees, 3 m tall."""
    return CylindricalWall(
        base_center=(0.0, 0.0, 0.0),
        radius=8.0,
        height=3.0,
        angle_start=math.radians(-45.0),
        angle_end=math.radians(45.0),
        name="FeatureWall",
    )


@pytest.fixture
def spec() -> ProjectorSpec:
    return ProjectorSpec(
        throw_ratio=1.2,
        aspect_w=16,
        aspect_h=9,
        lumens=7000.0,
        max_lens_shift_v=0.6,
    )


# -- arc arithmetic -------------------------------------------------------


def test_a_single_projector_must_cover_the_whole_arc():
    assert arc_width_per_projector(12.0, 1, 0.0) == pytest.approx(12.0)
    assert arc_width_per_projector(12.0, 1, 0.5) == pytest.approx(12.0)


def test_butt_joined_projectors_split_the_arc_evenly():
    assert arc_width_per_projector(12.0, 3, 0.0) == pytest.approx(4.0)
    assert arc_centers(12.0, 3, 0.0) == pytest.approx([2.0, 6.0, 10.0])


def test_overlap_forces_each_projector_to_cover_more():
    plain = arc_width_per_projector(12.0, 3, 0.0)
    overlapped = arc_width_per_projector(12.0, 3, 0.2)
    assert overlapped > plain


def test_the_overlap_formula_tiles_the_wall_exactly():
    arc, count, overlap = 12.0, 4, 0.15
    width = arc_width_per_projector(arc, count, overlap)
    centres = arc_centers(arc, count, overlap)
    assert centres[0] - width / 2 == pytest.approx(0.0)
    assert centres[-1] + width / 2 == pytest.approx(arc)
    # Neighbouring images share exactly the requested fraction.
    shared = (centres[0] + width / 2) - (centres[1] - width / 2)
    assert shared / width == pytest.approx(overlap)


def test_bad_array_inputs_are_rejected():
    with pytest.raises(ProjectionError):
        arc_width_per_projector(12.0, 0, 0.1)
    with pytest.raises(ProjectionError):
        arc_width_per_projector(12.0, 3, 1.0)
    with pytest.raises(ProjectionError):
        arc_width_per_projector(12.0, 3, -0.1)
    with pytest.raises(ProjectionError):
        arc_width_per_projector(0.0, 3, 0.1)


# -- the standoff solve ---------------------------------------------------


def test_the_solver_hits_the_requested_arc_width(wall, spec):
    target = 4.0
    distance, _pose, _spec, achieved = solve_standoff(
        wall, spec, wall.arc_length / 2, 1.5, 3.0, target, mode=MODE_LEVEL
    )
    assert achieved == pytest.approx(target, abs=0.01)
    placement = plan_projector(
        wall, spec, wall.arc_length / 2, target, mount_height=3.0, mode=MODE_LEVEL
    )
    assert placement.arc_span == pytest.approx(target, abs=0.01)
    assert placement.throw_distance == pytest.approx(distance, rel=1e-9)


@pytest.mark.parametrize("target", [2.0, 3.5, 5.0, 6.5])
def test_the_solver_converges_across_a_range_of_image_widths(wall, spec, target):
    placement = plan_projector(
        wall, spec, wall.arc_length / 2, target, mount_height=3.0, mode=MODE_LEVEL
    )
    assert placement.arc_span == pytest.approx(target, abs=0.02)


def test_a_wider_image_needs_a_longer_throw(wall, spec):
    near = plan_projector(wall, spec, wall.arc_length / 2, 2.5, mount_height=3.0)
    far = plan_projector(wall, spec, wall.arc_length / 2, 5.0, mount_height=3.0)
    assert far.throw_distance > near.throw_distance
    assert far.horizontal_standoff > near.horizontal_standoff


def test_a_longer_lens_pushes_the_projector_further_back(wall):
    short = ProjectorSpec(throw_ratio=0.9, max_lens_shift_v=0.8)
    long = ProjectorSpec(throw_ratio=2.0, max_lens_shift_v=0.8)
    a = plan_projector(wall, short, wall.arc_length / 2, 3.5, mount_height=3.0)
    b = plan_projector(wall, long, wall.arc_length / 2, 3.5, mount_height=3.0)
    assert b.horizontal_standoff > a.horizontal_standoff
    assert a.arc_span == pytest.approx(b.arc_span, abs=0.02)


# -- mounting modes -------------------------------------------------------


def test_level_mode_keeps_the_axis_horizontal_and_uses_lens_shift(wall, spec):
    p = plan_projector(
        wall, spec, wall.arc_length / 2, 4.0, mount_height=3.0,
        image_center_height=1.5, mode=MODE_LEVEL,
    )
    assert p.tilt_deg == pytest.approx(0.0, abs=1e-9)
    assert p.pose.forward[2] == pytest.approx(0.0, abs=1e-9)
    assert p.drop_below_mount == pytest.approx(1.5)
    assert p.spec.lens_shift_v < 0.0  # shifted down onto the wall
    # Throw distance is measured along the horizontal axis in this mode.
    assert p.throw_distance == pytest.approx(p.horizontal_standoff, rel=1e-9)


def test_level_mode_shift_equals_the_drop_over_the_image_height(wall, spec):
    p = plan_projector(
        wall, spec, wall.arc_length / 2, 4.0, mount_height=3.2,
        image_center_height=1.4, mode=MODE_LEVEL,
    )
    assert p.spec.lens_shift_v == pytest.approx(-p.drop_below_mount / p.image_height)


def test_tilt_mode_aims_at_the_target_with_no_lens_shift(wall, spec):
    p = plan_projector(
        wall, spec, wall.arc_length / 2, 4.0, mount_height=3.0,
        image_center_height=1.5, mode=MODE_TILT,
    )
    assert p.spec.lens_shift_v == 0.0
    assert p.tilt_deg < 0.0  # aiming downward
    assert vec_distance(p.position, p.aim_point) == pytest.approx(p.throw_distance, rel=1e-9)
    # Pythagoras between the axis, the standoff and the drop.
    assert p.throw_distance == pytest.approx(
        math.hypot(p.horizontal_standoff, p.drop_below_mount), rel=1e-6
    )


def test_both_modes_land_the_image_centre_on_the_aim_point(wall, spec):
    for mode in (MODE_LEVEL, MODE_TILT):
        p = plan_projector(
            wall, spec, wall.arc_length / 2, 4.0, mount_height=3.0,
            image_center_height=1.5, mode=mode,
        )
        centre = min(p.footprint.samples, key=lambda s: s.u * s.u + s.v * s.v)
        assert centre.hit is not None, mode
        assert vec_distance(centre.hit.point, p.aim_point) < 0.02, mode


def test_an_unknown_mount_mode_is_rejected(wall, spec):
    with pytest.raises(ProjectionError):
        plan_projector(wall, spec, 4.0, 3.0, mount_height=3.0, mode="SIDEWAYS")


def test_excessive_lens_shift_is_warned_about_not_silently_accepted(wall):
    tight = ProjectorSpec(throw_ratio=1.2, max_lens_shift_v=0.05)
    p = plan_projector(
        wall, tight, wall.arc_length / 2, 3.0, mount_height=4.0,
        image_center_height=1.0, mode=MODE_LEVEL,
    )
    assert any("vertical lens shift" in w for w in p.warnings)
    assert any("TILT" in w for w in p.warnings)


def test_a_steep_tilt_is_warned_about(wall, spec):
    # High mount, low image centre: the axis has to point well below horizontal.
    p = plan_projector(
        wall, spec, wall.arc_length / 2, 4.0, mount_height=3.6,
        image_center_height=1.5, mode=MODE_TILT,
    )
    assert abs(p.tilt_deg) > 15.0
    assert any("keystone" in w for w in p.warnings)


# -- full arrays ----------------------------------------------------------


def test_a_three_projector_array_covers_the_curved_wall_end_to_end(wall, spec):
    plan = plan_array(wall, spec, count=3, overlap_fraction=0.15, mount_height=3.0,
                      image_center_height=1.5)
    assert len(plan.placements) == 3
    report = analyze_coverage(plan.footprints, wall, grid_s=120, grid_z=24)

    assert report.gaps == []  # no dark band anywhere along the arc
    assert report.horizontal_coverage == pytest.approx(1.0)
    assert len(report.blend_zones) == 2
    assert report.max_overlap_count == 2


def test_a_16_9_array_letterboxes_a_taller_wall_and_says_so(wall, spec):
    """Truthful reporting of a real constraint: three 16:9 images spanning
    12.6 m of arc are only ~2.6 m tall, so a 3 m wall keeps unlit strips."""
    plan = plan_array(wall, spec, count=3, overlap_fraction=0.15, mount_height=3.0,
                      image_center_height=1.5)
    report = analyze_coverage(plan.footprints, wall, grid_s=120, grid_z=24)

    assert report.covered_fraction < report.horizontal_coverage
    assert report.covered_height < wall.height
    assert report.covered_height > 2.0
    assert any("unlit below" in w for w in report.warnings)


def test_covered_area_fraction_tracks_the_lit_band_height(wall, spec):
    plan = plan_array(wall, spec, count=3, overlap_fraction=0.15, mount_height=3.0,
                      image_center_height=1.5)
    report = analyze_coverage(plan.footprints, wall, grid_s=120, grid_z=24)
    # With full horizontal coverage, area coverage is just the height ratio.
    assert report.covered_fraction == pytest.approx(
        report.covered_height / wall.height, abs=0.03
    )


def test_array_blend_zones_match_the_requested_overlap(wall, spec):
    overlap = 0.18
    plan = plan_array(wall, spec, count=3, overlap_fraction=overlap, mount_height=3.0,
                      image_center_height=1.5)
    report = analyze_coverage(plan.footprints, wall, grid_s=120, grid_z=24)
    for zone in report.blend_zones:
        assert zone.overlap_fraction_left == pytest.approx(overlap, abs=0.04)


def test_more_overlap_means_more_of_the_wall_is_double_lit(wall, spec):
    light = plan_array(wall, spec, 3, overlap_fraction=0.10, mount_height=3.0,
                       image_center_height=1.5)
    heavy = plan_array(wall, spec, 3, overlap_fraction=0.30, mount_height=3.0,
                       image_center_height=1.5)
    a = analyze_coverage(light.footprints, wall, grid_s=120, grid_z=24)
    b = analyze_coverage(heavy.footprints, wall, grid_s=120, grid_z=24)
    assert b.overlap_fraction > a.overlap_fraction


def test_array_placements_are_spread_along_the_wall_in_order(wall, spec):
    plan = plan_array(wall, spec, 4, overlap_fraction=0.15, mount_height=3.0,
                      image_center_height=1.5)
    centres = [p.arc_center for p in plan.placements]
    assert centres == sorted(centres)
    assert plan.placements[0].name == "Projector_01"
    assert plan.placements[-1].name == "Projector_04"


def test_every_projector_in_an_array_hangs_at_the_mount_height(wall, spec):
    plan = plan_array(wall, spec, 3, overlap_fraction=0.15, mount_height=3.4,
                      image_center_height=1.5)
    for p in plan.placements:
        assert p.position[2] == pytest.approx(3.4)


def test_array_projectors_sit_inside_the_wall_radius(wall, spec):
    plan = plan_array(wall, spec, 3, overlap_fraction=0.15, mount_height=3.0,
                      image_center_height=1.5)
    for p in plan.placements:
        radius = math.hypot(p.position[0] - wall.base_center[0],
                            p.position[1] - wall.base_center[1])
        assert radius < wall.radius


def test_a_single_projector_array_still_works(wall):
    wide = ProjectorSpec(throw_ratio=0.65, max_lens_shift_v=0.9)
    plan = plan_array(wall, wide, count=1, overlap_fraction=0.0, mount_height=3.0,
                      image_center_height=1.5)
    assert len(plan.placements) == 1
    assert plan.placements[0].arc_span == pytest.approx(wall.arc_length, abs=0.05)


def test_a_tight_overlap_request_is_flagged(wall, spec):
    plan = plan_array(wall, spec, 3, overlap_fraction=0.02, mount_height=3.0,
                      image_center_height=1.5)
    assert any("edge blending" in w for w in plan.warnings)


def test_a_generous_overlap_produces_no_array_level_warning(wall, spec):
    plan = plan_array(wall, spec, 3, overlap_fraction=0.15, mount_height=3.0,
                      image_center_height=1.5)
    assert plan.warnings == []


def test_a_long_lens_that_would_overshoot_the_axis_is_flagged(wall):
    tele = ProjectorSpec(throw_ratio=6.0, max_lens_shift_v=0.9)
    p = plan_projector(wall, tele, wall.arc_length / 2, 5.0, mount_height=3.0,
                       image_center_height=1.5)
    assert any("cylinder axis" in w or "shorter lens" in w for w in p.warnings)


def test_tilt_mode_rejects_a_drop_taller_than_the_throw(wall):
    """A very long lens from a very high mount cannot reach a small image."""
    tele = ProjectorSpec(throw_ratio=1.2)
    with pytest.raises(ProjectionError):
        plan_projector(wall, tele, wall.arc_length / 2, 0.05, mount_height=40.0,
                       image_center_height=1.5, mode=MODE_TILT)


def test_placement_formatting_reports_what_an_installer_needs(wall, spec):
    p = plan_projector(wall, spec, wall.arc_length / 2, 4.0, mount_height=3.0,
                       image_center_height=1.5, name="PJ-01")
    text = "\n".join(format_placement(p))
    assert "PJ-01" in text
    assert "mount:" in text
    assert "throw distance:" in text
    assert "vertical lens shift" in text
    assert "arc covered" in text


def test_brightness_of_a_planned_array_is_reported(wall, spec):
    plan = plan_array(wall, spec, 3, overlap_fraction=0.15, mount_height=3.0,
                      image_center_height=1.5)
    report = analyze_coverage(plan.footprints, wall, grid_s=100, grid_z=20)
    assert report.brightness is not None
    assert report.brightness.mean_nits > 0.0
    assert report.brightness.assumptions


@pytest.mark.parametrize("mode", [MODE_LEVEL, MODE_TILT])
def test_automatic_planner_rejects_horizontal_lens_shift(wall, mode):
    shifted = ProjectorSpec(throw_ratio=1.2, lens_shift_h=0.2)
    with pytest.raises(ProjectionError, match="horizontal lens shift"):
        plan_projector(
            wall,
            shifted,
            wall.arc_length / 2,
            4.0,
            mount_height=3.0,
            image_center_height=1.5,
            mode=mode,
        )


def test_solver_rejects_a_target_it_cannot_converge_on(wall, monkeypatch):
    from blender_projection_system.core import array as array_module

    class FixedWidth:
        arc_span = 1.0

    monkeypatch.setattr(array_module, "compute_footprint", lambda *args, **kwargs: FixedWidth())
    with pytest.raises(ProjectionError, match="could not solve"):
        solve_standoff(
            wall,
            ProjectorSpec(throw_ratio=1.2),
            wall.arc_length / 2,
            1.5,
            3.0,
            4.0,
        )
