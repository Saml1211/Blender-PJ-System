"""Throw geometry: throw ratio, image size, lens shift and frustum rays.

Coordinate convention
--------------------
Projector-local axes follow Blender's camera convention:

* ``-Z`` is the optical axis (the direction light travels)
* ``+X`` is image right
* ``+Y`` is image up

Lens shift convention
---------------------
``lens_shift_v`` / ``lens_shift_h`` are the offset of the *image centre* from
the optical axis, expressed as a fraction of the *full* image height / width.
So ``lens_shift_v = 0.5`` puts the optical axis exactly on the bottom edge of
the image.

Manufacturers are not consistent here. Many datasheets (Christie, Barco,
Panasonic) call that same geometry "100% offset", i.e. they express shift as a
fraction of *half* the image dimension. Use
:func:`shift_from_half_image_percent` to convert a datasheet number into this
module's convention.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .errors import ProjectionError, require_finite, require_positive
from .vectors import Vec3, normalize

#: Image-plane corner order used everywhere in this package.
CORNER_UV: tuple[tuple[float, float], ...] = (
    (-0.5, 0.5),   # top-left
    (0.5, 0.5),    # top-right
    (0.5, -0.5),   # bottom-right
    (-0.5, -0.5),  # bottom-left
)


@dataclass(frozen=True)
class ProjectorSpec:
    """Static optical/photometric description of one projector.

    ``throw_ratio`` is the *native* throw ratio in use (D / W). Zoom lenses are
    represented by picking a value inside the lens range; ``throw_ratio_min``
    and ``throw_ratio_max`` are carried only so callers can validate a chosen
    value against the lens.
    """

    throw_ratio: float = 1.5
    aspect_w: int = 16
    aspect_h: int = 9
    lumens: float = 5000.0
    lens_shift_v: float = 0.0
    lens_shift_h: float = 0.0
    max_lens_shift_v: float = 0.5
    max_lens_shift_h: float = 0.15
    throw_ratio_min: float = 0.0
    throw_ratio_max: float = 0.0
    label: str = ""

    def __post_init__(self) -> None:
        require_positive("throw_ratio", self.throw_ratio)
        require_positive("aspect width", self.aspect_w)
        require_positive("aspect height", self.aspect_h)
        require_finite("lumens", self.lumens)
        require_finite("vertical lens shift", self.lens_shift_v)
        require_finite("horizontal lens shift", self.lens_shift_h)
        require_finite("maximum vertical lens shift", self.max_lens_shift_v)
        require_finite("maximum horizontal lens shift", self.max_lens_shift_h)
        require_finite("minimum throw ratio", self.throw_ratio_min)
        require_finite("maximum throw ratio", self.throw_ratio_max)
        if self.aspect_w <= 0 or self.aspect_h <= 0:
            raise ProjectionError(
                f"aspect ratio components must be positive, got "
                f"{self.aspect_w}:{self.aspect_h}"
            )
        if self.lumens < 0:
            raise ProjectionError(f"lumens must not be negative, got {self.lumens}")
        if self.max_lens_shift_v < 0 or self.max_lens_shift_h < 0:
            raise ProjectionError("maximum lens shifts must not be negative")
        if self.throw_ratio_min < 0 or self.throw_ratio_max < 0:
            raise ProjectionError("lens throw-ratio limits must not be negative")

    @property
    def aspect(self) -> float:
        """Image aspect ratio as width / height."""
        return self.aspect_w / self.aspect_h

    def lens_shift_within_limits(self) -> bool:
        return (
            abs(self.lens_shift_v) <= self.max_lens_shift_v + 1e-9
            and abs(self.lens_shift_h) <= self.max_lens_shift_h + 1e-9
        )

    def throw_ratio_within_lens(self) -> bool:
        """True unless an explicit lens range is set and the value falls outside."""
        if self.throw_ratio_min <= 0.0 or self.throw_ratio_max <= 0.0:
            return True
        lo, hi = sorted((self.throw_ratio_min, self.throw_ratio_max))
        return lo - 1e-9 <= self.throw_ratio <= hi + 1e-9


@dataclass(frozen=True)
class ImageSize:
    width: float
    height: float

    @property
    def diagonal(self) -> float:
        return math.hypot(self.width, self.height)

    @property
    def area(self) -> float:
        return self.width * self.height


def shift_from_half_image_percent(percent: float) -> float:
    """Convert a datasheet "% offset" (fraction of half the image) to our units.

    A datasheet quoting "±100% vertical offset" means the optical axis reaches
    the image edge, which is ``0.5`` in this module's convention.
    """
    return percent / 200.0


def shift_to_half_image_percent(shift: float) -> float:
    """Inverse of :func:`shift_from_half_image_percent`."""
    return shift * 200.0


def aspect_ratio(aspect_w: int, aspect_h: int) -> float:
    if aspect_w <= 0 or aspect_h <= 0:
        raise ProjectionError(
            f"aspect ratio components must be positive, got {aspect_w}:{aspect_h}"
        )
    return aspect_w / aspect_h


def image_width_from_distance(distance: float, throw_ratio: float) -> float:
    """W = D / TR."""
    require_positive("throw distance", distance)
    require_positive("throw ratio", throw_ratio)
    return distance / throw_ratio


def throw_distance_from_width(width: float, throw_ratio: float) -> float:
    """D = W * TR."""
    require_positive("image width", width)
    require_positive("throw ratio", throw_ratio)
    return width * throw_ratio


def throw_ratio_from(distance: float, width: float) -> float:
    """TR = D / W."""
    require_positive("throw distance", distance)
    require_positive("image width", width)
    return distance / width


def image_height_from_width(width: float, aspect: float) -> float:
    """H = W / aspect."""
    require_positive("image width", width)
    require_positive("aspect ratio", aspect)
    return width / aspect


def image_size(distance: float, spec: ProjectorSpec) -> ImageSize:
    """Image dimensions on a flat screen normal to the axis at ``distance``."""
    width = image_width_from_distance(distance, spec.throw_ratio)
    return ImageSize(width, image_height_from_width(width, spec.aspect))


def half_angles(spec: ProjectorSpec) -> tuple[float, float]:
    """Half of the horizontal and vertical field of view, in radians.

    ``tan(theta_h) = (W/2)/D = 1/(2*TR)`` and the vertical follows from the
    aspect ratio. Lens shift does not change these angles, only where the
    frustum sits relative to the axis.
    """
    th = math.atan(1.0 / (2.0 * spec.throw_ratio))
    tv = math.atan(1.0 / (2.0 * spec.throw_ratio * spec.aspect))
    return th, tv


def full_angles_deg(spec: ProjectorSpec) -> tuple[float, float]:
    th, tv = half_angles(spec)
    return math.degrees(2.0 * th), math.degrees(2.0 * tv)


def image_point_local(u: float, v: float, distance: float, spec: ProjectorSpec) -> Vec3:
    """Point on the image plane in projector-local space.

    ``u`` and ``v`` run from ``-0.5`` (left/bottom) to ``+0.5`` (right/top).
    """
    require_positive("throw distance", distance)
    size = image_size(distance, spec)
    x = (u + spec.lens_shift_h) * size.width
    y = (v + spec.lens_shift_v) * size.height
    return (x, y, -distance)


def ray_direction_local(u: float, v: float, spec: ProjectorSpec) -> Vec3:
    """Unit ray direction from the lens through image-plane point ``(u, v)``.

    Independent of throw distance: the image plane grows linearly with
    distance, so the direction is fixed by throw ratio, aspect and lens shift.
    """
    return normalize(image_point_local(u, v, 1.0, spec))


def frustum_corners_local(distance: float, spec: ProjectorSpec) -> list[Vec3]:
    """The four image corners at ``distance``, in :data:`CORNER_UV` order."""
    return [image_point_local(u, v, distance, spec) for u, v in CORNER_UV]


def frustum_corner_rays(spec: ProjectorSpec) -> list[Vec3]:
    """Unit direction vectors through the four image corners."""
    return [ray_direction_local(u, v, spec) for u, v in CORNER_UV]


def required_lens_shift_v(vertical_offset: float, image_height: float) -> float:
    """Vertical shift needed to move the image centre by ``vertical_offset``.

    Positive ``vertical_offset`` means the image centre sits above the optical
    axis. Used for ceiling mounts where the axis is kept horizontal and the
    lens is shifted down onto the screen (a negative result).
    """
    require_positive("image height", image_height)
    return vertical_offset / image_height


def grid_uv(samples: int) -> list[tuple[float, float]]:
    """Row-major ``(u, v)`` grid over the image plane, top row first.

    ``samples`` is the count per axis; the outermost samples land exactly on
    the image edges so footprint extents are not under-reported.
    """
    if samples < 2:
        raise ProjectionError(f"need at least 2 samples per axis, got {samples}")
    step = 1.0 / (samples - 1)
    out: list[tuple[float, float]] = []
    for row in range(samples):
        v = 0.5 - row * step
        for col in range(samples):
            u = -0.5 + col * step
            out.append((u, v))
    return out


def grid_boundary_indices(samples: int) -> list[int]:
    """Indices into :func:`grid_uv` tracing the image perimeter once, in order.

    The walk goes along the top row left-to-right, down the right column, back
    along the bottom row, then up the left column, producing a simple polygon.
    """
    if samples < 2:
        raise ProjectionError(f"need at least 2 samples per axis, got {samples}")
    n = samples

    def idx(row: int, col: int) -> int:
        return row * n + col

    out: list[int] = []
    for col in range(n):
        out.append(idx(0, col))
    for row in range(1, n):
        out.append(idx(row, n - 1))
    for col in range(n - 2, -1, -1):
        out.append(idx(n - 1, col))
    for row in range(n - 2, 0, -1):
        out.append(idx(row, 0))
    return out


@dataclass(frozen=True)
class ThrowReport:
    """Human-facing summary of one projector's throw geometry."""

    throw_distance: float
    image_width: float
    image_height: float
    image_diagonal: float
    throw_ratio: float
    aspect: float
    h_fov_deg: float
    v_fov_deg: float
    lens_shift_v: float
    lens_shift_h: float
    warnings: list[str] = field(default_factory=list)


def describe_throw(distance: float, spec: ProjectorSpec) -> ThrowReport:
    """Bundle the throw numbers plus any spec-limit warnings."""
    size = image_size(distance, spec)
    h_fov, v_fov = full_angles_deg(spec)
    warnings: list[str] = []
    if not spec.lens_shift_within_limits():
        warnings.append(
            f"lens shift V={spec.lens_shift_v:+.3f} H={spec.lens_shift_h:+.3f} "
            f"exceeds the configured limits "
            f"(±{spec.max_lens_shift_v:.3f} / ±{spec.max_lens_shift_h:.3f})"
        )
    if not spec.throw_ratio_within_lens():
        warnings.append(
            f"throw ratio {spec.throw_ratio:.3f} is outside the lens range "
            f"{spec.throw_ratio_min:.3f}-{spec.throw_ratio_max:.3f}"
        )
    return ThrowReport(
        throw_distance=distance,
        image_width=size.width,
        image_height=size.height,
        image_diagonal=size.diagonal,
        throw_ratio=spec.throw_ratio,
        aspect=spec.aspect,
        h_fov_deg=h_fov,
        v_fov_deg=v_fov,
        lens_shift_v=spec.lens_shift_v,
        lens_shift_h=spec.lens_shift_h,
        warnings=warnings,
    )
