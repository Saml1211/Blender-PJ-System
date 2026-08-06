"""Multi-projector coverage, gap and blend-zone analysis.

The wall is rasterised into a grid in ``(s, z)`` wall coordinates. Each cell
is tested against every projector's footprint polygon, giving an honest
per-cell count of how many projectors light it. Gaps are cells lit by nobody,
blend zones are cells lit by two or more.

Illuminance is accumulated per cell from the real geometry (distance and
incidence angle from each projector to that cell), under the assumptions
documented in :mod:`.photometry`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from .errors import ProjectionError
from .footprint import Footprint
from .photometry import BrightnessReport, illuminance_at, summarize_brightness
from .surfaces import CylindricalWall
from .vectors import Vec3, dot, normalize, sub

DEFAULT_GRID_S = 80
DEFAULT_GRID_Z = 24


@dataclass(frozen=True)
class Interval:
    start: float
    end: float

    @property
    def length(self) -> float:
        return max(0.0, self.end - self.start)

    def intersect(self, other: Interval) -> Interval | None:
        lo = max(self.start, other.start)
        hi = min(self.end, other.end)
        return Interval(lo, hi) if hi > lo else None


@dataclass(frozen=True)
class CoverageCell:
    """One sampled wall cell, expressed in wall ``(s, z)`` coordinates."""

    s_start: float
    s_end: float
    z_start: float
    z_end: float


@dataclass(frozen=True)
class BlendZone:
    """Horizontal overlap between two projectors, measured along the wall arc."""

    left: str
    right: str
    interval: Interval
    overlap_fraction_left: float
    """Overlap width as a fraction of the left projector's own arc span."""
    overlap_fraction_right: float
    cells: tuple[CoverageCell, ...] = ()
    """Sampled cells where both images actually land on the wall."""

    @property
    def width(self) -> float:
        return self.interval.length


@dataclass
class CoverageReport:
    wall_name: str
    wall_arc_length: float
    wall_height: float
    grid_s: int
    grid_z: int
    cell_area: float

    covered_cells: int = 0
    total_cells: int = 0
    overlap_cells: int = 0
    max_overlap_count: int = 0

    gaps: list[Interval] = field(default_factory=list)
    """Arc ranges that are dark at *every* height - true vertical dark bands.

    Kept separate from :attr:`covered_z_min` / :attr:`covered_z_max`, because a
    16:9 image on a taller wall leaves unlit strips top and bottom that are a
    normal design outcome, not a hole between projectors.
    """
    covered_z_min: float = 0.0
    covered_z_max: float = 0.0
    blend_zones: list[BlendZone] = field(default_factory=list)
    projector_spans: list[tuple[str, Interval]] = field(default_factory=list)
    brightness: BrightnessReport | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def covered_fraction(self) -> float:
        return self.covered_cells / self.total_cells if self.total_cells else 0.0

    @property
    def gap_fraction(self) -> float:
        return 1.0 - self.covered_fraction

    @property
    def overlap_fraction(self) -> float:
        return self.overlap_cells / self.total_cells if self.total_cells else 0.0

    @property
    def covered_area(self) -> float:
        return self.covered_cells * self.cell_area

    @property
    def gap_area(self) -> float:
        return (self.total_cells - self.covered_cells) * self.cell_area

    @property
    def covered_height(self) -> float:
        return max(0.0, self.covered_z_max - self.covered_z_min)

    @property
    def horizontal_coverage(self) -> float:
        """Fraction of the arc lit at *some* height.

        This is the number to look at when asking "is the wall covered
        left-to-right"; :attr:`covered_fraction` also penalises the unlit
        strips above and below a shorter-than-the-wall image.
        """
        gap_total = sum(g.length for g in self.gaps)
        if self.wall_arc_length <= 0.0:
            return 0.0
        return max(0.0, 1.0 - gap_total / self.wall_arc_length)


def _cell_centers(wall: CylindricalWall, grid_s: int, grid_z: int):
    if grid_s < 1 or grid_z < 1:
        raise ProjectionError("coverage grid dimensions must be at least 1")
    ds = wall.arc_length / grid_s
    dz = wall.height / grid_z
    for iz in range(grid_z):
        z = (iz + 0.5) * dz
        for i_s in range(grid_s):
            s = (i_s + 0.5) * ds
            yield i_s, iz, s, z


def analyze_coverage(
    footprints: Sequence[Footprint],
    wall: CylindricalWall,
    grid_s: int = DEFAULT_GRID_S,
    grid_z: int = DEFAULT_GRID_Z,
    screen_gain: float = 1.0,
) -> CoverageReport:
    """Rasterised coverage, gap, overlap and brightness analysis for a wall."""
    if grid_s < 1 or grid_z < 1:
        raise ProjectionError("coverage grid dimensions must be at least 1")
    ds = wall.arc_length / grid_s
    dz = wall.height / grid_z
    report = CoverageReport(
        wall_name=wall.name,
        wall_arc_length=wall.arc_length,
        wall_height=wall.height,
        grid_s=grid_s,
        grid_z=grid_z,
        cell_area=ds * dz,
        total_cells=grid_s * grid_z,
    )

    usable = [fp for fp in footprints if fp.hit_ratio > 0.0]
    if not usable:
        report.warnings.append(
            "no projector footprint lands on the wall; coverage is zero"
        )
        return report

    lux_grid: list[float] = []
    uncovered_by_row: list[list[bool]] = [[False] * grid_s for _ in range(grid_z)]
    covered_z: list[float] = []

    for i_s, iz, s, z in _cell_centers(wall, grid_s, grid_z):
        point = wall.point_at(s, z)
        normal = wall.normal_at_s(s)
        count = 0
        lux = 0.0
        for fp in usable:
            # Back-project the cell through each lens rather than testing the
            # sampled outline: a footprint clipped by the wall edge has a
            # boundary polygon that closes across the missing samples.
            if not fp.covers(point):
                continue
            count += 1
            lux += _cell_illuminance(fp, point, normal)
        if count:
            report.covered_cells += 1
            lux_grid.append(lux)
            covered_z.append(z)
        else:
            uncovered_by_row[iz][i_s] = True
        if count >= 2:
            report.overlap_cells += 1
        report.max_overlap_count = max(report.max_overlap_count, count)

    report.gaps = _gap_intervals(uncovered_by_row, ds, grid_s, grid_z)
    if covered_z:
        report.covered_z_min = min(covered_z) - dz * 0.5
        report.covered_z_max = max(covered_z) + dz * 0.5
    report.projector_spans = [
        (fp.name, Interval(fp.s_min, fp.s_max)) for fp in usable
    ]
    report.blend_zones = compute_blend_zones(
        usable, wall=wall, grid_s=grid_s, grid_z=grid_z
    )

    if lux_grid:
        report.brightness = summarize_brightness(lux_grid, screen_gain)

    report.warnings.extend(_coverage_warnings(report))
    return report


def _cell_illuminance(fp: Footprint, point: Vec3, normal: Vec3) -> float:
    """Illuminance a single projector delivers to one wall cell."""
    to_lens = sub(fp.pose.origin, point)
    d = math.sqrt(dot(to_lens, to_lens))
    if d < 1e-9:
        return 0.0
    incidence = math.acos(max(-1.0, min(1.0, dot(normalize(to_lens), normal))))
    return illuminance_at(fp.spec, d, incidence)


def _gap_intervals(
    uncovered: list[list[bool]],
    ds: float,
    grid_s: int,
    grid_z: int,
) -> list[Interval]:
    """Arc ranges dark at *every* sampled height, merged into intervals.

    Using "every" rather than "any" is deliberate: an image that is shorter
    than the wall leaves unlit strips at the top and bottom of every column,
    and calling those a gap would mark a perfectly good design as failing.
    """
    fully_dark = [
        all(uncovered[iz][i_s] for iz in range(grid_z)) for i_s in range(grid_s)
    ]
    out: list[Interval] = []
    run_start: int | None = None
    for i in range(grid_s):
        if fully_dark[i] and run_start is None:
            run_start = i
        elif not fully_dark[i] and run_start is not None:
            out.append(Interval(run_start * ds, i * ds))
            run_start = None
    if run_start is not None:
        out.append(Interval(run_start * ds, grid_s * ds))
    return out


def compute_blend_zones(
    footprints: Sequence[Footprint],
    wall: CylindricalWall | None = None,
    grid_s: int = DEFAULT_GRID_S,
    grid_z: int = DEFAULT_GRID_Z,
) -> list[BlendZone]:
    """Horizontal overlap between arc-adjacent projector pairs.

    When a wall is supplied, overlap is raster-tested in both wall dimensions
    so horizontally aligned but vertically disjoint images are not called a
    blend. The no-wall form remains a quick extent-only helper.
    """
    full_circle = wall is not None and wall.sweep >= 2.0 * math.pi - 1e-9
    if full_circle:
        circumference = wall.arc_length
        ordered = sorted(
            footprints,
            key=lambda f: ((f.s_min + f.s_max) * 0.5) % circumference,
        )
        pairs = list(zip(ordered, ordered[1:], strict=False))
        if len(ordered) > 2:
            pairs.append((ordered[-1], ordered[0]))
    else:
        circumference = 0.0
        ordered = sorted(footprints, key=lambda f: (f.s_min + f.s_max) * 0.5)
        pairs = list(zip(ordered, ordered[1:], strict=False))
    zones: list[BlendZone] = []
    for a, b in pairs:
        ia = Interval(a.s_min, a.s_max)
        ib = Interval(b.s_min, b.s_max)
        if full_circle:
            center_a = 0.5 * (ia.start + ia.end)
            center_b = 0.5 * (ib.start + ib.end)
            shift = round((center_a - center_b) / circumference) * circumference
            ib = Interval(ib.start + shift, ib.end + shift)
        common = ia.intersect(ib)
        if common is None or common.length <= 0.0:
            continue
        interval_cells: list[tuple[Interval, tuple[CoverageCell, ...]]] = [(common, ())]
        if wall is not None:
            if grid_s < 1 or grid_z < 1:
                raise ProjectionError("coverage grid dimensions must be at least 1")
            ds = wall.arc_length / grid_s
            dz = wall.height / grid_z
            cells_by_column: dict[int, list[CoverageCell]] = {}
            for i_s in range(grid_s):
                s = (i_s + 0.5) * ds
                s_eval = (
                    s + round((0.5 * (common.start + common.end) - s) / circumference) * circumference
                    if full_circle
                    else s
                )
                if not common.start <= s_eval <= common.end:
                    continue
                for iz in range(grid_z):
                    z = (iz + 0.5) * dz
                    if a.covers(wall.point_at(s_eval, z)) and b.covers(wall.point_at(s_eval, z)):
                        cells_by_column.setdefault(i_s, []).append(
                            CoverageCell(
                                s_eval - 0.5 * ds,
                                s_eval + 0.5 * ds,
                                iz * dz,
                                (iz + 1) * dz,
                            )
                        )
            columns = sorted(
                cells_by_column,
                key=lambda column: cells_by_column[column][0].s_start,
            )
            intervals: list[Interval] = []
            run_start: int | None = None
            previous: int | None = None
            for column in columns:
                if run_start is None:
                    run_start = column
                elif previous is not None and (
                    cells_by_column[column][0].s_start
                    - cells_by_column[previous][0].s_start
                    > ds * 1.5
                ):
                    start_s = min(cell.s_start for cell in cells_by_column[run_start])
                    end_s = max(cell.s_end for cell in cells_by_column[previous])
                    intervals.append(Interval(start_s, end_s))
                    run_start = column
                previous = column
            if run_start is not None and previous is not None:
                start_s = min(cell.s_start for cell in cells_by_column[run_start])
                end_s = max(cell.s_end for cell in cells_by_column[previous])
                intervals.append(Interval(start_s, end_s))
            interval_cells = [
                (
                    interval,
                    tuple(
                        cell
                        for column, column_cells in cells_by_column.items()
                        if any(
                            interval.start <= cell.s_start + 0.5 * ds <= interval.end
                            for cell in column_cells
                        )
                        for cell in column_cells
                    ),
                )
                for interval in intervals
            ]
        for interval, cells in interval_cells:
            zones.append(
                BlendZone(
                    left=a.name,
                    right=b.name,
                    interval=interval,
                    overlap_fraction_left=interval.length / ia.length if ia.length else 0.0,
                    overlap_fraction_right=interval.length / ib.length if ib.length else 0.0,
                    cells=cells,
                )
            )
    return zones


def _coverage_warnings(report: CoverageReport) -> list[str]:
    out: list[str] = []
    if report.gaps:
        worst = max(report.gaps, key=lambda g: g.length)
        out.append(
            f"{len(report.gaps)} dark band(s) on '{report.wall_name}'; "
            f"largest runs {worst.start:.2f} m to {worst.end:.2f} m along the arc "
            f"({worst.length:.2f} m wide)"
        )
    unlit_below = report.covered_z_min
    unlit_above = report.wall_height - report.covered_z_max
    if report.covered_cells and unlit_below + unlit_above > 0.05:
        out.append(
            f"image band covers {report.covered_z_min:.2f}-{report.covered_z_max:.2f} m "
            f"of a {report.wall_height:.2f} m wall ({unlit_below:.2f} m unlit below, "
            f"{unlit_above:.2f} m above). Expected for a fixed aspect ratio - use a "
            "taller stack or accept the letterbox."
        )
    if report.max_overlap_count > 2:
        out.append(
            f"up to {report.max_overlap_count} projectors light the same area; "
            "triple overlap is usually a placement error, not a blend"
        )
    for zone in report.blend_zones:
        frac = max(zone.overlap_fraction_left, zone.overlap_fraction_right)
        if frac < 0.05:
            out.append(
                f"blend between {zone.left} and {zone.right} is only "
                f"{zone.width * 1000:.0f} mm ({frac * 100:.1f}% of image width); "
                "too narrow to blend reliably"
            )
        elif frac > 0.5:
            out.append(
                f"blend between {zone.left} and {zone.right} consumes "
                f"{frac * 100:.0f}% of the image width; you are paying for pixels "
                "you cannot use"
            )
    return out


def format_report(report: CoverageReport) -> list[str]:
    """Flat list of display lines, used by the Blender panel and the CLI."""
    lines = [
        f"Wall '{report.wall_name}': {report.wall_arc_length:.2f} m arc "
        f"x {report.wall_height:.2f} m high ({report.wall_arc_length * report.wall_height:.1f} m2)",
        f"Coverage: {report.covered_fraction * 100:.1f}% of wall area "
        f"({report.covered_area:.1f} m2 lit, {report.gap_area:.1f} m2 dark)",
        f"Horizontal coverage: {report.horizontal_coverage * 100:.1f}% of the arc; "
        f"lit band {report.covered_z_min:.2f}-{report.covered_z_max:.2f} m high",
        f"Overlap: {report.overlap_fraction * 100:.1f}% of the wall, "
        f"max {report.max_overlap_count} projector(s) on one spot",
    ]
    for name, span in report.projector_spans:
        lines.append(f"  {name}: arc {span.start:.2f} - {span.end:.2f} m ({span.length:.2f} m wide)")
    for zone in report.blend_zones:
        lines.append(
            f"  blend {zone.left} | {zone.right}: {zone.width:.2f} m "
            f"({zone.overlap_fraction_left * 100:.0f}% / "
            f"{zone.overlap_fraction_right * 100:.0f}% of image width)"
        )
    for gap in report.gaps:
        lines.append(f"  GAP: arc {gap.start:.2f} - {gap.end:.2f} m ({gap.length:.2f} m)")
    if report.brightness:
        b = report.brightness
        lines.append(
            f"Brightness: mean {b.mean_nits:.0f} nits "
            f"({b.mean_foot_lamberts:.1f} fL), range {b.min_nits:.0f}-{b.max_nits:.0f} nits, "
            f"uniformity {b.uniformity:.2f}"
        )
    return lines
