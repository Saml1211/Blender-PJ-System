# Next feature increments — candidate shortlist (v0.5.0 → v0.6 planning)

**Status:** Accepted & Landed (Increments #1, #2, #3a, #3b, #3c, #4 Phase 1, #5 completed in main)
**Date:** 2026-09-16
**Base:** `blender_projection_system` v0.5.0 at `2f98a72`
**Method:** Four independent research lanes — (1) user value & workflows, (2) competitive/industry landscape, (3) technical feasibility vs. architecture, (4) physics/standards credibility — each producing 5+ distinct candidate increments, an internal comparison, and an explicit rejected-ideas list, then cross-compared here. Full source lists are in the appendix. Lane execution note: the first subagent wave failed on a provider quota (all four lanes); all lanes were re-run on a working model and one lane required a second relaunch to deliver its full report. Two research claims are flagged medium-confidence by their lanes and are marked inline.

**How to read this document.** Sections 1–3 are the recommended shortlist. Section 4 is the **parked ideas** register — ideas that lost *this* cycle, each with the reason and an explicit **revisit trigger**, kept deliberately so they are not lost. Section 5 is the dependency-ordered sequence. Every increment is constrained by the standing ADRs: maths stays in the bpy-free `core/` (ADR 0001), assumptions are stated and unsupported claims are loud (ADR 0002), new surface/analysis behaviour rides the `Surface` ABC and the injectable ray-caster (ADR 0003/0004), and derived state inherits the debounced live sync (ADR 0005).

---

## 1. Where the research lanes independently converged

The strongest signal in the exercise: lanes using **different evidence bases** (practitioner forums, competitor feature maps, the repo's own seams, standards documents) independently arrived at the same shortlist heads.

| Candidate | User value / workflow | Competitive landscape | Technical feasibility | Physics / standards |
|---|---|---|---|---|
| **Occlusion / line-of-sight check** | Verbatim practitioner wish: "obstacles in the light path" (r/video_mapping) | Top pick — "worst failure mode for an engineering tool" | Top pick — plugs into the ADR 0004 ray-caster seam | Implied gap (noted as scope-creep risk for viewer audits) |
| **Projector / lens spec library** | "Actual projectors from a library of vendors" — user language | Top pick — "#1 dismissal trigger"; every free competitor ships a database | Cheap (S/M), unblocks other items | Deprioritised (data lane, not physics) — but endorsed indirectly |
| **Ambient contrast + lumens derates + standards vocabulary** | Numbers must survive consultants (PISCR/DISCAS/foot-lamberts) | Epson's free tool already models lens loss — we would read *optimistic* | The "honest version" of ambient derates is S effort | Top pick — the industry's most-contested number |
| **Structured export (JSON/CSV + rigging schedule)** | Exports toward calibration & client-facing artifacts | Bridges the design→documentation chain (AVIXA D401.01) | Cheapest total effort for the largest deliverable value | — |

Two independent *rejections* also converged: both web lanes separately rejected render-engine-based photometry (Depence-class and Cycles-based), and both identified the unwinnable fronts (photorealism, documentation suites, calibration hardware) as belonging to competitors with structural advantages.

---

## 2. The prioritized shortlist

Effort scale: **S** = single module + tests; **M** = 2–4 modules or a new Blender-layer surface; **L** = cross-cutting or new subsystem.

### #1 — Occlusion & line-of-sight check *(S/M — Landed in `a831e50`)*

**What.** For each coverage raster cell, cast from the projector aperture toward the surface point through a BVH built over user-selected occluder objects. Flag occluded cells in the coverage raster, report the occluded sample fraction per projector, and visualise shadowed cells (hatched or red overlay).

**Rationale.** "No occlusion. If a column stands between projector and wall, this add-on does not know" is the loudest stated gap in the README — and the worst failure *class* an engineering tool has: a silently wrong answer. Columns in lecture halls and houses of worship are routine; a column shading a blend zone can flip a real design decision.

**Expected impact.** Trustworthy analysis in obstructed rooms; also catches self-shadowing on curved walls.

**Effort.** S/M. The injectable `RayCaster` protocol (ADR 0004) exists exactly for this: the Blender side builds a BVH over occluders and injects it, matching the mesh-target pattern. Touches: `mesh_surface.py` (a blocking-hit variant), `scene_sync._analysis_inputs`, properties (occluder list), one overlay.

**Risks / tradeoffs.** False positives on the target wall itself (exclude it from the occluder set); the pure-Python test path needs synthetic occluder meshes; BVH cost on dense rasters (acceptable in Blender; tests use the pure-Python caster).

**Builds on.** ADR 0004's injection seam; the analysis-scope debounce gives live occlusion updates for free, including last-valid-state preservation on invalid edits.

### #2 — Projector & lens spec library *(M — Landed in `0c8c380`)*

**What.** A local, versioned spec library (JSON/CSV, user-extensible) keyed by model: lumens, contrast, lens lineup with per-lens throw-ratio range, horizontal/vertical shift range, lens transmission factor, weight, plus a `source_url` per row and a `verified` flag. A model picker populates and validates the throw/shift/lumens inputs; out-of-range entries warn rather than silently clamp.

**Rationale.** Every free competitor (Christie, Panasonic Throw Distance Calculator, Epson Throw Distance Simulator, Barco, ProjectorCentral's 12,500+ models) ships a spec database; "all TR/shift/lumens entered manually" is the first thing an AV professional notices. It is also verbatim practitioner demand. It *unblocks* #3's lens-transmission factor and #4's export provenance.

**Expected impact.** Hard validation instead of plausible-wrong numbers; stops datasheet transcription; makes the add-on credible to anyone specifying real hardware.

**Effort.** M — no new mathematics; the real cost is data curation and the validation UI. Start with a small curated starter set (common Christie/Barco/Panasonic/Epson models), per-row source URLs, and a CSV import so users add their own models without code.

**Risks / tradeoffs.** Wrong rows are worse than no rows — mitigate with the `verified` flag, cited sources, and range warnings. Spec data are facts (not creative content) but keep sources cited.

**Builds on.** Property groups and report machinery; a pure-`core/` schema is trivially testable under CPython.

### #3 — Photometry credibility cycle *(three S landings, sequential — Landed in `83dd189`, `d1ad64d`, `03c56bc`)*

**3a — Lumens derate chain + blend-ramp gamma (S — Landed in `83dd189`).** Explicit, cited factors replacing "full rated lumens": production lower-limit (default 80%, per the ISO/IEC 21118 ≥80%-of-spec rule¹), picture mode, lamp ageing/optics. The report shows rated / typical / worst-case, and every derived figure carries the band. Turns "6,000 lm assumed" into an audit-proof margin statement. Includes gamma-shaped blend ramp with exponent parameter (default 1.0, range 0.5–1.5 per Dataton WATCHOUT soft-edge gamma), theoretical mid-zone error prediction, overlap guidance (<5%, 5–10%, 10–20%, >20%), and on-site validation checklist.

**3b — Ambient-light effective contrast (M — Landed in `d1ad64d`).** Ambient illuminance at the screen (user-entered from a survey) × screen gain → veiling luminance; per-cell effective contrast raster `(L_white + L_amb) / (L_black + L_amb)` plus min/mean/worst in the report. This is the number design reviews actually argue about, computed with the same two-formula model working integrators publish publicly. AVIXA ISCR category *names* ("Basic Decision Making", "Passive Viewing", "Full Motion Video", "Analytical Decision Making") may label reference points — with an explicit disclaimer: "structure per ANSI/AVIXA V201.01:2021; this tool does not certify compliance; numeric tiers not reproduced."

**3c — ANSI/IEC 9-point vocabulary output (S — Landed in `03c56bc`).** Sample the existing coverage raster at the ANSI/IEC nine-zone positions (optionally 13/25-point); report light output (9-point average × area) and center-to-corner uniformity ratio in datasheet terms, in both nits and foot-lamberts. Tiny effort, outsized credibility: Draper's free planner anchors on AVIXA standards — this is table stakes in the category.

**Rationale.** The tool's weakest honesty point is zero-ambient luminance with full rated lumens and a uniform frustum. Three lanes independently flagged that a tool reporting *higher* lux than Epson's free web tool (which models lens transmission loss) will be read as optimistic — and oversell installs. #3a/3b/3c convert the already-stated assumptions 1, 2, and 4 from fine print into *inputs*.

**Expected impact.** The epistemic status of every number changes from "a Blender script's estimate" to "first-order calculation in the industry's units, grids, derates, and standards vocabulary, with assumptions stated."

**Effort.** Three S landings sharing the photometry/report machinery; land 3a before the blend-gamma work (same files), 3b before #5's full version.

**Risks / tradeoffs.** The uniform-ambient assumption must be stated (ADR 0002 wording); ISCR tier names invite a "certified" misreading — the disclaimer rides with the value, not the manual; users may enter native *dynamic* contrast (label the field "native, not dynamic"); the 80% anchor is medium-confidence (mirrored PDF¹) — cite it and allow override; wording for 3c must be "model output in ANSI/IEC vocabulary", never implying *measured* ANSI lumens.

**Builds on.** `core/photometry.py` multiplicative inputs; the coverage raster it already produces; the report pipeline.

### #4 — Structured handoff export: analysis JSON/CSV + rigging/mount schedule *(S/M, phase 1 — Landed in `a84e162`; phase 2 — Landed in `dd7820b`)*

**What.** Phase 1: serialize the existing report dataclasses (`CoverageReport`, `BrightnessReport`, `ArraySyncResult` placements) to JSON and the coverage raster to CSV, plus a rigging table (unit, mount x/y/z, throw, aim fraction) appended to report and CSV. One new operator, output path via the Blender file browser. Phase 2: per-projector corner/warp grids derived from the existing back-projection, exported toward processors (TouchDesigner/Resolume/media servers) — worded honestly as design-phase targets, not calibration.

**Rationale.** Clipboard text is where good numbers go to die. The analysis data is already structured (`format_report` merely flattens it). AVIXA D401.01 makes BOM/drawings/schedules the deliverable chain; XTEN-AV's entire pitch is that documentation churn is the integrator's biggest cost. For the owner's day job specifically, these are artifacts that sit next to an LLD's cable schedule.

**Expected impact.** Numbers enter the real workflow instead of being re-typed by hand from report text.

**Effort.** S/M for phase 1 (one operator + a small pure-`core/report_export.py`, trivially testable); M/L for phase 2 (formats, the generated warp image, schema stability).

**Risks / tradeoffs.** Format sprawl (pick two formats, document them); export schema must stay stable across versions; warp-grid fidelity claims must stay honest (ADR 0002 wording matters).

**Builds on.** The `copy_report` pattern; `footprint.py` back-projection already produces the corner/warp points; land after #2 so export rows carry resolved spec provenance.

### #5 — DISCAS / per-seat viewer audit *(S/M — Landed in `3412abd`)*

**What.** A farthest-viewer DISCAS check (ANSI/INFOCOMM V202.01: BDM/ADM content type, %element height) from viewer positions in the scene; optionally a per-seat off-axis luminance audit ("seat 14 at 31° off-axis sees 78 nits"). The luminance-only version can ship before #3b's contrast lands.

**Rationale.** The only uncontested standards flank in the competitive landscape — no surveyed tool performs DISCAS conformance inside a 3D planning scene; AVIXA ships it as a separate spreadsheet and integrators do it by hand afterwards. Directly relevant to LLD review workflows.

**Expected impact.** Turns "the wall is uniformly 120 nits" into "the end of the front row at 31° off-axis sees 78 nits" — the sentence that prevents post-install disputes.

**Effort.** S/M — the formulas are published arithmetic; effort is the decision-flow UI and farthest-viewer selection. Implement against the standard's own worked examples with tests.

**Risks / tradeoffs.** DISCAS edge rules (viewing-ratio bands, ADM content categories) must be implemented exactly or the "conformance" wording violates ADR 0002; seat-definition UX must stay bounded (a viewer line + count first) and must *not* drift into sightline territory — that is #1's job.

**Builds on.** #3b's contrast for the full version; `core/pose` and the Surface ABC for the per-seat geometry.

---

## 3. Differentiator bets and fold-ins

### Measured-vs-predicted calibration loop *(M — keep on the board, not this cycle)*

The user records a handful of on-site lux readings (from a $100 meter) against surface positions; core fits a scalar correction, applies it to the analysis, and keeps the residual visible in every report. No tool in the competitive survey closes the design→as-built loop. It weaponises the honest-claims ADR — instead of promising accuracy, the tool learns the room and reports its own residual error. **Why not now:** narrowest audience of the shortlist and the most UX-sensitive (marking measured positions). **Risk if built:** garbage readings in, garbage calibration out — require ≥3 readings, report dispersion, and never claim the photometry is "verified".

### Blend-ramp gamma exponent + blend design package *(S — fold into the photometry cycle after 3a)*

Upgrade the linear blend ramp to the industry-standard gamma-shaped ramp (exponent parameter, default 1.0, range 0.5–1.5 mirroring WATCHOUT's soft-edge gamma), plus a blend-design output per adjacent pair: recommended overlap as % of projected width (against the 10–20% common / <5% hard-to-blend guidance), per-cell predicted luminance error across the zone, and an on-site calibration checklist (grayscale-ramp validation at 25/50/75/100% white; black-level and colour matching flagged as tasks the tool deliberately does not simulate). The curve is perceptual, so "predicted flat" ≠ "calibrated flat" — the report says validation is always on-site, which satisfies ADR 0002 by construction.

---

## 4. Parked ideas — considered and rejected for this cycle (with revisit triggers)

Kept deliberately: several of these are attractive and may be worth building later. Each entry records why it lost **now** and what would need to be true to revisit it.

### 4.1 Photorealistic projection previz (Depence / Disguise class)

**Why it lost.** Depence's Stage module alone is €1,900 dongle-locked with a rendering engine purpose-built for show simulation; Disguise owns the server ecosystem. Blender already renders for free, so the "pretty picture" is available without us. Competing here abandons the engineering-planning lane where this add-on is effectively alone (the OSS survey found nothing doing coverage raster, photometry, or array planning).

**Revisit trigger.** If the planning core is complete (#1–#4) and there is demonstrated demand for a *free* engineering-grade previz (e.g. requests for textured/coloured coverage visualisation rather than engineering overlays), a viewport-shading mode that *visualises* the photometry model — not a ray-traced simulation — could be a legitimate middle ground that keeps ADR 0002 (it visualises the stated model, it does not fake a render's authority).

### 4.2 Render-engine-based photometry ("just render it" with Cycles)

**Why it lost.** Tonemapping, exposure, spectral approximations, and physically-based settings that no projector datasheet matches make render output non-comparable to any standard (ANSI 9-point, SMPTE RP 94 conventions). It would silently overpromise measurement-grade accuracy and duplicate `photometry.py`'s role — an ADR 0001/0002 defect. Rejected independently by two lanes.

**Revisit trigger.** Almost never as a *reporting* source. Conceivable someday as an optional *relative* visual comparison (this array vs that array, same engine, same settings) clearly labelled non-quantitative. Do not mix its output into the numeric reports.

### 4.3 Camera-based calibration / auto-alignment (Mystique / OmniCal class)

**Why it lost.** Requires camera hardware, vendor projector-control protocols, and an install-phase workflow. Zero of the pure-`core/`, headless-test architecture can validate camera code; Christie gives Mystique Operate away and still sells Premium as a hardware/service package.

**Revisit trigger.** If a real installation job provides hardware access and a concrete projector protocol (e.g. PJLink-adjacent geometric feedback), a *measurement import* mode (bring calibration data in, compare to prediction) is the honest slice — not live camera control.

### 4.4 Full documentation suite (XTEN-AV class: BOM generation, signal-flow, rack layouts, proposals)

**Why it lost.** XTEN-AV is an AI-funded subscription company attacking exactly this with AutoCAD/Visio import and dealer-pricing databases; a side-project clone is years behind on the hard parts (symbol libraries, pricing). The valuable slice — machine-readable export of *this tool's* data — is kept as #4.

**Revisit trigger.** If #4's export schema gains adoption, a thin bridge (e.g. generating rows that a real BOM/spreadsheet tool ingests) is worth having; a full suite is not.

### 4.5 Domes, columns, folded surfaces — arbitrary non-frontal projection targets

**Why it lost.** ADR 0004's loud rejection is deliberate: non-frontal geometry has no single-valued `(s, z)` parameterisation without a full 3D rasterisation of the most-tested module (`coverage.py`), and the realistic integrator case (walls, ceilings) is covered by the frontal heightfield. Depence/Disguise own immersive geometry at the high end.

**Revisit trigger.** A genuine dome/planetarium job arriving — exactly the condition ADR 0004 itself names ("revisit only if a real dome/column job arrives"). The #1 occlusion work will already exercise the caster seam, which is the natural foundation.

### 4.6 Multi-wall / multi-zone scenes

**Why it lost.** The single `scene.pj.target_wall` assumption is woven through operators, `scene_sync`, UI, and the smoke test — an L cross-cutting rename, not a module. Nothing else on the shortlist needs it yet.

**Revisit trigger.** The first real job with two coordinated walls (e.g. an L-shaped room or a wall + ceiling pair). Design note for that day: the per-projector spec path (`spec_from_object`) is already per-object, so the hard part is the scene model, not the maths.

### 4.7 Rotated / scaled generated walls

**Why it lost.** The honest path already exists: apply transform → *Set as Target Wall* → mesh BVH path. Teaching the generated `CylindricalWall`/Geometry-Nodes walls rotation breaks the vertical-axis and frontal assumptions for marginal gain.

**Revisit trigger.** If users repeatedly hit the apply-transform step (support signal), consider a one-click "bake to target" operator rather than generalising the analytic surfaces.

### 4.8 PDF / rich stakeholder report (VIOSO-style automated reports)

**Why it lost.** Needs a rendering/report dependency or headless Blender compositor work; CSV/JSON covers the engineering need. Two lanes flat-rejected it for this cycle.

**Revisit trigger.** Vendors are explicitly pitching "static PDFs and screenshots are increasingly inadequate" and shipping automated PDF reports — stakeholder artifacts are a real lever (user-value lane, finding 8). After #4's schema stabilises, a generated HTML (print-to-PDF) report is a legitimate stretch: data-driven, no rendering engine in the dependency tree, and the honest-claims footer ships in the template.

### 4.9 ALR (ambient-light-rejecting) screen modelling; "ISCR-certified" checkbox; inter-reflection radiosity; genlock / colour matching

**Why they lost.** ALR needs measured angular (BRDF-like) data — a scalar hack would *flatter* ALR screens; ISCR numeric tiers live in a purchased standard and conformance is measured on-site — a software "certified" checkbox would grant a certification the tool cannot; inter-reflection is a second-order effect dominated by direct ambient-on-screen light (the added complexity is exactly the fake precision ADR 0002 prohibits); genlock/colour is deliberately signal-chain scope.

**Revisit trigger.** ALR: if vendor measured gain/angle curves become available in a usable format, feed them to the angle-aware gain profile (see 4.10) rather than inventing scalars. The others: no realistic trigger; they are parked permanently unless the project's scope statement changes.

### 4.10 Angle-aware gain model on the Surface ABC *(adjacent S/M idea worth keeping visible)*

Replace the scalar Lambertian gain assumption with a `gain(viewing_angle)` profile family: Lambertian (today's model), retroflective, and a peaked profile parameterised by peak gain + half-gain angle (SMPTE RP 94 is the primary source; half-gain is the datasheet number integrators quote). Emit RP 94-derived warnings: viewers outside the half-gain cone; peak gain > 1.3 on a flat wall (RP 94 recommends curved screens above 1.3 — flag, don't model curvature). **Why not in the shortlist:** it matters mainly for gain-screen installs and its parametric curves are idealisations (disclose as three-parameter models). **Revisit trigger:** #3's photometry cycle landing well, plus 2–3 vendor gain-curve charts (Stewart, dnp, Elite) to validate the profile shape — it then becomes the natural next `photometry.py` increment and the foundation for the per-seat audit's off-axis correction.

---

## 5. Sequencing

```
#1 Occlusion (independent — land first, any time)
#2 Spec library
   └→ #3a derate chain → #3b ambient contrast → #3c ANSI/IEC vocabulary  (one photometry cycle; blend-gamma after 3a)
        └→ #4 phase 1 export (after #2 for provenance) → #4 phase 2 warp grids
             └→ #5 DISCAS / per-seat audit (needs #3b for full value)
```

- **#1** is independent of everything; it is also the correctness guard for every number the rest of the list produces, so earliest is best.
- **#2 before #3's lens transmission and #4's provenance.**
- **#3 as one cycle** (shared files: `photometry.py`, report machinery), 3a → 3b → 3c, blend-gamma folded in after 3a.
- **#4 phase 1** is S/M and can interleave after #3a if a deliverable deadline demands it.
- **#5** waits for #3b; the luminance-only variant may ship earlier.

Every increment above stays inside the ADR envelope: maths in bpy-free `core/` (ADR 0001), stated assumptions and loud rejections (ADR 0002), the Surface ABC and injectable ray-caster seams (ADR 0003/0004), and free live updates via analysis-scope debounce (ADR 0005).

---

## Appendix — research sources by lane

### Lane 1 — User value & workflow (web)

- [Inavate Magazine — "From fragmented workflow to virtual site surveys: why projection design needs a rethink" (VIOSO Experience Designer launch piece; pain narrative credible but vendor-framed)](https://www.inavateonthenet.net/features/article/from-fragmented-workflow-to-virtual-site-surveys-why-projection-design-needs-a-rethink) — workflow-fragmentation pain; competitor's full feature set (GPU coverage/brightness/pixel-density/occlusion simulation, vendor projector libraries, OBJ/FBX/GLTF import, shareable links, automated PDF reports).
- [r/video_mapping — "Software for simulating and planning projector setup"](https://www.reddit.com/r/video_mapping/comments/1cqyco3/software_for_simulating_and_planning_projector/) — verbatim practitioner wish-list ("replicate the actual room, obstacles and projection surface… actual projectors from a library of vendors… check for luminosity, spatial distortion and obstacles in the light path and also mounting angles").
- [r/projectors — preflight planning tool thread](https://www.reddit.com/r/projectors/comments/1tp79fv/would_a_projector_preflight_setup_planning_tool/) and [r/VIDEOENGINEERING — planning tool thread](https://www.reddit.com/r/VIDEOENGINEERING/comments/1sa2qpo/built_a_projection_planning_tool_that_tests/) — independent confirmation of pre-site-validation demand.
- [r/video_mapping — MappingKit V1 launch](https://www.reddit.com/r/video_mapping/comments/1tb4ha2/update_a_few_weeks_ago_i_asked_this_sub_to_beta/) and [r/Projection_Mapping — FieldLux](https://www.reddit.com/r/Projection_Mapping/comments/1torsy0/i_built_a_projection_preflight_tool_and_would/) — 2025–2026 competitor launches validating the niche; MappingKit author's counter-complaint that existing tools are "bloated" (simplicity-vs-depth tension to respect).
- [Draper Projection Planner 2.0](https://www.draperinc.com/projectionscreens/projectionplanner.aspx) and [AVToolsPro projector calculator](https://avtoolspro.com/projector-calculator) — free calculators anchor credibility on AVIXA PISCR/DISCAS and foot-lamberts.
- [Epson Projector Professional Tool](https://epson.com/Accessories/Projector-Accessories/Epson-Projector-Accessories/Epson-Projector-Professional-Tool-Software/p/Epson-PJ-Pro-Tool) and [Panasonic Visual Software Suite](https://docs.connect.panasonic.com/projector/products/vss/) — vendor tools stop at calibration/fleet management, not planning.
- [baptistejaze.com — mapping workflow guides (2D vs 3D, 3D scanning)](https://www.baptistejaze.com/en/blog/mapping-preparation-workflow) — practitioner workflow split; Blender-style geometry is the natural substrate of the 3D path.
- Blender add-on landscape: [ocupe/Projectors](https://github.com/ocupe/Projectors) (throw/shift objects only), [FTW3DForge Image Projector](https://extensions.blender.org/add-ons/ftw3dforge-image-projector/) (UV baking), [Eevee Projectors](https://extensions.blender.org/add-ons/eevee-projectors/) (fake lights) — no Blender-native AV planner exists.

### Lane 2 — Competitive & industry landscape (web)

- [Epson Throw Distance Simulator](https://epson.com/support/projection-distance-calculators) ([Europe TDS PDF](https://download.epson-europe.com/pub/download/6355/epson635525eu.pdf)) — models "brightness reduced due to loss by optical characteristics" (lens transmission loss).
- [Panasonic Throw Distance Calculator](https://docs.connect.panasonic.com/projector/calculator/tdc/index.html) (v2.78, 2026) and [Barco Lens Calculator](https://lenscalculator.barco.com/) — active manufacturer calculators; Barco outputs on-screen contrast/lux.
- [Christie projection calculator](https://www.christiedigital.com/projection-calculator/) and [Mystique](https://www.christiedigital.com/products/warping-blending/mystique/) — blend planning + install calibration split. *(Mystique's product page is JS-only; capability claims rest on search excerpts — medium confidence.)*
- [ProjectorCentral Projection Calculator Pro](https://www.projectorcentral.com/projection-calculator-pro.cfm) — 12,500+ model database.
- Syncronorm Depence licensing ([licensing](https://www.syncronorm.com/products/depence2/licensing), [Stage module €1,900](https://shop.syncronorm.com/software/2-D2stagemodule.html)); [Disguise Designer / projection mapping](https://www.disguise.one/en/solutions/projection-mapping) — the photorealism/calibration pole.
- XTEN-AV ([X-DRAW](https://xtenav.com/x-draw/), [XAVIA](https://xtenav.com/xavia/)) — the documentation-automation pole (AI BOMs, signal flow, AutoCAD/Visio import).
- AVIXA: [DISCAS V202.01](https://www.avixa.org/resources/standards/display-image-size-for-2d-content), [ISCR/V201.01](https://www.avixa.org/resources/standards/image-system-contrast-ratio), [D401.01 documentation requirements](https://www.avixa.org/resources/standards/documentation-requirements-for-audiovisual-systems) — the standards pole.
- OSS landscape: [Splash](https://splashmapper.xyz/en/index.html) (GPL calibration for shows); BlenderMap (dead since 2016); the GitHub survey surfaced **Blender-PJ-System itself as the top result in its niche** — the lane is effectively empty.

### Lane 3 — Technical feasibility (repo-only; no web sources)

Evidence: `README.md`; `docs/features/index.md`; `docs/adr/0003`, `0004`, `0005`; `core/surfaces.py`, `core/photometry.py`, `core/mesh_surface.py`; `scene_sync.py`; `operators.py`; test layout. Key architecture facts used: the Surface ABC makes new surface types leaf additions; the injectable `RayCaster` is the occlusion seam; reports are already structured dataclasses; `sync_analysis._analysis_inputs` is already per-projector (mixed-lens analysis nearly free, mixed-lens planning not); the single `scene.pj.target_wall` is a cross-cutting assumption.

### Lane 4 — Physics / standards credibility (web)

- SMPTE RP 94-2000, *Gain Determination of Front Projection Screens* — https://pub.smpte.org/pub/rp94/rp0094-2000.pdf (primary standard for gain; half-gain region; >1.3 gain → curved screens per RP 95).
- Dataton WATCHOUT 7, *Edge Blending* — https://docs.dataton.com/watchout-7-new/watchout/displays-and-outputs/edge-blending.html (soft-edge gamma 0.5–1.5, default 1.0; 10–20% overlap guidance; grayscale-ramp validation practice).
- Ambient contrast formulas: [Visual Displays Ltd projected-image-contrast calculator](https://visualdisplaysltd.com/resources/tools/useful-calculator-tools/projected-image-contrast-calculator); [projector contrast with ambient light calculator](https://codingace.net/physics/cal_projector_contrast_with_ambient_light.html) — effective contrast = (projected white + ambient reflected) / (native black + ambient reflected); measure ambient lux at the screen in the room's use state.
- [AVIXA ISCR (ANSI/AVIXA V201.01:2021)](https://www.avixa.org/resources/standards/image-system-contrast-ratio) — four content categories (ADM/BDM/Passive/Full Motion Video); numeric tiers not reproduced (purchased standard).
- [ANSI IT7.228 → IEC 61947-1 measurement lineage](https://3lcd.com/download/3LCDISOLumensWhitePaper.pdf); [IEC 61947-1:2002 sample](https://cdn.standards.iteh.ai/samples/8517/bec408983496450e8c12287edc508dae/IEC-61947-1-2002.pdf) — 9-point lumen measurement and center-to-corner uniformity vocabulary.
- [ISO/IEC 21118:2012](http://www.hiqiang.com/gm/kindeditor-4.1.7/attached/file/20130814/ISOIEC21118-2012.pdf) — spec-sheet values are production averages; lower limit ≥80% of spec for light output, contrast, and center-to-corner ratio. ¹ *Medium confidence: verified against a mirrored PDF only; original fetch failed.*
- [ProjectorCentral — "Brightness Uniformity: What It Means…and What It Doesn't"](https://www.projectorcentral.com/Brightness-Uniformity-Explained.htm); [Elite Screens screen terminology (half-gain)](https://elitescreens.com/screen-terminology/); [Barco — "What is screen gain?"](https://www.barco.com/en/news/entertainment-glossary/what-is-screen-gain).
- [Foot-lambert / SMPTE 196M (16 fL cinema reference)](https://en.wikipedia.org/wiki/Foot-lambert); [AVIXA DISCAS V202.01:2016/2026](https://www.avixa.org/resources/standards/display-image-size-for-2d-content).

**Disclosed gaps across lanes:** ISCR numeric tier values (purchased standard) — #3b ships without them or with user-entered targets; the ISO/IEC 21118 80% quote (mirrored PDF); real measured gain curves per commercial screen (would upgrade 4.10 from parametric to data-driven); VIOSO/MappingKit pricing; Reddit comment-thread sentiment (fetches blocked; OP quotes only).
