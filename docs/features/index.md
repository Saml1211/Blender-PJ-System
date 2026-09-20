# Feature reference

What each capability actually computes, and where it stops. Every entry maps to
a module in `blender_projection_system/core/` and to tests that import it.

---

## Throw geometry — `core/throw.py`

`TR = D / W`, with `W = D / TR`, `D = W · TR`, and `H = W / aspect`.

Field of view comes from the same relationship: `tan(θ_h) = 1 / (2·TR)`, and
the vertical half-angle follows `tan(θ_v) = tan(θ_h) / aspect`.

**Edge cases raise instead of returning infinity.** v0.1 returned
`float('inf')` for a zero image width, which then propagated silently into the
scene. A zero or negative distance, width, ratio or aspect component now raises
`ProjectionError`, which the operators surface as a readable error.

**Limits:** these analytic relationships are deterministic to floating-point
precision; they do not model manufacturer lens tolerances or calibration error.

### Lens shift

Shift is the offset of the image centre from the optical axis, expressed as a
fraction of the **full** image dimension. `lens_shift_v = 0.5` puts the axis on
the image's bottom edge.

Manufacturers are inconsistent here. Christie, Barco and Panasonic typically
call that same geometry "100% offset", measuring against *half* the image.
Use `shift_from_half_image_percent()` to convert, or simply halve the datasheet
number.

Shift changes where the frustum sits, never its angles or the image size.
Configured limits are checked and reported.

---

## Projector & lens spec library — `core/specs.py`

A local, versioned specification library keyed by manufacturer and model.
Eliminates manual transcription of datasheets and validates planning inputs
against real hardware optics.

Ships with a bundled starter catalog of verified venue/staging projectors
(`core/data/projector_library.json`) covering Christie, Panasonic, Barco, and
Epson lines with their complete lens lineups. Users can import custom CSV files
(`projection.import_spec_csv`) to extend or override library models without
code changes.

**Honest validation (ADR 0002):**
- **Warn, never clamp:** applying a preset checks whether the current throw ratio
  and shift settings fall within the fitted lens's rated limits (`TR_min`..`TR_max`,
  `max_shift_v`, `max_shift_h`). Out-of-range values stay as typed and produce
  loud warnings in both the operator report and the coverage report — numbers
  are never silently altered to look valid.
- **Cited provenance:** every bundled row records a `source_url` pointing to the
  official manufacturer datasheet or throw calculator, and a `verified` boolean
  flag marking entries confirmed against primary sources.
- **Lens transmission factor:** each lens records a transmission factor
  (typically 0.75–0.92, accounting for optical elements and zoom loss),
  unblocking realistic photometric calculations.

---

## Curved surfaces — `core/surfaces.py`

A `CylindricalWall` is a vertical-axis cylinder segment: base centre, radius,
height, angular start/end, and whether the usable face is concave.

Surface points carry an `(s, z)` parameterisation where `s` is **arc length**
from the start angle — the dimension an installer measures along the wall.

Ray intersection solves the quadratic against the infinite cylinder and then
applies the height and angular bounds, returning the hit point, distance,
surface normal and incidence angle. Vertical rays, rays that miss, and rays
that only hit behind the origin all return `None`.

**Limits:**

- Cylinders, planes, and mostly-frontal imported meshes. Mesh targets (`Set as
  Target Wall` on any mesh object, `core/mesh_surface.py`) are ray-cast via a
  BVH against a frontal heightfield; folds, overhangs, domes, and columns are
  rejected loudly with the offending region named (ADR 0004).
- Rotated walls and walls with unapplied object scale are rejected. Translation
  is supported. Imported-mesh targets use their depsgraph-evaluated geometry,
  including modifier stacks.
- Obstacles in the light path are tested against user-selected obstacle
  objects (see Line-of-sight occlusion below). When no obstacles are
  configured, line of sight is assumed clear.

---

## Line-of-sight occlusion — `core/occlusion.py`

A projector's coverage claim is only honest if nothing stands in the light path.
For each cell in the coverage raster, a ray is cast from the projector aperture
to the surface point. If any user-selected obstacle intercepts the ray before it
reaches the wall, the projector contributes zero light to that cell.

Casting delegates through the injectable `OcclusionCaster` protocol (ADR 0004):
`core` ships a pure-Python Möller–Trumbore implementation
(`TriMeshOcclusionCaster`) used by unit tests, while the Blender layer builds a
`mathutils.bvhtree.BVHTree` across evaluated obstacle meshes and injects it.

**Honest reporting (ADR 0002):**
- Obstacles never silently delete or shift cells; occluded cells are tallied
  per projector, reported in `CoverageReport.projector_occlusions`, and warned
  about loudly whenever an image is partially or fully shaded.
- Cells where every covering projector is blocked are recorded as
  `shadowed_cells` and drawn in the viewport as a dedicated red overlay
  (`PJ_Occlusion`).
- The target wall itself, other wall objects, projectors, and add-on-owned
  overlays are automatically excluded from the obstacle set so the target
  never occludes its own surface samples.

---

## Image footprints — `core/footprint.py`

An N×N grid of rays through the image plane is cast onto the wall. Each sample
records where it landed, how far it travelled and at what incidence.

From those samples the add-on reports arc span, height span, throw spread
across the image, worst incidence angle, and the fraction of the image that
actually landed on the target.

Two results here are worth knowing because they are counter-intuitive, and both
are covered by tests:

- **On a concave wall the image centre is the *nearest* point**, not the
  farthest. From inside a cylinder the closest surface point lies straight out
  along the radius, so corners are further away and focus must cover a range.
- **A concave wall clips the image *narrower* than `W = D/TR`.** A flat screen
  at the same axial distance would sit outside the cylinder at its edges, so
  the wall intercepts the edge rays early.

Coverage tests use **back-projection** (`Footprint.covers`), the exact inverse
of the forward ray cast, rather than a point-in-polygon test against the
sampled outline. When an image spills off the wall the outline walk skips the
missed samples and closes across the gap, which understates the lit area.

**Limits:** sample count trades speed for resolution. The image edges are always
sampled, but curved/clipped extrema can fall between rays, and interior coverage
is deliberately a finite raster estimate.

---

## Projector placement — `core/pose.py`, `core/array.py`

A `Pose` is an origin plus an orthonormal basis, with local `-Z` as the optical
axis — the same convention as a Blender camera, so the mapping into the scene
is direct.

Two mounting modes:

| Mode | Behaviour | Trade-off |
| --- | --- | --- |
| **Level + Lens Shift** | Optical axis stays horizontal; lens shift moves the image down. | No keystone, even focus. Warns when the required shift exceeds the configured lens limit. |
| **Tilt to Target** | Projector tilts to aim at the target point. | Avoids lens shift, but can be geometrically infeasible; successful layouts introduce keystone. |

Array planning distributes *N* projectors across the wall so that
`arc = N·w − (N−1)·f·w` for overlap fraction `f`, then **solves numerically**
for the standoff distance that produces arc width `w`. The solve is iterative
because a planar image landing on a cylinder has no closed-form arc width; it
runs against an oversized copy of the wall so edge projectors are not measured
against a clipped image.

If the request cannot be met — for example a lens too long to reach the
required image size from the given ceiling height — it raises with a message
naming the constraint, rather than returning a number that ignores the request.

---

## Realtime scene adapter — `procedural_geometry.py`, `scene_sync.py`

Generated flat and curved walls share one owned, versioned Geometry Nodes group.
Drivers map the persisted `pj_wall` controls to hidden modifier inputs, so wall
shape, height, resolution, yaw, arc limits, and face direction update through
Blender's dependency graph without replacing the object's mesh datablock.

Projector placement and coverage remain Python because cameras, ray casting,
reports, and photometry use the single tested implementation in `core/`. Input
callbacks queue a main-thread refresh after about 200 ms of idle time. The
refresh reconciles only owned array cameras, then rebuilds overlays, calculated
fields, and the report. Invalid intermediate edits preserve the last valid
derived scene and expose a live error until the next valid edit.

---

## Coverage, gaps and blend zones — `core/coverage.py`

The wall is rasterised in `(s, z)`. Each cell is tested against every
projector, giving a per-cell count.

The report separates two things that are easy to conflate:

- **Dark bands (`gaps`)** — arc ranges lit by nobody *at any height*. These are
  real holes between projectors.
- **The lit band height** — how much of the wall's height the images reach. A
  16:9 image on a taller wall leaves strips top and bottom. That is a normal
  consequence of a fixed aspect ratio, not a fault, and is reported separately
  so it does not masquerade as a gap.

Blend zones are raster-tested in both arc and height between neighbouring
projectors, then reported in metres and as a fraction of image width. Overlaps
below ~5% are flagged as too narrow to blend reliably; above ~50% as wasteful.

**Limits:** this is overlap **geometry**. The soft-edge luminance ramp a
blending processor applies is not modelled.

---

## Brightness — `core/photometry.py`

Luminous intensity is `Φ / Ω`, where `Ω` is the analytic solid angle of the
possibly off-axis rectangular frustum. Illuminance at a surface point is
`E = I·cos(incidence) / d²`, using the real per-point distance and incidence
from the footprint samples. Luminance is `E · gain / π`.

Reported in lux, nits and foot-lamberts, with min/max/mean and a uniformity
ratio.

### The five assumptions — printed with every report

1. Uniform intensity across the frustum. Real projectors fall off toward the
   corners; ANSI 9-point uniformity commonly expresses corner or minimum output
   relative to a center/reference value. A 70–90% result therefore represents
   roughly a 10–30% corner-output shortfall, which this estimate does not model.
2. Rated lumens delivered in full — no lamp ageing, eco mode, or colour-mode
   derate. Divide the lumens input yourself to model those.
3. A Lambertian screen at the stated gain. High-gain screens only deliver rated
   gain near the specular direction.
4. **No ambient light and no inter-reflection.** Contrast in a real room will be
   worse.
5. Overlapping projectors add linearly. Correct for incoherent sources, but it
   ignores the blend processor's ramp.

### One subtlety worth knowing

`lumens / area` is the **mean** illuminance across a flat screen.
`I / d²` is the **on-axis** value. They differ by a purely geometric factor
(`center_to_mean_ratio`) — about 11% for a 1.2:1 lens, 1% for a 4:1 — because
corners are further away and struck obliquely. The add-on reports both
correctly rather than conflating them.

Results are flagged against the ~55 nit (16 fL) cinema-white reference and a
100–500 nit presentation band.

---

## Photometry credibility cycle — `core/photometry.py`, `core/coverage.py`

### Lumens derate chain

Replaces "full rated lumens assumed" with an explicit, cited derate chain:
- **Production lower limit:** default 80%, based on ISO/IEC 21118:2012 §4.1/§6.1
  which defines datasheet light output as a production average and sets the
  minimum allowable delivered output at ≥ 80% of specification.
- **Picture mode factor:** default 0.85, representing calibrated/standard color
  mode relative to uncalibrated peak dynamic boost.
- **Aging factor:** default 0.80, modeling lamp or laser flux degradation down
  to target service point or end-of-life replacement threshold.
- **Fitted lens transmission factor:** optical transmission factor from the
  selected lens in the spec library (typically 0.75–0.92).

Every report outputs **rated**, **typical**, and **worst-case** performance
bands across both luminance (nits) and illuminance (lux), transforming estimates
into audit-proof margin statements.

### Gamma-shaped blend ramp & overlap guidance

Upgrades linear blending to industry-standard soft-edge gamma curves:
- **Gamma exponent:** parameter (default 1.0, range 0.5–1.5) matching the
  Dataton WATCHOUT soft-edge gamma convention.
- **Luminance error prediction:** computes theoretical mid-zone deviation
  `2^(1 - gamma) - 1.0` (e.g. +14.9% center hot spot for γ=0.8, -12.9% dip for γ=1.2).
- **Overlap guidance:** evaluates adjacent overlap fraction against industry
  rules (<5% difficult to blend seamlessly, 5–10% tight, 10–20% recommended,
  >20% generous).
- **On-site calibration checklist:** provides an explicit checklist for
  grayscale-ramp verification (25/50/75/100% white), black-level matching, and
  color gamut calibration.

### Ambient-light effective contrast — AVIXA ISCR

Computes on-screen contrast in real rooms from user-entered ambient illuminance
(lux) measured at the screen surface:
- **Veiling luminance:** `L_amb = E_amb · gain / π` in nits.
- **Per-cell effective contrast:** `(L_white + L_amb) / (L_black + L_amb)`
  accumulated over the raster using each projector's native contrast
  (`ProjectorSpec.native_contrast`, labeled native, not dynamic).
- **AVIXA ISCR Categories:** reference categories per ANSI/AVIXA V201.01:2021
  (Passive Viewing, Basic Decision Making, Analytical Decision Making, Full
  Motion Video) alongside mandatory disclaimer:
  *"Structure per ANSI/AVIXA V201.01:2021; this tool does not certify compliance; numeric tiers not reproduced."*

### ANSI/IEC 9-point vocabulary output

Samples the active coverage area at the ANSI/IEC 61947-1 / ANSI IT7.228 3×3
equal zone centers:
- Reports total light output (`9-point average illuminance · area`) in datasheet lumens.
- Reports center-to-corner uniformity ratio (`min(corners) / center`), 4-corner
  average to center, and 9-point min/max uniformity in both nits and foot-lamberts.
- Mandatory disclaimer: *"Model output in ANSI/IEC vocabulary; calculated from geometric simulation, not physical laboratory measurement."*

---

## Structured handoff export — `core/report_export.py`, `operators.py`

Direct export of all analysis results to structured, machine-readable formats:
- **JSON (`schema_version: 1`):** Complete tree containing wall geometry,
  raster coverage, gaps, blend zones with guidance, photometry stats and derate
  bands, effective contrast, 9-point sample coordinates and metrics, and rigging
  schedules.
- **CSV:** Tabular export suitable for Excel or CAD schedules, including mount
  coordinates (x, y, z), aim angles (yaw, pitch, roll), throw distances, image
  dimensions, lens shift percentages, lumens, and weight.
- **3D World Corners:** Each projector's 4 image corners on the wall in world
  coordinates, providing targets for media server processors (TouchDesigner,
  Resolume).

---

## Warp & corner-pin grid export — `core/warp_export.py`, `operators.py`

Per-projector mapping from the wall to each projector's image, for feeding
media processors (TouchDesigner, Resolume, media servers). Derived entirely
from the existing back-projection (`Footprint.image_uv_of`).

- **JSON (`schema_version: 1`):** per projector, a lattice over the
  projector's illuminated wall region — each vertex carries its wall
  coordinates `(s, z)` in metres, its world position, and the normalized
  image UV that lands there (`(0, 0)` at the image's top-left; vertices the
  image does not reach are marked invalid with no UV). Corner-pin points
  carry their image UVs and are flagged incomplete when any image corner
  misses the wall. The wall's arc coordinate `s` is unwrapped on full-circle
  walls and may fall outside `[0, arc_length]` for continuity.
- **OBJ:** one UV-mapped mesh object per projector in world-space metres.
  Faces are emitted only where all four lattice corners are illuminated;
  unused vertices are omitted.
- **Honesty (ADR 0002):** every export carries the disclaimer that these are
  *design-phase geometric targets computed from the add-on's model — not a
  calibration substitute*. On a curved wall four corner points can never
  represent the projected geometry — use the mesh grid. Occlusion is
  deliberately not part of the mapping: occluders change what gets
  illuminated, not where the processor's output geometry maps.

---

## DISCAS / Per-seat viewer audit — `core/discas.py`

Implements display sizing mathematics per ANSI/INFOCOMM V202.01 (DISCAS):
- **Basic Decision Making (BDM):** Legibility distance based on 10 arcminutes
  visual subtension for `% Element Height` (default 3.0%):
  `D_max = (H · %EH / 100) / tan(10 arcmin)`.
- **Analytical Decision Making (ADM):** 1-arcminute single-pixel visual acuity
  limit based on display vertical resolution (e.g. 1080p, 4K):
  `D_max = (H / V_res) / tan(1 arcmin)`.
- **Closest viewer limit:** Minimum recommended distance `D_min = H · 1.0`.
- **Per-seat off-axis audit:** Computes viewer distance, horizontal off-axis
  angle relative to screen normal, and perceived luminance — view-independent
  for the (default) Lambertian case, shaped by the selected gain profile for
  peaked/retroflective screens (see the angle-aware gain model below) —
  auditing scene objects (`Viewer*`, `Seat*`) or user-entered farthest viewer
  distance.
- Mandatory disclaimer: *"Calculated per ANSI/INFOCOMM V202.01 (DISCAS) geometric equations; evaluates mathematical sizing limits, does not certify human vision."*

---

## Angle-aware gain model — `core/gain.py`, `core/discas.py`, `core/coverage.py`

Replaces the scalar Lambertian gain assumption with a `gain(viewing_angle)`
profile family per SMPTE RP 94-2000, *Gain Determination of Front Projection
Screens*:

- **Lambertian (default):** the scalar model — constant gain at every viewing
  angle; luminance is view-independent.
- **Peaked:** specular lobe centred on the screen normal — peak gain on-axis,
  half-gain angle (the datasheet number integrators quote), off-axis floor
  gain. The curve is a cosine-power idealisation fitted so that
  `gain(half-gain angle)` equals exactly half the peak.
- **Retroflective:** the same curve with the lobe centred on the direction
  toward the projector (glass-beaded screens return light to the source);
  per-seat angles are measured from that axis.

RP 94-derived warnings:

- Viewers outside the half-gain cone are flagged by name with their perceived
  luminance.
- Peak gain above ~1.3 on a flat wall is flagged (curved screens recommended
  above 1.3) via the Surface ABC `curvature_radius` hook; curvature itself is
  flagged, never modelled.

Per-seat correction: the DISCAS audit's perceived luminance is view-independent
for Lambertian screens (the earlier `L_mean · cos θ` falloff was not Lambertian
behaviour and was corrected in this increment); peaked/retroflective profiles
apply `factor(θ)` to it, so "seat 14 at 31° off-axis" now answers with the
screen's actual reflectance shape.

**Honesty (ADR 0002):** the curves are three-parameter parametric idealisations
at **medium confidence** — vendor gain-curve charts (Stewart, dnp, Elite) were
not consulted. The disclaimer rides with every surfaced number: the report
assumption line, the report's gain-profile line, the JSON/CSV export, and the
panel note. On-site gain verification is always required.

---

## What is not here

Phase synchronisation, thermal modelling, ambient-light AI, VR/AR, and CAD
import were advertised by v0.1 and do not exist. See
[ADR 0002](../adr/0002-removed-claims.md).
