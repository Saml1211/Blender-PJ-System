"""Tests for the planar wall surface and the shared Surface contract."""

from __future__ import annotations

import math

import pytest

from blender_projection_system.core.errors import ProjectionError
from blender_projection_system.core.surfaces import (
    CylindricalWall,
    PlanarWall,
    Surface,
    flat_wall_as_cylinder,
)
from blender_projection_system.core.vectors import distance, normalize, sub


@pytest.fixture
def wall() -> PlanarWall:
    """A 4 m wide, 2.5 m tall flat wall whose face is at x=5, facing -X."""
    return PlanarWall(base_center=(5.0, 0.0, 0.0), width=4.0, height=2.5)


# -- construction -----------------------------------------------------------


def test_planar_wall_is_a_surface(wall):
    assert isinstance(wall, Surface)
    assert isinstance(flat_wall_as_cylinder(4.0, 2.5), Surface)


def test_invalid_planar_walls_are_rejected():
    with pytest.raises(ProjectionError):
        PlanarWall(width=0.0, height=2.0)
    with pytest.raises(ProjectionError):
        PlanarWall(width=3.0, height=-1.0)


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_non_finite_planar_dimensions_are_rejected(value):
    with pytest.raises(ProjectionError):
        PlanarWall(width=value, height=2.0)
    with pytest.raises(ProjectionError):
        PlanarWall(width=3.0, height=2.0, facing=(value, 0.0, 0.0))


def test_a_zero_length_facing_is_rejected():
    with pytest.raises(ProjectionError):
        PlanarWall(width=3.0, height=2.0, facing=(0.0, 0.0, 0.0))


def test_facing_is_normalised_and_must_be_horizontal():
    wall = PlanarWall(width=3.0, height=2.0, facing=(0.0, -5.0, 0.0))
    assert distance(wall.facing, (0.0, -1.0, 0.0)) == pytest.approx(0.0)
    with pytest.raises(ProjectionError):
        PlanarWall(width=3.0, height=2.0, facing=(0.0, 0.0, 1.0))


# -- basic geometry ----------------------------------------------------------


def test_dimensions_and_area(wall):
    assert wall.arc_length == pytest.approx(4.0)
    assert wall.height == pytest.approx(2.5)
    assert wall.area == pytest.approx(10.0)


def test_points_sit_on_the_wall_plane_at_requested_height(wall):
    for s in (0.0, 1.7, wall.arc_length):
        p = wall.point_at(s, 1.25)
        # The whole face lies in the plane x = 5.
        assert p[0] == pytest.approx(5.0)
        assert p[2] == pytest.approx(1.25)
    # s runs left-to-right along +Y here: s=0 at y=-2, s=width at y=+2.
    assert wall.point_at(0.0, 0.0)[1] == pytest.approx(-2.0)
    assert wall.point_at(wall.arc_length, 0.0)[1] == pytest.approx(2.0)


def test_the_normal_is_the_constant_facing(wall):
    for s in (0.0, wall.arc_length / 2, wall.arc_length):
        assert distance(wall.normal_at_s(s), (-1.0, 0.0, 0.0)) == pytest.approx(
            0.0
        )


def test_center_point_is_mid_wall(wall):
    c = wall.center_point()
    assert c == pytest.approx((5.0, 0.0, 1.25))


def test_contains_bounds_checking_in_wall_coordinates(wall):
    assert wall.contains(0.0, 0.0)
    assert wall.contains(wall.arc_length, wall.height)
    assert not wall.contains(-0.001, 1.0)
    assert not wall.contains(1.0, wall.height + 0.001)


# -- ray casting -------------------------------------------------------------


def test_a_ray_along_the_normal_hits_square_on(wall):
    target = wall.point_at(wall.arc_length / 2, 1.0)
    origin = (-1.0, 0.0, 1.0)  # 6 m in front of the face
    hit = wall.intersect_ray(origin, normalize(sub(target, origin)))
    assert hit is not None
    assert hit.distance == pytest.approx(6.0)
    assert hit.s == pytest.approx(wall.arc_length / 2)
    assert hit.z == pytest.approx(1.0)
    assert hit.incidence == pytest.approx(0.0, abs=1e-9)
    assert distance(hit.point, target) < 1e-9


def test_an_oblique_ray_reports_its_incidence(wall):
    origin = (-1.0, -3.0, 1.0)
    direction = normalize((1.0, 0.6, 0.0))
    cos_theta = math.sqrt(1.0 / (1.0 + 0.36))  # angle to the x-axis normal
    expected = math.acos(cos_theta)
    hit = wall.intersect_ray(origin, direction)
    assert hit is not None
    assert hit.incidence == pytest.approx(expected, abs=1e-9)
    assert hit.point[0] == pytest.approx(5.0)


def test_a_ray_beyond_the_wall_edges_misses(wall):
    # Aimed at a point level with the face but outside the width span.
    assert wall.intersect_ray((-1.0, -4.0, 1.0), normalize((1.0, 0.0, 0.0))) is None
    # Aimed above the top edge.
    assert wall.intersect_ray((-1.0, 0.0, 9.0), normalize((1.0, 0.0, -0.1))) is None


def test_a_ray_pointing_away_from_the_front_face_misses(wall):
    # Behind the wall looking further away: back-face hits are rejected just
    # like a concave cylinder rejects them.
    assert wall.intersect_ray((9.0, 0.0, 1.0), (1.0, 0.0, 0.0)) is None


def test_a_vertical_ray_parallel_to_the_wall_never_hits(wall):
    assert wall.intersect_ray((-1.0, 0.0, 0.5), (0.0, 0.0, 1.0)) is None


def test_intersection_respects_max_distance(wall):
    origin = (-1.0, 0.0, 1.0)
    direction = (1.0, 0.0, 0.0)
    assert wall.intersect_ray(origin, direction, max_distance=5.0) is None
    assert wall.intersect_ray(origin, direction, max_distance=7.0) is not None


def test_offset_base_centre_is_honoured():
    wall = PlanarWall(
        base_center=(2.0, 8.0, 1.0),
        width=3.0,
        height=2.0,
        facing=(0.0, -1.0, 0.0),
    )
    origin = (2.0, 4.0, 2.0)
    hit = wall.intersect_ray(origin, normalize((0.0, 1.0, 0.0)))
    assert hit is not None
    assert hit.distance == pytest.approx(4.0)
    assert hit.z == pytest.approx(1.0)  # base z 1.0 + local z 0.0... centre row
    assert hit.point[1] == pytest.approx(8.0)


def test_project_point_snaps_onto_the_face(wall):
    near = (5.4, 0.8, 2.0)
    hit = wall.project_point(near)
    assert hit is not None
    assert hit.point[0] == pytest.approx(5.0)  # snapped onto the plane
    assert hit.z == pytest.approx(2.0)
    assert hit.distance == pytest.approx(0.4)  # radial snap offset


def test_project_point_rejects_locations_outside_the_rectangle(wall):
    assert wall.project_point((5.0, 3.5, 1.0)) is None  # past the right edge
    assert wall.project_point((5.0, -3.5, 1.0)) is None  # past the left edge
    assert wall.project_point((5.0, 0.0, 9.0)) is None  # above the top


# -- generic Surface hooks ---------------------------------------------------


def test_planar_walls_do_not_wrap_around(wall):
    assert wall.wraps_around is False


def test_chord_equals_span_on_a_flat_wall(wall):
    assert wall.chord(1.234) == pytest.approx(1.234)


def test_expanded_pads_width_height_and_base(wall):
    big = wall.expanded(pad_s=2.0, pad_z=1.5)
    assert big.arc_length == pytest.approx(wall.arc_length + 2 * 2.0)
    assert big.height == pytest.approx(wall.height + 2 * 1.5)
    assert big.base_center[2] == pytest.approx(-1.5)
    assert distance(big.normal_at_s(1.0), wall.normal_at_s(1.0)) < 1e-12
    # The original rectangle stays centred inside the padded one.
    assert big.contains(wall.arc_length / 2, wall.height / 2)


def test_cylindrical_wall_hooks_match_direct_fields():
    cyl = CylindricalWall(radius=5.0, height=3.0)
    assert cyl.wraps_around is False
    span = cyl.arc_length / 3
    assert cyl.chord(span) == pytest.approx(
        2.0 * 5.0 * math.sin(span / (2.0 * 5.0))
    )
    full = CylindricalWall(radius=5.0, height=3.0, angle_start=0.0, angle_end=2 * math.pi)
    assert full.wraps_around is True
    assert cyl.curvature_radius == pytest.approx(5.0)


def test_cylindrical_expanded_matches_the_old_measurement_wall():
    from dataclasses import replace

    cyl = CylindricalWall(
        radius=6.0, height=4.0, angle_start=math.radians(-60), angle_end=math.radians(60)
    )
    pad_angle = min(math.pi * 0.5, cyl.sweep * 0.75 + 0.35)
    old = replace(
        cyl,
        base_center=(0.0, 0.0, -8.0),
        height=cyl.height + 16.0,
        angle_start=cyl.angle_start - pad_angle,
        angle_end=cyl.angle_end + pad_angle,
    )
    new = cyl.expanded(pad_angle * 6.0, 8.0)
    assert new.angle_start == pytest.approx(old.angle_start)
    assert new.angle_end == pytest.approx(old.angle_end)
    assert new.height == pytest.approx(old.height)
    assert new.base_center == pytest.approx(old.base_center)


# -- compatibility with the large-radius hack -------------------------------


def test_planar_footprint_matches_the_flat_cylinder_hack():
    """The compatibility bar: same projector, same numbers within tolerance."""
    from blender_projection_system.core.footprint import compute_footprint
    from blender_projection_system.core.pose import look_at
    from blender_projection_system.core.throw import ProjectorSpec

    spec = ProjectorSpec(throw_ratio=1.2, lumens=6000.0)  # default 16:9
    width, height = 4.0, 2.5

    def footprint_against(surface, throw_distance):
        target = surface.center_point()
        pose = look_at(
            (
                target[0] - throw_distance,
                target[1],
                target[2],
            ),
            target,
        )
        return compute_footprint(pose, spec, surface)

    hack = flat_wall_as_cylinder(width=width, height=height)
    # 4.5 m throw with a 1.2:1 lens makes a 3.75 m wide image that fits the
    # 4 m wall entirely, so both surfaces see the full frustum.
    fp_hack = footprint_against(hack, throw_distance=4.5)
    fp_flat = footprint_against(
        PlanarWall(base_center=(hack.radius, 0.0, 0.0), width=width, height=height),
        throw_distance=4.5,
    )
    assert fp_flat.hit_ratio == 1.0
    assert fp_flat.arc_span == pytest.approx(fp_hack.arc_span, abs=1e-3)
    assert fp_flat.height_span == pytest.approx(fp_hack.height_span, abs=1e-3)
    for sample_flat, sample_hack in zip(fp_flat.samples, fp_hack.samples, strict=True):
        hit_flat = sample_flat.hit
        hit_hack = sample_hack.hit
        if hit_flat is None:
            assert hit_hack is None
            continue
        assert hit_hack is not None
        assert hit_flat.s == pytest.approx(hit_hack.s, abs=1e-3)
        assert hit_flat.z == pytest.approx(hit_hack.z, abs=1e-3)
        # A 5000 m radius still bows: its normals tilt by up to s/R ~ 4e-4 rad
        # across the face, so incidence may differ by that much from a plane.
        assert hit_flat.incidence == pytest.approx(hit_hack.incidence, abs=1e-3)


def test_coverage_analysis_runs_end_to_end_on_a_planar_wall():
    from blender_projection_system.core.coverage import analyze_coverage
    from blender_projection_system.core.pose import look_at
    from blender_projection_system.core.throw import ProjectorSpec

    spec = ProjectorSpec(throw_ratio=1.2, lumens=6000.0)
    wall = PlanarWall(base_center=(5.0, 0.0, 0.0), width=4.0, height=2.5)
    target = wall.center_point()
    pose = look_at((target[0] - 5.0, target[1], target[2]), target)
    fp = compute_fp(pose, spec, wall)
    report = analyze_coverage([fp], wall, grid_s=20, grid_z=10)
    assert report.total_cells == 200
    assert report.covered_fraction > 0.5
    assert report.wall_arc_length == pytest.approx(4.0)
    assert report.blend_zones == []


def compute_fp(pose, spec, wall):
    from blender_projection_system.core.footprint import compute_footprint

    return compute_footprint(pose, spec, wall)
