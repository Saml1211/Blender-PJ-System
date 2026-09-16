"""Coalesced synchronization from persisted controls to derived scene state.

Geometry Nodes handles generated-wall display geometry immediately. This module
owns the derived objects that still require the tested Python core: projector
cameras, coverage overlays, computed fields, and report text.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from enum import IntEnum

import bpy

from . import visualization as viz
from .core.array import format_placement, plan_array
from .core.coverage import analyze_coverage, format_report
from .core.errors import ProjectionError
from .core.footprint import compute_footprint
from .core.photometry import BlendModel, brightness_warnings
from .core.pose import Pose
from .core.throw import ProjectorSpec, describe_throw, image_size
from .scene_ids import OBJECT_ROLE_KEY, OWNER_ID, OWNER_KEY

ARRAY_OBJECT_ROLE = "generated_projector_array"
DEBOUNCE_SECONDS = 0.2


class SyncScope(IntEnum):
    """Smallest derived scene scope invalidated by an input edit."""

    ANALYSIS = 1
    ARRAY = 2
    WALL = 3


@dataclass(frozen=True)
class ArraySyncResult:
    projectors: tuple[bpy.types.Object, ...]
    lines: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class AnalysisSyncResult:
    lines: tuple[str, ...]
    warnings: tuple[str, ...]
    covered_fraction: float
    horizontal_coverage: float
    gap_count: int
    blend_count: int


_suspend_depth = 0
_pending: dict[str, tuple[SyncScope, float]] = {}
_timer_registered = False


@contextlib.contextmanager
def suspend_requests():
    """Suppress property-driven requests while computed state is being written."""
    global _suspend_depth
    _suspend_depth += 1
    try:
        yield
    finally:
        _suspend_depth -= 1


def requests_suspended() -> bool:
    return _suspend_depth > 0


def target_wall(scene: bpy.types.Scene) -> bpy.types.Object | None:
    wall = scene.pj.target_wall
    return wall if wall is not None and wall.pj_wall.is_wall else None


def wall_for_scene(scene: bpy.types.Scene):
    wall_obj = target_wall(scene)
    if wall_obj is None:
        raise ProjectionError("No target wall set. Create or select one first.")
    viz.sync_generated_wall_mesh(wall_obj)
    return wall_obj, viz.wall_from_object(wall_obj)


def scene_spec(scene: bpy.types.Scene) -> ProjectorSpec:
    pj = scene.pj
    return ProjectorSpec(
        throw_ratio=pj.throw_ratio,
        aspect_w=pj.aspect_w,
        aspect_h=pj.aspect_h,
        lumens=pj.lumens,
        max_lens_shift_v=pj.max_lens_shift_v,
    )


def projectors_in_scene(scene: bpy.types.Scene) -> list[bpy.types.Object]:
    return [
        obj
        for obj in scene.objects
        if obj.pj_projector.is_projector and not obj.hide_viewport and not obj.hide_get()
    ]


def pose_from_matrix(matrix) -> Pose:
    """Build a core pose from Blender's +X/+Y/-Z camera basis."""
    basis = matrix.to_quaternion().to_matrix()
    origin = matrix.translation
    col_x = basis.col[0]
    col_y = basis.col[1]
    col_z = basis.col[2]
    return Pose(
        origin=(origin.x, origin.y, origin.z),
        right=(col_x.x, col_x.y, col_x.z),
        up=(col_y.x, col_y.y, col_y.z),
        forward=(-col_z.x, -col_z.y, -col_z.z),
    )


def set_report(scene: bpy.types.Scene, lines: list[str], warnings: list[str]) -> None:
    """Replace the report shown in the sidebar."""
    pj = scene.pj
    pj.report_lines.clear()
    for text in lines:
        entry = pj.report_lines.add()
        entry.text = text
        entry.kind = "INFO"
    for text in warnings:
        entry = pj.report_lines.add()
        entry.text = text
        entry.kind = "WARNING"
    pj.has_report = True


def _owned_array_projectors(scene: bpy.types.Scene) -> list[bpy.types.Object]:
    return sorted(
        (
            obj
            for obj in scene.objects
            if obj.pj_projector.is_projector
            and obj.get(OWNER_KEY) == OWNER_ID
            and (obj.get(OBJECT_ROLE_KEY) == ARRAY_OBJECT_ROLE or bool(obj.get("pj_generated")))
        ),
        key=lambda obj: obj.name,
    )


def _remove_camera_object(obj: bpy.types.Object) -> None:
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if isinstance(data, bpy.types.Camera) and data.users == 0:
        bpy.data.cameras.remove(data)


def _camera_for_placement(
    existing: list[bpy.types.Object], index: int, name: str
) -> bpy.types.Object:
    if index < len(existing):
        obj = existing[index]
        if isinstance(obj.data, bpy.types.Camera):
            return obj
        _remove_camera_object(obj)
    camera = bpy.data.cameras.new(name)
    return bpy.data.objects.new(name, camera)


def sync_array(scene: bpy.types.Scene) -> ArraySyncResult:
    """Plan and reconcile the owned projector array without touching manual cameras."""
    wall_obj, wall = wall_for_scene(scene)
    pj = scene.pj
    plan = plan_array(
        wall,
        scene_spec(scene),
        count=pj.projector_count,
        overlap_fraction=pj.overlap,
        mount_height=pj.mount_height,
        image_center_height=pj.image_center_height,
        mode=pj.mount_mode,
        samples=pj.samples,
        name_prefix="PJ",
    )

    existing = _owned_array_projectors(scene)
    collection = viz.get_collection(scene, viz.COLLECTION_PROJECTORS)
    reconciled: list[bpy.types.Object] = []
    with suspend_requests():
        for index, placement in enumerate(plan.placements):
            obj = _camera_for_placement(existing, index, placement.name)
            obj.name = placement.name
            obj.data.name = placement.name
            obj[OWNER_KEY] = OWNER_ID
            obj[OBJECT_ROLE_KEY] = ARRAY_OBJECT_ROLE
            obj["pj_generated"] = True  # backward-compatible ownership marker
            obj.matrix_world = viz.pose_matrix(placement.position, placement.pose.basis_columns())
            viz.apply_spec_to_object(obj, placement.spec, placement.mode)
            viz.configure_camera(obj, placement.spec, placement.throw_distance)
            viz.store_placement_results(obj, placement)
            viz.link_only_to(obj, collection)
            reconciled.append(obj)
        for obsolete in existing[len(plan.placements) :]:
            _remove_camera_object(obsolete)

    warnings = list(plan.warnings)
    for placement in plan.placements:
        warnings.extend(placement.warnings)
    lines = [
        f"Planned {len(reconciled)} projector(s) on '{wall_obj.name}'",
        f"Target image width per projector: {plan.target_arc_width:.2f} m of arc "
        f"at {pj.overlap * 100:.0f}% overlap",
        f"Mount height {pj.mount_height:.2f} m, image centre "
        f"{pj.image_center_height:.2f} m above wall base, mode {pj.mount_mode}",
    ]
    for placement in plan.placements:
        lines.extend(format_placement(placement))
    with suspend_requests():
        set_report(scene, lines, warnings)
    return ArraySyncResult(tuple(reconciled), tuple(lines), tuple(warnings))


def _analysis_inputs(scene: bpy.types.Scene):
    wall_obj, wall = wall_for_scene(scene)
    projectors = projectors_in_scene(scene)
    if not projectors:
        raise ProjectionError(
            "No projectors in the scene. Add one or configure the automatic array."
        )

    pj = scene.pj
    footprints = []
    warnings: list[str] = []
    for obj in projectors:
        spec = viz.spec_from_object(obj)
        pose = pose_from_matrix(obj.matrix_world)
        try:
            footprint = compute_footprint(pose, spec, wall, samples=pj.samples, name=obj.name)
        except ProjectionError as exc:
            raise ProjectionError(f"{obj.name}: {exc}") from exc
        footprints.append((obj, spec, footprint))
        warnings.extend(footprint.warnings)
        warnings.extend(describe_throw(max(footprint.center_distance, 1e-3), spec).warnings)

    report = analyze_coverage(
        [footprint for _obj, _spec, footprint in footprints],
        wall,
        grid_s=pj.grid_s,
        grid_z=pj.grid_z,
        screen_gain=pj.screen_gain,
        blend_model=BlendModel[pj.blend_model],
        # Obstacles are always tested, even with the shadow overlay switched
        # off: the numbers in the report must not depend on what is drawn.
        occlusion_caster=viz.build_occlusion_caster(scene),
    )
    warnings.extend(report.warnings)
    if report.brightness is not None:
        warnings.extend(brightness_warnings(report.brightness))
    return wall_obj, wall, footprints, report, warnings


def sync_analysis(scene: bpy.types.Scene, *, visualize: bool = True) -> AnalysisSyncResult:
    """Recompute footprints, overlays, computed fields, and report as one refresh."""
    _wall_obj, wall, footprints, report, warnings = _analysis_inputs(scene)
    pj = scene.pj

    lines = format_report(report)
    lines.append("Projector mounting and throw:")
    for obj, spec, footprint in sorted(footprints, key=lambda item: item[0].name):
        props = obj.pj_projector
        location = obj.matrix_world.translation
        size = image_size(max(footprint.center_distance, 1e-3), spec)
        lines.append(
            f"  {obj.name}: mount x={location.x:+.2f} y={location.y:+.2f} "
            f"z={location.z:.2f} m; throw {footprint.center_distance:.2f} m; "
            f"image {size.width:.2f} x {size.height:.2f} m; "
            f"shift V={props.lens_shift_v * 100:+.1f}% "
            f"H={props.lens_shift_h * 100:+.1f}%"
        )
    if report.brightness is not None:
        lines.append("Brightness assumptions: " + "; ".join(report.brightness.assumptions))

    with suspend_requests():
        for obj, spec, footprint in footprints:
            viz.configure_camera(obj, spec, max(footprint.center_distance, 1e-3))
            viz.store_footprint_results(obj, footprint, pj.screen_gain)
            occlusion = report.projector_occlusions.get(obj.name)
            props = obj.pj_projector
            if occlusion is None:
                props.calc_occluded_cells = 0
                props.calc_occluded_ratio = 0.0
            else:
                props.calc_occluded_cells = occlusion.occluded_cells
                props.calc_occluded_ratio = occlusion.occluded_fraction
        set_report(scene, lines, warnings)
        if visualize:
            viz.clear_collection(scene, viz.COLLECTION_ANALYSIS)
            for index, (_obj, _spec, footprint) in enumerate(footprints):
                viz.build_footprint_object(scene, footprint, wall, index)
                if pj.draw_frustums:
                    viz.build_frustum_object(scene, footprint, index)
            viz.build_gap_object(scene, wall, report.gaps)
            viz.build_blend_object(scene, wall, report.blend_zones)
            if pj.show_occlusion_overlay and report.shadowed_cells:
                viz.build_occlusion_object(scene, wall, report.shadowed_cells)

    return AnalysisSyncResult(
        tuple(lines),
        tuple(warnings),
        report.covered_fraction,
        report.horizontal_coverage,
        len(report.gaps),
        len(report.blend_zones),
    )


def _set_live_error(scene: bpy.types.Scene, message: str) -> None:
    if hasattr(scene.pj, "live_error"):
        with suspend_requests():
            scene.pj.live_error = message


def _clear_live_error(scene: bpy.types.Scene) -> None:
    _set_live_error(scene, "")


def sync_scene(scene: bpy.types.Scene, scope: SyncScope = SyncScope.WALL) -> None:
    """Synchronously converge every derived subsystem invalidated by ``scope``."""
    if scope >= SyncScope.ARRAY:
        sync_array(scene)
    sync_analysis(scene)
    _clear_live_error(scene)


def request_scene_sync(
    scene: bpy.types.Scene,
    scope: SyncScope = SyncScope.ARRAY,
    *,
    delay: float = DEBOUNCE_SECONDS,
) -> None:
    """Coalesce a scene refresh for Blender's main-thread timer loop."""
    global _timer_registered
    if requests_suspended() or target_wall(scene) is None:
        return
    deadline = time.monotonic() + max(0.0, delay)
    previous = _pending.get(scene.name_full)
    merged_scope = max(scope, previous[0]) if previous is not None else scope
    _pending[scene.name_full] = (merged_scope, deadline)
    if not _timer_registered:
        bpy.app.timers.register(_flush_pending, first_interval=max(0.0, delay))
        _timer_registered = True


def _run_sync(scene: bpy.types.Scene, scope: SyncScope) -> bool:
    try:
        sync_scene(scene, scope)
    except ProjectionError as exc:
        _set_live_error(scene, str(exc))
        return False
    except Exception as exc:  # pragma: no cover - defensive Blender boundary
        message = f"Unexpected live-update error: {type(exc).__name__}: {exc}"
        _set_live_error(scene, message)
        print(f"[Projection Planner] {message}")
        return False
    return True


def _flush_pending() -> float | None:
    global _timer_registered
    now = time.monotonic()
    ready = [(name, scope) for name, (scope, deadline) in _pending.items() if deadline <= now]
    for name, scope in ready:
        _pending.pop(name, None)
        scene = bpy.data.scenes.get(name)
        if scene is not None:
            _run_sync(scene, scope)
    if _pending:
        next_deadline = min(deadline for _scope, deadline in _pending.values())
        return max(0.01, next_deadline - time.monotonic())
    _timer_registered = False
    return None


def pending_scope(scene: bpy.types.Scene) -> SyncScope | None:
    """Return the currently queued scope for diagnostics and acceptance tests."""
    pending = _pending.get(scene.name_full)
    return pending[0] if pending is not None else None


def timer_registered() -> bool:
    """Whether this module currently owns a registered Blender timer."""
    return _timer_registered and bpy.app.timers.is_registered(_flush_pending)


def flush_scene_sync(scene: bpy.types.Scene) -> bool:
    """Immediately run a queued refresh; used by explicit operators and tests."""
    pending = _pending.pop(scene.name_full, None)
    scope = pending[0] if pending is not None else SyncScope.WALL
    result = _run_sync(scene, scope)
    global _timer_registered
    if not _pending and _timer_registered and bpy.app.timers.is_registered(_flush_pending):
        bpy.app.timers.unregister(_flush_pending)
        _timer_registered = False
    return result


def cancel_pending_syncs() -> None:
    """Cancel module-owned timers during add-on unregister/reload."""
    global _timer_registered
    _pending.clear()
    if _timer_registered and bpy.app.timers.is_registered(_flush_pending):
        bpy.app.timers.unregister(_flush_pending)
    _timer_registered = False


def register() -> None:
    """Migrate loaded generated walls and converge scenes after registration."""
    for obj in bpy.data.objects:
        if obj.get("pj_generated_wall") and obj.get(OWNER_KEY) == OWNER_ID:
            try:
                viz.sync_generated_wall_mesh(obj)
            except ProjectionError as exc:
                print(f"[Projection Planner] Could not migrate '{obj.name}': {exc}")
    for scene in bpy.data.scenes:
        if target_wall(scene) is not None:
            request_scene_sync(scene, SyncScope.WALL)


def unregister() -> None:
    cancel_pending_syncs()
