# Plan — Increment C: angle-aware gain model (SMPTE RP 94)

**Date:** 2026-09-20 · **Status:** Landed — feat `9e95929` · **Base:** `main` @ `7e84673` (v0.6.0)
**Increment spec:** `docs/features/next-increments.md` §4.10 (Surface ABC revisit, parked idea)
**Authorisation note:** Sam authorised moving without the 2–3 vendor gain-curve charts
(Stewart/dnp/Elite) the revisit trigger demanded — the parametric curves are therefore
**medium-confidence data** and are flagged loudly per ADR 0002, in code, reports and docs.
**Standing constraints:** ADR 0001 (bpy-free `core/`), ADR 0002 (stated assumptions, loud
medium-confidence flags), ADR 0003 (Surface ABC — `curvature_radius` hook drives the
flat-wall warning), ADR 0005 (analysis edits ride the debounced live sync), repo AGENTS.md
(impact analysis before edit, detect-changes before commit).

## Objective

Replace the scalar Lambertian gain assumption with a `gain(viewing_angle)` profile family
in `core/`:

- **LAMBERTIAN** — today's model, exactly: constant gain at every viewing angle.
- **PEAKED** — lobe centred on the screen normal, parameterised by **peak gain**
  (the existing `screen_gain` value), **half-gain angle** (the datasheet number
  integrators quote) and an **off-axis floor gain** (third parameter; ADR 0002
  three-parameter idealisation).
- **RETROFLECTIVE** — same curve shape, but the lobe is centred on the direction from
  the screen point toward the projector (glass-beaded screens return light to the source).

Emit RP 94-derived warnings: viewers outside the half-gain cone; peak gain > 1.3 on a
flat wall (flag, never model curvature). Per-seat DISCAS luminance becomes the off-axis
correction the per-seat audit was designed to grow into.

## GitNexus impact analysis (run before planning, 2026-09-20)

| Symbol | Risk | Disposition |
|---|---|---|
| `analyze_coverage` | CRITICAL (8 impacted, 6 processes) | extended with `gain_profile`; full ladder covers it |
| `audit_viewers` | CRITICAL (7 impacted) | extended with profile + changed default falloff |
| `assumptions_for_blend_model` | CRITICAL (10 impacted) | gains optional `gain_profile` line replacement |
| `summarize_brightness` | CRITICAL (9 impacted) | **not edited** — effective scalar gain computed by caller |
| `compute_nine_point_report` | CRITICAL (7 impacted) | **not edited** — receives effective scalar gain |
| `luminance_nits` | CRITICAL (9 impacted) | **not edited** — stays the scalar conversion |
| `format_report` | HIGH (4 impacted) | extended with gain-profile line |
| `report_to_dict`, `PJ_PG_Scene`, `PJ_PT_analysis` | LOW | extended |

The CRITICAL set is the analysis→report→export chain the increment is specified to
extend; mitigation is the unpiped verification ladder (ruff → compileall → pytest →
Blender smoke → extension validate) run before every commit.

## Verified ground truth (source-read this session)

- `luminance_nits(illuminance, gain) = lux · gain / π` (`core/photometry.py:117-124`);
  every luminance number in the codebase flows through it or `veiling_luminance_nits`.
- `analyze_coverage(... screen_gain=1.0 ...)` passes the scalar into
  `summarize_brightness`, `summarize_contrast` and `compute_nine_point_report`
  (`core/coverage.py:343,353,373,411,463,479`).
- `audit_viewers` currently reports `perceived = mean_screen_nits · cos θ`
  (`core/discas.py:135`) — labelled "Lambertian cosine falloff", which is physically
  wrong: a Lambertian screen has **no** viewing-angle falloff. Increment C corrects the
  default to no-falloff (true Lambertian) and makes peaked/retroflective profiles the
  angle-aware cases. `tests/test_discas.py:100` pins the old value
  (`200·4/5`) and is updated deliberately with a comment.
- `Surface.curvature_radius` is `None` on `PlanarWall` and `MeshSurface`'s flat-face
  behaviour, `radius` on `CylindricalWall` (`core/surfaces.py:123,252`) — the exact
  hook the >1.3 flat-wall warning needs.
- `ASSUMPTIONS[2]` = "Lambertian screen at the stated gain";
  `assumptions_for_blend_model(model, gamma, derate_chain)` already replaces named lines
  (`core/photometry.py:262-297,486-520`) — the same mechanism replaces the gain line.
- Properties live on `scene.pj` (`PJ_PG_Scene`), analysis inputs assembled in
  `scene_sync._analysis_inputs` (`scene_sync.py:233-311`), which builds
  `DerateChain` from properties the same way the profile will be built.
- Viewer angles are computed against `screen_center`/`screen_normal` at the mid-span of
  the lit band (`core/coverage.py:361-386`) — the reference point for lobe axes.
- `Vec3` is a tuple alias — index `c[0]`, never `.x`.

## Design

### 1. `core/gain.py` (new, bpy-free, ADR 0001)

- `GainModel(str, Enum)`: `LAMBERTIAN`, `PEAKED`, `RETROFLECTIVE`.
- `@dataclass(frozen=True) GainProfile`: `kind`, `peak_gain`, `half_gain_angle_deg`,
  `off_axis_gain`; factory classmethods `lambertian(gain)`, `peaked(peak, half_deg, floor)`,
  `retroflective(peak, half_deg, floor)`.
  - Validation (loud, ADR 0002): `peak_gain > 0` always; for peaked/retro also
    `0 < off_axis_gain < peak_gain / 2` and `0 < half_gain_angle_deg < 90` —
    otherwise `ProjectionError` explaining the half-gain convention
    ("floor gain must sit below half the peak for a half-gain angle to exist").
- Curve: `gain(θ) = off_axis + (peak − off_axis) · cos(θ)^n` with the exponent fitted at
  construction so `gain(θ_h) = peak / 2` exactly:
  `n = ln((peak/2 − floor)/(peak − floor)) / ln(cos θ_h)`. Monotonic in `θ ∈ [0°, 90°]`;
  `θ ≥ 90°` clamps to `off_axis_gain`; negative angle uses the symmetric lobe (`|θ|`).
- API: `gain_at(profile, angle_deg) -> float`, `factor_at(profile, angle_deg)`
  (= `gain_at / peak`, 1.0 on-axis), `lobe_axis(profile, surface_point, surface_normal,
  projector_origin) -> Vec3 | None` (peaked → normal; retro → direction to projector,
  `ProjectionError` if origin missing; lambertian → None),
  `viewing_angle_deg(viewer_point, surface_point, axis) -> float`.
- RP 94 constants + helpers: `RP94_FLAT_WALL_MAX_PEAK = 1.3`,
  `GAIN_CITATION = "SMPTE RP 94-2000, Gain Determination of Front Projection Screens"`,
  `GAIN_PROFILE_DISCLAIMER` (medium-confidence parametric idealisation, vendor charts not
  consulted, per ADR 0002), `assumptions_for_gain_profile(profile) -> str`,
  `flat_wall_gain_warning(profile, wall) -> str | None` (fires only when
  `peak_gain > 1.3` **and** `wall.curvature_radius is None`; names RP 94 and says
  curvature is flagged, not modelled), `gain_model_label(model) -> str`.

### 2. `core/photometry.py` — minimal extension

`assumptions_for_blend_model(model, gamma=1.0, derate_chain=None, gain_profile=None)`:
when a non-Lambertian profile is supplied, the "Lambertian screen at the stated gain"
line is replaced by `assumptions_for_gain_profile(profile)` (peak / half-gain / floor +
RP 94 citation + medium-confidence flag). No other photometry function changes.

### 3. `core/coverage.py` — analysis integration

- `analyze_coverage(..., gain_profile: GainProfile | None = None, projector_origin=None)`:
  - Effective scalar gain = `gain_profile.peak_gain` when a profile is given
    (its peak **is** the on-axis gain; the Blender layer builds the profile from
    `screen_gain` so they agree), else the existing scalar. All scalar consumers
    (brightness bands, contrast, nine-point) receive the effective gain — untouched.
  - `report.gain_profile = gain_profile`.
  - DISCAS audit call gains `gain_profile` and `projector_origin`
    (centroid of usable footprints' lens origins — the array centroid; stated in the
    assumption line for the retroflective case).
  - Warnings appended: `flat_wall_gain_warning(profile, wall)`; per-viewer
    "outside the half-gain cone" lines when `off_axis_deg > half_gain_angle_deg`.
- `format_report`: a "Gain profile: …" line whenever a non-Lambertian profile is active.

### 4. `core/discas.py` — the off-axis correction

`audit_viewers(..., gain_profile=None, projector_origin=None)`:
- No profile / LAMBERTIAN: `perceived = mean_screen_nits` (no falloff — the honest
  Lambertian behaviour; **intentional change** from the old `·cos θ`, documented in the
  docstring and the updated test).
- PEAKED: `perceived = mean_screen_nits · factor_at(profile, θ_normal)`.
- RETROFLECTIVE: θ measured from `lobe_axis` toward `projector_origin`
  (raises `ProjectionError` when the origin is missing — loud, never guessed).

### 5. Blender layer (thin adapter, ADR 0005)

- `properties.py`: `gain_model` (EnumProperty, default LAMBERTIAN, `_update_analysis`),
  `gain_half_angle_deg` (30.0, 1–89), `gain_off_axis` (0.6, min 0.01). `screen_gain`
  keeps its meaning and becomes the peak/on-axis gain for every kind.
- `scene_sync._analysis_inputs`: builds `GainProfile` from properties when
  `gain_model != "LAMBERTIAN"`; validation errors surface through the existing
  live-error path (last valid scene preserved, ADR 0005).
- `ui.py` (`PJ_PT_analysis`): profile enum below Screen Gain; half-gain/floor fields
  and the medium-confidence note shown only for peaked/retroflective.
- `report_export.py`: `report_to_dict` appends a `gain_profile` block (kind, peak,
  half-gain, floor, disclaimer) when active — append-only, `schema_version` stays 1.

### 6. Tests

- `tests/test_gain_profiles.py` (new): curve shape (peak at 0°, exact half at θ_h,
  floor asymptote, monotonic, symmetric), validation rejections, lobe-axis geometry,
  assumption/disclaimer text, flat-wall warning (fires on `PlanarWall`, silent on
  `CylindricalWall`), half-gain-cone warnings via `analyze_coverage` fixtures,
  `audit_viewers` integration (peaked viewer at θ_h sees ≈ half the on-axis nits;
  retro raises without projector origin), `format_report`/`report_to_dict` surfacing.
- `tests/test_discas.py`: deliberate update of the pinned `·cos θ` expectation, with a
  comment citing the correction.
- `tests/blender_smoke.py` `[4j]`: properties exposed, live sync converges with
  PEAKED profile, report carries the profile line, no flat-wall warning on the smoke's
  curved wall.

## Sequencing (TDD)

1. Red: `tests/test_gain_profiles.py` curve + validation tests.
2. Green: `core/gain.py`.
3. Red→green: `assumptions_for_blend_model` profile line; `discas.audit_viewers`
   correction (+ the deliberate `test_discas.py` update).
4. Red→green: `analyze_coverage`/`format_report` integration + warnings.
5. Properties + UI + scene_sync wiring; `report_to_dict` block; smoke `[4j]`.
6. Ladder, detect-changes, explicit-path `feat:` commit, push, gates, docs
   (README bullet, features-index section, landed marker), re-index both graphs.

## Risks / notes

- **Default-falloff change:** DISCAS perceived nits for off-axis viewers rise for the
  default Lambertian case (no falloff is the correct Lambertian behaviour). Deliberate,
  documented, and covered by the updated test — this is increment C's stated purpose.
- **Medium-confidence data:** the profile family is an idealisation; the disclaimer
  constant rides with every surfaced number (assumption line, report line, JSON block,
  README, features doc). Vendor gain-curve charts were not consulted — authorised
  explicitly by Sam.
- **Retro lobe reference:** the array centroid stands in for "the projector";
  multi-projector lobes are not modelled — stated in the assumption line, not hidden.
- **Not modelled:** specular-lobe shift for off-axis peaked projectors, screen curvature
  above 1.3 (flag only), ALR angular data (§4.9 keeps its own trigger).
