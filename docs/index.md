# Projection Planner documentation

Blender 4.2 add-on for planning ceiling-mounted projector arrays against curved
and flat walls.

**Start with the [README](../README.md).** It carries the authoritative status
table, the install steps, and the curved-wall quick start.

## Current documents

| Document | What it is |
|---|---|
| [README](../README.md) | Status, install, quick start, verification |
| [ADR 0001](adr/0001-canonical-architecture.md) | Why the Blender add-on is the only product, and how to recover the retired web app |
| [ADR 0002](adr/0002-removed-claims.md) | Which advertised features were removed as unimplemented, and why |
| [Feature reference](features/index.md) | What each capability computes, and its limits |
| [Multi-projector arrays](features/multi-projector.md) | Array layout, overlap and blend-zone reporting |
| [User manual](manual/index.md) | Panel-by-panel walkthrough |

## Historical documents — not a specification

The following describe an aspirational product that was never built. They are
kept for provenance only. **Do not treat them as a description of the
software.** Where they conflict with the README, the README is correct.

- `PRD-BlenderProjectionMVP-20250329.md`
- `Blender-PJ-System-PRD.md`
- `noindex/Blender-PJ-System-PRD.md`
- `noindex/Blender-PJ-System-PRD-v2.md`
- `noindex/Blender-PJ-System-PRD-Final.md`
- `../memory-bank/` — context notes from a previous agent-assisted session

Specifically, these documents describe phase synchronisation, thermal CFD,
ambient-light AI, VR/AR integration and CAD import. None of that exists; see
[ADR 0002](adr/0002-removed-claims.md).

## A note on numbers

Throw formulae and ray/cylinder intersections are analytic. Footprints,
coverage, gaps, and blends are sampled at user-controlled resolution.
**Photometry is a first-order estimate.** Every brightness report prints its
assumptions: zero ambient light, full rated lumens, uniform intensity, and a
Lambertian screen. Real rooms are dimmer.
