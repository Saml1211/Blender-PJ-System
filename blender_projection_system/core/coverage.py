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
from .occlusion import RAY_TOLERANCE, OcclusionCaster
from .photometry import (
    ISCR_CATEGORY_LABELS,
    BlendModel,
    BrightnessReport,
    ContrastReport,
    DerateChain,
    ISCRCategory,
    assumptions_for_blend_model,
    blend_ramp_luminance_error,
    effective_contrast_ratio,
    illuminance_at,
    linear_ramp_weight,
    overlap_guidance,
    summarize_brightness,
    summarize_contrast,
)
from .surfaces import Surface
from .vectors import Vec3, distance, dot, normalize, sub

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


@dataclass
class ProjectorOcclusion:
    """Occlusion tally for one projector over the coverage raster.

    ``total_potential_cells`` counts the raster cells the projector's image
    covers before occlusion is considered; ``occluded_cells`` counts those
    whose line of sight is blocked. A projector absent from the report's
    :attr:`CoverageReport.projector_occlusions` was never occlusion-tested.
    """

    projector_name: str
    occluded_cells: int = 0
    total_potential_cells: int = 0

    @property
    def occluded_fraction(self) -> float:
        return (
            self.occluded_cells / self.total_potential_cells if self.total_potential_cells else 0.0
        )


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

    @property
    def mean_overlap_fraction(self) -> float:
        return 0.5 * (self.overlap_fraction_left + self.overlap_fraction_right)

    @property
    def guidance(self) -> str:
        return overlap_guidance(self.mean_overlap_fraction)


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
    contrast: ContrastReport | None = None
    blend_model: BlendModel = BlendModel.RAW
    blend_gamma: float = 1.0
    derate_chain: DerateChain | None = None
    """How overlapping illuminance was combined - see :class:`BlendModel`."""
    projector_occlusions: dict[str, ProjectorOcclusion] = field(default_factory=dict)
    """Per-projector occlusion tallies; empty when no occluders are in play."""
    occluded_cells: list[CoverageCell] = field(default_factory=list)
    """Cells where at least one covering projector's line of sight is blocked."""
    shadowed_cells: list[CoverageCell] = field(default_factory=list)
    """Cells whose every covering projector is blocked - counted as covered by
    geometry but dark in reality. Always a subset of :attr:`occluded_cells`."""
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


def _cell_centers(wall: Surface, grid_s: int, grid_z: int):
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
    wall: Surface,
    grid_s: int = DEFAULT_GRID_S,
    grid_z: int = DEFAULT_GRID_Z,
    screen_gain: float = 1.0,
    blend_model: BlendModel = BlendModel.RAW,
    occlusion_caster: OcclusionCaster | None = None,
    derate_chain: DerateChain | None = None,
    blend_gamma: float = 1.0,
    ambient_lux: float = 0.0,
    iscr_category: ISCRCategory = ISCRCategory.NONE,
    target_contrast_ratio: float = 0.0,
) -> CoverageReport:
    """Rasterised coverage, gap, overlap and brightness analysis for a wall.

    ``blend_model`` selects how overlapping projectors' light is combined:
    raw addition (:attr:`BlendModel.RAW`, the default) or the complementary
    linear ramps an edge-blending processor applies
    (:attr:`BlendModel.LINEAR_RAMP`). The ramp applies only where exactly two
    images overlap; triple overlaps stay additive because they are flagged as
    placement errors rather than blends.

    ``occlusion_caster`` optionally supplies line-of-sight checks (see
    :mod:`.occlusion`). When given, every projector-to-cell ray is tested:
    blocked rays contribute no light, affected cells are tallied per
    projector and listed in :attr:`CoverageReport.occluded_cells`, and cells
    left dark by occlusion are listed in :attr:`CoverageReport.shadowed_cells`
    and warned about loudly. With ``None`` (the default) nothing is occluded
    and the report is identical to the unoccluded analysis.
    """
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
        report.gaps = [Interval(0.0, wall.arc_length)]
        report.warnings.append("no projector footprint lands on the wall; coverage is zero")
        return report

    lux_grid: list[float] = []
    contrast_grid: list[float] = []
    uncovered_by_row: list[list[bool]] = [[False] * grid_s for _ in range(grid_z)]
    covered_z: list[float] = []
    occlusion_by: dict[str, ProjectorOcclusion] = (
        {fp.name: ProjectorOcclusion(projector_name=fp.name) for fp in usable}
        if occlusion_caster is not None
        else {}
    )

    for i_s, iz, s, z in _cell_centers(wall, grid_s, grid_z):
        point = wall.point_at(s, z)
        normal = wall.normal_at_s(s)
        contributions: list[tuple[Footprint, float]] = []
        potential = 0
        cell_occluded = False
        for fp in usable:
            # Back-project the cell through each lens rather than testing the
            # sampled outline: a footprint clipped by the wall edge has a
            # boundary polygon that closes across the missing samples.
            if not fp.covers(point):
                continue
            potential += 1
            if occlusion_caster is not None:
                tally = occlusion_by[fp.name]
                tally.total_potential_cells += 1
                direction = normalize(sub(point, fp.pose.origin))
                # Trim a tolerance off the reach so a caster built from the
                # target wall's own mesh never occludes its sample point.
                reach = max(0.0, distance(fp.pose.origin, point) - RAY_TOLERANCE)
                if occlusion_caster(fp.pose.origin, direction, reach):
                    tally.occluded_cells += 1
                    cell_occluded = True
                    continue
            contributions.append((fp, _cell_illuminance(fp, point, normal)))
        if cell_occluded:
            report.occluded_cells.append(
                CoverageCell(s - 0.5 * ds, s + 0.5 * ds, z - 0.5 * dz, z + 0.5 * dz)
            )
        if potential and not contributions:
            report.shadowed_cells.append(
                CoverageCell(s - 0.5 * ds, s + 0.5 * ds, z - 0.5 * dz, z + 0.5 * dz)
            )
        count = len(contributions)
        if count:
            lux = _combined_illuminance(contributions, s, wall, blend_model, blend_gamma)
            report.covered_cells += 1
            lux_grid.append(lux)
            covered_z.append(z)
            black_contributions = [
                (fp, lux_val / max(1.0, fp.spec.native_contrast))
                for fp, lux_val in contributions
            ]
            black_lux = _combined_illuminance(
                black_contributions, s, wall, blend_model, blend_gamma
            )
            contrast_grid.append(effective_contrast_ratio(lux, black_lux, ambient_lux))
        else:
            uncovered_by_row[iz][i_s] = True
        if count >= 2:
            report.overlap_cells += 1
        report.max_overlap_count = max(report.max_overlap_count, count)

    report.gaps = _gap_intervals(uncovered_by_row, ds, grid_s, grid_z)
    if covered_z:
        report.covered_z_min = min(covered_z) - dz * 0.5
        report.covered_z_max = max(covered_z) + dz * 0.5
    report.projector_spans = [(fp.name, Interval(fp.s_min, fp.s_max)) for fp in usable]
    report.projector_occlusions = occlusion_by
    report.blend_zones = compute_blend_zones(usable, wall=wall, grid_s=grid_s, grid_z=grid_z)

    if lux_grid:
        report.brightness = summarize_brightness(
            lux_grid,
            screen_gain,
            assumptions_for_blend_model(blend_model, blend_gamma, derate_chain),
            derate_chain=derate_chain,
        )
    if contrast_grid and (
        ambient_lux > 0.0 or iscr_category is not ISCRCategory.NONE or target_contrast_ratio > 0.0
    ):
        report.contrast = summarize_contrast(
            contrast_grid,
            ambient_lux,
            screen_gain,
            target_category=iscr_category,
            user_target_ratio=target_contrast_ratio,
        )
    report.blend_model = blend_model
    report.blend_gamma = blend_gamma
    report.derate_chain = derate_chain

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


def _combined_illuminance(
    contributions: list[tuple[Footprint, float]],
    s: float,
    wall: Surface,
    blend_model: BlendModel,
    blend_gamma: float = 1.0,
) -> float:
    """Combine per-projector illuminance for one wall cell.

    Raw addition everywhere except: exactly two overlapping images under
    :attr:`BlendModel.LINEAR_RAMP` or :attr:`BlendModel.GAMMA_RAMP` get the
    complementary processor ramps. Triple overlaps stay additive - they are
    flagged as placement errors, not blends.
    """
    if blend_model in (BlendModel.LINEAR_RAMP, BlendModel.GAMMA_RAMP) and len(contributions) == 2:
        gamma = 1.0 if blend_model is BlendModel.LINEAR_RAMP else blend_gamma
        blended = _ramp_weighted_pair(contributions, s, wall.arc_length, gamma=gamma)
        if blended is not None:
            return blended
    return sum(lux for _, lux in contributions)


def _ramp_weighted_pair(
    contributions: list[tuple[Footprint, float]],
    s: float,
    circumference: float,
    gamma: float = 1.0,
) -> float | None:
    """Ramp-weighted illuminance for an exactly-two-image cell.

    Returns ``None`` when the pair's arc spans do not actually intersect
    (e.g. vertically disjoint images), in which case the caller falls back
    to raw addition.
    """
    (a, lux_a), (b, lux_b) = contributions
    ia = Interval(a.s_min, a.s_max)
    ib = Interval(b.s_min, b.s_max)
    if circumference > 0.0:
        # Same seam handling as compute_blend_zones: pull b into a's frame.
        center_a = 0.5 * (ia.start + ia.end)
        center_b = 0.5 * (ib.start + ib.end)
        shift = round((center_b - center_a) / circumference) * circumference
        ib = Interval(ib.start + shift, ib.end + shift)
    common = ia.intersect(ib)
    if common is None or common.length <= 0.0:
        return None
    s_eval = (
        s + round((0.5 * (common.start + common.end) - s) / circumference) * circumference
        if circumference > 0.0
        else s
    )
    w_l = linear_ramp_weight(s_eval, common.start, common.end, side="left", gamma=gamma)
    w_r = linear_ramp_weight(s_eval, common.start, common.end, side="right", gamma=gamma)
    a_on_left = 0.5 * (ia.start + ia.end) <= 0.5 * (ib.start + ib.end)
    return (w_l * lux_a + w_r * lux_b) if a_on_left else (w_r * lux_a + w_l * lux_b)


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
    fully_dark = [all(uncovered[iz][i_s] for iz in range(grid_z)) for i_s in range(grid_s)]
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
    wall: Surface | None = None,
    grid_s: int = DEFAULT_GRID_S,
    grid_z: int = DEFAULT_GRID_Z,
) -> list[BlendZone]:
    """Horizontal overlap between arc-adjacent projector pairs.

    When a wall is supplied, overlap is raster-tested in both wall dimensions
    so horizontally aligned but vertically disjoint images are not called a
    blend. The no-wall form remains a quick extent-only helper.
    """
    circumference = 0.0
    if wall is None:
        full_circle = False
        ordered = sorted(footprints, key=lambda f: (f.s_min + f.s_max) * 0.5)
        pairs = list(zip(ordered, ordered[1:], strict=False))
    else:
        full_circle = wall.wraps_around
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
                    s
                    + round((0.5 * (common.start + common.end) - s) / circumference) * circumference
                    if full_circle
                    else s
                )
                if not common.start <= s_eval <= common.end:
                    continue
                for iz in range(grid_z):
                    z = (iz + 0.5) * dz
                    point = wall.point_at(s_eval, z)
                    if a.covers(point) and b.covers(point):
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
                    cells_by_column[column][0].s_start - cells_by_column[previous][0].s_start
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
    occluded = [o for o in report.projector_occlusions.values() if o.occluded_cells > 0]
    for occ in occluded:
        out.append(
            f"{occ.projector_name}: {occ.occluded_cells} of {occ.total_potential_cells} "
            f"image cells ({occ.occluded_fraction * 100:.1f}%) are occluded by an "
            "obstacle - those cells get no light from it"
        )
    if report.contrast is not None:
        c = report.contrast
        if c.user_target_ratio > 0.0 and c.meets_user_target is False:
            out.append(
                f"worst-case effective contrast {c.min_contrast:.1f}:1 fails user target "
                f"{c.user_target_ratio:.1f}:1 under {c.ambient_lux:.0f} lux ambient illuminance"
            )
        elif c.min_contrast < 5.0 and c.ambient_lux > 0.0:
            out.append(
                f"worst-case effective contrast {c.min_contrast:.1f}:1 is very low; "
                f"image will appear washed out under {c.ambient_lux:.0f} lux ambient light"
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
        lines.append(
            f"  {name}: arc {span.start:.2f} - {span.end:.2f} m ({span.length:.2f} m wide)"
        )
    for zone in report.blend_zones:
        lines.append(
            f"  blend {zone.left} | {zone.right}: {zone.width:.2f} m "
            f"({zone.overlap_fraction_left * 100:.0f}% / "
            f"{zone.overlap_fraction_right * 100:.0f}% of image width) - "
            f"{zone.guidance}"
        )
    for gap in report.gaps:
        lines.append(f"  GAP: arc {gap.start:.2f} - {gap.end:.2f} m ({gap.length:.2f} m)")
    occluded = [o for o in report.projector_occlusions.values() if o.occluded_cells > 0]
    if occluded:
        lines.append(f"Occlusion: {len(report.occluded_cells)} cell(s) shadowed by obstacles")
        for occ in occluded:
            lines.append(
                f"  {occ.projector_name}: {occ.occluded_cells}/{occ.total_potential_cells} "
                f"of its image cells ({occ.occluded_fraction * 100:.1f}%) occluded"
            )
    if report.brightness:
        b = report.brightness
        lines.append(
            f"Brightness: mean {b.mean_nits:.0f} nits "
            f"({b.mean_foot_lamberts:.1f} fL), range {b.min_nits:.0f}-{b.max_nits:.0f} nits, "
            f"uniformity {b.uniformity:.2f}"
        )
        if b.rated_band and b.typical_band and b.worst_case_band:
            lines.append(
                f"  Bands (rated / typical / worst-case): "
                f"{b.rated_band.mean_nits:.0f} / {b.typical_band.mean_nits:.0f} / {b.worst_case_band.mean_nits:.0f} nits "
                f"({b.rated_band.mean_lux:.0f} / {b.typical_band.mean_lux:.0f} / {b.worst_case_band.mean_lux:.0f} lux)"
            )
    if report.blend_model is BlendModel.LINEAR_RAMP:
        lines.append("Overlap luminance uses a linear-ramp blend model; see brightness assumptions")
    elif report.blend_model is BlendModel.GAMMA_RAMP:
        err = blend_ramp_luminance_error(report.blend_gamma)
        lines.append(
            f"Overlap luminance uses a gamma-ramp blend model (gamma={report.blend_gamma:.2f}, "
            f"theoretical mid-zone error {err * 100:+.1f}%); see brightness assumptions"
        )
    if report.contrast:
        c = report.contrast
        cat_suffix = (
            f" [target: {ISCR_CATEGORY_LABELS.get(c.target_category, '')}]"
            if c.target_category is not ISCRCategory.NONE
            else ""
        )
        lines.append(
            f"Effective contrast{cat_suffix}: mean {c.mean_contrast:.1f}:1, "
            f"min/worst {c.min_contrast:.1f}:1 (ambient {c.ambient_lux:.1f} lux, "
            f"veiling {c.veiling_nits:.1f} nits)"
        )
        if c.user_target_ratio > 0.0:
            verdict = "PASS" if c.meets_user_target else "FAIL"
            lines.append(
                f"  Target ratio {c.user_target_ratio:.1f}:1: {verdict} "
                f"(worst-case {c.min_contrast:.1f}:1)"
            )
        lines.append(f"  Disclaimer: {c.disclaimer}")
    return lines
