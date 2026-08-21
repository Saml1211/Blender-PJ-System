# Curved Wall Planner Replacement PR

## Goal

Replace the inherited, unverified Blender Projection System changes with a
truthful, installable, independently verified Blender 4.2 projection-planning
add-on; commit and push the branch; open a replacement PR; then close PR #1
only after the replacement PR is demonstrably ready. Never merge automatically.

## Success Criteria

- Complete diff and deletion inventory reviewed before product edits.
- Throw, pose, cylindrical-surface, footprint, coverage, overlap, array, lens
  shift, and photometry behaviour independently reviewed and defect-tested.
- Blender registration cycles, headless workflow, extension validation/build,
  local installation, and live MCP scene workflow pass in Blender 4.2.3.
- Live scene contains one curved wall, three ceiling projectors, sampled
  footprints, configurable overlap, organized collections, and useful report
  evidence; viewport is visually inspected rather than accepted on object count.
- Documentation separates implemented, approximate/experimental, unsupported,
  and future scope and records what unique web-prototype features were retired.
- Final lint, compile, tests, security review, diff review, commit, push, and PR
  evidence complete. PR #1 is closed only after the replacement PR is open and
  green/ready.

## Current Context

- Branch: `feat/curved-wall-planner-v1` at `bf4cbd5`, based on `origin/main`.
- Inherited tree: 19 modified files, 1,198 deletions, 17 untracked product/test
  files; 1,157 deletions are tracked `node_modules`, 39 are retired web source/
  config files, and two are obsolete Python files.
- Blender 4.2.3 is installed; a fresh interactive Blender session is open with
  current blender-mcp. The existing archive is extension-shaped but Blender
  reported a local extension-repository lock-cookie error before archive checks.
- This run is Codex, not Claude/Hermes. Inherited claims remain unverified.

## Constraints

- Do not invoke Claude or Kimi. Use Codex subagents only.
- Do not touch `Blender-PJ-System-pr1`.
- Do not commit local `.agents/`, `.codex/`, `.workflow/`, MCP logs, caches,
  `.blend` files, or generated zip archives.
- Preserve unrelated open Blender files; live MCP work may use only the current
  unsaved/factory scene and generated add-on collections.
- Keep the add-on canonical; do not revive the React app unless the deletion
  review finds a required unique capability.

## Risks

- Engineering formulas may be internally consistent but use a wrong Blender
  camera/lens-shift convention. Mitigate with independent review plus live
  `Camera.view_frame()`/ray comparisons.
- Sampled/raster reports may be documented as exact. Mitigate by convergent
  tests and explicit approximation language.
- Extension archive shape and Blender's local repository lock are separate
  failure modes. Validate/build the archive independently, then repair/retry
  local installation without deleting unrelated extensions.
- Committing 1,198 deletions can hide unintended loss. Review all 41 non-vendor
  deletions individually and categorize all 1,157 dependency artifacts.

## Approval Required

Already granted in the user request: recreate/delete the generated zip, commit,
push the feature branch, open the replacement PR, and close PR #1 after the
replacement is verified ready. Force-push, merge, destructive Blender-file
operations, credential changes, and worktree changes are not authorized.

## Work Packets

1. Engineering core audit (subagent, read-only): math, coordinate conventions,
   edge cases, and missing tests.
2. Blender integration/UI/package audit (subagent, read-only): registration,
   data API, collections, camera mapping, archive/install path, and UI usability.
3. Deletion/docs/security audit (subagent, read-only): all non-vendor deletions,
   unique web prototype features, documentation truthfulness, and risk scan.
4. Parent integration: run baseline checks, reproduce defects, add tests, make
   surgical fixes, and reconcile reviewer findings.
5. Parent acceptance: headless Blender, extension build/install, live MCP scene,
   viewport inspection, final quality/security/diff checks, commit/push/PR.

## Integration Policy

The parent owns every edit and final judgment. Subagents return evidence and
recommended tests only; conflicting claims are resolved against production code,
Blender 4.2.3 runtime behaviour, and explicit documented assumptions.

## Verification

1. `ruff check blender_projection_system tests`
2. `python -m compileall -q blender_projection_system tests`
3. `pytest -v`
4. Blender 4.2.3 repeated registration and camera-convention probes.
5. `blender -b --factory-startup --python-exit-code 1 --python tests/blender_smoke.py`
6. Blender extension manifest validation/build plus archive-content inspection.
7. Local extension installation/enable in a clean Blender user-resource sandbox.
8. Blender MCP live workflow, report extraction, scene-object inspection, and
   viewport screenshot review.
9. `git diff --check`, security scan, deletion inventory, final staged diff,
   branch/remote/PR/CI checks.

## Reusable Artifacts

- Verified extension zip in the repository root (ignored, not committed).
- Live viewport evidence under `docs/images/` only if regenerated and verified.
- Replacement PR body containing migration notes, limitations, and exact tests.
