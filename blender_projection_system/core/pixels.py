"""Pixel and image-size arithmetic: pitch, density, acuity, blended canvases.

Pure Python (ADR 0001). Lengths are metres and angles radians like the rest
of :mod:`core`; the ``fmt_*`` helpers and :func:`scenario_rows` turn them into
the millimetre text the add-on prints.

Lens shift uses the convention of :mod:`.throw`: ``lens_shift_v`` is the
offset of the image centre from the optical axis as a fraction of the *full*
image height, positive upward. So for a level projector the image centre sits
at ``lens_height + lens_shift_v * image_height``.
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from .errors import ProjectionError, require_finite, require_positive
from .throw import (
    ProjectorSpec,
    image_height_from_width,
    image_width_from_distance,
    required_lens_shift_v,
    throw_distance_from_width,
    throw_ratio_from,
)

#: One minute of arc, the 20/20 visual-acuity limit, in radians.
ARCMINUTE = math.radians(1.0 / 60.0)

_MM = 1000.0


# ---------------------------------------------------------------------------
# Pitch and density
# ---------------------------------------------------------------------------


def pixel_pitch(image_width: float, pixels: int) -> float:
    """Mean distance between pixel centres across ``image_width`` (m/px)."""
    require_positive("image width", image_width)
    require_positive("pixel count", pixels)
    return image_width / pixels


def pixels_per_metre(image_width: float, pixels: int) -> float:
    """Pixel density across ``image_width`` (px/m), the inverse of the pitch."""
    return 1.0 / pixel_pitch(image_width, pixels)


# ---------------------------------------------------------------------------
# Image size from any two throw quantities
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImageSolution:
    """A consistent set of throw distance, throw ratio and image size."""

    distance: float
    throw_ratio: float
    width: float
    height: float

    @property
    def diagonal(self) -> float:
        return math.hypot(self.width, self.height)


def width_from_diagonal(diagonal: float, aspect: float) -> float:
    """Image width for a diagonal at ``aspect`` (width / height)."""
    require_positive("image diagonal", diagonal)
    require_positive("aspect ratio", aspect)
    return diagonal * aspect / math.hypot(aspect, 1.0)


def solve_image(
    aspect: float,
    *,
    distance: float | None = None,
    throw_ratio: float | None = None,
    width: float | None = None,
    height: float | None = None,
    diagonal: float | None = None,
) -> ImageSolution:
    """Solve the throw triangle from exactly two of the five quantities.

    ``width``, ``height`` and ``diagonal`` are one degree of freedom at a
    fixed ``aspect``, so a valid pair is either distance + throw ratio, or one
    of those plus one image dimension. Anything else raises.
    """
    require_positive("aspect ratio", aspect)
    sizes = (("width", width), ("height", height), ("diagonal", diagonal))
    given_sizes = [(k, v) for k, v in sizes if v is not None]
    given = len(given_sizes) + (distance is not None) + (throw_ratio is not None)
    if given != 2 or len(given_sizes) > 1:
        raise ProjectionError(
            "give exactly two of distance, throw ratio and one image dimension "
            "(width, height or diagonal)"
        )
    if given_sizes:
        kind, value = given_sizes[0]
        if kind == "width":
            w = value
        elif kind == "height":
            require_positive("image height", value)
            w = value * aspect
        else:
            w = width_from_diagonal(value, aspect)
        require_positive("image width", w)
        if distance is not None:
            tr = throw_ratio_from(distance, w)
            d = distance
        else:
            d = throw_distance_from_width(w, throw_ratio)
            tr = throw_ratio
    else:
        d, tr = distance, throw_ratio
        w = image_width_from_distance(d, tr)
    return ImageSolution(d, tr, w, image_height_from_width(w, aspect))


# ---------------------------------------------------------------------------
# Vertical placement: image edges above the floor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerticalExtent:
    """Image centre, bottom and top edge heights above the floor (AFF)."""

    centre: float
    bottom: float
    top: float


def image_vertical_extent(
    lens_height: float, image_height: float, lens_shift_v: float
) -> VerticalExtent:
    """Image edges for a level projector whose lens sits at ``lens_height``.

    ``lens_shift_v`` uses the :mod:`.throw` convention (fraction of the full
    image height, positive puts the image above the axis). A tilted mount is
    out of scope: tilt keystones the image and the edges stop being level.
    """
    require_finite("lens height", lens_height)
    require_positive("image height", image_height)
    require_finite("vertical lens shift", lens_shift_v)
    centre = lens_height + lens_shift_v * image_height
    return VerticalExtent(centre, centre - 0.5 * image_height, centre + 0.5 * image_height)


def shift_for_bottom_edge(lens_height: float, image_height: float, target_bottom: float) -> float:
    """Vertical shift that puts the image bottom edge on ``target_bottom``."""
    centre = target_bottom + 0.5 * image_height
    return required_lens_shift_v(centre - lens_height, image_height)


def vertical_fit_warnings(
    extent: VerticalExtent,
    target_bottom: float,
    target_height: float = 0.0,
    tolerance: float = 0.001,
) -> list[str]:
    """Compare the image edges with a screen's bottom edge and height.

    ``target_height <= 0`` checks the bottom edge only. Differences within
    ``tolerance`` (1 mm by default) pass silently.
    """
    out: list[str] = []
    below = target_bottom - extent.bottom
    if abs(below) > tolerance:
        where = "below" if below > 0 else "above"
        out.append(
            f"Image bottom {fmt_mm(extent.bottom)} AFF is {fmt_mm(abs(below))} {where} "
            f"the screen bottom edge {fmt_mm(target_bottom)}"
        )
    if target_height > 0.0:
        target_top = target_bottom + target_height
        above = extent.top - target_top
        if abs(above) > tolerance:
            where = "above" if above > 0 else "below"
            out.append(
                f"Image top {fmt_mm(extent.top)} AFF is {fmt_mm(abs(above))} {where} "
                f"the screen top edge {fmt_mm(target_top)}"
            )
    return out


# ---------------------------------------------------------------------------
# Visual acuity
# ---------------------------------------------------------------------------


def pixel_angle(pitch: float, viewing_distance: float) -> float:
    """Angle one pixel subtends at the eye (radians), viewer on axis."""
    require_positive("pixel pitch", pitch)
    require_positive("viewing distance", viewing_distance)
    return 2.0 * math.atan(pitch / (2.0 * viewing_distance))


def pixels_per_degree(pitch: float, viewing_distance: float) -> float:
    """Pixels inside one degree of the viewer's field (60 is the 20/20 limit)."""
    return 1.0 / math.degrees(pixel_angle(pitch, viewing_distance))


def one_arcminute_distance(pitch: float) -> float:
    """Viewing distance at which one pixel subtends one arcminute (20/20).

    Viewers closer than this can resolve individual pixels; viewers farther
    away cannot. Roughly ``3438 x pitch``.
    """
    require_positive("pixel pitch", pitch)
    return pitch / (2.0 * math.tan(0.5 * ARCMINUTE))


# ---------------------------------------------------------------------------
# Blended arrays
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Canvas:
    """The blended raster of a projector array.

    ``width`` is the physical canvas width in metres, ``0.0`` when unknown.
    """

    projectors: int
    pixels_x: int
    pixels_y: int
    overlap_px_total: int
    width: float = 0.0

    @property
    def pixels_per_metre(self) -> float:
        return self.pixels_x / self.width if self.width > 0.0 else 0.0

    @property
    def pitch(self) -> float:
        return self.width / self.pixels_x if self.width > 0.0 and self.pixels_x else 0.0


def blended_canvas(
    res_x: int,
    res_y: int,
    count: int,
    *,
    overlap_fraction: float | None = None,
    overlap_px: int | None = None,
    image_width: float = 0.0,
) -> Canvas:
    """Canvas of ``count`` identical projectors side by side in one row.

    Give the blend as ``overlap_fraction`` of one image width (rounded to whole
    pixels) or as ``overlap_px``. Canvas pixels are
    ``count * res_x - (count - 1) * overlap_px``; with ``image_width`` the
    physical width follows the same rule.
    """
    require_positive("horizontal resolution", res_x)
    require_positive("vertical resolution", res_y)
    if count < 1:
        raise ProjectionError(f"projector count must be at least 1, got {count}")
    if (overlap_fraction is None) == (overlap_px is None):
        raise ProjectionError("give the overlap as a fraction or in pixels, not both")
    if overlap_px is None:
        require_finite("overlap fraction", overlap_fraction)
        overlap_px = round(overlap_fraction * res_x)
    if not 0 <= overlap_px < res_x:
        raise ProjectionError(f"overlap must be 0 to {res_x - 1} px, got {overlap_px}")
    seams = count - 1
    pixels_x = count * res_x - seams * overlap_px
    width = 0.0
    if image_width > 0.0:
        width = image_width * (count - seams * overlap_px / res_x)
    return Canvas(count, pixels_x, res_y, seams * overlap_px, width)


def array_canvas(footprints: Sequence, blend_zones: Sequence) -> Canvas | None:
    """Blended canvas of the projectors actually on a wall.

    Uses each footprint's own resolution (``spec.resolution``) and arc span,
    and the measured overlap of each blend zone: a zone covering fraction
    ``f`` of a projector's arc span removes ``f * res_x`` of its pixels,
    averaged over the two neighbours. Physical width is the summed arc spans
    less the blend-zone widths. ``None`` when no footprint lands.
    """
    usable = [fp for fp in footprints if fp.hit_ratio > 0.0 and fp.arc_span > 0.0]
    if not usable:
        return None
    res = {fp.name: fp.spec.resolution for fp in usable}
    overlap = 0
    for zone in blend_zones:
        if zone.left not in res or zone.right not in res:
            continue
        overlap += round(
            0.5
            * (
                zone.overlap_fraction_left * res[zone.left][0]
                + zone.overlap_fraction_right * res[zone.right][0]
            )
        )
    pixels_x = sum(r[0] for r in res.values()) - overlap
    width = sum(fp.arc_span for fp in usable) - sum(z.width for z in blend_zones)
    return Canvas(
        len(usable), pixels_x, min(r[1] for r in res.values()), overlap, max(width, 0.0)
    )


@dataclass(frozen=True)
class SurfacePitch:
    """Pixel pitch of one projector on the target surface (m/px).

    ``mean`` is the arc span over the horizontal resolution. ``minimum`` and
    ``maximum`` are local pitches from neighbouring footprint samples along
    each image row, so keystone and curvature show up as a spread.
    """

    mean: float
    minimum: float
    maximum: float


def surface_pitch(footprint) -> SurfacePitch | None:
    """Mean and local pixel pitch of a sampled footprint, or ``None``.

    The footprint grid has ``grid`` samples per axis with the outer samples
    on the image edges, so neighbours in a row are ``res_x / (grid - 1)``
    pixels apart. Their 3D chord divided by that is the local pitch.
    """
    res_x = footprint.spec.resolution[0]
    if footprint.hit_ratio <= 0.0 or footprint.arc_span <= 0.0:
        return None
    n = footprint.grid
    step_px = res_x / (n - 1)
    local: list[float] = []
    for row in range(n):
        for col in range(n - 1):
            a = footprint.samples[row * n + col].hit
            b = footprint.samples[row * n + col + 1].hit
            if a is not None and b is not None:
                local.append(math.dist(a.point, b.point) / step_px)
    mean = footprint.arc_span / res_x
    if not local:
        return SurfacePitch(mean, mean, mean)
    return SurfacePitch(mean, min(local), max(local))


# ---------------------------------------------------------------------------
# Scenario calculator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioInputs:
    """Everything the Image & Pixel Calculator needs for one trial.

    Lengths in metres. Zero means "not set" for ``viewing_distance``,
    ``target_height`` and the lens limits; ``target_bottom`` is only checked
    when ``check_target`` is True (a screen may sit at floor level).
    """

    distance: float
    throw_ratio: float
    res_x: int
    res_y: int
    lens_height: float = 0.0
    lens_shift_v: float = 0.0
    lens_shift_h: float = 0.0
    check_target: bool = False
    target_bottom: float = 0.0
    target_height: float = 0.0
    viewing_distance: float = 0.0
    projector_count: int = 1
    overlap_fraction: float = 0.0
    throw_ratio_min: float = 0.0
    throw_ratio_max: float = 0.0
    max_lens_shift_v: float = 0.0
    max_lens_shift_h: float = 0.0


@dataclass(frozen=True)
class ScenarioResult:
    image: ImageSolution
    pitch: float
    pixels_per_metre: float
    extent: VerticalExtent
    canvas: Canvas
    pixels_per_degree: float = 0.0
    one_arcminute_distance: float = 0.0
    warnings: list[str] = field(default_factory=list)


def lens_range_warnings(inp: ScenarioInputs) -> list[str]:
    """Throw-ratio and shift checks against the lens limits in ``inp``.

    Uses :class:`~.throw.ProjectorSpec`'s own range tests so the calculator and
    the scene agree. A limit of 0 everywhere means no lens is selected and the
    shift check is skipped; it warns, never clamps (ADR 0002).
    """
    spec = ProjectorSpec(
        throw_ratio=inp.throw_ratio,
        lens_shift_v=inp.lens_shift_v,
        lens_shift_h=inp.lens_shift_h,
        max_lens_shift_v=inp.max_lens_shift_v,
        max_lens_shift_h=inp.max_lens_shift_h,
        throw_ratio_min=inp.throw_ratio_min,
        throw_ratio_max=inp.throw_ratio_max,
    )
    out: list[str] = []
    if not spec.throw_ratio_within_lens():
        out.append(
            f"Throw ratio {inp.throw_ratio:.3f}:1 is outside the lens range "
            f"{inp.throw_ratio_min:.3f}-{inp.throw_ratio_max:.3f}:1"
        )
    lens_known = inp.throw_ratio_min > 0.0 or inp.max_lens_shift_v > 0.0 or inp.max_lens_shift_h > 0.0
    if lens_known and not spec.lens_shift_within_limits():
        if abs(inp.lens_shift_v) > inp.max_lens_shift_v + 1e-9:
            out.append(
                f"Vertical shift {inp.lens_shift_v:+.3f} exceeds the lens limit "
                f"+/-{inp.max_lens_shift_v:.3f} (fraction of image height)"
            )
        if abs(inp.lens_shift_h) > inp.max_lens_shift_h + 1e-9:
            out.append(
                f"Horizontal shift {inp.lens_shift_h:+.3f} exceeds the lens limit "
                f"+/-{inp.max_lens_shift_h:.3f} (fraction of image width)"
            )
    return out


def evaluate_scenario(inp: ScenarioInputs) -> ScenarioResult:
    """All pixel and image numbers for one calculator scenario.

    The image aspect is the signal's, ``res_x / res_y``, filling the throw
    width ``distance / throw_ratio``.
    """
    image = solve_image(inp.res_x / inp.res_y, distance=inp.distance, throw_ratio=inp.throw_ratio)
    pitch = pixel_pitch(image.width, inp.res_x)
    extent = image_vertical_extent(inp.lens_height, image.height, inp.lens_shift_v)
    canvas = blended_canvas(
        inp.res_x,
        inp.res_y,
        inp.projector_count,
        overlap_fraction=inp.overlap_fraction,
        image_width=image.width,
    )
    warnings = lens_range_warnings(inp)
    if inp.check_target:
        warnings.extend(vertical_fit_warnings(extent, inp.target_bottom, inp.target_height))
    ppd = 0.0
    if inp.viewing_distance > 0.0:
        ppd = pixels_per_degree(pitch, inp.viewing_distance)
        if ppd < 60.0:
            warnings.append(
                f"Viewer at {fmt_mm(inp.viewing_distance)} sees {ppd:.0f} px/deg, under the "
                "60 px/deg 20/20 limit: pixel structure is visible"
            )
    return ScenarioResult(
        image=image,
        pitch=pitch,
        pixels_per_metre=1.0 / pitch,
        extent=extent,
        canvas=canvas,
        pixels_per_degree=ppd,
        one_arcminute_distance=one_arcminute_distance(pitch),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Millimetre text
# ---------------------------------------------------------------------------


def fmt_mm(metres: float) -> str:
    """Whole millimetres, e.g. ``"9158 mm"``."""
    return f"{metres * _MM:.0f} mm"


def fmt_pitch(metres_per_px: float) -> str:
    """Pixel pitch to 0.01 mm, e.g. ``"4.77 mm/px"``."""
    return f"{metres_per_px * _MM:.2f} mm/px"


def scenario_rows(inp: ScenarioInputs, res: ScenarioResult) -> list[tuple[str, str]]:
    """Label/value pairs shared by the compare table and the CSV export."""
    img = res.image
    rows = [
        ("Resolution", f"{inp.res_x} x {inp.res_y}"),
        ("Throw distance", fmt_mm(img.distance)),
        ("Throw ratio", f"{img.throw_ratio:.3f}:1"),
        ("Image W x H", f"{img.width * _MM:.0f} x {img.height * _MM:.0f} mm"),
        ("Diagonal", fmt_mm(img.diagonal)),
        ("Pixel pitch", fmt_pitch(res.pitch)),
        ("Density", f"{res.pixels_per_metre:.0f} px/m"),
        ("Lens height AFF", fmt_mm(inp.lens_height)),
        ("Vertical shift", f"{inp.lens_shift_v:+.3f}"),
        ("Image bottom AFF", fmt_mm(res.extent.bottom)),
        ("Image top AFF", fmt_mm(res.extent.top)),
        ("1-arcmin distance", fmt_mm(res.one_arcminute_distance)),
    ]
    if inp.viewing_distance > 0.0:
        rows.append(("Viewer distance", fmt_mm(inp.viewing_distance)))
        rows.append(("Pixels per degree", f"{res.pixels_per_degree:.1f}"))
    else:
        rows.append(("Viewer distance", "-"))
        rows.append(("Pixels per degree", "-"))
    c = res.canvas
    rows.extend(
        [
            ("Projectors", str(c.projectors)),
            ("Overlap", f"{inp.overlap_fraction * 100:.1f}%"),
            ("Canvas px", f"{c.pixels_x} x {c.pixels_y}"),
            ("Canvas width", fmt_mm(c.width)),
            ("Canvas px/mm", f"{c.pixels_per_metre / _MM:.3f}"),
            ("Warnings", "; ".join(res.warnings) or "none"),
        ]
    )
    return rows


def scenarios_to_csv(scenarios: Sequence[tuple[str, ScenarioInputs, ScenarioResult]]) -> str:
    """One CSV row per named scenario, columns from :func:`scenario_rows`."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for index, (name, inp, res) in enumerate(scenarios):
        rows = scenario_rows(inp, res)
        if index == 0:
            writer.writerow(["Scenario", *(label for label, _value in rows)])
        writer.writerow([name, *(value for _label, value in rows)])
    return buf.getvalue()
