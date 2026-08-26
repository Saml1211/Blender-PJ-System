"""Arbitrary imported meshes as projection targets (ADR 0004).

An imported mesh has no analytic ``(s, z)`` formula, so :class:`MeshSurface`
gives it one: a *frontal heightfield*. The mesh is framed by a horizontal
facing direction (detected from area-weighted triangle normals, or supplied),
``s`` runs across the bounding width and ``z`` up the bounding height, and a
lattice of rays parallel to the facing axis records which surface depth each
``(s, z)`` column hits first.

Meshes that are not mostly-frontal — domes, columns, folded geometry — fail
the depth-smoothness validation loudly with a :class:`ProjectionError` naming
the region, rather than being silently mangled (ADR 0002).

Ray casting goes through a small protocol (:class:`MeshRayCast`). The default
implementation is pure Python (Möller–Trumbore), keeping this module importable
without bpy; the Blender layer may inject ``mathutils.bvhtree.BVHTree.ray_cast``
for heavy meshes at rebuild time. Nothing in ``footprint.py`` or
``coverage.py`` changes — they consume only the :class:`Surface` ABC.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, fields

from .errors import ProjectionError, require_finite
from .surfaces import Surface, SurfaceHit
from .vectors import (
    Vec3,
    add,
    cross,
    distance,
    dot,
    length,
    normalize,
    scale,
    sub,
)

#: Local slope above which adjacent scan depths count as a fold/overhang.
#: Two neighbouring cells whose depth differs by more than
#: ``_SLOPE_LIMIT * max(cell_size)`` cannot belong to one frontal face.
_SLOPE_LIMIT = 2.0

#: Absolute floor for the smoothness check so tiny cells stay sane, in metres.
_MIN_DEPTH_STEP = 1e-3

#: Padding added around the mesh when choosing scan-ray start offsets, in m.
_SCAN_MARGIN = 1.0


@dataclass(frozen=True)
class MeshHit:
    """A raw caster hit in world space, before ``(s, z)`` mapping."""

    point: Vec3
    distance: float
    face_normal: Vec3


#: Caster signature shared by the pure-Python fallback and injected BVH casters.
MeshRayCast = Callable[[Vec3, Vec3, float], "MeshHit | None"]


def _moller_trumbore(
    origin: Vec3,
    direction: Vec3,
    a: Vec3,
    b: Vec3,
    c: Vec3,
) -> tuple[float, Vec3] | None:
    """First-hit distance and geometric normal of a ray/triangle crossing.

    Returns ``None`` when the ray misses or runs parallel to the triangle.
    Both front- and back-face crossings are reported; filtering is the
    caller's business.
    """
    e1 = sub(b, a)
    e2 = sub(c, a)
    p = cross(direction, e2)
    det = dot(e1, p)
    if abs(det) < 1e-12:
        return None
    inv_det = 1.0 / det
    t = sub(origin, a)
    u = dot(t, p) * inv_det
    if not -1e-9 <= u <= 1.0 + 1e-9:
        return None
    q = cross(t, e1)
    v = dot(direction, q) * inv_det
    if v < -1e-9 or u + v > 1.0 + 1e-9:
        return None
    dist = dot(e2, q) * inv_det
    if dist < 1e-9:
        return None
    normal = normalize(cross(e1, e2))
    return dist, normal


class _PurePythonCaster:
    """Bpy-free reference caster: Möller–Trumbore over every triangle.

    Deterministic (first hit by distance, ties broken by triangle index) and
    adequate for test-sized meshes and modest imports; heavy meshes should use
    an injected BVH caster instead.
    """

    def __init__(self, vertices: Sequence[Vec3], triangles: Sequence[tuple[int, int, int]]) -> None:
        self._tris = [(vertices[a], vertices[b], vertices[c]) for a, b, c in triangles]

    def __call__(self, origin: Vec3, direction: Vec3, max_distance: float = 1e6) -> MeshHit | None:
        best: tuple[float, int, Vec3] | None = None
        for index, (a, b, c) in enumerate(self._tris):
            result = _moller_trumbore(origin, direction, a, b, c)
            if result is None:
                continue
            dist, normal = result
            if dist > max_distance:
                continue
            if best is None or dist < best[0]:
                best = (dist, index, normal)
        if best is None:
            return None
        dist, _, normal = best
        return MeshHit(
            point=add(origin, scale(direction, dist)),
            distance=dist,
            face_normal=normal,
        )


@dataclass(frozen=True)
class MeshSurface(Surface):
    """A scanned arbitrary mesh presented through the ``Surface`` contract.

    Construct via :meth:`from_triangles`. ``base_center`` anchors the frame's
    bottom-centre on the frontal reference plane; actual surface points carry
    the interpolated scan depth toward the projector side.
    """

    base_center: Vec3 = (0.0, 0.0, 0.0)
    facing: Vec3 = (-1.0, 0.0, 0.0)
    name: str = "Imported Mesh"
    #: Declared so clones carry it; derived from ``z_range`` in post-init.
    height: float = field(default=0.0)

    #: Frame origin: the world point mapped to ``(s_min, z_min, depth 0)``.
    origin: Vec3 = field(default=(0.0, 0.0, 0.0))
    s_range: tuple[float, float] = field(default=(0.0, 4.0))
    z_range: tuple[float, float] = field(default=(0.0, 2.5))

    #: Scan lattice: depth along ``facing`` and oriented normal per node.
    depth_grid: list[list[float | None]] = field(default_factory=list)
    normal_grid: list[list[Vec3]] = field(default_factory=list)

    triangles: tuple[tuple[int, int, int], ...] = ()
    caster: MeshRayCast | None = None

    def __post_init__(self) -> None:
        # ``Surface`` declares ``height`` as a plain attribute; derive it from
        # the frame's z-range so it can never disagree with it.
        object.__setattr__(self, "height", self.z_range[1] - self.z_range[0])
        for axis, value in zip("xyz", self.base_center, strict=True):
            require_finite(f"mesh base {axis}", value)
        length_sq = sum(component * component for component in self.facing)
        if length_sq < 1e-18:
            raise ProjectionError("mesh facing direction must not be zero")
        for axis, value in zip("xyz", self.facing, strict=True):
            require_finite(f"mesh facing {axis}", value)
        if abs(self.facing[2]) > 1e-6:
            raise ProjectionError(
                "mesh frontal axis must be horizontal; " "floor/ceiling projection is not supported"
            )
        object.__setattr__(self, "facing", normalize(self.facing))

    # -- factory --------------------------------------------------------------

    @classmethod
    def from_triangles(
        cls,
        vertices: Sequence[Vec3],
        triangles: Sequence[tuple[int, int, int]],
        *,
        frontal_axis: Vec3 | None = None,
        scan_s: int = 48,
        scan_z: int = 24,
        caster: MeshRayCast | None = None,
        name: str = "Imported Mesh",
    ) -> MeshSurface:
        """Frame, scan, validate, and build a surface from raw mesh data.

        Raises :class:`ProjectionError` for degenerate geometry, a
        non-horizontal explicit frontal axis, no detectable frontal direction,
        or a fold/overhang that breaks single-valuedness.
        """
        if scan_s < 1 or scan_z < 1:
            raise ProjectionError("scan lattice dimensions must be at least 1")
        if len(triangles) == 0:
            raise ProjectionError("mesh must contain at least one triangle")
        for index, vertex in enumerate(vertices):
            for axis, value in zip("xyz", vertex, strict=True):
                require_finite(f"mesh vertex {index} {axis}", value)

        facing = cls._resolve_frontal_axis(vertices, triangles, frontal_axis)
        right: Vec3 = (facing[1], -facing[0], 0.0)

        s_values = [dot(v, right) for v in vertices]
        s_min, s_max = min(s_values), max(s_values)
        z_values = [v[2] for v in vertices]
        z_min, z_max = min(z_values), max(z_values)
        if s_max - s_min <= 1e-9 or z_max - z_min <= 1e-9:
            raise ProjectionError("mesh has no extent across the wall; degenerate geometry")

        origin: Vec3 = (
            dot((s_min, 0.0, 0.0), right) + 0.0,
            0.0,
            z_min,
        )
        # The frame origin needs the full 3D position: its right-component
        # equals s_min projected back onto world X/Y, its Z is z_min, and its
        # depth-component defines the frontal reference plane. Reconstruct it
        # from any vertex-independent anchor: take centroid depth as plane.
        centroid_x = sum(v[0] for v in vertices) / len(vertices)
        centroid_y = sum(v[1] for v in vertices) / len(vertices)
        centroid_z = sum(v[2] for v in vertices) / len(vertices)
        centroid: Vec3 = (centroid_x, centroid_y, centroid_z)
        depth_ref = dot(centroid, facing)
        origin = (
            right[0] * s_min + facing[0] * depth_ref,
            right[1] * s_min + facing[1] * depth_ref,
            z_min,
        )

        tri_list_list: list[tuple[int, int, int]] = []
        for tri in triangles:
            try:
                a, b, c = tri
            except (TypeError, ValueError) as exc:
                raise ProjectionError(
                    f"mesh triangle data is malformed (need index triples): {exc}"
                ) from exc
            tri_list_list.append((a, b, c))
        tri_list = tuple(tri_list_list)
        try:
            float_vertices = [(float(v[0]), float(v[1]), float(v[2])) for v in vertices]
        except (TypeError, ValueError, IndexError) as exc:
            raise ProjectionError(f"mesh vertex data is not numeric: {exc}") from exc
        resolved_caster = (
            caster if caster is not None else _PurePythonCaster(float_vertices, tri_list)
        )

        depth_grid, normal_grid = cls._scan(
            origin=origin,
            facing=facing,
            right=right,
            s_min=s_min,
            s_max=s_max,
            z_min=z_min,
            z_max=z_max,
            scan_s=scan_s,
            scan_z=scan_z,
            vertices=float_vertices,
            triangles=tri_list,
            caster=resolved_caster,
        )
        cls._validate_smoothness(depth_grid, s_max - s_min, z_max - z_min)

        base_center = cls.point_on_plane(
            origin=origin,
            right=right,
            s=(s_max - s_min) * 0.5,
            z=0.0,
        )
        return cls(
            base_center=base_center,
            facing=facing,
            name=name,
            origin=origin,
            s_range=(s_min, s_max),
            z_range=(z_min, z_max),
            depth_grid=depth_grid,
            normal_grid=normal_grid,
            triangles=tri_list,
            caster=resolved_caster,
        )

    @staticmethod
    def point_on_plane(*, origin: Vec3, right: Vec3, s: float, z: float) -> Vec3:
        """The frame-plane point at ``(s, z)`` (zero depth)."""
        return (origin[0] + right[0] * s, origin[1] + right[1] * s, z)

    @classmethod
    def _resolve_frontal_axis(
        cls,
        vertices: Sequence[Vec3],
        triangles: Sequence[tuple[int, int, int]],
        frontal_axis: Vec3 | None,
    ) -> Vec3:
        if frontal_axis is not None:
            candidate = normalize(frontal_axis)
            if abs(candidate[2]) > 1e-6:
                raise ProjectionError(
                    "explicit frontal axis must be horizontal; got a vertical "
                    "component — floor/ceiling projection is not supported"
                )
            return (candidate[0], candidate[1], 0.0)

        weighted: Vec3 = (0.0, 0.0, 0.0)
        for ia, ib, ic in triangles:
            a, b, c = vertices[ia], vertices[ib], vertices[ic]
            n = cross(sub(b, a), sub(c, a))
            area = length(n) * 0.5
            if area < 1e-15:
                continue
            unit = scale(n, 1.0 / (length(n) or 1e-30))
            weighted = add(weighted, scale(unit, area))
        horizontal = (weighted[0], weighted[1], 0.0)
        if length(horizontal) < 1e-9:
            raise ProjectionError(
                "cannot determine a horizontal frontal axis from this mesh; "
                "supply frontal_axis explicitly"
            )
        return normalize(horizontal)

    @classmethod
    def _scan(
        cls,
        *,
        origin: Vec3,
        facing: Vec3,
        right: Vec3,
        s_min: float,
        s_max: float,
        z_min: float,
        z_max: float,
        scan_s: int,
        scan_z: int,
        vertices: Sequence[Vec3],
        triangles: Sequence[tuple[int, int, int]],
        caster: MeshRayCast,
    ) -> tuple[list[list[float | None]], list[list[Vec3]]]:
        ds = (s_max - s_min) / scan_s
        dz = (z_max - z_min) / scan_z

        depths: list[float] = [dot(v, facing) - dot(origin, facing) for v in vertices]
        d_min, d_max = min(depths), max(depths)
        margin = d_max - min(d_min, 0.0) + _SCAN_MARGIN

        depth_grid: list[list[float | None]] = []
        normal_grid: list[list[Vec3]] = []
        for iz in range(scan_z):
            row_depth: list[float | None] = []
            row_normal: list[Vec3] = []
            z = z_min + (iz + 0.5) * dz
            for i_s in range(scan_s):
                # Contract-relative offset: ``origin`` already sits at the
                # s_min edge, so adding raw s here would push half the lines
                # off the mesh.
                s_offset = (i_s + 0.5) * ds
                plane_point = cls.point_on_plane(origin=origin, right=right, s=s_offset, z=z)
                # Start on the PROJECTOR side (the side ``facing`` points
                # toward) and travel INTO the surface, so depth-varying
                # meshes record their near face, not their far shell.
                ray_origin = add(plane_point, scale(facing, margin))
                hit = caster(ray_origin, scale(facing, -1.0), margin + d_max + _SCAN_MARGIN)
                if hit is None or dot(hit.face_normal, facing) <= 0.0:
                    row_depth.append(None)
                    row_normal.append((facing[0], facing[1], facing[2]))
                    continue
                row_depth.append(dot(sub(hit.point, origin), facing))
                normal = hit.face_normal
                if dot(normal, facing) < 0.0:
                    normal = scale(normal, -1.0)
                row_normal.append(normal)
            depth_grid.append(row_depth)
            normal_grid.append(row_normal)
        return depth_grid, normal_grid

    @staticmethod
    def _validate_smoothness(
        depth_grid: list[list[float | None]],
        span_s: float,
        span_z: float,
    ) -> None:
        """Reject meshes where neighbouring scan depths jump like a fold."""
        rows = len(depth_grid)
        cols = len(depth_grid[0]) if rows else 0
        cell = max(span_s / max(cols, 1), span_z / max(rows, 1))
        limit = max(_SLOPE_LIMIT * cell, _MIN_DEPTH_STEP)
        for iz in range(rows):
            for i_s in range(cols):
                here = depth_grid[iz][i_s]
                if here is None:
                    continue
                if i_s + 1 < cols:
                    other = depth_grid[iz][i_s + 1]
                    if other is not None and abs(here - other) > limit:
                        raise ProjectionError(
                            "mesh folds back on itself near "
                            f"s≈{(i_s + 0.5) * span_s / cols:.2f} m, "
                            f"z≈{(iz + 0.5) * span_z / rows:.2f} m — "
                            "not usable as a frontal projection target"
                        )
                if iz + 1 < rows:
                    other = depth_grid[iz + 1][i_s]
                    if other is not None and abs(here - other) > limit:
                        raise ProjectionError(
                            "mesh folds back on itself near "
                            f"s≈{(i_s + 0.5) * span_s / cols:.2f} m, "
                            f"z≈{(iz + 1.5) * span_z / rows:.2f} m — "
                            "not usable as a frontal projection target"
                        )

    # -- Surface contract -----------------------------------------------------

    @property
    def arc_length(self) -> float:
        return self.s_range[1] - self.s_range[0]

    def _clone(self) -> MeshSurface:
        """An unfrozen copy sharing every field; mutate via setattr after."""
        clone = object.__new__(MeshSurface)
        for spec in fields(self):
            object.__setattr__(clone, spec.name, getattr(self, spec.name))
        return clone

    def _plane_point(self, s: float, z: float) -> Vec3:
        return self.point_on_plane(
            origin=self.origin,
            right=(self.facing[1], -self.facing[0], 0.0),
            s=s,
            z=self.z_range[0] + z,
        )

    def _grid_cell(self, s: float, z: float) -> tuple[int, int, float, float]:
        """Lattice indices and bilinear fractions for ``(s, z)``."""
        cols = len(self.depth_grid[0]) if self.depth_grid else 1
        rows = len(self.depth_grid) if self.depth_grid else 1
        fx = (s / max(self.arc_length, 1e-9)) * cols - 0.5
        fz = (z / max(self.height, 1e-9)) * rows - 0.5
        i_s = min(max(math.floor(fx), 0), cols - 2) if cols >= 2 else 0
        iz = min(max(math.floor(fz), 0), rows - 2) if rows >= 2 else 0
        tx = min(max(fx - i_s, 0.0), 1.0)
        tz = min(max(fz - iz, 0.0), 1.0)
        return i_s, iz, tx, tz

    def _bilinear_depth(self, i_s: int, iz: int, tx: float, tz: float) -> float | None:
        corners = (
            self.depth_grid[iz][i_s],
            self.depth_grid[iz][i_s + 1],
            self.depth_grid[iz + 1][i_s],
            self.depth_grid[iz + 1][i_s + 1],
        )
        values = [
            (t, d) for t, d in zip((1 - tx, tx, 1 - tx, tx), corners, strict=True) if d is not None
        ]
        if not values:
            return None
        total = sum(weight for weight, _ in values)
        return sum(weight * d for weight, d in values) / total

    def _bilinear_normal(self, i_s: int, iz: int, tx: float, tz: float) -> Vec3:
        n00, n10, n01, n11 = (
            self.normal_grid[iz][i_s],
            self.normal_grid[iz][i_s + 1],
            self.normal_grid[iz + 1][i_s],
            self.normal_grid[iz + 1][i_s + 1],
        )
        blended = tuple(
            n00[k] * (1 - tx) * (1 - tz)
            + n10[k] * tx * (1 - tz)
            + n01[k] * (1 - tx) * tz
            + n11[k] * tx * tz
            for k in range(3)
        )
        if length(blended) < 1e-12:  # type: ignore[arg-type]
            return self.facing
        return normalize(blended)  # type: ignore[arg-type]

    def point_at(self, s: float, z: float) -> Vec3:
        """World point at ``(s, z)``: plane position plus interpolated depth."""
        i_s, iz, tx, tz = self._grid_cell(s, z)
        depth = self._bilinear_depth(i_s, iz, tx, tz)
        offset = depth if depth is not None else 0.0
        return add(self._plane_point(s, z), scale(self.facing, offset))

    def normal_at_s(self, s: float) -> Vec3:
        """Depth-averaged outward normal of the column at ``s``."""
        cols = len(self.depth_grid[0]) if self.depth_grid else 0
        rows = len(self.depth_grid) if self.depth_grid else 0
        if cols == 0 or rows == 0:
            return self.facing
        column = max(0, min(cols - 1, math.floor(s / max(self.arc_length, 1e-9) * cols)))
        acc: Vec3 = (0.0, 0.0, 0.0)
        used = 0
        for iz in range(rows):
            n = self.normal_grid[iz][column]
            acc = add(acc, n)
            used += 1
        if used == 0 or length(acc) < 1e-12:
            return self.facing
        return normalize(acc)

    def intersect_ray(
        self,
        origin: Vec3,
        direction: Vec3,
        max_distance: float = 1e6,
    ) -> SurfaceHit | None:
        """First forward intersection with the usable (front-facing) face."""
        if self.caster is None:
            return None
        d = normalize(direction)
        # Parity with PlanarWall: only rays travelling INTO the usable face
        # (against ``facing``, which points at the projector side) count.
        if dot(d, self.facing) >= -1e-12:
            return None
        hit = self.caster(origin, d, max_distance)
        if hit is None:
            return None
        if dot(hit.face_normal, self.facing) <= 0.0:
            # Struck the far side or an inward-facing flap: not usable.
            return None
        right: Vec3 = (self.facing[1], -self.facing[0], 0.0)
        # The frame origin sits at the left edge, so the projection onto
        # ``right`` relative to the origin IS the contract ``s``.
        local_s = dot(sub(hit.point, self.origin), right)
        local_z = hit.point[2] - self.z_range[0]
        tol = 1e-9
        if not (-tol <= local_s <= self.arc_length + tol):
            return None
        if not (-tol <= local_z <= self.height + tol):
            return None
        cos_i = -dot(d, hit.face_normal)
        incidence = math.acos(max(-1.0, min(1.0, cos_i)))
        return SurfaceHit(
            point=hit.point,
            distance=hit.distance,
            s=min(max(local_s, 0.0), self.arc_length),
            z=min(max(local_z, 0.0), self.height),
            normal=hit.face_normal,
            incidence=incidence,
        )

    def project_point(self, point: Vec3) -> SurfaceHit | None:
        """Nearest scanned surface node to ``point``, or ``None`` outside."""
        best: tuple[float, int, int] | None = None
        for iz, row in enumerate(self.depth_grid):
            for i_s, depth in enumerate(row):
                if depth is None:
                    continue
                cols = len(row)
                rows_n = len(self.depth_grid)
                s_node = (i_s + 0.5) * self.arc_length / cols
                z_node = (iz + 0.5) * self.height / rows_n
                node_point = add(self._plane_point(s_node, z_node), scale(self.facing, depth))
                d = distance(point, node_point)
                if best is None or d < best[0]:
                    best = (d, i_s, iz)
        if best is None:
            return None
        d, i_s, iz = best
        cols = len(self.depth_grid[0])
        rows_n = len(self.depth_grid)
        s_query = dot(sub(point, self.origin), (self.facing[1], -self.facing[0], 0.0))
        z_query = point[2] - self.z_range[0]
        if not self.contains(s_query, z_query):
            return None
        return SurfaceHit(
            point=add(
                self._plane_point(s_query, z_query),
                scale(self.facing, self.depth_grid[iz][i_s] or 0.0),
            ),
            distance=d,
            s=s_query,
            z=z_query,
            normal=self.normal_grid[iz][i_s],
            incidence=0.0,
        )

    def expanded(self, pad_s: float, pad_z: float) -> MeshSurface:
        """An oversized copy padded by ``pad_s``/``pad_z`` metres each side."""
        clone = self._clone()
        s_min = self.s_range[0] - pad_s
        z_min_world = self.z_range[0] - pad_z
        right: Vec3 = (self.facing[1], -self.facing[0], 0.0)
        shift_origin = add(self.origin, sub(scale(right, s_min), scale(right, self.s_range[0])))
        object.__setattr__(
            clone,
            "origin",
            (shift_origin[0], shift_origin[1], z_min_world),
        )
        object.__setattr__(clone, "s_range", (s_min, self.s_range[1] + pad_s))
        object.__setattr__(clone, "z_range", (z_min_world, self.z_range[1] + pad_z))
        object.__setattr__(clone, "height", clone.z_range[1] - clone.z_range[0])
        object.__setattr__(
            clone,
            "base_center",
            self.point_on_plane(
                origin=clone.origin,
                right=right,
                s=clone.arc_length * 0.5,
                z=0.0,
            ),
        )
        return clone

    def measurement_wall(self) -> MeshSurface:
        """Deliberately oversized copy for the array solver (ADR 0003 hook)."""
        widened = self.expanded(max(2.0, self.arc_length * 0.5), self.height * 2.0)
        return widened.renamed(widened.name + "(solve)")

    def renamed(self, name: str) -> MeshSurface:
        clone = self._clone()
        object.__setattr__(clone, "name", name)
        return clone
