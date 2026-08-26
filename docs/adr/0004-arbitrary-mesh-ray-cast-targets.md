# ADR 0004: Arbitrary-mesh projection targets via an injectable ray-caster

**Status:** Accepted
**Date:** 2026-08-26 (accepted 2026-08-26)

## Context

The add-on can only project onto surfaces it generated itself: a
`CylindricalWall` or `PlanarWall` rebuilt from `pj_wall` properties by
`visualization.wall_from_object`. Imported geometry — a curved façade from an
architect's model, a stage set, an irregular feature wall — cannot be used as a
target, because there is no analytic `(s, z)` formula behind it.

ADR 0003 anticipated this: every downstream module (`footprint`, `coverage`,
`array`, `visualization`) operates exclusively through the `Surface` ABC
(`point_at`, `normal_at_s`, `intersect_ray`, `project_point`, `arc_length`,
`height`) plus four generic hooks. Graph evidence confirms it: the only direct
consumer of `measurement_wall` outside surfaces.py is `array.solve_standoff`;
`analyze_coverage` touches nothing cylinder-specific. A new surface type is a
leaf addition, not a pipeline change.

Three questions had to be settled before this could be designed:

### Q1 — Where does ray-casting live?

`core/` must stay importable without `bpy` (ADR 0001; the whole pytest suite
depends on it). Blender ships a fast C-backed `mathutils.bvhtree.BVHTree`, but
it is bpy-only, so it cannot be called from `core/surfaces.py`.

### Q2 — How does an arbitrary mesh get an `(s, z)` parameterisation?

`analyze_coverage` rasters over `[0, arc_length] × [0, height]` and asks the
surface for `point_at(s, z)` / `normal_at_s(s)`. An arbitrary mesh has no
single-valued answer to those questions unless we give it one.

### Q3 — How much of `coverage.py` survives?

If Q2 produces an honest `Surface` implementation, the answer should ideally
be "all of it".

## Decision

### 1. A `RayCaster` protocol in `core`; pure-Python default, BVH injected from the Blender layer

`core/mesh_surface.py` defines:

```python
class MeshRayCast(Protocol):
    def __call__(self, origin: Vec3, direction: Vec3,
                 max_distance: float) -> MeshHit | None: ...
```

- **Pure-Python implementation** (Möller–Trumbore over a uniform spatial grid)
  lives in `core/` and is the default. Sample counts are small — footprint
  casting is ~N×N rays per projector and coverage back-projection never casts
  at all (it uses `covers()`/`point_at`) — so pure Python is adequate for
  correctness-first tests and modest meshes.
- **The Blender layer may inject `BVHTree.ray_cast`** as the caster when
  rebuilding the surface from an object (`wall_from_object`). This keeps the
  heavy-mesh case fast without ever importing bpy inside `core/`.
- Deterministic tie-breaking in the pure-Python caster so tests are stable.

This is dependency inversion, not duplication: one `MeshSurface`, two casters,
chosen at construction time.

### 2. Parameterise the mesh as a frontal heightfield, and refuse what doesn't fit

At construction, `MeshSurface` takes the mesh's world-space vertices/triangles
plus a **frontal axis** (default: the dominant horizontal normal of the
triangle area-weighted distribution, overridable). It then:

1. Builds a bounding rectangle in the plane perpendicular to the frontal axis;
   `s` runs along its width, `z` along its vertical extent.
2. Casts parallel rays on an S×Z scan lattice, starting on the projector side
   (the side `facing` points toward) and travelling into the surface, so
   depth-varying meshes record their *near* face rather than a far shell.
   `point_at(s, z)` bilinearly interpolates the recorded triangle hit points;
   `normal_at_s(s)` averages the column's oriented face normals.
3. **Validates single-valuedness** as a depth-smoothness check: adjacent
   lattice depths that jump by more than `_SLOPE_LIMIT × max(cell size)`
   (steeper than ~63° relative to the frontal axis) mark the mesh unsuitable
   and raise a `ProjectionError` naming the offending region.
   (Implementation note: this replaced the original per-ray multi-hit idea —
   Blender's `BVHTree.ray_cast` reports only the first hit, so smoothness
   over recorded depths is the equivalent test both casters run identically.)

Consequence, stated honestly: domes, columns, and deeply folded geometry are
**out of scope and rejected loudly**, not silently mangled. A projection target
that a bank of ceiling projectors faces frontally is precisely the case this
accepts; the README limitation list gets narrower but not empty.

`intersect_ray` delegates to the injected/pure-Python caster filtered to the
usable face; `project_point` finds the nearest recorded scan point and refines
on the containing triangle. `expanded`/`chord`/`measurement_wall` implement the
ADR 0003 hook semantics against the bounding rectangle (flat-face behaviour:
`chord(span) = span`).

### 3. Nothing in `footprint.py` or `coverage.py` changes

Both consume only the ABC. `compute_footprint` calls `intersect_ray`;
`analyze_coverage` calls `point_at`/`normal_at_s`/`covers`. With a correct
`MeshSurface`, they run unmodified — that is the payoff of the ADR 0003 seam
and the acceptance criterion for this ADR's implementation.

Blender-side changes are confined to the established dispatch pattern:

- `PJ_OT_set_target_wall` accepts arbitrary mesh objects (currently restricted);
- `pj_wall.kind = 'MESH'` tags them (no new operator needed — users mark their
  own imported object rather than asking us to generate one);
- `wall_from_object` gains a `'MESH'` branch that builds a `BVHTree` from the
  object and injects it into `MeshSurface`.

Rejected alternatives:

- **UV-map-based parameterisation** — many imported meshes have missing,
  overlapping, or non-planar-conformal UVs; silently trusting them fails in
  ways an AV engineer can't diagnose. The scanline approach validates instead.
- **Full 3D rasterisation of `coverage.py`** — rewrites the most-tested module
  in the codebase for a case (non-frontal targets) that mostly isn't a
  projector wall. Revisit only if a real dome/column job arrives.

## Consequences

- **Good:** imported geometry becomes a supported target; all 251 existing
  tests keep passing untouched; heavy meshes stay fast inside Blender while
  everything remains testable under plain CPython.
- **Cost:** one new core module with its own acceleration structure; the
  frontal-axis assumption must be explained in UI copy and README.
- **Risk:** scanline validation thresholds need tuning against real
  architectural meshes; mitigated by making the rejection message name the
  region so failures are diagnosable.

## Verification plan (TDD, house order)

1. Pure-Python tests for `core/mesh_surface.py`: construction from synthetic
   triangles (plane, gentle curve), `point_at` round-trips, `intersect_ray`
   parity between pure-Python and an injected fake caster, single-valuedness
   rejection on a folded shape, hook semantics (`chord`, `expanded`,
   `measurement_wall`).
2. Contract tests: footprint + coverage against a tessellated flat wall match
   `PlanarWall` within tessellation error.
3. Headless smoke: import a small generated mesh, tag `'MESH'`, set target,
   add projector, analyse — scene-level acceptance only.

## Related

- ADR 0001 (one canonical product; maths lives in `core/`, bpy-free)
- ADR 0002 (honest claims — rejected meshes must be reported as unsupported,
  never approximated)
- ADR 0003 (the `Surface` seam this builds on)
