# ADR 0005: Realtime parametric scene via Geometry Nodes and debounced core sync

**Status:** Accepted
**Date:** 2026-08-26

## Context

The add-on stores its inputs as Blender properties, but most of the scene is
only eventually consistent with them:

- editing a generated wall changes `pj_wall`, while its visible mesh is rebuilt
  only when another operator calls `sync_generated_wall_mesh`;
- array settings affect camera objects only after **Plan Projector Array**;
- projector and analysis settings affect overlays and reports only after
  **Calculate Coverage**.

That makes the controls feel like an operator form rather than a parametric
Blender tool. The desired interaction is explicit: after a target is selected,
**all dependent scene content updates automatically** when any relevant control
changes. Sam selected “Always live everything” when asked whether automatic
updates should stop at geometry, placement, or include analysis.

Geometry Nodes is well suited to responsive generated geometry, but it cannot
replace the Python planner. Projector cameras are Blender objects, and array
placement, ray intersections, coverage, and photometry already have one tested
implementation in `core/`. Reimplementing those formulas as node graphs would
violate ADR 0001.

A local timing probe of the default three-projector case measured array planning
at roughly 25 ms median / 36 ms p95 and footprint plus coverage at roughly
99 ms median / 129 ms p95 before Blender overlay creation. Running the full
chain on every slider tick would visibly stall interaction.

## Decision

### 1. Properties and `core/` remain the source of truth

`pj_wall`, `scene.pj`, and `pj_projector` properties are the persisted user
inputs. `core/` remains the only implementation of projection mathematics.
Neither Geometry Nodes nor Blender drivers duplicate throw, placement,
intersection, coverage, or photometry formulas.

`wall_from_object` continues rebuilding the analytic `Surface` from properties
for generated walls. Imported mesh targets continue using their depsgraph-
evaluated mesh and BVH under ADR 0004.

### 2. Geometry Nodes owns generated wall display geometry

One add-on-owned, versioned Geometry Nodes group produces both flat and curved
generated walls. Per-object modifier inputs cover wall kind, width, yaw,
radius, height, arc limits, segment count, and concavity.

Modifier inputs are driven from `obj.pj_wall.*` through RNA drivers. Blender's
dependency graph therefore updates the wall mesh immediately while a value is
edited, without a Python property callback rebuilding mesh datablocks.

The group is an implementation detail:

- its modifier sockets are hidden from the modifier panel so the Projection
  sidebar remains the one control surface;
- its node group, modifier, and generated objects carry the existing ownership
  metadata plus a schema version;
- creation and migration are idempotent;
- the object mesh datablock is stable instead of being replaced after edits.

Imported user meshes never receive or surrender geometry to this node group.

### 3. One debounced synchronization module owns derived scene state

A Blender-facing `live_sync` module exposes one small interface:

- request a refresh at wall, array, projector, or analysis scope;
- synchronously refresh now for operators and tests;
- suspend requests while the synchronizer writes computed properties.

Property callbacks only enqueue a dirty scope. They do not call operators or
perform heavy Blender work. A non-persistent `bpy.app.timers` callback coalesces
changes for approximately 200 ms, then uses the direct data API and existing
`core/` functions to update:

1. the generated projector array and camera data;
2. individual projector camera configuration;
3. footprints, frustums, gaps, blend zones, computed fields, and report text.

A wall or array change implies analysis refresh. An analysis-only setting does
not unnecessarily re-plan the array. Requests made while synchronization is
writing results are suppressed to prevent feedback loops.

Once a valid target wall exists, dependent generated content is created as
needed; the user does not have to press Plan or Calculate first. Manual
projectors remain additional projectors and are never deleted by array sync.
Only add-on-owned array cameras may be replaced or removed.

### 4. Operators become explicit adapters over the same implementation

The existing Plan and Calculate operators remain for scripting, recovery, and
backward compatibility, but call the same synchronization module with no
second implementation. In the UI they are presented as explicit refresh
controls rather than required workflow steps.

### 5. Live failures preserve the last valid derived scene

Slider edits can pass through temporarily invalid states. If planning or
analysis raises `ProjectionError`, synchronization keeps the last valid
cameras, overlays, and report, records the live error on the scene, and stops
that refresh. The panel shows the error immediately. The next valid edit clears
it and refreshes normally.

Unexpected exceptions are logged with context and also leave the last valid
derived scene intact. They are not silently treated as user input errors.

### 6. Verification is behavioral, not node-topology based

Plain CPython tests continue exercising `core/` through its existing
interfaces. Add-on contract tests verify that update callbacks never call
operators and that orchestration has one implementation.

Headless Blender acceptance verifies:

- changing each generated-wall property changes evaluated geometry without an
  explicit sync call;
- the underlying mesh datablock remains stable;
- changing array controls creates/moves/resizes owned cameras after the timer;
- changing projector or analysis controls refreshes evaluated camera data,
  overlays, computed fields, and report;
- invalid edits preserve the last valid scene and expose a live error;
- enable/disable/re-enable and file reload do not duplicate node groups,
  modifiers, drivers, timers, or handlers.

Tests assert geometry and scene behavior, not internal node positions or names.

## Consequences

- **Good:** controls behave like a procedural Blender system; generated wall
  edits are frame-rate dependency-graph updates; every derived result converges
  automatically without buttons.
- **Good:** `core/` remains bpy-free and the only maths implementation.
- **Good:** stable mesh datablocks avoid allocation churn and preserve object-
  level links better than replacement meshes.
- **Cost:** the Blender adapter gains an owned node graph, driver migration, a
  dirty-scope scheduler, and explicit feedback-loop protection.
- **Cost:** full live analysis settles after a short idle delay rather than on
  every intermediate slider tick.
- **Risk:** timers and file reloads can duplicate work if registration is not
  idempotent; mitigated by one module-owned timer flag, non-persistent timers,
  ownership tags, schema versions, and reload smoke tests.

## Rejected alternatives

- **Put all maths in Geometry Nodes.** This duplicates the tested `core/`
  implementation, cannot create real camera objects cleanly, and makes reports
  and numerical verification harder.
- **Python mesh rebuilds from every property callback.** RNA update callbacks
  may run in threaded contexts, mesh replacement allocates constantly, and the
  result still does not solve cameras or analysis safely.
- **Geometry Nodes for proxy projectors only.** A proxy scene that disagrees
  with the real cameras would be fast but dishonest.
- **Live geometry with manual analysis.** Lower cost, but explicitly rejected in
  favour of “Always live everything”.

## Related

- ADR 0001 (one canonical product and one maths implementation)
- ADR 0003 (the `Surface` seam consumed by planning and analysis)
- ADR 0004 (imported meshes use depsgraph-evaluated geometry and an injected BVH)
