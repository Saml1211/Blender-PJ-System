"""Line-of-sight occlusion between projectors and the wall.

A projector's coverage claim is only honest if nothing stands in the light
path. This module answers exactly one question — *is the straight ray from
the projector aperture to a wall point blocked before it gets there?* — and
leaves everything else (rasterising, counting, reporting) to
:mod:`.coverage`.

Casting goes through the :class:`OcclusionCaster` protocol, the same
dependency-inversion pattern as ADR 0004's ``MeshRayCast``: the pure-Python
:class:`TriMeshOcclusionCaster` here is the deterministic reference used by
the test suite and small scenes, while the Blender layer may inject a
BVH-backed caster over user-selected occluder objects. Nothing in ``core``
imports bpy.

Distances are in metres and directions must be unit vectors. A caster that
cannot answer (no occluders, degenerate geometry) simply reports "not
blocked"; occlusion is an overlay on coverage, never a silent edit of it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .vectors import Vec3, cross, dot, sub

#: Hits closer than this to the ray origin belong to the surface the ray
#: starts on (the projector body, or a caster built from the target wall's
#: own mesh) and are ignored. :func:`.coverage.analyze_coverage` also trims
#: this amount off ``max_distance`` so a wall quad at the exact aim distance
#: never occludes its own sample point.
RAY_TOLERANCE = 1e-3

#: Parallel threshold for ray/triangle intersection (same value as the
#: Möller–Trumbore reference in :mod:`.mesh_surface`).
_PARALLEL_DET = 1e-12


class OcclusionCaster(Protocol):
    """Answers whether a ray is blocked before ``max_distance``.

    ``origin`` is the ray start (the projector aperture), ``direction`` a
    unit vector toward the wall point, and ``max_distance`` the remaining
    distance in metres. Returns ``True`` only when something solid stands in
    the path within that distance; ``False`` means line of sight is clear.
    """

    def __call__(self, origin: Vec3, direction: Vec3, max_distance: float) -> bool: ...


def _ray_triangle_distance(
    origin: Vec3,
    direction: Vec3,
    a: Vec3,
    b: Vec3,
    c: Vec3,
) -> float | None:
    """Distance where the ray crosses triangle ``(a, b, c)``, or ``None``.

    Möller–Trumbore, both face orientations accepted — an occluder is solid
    from either side. Returns the hit distance in units of ``|direction|``
    (metres for a unit direction).
    """
    e1 = sub(b, a)
    e2 = sub(c, a)
    p = cross(direction, e2)
    det = dot(e1, p)
    if abs(det) < _PARALLEL_DET:
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
    return dot(e2, q) * inv_det


class TriMeshOcclusionCaster:
    """Pure-Python occlusion caster: Möller–Trumbore over every triangle.

    Deterministic and dependency-free, sized for test scenes and modest
    occluder meshes; heavy scenes should inject a BVH-backed caster with the
    same call signature. Reports blocked when any triangle is crossed at a
    distance in ``[RAY_TOLERANCE, max_distance]``.
    """

    def __init__(
        self,
        vertices: Sequence[Vec3],
        triangles: Sequence[tuple[int, int, int]],
    ) -> None:
        self._tris = [(vertices[a], vertices[b], vertices[c]) for a, b, c in triangles]

    def __call__(self, origin: Vec3, direction: Vec3, max_distance: float = 1e6) -> bool:
        if max_distance <= RAY_TOLERANCE:
            return False
        for a, b, c in self._tris:
            dist = _ray_triangle_distance(origin, direction, a, b, c)
            if dist is None:
                continue
            if RAY_TOLERANCE <= dist <= max_distance:
                return True
        return False


def box_triangles(
    min_pt: Vec3,
    max_pt: Vec3,
) -> tuple[list[Vec3], list[tuple[int, int, int]]]:
    """The 12 triangles of an axis-aligned box, for synthetic occluders."""
    x0, y0, z0 = min_pt
    x1, y1, z1 = max_pt
    vertices = [
        (x0, y0, z0),
        (x1, y0, z0),
        (x1, y1, z0),
        (x0, y1, z0),
        (x0, y0, z1),
        (x1, y0, z1),
        (x1, y1, z1),
        (x0, y1, z1),
    ]
    triangles = [
        (0, 2, 1),
        (0, 3, 2),  # bottom
        (4, 5, 6),
        (4, 6, 7),  # top
        (0, 1, 5),
        (0, 5, 4),  # front (-y)
        (3, 7, 6),
        (3, 6, 2),  # back (+y)
        (0, 4, 7),
        (0, 7, 3),  # left (-x)
        (1, 2, 6),
        (1, 6, 5),  # right (+x)
    ]
    return vertices, triangles


def quad_triangles(
    p0: Vec3,
    p1: Vec3,
    p2: Vec3,
    p3: Vec3,
) -> tuple[list[Vec3], list[tuple[int, int, int]]]:
    """Two triangles over a planar quad, for synthetic panels and walls."""
    return [p0, p1, p2, p3], [(0, 1, 2), (0, 2, 3)]
