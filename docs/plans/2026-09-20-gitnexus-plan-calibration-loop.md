# Plan — Increment D: measured-vs-predicted calibration loop

**Date:** 2026-09-20 · **Status:** Landed — feat `7859425` · **Base:** `main` @ `db9f047` (v0.6.0, increment C landed)
**Increment spec:** `docs/features/next-increments.md` §3 ("Measured-vs-predicted calibration loop")
**Standing constraints:** ADR 0001 (bpy-free `core/`), ADR 0002 (stated assumptions, never
claim the photometry is "verified"), ADR 0003 (Surface ABC for reading positions),
ADR 0005 (analysis edits ride the debounced live sync), repo AGENTS.md (impact analysis
before edit, detect-changes before commit).

## Objective

Close the design→as-built loop: the user records **≥3 on-site lux readings** (from a
handheld meter) against known wall positions; `core/` fits a **scalar correction factor**,
the analysis applies it to every prediction, and the **residual stays visible in every
report**. The fit is recomputed live on every analysis sync — no stale stored factor.

## GitNexus impact analysis (re-run on the fresh post-C index, 2026-09-20)

`analyze_coverage` (extended again), `format_report` (HIGH), `report_to_dict`,
`_analysis_inputs`, `PJ_PG_Scene`, `PJ_PT_analysis` — the same critical-chain set as
increment C's analysis, with the same mitigation: the unpiped verification ladder before
every commit. New symbols (`fit_calibration`, `predict_illuminance_at`,
`CalibrationFit`, the reading operators) have no upstream callers yet.

## Verified ground truth (source-read this session)

- Per-cell illuminance lives in `core/coverage.py::_cell_illuminance` (distance +
  incidence per footprint) combined by `_combined_illuminance` (blend-aware); the raster
  loop additionally occlusion-filters each contribution — a prediction at a reading
  position must apply the identical filtering or the fit double-counts occlusion.
- `analyze_coverage(..., gain_profile=..., calibration=...)`: increment C already
  routed an effective scalar gain through brightness/contrast/nine-point; a calibration
  factor multiplies the combined per-cell illuminance and every downstream number
  inherits it. Ambient light does *not* scale — which is exactly why the effective
  contrast recomputation stays physically correct under a fitted factor.
- `Surface.project_point` (ADR 0003 contract, implemented by `PlanarWall`,
  `CylindricalWall`, `MeshSurface`) returns a `SurfaceHit` with wall `(s, z)` — the
  natural "mark measured positions" primitive for the 3D-cursor operator.
- `_analysis_inputs` already builds `DerateChain` from properties and assembles
  `viewers` the same way the readings will be assembled; `viz.build_occlusion_caster`
  is currently built inline in the `analyze_coverage` call and must be hoisted so the
  prediction path and the raster share one caster.
- Report surfaces: `format_report` (panel + clipboard), `report_to_dict` (JSON,
  append-only keys, `schema_version: 1` stays), `export_coverage_summary_to_csv` (rows).
- Properties live on `scene.pj` (`PJ_PG_Scene`); nested `PropertyGroup` rows (the
  occluder pattern) already use module-level `_update_analysis` update callbacks.
- `Vec3` is a tuple alias — index `c[0]`, never `.x`.

## Design

### 1. `core/calibration.py` (new, bpy-free, ADR 0001)

- `CALIBRATION_DISCLAIMER` — loud ADR 0002 text: scalar correction from on-site
  readings; photometry remains a first-order estimate; **this is not calibration
  certification and does not verify the photometry**.
- `MIN_READINGS = 3` (the spec's own floor).
- `@dataclass(frozen=True) CalibrationReading`: `label`, `s`, `z` (wall coordinates),
  `measured_lux`; finiteness validated; a zero measured value is constructible but
  excluded loudly at fit time.
- `@dataclass(frozen=True) CalibrationFit`: `factor`, `readings_used`,
  `excluded` (reading + reason pairs), `samples` (reading, predicted-projected pairs —
  the visible residual source data), `mean_ratio`, `ratio_std`, `ratio_cv`, `min_ratio`,
  `max_ratio`, `worst_residual_pct`, `ambient_lux`, `disclaimer`; `apply(lux)` helper.
- `fit_calibration(pairs, ambient_lux=0.0, min_readings=MIN_READINGS)`:
  - Model total per reading = `predicted_projected + ambient_lux` — the meter reads the
    total; fitting against the total is honest when ambient is entered, and reduces to
    plain `measured/predicted` when ambient is zero (the default).
  - Exclusions (each with a stated reason): zero predicted (unlit/occluded position),
    non-positive measured, non-finite values.
  - **`< 3` usable readings → `ProjectionError`** (the spec's own requirement; the
    Blender layer degrades to "running uncalibrated" with the error as a warning).
  - `factor = Σ measured / Σ model_total` (ratio of means — the standard scalar-gain
    fit, flux-weighted); per-reading ratios `r_i = measured_i / model_total_i` for the
    dispersion stats; residual per reading = `measured − factor · model_total`,
    reported as worst relative residual.
  - Never invents outlier thresholds — dispersion is reported, not acted on.

### 2. `core/coverage.py` — prediction + application

- New public `predict_illuminance_at(footprints, wall, s, z, blend_model, blend_gamma,
  occlusion_caster)` — the exact raster-cell computation at one position:
  hit-ratio filter, `covers()` back-projection, identical occlusion filter
  (`RAY_TOLERANCE` trim), blend-aware combination. Positions outside the wall raise
  `ProjectionError` naming the coordinates.
- `analyze_coverage(..., calibration: CalibrationFit | None = None)`: the fitted factor
  multiplies the combined per-cell illuminance (white and black paths alike, keeping
  native-contrast black levels consistent); `report.calibration` carries the fit;
  no calibration → byte-for-byte the pre-increment behaviour.
- `format_report`: calibration block — factor, reading count, ambient note, residual
  line (ratio spread, mean, σ, CV, worst residual), per-reading
  measured-vs-model lines, exclusions with reasons, disclaimer.

### 3. Blender layer (thin adapter, ADR 0005)

- `properties.py`: `PJ_PG_CalibrationReading` (label, s, z, measured_lux — s/z/lux
  update `_update_analysis` so edits re-converge live); `enable_calibration`,
  `calibration_readings` collection, `calibration_index` on the scene.
- `operators.py`: `PJ_OT_add_reading_cursor` (projects the 3D cursor onto the target
  wall via `Surface.project_point`, prefills s/z, auto-labels), `PJ_OT_remove_reading`,
  `PJ_OT_clear_readings` (mirroring the occluder operators). Registered in `_CLASSES`.
- `ui.py` (`PJ_PT_analysis`): an "On-Site Calibration" box — enable toggle, reading
  list, add-at-cursor/remove/clear, the active row's editable fields, and the
  coordinate convention note.
- `scene_sync._analysis_inputs`: hoists one `viz.build_occlusion_caster(scene)` for
  both the prediction path and the raster; when enabled, builds readings from the
  collection, predicts at each position, fits, and passes the fit to
  `analyze_coverage`; any `ProjectionError` (too few usable readings, position outside
  the wall) degrades to a loud warning + uncalibrated run rather than killing the
  analysis. The fit is recomputed every sync — nothing stored goes stale.
- `report_export.py`: `report_to_dict` appends a `calibration` block (factor,
  dispersion, samples, exclusions, disclaimer — append-only, schema stays 1); CSV gains
  Calibration rows.

### 4. Tests

- `tests/test_calibration.py` (new): exact fit arithmetic (factor, ratios, σ, CV, worst
  residual, ambient handling), the ≥3 rejection, exclusion reasons, `apply()`,
  disclaimer loudness; `predict_illuminance_at` parity with the raster path (covered
  point, uncovered point, outside-wall rejection, occlusion filtering); `analyze_coverage`
  integration (brightness scales by the factor, `report.calibration` set, format lines,
  JSON block, uncalibrated default unchanged).
- `tests/blender_smoke.py` `[4k]`: properties exposed, three readings added directly,
  live sync converges with a "Calibration:" report line and residual line, JSON export
  carries the block, disabling returns the uncalibrated report.

## Sequencing (TDD)

1. Red: `tests/test_calibration.py` fit-math tests.
2. Green: `core/calibration.py`.
3. Red→green: `predict_illuminance_at` + `analyze_coverage(calibration=...)` +
   `format_report` + export block.
4. Properties + operators + UI + scene_sync wiring; smoke `[4k]`.
5. Ladder, detect-changes, explicit-path `feat:` commit, push, gates, docs
   (README row, features-index section, landed marker), re-index both graphs.

## Risks / notes

- **Garbage in, garbage out is bounded by design:** ≥3 usable readings enforced,
  dispersion always reported, and the disclaimer refuses "verified" language — the
  spec's own three mitigations, all implemented.
- **Ambient subtlety:** readings include ambient illuminance; the fit uses
  `predicted + ambient` (the model's total prediction) and states this in the
  disclaimer/report. With ambient = 0 the fit is the plain measured/predicted ratio.
- **Honesty:** the tool reports its own residual; it never claims the photometry is
  calibrated or verified (ADR 0002 by construction).
- **UX bounded:** positions are wall `(s, z)` coordinates — the same convention every
  report already prints — with a one-click 3D-cursor projection operator. No freeform
  3D marking surface; that is the deliberate scope line from §3.
