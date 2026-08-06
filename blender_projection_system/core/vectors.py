"""Minimal 3D vector helpers.

The core package must import cleanly outside Blender, so it cannot use
``mathutils``. Vectors are plain ``(x, y, z)`` tuples of floats.
"""

from __future__ import annotations

import math

from .errors import ProjectionError

Vec3 = tuple[float, float, float]

EPS = 1e-9


def add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a: Vec3, k: float) -> Vec3:
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(a: Vec3) -> float:
    return math.sqrt(dot(a, a))


def distance(a: Vec3, b: Vec3) -> float:
    return length(sub(a, b))


def normalize(a: Vec3) -> Vec3:
    n = length(a)
    if n < EPS:
        raise ProjectionError("cannot normalize a zero-length vector")
    return (a[0] / n, a[1] / n, a[2] / n)


def angle_between(a: Vec3, b: Vec3) -> float:
    """Angle in radians between two vectors, clamped against float drift."""
    c = dot(normalize(a), normalize(b))
    return math.acos(max(-1.0, min(1.0, c)))


def lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )
