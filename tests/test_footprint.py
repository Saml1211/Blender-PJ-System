"""Tests for footprint sampling on curved and near-flat surfaces."""

from __future__ import annotations

import math

import pytest

from blender_projection_system.core import photometry as ph
from blender_projection_system.core.errors import ProjectionError
from blender_projection_system.core.footprint import (
    compute_footprint,
    footprint_corners_world,
    frustum_edge_lines,
    point_in_polygon,
    polygon_area,
    throw_distance_to_wall,
)
from blender_projection_system.core.pose import look_at
from blender_projection_system.core.surfaces import CylindricalWall, flat_wall_as_cylinder
from blender_projection_system.core.throw import ProjectorSpec, image_size


@pytest.fixture
def curved_wall() -> CylindricalWall:
    return CylindricalWall(
        base_center=(0.0, 0.0, 0.0),
        radius=8.0,
        height=3.5,
        angle_start=math.radians(-45.0),
        angle_end=math.radians(45.0),
    )


def _aim_from_axis(wall: CylindricalWall, distance_from_wall: float, z: float, spec):
    """Place a projector on the radial centre line, aimed square at the wall."""
    s = wall.arc_length / 2
    target = wall.point_at(s, z)
    normal = wall.normal_at_s(s)
    origin = (
        target[0] + normal[0] * distance_from_wall,
        target[1] + normal[1] * distance_from_wall,
        z,
    )
    return look_at(origin, target), origin, target


# -- validation against textbook flat-screen geometry --------------------


def test_a_near_flat_wall_reproduces_the_throw_formula_image_size():
    """Footprint sampling must agree with W = D/TR on an (almost) flat wall."""
    wall = flat_wall_as_cylinder(width=40.0, height=20.0, radius=100000.0)
    spec = ProjectorSpec(throw_ratio=1.5, aspect_w=16, aspect_h=9)
    distance = 6.0
    pose, _origin, _target = _aim_from_axis(wall, distance, wall.height / 2, spec)

    fp = compute_footprint(pose, spec, wall, samples=9)
    expected = image_size(distance, spec)

    assert fp.hit_ratio == 1.0
    assert fp.arc_span == pytest.approx(expected.width, rel=1e-3)
    assert fp.height_span == pytest.approx(expected.height, rel=1e-3)
    assert fp.center_distance == pytest.approx(distance, rel=1e-4)


def test_full_circle_footprint_crossing_the_seam_keeps_its_narrow_arc_span():
    wall = CylindricalWall(
        radius=8.0,
        height=3.0,
        angle_start=-math.pi,
        angle_end=math.pi,
    )
    spec = ProjectorSpec(throw_ratio=1.5)
    target = wall.point_at(0.0, 1.5)
    inward = wall.normal_at_s(0.0)
    origin = (
        target[0] + inward[0] * 4.0,
        target[1] + inward[1] * 4.0,
        target[2],
    )
    fp = compute_footprint(look_at(origin, target), spec, wall, samples=11)

    assert fp.hit_ratio == 1.0
    assert 1.0 < fp.arc_span < 5.0
    assert max(s for s, _z in fp.boundary) - min(s for s, _z in fp.boundary) < 5.0


@pytest.mark.parametrize("throw_ratio", [0.8, 1.2, 2.5])
def test_flat_wall_image_width_tracks_throw_ratio(throw_ratio):
    wall = flat_wall_as_cylinder(width=60.0, height=30.0, radius=100000.0)
    spec = ProjectorSpec(throw_ratio=throw_ratio)
    distance = 5.0
    pose, _o, _t = _aim_from_axis(wall, distance, wall.height / 2, spec)
    fp = compute_footprint(pose, spec, wall, samples=7)
    assert fp.arc_span == pytest.approx(distance / throw_ratio, rel=2e-3)


def test_mean_illuminance_on_a_flat_wall_conserves_luminous_flux():
    """Energy check: averaging the sampled lux over a flat image must return
    lumens / area, because a uniform (u, v) grid is uniform in screen area."""
    wall = flat_wall_as_cylinder(width=60.0, height=30.0, radius=200000.0)
    spec = ProjectorSpec(throw_ratio=2.0, lumens=6000.0)
    distance = 6.0
    pose, _o, _t = _aim_from_axis(wall, distance, wall.height / 2, spec)
    fp = compute_footprint(pose, spec, wall, samples=21)

    size = image_size(distance, spec)
    expected_mean = ph.nominal_screen_illuminance(spec, size.area)
    got_mean = sum(fp.illuminance_samples()) / len(fp.illuminance_samples())
    assert got_mean == pytest.approx(expected_mean, rel=0.01)


# -- curved-wall behaviour ------------------------------------------------


def test_a_curved_wall_footprint_lands_entirely_on_the_surface(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    pose, _o, _t = _aim_from_axis(curved_wall, 4.0, 1.75, spec)
    fp = compute_footprint(pose, spec, curved_wall, samples=9, name="P1")
    assert fp.hit_ratio == 1.0
    assert fp.fully_on_surface
    assert fp.arc_span > 0.0 and fp.height_span > 0.0
    assert all(0.0 <= h.s <= curved_wall.arc_length for h in fp.hits())
    assert all(0.0 <= h.z <= curved_wall.height for h in fp.hits())


def test_the_axial_hit_is_the_nearest_point_of_a_concave_wall(curved_wall):
    """From inside a cylinder the closest surface point lies straight out along
    the radius, so the image centre has the shortest throw and the corners the
    longest. Focus therefore has to be set for a range, not a single distance.
    """
    spec = ProjectorSpec(throw_ratio=1.0)
    pose, _o, _t = _aim_from_axis(curved_wall, 5.0, 1.75, spec)
    fp = compute_footprint(pose, spec, curved_wall, samples=9)
    assert fp.center_distance == pytest.approx(fp.min_distance, rel=1e-9)
    assert fp.max_distance > fp.center_distance


def test_a_concave_wall_clips_the_image_narrower_than_a_flat_screen(curved_wall):
    """A flat screen at the same axial distance would sit outside the cylinder
    at the edges, so the curved wall intercepts the edge rays early and the
    image comes out narrower than W = D/TR - while still exceeding the chord."""
    spec = ProjectorSpec(throw_ratio=1.0)
    distance = 5.0
    pose, _o, _t = _aim_from_axis(curved_wall, distance, 1.75, spec)
    fp = compute_footprint(pose, spec, curved_wall, samples=11)
    flat_width = image_size(distance, spec).width

    assert fp.arc_span < flat_width

    left = curved_wall.point_at(fp.s_min, 1.75)
    right = curved_wall.point_at(fp.s_max, 1.75)
    chord = math.dist(left, right)
    assert chord < fp.arc_span  # arc always exceeds the chord it subtends


def test_the_curved_wall_error_shrinks_as_the_radius_grows():
    """Sanity anchor: as the wall flattens, the sampled span must converge on
    the textbook flat-screen width."""
    spec = ProjectorSpec(throw_ratio=1.0)
    distance = 5.0
    flat_width = image_size(distance, spec).width
    errors = []
    for radius in (8.0, 40.0, 200.0, 2000.0):
        wall = CylindricalWall(
            radius=radius,
            height=3.5,
            angle_start=-math.radians(45.0),
            angle_end=math.radians(45.0),
        )
        pose, _o, _t = _aim_from_axis(wall, distance, 1.75, spec)
        fp = compute_footprint(pose, spec, wall, samples=9)
        errors.append(abs(fp.arc_span - flat_width) / flat_width)
    assert errors == sorted(errors, reverse=True)
    assert errors[-1] < 1e-3


def test_incidence_is_worst_at_the_image_edges(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.0)
    pose, _o, _t = _aim_from_axis(curved_wall, 5.0, 1.75, spec)
    fp = compute_footprint(pose, spec, curved_wall, samples=9)
    centre = min(fp.samples, key=lambda s: s.u * s.u + s.v * s.v)
    assert centre.hit is not None
    assert fp.max_incidence > centre.hit.incidence


def test_an_over_wide_image_spills_and_is_reported(curved_wall):
    spec = ProjectorSpec(throw_ratio=0.35)  # very wide lens, image overruns the wall
    pose, _o, _t = _aim_from_axis(curved_wall, 6.0, 1.75, spec)
    fp = compute_footprint(pose, spec, curved_wall, samples=9, name="Spill")
    assert fp.hit_ratio < 1.0
    assert not fp.fully_on_surface
    assert any("spills past" in w for w in fp.warnings)


def test_aiming_away_from_the_wall_yields_no_hits(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    origin = curved_wall.axis_point(1.75)
    pose = look_at(origin, (origin[0] - 5.0, origin[1], origin[2]))
    fp = compute_footprint(pose, spec, curved_wall, samples=5, name="Missed")
    assert fp.hit_ratio == 0.0
    assert fp.boundary == []
    assert any("no part of the image lands" in w for w in fp.warnings)


def test_a_grazing_hit_raises_an_incidence_warning(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    # Sit near one end of the arc and rake across to the other.
    origin_target = curved_wall.point_at(curved_wall.arc_length * 0.02, 1.75)
    normal = curved_wall.normal_at_s(curved_wall.arc_length * 0.02)
    origin = (
        origin_target[0] + normal[0] * 1.0,
        origin_target[1] + normal[1] * 1.0,
        1.75,
    )
    pose = look_at(origin, curved_wall.point_at(curved_wall.arc_length * 0.85, 1.75))
    fp = compute_footprint(pose, spec, curved_wall, samples=9, name="Grazing")
    assert math.degrees(fp.max_incidence) > 45.0
    assert any("incidence" in w for w in fp.warnings)


def test_lens_shift_moves_the_footprint_down_without_resizing_it(curved_wall):
    base = ProjectorSpec(throw_ratio=1.5)
    shifted = ProjectorSpec(throw_ratio=1.5, lens_shift_v=-0.4)
    pose, _o, _t = _aim_from_axis(curved_wall, 4.0, 2.5, base)

    a = compute_footprint(pose, base, curved_wall, samples=9)
    b = compute_footprint(pose, shifted, curved_wall, samples=9)
    assert b.z_max < a.z_max and b.z_min < a.z_min
    assert b.height_span == pytest.approx(a.height_span, rel=0.05)

    centre_sample = min(b.samples, key=lambda sample: sample.u**2 + sample.v**2)
    assert centre_sample.hit is not None
    optical_depth = sum(
        (centre_sample.hit.point[i] - pose.origin[i]) * pose.forward[i]
        for i in range(3)
    )
    assert b.center_distance == pytest.approx(optical_depth)
    assert b.center_distance < centre_sample.hit.distance


def test_sample_count_below_two_is_rejected(curved_wall):
    with pytest.raises(ProjectionError):
        compute_footprint(
            look_at((0.0, 0.0, 1.0), (8.0, 0.0, 1.0)),
            ProjectorSpec(),
            curved_wall,
            samples=1,
        )


def test_higher_sampling_converges_rather_than_drifting(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.2)
    pose, _o, _t = _aim_from_axis(curved_wall, 4.5, 1.75, spec)
    spans = [compute_footprint(pose, spec, curved_wall, samples=n).arc_span for n in (5, 9, 17, 33)]
    # The extents come from the image edges, which every grid includes.
    assert spans[-1] == pytest.approx(spans[0], rel=1e-6)


# -- derived geometry -----------------------------------------------------


def test_boundary_is_a_closed_perimeter_with_real_area(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    pose, _o, _t = _aim_from_axis(curved_wall, 4.0, 1.75, spec)
    fp = compute_footprint(pose, spec, curved_wall, samples=9)
    assert len(fp.boundary) == 4 * (9 - 1)
    assert len(fp.boundary_points) == len(fp.boundary)
    area = polygon_area(fp.boundary)
    assert area == pytest.approx(fp.arc_span * fp.height_span, rel=0.15)


def test_the_footprint_centre_is_inside_its_own_boundary(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    pose, _o, _t = _aim_from_axis(curved_wall, 4.0, 1.75, spec)
    fp = compute_footprint(pose, spec, curved_wall, samples=9)
    centre = ((fp.s_min + fp.s_max) / 2, (fp.z_min + fp.z_max) / 2)
    assert point_in_polygon(centre, fp.boundary)
    assert not point_in_polygon((fp.s_max + 1.0, centre[1]), fp.boundary)
    assert not point_in_polygon((centre[0], fp.z_max + 1.0), fp.boundary)


def test_point_in_polygon_handles_a_simple_square():
    square = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    assert point_in_polygon((1.0, 1.0), square)
    assert not point_in_polygon((3.0, 1.0), square)
    assert not point_in_polygon((-1.0, 1.0), square)
    assert polygon_area(square) == pytest.approx(4.0)


def test_polygon_area_of_a_degenerate_shape_is_zero():
    assert polygon_area([(0.0, 0.0), (1.0, 1.0)]) == 0.0


def test_corner_and_edge_helpers_produce_drawable_geometry(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    pose, origin, _t = _aim_from_axis(curved_wall, 4.0, 1.75, spec)
    fp = compute_footprint(pose, spec, curved_wall, samples=9)
    corners = footprint_corners_world(fp)
    assert len(corners) == 4
    lines = frustum_edge_lines(fp)
    assert len(lines) == 4
    assert all(start == origin for start, _end in lines)


def test_axis_throw_distance_matches_the_centre_sample(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    pose, _o, _t = _aim_from_axis(curved_wall, 4.25, 1.75, spec)
    fp = compute_footprint(pose, spec, curved_wall, samples=9)
    assert throw_distance_to_wall(pose, spec, curved_wall) == pytest.approx(
        fp.center_distance, rel=1e-6
    )


def test_axis_throw_distance_is_none_when_the_wall_is_missed(curved_wall):
    origin = curved_wall.axis_point(1.75)
    pose = look_at(origin, (origin[0] - 5.0, origin[1], origin[2]))
    assert throw_distance_to_wall(pose, ProjectorSpec(), curved_wall) is None


# -- back-projection (inverse of the forward ray cast) --------------------


def test_back_projection_inverts_the_forward_ray_cast(curved_wall):
    """Every sampled hit must map back to the (u, v) it was cast from."""
    spec = ProjectorSpec(throw_ratio=1.3, lens_shift_v=-0.35, lens_shift_h=0.05)
    pose, _o, _t = _aim_from_axis(curved_wall, 4.5, 2.2, spec)
    fp = compute_footprint(pose, spec, curved_wall, samples=7)

    for sample in fp.samples:
        if sample.hit is None:
            continue
        uv = fp.image_uv_of(sample.hit.point)
        assert uv is not None
        assert uv[0] == pytest.approx(sample.u, abs=1e-9)
        assert uv[1] == pytest.approx(sample.v, abs=1e-9)


def test_covers_accepts_points_inside_and_rejects_points_outside(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    pose, _o, _t = _aim_from_axis(curved_wall, 4.0, 1.75, spec)
    fp = compute_footprint(pose, spec, curved_wall, samples=9)

    centre = curved_wall.point_at((fp.s_min + fp.s_max) / 2, (fp.z_min + fp.z_max) / 2)
    assert fp.covers(centre)

    outside = curved_wall.point_at(curved_wall.arc_length * 0.02, 0.1)
    assert not fp.covers(outside)


def test_points_behind_the_lens_are_never_covered(curved_wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    pose, origin, _t = _aim_from_axis(curved_wall, 4.0, 1.75, spec)
    fp = compute_footprint(pose, spec, curved_wall, samples=5)

    behind = (
        origin[0] - pose.forward[0] * 2.0,
        origin[1] - pose.forward[1] * 2.0,
        origin[2] - pose.forward[2] * 2.0,
    )
    assert fp.image_uv_of(behind) is None
    assert not fp.covers(behind)
    assert not fp.covers(origin)


def test_back_projection_survives_a_footprint_clipped_by_the_wall_edge(curved_wall):
    """The regression this replaced polygon testing for.

    When the image overruns the wall, the boundary walk skips the missed
    samples and closes across the gap, so a point-in-polygon test reports the
    lit area as smaller than it is. Back-projection is unaffected.
    """
    spec = ProjectorSpec(throw_ratio=0.5)  # wide enough to spill off the top
    pose, _o, _t = _aim_from_axis(curved_wall, 5.0, 2.8, spec)
    fp = compute_footprint(pose, spec, curved_wall, samples=9)
    assert not fp.fully_on_surface  # precondition: it really does spill

    covered_by_backprojection = 0
    covered_by_polygon = 0
    for i in range(60):
        for j in range(20):
            s = curved_wall.arc_length * (i + 0.5) / 60
            z = curved_wall.height * (j + 0.5) / 20
            if fp.covers(curved_wall.point_at(s, z)):
                covered_by_backprojection += 1
            if point_in_polygon((s, z), fp.boundary):
                covered_by_polygon += 1

    assert covered_by_backprojection > covered_by_polygon
    # Every sampled hit is by definition inside the image, so back-projection
    # must agree with the forward cast on all of them.
    for sample in fp.samples:
        if sample.hit is not None:
            assert fp.covers(sample.hit.point)


def test_lens_shift_is_honoured_by_back_projection(curved_wall):
    """A shifted lens must report a shifted covered region, not a centred one."""
    base = ProjectorSpec(throw_ratio=1.5)
    shifted = ProjectorSpec(throw_ratio=1.5, lens_shift_v=-0.45)
    pose, _o, _t = _aim_from_axis(curved_wall, 4.0, 2.6, base)

    a = compute_footprint(pose, base, curved_wall, samples=9)
    b = compute_footprint(pose, shifted, curved_wall, samples=9)

    high = curved_wall.point_at(curved_wall.arc_length / 2, 3.3)
    low = curved_wall.point_at(curved_wall.arc_length / 2, 1.4)
    assert a.covers(high) and not b.covers(high)
    assert b.covers(low) and not a.covers(low)


def test_full_convex_cylinder_does_not_cover_the_occluded_far_side():
    wall = CylindricalWall(
        radius=5.0,
        height=3.0,
        angle_start=-math.pi,
        angle_end=math.pi,
        concave=False,
    )
    spec = ProjectorSpec(throw_ratio=0.5)
    pose = look_at((8.0, 0.0, 1.5), (5.0, 0.0, 1.5))
    fp = compute_footprint(pose, spec, wall, samples=9)
    assert fp.covers((-5.0, 0.0, 1.5)) is False
