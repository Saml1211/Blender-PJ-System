# Plan — Increment #4 Phase 2: warp/corner-pin grid export

**Date:** 2026-09-20 · **Status:** Landed — feat `dd7820b` · **Base:** `main` @ `ba154c4` (v0.6.0)
**Increment spec:** `docs/features/next-increments.md` §2 #4 phase 2
**Standing constraints:** ADR 0001 (bpy-free `core/`), ADR 0002 (design-phase targets, never calibration), ADR 0003 (Surface ABC), repo AGENTS.md (impact analysis before edit, detect-changes before commit)

## Objective

Per-projector warp and corner-pin grids derived from the existing back-projection
(`core/footprint.py::Footprint.image_uv_of`, `footprint_corners_world`), exported toward
processors (TouchDesigner / Resolume / media servers), worded honestly as **design-phase
targets, not calibration**.

## Verified ground truth (source-read this session)

- `Footprint.image_uv_of(point)` → `(u, v)` in `[-0.5, 0.5]`, or `None` behind the lens
  (`core/footprint.py:88-106`).
- `footprint_corners_world(fp)` → up to 4 wall corner points in `throw.CORNER_UV` order;
  **missed corners are omitted — callers must check length** (`core/footprint.py:299-311`).
- `throw.CORNER_UV` = TL(-0.5,0.5), TR(0.5,0.5), BR(0.5,-0.5), BL(-0.5,-0.5); `grid_uv`
  is row-major, top row first, outermost samples on image edges (`core/throw.py:34,257`).
- `Surface.point_at(s, z)` exists on `PlanarWall`, `CylindricalWall`, `MeshSurface`
  (Surface ABC contract); `CylindricalWall.angle_at_s` is linear and unclamped, so
  unwrapped arc coordinates (from `_minimal_arc_values`) map continuously — no seam bug.
- Phase-1 export shape: pure-`core` serializers with `schema_version: 1`
  (`core/report_export.py`), operator `PJ_OT_export_analysis` polls
  `scene.pj.has_report`, calls `_sync_analysis_inputs(scene)` → `(wall_obj, wall,
  footprints, report, warnings)` where `footprints` = `(obj, spec, fp)` tuples
  (`operators.py:807-878`). UI row at `ui.py:337-339`.
- Test pattern: pure-Python fixture (CylindricalWall + ProjectorSpec + Pose +
  `compute_footprint`) → JSON round-trip / CSV line assertions
  (`tests/test_report_export.py`).
- `Vec3` is a tuple alias — index `c[0]`, never `.x` (handoff gotcha #2).

## Design

### 1. `core/warp_export.py` (new, bpy-free, ADR 0001)

- `WarpVertex`: `(s, z)` wall coords (m), world `(x, y, z)`, image uv `(u, v)` normalized
  or `None`, `valid: bool`.
- `WarpGrid`: projector name, resolution, vertices (row-major, top row first),
  corners (corner-pin points + normalized uv, may be < 4), warnings.
- `build_warp_grid(fp, resolution=16) -> WarpGrid` — lattice over the footprint's
  illuminated extents `(fp.s_min..fp.s_max) × (fp.z_min..fp.z_max)`; per lattice point:
  `wall.point_at(s, z)` → `fp.image_uv_of(point)` → uv, `valid` = uv present **and**
  `|u| ≤ 0.5 and |v| ≤ 0.5` (normalized `u + 0.5`, `v + 0.5`). Corner-pin points come
  from `footprint_corners_world`; < 4 corners ⇒ warning "corner pin incomplete — use
  the mesh grid" (curved walls: 4 corners can never represent the geometry — say so).
- `export_warp_grids_to_json(wall, grids, generator) -> str` — `schema_version: 1`,
  per-wall meta, per-projector grid arrays, disclaimer string, warnings. New keys may
  only be appended in future versions (schema stability).
- `export_warp_meshes_to_obj(wall, grids) -> str` — one `o` object per projector;
  `v` = world XYZ (metres), `vt` = normalized uv with v-up (OBJ bottom-left
  convention: `vt = (u+0.5, 0.5-v)`); faces only where all 4 lattice corners are valid;
  vertices used by no valid face are omitted. Header comment states units and uv
  convention.

### 2. Operator + UI (Blender side)

- `PJ_OT_export_warp` mirroring `PJ_OT_export_analysis`: poll `scene.pj.has_report`,
  fileselect, format enum `{"JSON", "OBJ"}`, extension suffixing, reuse
  `_sync_analysis_inputs`. Register in `_CLASSES`.
- `ui.py`: "Export Warp Grids" button on a row below the phase-1 export row.
- No new scene properties (resolution is an operator property, default 16, range 2–64).

### 3. Docs

- `docs/features/index.md`: new section for warp export (mirrors phase-1 entry).
- `README.md` feature list: one line, ADR 0002 wording.
- Disclaimer (rides with the data, not only the manual): "Design-phase geometric
  targets computed from the add-on's projector/wall model. Not a calibration
  substitute — on-site alignment and image mapping remain calibration tasks."

### 4. Tests (`tests/test_warp_export.py`, pure Python first)

Flat wall + cylindrical wall fixtures; assertions:

1. Round-trip property: for each valid vertex, `point_at(s, z)` back-projects to the
   emitted uv, and the forward ray through that uv re-hits within tolerance.
2. Validity: lattice points outside the image are marked invalid; none are emitted
   with uv outside `[0, 1]` (±float epsilon).
3. Corner omission: tilted pose with a spilling corner ⇒ < 4 corners + warning.
4. JSON round-trip: `schema_version == 1`, uv/valid arrays consistent with vertices.
5. OBJ: vertex count == count of face-used vertices; face count == valid cell count;
   all `vt` in `[0, 1]`; one `o` per projector.
6. Wrapped cylindrical wall: unwrapped s lattice still round-trips.
7. Grid resolution 2 (minimum) and a too-small resolution raise `ProjectionError`.

Blender smoke test gains a `[4i]` section (export operator path via headless invoke).

## Sequencing (TDD)

1. Red: `tests/test_warp_export.py` for `build_warp_grid` + round-trip on a flat wall.
2. Green: `core/warp_export.py` (grid + corner pin only).
3. Red→green: JSON + OBJ serializers (schema, conventions, faces).
4. Red→green: wrapped-cylinder + spill-omission cases.
5. Operator + UI + registration; smoke `[4i]`; `extension validate`.
6. Docs (features index, README, plan-status note); ruff + compileall + pytest +
   Blender smoke; GitNexus impact on every edited symbol before each edit;
   `detect-changes` before commit; explicit-path commits (`feat:`/`docs:`), push per landing.

## Risks / notes

- **Format sprawl:** exactly two formats (JSON, OBJ), both documented — per the
  increment's own constraint.
- **Schema stability:** `schema_version: 1`, append-only keys, frozen key names.
- **Honesty:** no claims about specific processors' native import paths (unverified);
  the JSON/OBJ are generic data carriers. Curved-wall corner-pin insufficiency stated
  inline. Occlusion is deliberately excluded (geometric mapping, not illumination) —
  stated in the disclaimer.
- **Deferred:** the generated warp *image* (test-pattern PNG) is out of this pass;
  record as a follow-up in the features doc if wanted.
