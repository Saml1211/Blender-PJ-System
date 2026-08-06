"""Planning a ceiling-mounted projector array across a curved wall.

The planner works backwards from the wall: decide how much arc each projector
must cover given the requested overlap, then solve for the standoff distance
that actually produces that arc width when the frustum is ray-cast onto the
curved surface. The solve is numerical because a planar image landing on a
cylinder does not map to a closed-form arc width.

Two mounting modes are supported:

``LEVEL``
    The optical axis is kept horizontal and vertical lens shift moves the image
    down onto the wall. This is the preferred install: no keystone, no
    correction, and focus stays even. It fails when the required shift exceeds
    the lens.

``TILT``
    The projector is tilted to aim straight at the target point. Always
    geometrically possible, but introduces keystone that must be corrected
    electronically (losing pixels) and widens the focus spread.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from .errors import ProjectionError, require_positive
from .footprint import DEFAULT_SAMPLES, Footprint, compute_footprint
from .pose import Pose, level_pose, look_at
from .surfaces import CylindricalWall
from .throw import ProjectorSpec, image_size, required_lens_shift_v
from .vectors import Vec3, add, scale

MODE_LEVEL = "LEVEL"
MODE_TILT = "TILT"
MOUNT_MODES = (MODE_LEVEL, MODE_TILT)

#: Iteration limits for the standoff-distance solve.
SOLVE_MAX_ITERATIONS = 24
SOLVE_TOLERANCE = 1e-3  # metres of arc width


@dataclass
class ProjectorPlacement:
    """One planned projector: where it hangs, where it aims, and what it makes."""

    name: str
    index: int
    position: Vec3
    aim_point: Vec3
    pose: Pose
    spec: ProjectorSpec
    throw_distance: float
    image_width: float
    image_height: float
    arc_center: float
    arc_span: float
    horizontal_standoff: float
    """Horizontal distance from the wall surface to the lens, in metres."""
    drop_below_mount: float
    """How far the image centre sits below the mount height, in metres."""
    mode: str
    footprint: Footprint | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def lens_shift_v(self) -> float:
        return self.spec.lens_shift_v

    @property
    def tilt_deg(self) -> float:
        return self.pose.tilt_deg


@dataclass
class ArrayPlan:
    wall: CylindricalWall
    placements: list[ProjectorPlacement]
    target_arc_width: float
    overlap_fraction: float
    mode: str
    mount_height: float
    warnings: list[str] = field(default_factory=list)

    @property
    def footprints(self) -> list[Footprint]:
        return [p.footprint for p in self.placements if p.footprint is not None]


def arc_width_per_projector(
    arc_length: float,
    count: int,
    overlap_fraction: float,
) -> float:
    """Arc each projector must cover so ``count`` of them tile the wall.

    With overlap fraction ``f``, neighbours share ``f`` of one image width, so
    ``arc_length = count * w - (count - 1) * f * w``.
    """
    require_positive("wall arc length", arc_length)
    if count < 1:
        raise ProjectionError(f"projector count must be at least 1, got {count}")
    if not 0.0 <= overlap_fraction < 1.0:
        raise ProjectionError(
            f"overlap fraction must be in [0, 1), got {overlap_fraction}"
        )
    denom = count - (count - 1) * overlap_fraction
    if denom <= 0.0:
        raise ProjectionError("overlap fraction is too large for this projector count")
    return arc_length / denom


def arc_centers(
    arc_length: float,
    count: int,
    overlap_fraction: float,
) -> list[float]:
    """Arc-length position of each projector's image centre."""
    width = arc_width_per_projector(arc_length, count, overlap_fraction)
    step = width * (1.0 - overlap_fraction)
    return [width * 0.5 + i * step for i in range(count)]


def _measurement_wall(wall: CylindricalWall) -> CylindricalWall:
    """A deliberately oversized copy of the wall, used only while solving.

    Edge projectors aim at the very end of the arc, so their image would be
    clipped by the real wall bounds and the measured span would be wrong. The
    solve runs against this extended surface and the final footprint is then
    evaluated against the real wall.
    """
    pad_angle = min(math.pi * 0.5, wall.sweep * 0.75 + 0.35)
    start = wall.angle_start - pad_angle
    end = wall.angle_end + pad_angle
    if end - start > 2.0 * math.pi:
        mid = 0.5 * (wall.angle_start + wall.angle_end)
        start, end = mid - math.pi + 1e-6, mid + math.pi - 1e-6
    pad_h = wall.height * 2.0
    return replace(
        wall,
        base_center=(wall.base_center[0], wall.base_center[1], wall.base_center[2] - pad_h),
        height=wall.height + 2.0 * pad_h,
        angle_start=start,
        angle_end=end,
        name=wall.name + "(solve)",
    )


def _build_pose_and_spec(
    wall: CylindricalWall,
    base_spec: ProjectorSpec,
    arc_center: float,
    target_z: float,
    mount_height: float,
    mode: str,
    axis_distance: float,
) -> tuple[Pose, ProjectorSpec, Vec3, Vec3, float, float]:
    """Place one projector at ``axis_distance`` along its optical axis.

    Returns ``(pose, spec, position, aim_point, horizontal_standoff, drop)``.
    """
    aim_point = wall.point_at(arc_center, target_z)
    inward = wall.normal_at_s(arc_center)  # concave wall: points at the axis
    drop = mount_height - aim_point[2]

    if mode == MODE_LEVEL:
        horizontal = axis_distance
        position = add(add(aim_point, scale(inward, horizontal)), (0.0, 0.0, drop))
        pose = level_pose(position, scale(inward, -1.0))
        size = image_size(axis_distance, base_spec)
        shift_v = required_lens_shift_v(-drop, size.height)
        spec = replace(base_spec, lens_shift_v=shift_v)
    elif mode == MODE_TILT:
        if axis_distance <= abs(drop) + 1e-6:
            raise ProjectionError(
                f"throw distance {axis_distance:.3f} m is shorter than the "
                f"{abs(drop):.3f} m vertical drop from the mount to the image centre; "
                "the projector cannot physically reach that image size from this height"
            )
        horizontal = math.sqrt(axis_distance * axis_distance - drop * drop)
        position = add(add(aim_point, scale(inward, horizontal)), (0.0, 0.0, drop))
        pose = look_at(position, aim_point)
        spec = replace(base_spec, lens_shift_v=0.0)
    else:
        raise ProjectionError(f"unknown mount mode {mode!r}; expected one of {MOUNT_MODES}")

    return pose, spec, position, aim_point, horizontal, drop


def solve_standoff(
    wall: CylindricalWall,
    base_spec: ProjectorSpec,
    arc_center: float,
    target_z: float,
    mount_height: float,
    target_arc_width: float,
    mode: str = MODE_LEVEL,
    samples: int = DEFAULT_SAMPLES,
) -> tuple[float, Pose, ProjectorSpec, float]:
    """Find the axis distance whose footprint spans ``target_arc_width`` of arc.

    Returns ``(distance, pose, spec, achieved_arc_width)``. The achieved width
    is measured against an oversized copy of the wall, so it is the true image
    width even when the real wall would clip it.

    Fixed-point iteration on ``D_next = D * target / measured``. Arc span is
    very nearly linear in throw distance, so this converges in a handful of
    steps; the loop is capped and the best result so far is returned.
    """
    require_positive("target arc width", target_arc_width)
    if abs(base_spec.lens_shift_h) > 1e-9:
        raise ProjectionError(
            "automatic array planning does not support horizontal lens shift; "
            "set it to zero and place the image centres along the wall arc"
        )
    solve_wall = _measurement_wall(wall)

    # In TILT mode the optical axis is the hypotenuse over the vertical drop,
    # so no candidate distance shorter than that drop is geometrically valid.
    # Clamping the iterate keeps a poor starting guess from aborting a solve
    # that does have an answer.
    drop = abs(mount_height - wall.point_at(arc_center, target_z)[2])
    floor = max(0.05, drop * 1.000001 + 1e-6) if mode == MODE_TILT else 0.05

    # Seed from the chord that subtends the target arc, treated as a flat image.
    chord = 2.0 * wall.radius * math.sin(min(math.pi, target_arc_width / (2.0 * wall.radius)))
    distance = max(floor, chord * base_spec.throw_ratio)

    best: tuple[float, float, Pose, ProjectorSpec, float] | None = None
    for _ in range(SOLVE_MAX_ITERATIONS):
        pose, spec, _pos, _aim, _h, _drop = _build_pose_and_spec(
            wall, base_spec, arc_center, target_z, mount_height, mode, distance
        )
        fp = compute_footprint(pose, spec, solve_wall, samples=samples, name="solve")
        measured = fp.arc_span
        if measured <= 1e-6:
            raise ProjectionError(
                "the projector does not illuminate the wall at any tested distance; "
                "check the wall radius, arc and mount height"
            )
        error = abs(measured - target_arc_width)
        if best is None or error < best[0]:
            best = (error, distance, pose, spec, measured)
        if error <= SOLVE_TOLERANCE:
            break
        # Damped update keeps the curved-wall feedback from oscillating.
        ratio = target_arc_width / measured
        distance *= 1.0 + 0.85 * (ratio - 1.0)
        distance = max(floor, distance)

    assert best is not None  # loop runs at least once
    _err, distance, pose, spec, measured = best
    if _err > SOLVE_TOLERANCE:
        raise ProjectionError(
            f"could not solve a {target_arc_width:.3f} m image width on "
            f"'{wall.name}' within {SOLVE_TOLERANCE:.3f} m; closest was "
            f"{measured:.3f} m"
        )
    return distance, pose, spec, measured


def plan_projector(
    wall: CylindricalWall,
    base_spec: ProjectorSpec,
    arc_center: float,
    target_arc_width: float,
    mount_height: float,
    image_center_height: float | None = None,
    mode: str = MODE_LEVEL,
    samples: int = DEFAULT_SAMPLES,
    index: int = 0,
    name: str = "Projector",
) -> ProjectorPlacement:
    """Plan a single projector to cover ``target_arc_width`` centred on ``arc_center``."""
    if mode not in MOUNT_MODES:
        raise ProjectionError(f"unknown mount mode {mode!r}; expected one of {MOUNT_MODES}")
    target_z = wall.height * 0.5 if image_center_height is None else image_center_height

    distance, pose, spec, achieved_width = solve_standoff(
        wall,
        base_spec,
        arc_center,
        target_z,
        mount_height,
        target_arc_width,
        mode=mode,
        samples=samples,
    )
    _pose, _spec, position, aim_point, horizontal, drop = _build_pose_and_spec(
        wall, base_spec, arc_center, target_z, mount_height, mode, distance
    )
    footprint = compute_footprint(pose, spec, wall, samples=samples, name=name)
    size = image_size(distance, spec)

    # The solve is distance-clamped in TILT mode (the axis cannot be shorter
    # than the vertical drop). If that clamp forced a badly wrong image size,
    # the request is not satisfiable and saying so beats returning a number
    # that quietly ignores what was asked for. ``achieved_width`` comes from
    # the oversized solve wall, so wall clipping does not mask the error.
    if abs(achieved_width - target_arc_width) / target_arc_width > 0.5:
        raise ProjectionError(
            f"cannot produce a {target_arc_width:.2f} m wide image on '{wall.name}' with a "
            f"{base_spec.throw_ratio:.2f}:1 lens mounted at {mount_height:.2f} m in {mode} "
            f"mode: the closest achievable is {achieved_width:.2f} m. Lower the mount, "
            "change the lens, or use more projectors."
        )

    placement = ProjectorPlacement(
        name=name,
        index=index,
        position=position,
        aim_point=aim_point,
        pose=pose,
        spec=spec,
        throw_distance=distance,
        image_width=size.width,
        image_height=size.height,
        arc_center=arc_center,
        arc_span=footprint.arc_span,
        horizontal_standoff=horizontal,
        drop_below_mount=drop,
        mode=mode,
        footprint=footprint,
    )
    placement.warnings.extend(_placement_warnings(placement, wall, target_arc_width))
    placement.warnings.extend(footprint.warnings)
    return placement


def _placement_warnings(
    placement: ProjectorPlacement,
    wall: CylindricalWall,
    target_arc_width: float,
) -> list[str]:
    out: list[str] = []
    spec = placement.spec

    if placement.mode == MODE_LEVEL and not spec.lens_shift_within_limits():
        out.append(
            f"{placement.name}: needs {spec.lens_shift_v * 100:+.0f}% vertical lens shift "
            f"(limit ±{spec.max_lens_shift_v * 100:.0f}%). Lower the mount, raise the image "
            "centre, or switch to TILT mounting with keystone correction."
        )
    if placement.mode == MODE_TILT and abs(placement.tilt_deg) > 15.0:
        out.append(
            f"{placement.name}: tilted {placement.tilt_deg:.1f} deg off horizontal; "
            "keystone correction will crop the image and soften focus"
        )
    if placement.horizontal_standoff >= wall.radius:
        out.append(
            f"{placement.name}: the lens sits {placement.horizontal_standoff:.2f} m from the "
            f"wall but the wall radius is only {wall.radius:.2f} m, so the projector would "
            "pass through the cylinder axis. Use a shorter lens (lower throw ratio)."
        )
    if placement.position[2] <= wall.base_center[2]:
        out.append(
            f"{placement.name}: computed mount height {placement.position[2]:.2f} m is at or "
            "below the base of the wall"
        )
    if target_arc_width > 0:
        err = abs(placement.arc_span - target_arc_width) / target_arc_width
        if err > 0.05 and placement.footprint and placement.footprint.fully_on_surface:
            out.append(
                f"{placement.name}: achieved {placement.arc_span:.2f} m of arc against a "
                f"{target_arc_width:.2f} m target ({err * 100:.0f}% off); the geometry may be "
                "over-constrained"
            )
    if not spec.throw_ratio_within_lens():
        out.append(
            f"{placement.name}: throw ratio {spec.throw_ratio:.2f} is outside the configured "
            f"lens range {spec.throw_ratio_min:.2f}-{spec.throw_ratio_max:.2f}"
        )
    return out


def plan_array(
    wall: CylindricalWall,
    base_spec: ProjectorSpec,
    count: int,
    overlap_fraction: float = 0.15,
    mount_height: float = 3.0,
    image_center_height: float | None = None,
    mode: str = MODE_LEVEL,
    samples: int = DEFAULT_SAMPLES,
    name_prefix: str = "Projector",
) -> ArrayPlan:
    """Lay ``count`` projectors across the wall with the requested overlap."""
    if count < 1:
        raise ProjectionError(f"projector count must be at least 1, got {count}")
    width = arc_width_per_projector(wall.arc_length, count, overlap_fraction)
    centers = arc_centers(wall.arc_length, count, overlap_fraction)

    placements: list[ProjectorPlacement] = []
    for i, center in enumerate(centers):
        placements.append(
            plan_projector(
                wall,
                base_spec,
                arc_center=center,
                target_arc_width=width,
                mount_height=mount_height,
                image_center_height=image_center_height,
                mode=mode,
                samples=samples,
                index=i,
                name=f"{name_prefix}_{i + 1:02d}",
            )
        )

    plan = ArrayPlan(
        wall=wall,
        placements=placements,
        target_arc_width=width,
        overlap_fraction=overlap_fraction,
        mode=mode,
        mount_height=mount_height,
    )
    if count > 1 and overlap_fraction < 0.08:
        plan.warnings.append(
            f"overlap of {overlap_fraction * 100:.0f}% is tight for edge blending; "
            "10-20% is the usual working range"
        )
    return plan


def format_placement(placement: ProjectorPlacement) -> list[str]:
    """Display lines for one placement, used by the Blender panel and the CLI."""
    p = placement
    lines = [
        f"{p.name} [{p.mode}]",
        f"  mount: x={p.position[0]:.3f} y={p.position[1]:.3f} z={p.position[2]:.3f} m",
        f"  standoff from wall: {p.horizontal_standoff:.3f} m, "
        f"image centre {abs(p.drop_below_mount):.3f} m below mount",
        f"  throw distance: {p.throw_distance:.3f} m "
        f"(TR {p.spec.throw_ratio:.2f}), image {p.image_width:.3f} x {p.image_height:.3f} m",
        f"  arc covered: {p.arc_span:.3f} m centred at {p.arc_center:.3f} m",
    ]
    if p.mode == MODE_LEVEL:
        lines.append(f"  vertical lens shift: {p.spec.lens_shift_v * 100:+.1f}% of image height")
    else:
        lines.append(f"  tilt: {p.tilt_deg:+.2f} deg from horizontal")
    if p.footprint:
        lines.append(
            f"  incidence worst case: {math.degrees(p.footprint.max_incidence):.1f} deg, "
            f"throw spread {p.footprint.min_distance:.2f}-{p.footprint.max_distance:.2f} m"
        )
    return lines
