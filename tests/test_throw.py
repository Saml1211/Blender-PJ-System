"""Tests for throw geometry against the production module."""

from __future__ import annotations

import math

import pytest

from blender_projection_system.core import throw
from blender_projection_system.core.errors import ProjectionError


def test_throw_ratio_is_distance_over_width():
    assert throw.throw_ratio_from(6.0, 3.0) == pytest.approx(2.0)


def test_the_three_throw_quantities_round_trip():
    distance, ratio = 7.5, 1.35
    width = throw.image_width_from_distance(distance, ratio)
    assert throw.throw_distance_from_width(width, ratio) == pytest.approx(distance)
    assert throw.throw_ratio_from(distance, width) == pytest.approx(ratio)


@pytest.mark.parametrize(
    "func, args",
    [
        (throw.image_width_from_distance, (0.0, 2.0)),
        (throw.image_width_from_distance, (5.0, 0.0)),
        (throw.throw_distance_from_width, (-1.0, 2.0)),
        (throw.throw_ratio_from, (5.0, 0.0)),
        (throw.image_height_from_width, (2.0, 0.0)),
    ],
)
def test_degenerate_inputs_raise_rather_than_returning_inf(func, args):
    # The old implementation returned float('inf') and let it poison the
    # scene; refusing the input is the useful behaviour.
    with pytest.raises(ProjectionError):
        func(*args)


def test_image_height_follows_aspect_ratio():
    spec = throw.ProjectorSpec(throw_ratio=2.0, aspect_w=16, aspect_h=9)
    size = throw.image_size(distance=8.0, spec=spec)
    assert size.width == pytest.approx(4.0)
    assert size.height == pytest.approx(4.0 * 9 / 16)
    assert size.diagonal == pytest.approx(math.hypot(size.width, size.height))


def test_image_size_scales_linearly_with_distance():
    spec = throw.ProjectorSpec(throw_ratio=1.2)
    a = throw.image_size(3.0, spec)
    b = throw.image_size(9.0, spec)
    assert b.width == pytest.approx(a.width * 3.0)
    assert b.height == pytest.approx(a.height * 3.0)


def test_half_angles_match_the_tangent_definition():
    spec = throw.ProjectorSpec(throw_ratio=1.5, aspect_w=16, aspect_h=10)
    th, tv = throw.half_angles(spec)
    assert math.tan(th) == pytest.approx(1.0 / (2 * 1.5))
    assert math.tan(tv) == pytest.approx(1.0 / (2 * 1.5 * 1.6))


def test_half_angle_reproduces_the_image_at_the_throw_distance():
    spec = throw.ProjectorSpec(throw_ratio=0.8)
    distance = 5.0
    th, tv = throw.half_angles(spec)
    size = throw.image_size(distance, spec)
    assert 2 * distance * math.tan(th) == pytest.approx(size.width)
    assert 2 * distance * math.tan(tv) == pytest.approx(size.height)


def test_aspect_ratio_rejects_zero_components():
    with pytest.raises(ProjectionError):
        throw.ProjectorSpec(aspect_w=0)
    with pytest.raises(ProjectionError):
        throw.ProjectorSpec(aspect_h=-9)


def test_zero_throw_ratio_is_rejected_at_construction():
    with pytest.raises(ProjectionError):
        throw.ProjectorSpec(throw_ratio=0.0)


def test_lens_shift_moves_the_image_but_not_its_size():
    plain = throw.ProjectorSpec(throw_ratio=1.5)
    shifted = throw.ProjectorSpec(throw_ratio=1.5, lens_shift_v=-0.25)
    assert throw.image_size(4.0, plain) == throw.image_size(4.0, shifted)
    assert throw.half_angles(plain) == throw.half_angles(shifted)

    size = throw.image_size(4.0, plain)
    centre = throw.image_point_local(0.0, 0.0, 4.0, shifted)
    assert centre[1] == pytest.approx(-0.25 * size.height)
    assert centre[2] == pytest.approx(-4.0)


def test_half_image_shift_puts_the_axis_on_the_image_edge():
    spec = throw.ProjectorSpec(throw_ratio=1.5, lens_shift_v=0.5)
    top = throw.image_point_local(0.0, 0.5, 4.0, spec)
    bottom = throw.image_point_local(0.0, -0.5, 4.0, spec)
    assert bottom[1] == pytest.approx(0.0)  # axis sits on the bottom edge
    assert top[1] > 0.0


def test_datasheet_percent_conversion():
    # A datasheet "100% offset" means the axis reaches the image edge.
    assert throw.shift_from_half_image_percent(100.0) == pytest.approx(0.5)
    assert throw.shift_to_half_image_percent(0.5) == pytest.approx(100.0)
    assert throw.shift_from_half_image_percent(
        throw.shift_to_half_image_percent(0.123)
    ) == pytest.approx(0.123)


def test_ray_direction_is_independent_of_distance():
    spec = throw.ProjectorSpec(throw_ratio=1.1, lens_shift_v=-0.3, lens_shift_h=0.05)
    direction = throw.ray_direction_local(0.25, -0.4, spec)
    for distance in (0.5, 4.0, 40.0):
        point = throw.image_point_local(0.25, -0.4, distance, spec)
        scale = -distance / direction[2]
        for got, want in zip((d * scale for d in direction), point, strict=False):
            assert got == pytest.approx(want)


def test_ray_directions_are_unit_length():
    spec = throw.ProjectorSpec(throw_ratio=0.75, aspect_w=16, aspect_h=9)
    for direction in throw.frustum_corner_rays(spec):
        assert math.sqrt(sum(c * c for c in direction)) == pytest.approx(1.0)
        assert direction[2] < 0.0  # forward is -Z


def test_frustum_corners_are_ordered_and_sized():
    spec = throw.ProjectorSpec(throw_ratio=2.0, aspect_w=2, aspect_h=1)
    tl, tr, br, bl = throw.frustum_corners_local(4.0, spec)
    size = throw.image_size(4.0, spec)
    assert tr[0] - tl[0] == pytest.approx(size.width)
    assert br[0] - bl[0] == pytest.approx(size.width)
    assert tl[1] - bl[1] == pytest.approx(size.height)
    assert all(c[2] == pytest.approx(-4.0) for c in (tl, tr, br, bl))


def test_required_lens_shift_for_a_ceiling_drop():
    # A 0.9 m drop with a 1.8 m tall image needs -50% shift.
    assert throw.required_lens_shift_v(-0.9, 1.8) == pytest.approx(-0.5)


def test_grid_uv_covers_the_full_image_including_edges():
    uv = throw.grid_uv(5)
    assert len(uv) == 25
    us = {round(u, 6) for u, _ in uv}
    vs = {round(v, 6) for _, v in uv}
    assert min(us) == pytest.approx(-0.5) and max(us) == pytest.approx(0.5)
    assert min(vs) == pytest.approx(-0.5) and max(vs) == pytest.approx(0.5)
    assert uv[0] == (-0.5, 0.5)  # top-left first


def test_grid_boundary_walks_the_perimeter_once():
    n = 5
    indices = throw.grid_boundary_indices(n)
    assert len(indices) == 4 * (n - 1)
    assert len(set(indices)) == len(indices)
    uv = throw.grid_uv(n)
    for i in indices:
        u, v = uv[i]
        assert abs(u) == pytest.approx(0.5) or abs(v) == pytest.approx(0.5)


def test_describe_throw_flags_lens_shift_beyond_the_limit():
    spec = throw.ProjectorSpec(throw_ratio=1.5, lens_shift_v=-0.8, max_lens_shift_v=0.5)
    report = throw.describe_throw(6.0, spec)
    assert report.warnings
    assert "lens shift" in report.warnings[0]


def test_describe_throw_flags_a_ratio_outside_the_lens_range():
    spec = throw.ProjectorSpec(throw_ratio=3.0, throw_ratio_min=0.8, throw_ratio_max=1.6)
    report = throw.describe_throw(6.0, spec)
    assert any("lens range" in w for w in report.warnings)


def test_describe_throw_is_quiet_when_everything_is_in_range():
    spec = throw.ProjectorSpec(throw_ratio=1.2, throw_ratio_min=0.8, throw_ratio_max=1.6)
    assert throw.describe_throw(6.0, spec).warnings == []
