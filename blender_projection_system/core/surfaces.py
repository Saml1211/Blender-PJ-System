"""Curved projection surfaces and ray intersection.

The only surface implemented is a vertical-axis cylindrical wall segment,
which covers the common AV case of a curved projection wall. Surface points
carry a 2D ``(s, z)`` parameterisation:

* ``s`` is arc length measured from ``angle_start``, in metres
* ``z`` is height above the wall base, in metres

That parameterisation is what coverage and blend analysis operate in, because
arc length is what an installer actually measures along the wall.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import ProjectionError, require_finite, require_positive
from .vectors import Vec3, dot, normalize, scale

#: Radial tolerance when classifying a point as "on" the wall, in metres.
SURFACE_TOL = 1e-6


@dataclass(frozen=True)
class SurfaceHit:
    """A ray/surface intersection expressed in both world and wall coordinates."""

    point: Vec3
    distance: float
    """Distance supplied by the producing operation, in metres.

    Ray intersections report travel from the ray origin. ``project_point``
    reports radial snap offset instead; only ray-intersection hits are valid
    inputs to inverse-square photometry.
    """
    s: float
    z: float
    normal: Vec3
    incidence: float
    """Angle in radians between the incoming ray and the surface normal.

    Zero means the ray strikes the wall square-on; approaching pi/2 means a
    grazing hit, which stretches the image and dims it.
    """


@dataclass(frozen=True)
class CylindricalWall:
    """A vertical-axis cylindrical wall segment.

    ``base_center`` is the point on the cylinder axis at the bottom of the
    wall. ``angle_start``/``angle_end`` are measured in the XY plane from the
    +X axis, counter-clockwise, in radians. ``concave=True`` means the usable
    projection surface faces the axis, i.e. projectors stand inside the arc.
    """

    base_center: Vec3 = (0.0, 0.0, 0.0)
    radius: float = 5.0
    height: float = 3.0
    angle_start: float = math.radians(-60.0)
    angle_end: float = math.radians(60.0)
    concave: bool = True
    name: str = "CurvedWall"

    def __post_init__(self) -> None:
        for axis, value in zip("xyz", self.base_center, strict=True):
            require_finite(f"wall base {axis}", value)
        require_positive("wall radius", self.radius)
        require_positive("wall height", self.height)
        require_finite("wall angle_start", self.angle_start)
        require_finite("wall angle_end", self.angle_end)
        if self.angle_end <= self.angle_start:
            raise ProjectionError(
                "wall angle_end must be greater than angle_start "
                f"(got {self.angle_start} to {self.angle_end})"
            )
        if self.angle_end - self.angle_start > 2.0 * math.pi + 1e-9:
            raise ProjectionError("wall arc cannot exceed a full revolution")

    # -- basic geometry ---------------------------------------------------

    @property
    def sweep(self) -> float:
        """Angular sweep in radians."""
        return self.angle_end - self.angle_start

    @property
    def arc_length(self) -> float:
        """Length of the wall measured along its curve, in metres."""
        return self.radius * self.sweep

    @property
    def z_bottom(self) -> float:
        return self.base_center[2]

    @property
    def z_top(self) -> float:
        return self.base_center[2] + self.height

    @property
    def area(self) -> float:
        return self.arc_length * self.height

    def angle_at_s(self, s: float) -> float:
        return self.angle_start + s / self.radius

    def s_at_angle(self, angle: float) -> float:
        return (angle - self.angle_start) * self.radius

    def point_at(self, s: float, z: float) -> Vec3:
        """World point at arc length ``s`` and height ``z`` above the base."""
        a = self.angle_at_s(s)
        return (
            self.base_center[0] + self.radius * math.cos(a),
            self.base_center[1] + self.radius * math.sin(a),
            self.base_center[2] + z,
        )

    def normal_at_s(self, s: float) -> Vec3:
        """Outward-facing surface normal (points away from the wall material).

        For a concave wall this points toward the axis, i.e. back at the
        projectors.
        """
        a = self.angle_at_s(s)
        radial = (math.cos(a), math.sin(a), 0.0)
        return scale(radial, -1.0 if self.concave else 1.0)

    def center_point(self) -> Vec3:
        return self.point_at(self.arc_length * 0.5, self.height * 0.5)

    def axis_point(self, z: float) -> Vec3:
        return (self.base_center[0], self.base_center[1], self.base_center[2] + z)

    def contains(self, s: float, z: float, tol: float = 1e-9) -> bool:
        return (
            -tol <= s <= self.arc_length + tol
            and -tol <= z <= self.height + tol
        )

    def project_point(self, point: Vec3) -> SurfaceHit | None:
        """Nearest wall point to ``point``, or ``None`` if outside the segment.

        Used to sanity-check a supplied aim target: an AV designer clicks a
        spot near the wall, and we snap it onto the surface.
        """
        dx = point[0] - self.base_center[0]
        dy = point[1] - self.base_center[1]
        r = math.hypot(dx, dy)
        if r < 1e-9:
            return None
        angle = math.atan2(dy, dx)
        s = self._wrapped_s(angle)
        z = point[2] - self.base_center[2]
        if s is None or not self.contains(s, z):
            return None
        return SurfaceHit(
            point=self.point_at(s, z),
            distance=abs(r - self.radius),
            s=s,
            z=z,
            normal=self.normal_at_s(s),
            incidence=0.0,
        )

    def _wrapped_s(self, angle: float) -> float | None:
        """Arc length for a world angle, independent of full-turn offsets."""
        delta = (angle - self.angle_start) % (2.0 * math.pi)
        if delta <= self.sweep + 1e-9:
            return min(delta, self.sweep) * self.radius
        # A point at the end of a full revolution may wrap numerically to zero.
        if self.sweep >= 2.0 * math.pi - 1e-9:
            return 0.0
        return None

    # -- ray casting ------------------------------------------------------

    def intersect_ray(
        self,
        origin: Vec3,
        direction: Vec3,
        max_distance: float = 1e6,
    ) -> SurfaceHit | None:
        """First forward intersection of a ray with the wall segment.

        Returns ``None`` when the ray misses the infinite cylinder, only hits
        it behind the origin, or hits outside the wall's angular/height bounds.
        """
        d = normalize(direction)
        px = origin[0] - self.base_center[0]
        py = origin[1] - self.base_center[1]

        a = d[0] * d[0] + d[1] * d[1]
        if a < 1e-12:
            # Ray is vertical: it is parallel to the wall and never crosses it.
            return None
        b = 2.0 * (px * d[0] + py * d[1])
        c = px * px + py * py - self.radius * self.radius
        disc = b * b - 4.0 * a * c
        if disc < 0.0:
            return None

        sqrt_disc = math.sqrt(disc)
        roots = sorted(((-b - sqrt_disc) / (2.0 * a), (-b + sqrt_disc) / (2.0 * a)))

        for t in roots:
            if t <= SURFACE_TOL or t > max_distance:
                continue
            hit = self._hit_at(origin, d, t)
            if hit is not None:
                if hit.incidence >= math.pi * 0.5 - 1e-9:
                    return None
                return hit
        return None

    def _hit_at(self, origin: Vec3, d: Vec3, t: float) -> SurfaceHit | None:
        point = (
            origin[0] + d[0] * t,
            origin[1] + d[1] * t,
            origin[2] + d[2] * t,
        )
        z = point[2] - self.base_center[2]
        if not (-1e-9 <= z <= self.height + 1e-9):
            return None
        angle = math.atan2(point[1] - self.base_center[1], point[0] - self.base_center[0])
        s = self._wrapped_s(angle)
        if s is None:
            return None
        normal = self.normal_at_s(s)
        # Incidence is measured between the reversed ray and the outward normal.
        cos_i = dot(scale(d, -1.0), normal)
        incidence = math.acos(max(-1.0, min(1.0, cos_i)))
        return SurfaceHit(
            point=point,
            distance=t,
            s=s,
            z=z,
            normal=normal,
            incidence=incidence,
        )


def flat_wall_as_cylinder(width: float, height: float, radius: float = 5000.0) -> CylindricalWall:
    """A very large-radius cylinder, close enough to flat for comparison tests.

    Handy for validating curved-wall code against textbook flat-screen throw
    numbers without writing a second surface type.
    """
    require_positive("wall width", width)
    require_positive("wall radius", radius)
    half_sweep = (width / radius) / 2.0
    return CylindricalWall(
        base_center=(0.0, 0.0, 0.0),
        radius=radius,
        height=height,
        angle_start=-half_sweep,
        angle_end=half_sweep,
        concave=True,
        name="FlatWall",
    )


def wall_outline(wall: CylindricalWall, segments: int = 48) -> list[Vec3]:
    """Bottom-edge polyline of the wall, for quick visual checks."""
    if segments < 2:
        raise ProjectionError(f"need at least 2 segments, got {segments}")
    step = wall.arc_length / (segments - 1)
    return [wall.point_at(i * step, 0.0) for i in range(segments)]
