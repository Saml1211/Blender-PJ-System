"""Projection surfaces and ray intersection.

Two vertical projection walls are implemented: a cylindrical segment
(:class:`CylindricalWall`) covering the curved-wall AV case, and a true planar
wall (:class:`PlanarWall`) for the even more common flat-wall case. Both share
a 2D ``(s, z)`` parameterisation declared by :class:`Surface`:

* ``s`` is distance measured along the wall face from one edge, in metres
  (arc length on a cylinder, straight-line distance on a plane)
* ``z`` is height above the wall base, in metres

That parameterisation is what coverage and blend analysis operate in, because
measuring along the wall is what an installer actually does.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace

from .errors import ProjectionError, require_finite, require_positive
from .vectors import Vec3, dot, normalize, scale

#: Radial tolerance when classifying a point as "on" the wall, in metres.
SURFACE_TOL = 1e-6

#: World-up direction; both implemented surfaces are vertical walls.
_UP: Vec3 = (0.0, 0.0, 1.0)


class Surface(ABC):
    """Common contract for a vertical projection surface in ``(s, z)`` coords.

    ``s`` runs from one edge of the usable face to the other (``[0,
    arc_length]``) and ``z`` from the base upward (``[0, height]``).
    Downstream modules (footprint, coverage, array, visualization) operate
    exclusively through this interface; concrete geometry lives in the
    subclasses. See ADR 0003 for why the cylinder-specific questions below
    are asked through generic hooks rather than by reading fields.
    """

    #: Bottom-centre reference point of the wall, in world coordinates.
    base_center: Vec3
    #: Display name carried through reports and Blender objects.
    name: str
    #: Wall height above the base, in metres.
    height: float

    # -- geometry every surface must define ---------------------------------

    @property
    @abstractmethod
    def arc_length(self) -> float:
        """Length of the usable face measured along the wall, in metres."""

    @abstractmethod
    def point_at(self, s: float, z: float) -> Vec3:
        """World point at wall-coordinate ``(s, z)``."""

    @abstractmethod
    def normal_at_s(self, s: float) -> Vec3:
        """Outward-facing surface normal at ``s`` (points at the projectors)."""

    @abstractmethod
    def intersect_ray(
        self,
        origin: Vec3,
        direction: Vec3,
        max_distance: float = 1e6,
    ) -> SurfaceHit | None:
        """First forward intersection of a ray with the usable face."""

    @abstractmethod
    def project_point(self, point: Vec3) -> SurfaceHit | None:
        """Nearest point on the usable face, or ``None`` if outside it."""

    @abstractmethod
    def expanded(self, pad_s: float, pad_z: float) -> Surface:
        """An oversized copy padded by ``pad_s``/``pad_z`` metres each side."""

    @abstractmethod
    def measurement_wall(self) -> Surface:
        """A deliberately oversized copy, used while solving placements.

        Edge projectors aim at the very end of the face, so their image would
        be clipped by the real bounds and the measured span would be wrong.
        The array solver iterates against this extended surface and evaluates
        the final footprint against the real one.
        """

    # -- derived quantities shared by every surface -------------------------

    @property
    def area(self) -> float:
        return self.arc_length * self.height

    @property
    def z_bottom(self) -> float:
        return self.base_center[2]

    @property
    def z_top(self) -> float:
        return self.base_center[2] + self.height

    def contains(self, s: float, z: float, tol: float = 1e-9) -> bool:
        return (
            -tol <= s <= self.arc_length + tol
            and -tol <= z <= self.height + tol
        )

    def center_point(self) -> Vec3:
        return self.point_at(self.arc_length * 0.5, self.height * 0.5)

    # -- hooks for behaviour that only some surfaces have --------------------

    @property
    def wraps_around(self) -> bool:
        """Whether the face closes on itself, needing seam unwrapping."""
        return False

    @property
    def curvature_radius(self) -> float | None:
        """Radius of curvature, or ``None`` for a flat face."""
        return None

    def chord(self, span: float) -> float:
        """Straight-line width across the face subtending ``span`` along it."""
        return span

    @property
    def normal_faces_projectors(self) -> bool:
        """Whether ``normal_at_s`` points toward the projector side.

        Used by the Blender layer to wind generated wall faces so they are
        visible from the projector side of the surface.
        """
        return True


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
class CylindricalWall(Surface):
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

    # -- Surface contract ----------------------------------------------------

    @property
    def wraps_around(self) -> bool:
        """Whether the face closes on itself and needs seam unwrapping."""
        return self.sweep >= 2.0 * math.pi - 1e-9

    @property
    def normal_faces_projectors(self) -> bool:
        return self.concave

    @property
    def curvature_radius(self) -> float | None:
        return self.radius

    def chord(self, span: float) -> float:
        """Straight-line chord subtending ``span`` of arc."""
        return 2.0 * self.radius * math.sin(min(math.pi, span / (2.0 * self.radius)))

    def expanded(self, pad_s: float, pad_z: float) -> CylindricalWall:
        """An oversized copy padded by ``pad_s`` m of arc / ``pad_z`` m each side."""
        pad_angle = pad_s / self.radius
        start = self.angle_start - pad_angle
        end = self.angle_end + pad_angle
        if end - start > 2.0 * math.pi:
            mid = 0.5 * (self.angle_start + self.angle_end)
            start, end = mid - math.pi + 1e-6, mid + math.pi - 1e-6
        return replace(
            self,
            base_center=(
                self.base_center[0],
                self.base_center[1],
                self.base_center[2] - pad_z,
            ),
            height=self.height + 2.0 * pad_z,
            angle_start=start,
            angle_end=end,
        )

    def measurement_wall(self) -> CylindricalWall:
        """Extend the arc by roughly three quarters of itself, plus slack.

        The generous padding keeps even edge-aimed solve iterations from being
        clipped by the real bounds; see :meth:`Surface.measurement_wall`.
        """
        pad_angle = min(math.pi * 0.5, self.sweep * 0.75 + 0.35)
        return replace(
            self.expanded(pad_angle * self.radius, self.height * 2.0),
            name=self.name + "(solve)",
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

    Kept for backwards compatibility with tests that pin its behaviour; new
    code should model a genuinely flat wall with :class:`PlanarWall`, which is
    exact rather than "under a millimetre of bow".
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


@dataclass(frozen=True)
class PlanarWall(Surface):
    """A vertical rectangular flat wall.

    ``base_center`` is the bottom-centre of the wall *on the wall face* —
    unlike :class:`CylindricalWall`, whose base centre sits on the cylinder
    axis. ``facing`` is the horizontal normal pointing at the projectors; it
    is normalised on construction. ``s`` runs from 0 at the left edge (as seen
    from the projector side) to ``width`` at the right edge.
    """

    base_center: Vec3 = (0.0, 0.0, 0.0)
    width: float = 4.0
    height: float = 2.5
    facing: Vec3 = (-1.0, 0.0, 0.0)
    name: str = "FlatWall"

    def __post_init__(self) -> None:
        for axis, value in zip("xyz", self.base_center, strict=True):
            require_finite(f"wall base {axis}", value)
        require_positive("wall width", self.width)
        require_positive("wall height", self.height)
        length_sq = sum(component * component for component in self.facing)
        if length_sq < 1e-18:
            raise ProjectionError("wall facing direction must not be a zero vector")
        for axis, value in zip("xyz", self.facing, strict=True):
            require_finite(f"wall facing {axis}", value)
        if abs(self.facing[2]) > 1e-6:
            raise ProjectionError(
                "wall facing must be horizontal; inclined walls are not supported"
            )
        # Frozen dataclass: store the normalised facing via object.__setattr__.
        object.__setattr__(self, "facing", normalize(self.facing))

    # -- Surface contract ----------------------------------------------------

    @property
    def arc_length(self) -> float:
        return self.width

    @property
    def right(self) -> Vec3:
        """Unit vector along the face toward increasing ``s``."""
        n = self.facing
        # Horizontal cross product of the facing normal with +Z; unit-length
        # because the normal is horizontal.
        return (n[1], -n[0], 0.0)

    def point_at(self, s: float, z: float) -> Vec3:
        """World point at wall-coordinate ``(s, z)``."""
        offset = s - self.width * 0.5
        r = self.right
        return (
            self.base_center[0] + r[0] * offset,
            self.base_center[1] + r[1] * offset,
            self.base_center[2] + z,
        )

    def normal_at_s(self, s: float) -> Vec3:
        """Outward-facing surface normal; constant across a flat face."""
        return self.facing

    def project_point(self, point: Vec3) -> SurfaceHit | None:
        """Nearest point on the wall rectangle, or ``None`` if outside it."""
        v = (
            point[0] - self.base_center[0],
            point[1] - self.base_center[1],
            point[2] - self.base_center[2],
        )
        r = self.right
        s = v[0] * r[0] + v[1] * r[1] + self.width * 0.5
        z = v[2]
        if not self.contains(s, z):
            return None
        off_plane = v[0] * self.facing[0] + v[1] * self.facing[1]
        return SurfaceHit(
            point=self.point_at(min(max(s, 0.0), self.width), min(max(z, 0.0), self.height)),
            distance=abs(off_plane),
            s=s,
            z=z,
            normal=self.facing,
            incidence=0.0,
        )

    def intersect_ray(
        self,
        origin: Vec3,
        direction: Vec3,
        max_distance: float = 1e6,
    ) -> SurfaceHit | None:
        """First forward intersection of a ray with the wall rectangle.

        Back-face hits are rejected exactly as a concave cylinder rejects
        them: a ray travelling along the normal can never strike the usable
        side of the face.
        """
        d = normalize(direction)
        denom = d[0] * self.facing[0] + d[1] * self.facing[1] + d[2] * self.facing[2]
        if denom >= -1e-12:
            # Parallel to the face, or approaching it from behind.
            return None
        to_base = (
            self.base_center[0] - origin[0],
            self.base_center[1] - origin[1],
            self.base_center[2] - origin[2],
        )
        t = (to_base[0] * self.facing[0] + to_base[1] * self.facing[1]) / denom
        if t <= SURFACE_TOL or t > max_distance:
            return None
        hit_point = (
            origin[0] + d[0] * t,
            origin[1] + d[1] * t,
            origin[2] + d[2] * t,
        )
        r = self.right
        local_s = (
            (hit_point[0] - self.base_center[0]) * r[0]
            + (hit_point[1] - self.base_center[1]) * r[1]
        ) + self.width * 0.5
        z = hit_point[2] - self.base_center[2]
        if not (-1e-9 <= local_s <= self.width + 1e-9):
            return None
        if not (-1e-9 <= z <= self.height + 1e-9):
            return None
        cos_i = -(d[0] * self.facing[0] + d[1] * self.facing[1] + d[2] * self.facing[2])
        incidence = math.acos(max(-1.0, min(1.0, cos_i)))
        return SurfaceHit(
            point=hit_point,
            distance=t,
            s=min(max(local_s, 0.0), self.width),
            z=min(max(z, 0.0), self.height),
            normal=self.facing,
            incidence=incidence,
        )

    def expanded(self, pad_s: float, pad_z: float) -> PlanarWall:
        """An oversized copy padded by ``pad_s``/``pad_z`` metres each side."""
        return replace(
            self,
            width=self.width + 2.0 * pad_s,
            height=self.height + 2.0 * pad_z,
            base_center=(
                self.base_center[0],
                self.base_center[1],
                self.base_center[2] - pad_z,
            ),
        )

    def measurement_wall(self) -> PlanarWall:
        """Widen by about half the wall plus slack, and double the height."""
        return replace(
            self.expanded(max(2.0, self.width * 0.5), self.height * 2.0),
            name=self.name + "(solve)",
        )


def wall_outline(wall: Surface, segments: int = 48) -> list[Vec3]:
    """Bottom-edge polyline of the wall, for quick visual checks."""
    if segments < 2:
        raise ProjectionError(f"need at least 2 segments, got {segments}")
    step = wall.arc_length / (segments - 1)
    return [wall.point_at(i * step, 0.0) for i in range(segments)]
