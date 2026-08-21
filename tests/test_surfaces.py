"""Tests for the cylindrical wall model and ray intersection."""

from __future__ import annotations

import math

import pytest

from blender_projection_system.core.errors import ProjectionError
from blender_projection_system.core.surfaces import (
    CylindricalWall,
    flat_wall_as_cylinder,
    wall_outline,
)
from blender_projection_system.core.vectors import distance, normalize, sub


@pytest.fixture
def wall() -> CylindricalWall:
    """A 6 m radius, 120 degree, 4 m tall wall centred on the origin."""
    return CylindricalWall(
        base_center=(0.0, 0.0, 0.0),
        radius=6.0,
        height=4.0,
        angle_start=math.radians(-60.0),
        angle_end=math.radians(60.0),
        concave=True,
    )


def test_arc_length_is_radius_times_sweep(wall):
    assert wall.sweep == pytest.approx(math.radians(120.0))
    assert wall.arc_length == pytest.approx(6.0 * math.radians(120.0))
    assert wall.area == pytest.approx(wall.arc_length * 4.0)


def test_points_sit_at_the_radius_and_requested_height(wall):
    for s in (0.0, wall.arc_length / 3, wall.arc_length):
        for z in (0.0, 2.0, 4.0):
            p = wall.point_at(s, z)
            assert math.hypot(p[0], p[1]) == pytest.approx(6.0)
            assert p[2] == pytest.approx(z)


def test_arc_length_and_angle_are_inverses(wall):
    for s in (0.0, 1.0, wall.arc_length):
        assert wall.s_at_angle(wall.angle_at_s(s)) == pytest.approx(s)


def test_concave_normal_points_at_the_axis(wall):
    s = wall.arc_length / 2
    p = wall.point_at(s, 2.0)
    n = wall.normal_at_s(s)
    axis = wall.axis_point(2.0)
    assert distance(p, axis) == pytest.approx(6.0)
    # Stepping along the normal must reduce the distance to the axis.
    stepped = (p[0] + n[0] * 0.5, p[1] + n[1] * 0.5, p[2])
    assert distance(stepped, axis) < distance(p, axis)


def test_convex_normal_points_away_from_the_axis():
    convex = CylindricalWall(radius=3.0, height=2.0, concave=False)
    n = convex.normal_at_s(convex.arc_length / 2)
    p = convex.point_at(convex.arc_length / 2, 1.0)
    assert n[0] * p[0] + n[1] * p[1] > 0.0


def test_invalid_walls_are_rejected():
    with pytest.raises(ProjectionError):
        CylindricalWall(radius=0.0)
    with pytest.raises(ProjectionError):
        CylindricalWall(height=-1.0)
    with pytest.raises(ProjectionError):
        CylindricalWall(angle_start=1.0, angle_end=1.0)
    with pytest.raises(ProjectionError):
        CylindricalWall(angle_start=0.0, angle_end=10.0)


def test_a_ray_from_the_axis_hits_the_wall_at_the_radius(wall):
    origin = wall.axis_point(2.0)
    target = wall.point_at(wall.arc_length / 2, 2.0)
    hit = wall.intersect_ray(origin, normalize(sub(target, origin)))
    assert hit is not None
    assert hit.distance == pytest.approx(6.0)
    assert hit.z == pytest.approx(2.0)
    assert hit.s == pytest.approx(wall.arc_length / 2)


def test_a_ray_along_the_normal_has_zero_incidence(wall):
    s = wall.arc_length / 3
    target = wall.point_at(s, 1.5)
    normal = wall.normal_at_s(s)
    # Walk back along the normal, then fire straight down it.
    origin = (target[0] + normal[0] * 3.0, target[1] + normal[1] * 3.0, target[2])
    hit = wall.intersect_ray(origin, (-normal[0], -normal[1], 0.0))
    assert hit is not None
    assert hit.incidence == pytest.approx(0.0, abs=1e-9)
    assert hit.distance == pytest.approx(3.0)


def test_incidence_grows_for_an_oblique_ray(wall):
    origin = wall.axis_point(2.0)
    square_on = wall.intersect_ray(origin, normalize(sub(wall.point_at(wall.arc_length / 2, 2.0), origin)))
    # An off-axis origin makes the same wall point an oblique hit.
    oblique_origin = (2.0, 0.0, 2.0)
    target = wall.point_at(wall.arc_length * 0.9, 2.0)
    oblique = wall.intersect_ray(oblique_origin, normalize(sub(target, oblique_origin)))
    assert square_on is not None and oblique is not None
    assert oblique.incidence > square_on.incidence
    assert 0.0 <= oblique.incidence < math.pi / 2


def test_a_ray_beyond_the_arc_ends_misses(wall):
    origin = wall.axis_point(2.0)
    # Straight backwards, outside the +/-60 degree arc.
    hit = wall.intersect_ray(origin, (-1.0, 0.0, 0.0))
    assert hit is None


def test_a_ray_above_the_wall_top_misses(wall):
    origin = wall.axis_point(3.9)
    hit = wall.intersect_ray(origin, normalize((1.0, 0.0, 1.0)))
    assert hit is None


def test_a_vertical_ray_never_hits_a_vertical_wall(wall):
    assert wall.intersect_ray(wall.axis_point(1.0), (0.0, 0.0, 1.0)) is None


def test_a_ray_pointing_away_from_the_wall_misses(wall):
    target = wall.point_at(wall.arc_length / 2, 2.0)
    origin = wall.axis_point(2.0)
    away = normalize(sub(origin, target))
    assert wall.intersect_ray(origin, away) is None


def test_intersection_respects_max_distance(wall):
    origin = wall.axis_point(2.0)
    direction = normalize(sub(wall.point_at(wall.arc_length / 2, 2.0), origin))
    assert wall.intersect_ray(origin, direction, max_distance=5.0) is None
    assert wall.intersect_ray(origin, direction, max_distance=7.0) is not None


def test_offset_wall_centre_is_honoured():
    wall = CylindricalWall(
        base_center=(10.0, -4.0, 1.0),
        radius=5.0,
        height=3.0,
        angle_start=math.radians(-30),
        angle_end=math.radians(30),
    )
    origin = wall.axis_point(1.5)
    target = wall.point_at(wall.arc_length / 2, 1.5)
    hit = wall.intersect_ray(origin, normalize(sub(target, origin)))
    assert hit is not None
    assert hit.distance == pytest.approx(5.0)
    assert hit.point[2] == pytest.approx(2.5)  # base z 1.0 + 1.5


def test_project_point_snaps_onto_the_surface(wall):
    near = (4.0, 0.5, 2.0)
    hit = wall.project_point(near)
    assert hit is not None
    assert math.hypot(hit.point[0], hit.point[1]) == pytest.approx(6.0)
    assert hit.z == pytest.approx(2.0)


def test_project_point_rejects_locations_outside_the_segment(wall):
    assert wall.project_point((-4.0, 0.0, 2.0)) is None  # behind the arc
    assert wall.project_point((4.0, 0.0, 9.0)) is None  # above the top


def test_flat_wall_helper_is_effectively_planar():
    wall = flat_wall_as_cylinder(width=4.0, height=2.5)
    assert wall.arc_length == pytest.approx(4.0)
    sagitta = wall.radius - math.sqrt(wall.radius**2 - (4.0 / 2) ** 2)
    assert sagitta < 1e-3  # under a millimetre of bow across 4 m


@pytest.mark.parametrize("radius", [0.0, -1.0])
def test_flat_wall_helper_rejects_non_positive_radius(radius):
    with pytest.raises(ProjectionError, match="wall radius must be greater than zero"):
        flat_wall_as_cylinder(width=4.0, height=2.5, radius=radius)


def test_wall_outline_spans_the_whole_arc(wall):
    pts = wall_outline(wall, segments=12)
    assert len(pts) == 12
    assert pts[0] == pytest.approx(wall.point_at(0.0, 0.0))
    assert pts[-1] == pytest.approx(wall.point_at(wall.arc_length, 0.0))


def test_concave_wall_rejects_a_back_face_hit():
    wall = CylindricalWall(radius=5.0, height=3.0, concave=True)
    assert wall.intersect_ray((7.0, 0.0, 1.5), (-1.0, 0.0, 0.0)) is None


def test_angle_wrapping_handles_arbitrary_full_turn_offsets():
    wall = CylindricalWall(
        radius=5.0,
        height=3.0,
        angle_start=100.0,
        angle_end=101.0,
    )
    origin = wall.axis_point(1.5)
    assert wall.intersect_ray(origin, normalize(sub(wall.center_point(), origin))) is not None


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_non_finite_wall_dimensions_and_angles_are_rejected(value):
    with pytest.raises(ProjectionError):
        CylindricalWall(radius=value)
    with pytest.raises(ProjectionError):
        CylindricalWall(angle_start=value, angle_end=1.0)
