"""Tests for line-of-sight occlusion (core/occlusion.py + coverage integration)."""

from __future__ import annotations

import math

import pytest

from blender_projection_system.core.coverage import (
    analyze_coverage,
    format_report,
)
from blender_projection_system.core.footprint import compute_footprint
from blender_projection_system.core.occlusion import (
    RAY_TOLERANCE,
    TriMeshOcclusionCaster,
    box_triangles,
    quad_triangles,
)
from blender_projection_system.core.pose import look_at
from blender_projection_system.core.surfaces import PlanarWall
from blender_projection_system.core.throw import ProjectorSpec


@pytest.fixture
def wall() -> PlanarWall:
    """A 4 m wide, 2.5 m tall flat wall whose face is at x=5, facing -X."""
    return PlanarWall(base_center=(5.0, 0.0, 0.0), width=4.0, height=2.5)


def _projector_at(wall, aim_y, spec, name="P1", standoff=4.0):
    z = wall.height / 2
    target = wall.point_at(wall.arc_length / 2 + aim_y, z)
    origin = (target[0] - standoff, target[1], z)
    return compute_footprint(look_at(origin, target), spec, wall, samples=9, name=name)


def _pillar_caster(y_center=0.0, y_half=0.3, x_near=3.0, x_far=3.5):
    """A full-height pillar slab between the projectors (x<3) and the wall (x=5)."""
    vertices, triangles = box_triangles(
        (x_near, y_center - y_half, 0.0), (x_far, y_center + y_half, 2.5)
    )
    return TriMeshOcclusionCaster(vertices, triangles)


# -- caster primitives --------------------------------------------------------


def test_box_and_quad_helpers_produce_sound_geometry():
    vertices, triangles = box_triangles((0.0, 0.0, 0.0), (1.0, 2.0, 3.0))
    assert len(vertices) == 8
    assert len(triangles) == 12
    assert all(len(tri) == 3 for tri in triangles)
    q_verts, q_tris = quad_triangles((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))
    assert len(q_verts) == 4
    assert len(q_tris) == 2


def test_a_ray_through_the_box_is_blocked():
    caster = TriMeshOcclusionCaster(*box_triangles((2.0, -0.5, -0.5), (3.0, 0.5, 0.5)))
    assert caster((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 10.0) is True


def test_a_ray_missing_the_box_reports_clear():
    caster = TriMeshOcclusionCaster(*box_triangles((2.0, -0.5, -0.5), (3.0, 0.5, 0.5)))
    diag = math.sqrt(0.5)
    # 45 degrees off axis passes the box at y=2.5, far outside its +-0.5 span.
    assert caster((0.0, 0.0, 0.0), (diag, diag, 0.0), 10.0) is False


def test_a_hit_beyond_max_distance_does_not_block():
    caster = TriMeshOcclusionCaster(*box_triangles((2.0, -0.5, -0.5), (3.0, 0.5, 0.5)))
    assert caster((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1.5) is False


def test_geometry_behind_the_origin_never_blocks():
    caster = TriMeshOcclusionCaster(*box_triangles((-3.0, -0.5, -0.5), (-2.0, 0.5, 0.5)))
    assert caster((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 10.0) is False


def test_hits_closer_than_the_tolerance_are_ignored():
    # A quad 0.5 mm in front of the origin: nearer than RAY_TOLERANCE, so it
    # belongs to the surface the ray starts on, not to an occluder.
    vertices, triangles = quad_triangles(
        (RAY_TOLERANCE / 2, -1.0, -1.0),
        (RAY_TOLERANCE / 2, 1.0, -1.0),
        (RAY_TOLERANCE / 2, 1.0, 1.0),
        (RAY_TOLERANCE / 2, -1.0, 1.0),
    )
    caster = TriMeshOcclusionCaster(vertices, triangles)
    assert caster((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 5.0) is False


def test_a_zero_reach_reports_clear():
    caster = TriMeshOcclusionCaster(*box_triangles((2.0, -0.5, -0.5), (3.0, 0.5, 0.5)))
    assert caster((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), RAY_TOLERANCE / 2) is False


def test_the_target_wall_itself_never_occludes_its_own_samples(wall):
    """A caster built from the wall plane must not shadow the wall (ADR 0002)."""
    vertices, triangles = quad_triangles(
        (5.0, -3.0, 0.0),
        (5.0, 3.0, 0.0),
        (5.0, 3.0, 3.0),
        (5.0, -3.0, 3.0),
    )
    caster = TriMeshOcclusionCaster(vertices, triangles)
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(wall, 0.0, spec)
    report = analyze_coverage([fp], wall, grid_s=40, grid_z=12, occlusion_caster=caster)

    assert report.occluded_cells == []
    assert report.shadowed_cells == []
    assert all(o.occluded_cells == 0 for o in report.projector_occlusions.values())
    assert all(o.total_potential_cells > 0 for o in report.projector_occlusions.values())
    assert not any("occluded" in w for w in report.warnings)


# -- coverage integration: one projector, one pillar --------------------------


def test_a_pillar_shadows_the_cells_behind_it(wall):
    """A full-height pillar casts a vertical shadow band on the wall.

    Geometry: projector 4 m from the wall, pillar 1.5-2.0 m from the wall
    (t = 0.5-0.625 of the throw) spanning |y| <= 0.3. A wall point at y_w is
    shadowed iff the ray crosses the pillar slab within its y span, i.e.
    roughly |y_w| < 0.53.
    """
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(wall, 0.0, spec)
    baseline = analyze_coverage([fp], wall, grid_s=40, grid_z=25)
    report = analyze_coverage([fp], wall, grid_s=40, grid_z=25, occlusion_caster=_pillar_caster())

    assert report.shadowed_cells, "the pillar must shadow something"
    assert all(
        abs((cell.s_start + cell.s_end) / 2 - wall.arc_length / 2) < 0.6
        for cell in report.shadowed_cells
    ), "shadowed cells must sit behind the pillar"
    # Single projector: every occluded cell is fully shadowed.
    tally = report.projector_occlusions["P1"]
    assert tally.occluded_cells == len(report.occluded_cells) == len(report.shadowed_cells)
    assert 0.0 < tally.occluded_fraction < 1.0
    assert report.covered_fraction < baseline.covered_fraction
    assert report.gap_area > baseline.gap_area


def test_occlusion_is_reported_loudly_in_warnings_and_report(wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(wall, 0.0, spec)
    report = analyze_coverage([fp], wall, grid_s=40, grid_z=25, occlusion_caster=_pillar_caster())

    assert any("occluded by an obstacle" in w for w in report.warnings)
    lines = format_report(report)
    assert any(line.startswith("Occlusion:") for line in lines)
    assert any("P1" in line and "occluded" in line for line in lines)


# -- coverage integration: two projectors -------------------------------------


def test_a_pillar_blocking_one_projector_thins_the_blend_zone(wall):
    """P1 and P2 overlap near the wall centre. A pillar offset toward P1's
    side blocks P1's rays across the whole overlap (each ray crosses the slab
    at 50-62% of the throw, landing inside the slab's y band), so those cells
    fall back to P2 alone. P2's own image never reaches the slab's shadow
    band, so its tally stays at zero; P1-only cells inside the band go dark."""
    spec = ProjectorSpec(throw_ratio=1.5)
    fp_left = _projector_at(wall, -1.0, spec, name="P1")
    fp_right = _projector_at(wall, +1.0, spec, name="P2")
    baseline = analyze_coverage([fp_left, fp_right], wall, grid_s=40, grid_z=25)
    assert baseline.overlap_cells > 0, "the setup must actually overlap"

    report = analyze_coverage(
        [fp_left, fp_right],
        wall,
        grid_s=40,
        grid_z=25,
        occlusion_caster=_pillar_caster(y_center=-0.45),
    )

    assert report.projector_occlusions["P1"].occluded_cells > 0
    assert report.projector_occlusions["P2"].occluded_cells == 0
    assert report.overlap_cells < baseline.overlap_cells
    # P1-only cells in the block band are fully shadowed and reported loudly.
    assert report.shadowed_cells
    assert all(
        -0.7 < (cell.s_start + cell.s_end) / 2 - wall.arc_length / 2 < -0.3
        for cell in report.shadowed_cells
    )
    assert any("occluded by an obstacle" in w for w in report.warnings)


def test_occlusion_cells_are_wall_coordinate_quads(wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(wall, 0.0, spec)
    report = analyze_coverage([fp], wall, grid_s=40, grid_z=25, occlusion_caster=_pillar_caster())
    cell = report.occluded_cells[0]
    assert 0.0 <= cell.s_start < cell.s_end <= wall.arc_length
    assert 0.0 <= cell.z_start < cell.z_end <= wall.height


# -- backward compatibility ---------------------------------------------------


def test_no_caster_matches_the_unoccluded_analysis_exactly(wall):
    spec = ProjectorSpec(throw_ratio=1.5)
    fp = _projector_at(wall, 0.0, spec)
    baseline = analyze_coverage([fp], wall, grid_s=40, grid_z=25)
    explicit = analyze_coverage([fp], wall, grid_s=40, grid_z=25, occlusion_caster=None)

    assert explicit.covered_fraction == baseline.covered_fraction
    assert explicit.gaps == baseline.gaps
    assert explicit.overlap_cells == baseline.overlap_cells
    assert explicit.warnings == baseline.warnings
    assert explicit.brightness == baseline.brightness
    assert explicit.projector_occlusions == {}
    assert explicit.occluded_cells == []
    assert explicit.shadowed_cells == []
