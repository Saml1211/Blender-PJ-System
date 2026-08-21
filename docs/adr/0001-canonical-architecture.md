# ADR 0001: One canonical product — the Blender add-on

**Status:** Accepted
**Date:** 2026-08-05

## Context

The repository contained two overlapping products, both presenting themselves as
complete:

1. `blender_projection_system/` — a Blender add-on whose README claimed a
   finished MVP with "accurate projection calculations" and multi-projector
   support.
2. `web-projection-system/` — a Create React App + three.js single-page app
   reimplementing the same projector maths in TypeScript.

Neither claim held up:

- The add-on's panel called three operator IDs (`projection.add_projection_cone`,
  `projection.create_test_surface`, `projection.setup_projection_mapping`) from a
  module that `__init__.py` registered *after* the UI, and its "multi-projector
  overlap detection" compared projector spacing against throw distance rather
  than computing any actual geometry. Its only two tests asserted against mock
  functions defined inside the test file, so they passed no matter what the
  add-on did.
- The web app had zero tests, 1,157 `node_modules` files committed to git, and a
  `react-scripts` 5.0.1 dependency tree carrying 56 advisories (3 critical).
  `react-scripts` has been unmaintained since 2022.
- The two codebases had already diverged. `web-projection-system/src/utils/
  projectionCalculations.ts` and the add-on's `properties.py` implemented the
  same throw relationship with different edge-case behaviour, and nothing kept
  them in sync.

## Decision

**The Blender add-on is the product.** The web app is retired.

Concretely:

1. All projection mathematics moves into `blender_projection_system/core/`, a
   package that never imports `bpy`. A test
   (`tests/test_addon_contract.py::test_core_modules_never_import_bpy`)
   enforces this. The maths is therefore testable under plain CPython, and the
   Blender layer is a thin adapter over it.
2. `web-projection-system/` is deleted from the working tree. It is not
   maintained, not tested, and not part of the projector-planning workflow.
   Deleting it removes the entire vulnerable dependency surface rather than
   nursing an unmaintained CRA build.
   The obsolete root-level `cleanup_addon.py` helper is also deleted: it was a
   one-off development cleanup script, not an installed add-on feature, and
   its hard-coded object removal predated the owned-collection workflow.
3. There is no second implementation of any formula. If a number appears in the
   Blender UI, it came from `core/`.

## Retired web conveniences and migration

The retired app uniquely provided a basic three.js viewport with grid/theme and
transform controls, a measurement tool, browser local-storage projects and
backups, JSON import/export, unit display, and an OBJ/FBX import affordance. The
import action only simulated success; it did not parse either format. Blender
already provides the durable scene, transforms, measurement, unit, and model
import workflows needed by the canonical product. Browser JSON/local-storage
project exchange is intentionally not carried forward.

The retired source remains available in git history. To inspect or restore it:

```bash
# Browse the retired tree
git show bf4cbd50:web-projection-system/src/utils/projectionCalculations.ts

# List everything that was there
git ls-tree -r --name-only bf4cbd50 -- web-projection-system | grep -v node_modules

# Restore it wholesale (then expect to migrate off react-scripts before use)
git checkout bf4cbd50 -- web-projection-system
```

If a browser-based viewer is ever wanted, the honest path is a fresh Vite +
TypeScript front end that calls the same `core/` algorithms compiled or ported
deliberately — not a revival of the CRA app.

## Consequences

- **Good:** one place for every formula; a real test suite; no npm supply-chain
  surface; no contradictory claims about what is implemented.
- **Good:** `git ls-files` drops from 1,233 to ~70 real files, so the repo is
  navigable and CI is fast.
- **Cost:** the three.js viewer and browser-local project conveniences are gone.
  Their source is recoverable, but they are not maintained functionality.
- **Cost:** anyone who wants projector maths outside Blender has to call the
  Python `core/` package rather than a browser page. That is a deliberate
  trade — one correct implementation beats two drifting ones.

## Related

- ADR 0002 records which product claims were removed as unimplemented.
