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
    ray_direction_local,
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


@dataclass(frozen=True)
class RasterOnTarget:
    """Where one projector's real pixel raster lands on the target.

    Built by casting individual pixels, not the coarse footprint grid:
    ``rows_on_target`` counts the image rows of one column (the centre column
    when it reaches the target) that hit the wall, and ``column_s`` is the arc
    position of every column on the row through the middle of those rows,
    ``None`` where that column misses. For a level projector every column is a
    vertical plane, so one row describes the horizontal raster at all heights.
    """

    name: str
    res_x: int
    res_y: int
    rows_on_target: int
    row_v: float
    column_s: tuple[float | None, ...]

    @property
    def hits(self) -> list[float]:
        return [s for s in self.column_s if s is not None]

    @property
    def columns_on_target(self) -> int:
        return len(self.hits)


def _pixel_hit(footprint, u: float, v: float):
    direction = footprint.pose.local_to_world_dir(ray_direction_local(u, v, footprint.spec))
    return footprint.wall.intersect_ray(footprint.pose.origin, direction)


def raster_on_target(footprint) -> RasterOnTarget | None:
    """Cast one column and one row of real pixels onto the footprint's wall.

    Pixel ``(i, j)`` sits at ``u = (i + 0.5) / res_x - 0.5`` and
    ``v = 0.5 - (j + 0.5) / res_y``. The column is the image centre column;
    if it misses the wall entirely, the column of the footprint sample
    nearest the centre that hit is used. ``None`` when nothing lands.
    Cached on the footprint, which is rebuilt whenever the scene changes.
    """
    cached = getattr(footprint, "_raster_on_target", None)
    if cached is not None:
        return cached
    if footprint.hit_ratio <= 0.0:
        return None
    res_x, res_y = footprint.spec.resolution
    row_vs = [0.5 - (j + 0.5) / res_y for j in range(res_y)]
    candidates = [0.0] + [
        sample.u
        for sample in sorted(footprint.samples, key=lambda smp: (abs(smp.u), abs(smp.v)))
        if sample.hit is not None
    ]
    rows: list[float] = []
    for u in candidates:
        rows = [v for v in row_vs if _pixel_hit(footprint, u, v) is not None]
        if rows:
            break
    if not rows:
        return None
    row_v = rows[len(rows) // 2]
    column_s: list[float | None] = []
    for i in range(res_x):
        hit = _pixel_hit(footprint, (i + 0.5) / res_x - 0.5, row_v)
        column_s.append(hit.s if hit is not None else None)
    if footprint.wall.wraps_around:
        column_s = _unwrap(column_s, footprint.wall.arc_length)
    raster = RasterOnTarget(footprint.name, res_x, res_y, len(rows), row_v, tuple(column_s))
    footprint._raster_on_target = raster
    return raster


def _unwrap(values: list[float | None], circumference: float) -> list[float | None]:
    """Make arc positions continuous across the seam of a full-circle wall."""
    out: list[float | None] = []
    previous: float | None = None
    offset = 0.0
    for value in values:
        if value is None:
            out.append(None)
            continue
        if previous is not None:
            jump = value + offset - previous
            offset -= round(jump / circumference) * circumference
        out.append(value + offset)
        previous = value + offset
    return out


def array_canvas(footprints: Sequence, blend_zones: Sequence) -> Canvas | None:
    """Blended canvas of the projectors on a wall, counted in real pixels.

    * ``pixels_x``: columns on the target summed over the array, less each
      blend: for every neighbouring pair in ``blend_zones`` the overlap is the
      shared stretch of their column hits on the target, and the blend removes
      the mean of the two images' column counts inside it.
    * ``pixels_y``: the fewest image rows on the target along any projector's
      centre column (see :func:`raster_on_target`), so vertical spill onto
      the floor or ceiling is not counted.
    * ``width``: lit arc, the summed column spans less the overlaps, never more
      than the wall's arc length.

    ``blend_zones`` supplies adjacency only. ``None`` when nothing lands.
    """
    rasters = {}
    for fp in footprints:
        raster = raster_on_target(fp)
        if raster is not None and raster.hits:
            rasters[fp.name] = (fp, raster)
    if not rasters:
        return None
    overlap_px = 0
    overlap_len = 0.0
    seen: set[frozenset[str]] = set()
    for zone in blend_zones:
        key = frozenset((zone.left, zone.right))
        if zone.left not in rasters or zone.right not in rasters or key in seen:
            continue
        seen.add(key)
        fp_a, a = rasters[zone.left]
        _fp_b, b = rasters[zone.right]
        sa, sb = a.hits, b.hits
        if fp_a.wall.wraps_around:
            circumference = fp_a.wall.arc_length
            centre_a = 0.5 * (min(sa) + max(sa))
            centre_b = 0.5 * (min(sb) + max(sb))
            shift = round((centre_a - centre_b) / circumference) * circumference
            sb = [x + shift for x in sb]
        lo, hi = max(min(sa), min(sb)), min(max(sa), max(sb))
        if hi <= lo:
            continue
        inside = [sum(1 for x in hits if lo <= x <= hi) for hits in (sa, sb)]
        overlap_px += round(0.5 * (inside[0] + inside[1]))
        overlap_len += hi - lo
    pixels_x = sum(r.columns_on_target for _fp, r in rasters.values()) - overlap_px
    span = sum(max(r.hits) - min(r.hits) for _fp, r in rasters.values()) - overlap_len
    wall_arc = next(iter(rasters.values()))[0].wall.arc_length
    return Canvas(
        len(rasters),
        pixels_x,
        min(r.rows_on_target for _fp, r in rasters.values()),
        overlap_px,
        min(max(span, 0.0), wall_arc),
    )


@dataclass(frozen=True)
class SurfacePitch:
    """Horizontal pixel pitch of one projector on the target surface (m/px).

    From the per-pixel row of :func:`raster_on_target`: ``mean`` is the arc
    the on-target columns cover divided by their count, ``minimum`` and
    ``maximum`` the narrowest and widest single pixel along that row, so
    keystone and curvature show up as a spread.
    """

    mean: float
    minimum: float
    maximum: float


def surface_pitch(footprint) -> SurfacePitch | None:
    """Mean and local pixel pitch on the target, or ``None`` if nothing lands."""
    raster = raster_on_target(footprint)
    if raster is None or raster.columns_on_target < 2:
        return None
    steps: list[float] = []
    previous: float | None = None
    for s_value in raster.column_s:
        if s_value is not None and previous is not None:
            steps.append(abs(s_value - previous))
        previous = s_value
    hits = raster.hits
    mean = (max(hits) - min(hits)) / (len(hits) - 1)
    if not steps:
        return SurfacePitch(mean, mean, mean)
    return SurfacePitch(mean, min(steps), max(steps))


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


def fmt_size(width: float, height: float) -> str:
    """Width by height in whole millimetres, e.g. ``"9158 x 5724 mm"``."""
    return f"{width * _MM:.0f} x {height * _MM:.0f} mm"


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
        ("Image W x H", fmt_size(img.width, img.height)),
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
