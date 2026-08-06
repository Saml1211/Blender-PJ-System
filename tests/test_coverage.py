"""Tests for multi-projector coverage, gap and blend-zone analysis."""

from __future__ import annotations

import math

import pytest

from blender_projection_system.core.coverage import (
    Interval,
    analyze_coverage,
    compute_blend_zones,
    format_report,
)
from blender_projection_system.core.errors import ProjectionError
from blender_projection_system.core.footprint import compute_footprint
from blender_projection_system.core.pose import look_at
from blender_projection_system.core.surfaces import CylindricalWall
from blender_projection_system.core.throw import ProjectorSpec


@pytest.fixture
def wall() -> CylindricalWall:
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


# -- intervals ------------------------------------------------------------


def test_intervals_intersect_and_measure():
    a, b = Interval(0.0, 4.0), Interval(3.0, 7.0)
    common = a.intersect(b)
    assert common is not None
    assert common.start == 3.0 and common.end == 4.0 and common.length == 1.0
    assert a.intersect(Interval(9.0, 10.0)) is None
    assert Interval(2.0, 2.0).length == 0.0


# -- single projector -----------------------------------------------------


def test_a_single_projector_covers_only_part_of_a_wide_wall(wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(wall, wall.arc_length / 2, 4.0, spec, "P1")
    report = analyze_coverage([fp], wall, grid_s=60, grid_z=18)

    assert 0.0 < report.covered_fraction < 1.0
    assert report.gap_fraction == pytest.approx(1.0 - report.covered_fraction)
    assert report.overlap_cells == 0
    assert report.max_overlap_count == 1
    assert report.blend_zones == []
    assert report.gaps  # bare wall on both sides
    assert any("dark band" in w for w in report.warnings)


def test_covered_area_and_cell_bookkeeping_are_consistent(wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(wall, wall.arc_length / 2, 4.0, spec, "P1")
    report = analyze_coverage([fp], wall, grid_s=40, grid_z=12)

    assert report.total_cells == 40 * 12
    assert report.cell_area == pytest.approx(
        (wall.arc_length / 40) * (wall.height / 12)
    )
    assert report.covered_area + report.gap_area == pytest.approx(wall.area)


def test_no_usable_footprints_reports_zero_coverage(wall):
    origin = wall.axis_point(1.5)
    missed = compute_footprint(
        look_at(origin, (origin[0] - 5.0, origin[1], origin[2])),
        ProjectorSpec(),
        wall,
        samples=5,
        name="Missed",
    )
    report = analyze_coverage([missed], wall, grid_s=20, grid_z=6)
    assert report.covered_fraction == 0.0
    assert report.brightness is None
    assert any("coverage is zero" in w for w in report.warnings)


# -- multiple projectors --------------------------------------------------


def test_two_overlapping_projectors_produce_a_blend_zone(wall):
    # A 1.0:1 lens at 4.5 m standoff spans ~4.27 m of arc, so centres 3.77 m
    # apart share roughly half a metre.
    spec = ProjectorSpec(throw_ratio=1.0)
    a = _projector_at(wall, wall.arc_length * 0.35, 4.5, spec, "Left")
    b = _projector_at(wall, wall.arc_length * 0.65, 4.5, spec, "Right")
    report = analyze_coverage([a, b], wall, grid_s=80, grid_z=20)

    assert report.overlap_cells > 0
    assert report.max_overlap_count == 2
    assert len(report.blend_zones) == 1
    zone = report.blend_zones[0]
    assert zone.left == "Left" and zone.right == "Right"
    assert zone.width > 0.0
    assert 0.0 < zone.overlap_fraction_left < 1.0
    assert zone.cells
    assert all(0.0 <= cell.z_start < cell.z_end <= wall.height for cell in zone.cells)


def test_projectors_far_apart_leave_a_gap_and_no_blend(wall):
    spec = ProjectorSpec(throw_ratio=3.0)  # narrow images
    a = _projector_at(wall, wall.arc_length * 0.12, 4.0, spec, "Left")
    b = _projector_at(wall, wall.arc_length * 0.88, 4.0, spec, "Right")
    report = analyze_coverage([a, b], wall, grid_s=80, grid_z=16)

    assert report.blend_zones == []
    assert report.overlap_cells == 0
    assert len(report.gaps) >= 1
    middle = wall.arc_length / 2
    assert any(g.start < middle < g.end for g in report.gaps)


def test_blend_zones_are_ordered_left_to_right_along_the_arc(wall):
    spec = ProjectorSpec(throw_ratio=1.0)
    fps = [
        _projector_at(wall, wall.arc_length * f, 4.5, spec, f"P{i}")
        for i, f in enumerate((0.7, 0.25, 0.475))  # deliberately out of order
    ]
    zones = compute_blend_zones(fps)
    assert [z.left for z in zones] == ["P1", "P2"]
    assert [z.right for z in zones] == ["P2", "P0"]


def test_a_narrow_blend_is_flagged_as_unusable(wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    a = _projector_at(wall, wall.arc_length / 2, 4.5, spec, "Left")
    b = _projector_at(wall, wall.arc_length / 2, 4.5, spec, "Right")
    # Force a sliver of overlap by shrinking one span artificially.
    b.s_min = a.s_max - 0.01
    b.s_max = a.s_max + 2.0
    zones = compute_blend_zones([a, b])
    assert len(zones) == 1
    assert zones[0].width == pytest.approx(0.01, abs=1e-9)


def test_triple_overlap_is_called_out(wall):
    spec = ProjectorSpec(throw_ratio=1.2)
    fps = [
        _projector_at(wall, wall.arc_length / 2, 5.0, spec, f"P{i}") for i in range(3)
    ]
    report = analyze_coverage(fps, wall, grid_s=40, grid_z=12)
    assert report.max_overlap_count == 3
    assert any("triple overlap" in w for w in report.warnings)


def test_overlap_adds_illuminance(wall):
    spec = ProjectorSpec(throw_ratio=1.5, lumens=5000.0)
    one = _projector_at(wall, wall.arc_length / 2, 4.5, spec, "A")
    two = _projector_at(wall, wall.arc_length / 2, 4.5, spec, "B")
    single = analyze_coverage([one], wall, grid_s=40, grid_z=12)
    doubled = analyze_coverage([one, two], wall, grid_s=40, grid_z=12)

    assert single.brightness is not None and doubled.brightness is not None
    assert doubled.brightness.mean_lux == pytest.approx(
        2.0 * single.brightness.mean_lux, rel=1e-6
    )


def test_screen_gain_scales_reported_luminance(wall):
    spec = ProjectorSpec(throw_ratio=1.5, lumens=5000.0)
    fp = _projector_at(wall, wall.arc_length / 2, 4.5, spec, "A")
    unity = analyze_coverage([fp], wall, grid_s=30, grid_z=10, screen_gain=1.0)
    gained = analyze_coverage([fp], wall, grid_s=30, grid_z=10, screen_gain=1.8)
    assert gained.brightness.mean_nits == pytest.approx(
        1.8 * unity.brightness.mean_nits, rel=1e-9
    )
    assert gained.brightness.mean_lux == pytest.approx(unity.brightness.mean_lux)


def test_a_finer_grid_does_not_change_the_answer_much(wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(wall, wall.arc_length / 2, 4.5, spec, "A")
    coarse = analyze_coverage([fp], wall, grid_s=40, grid_z=12).covered_fraction
    fine = analyze_coverage([fp], wall, grid_s=160, grid_z=48).covered_fraction
    assert fine == pytest.approx(coarse, abs=0.02)


def test_report_formatting_mentions_the_key_numbers(wall):
    spec = ProjectorSpec(throw_ratio=1.0, lumens=6000.0)
    a = _projector_at(wall, wall.arc_length * 0.35, 4.5, spec, "Left")
    b = _projector_at(wall, wall.arc_length * 0.65, 4.5, spec, "Right")
    lines = format_report(analyze_coverage([a, b], wall, grid_s=60, grid_z=16))
    text = "\n".join(lines)
    assert "Coverage:" in text
    assert "Overlap:" in text
    assert "blend Left | Right" in text
    assert "nits" in text


def test_vertically_disjoint_images_do_not_report_a_blend_zone(wall):
    spec = ProjectorSpec(throw_ratio=4.0)
    low = _projector_at(wall, wall.arc_length / 2, 2.0, spec, "Low", z=0.5)
    high = _projector_at(wall, wall.arc_length / 2, 2.0, spec, "High", z=2.5)
    report = analyze_coverage([low, high], wall, grid_s=80, grid_z=40)
    assert report.overlap_cells == 0
    assert report.blend_zones == []


@pytest.mark.parametrize("grid_s,grid_z", [(0, 10), (10, 0), (-1, 10)])
def test_invalid_grid_dimensions_raise_projection_error(wall, grid_s, grid_z):
    with pytest.raises(ProjectionError, match="grid dimensions"):
        analyze_coverage([], wall, grid_s=grid_s, grid_z=grid_z)
