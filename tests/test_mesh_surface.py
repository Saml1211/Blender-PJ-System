"""Tests for core.mesh_surface — arbitrary imported meshes as targets.

Seams under test (ADR 0004):

1. ``MeshSurface.from_triangles`` construction and validation
2. the ``Surface`` ``(s, z)`` contract on scanned meshes
3. ``intersect_ray`` parity between the pure-Python caster and injected casters
4. hook semantics (``chord``, ``expanded``, ``measurement_wall``, ...)
5. contract parity with :class:`PlanarWall` for a tessellated flat wall
"""

from __future__ import annotations

import pytest

from blender_projection_system.core.errors import ProjectionError
from blender_projection_system.core.footprint import compute_footprint
from blender_projection_system.core.mesh_surface import MeshRayCast, MeshSurface
from blender_projection_system.core.pose import Pose
from blender_projection_system.core.surfaces import PlanarWall
from blender_projection_system.core.throw import ProjectorSpec


def _flat_quad_mesh(
    width: float = 4.0,
    height: float = 2.5,
    segments: int = 2,
    facing=(-1.0, 0.0, 0.0),
    base_center=(8.0, 0.0, 0.0),
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    """Vertices/triangles of a flat wall matching ``PlanarWall`` conventions.

    Mirrors what ``projection.create_flat_wall`` generates: a grid in the
    wall's own frame, wound so face normals point at the projector side
    (toward ``facing``).
    """
    fx, fy, _ = facing
    right = (fy, -fx, 0.0)
    vertices: list[tuple[float, float, float]] = []
    for iz in range(segments + 1):
        for i_s in range(segments + 1):
            s = width * i_s / segments
            z = height * iz / segments
            # s=0 is the LEFT edge seen from the projector side, so the wall
            # runs from +right*width/2 down to -right*width/2.
            offset = s - width * 0.5
            vertices.append(
                (
                    base_center[0] + right[0] * offset,
                    base_center[1] + right[1] * offset,
                    base_center[2] + z,
                )
            )
    triangles: list[tuple[int, int, int]] = []
    stride = segments + 1
    for iz in range(segments):
        for i_s in range(segments):
            a = iz * stride + i_s
            b = a + 1
            c = a + stride
            d = c + 1
            # Wound counter-clockwise seen from the projector side, so face
            # normals point along ``facing`` — same convention as the walls
            # the add-on generates itself.
            triangles.append((a, d, b))
            triangles.append((a, c, d))
    return vertices, triangles


class TestConstruction:
    def test_a_tessellated_flat_wall_matches_planar_bounds(self) -> None:
        vertices, triangles = _flat_quad_mesh()
        mesh = MeshSurface.from_triangles(vertices, triangles, name="Imported Wall")

        planar = PlanarWall(base_center=(8.0, 0.0, 0.0), name="planar")
        assert mesh.arc_length == pytest.approx(planar.arc_length)
        assert mesh.height == pytest.approx(planar.height)

    def test_the_dominant_horizontal_normal_becomes_the_facing(self) -> None:
        vertices, triangles = _flat_quad_mesh(facing=(0.0, -1.0, 0.0))
        mesh = MeshSurface.from_triangles(vertices, triangles)
        assert mesh.facing == pytest.approx((0.0, -1.0, 0.0))

    def test_an_explicit_frontal_axis_overrides_the_detected_one(self) -> None:
        vertices, triangles = _flat_quad_mesh()
        mesh = MeshSurface.from_triangles(vertices, triangles, frontal_axis=(-1.0, 0.0, 0.0))
        assert mesh.facing == pytest.approx((-1.0, 0.0, 0.0))

    def test_degenerate_geometry_is_rejected(self) -> None:
        vertices = [(0.0, 0.0, 0.0)] * 4
        triangles = [(0, 1, 2)]
        with pytest.raises(ProjectionError):
            MeshSurface.from_triangles(vertices, triangles)


class TestSurfaceContract:
    """The ``(s, z)`` contract on a known flat mesh."""

    @pytest.fixture()
    def flat_mesh(self) -> MeshSurface:
        vertices, triangles = _flat_quad_mesh()
        return MeshSurface.from_triangles(vertices, triangles, scan_s=16, scan_z=10, name="flat")

    def test_point_at_lands_on_the_wall_face(self, flat_mesh: MeshSurface) -> None:
        # Depth reference is the centroid plane; a flat wall has zero depth.
        assert flat_mesh.point_at(2.0, 1.25) == pytest.approx((8.0, 0.0, 1.25))
        assert flat_mesh.point_at(0.0, 0.0) == pytest.approx((8.0, -2.0, 0.0))
        assert flat_mesh.point_at(4.0, 2.5) == pytest.approx((8.0, 2.0, 2.5))

    def test_normal_faces_the_projector_side(self, flat_mesh: MeshSurface) -> None:
        assert flat_mesh.normal_at_s(0.0) == pytest.approx((-1.0, 0.0, 0.0))
        assert flat_mesh.normal_at_s(4.0) == pytest.approx((-1.0, 0.0, 0.0))

    def test_a_square_on_ray_reports_the_hit(self, flat_mesh: MeshSurface) -> None:
        hit = flat_mesh.intersect_ray((0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
        assert hit is not None
        assert hit.point == pytest.approx((8.0, 0.0, 1.0))
        assert hit.distance == pytest.approx(8.0)
        assert hit.s == pytest.approx(2.0)
        assert hit.z == pytest.approx(1.0)
        assert hit.incidence == pytest.approx(0.0)

    def test_a_ray_beyond_the_face_edges_misses(self, flat_mesh: MeshSurface) -> None:
        assert flat_mesh.intersect_ray((0.0, -5.0, 1.0), (1.0, 0.0, 0.0)) is None
        assert flat_mesh.intersect_ray((0.0, 0.0, 9.0), (1.0, 0.0, 0.0)) is None

    def test_a_ray_from_behind_the_wall_is_rejected(self, flat_mesh: MeshSurface) -> None:
        # Parity with PlanarWall: a ray travelling along -facing comes from
        # the far side and never counts as a usable projection hit.
        assert flat_mesh.intersect_ray((9.0, 0.0, 1.0), (-1.0, 0.0, 0.0)) is None


class TestInjectedCasterParity:
    """intersect_ray behaves identically under an injected caster."""

    @pytest.fixture()
    @staticmethod
    def fake_caster() -> type:
        class FakeBVH:
            """Stands in for mathutils.bvhtree.BVHTree.ray_cast semantics."""

            def __init__(self, inner: MeshRayCast) -> None:
                self.inner = inner
                self.calls = 0

            def __call__(self, origin, direction, max_distance):
                self.calls += 1
                return self.inner(origin, direction, max_distance)

        return FakeBVH

    def test_injected_fake_agrees_with_pure_python_default(self, fake_caster: type) -> None:
        vertices, triangles = _flat_quad_mesh()
        default = MeshSurface.from_triangles(vertices, triangles, scan_s=16, scan_z=10)
        injected = MeshSurface.from_triangles(
            vertices,
            triangles,
            scan_s=16,
            scan_z=10,
            caster=fake_caster(default.caster),
        )
        for origin, direction in [
            ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
            ((0.0, -5.0, 1.0), (1.0, 0.0, 0.0)),
            ((9.0, 0.0, 1.0), (-1.0, 0.0, 0.0)),
        ]:
            assert injected.intersect_ray(origin, direction) == (
                default.intersect_ray(origin, direction)
            )


def _two_quad_wall(x_left: float, x_right: float) -> tuple[list, list]:
    """Two vertical quads meeting at y=0: left half at ``x_left``,
    right half at ``x_right``, both wound toward the projector side (-X)."""
    y_split = 0.0
    z0, z1 = 0.0, 2.5
    y0, y1 = -2.0, 2.0
    v = [
        (x_left, y0, z0),  # 0 left-bottom-left
        (x_left, y0, z1),  # 1 left-top-left
        (x_left, y_split, z0),  # 2 left-bottom-right
        (x_left, y_split, z1),  # 3 left-top-right
        (x_right, y_split, z0),  # 4 right-bottom-left
        (x_right, y_split, z1),  # 5 right-top-left
        (x_right, y1, z0),  # 6 right-bottom-right
        (x_right, y1, z1),  # 7 right-top-right
    ]
    # CCW seen from -X, matching _flat_quad_mesh winding.
    tris = [
        (0, 1, 3),
        (0, 3, 2),  # left quad
        (4, 5, 7),
        (4, 7, 6),  # right quad
    ]
    return v, tris


class TestFrontalValidation:
    def test_a_fold_back_is_rejected_with_the_region_named(self) -> None:
        vertices, triangles = _two_quad_wall(x_left=8.0, x_right=9.0)
        with pytest.raises(ProjectionError, match="folds back"):
            MeshSurface.from_triangles(vertices, triangles, scan_s=16, scan_z=10)

    def test_a_shallow_recess_passes_and_scans_the_near_face(self) -> None:
        vertices, triangles = _two_quad_wall(x_left=8.0, x_right=8.2)
        mesh = MeshSurface.from_triangles(vertices, triangles, scan_s=16, scan_z=10)
        # The recess is 0.2 m deep; cells over it must report that depth.
        shallow_x = mesh.point_at(0.5, 1.25)[0]
        deep_x = mesh.point_at(3.5, 1.25)[0]
        assert shallow_x == pytest.approx(8.0, abs=1e-6)
        assert deep_x == pytest.approx(8.2, abs=1e-6)


class TestHooks:
    @pytest.fixture()
    def mesh(self) -> MeshSurface:
        vertices, triangles = _flat_quad_mesh()
        return MeshSurface.from_triangles(vertices, triangles, scan_s=16, scan_z=10)

    def test_flat_face_hooks_match_planar_semantics(self, mesh: MeshSurface) -> None:
        assert mesh.wraps_around is False
        assert mesh.curvature_radius is None
        assert mesh.chord(3.0) == 3.0
        assert mesh.normal_faces_projectors is True

    def test_expanded_pads_each_side_and_keeps_scan_data(self, mesh: MeshSurface) -> None:
        wide = mesh.expanded(1.0, 0.5)
        assert wide.arc_length == pytest.approx(mesh.arc_length + 2.0)
        assert wide.height == pytest.approx(mesh.height + 1.0)
        assert wide.depth_grid == mesh.depth_grid

    def test_measurement_wall_is_oversized_and_renamed(self, mesh: MeshSurface) -> None:
        solve = mesh.measurement_wall()
        assert solve.name.endswith("(solve)")
        assert solve.arc_length > mesh.arc_length
        assert solve.height > mesh.height


class TestPlanarParity:
    """A tessellated flat wall must behave exactly like PlanarWall."""

    def test_footprints_agree_within_tessellation_error(self) -> None:
        vertices, triangles = _flat_quad_mesh()
        mesh = MeshSurface.from_triangles(vertices, triangles, scan_s=16, scan_z=10)
        planar = PlanarWall(base_center=(8.0, 0.0, 0.0), name="planar")

        pose = Pose(
            origin=(2.0, 0.0, 1.25),
            right=(0.0, -1.0, 0.0),
            up=(0.0, 0.0, 1.0),
            forward=(1.0, 0.0, 0.0),
        )
        spec = ProjectorSpec(throw_ratio=1.5)

        from_mesh = compute_footprint(pose, spec, mesh, name="mesh")
        from_planar = compute_footprint(pose, spec, planar, name="planar")

        assert from_mesh.hit_ratio == from_planar.hit_ratio
        assert from_mesh.s_min == pytest.approx(from_planar.s_min, abs=1e-6)
        assert from_mesh.s_max == pytest.approx(from_planar.s_max, abs=1e-6)
        assert from_mesh.z_min == pytest.approx(from_planar.z_min, abs=1e-6)
        assert from_mesh.z_max == pytest.approx(from_planar.z_max, abs=1e-6)
        assert from_mesh.min_distance == pytest.approx(from_planar.min_distance, abs=1e-6)
