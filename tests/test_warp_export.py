"""Tests for warp/corner-pin grid export (increment #4 phase 2).

The grid describes, per projector, a lattice over the illuminated wall
region with the image-space UV each lattice point receives. Output space is
the wall's ``(s, z)`` coordinates plus the world point; input space is the
projector image normalized to ``[0, 1]`` with ``(0, 0)`` at the image's
top-left. Everything is design-phase geometry per ADR 0002.
"""

from __future__ import annotations

import json

import pytest

from blender_projection_system.core.errors import ProjectionError
from blender_projection_system.core.footprint import (
    compute_footprint,
    footprint_corners_world,
)
from blender_projection_system.core.pose import look_at
from blender_projection_system.core.surfaces import CylindricalWall, PlanarWall
from blender_projection_system.core.throw import ProjectorSpec, ray_direction_local
from blender_projection_system.core.vectors import distance
from blender_projection_system.core.warp_export import (
    WARP_SCHEMA_VERSION,
    build_warp_grid,
    export_warp_grids_to_json,
    export_warp_meshes_to_obj,
)


def _wall_and_pose(standoff: float):
    """A 4 x 2.5 m flat wall at x=5 facing -X, projector aimed at its centre."""
    wall = PlanarWall(base_center=(5.0, 0.0, 0.0), width=4.0, height=2.5)
    spec = ProjectorSpec(throw_ratio=1.2, lumens=6000.0)
    target = wall.center_point()
    pose = look_at((target[0] - standoff, target[1], target[2]), target)
    return wall, spec, pose


@pytest.fixture
def contained():
    """Wall, spec, pose and footprint for a fully contained image (4.5 m throw)."""
    wall, spec, pose = _wall_and_pose(4.5)
    fp = compute_footprint(pose, spec, wall, samples=9, name="PJ_01")
    return wall, spec, pose, fp


@pytest.fixture
def spilling():
    """Same wall, projector pulled back to 7 m so the image spills off all edges."""
    wall, spec, pose = _wall_and_pose(7.0)
    fp = compute_footprint(pose, spec, wall, samples=9, name="PJ_01")
    return wall, spec, pose, fp


@pytest.fixture
def keystoned():
    """Flat wall, projector below centre aiming up: a keystone trapezoid.

    The projected quad is wider at the top than at the bottom, so the
    (s, z) bounding box has corners the image never reaches - the
    deterministic out-of-image case for the validity filter.
    """
    wall = PlanarWall(base_center=(5.0, 0.0, 0.0), width=4.0, height=2.5)
    spec = ProjectorSpec(throw_ratio=1.5, lumens=6000.0)
    target = wall.center_point()
    pose = look_at((1.0, 0.0, 0.6), target)
    fp = compute_footprint(pose, spec, wall, samples=15, name="PJ_02")
    return wall, spec, pose, fp


# -- grid construction --------------------------------------------------------


def test_contained_image_yields_an_all_valid_grid(contained):
    wall, spec, pose, fp = contained
    grid = build_warp_grid(fp, resolution=8)

    assert grid.name == "PJ_01"
    assert grid.columns == 8 and grid.rows == 8
    assert len(grid.vertices) == 64
    assert all(v.valid for v in grid.vertices)
    for vertex in grid.vertices:
        assert vertex.uv is not None
        u, v = vertex.uv
        assert 0.0 <= u <= 1.0
        assert 0.0 <= v <= 1.0


def test_grid_vertices_are_row_major_top_first(contained):
    wall, spec, pose, fp = contained
    grid = build_warp_grid(fp, resolution=4)

    rows = [grid.vertices[i * 4 : (i + 1) * 4] for i in range(4)]
    # Row 0 is the highest z; column 0 is the lowest s.
    assert rows[0][0].z == max(v.z for v in grid.vertices)
    assert rows[-1][0].z == min(v.z for v in grid.vertices)
    s_row0 = [v.s for v in rows[0]]
    assert s_row0 == sorted(s_row0)


def test_emitted_uv_forward_casts_back_to_the_wall_point(contained):
    """For each valid vertex, the ray through its uv must re-hit its wall point."""
    wall, spec, pose, fp = contained
    grid = build_warp_grid(fp, resolution=8)

    for vertex in grid.vertices:
        assert vertex.valid and vertex.uv is not None
        u_img = vertex.uv[0] - 0.5
        v_img = vertex.uv[1] - 0.5
        direction = pose.local_to_world_dir(ray_direction_local(u_img, v_img, spec))
        hit = wall.intersect_ray(pose.origin, direction)
        assert hit is not None
        expected = wall.point_at(vertex.s, vertex.z)
        assert distance(hit.point, expected) < 1e-6


def test_corner_pin_matches_the_footprint_corners(contained):
    wall, spec, pose, fp = contained
    grid = build_warp_grid(fp, resolution=4)

    assert len(grid.corners) == 4
    assert {c.uv for c in grid.corners} == {(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)}
    for corner, world in zip(grid.corners, footprint_corners_world(fp), strict=True):
        assert distance(corner.world, world) < 1e-9


def test_spilling_image_reports_an_incomplete_corner_pin(spilling):
    wall, spec, pose, fp = spilling
    assert len(footprint_corners_world(fp)) == 0  # all four corners off the wall

    grid = build_warp_grid(fp, resolution=4)

    assert len(grid.corners) == 0
    assert any("corner" in w.lower() for w in grid.warnings)
    # The clipped lattice is still fully illuminated on a flat, centred throw.
    assert all(v.valid for v in grid.vertices)


def test_keystoned_image_marks_out_of_image_vertices_invalid(keystoned):
    wall, spec, pose, fp = keystoned
    grid = build_warp_grid(fp, resolution=12)

    assert any(not v.valid for v in grid.vertices)
    for vertex in grid.vertices:
        if vertex.valid:
            assert vertex.uv is not None
            u, v = vertex.uv
            assert 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0
        else:
            assert vertex.uv is None


def test_valid_vertices_round_trip_on_the_keystoned_wall(keystoned):
    wall, spec, pose, fp = keystoned
    grid = build_warp_grid(fp, resolution=12)

    for vertex in grid.vertices:
        if not vertex.valid:
            continue
        u_img = vertex.uv[0] - 0.5
        v_img = vertex.uv[1] - 0.5
        direction = pose.local_to_world_dir(ray_direction_local(u_img, v_img, spec))
        hit = wall.intersect_ray(pose.origin, direction)
        assert hit is not None
        expected = wall.point_at(vertex.s, vertex.z)
        assert distance(hit.point, expected) < 1e-6


def test_full_circle_seam_round_trips():
    """A wrapped footprint's unwrapped s values still round-trip through point_at."""
    wall = CylindricalWall(radius=8.0, height=3.0, angle_start=0.0, angle_end=2.0 * 3.141592653589793)
    spec = ProjectorSpec(throw_ratio=1.2, lumens=6000.0)
    pose = look_at((0.0, 0.0, 1.5), (8.0, 0.0, 1.5))  # aimed at the s = 0 seam
    fp = compute_footprint(pose, spec, wall, samples=15, name="PJ_03")

    grid = build_warp_grid(fp, resolution=8)

    assert wall.wraps_around
    assert grid.s_min < wall.arc_length < grid.s_max  # footprint straddles the seam
    for vertex in grid.vertices:
        if not vertex.valid:
            continue
        u_img = vertex.uv[0] - 0.5
        v_img = vertex.uv[1] - 0.5
        direction = pose.local_to_world_dir(ray_direction_local(u_img, v_img, spec))
        hit = wall.intersect_ray(pose.origin, direction)
        assert hit is not None
        expected = wall.point_at(vertex.s, vertex.z)
        assert distance(hit.point, expected) < 1e-6


def test_resolution_below_two_is_rejected(contained):
    wall, spec, pose, fp = contained
    with pytest.raises(ProjectionError):
        build_warp_grid(fp, resolution=1)


# -- JSON export --------------------------------------------------------------


def test_json_export_structure_and_round_trip(contained):
    wall, spec, pose, fp = contained
    grid = build_warp_grid(fp, resolution=4)

    payload = json.loads(
        export_warp_grids_to_json(wall, [grid], generator="Projection Planner 0.6.0")
    )

    assert payload["schema_version"] == WARP_SCHEMA_VERSION == 1
    assert payload["generator"] == "Projection Planner 0.6.0"
    assert payload["wall"]["name"] == wall.name
    assert payload["wall"]["arc_length_m"] == pytest.approx(wall.arc_length, abs=1e-6)

    entry = payload["projectors"][0]
    assert entry["name"] == "PJ_01"
    assert entry["columns"] == 4 and entry["rows"] == 4
    assert len(entry["vertices"]) == 16
    assert len(entry["uv"]) == 16
    assert len(entry["valid"]) == 16
    first = entry["vertices"][0]
    assert len(first) == 5  # s, z, x, y, z
    assert entry["corner_pin"]["complete"] is True
    assert len(entry["corner_pin"]["corners"]) == 4


def test_json_disclaimer_states_design_phase_targets(contained):
    wall, spec, pose, fp = contained
    grid = build_warp_grid(fp, resolution=4)

    payload = json.loads(export_warp_grids_to_json(wall, [grid], generator="g"))

    assert "design-phase" in payload["disclaimer"].lower()
    assert "calibration" in payload["disclaimer"].lower()


def test_json_corner_pin_completeness_flag(spilling):
    wall, spec, pose, fp = spilling
    grid = build_warp_grid(fp, resolution=4)

    payload = json.loads(export_warp_grids_to_json(wall, [grid], generator="g"))

    entry = payload["projectors"][0]
    assert entry["corner_pin"]["complete"] is False
    assert entry["corner_pin"]["corners"] == []
    assert entry["warnings"]


# -- OBJ export ---------------------------------------------------------------


def test_obj_mesh_counts_and_uv_bounds(contained):
    wall, spec, pose, fp = contained
    grid = build_warp_grid(fp, resolution=5)

    obj = export_warp_meshes_to_obj(wall, [grid])
    lines = obj.splitlines()

    assert any(line.startswith("o ") and "PJ_01" in line for line in lines)
    v_count = sum(1 for line in lines if line.startswith("v "))
    vt_count = sum(1 for line in lines if line.startswith("vt "))
    f_count = sum(1 for line in lines if line.startswith("f "))
    assert v_count == 25
    assert vt_count == v_count
    assert f_count == 16  # every interior cell is valid
    for line in lines:
        if line.startswith("vt "):
            _, u, v = line.split()
            assert 0.0 <= float(u) <= 1.0
            assert 0.0 <= float(v) <= 1.0


def test_obj_skips_faces_for_invalid_cells(keystoned):
    wall, spec, pose, fp = keystoned
    grid = build_warp_grid(fp, resolution=12)

    obj = export_warp_meshes_to_obj(wall, [grid])
    lines = obj.splitlines()

    f_count = sum(1 for line in lines if line.startswith("f "))
    valid_cells = sum(
        1
        for row in range(11)
        for col in range(11)
        if all(
            grid.vertices[(row + dr) * 12 + col + dc].valid
            for dr in (0, 1)
            for dc in (0, 1)
        )
    )
    assert f_count == valid_cells
    assert f_count < 121  # the skewed quad really does lose cells


def test_obj_header_documents_units_and_uv_convention(contained):
    wall, spec, pose, fp = contained
    grid = build_warp_grid(fp, resolution=4)

    obj = export_warp_meshes_to_obj(wall, [grid])

    assert "metres" in obj.lower()
    assert "vt" in obj.lower() and "uv" in obj.lower()
    assert "design-phase" in obj.lower()
