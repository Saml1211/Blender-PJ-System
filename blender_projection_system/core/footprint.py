"""Sampled image footprints on a curved surface.

A footprint is produced by casting a grid of rays through the projector's
image plane and intersecting each with the target wall. Everything downstream
- coverage, gaps, overlap, brightness - is derived from these samples rather
than from an idealised rectangle, because a rectangular frustum landing on a
curved wall does not produce a rectangle.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from .errors import ProjectionError
from .photometry import BrightnessReport, illuminance_at, summarize_brightness
from .pose import Pose
from .surfaces import CylindricalWall, SurfaceHit
from .throw import ProjectorSpec, grid_boundary_indices, grid_uv, ray_direction_local
from .vectors import Vec3, dot, normalize, sub
from .vectors import distance as vec_distance

DEFAULT_SAMPLES = 9


@dataclass(frozen=True)
class FootprintSample:
    u: float
    v: float
    hit: SurfaceHit | None

    @property
    def on_surface(self) -> bool:
        return self.hit is not None


@dataclass
class Footprint:
    """Where one projector's image lands on the wall."""

    name: str
    samples: list[FootprintSample]
    grid: int
    spec: ProjectorSpec
    pose: Pose
    wall: CylindricalWall

    # Derived, filled by :func:`compute_footprint`.
    hit_ratio: float = 0.0
    s_min: float = 0.0
    s_max: float = 0.0
    z_min: float = 0.0
    z_max: float = 0.0
    min_distance: float = 0.0
    max_distance: float = 0.0
    center_distance: float = 0.0
    """Perpendicular optical depth to the image-centre hit, in metres."""
    max_incidence: float = 0.0
    boundary: list[tuple[float, float]] = field(default_factory=list)
    boundary_points: list[Vec3] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def fully_on_surface(self) -> bool:
        return self.hit_ratio >= 1.0 - 1e-9

    @property
    def arc_span(self) -> float:
        return max(0.0, self.s_max - self.s_min)

    @property
    def height_span(self) -> float:
        return max(0.0, self.z_max - self.z_min)

    def hits(self) -> list[SurfaceHit]:
        return [s.hit for s in self.samples if s.hit is not None]

    def illuminance_samples(self) -> list[float]:
        """Per-sample illuminance in lux on the wall."""
        return [
            illuminance_at(self.spec, h.distance, h.incidence) for h in self.hits()
        ]

    def brightness(self, screen_gain: float = 1.0) -> BrightnessReport:
        return summarize_brightness(self.illuminance_samples(), screen_gain)

    def image_uv_of(self, point: Vec3) -> tuple[float, float] | None:
        """Where a world point falls in this projector's image, or ``None``.

        This is the inverse of :func:`~.throw.image_point_local`: it projects a
        surface point back through the lens. Returns ``(u, v)`` in the same
        ``[-0.5, 0.5]`` convention as the forward pass, or ``None`` if the
        point lies behind the lens.
        """
        d = sub(point, self.pose.origin)
        lx = dot(d, self.pose.right)
        ly = dot(d, self.pose.up)
        lz = -dot(d, self.pose.forward)  # local -Z is forward
        if lz >= -1e-9:
            return None  # behind the lens, or exactly at it
        depth = -lz
        tr = self.spec.throw_ratio
        u = lx * tr / depth - self.spec.lens_shift_h
        v = ly * tr * self.spec.aspect / depth - self.spec.lens_shift_v
        return u, v

    def covers(self, point: Vec3, tol: float = 0.0) -> bool:
        """Whether this projector's image lands on a given world point.

        Used instead of a point-in-polygon test against :attr:`boundary`,
        because when part of the image spills off the wall the boundary walk
        skips the missed samples and closes across the gap, which silently
        understates coverage. Back-projection has no such failure mode.
        """
        uv = self.image_uv_of(point)
        if uv is None:
            return False
        u, v = uv
        limit = 0.5 + tol
        if not (-limit <= u <= limit and -limit <= v <= limit):
            return False

        to_point = sub(point, self.pose.origin)
        distance = vec_distance(point, self.pose.origin)
        if distance <= 1e-9:
            return False
        first_hit = self.wall.intersect_ray(
            self.pose.origin,
            normalize(to_point),
            max_distance=distance + max(1e-6, tol),
        )
        return first_hit is not None and vec_distance(first_hit.point, point) <= max(
            1e-5, tol
        )


def compute_footprint(
    pose: Pose,
    spec: ProjectorSpec,
    wall: CylindricalWall,
    samples: int = DEFAULT_SAMPLES,
    name: str = "Projector",
    max_distance: float = 1e6,
) -> Footprint:
    """Cast the projector's frustum onto ``wall`` and summarise the result."""
    if samples < 2:
        raise ProjectionError(f"need at least 2 samples per axis, got {samples}")

    uv = grid_uv(samples)
    sample_list: list[FootprintSample] = []
    for u, v in uv:
        world_dir = pose.local_to_world_dir(ray_direction_local(u, v, spec))
        hit = wall.intersect_ray(pose.origin, world_dir, max_distance=max_distance)
        sample_list.append(FootprintSample(u=u, v=v, hit=hit))

    fp = Footprint(
        name=name,
        samples=sample_list,
        grid=samples,
        spec=spec,
        pose=pose,
        wall=wall,
    )

    hits = fp.hits()
    fp.hit_ratio = len(hits) / len(sample_list)

    if not hits:
        fp.warnings.append(
            f"{name}: no part of the image lands on '{wall.name}' - "
            "check the aim direction, throw ratio and wall extents"
        )
        return fp

    arc_values = _minimal_arc_values([h.s for h in hits], wall)
    fp.s_min = min(arc_values)
    fp.s_max = max(arc_values)
    fp.z_min = min(h.z for h in hits)
    fp.z_max = max(h.z for h in hits)
    fp.min_distance = min(h.distance for h in hits)
    fp.max_distance = max(h.distance for h in hits)
    fp.max_incidence = max(h.incidence for h in hits)

    center_hit = _center_hit(fp)
    fp.center_distance = (
        dot(sub(center_hit.point, pose.origin), pose.forward)
        if center_hit
        else fp.min_distance
    )

    fp.boundary, fp.boundary_points = _boundary(fp)

    if fp.hit_ratio < 1.0:
        fp.warnings.append(
            f"{name}: {(1.0 - fp.hit_ratio) * 100:.0f}% of the image spills past "
            f"'{wall.name}' - it will land on adjacent surfaces"
        )
    if math.degrees(fp.max_incidence) > 45.0:
        fp.warnings.append(
            f"{name}: worst incidence angle {math.degrees(fp.max_incidence):.0f} deg "
            "means noticeable geometric stretch and brightness falloff at that edge"
        )
    if fp.max_distance > 0 and fp.min_distance / fp.max_distance < 0.75:
        fp.warnings.append(
            f"{name}: throw distance varies from {fp.min_distance:.2f} m to "
            f"{fp.max_distance:.2f} m across the image; depth of field and focus "
            "uniformity will be tested"
        )
    return fp


def _center_hit(fp: Footprint) -> SurfaceHit | None:
    """Sample nearest the image centre, used to find the image-plane depth."""
    best: FootprintSample | None = None
    best_r2 = float("inf")
    for s in fp.samples:
        if s.hit is None:
            continue
        r2 = s.u * s.u + s.v * s.v
        if r2 < best_r2:
            best, best_r2 = s, r2
    return best.hit if best else None


def _minimal_arc_values(values: Sequence[float], wall: CylindricalWall) -> list[float]:
    """Unwrap full-circle coordinates across the seam to their shortest span."""
    if len(values) < 2 or wall.sweep < 2.0 * math.pi - 1e-9:
        return list(values)
    circumference = wall.arc_length
    ordered = sorted(value % circumference for value in values)
    gaps = [
        (
            (ordered[(i + 1) % len(ordered)] - ordered[i]) % circumference,
            i,
        )
        for i in range(len(ordered))
    ]
    _, gap_index = max(gaps)
    start = ordered[(gap_index + 1) % len(ordered)]
    return [value if value >= start else value + circumference for value in ordered]


def _boundary(fp: Footprint) -> tuple[list[tuple[float, float]], list[Vec3]]:
    """Perimeter polygon of the footprint in wall ``(s, z)`` coords.

    Samples that missed the wall are skipped, so a partially-spilled image
    still yields a usable (if clipped) polygon.
    """
    poly: list[tuple[float, float]] = []
    pts: list[Vec3] = []
    for idx in grid_boundary_indices(fp.grid):
        hit = fp.samples[idx].hit
        if hit is None:
            continue
        s = hit.s
        if fp.wall.sweep >= 2.0 * math.pi - 1e-9 and fp.arc_span < fp.wall.arc_length:
            midpoint = 0.5 * (fp.s_min + fp.s_max)
            s += round((midpoint - s) / fp.wall.arc_length) * fp.wall.arc_length
        poly.append((s, hit.z))
        pts.append(hit.point)
    return poly, pts


def point_in_polygon(point: tuple[float, float], polygon: Sequence[tuple[float, float]]) -> bool:
    """Standard even-odd ray-crossing test in 2D."""
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            denom = yj - yi
            if abs(denom) > 1e-15:
                x_cross = xi + (y - yi) * (xj - xi) / denom
                if x_cross > x:
                    inside = not inside
        j = i
    return inside


def polygon_area(polygon: Sequence[tuple[float, float]]) -> float:
    """Absolute shoelace area of a simple polygon in wall coordinates (m^2)."""
    if len(polygon) < 3:
        return 0.0
    total = 0.0
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) * 0.5


def footprint_corners_world(fp: Footprint) -> list[Vec3]:
    """The four image corners on the wall, in :data:`throw.CORNER_UV` order.

    Corners that missed the wall are omitted, so callers must check the length.
    """
    n = fp.grid
    corner_indices = (0, n - 1, n * n - 1, n * (n - 1))
    out: list[Vec3] = []
    for idx in corner_indices:
        hit = fp.samples[idx].hit
        if hit is not None:
            out.append(hit.point)
    return out


def frustum_edge_lines(fp: Footprint) -> list[tuple[Vec3, Vec3]]:
    """Line segments from the lens to each landed image corner, for drawing."""
    return [(fp.pose.origin, c) for c in footprint_corners_world(fp)]


def throw_distance_to_wall(pose: Pose, spec: ProjectorSpec, wall: CylindricalWall) -> float | None:
    """Optical depth to the image-centre hit, or ``None`` if it misses.

    With lens shift the centre ray is not the optical axis. Throw ratio still
    uses the perpendicular depth to the image plane, not that ray's longer
    point-to-point travel distance.
    """
    axis = pose.local_to_world_dir(ray_direction_local(0.0, 0.0, spec))
    hit = wall.intersect_ray(pose.origin, axis)
    if hit is None:
        return None
    return dot(sub(hit.point, pose.origin), pose.forward)
