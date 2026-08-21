"""Projector placement and orientation in world space.

A :class:`Pose` is an origin plus an orthonormal basis. ``forward`` is the
direction light travels (projector-local ``-Z``), ``right`` is local ``+X`` and
``up`` is local ``+Y``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import ProjectionError
from .vectors import Vec3, add, cross, dot, normalize, scale, sub

WORLD_UP: Vec3 = (0.0, 0.0, 1.0)


@dataclass(frozen=True)
class Pose:
    origin: Vec3
    right: Vec3
    up: Vec3
    forward: Vec3

    def local_to_world_dir(self, local: Vec3) -> Vec3:
        """Map a projector-local direction into world space.

        Local ``-Z`` maps to :attr:`forward`, so the local Z basis vector is
        ``-forward``.
        """
        lx, ly, lz = local
        return add(
            add(scale(self.right, lx), scale(self.up, ly)),
            scale(self.forward, -lz),
        )

    def local_to_world_point(self, local: Vec3) -> Vec3:
        return add(self.origin, self.local_to_world_dir(local))

    def basis_columns(self) -> tuple[Vec3, Vec3, Vec3]:
        """Local X, Y, Z axes in world space, ready for a 3x3 rotation matrix."""
        back = scale(self.forward, -1.0)
        return self.right, self.up, back

    @property
    def tilt_deg(self) -> float:
        """Signed pitch of the optical axis: negative aims below horizontal."""
        return math.degrees(math.asin(max(-1.0, min(1.0, self.forward[2]))))


def look_at(origin: Vec3, target: Vec3, roll: float = 0.0) -> Pose:
    """Build a pose whose optical axis points from ``origin`` to ``target``.

    ``roll`` rotates the projector about its own optical axis, in radians.
    The up vector is derived from world +Z; if the axis is within a degree of
    vertical, world +Y is used instead so the basis stays well-conditioned.
    """
    delta = sub(target, origin)
    try:
        forward = normalize(delta)
    except ValueError:
        raise ProjectionError(
            "projector origin and aim target coincide; cannot derive an aim direction"
        ) from None

    reference: Vec3 = WORLD_UP
    if abs(dot(forward, WORLD_UP)) > 0.9998:
        reference = (0.0, 1.0, 0.0)

    right = normalize(cross(forward, reference))
    up = normalize(cross(right, forward))

    if roll:
        c, s = math.cos(roll), math.sin(roll)
        rolled_right = add(scale(right, c), scale(up, s))
        rolled_up = add(scale(up, c), scale(right, -s))
        right, up = normalize(rolled_right), normalize(rolled_up)

    return Pose(origin=origin, right=right, up=up, forward=forward)


def level_pose(origin: Vec3, heading: Vec3, roll: float = 0.0) -> Pose:
    """Pose with a strictly horizontal optical axis pointing along ``heading``.

    This is the ceiling-mount case where the projector is kept level and lens
    shift does the vertical work. The horizontal component of ``heading`` sets
    the direction; its Z component is discarded.
    """
    flat = (heading[0], heading[1], 0.0)
    if math.hypot(flat[0], flat[1]) < 1e-9:
        raise ProjectionError(
            "heading has no horizontal component; cannot build a level pose"
        )
    target = add(origin, normalize(flat))
    return look_at(origin, target, roll=roll)
