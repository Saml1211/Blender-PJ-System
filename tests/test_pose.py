"""Tests for projector placement and orientation."""

from __future__ import annotations

import math

import pytest

from blender_projection_system.core.errors import ProjectionError
from blender_projection_system.core.pose import level_pose, look_at
from blender_projection_system.core.vectors import cross, dot, length, normalize, sub


def _assert_orthonormal(pose):
    for v in (pose.right, pose.up, pose.forward):
        assert length(v) == pytest.approx(1.0)
    assert dot(pose.right, pose.up) == pytest.approx(0.0, abs=1e-9)
    assert dot(pose.right, pose.forward) == pytest.approx(0.0, abs=1e-9)
    assert dot(pose.up, pose.forward) == pytest.approx(0.0, abs=1e-9)


def test_look_at_points_forward_at_the_target():
    pose = look_at((0.0, 0.0, 3.0), (4.0, 0.0, 1.0))
    _assert_orthonormal(pose)
    expected = normalize(sub((4.0, 0.0, 1.0), (0.0, 0.0, 3.0)))
    assert pose.forward == pytest.approx(expected)


def test_look_at_basis_is_right_handed():
    pose = look_at((0.0, 0.0, 2.0), (3.0, 1.0, 0.5))
    # right x up must equal the local +Z axis, which is -forward.
    assert cross(pose.right, pose.up) == pytest.approx(
        tuple(-c for c in pose.forward), abs=1e-9
    )


def test_look_at_keeps_the_projector_upright():
    pose = look_at((0.0, 0.0, 3.0), (5.0, 0.0, 1.0))
    assert pose.up[2] > 0.0
    assert pose.right[2] == pytest.approx(0.0, abs=1e-9)


def test_look_at_survives_a_straight_down_aim():
    pose = look_at((0.0, 0.0, 3.0), (0.0, 0.0, 0.0))
    _assert_orthonormal(pose)
    assert pose.forward == pytest.approx((0.0, 0.0, -1.0))


def test_look_at_rejects_a_coincident_target():
    with pytest.raises(ProjectionError):
        look_at((1.0, 1.0, 1.0), (1.0, 1.0, 1.0))


def test_normalize_reports_zero_vectors_as_projection_errors():
    with pytest.raises(ProjectionError, match="zero-length"):
        normalize((0.0, 0.0, 0.0))


def test_roll_rotates_about_the_optical_axis():
    straight = look_at((0.0, 0.0, 2.0), (5.0, 0.0, 2.0))
    rolled = look_at((0.0, 0.0, 2.0), (5.0, 0.0, 2.0), roll=math.pi / 2)
    _assert_orthonormal(rolled)
    assert rolled.forward == pytest.approx(straight.forward)
    assert dot(rolled.right, straight.up) == pytest.approx(1.0, abs=1e-9)


def test_tilt_is_zero_for_a_level_aim():
    assert look_at((0.0, 0.0, 2.0), (5.0, 0.0, 2.0)).tilt_deg == pytest.approx(0.0)


def test_tilt_is_negative_when_aiming_downward():
    pose = look_at((0.0, 0.0, 3.0), (3.0, 0.0, 0.0))
    assert pose.tilt_deg == pytest.approx(-45.0)


def test_level_pose_discards_the_vertical_component():
    pose = level_pose((0.0, 0.0, 3.0), heading=(1.0, 0.0, -5.0))
    assert pose.forward == pytest.approx((1.0, 0.0, 0.0))
    assert pose.tilt_deg == pytest.approx(0.0)


def test_level_pose_rejects_a_purely_vertical_heading():
    with pytest.raises(ProjectionError):
        level_pose((0.0, 0.0, 3.0), heading=(0.0, 0.0, -1.0))


def test_local_forward_maps_to_the_world_aim_direction():
    pose = look_at((1.0, 2.0, 3.0), (1.0, 8.0, 3.0))
    assert pose.local_to_world_dir((0.0, 0.0, -1.0)) == pytest.approx(pose.forward)
    assert pose.local_to_world_dir((1.0, 0.0, 0.0)) == pytest.approx(pose.right)
    assert pose.local_to_world_dir((0.0, 1.0, 0.0)) == pytest.approx(pose.up)


def test_local_to_world_point_lands_at_the_aim_target():
    origin, target = (0.0, 0.0, 4.0), (6.0, 0.0, 4.0)
    pose = look_at(origin, target)
    assert pose.local_to_world_point((0.0, 0.0, -6.0)) == pytest.approx(target)


def test_basis_columns_form_a_valid_rotation_matrix():
    pose = look_at((0.0, 0.0, 2.5), (4.0, 3.0, 1.0))
    x, y, z = pose.basis_columns()
    assert dot(x, y) == pytest.approx(0.0, abs=1e-9)
    assert dot(y, z) == pytest.approx(0.0, abs=1e-9)
    assert dot(x, z) == pytest.approx(0.0, abs=1e-9)
    # Determinant of +1 means no mirroring, which would flip the image.
    det = dot(cross(x, y), z)
    assert det == pytest.approx(1.0)
