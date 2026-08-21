## Summary

Replaces the overstated dual-app prototype with one truthful product: a tested
Blender 4.2 Projection Planner for laying out multiple ceiling-mounted
projectors against a curved cylindrical wall.

- adds a pure-Python engineering core for throw, pose, cylinder intersections,
  sampled footprints, coverage/overlap, array planning, and first-order
  photometry
- makes the Blender layer use those production calculations for wall creation,
  LEVEL/TILT aiming, lens shift, array layout, reporting, and scene overlays
- makes registration repeatable and generated content owner-tagged,
  per-scene, collection-organized, and non-destructive to user objects/materials
- replaces fake tests and echo-only CI with production-importing unit tests,
  Ruff/compile checks, Blender 4.2 headless smoke coverage, and extension
  archive validation
- rewrites README/feature docs to separate implemented, limited, unsupported,
  and historical claims

## Engineering verification

- `ruff check blender_projection_system tests` — pass
- `python -m compileall -q blender_projection_system tests` — pass
- `pytest -q` — **213 passed, 6 structural skips**
- Blender **4.2.3 LTS / Python 3.11.7** headless smoke — pass, including
  repeated register/unregister, all workflow operators, inward wall normals,
  lens-shift aiming, generated geometry, owner isolation, per-scene clearing,
  core/Blender result agreement, and correct zero-coverage/no-hit reporting
- extension source and `projection_planner.zip` validate with Blender's
  extension CLI (`SHA256 EB807730324FDB3411D6FBF3BD77A50A707747290023E8DC44B835B280814162`)
- exact rebuilt archive installed successfully into a fresh live Blender 4.2.3
  User Default extension repository

Live Blender MCP exercise (8 m radius, 3 m high, 90 degree wall; three 7000 lm
projectors; 15% configured overlap; 3.2 m mount; 13x13 footprint sampling;
180x40 coverage grid):

- 100.0% horizontal coverage; 89.0% sampled wall-area coverage
- no horizontal gaps; two 0.70 m sampled blend zones; max overlap 2
- three 5.84 m throws with 4.87 x 2.74 m images
- LEVEL mounts at z=3.20 m with -56.6% vertical lens shift
- blend visualization occupies only cells where both images land; it stops
  above the measured 0.30 m unlit lower strip

Viewport evidence: `docs/images/curved-wall-3-projectors.png`.

## Security and quality review

Independent diff review found and fixed three medium local-scene risks before
commit: same-named user material mutation, unowned flagged-projector deletion,
and unbounded ribbon tessellation. Regression checks cover all three. The
runtime has no filesystem, process, network, dynamic-code, deserialization, or
credential handling paths, and the extension manifest requests no permissions.

## Web app retirement / migration

The contradictory CRA/Three prototype is deliberately removed, including
1,157 tracked `node_modules` files. Its unique browser conveniences were a
basic Three viewport, local-storage/JSON project exchange, theme/transform
controls, measurement, and a simulated OBJ/FBX import affordance; none supplied
required projector-engineering capability that Blender lacks. The architecture
decision and recovery commands are pinned to pre-removal commit `bf4cbd50` in
`docs/adr/0001-canonical-architecture.md`.

The obsolete root cleanup helper and two formula-duplicating fake tests are
also removed. No code from PR #1 is merged.

## Explicitly unsupported

No phase synchronization, thermal CFD, ambient-light AI, VR/AR, CAD ingestion,
arbitrary mesh targeting, or physical calibration is claimed. Brightness is a
first-order zero-ambient Lambertian estimate and prints its assumptions in
every report.

Implementation and verification provenance: OpenAI Codex, continuing the
Hermes handoff on `feat/curved-wall-planner-v1`.
