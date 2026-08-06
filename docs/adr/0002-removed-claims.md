# ADR 0002: Removing unimplemented and unphysical feature claims

**Status:** Accepted
**Date:** 2026-08-05

## Context

The README, the PRDs under `docs/`, and the `memory-bank/` files advertised
capabilities that had no implementation and, in several cases, no defensible
physical basis. An AV design engineer reading those documents would reasonably
expect to be able to make load-bearing decisions with them.

This matters more than ordinary documentation drift: the claims were about
*measurements*. A tool that says it models thermal behaviour, and does not,
invites someone to skip a real thermal check.

## Decision

The following claims are removed from all user-facing documentation, and no
code pretends to implement them.

| Claim | Status | Why removed |
|---|---|---|
| Phase synchronisation between projectors | **Removed — not physical** | Projectors are incoherent light sources. There is no phase relationship between two projectors' output to synchronise. The real concerns are frame-lock/genlock and colour matching, which are signal-chain matters this add-on does not touch. |
| Thermal CFD / thermal visualisation for placement | **Removed** | No CFD solver exists in the codebase, and writing one is far outside this tool's scope. Projector heat loads belong in the mechanical services calculation, from the manufacturer's stated BTU/h figure. |
| Ambient-light AI / AI-assisted ambient compensation | **Removed** | No model, no training data, no implementation. Ambient light is handled honestly by stating that the brightness figures assume **zero** ambient light, so the user knows to derate. |
| VR/AR integration | **Removed** | No implementation. Blender's own VR scene inspection works on the scene this add-on produces; nothing extra is needed or provided. |
| CAD import (DWG/DXF/RVT) | **Removed** | The v0.1 operator called `bpy.ops.import_scene.obj`, which does not exist in Blender 4.2 (it became `wm.obj_import` in 3.x). It supported OBJ/FBX only, on paper, and was broken in practice. Use Blender's own File > Import, then mark the surface as a target. |
| "Real-time" Geometry Nodes projection cone | **Replaced** | The node group was assembled by name-matching sockets that changed between Blender versions; when a lookup failed it printed to the console and produced no geometry. Replaced with explicit meshes rebuilt on demand from `core/`. |
| Edge blending | **Scope corrected** | The add-on reports blend-zone **geometry** — where images overlap, how wide the overlap is, as a fraction of image width. It does not model the soft-edge luminance ramp a blending processor applies. Documented as such. |
| "Calculations accurate to at least 3 decimal places" | **Replaced with honest bounds** | Precision is not accuracy. The geometry is exact to floating point; the *photometry* is a first-order estimate whose assumptions are listed in `core/photometry.py` and printed with every report. |

## What replaced them

Brightness is the clearest example. Rather than an "ambient light AI", the
add-on now:

- computes illuminance from real geometry (per-sample distance and incidence
  angle against the curved surface),
- states its five assumptions in `core.photometry.ASSUMPTIONS`, which are
  appended to every report the user copies,
- flags results below the ~55 nit cinema-white reference and flags poor
  uniformity,
- and documents that the on-axis figure exceeds the flat-screen average by a
  computable geometric factor (`center_to_mean_ratio`), rather than quietly
  reporting one and labelling it the other.

That is less impressive than "AI ambient compensation" and considerably more
useful, because the numbers can be checked.

## Consequences

- The feature list is shorter and every entry is verifiable.
- `docs/noindex/` PRDs are retained as historical artefacts but are marked
  clearly as aspirational and superseded; they are not a specification.
- If any of these features is genuinely wanted later, it starts from an honest
  baseline rather than from documentation claiming it already exists.
