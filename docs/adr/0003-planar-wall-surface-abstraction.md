# ADR 0003: Flat walls as first-class surfaces via a shared Surface base

**Status:** Accepted
**Date:** 2026-08-26

## Context

The only projection surface was `CylindricalWall` (`core/surfaces.py`). A flat
wall — by far the most common real-world AV case — was approximated with a
5000 m radius cylinder (`flat_wall_as_cylinder`), which is under a millimetre of
bow across 4 m but is still a hack: it carries meaningless parameters (a radius,
an angular sweep), the README lists "only cylindrical walls" as a headline
limitation, and the array planner's solver has to reason about cylinder axes
even when planning against a nominally flat wall.

Every downstream module (`footprint.py`, `coverage.py`, `array.py`,
`visualization.py`) operates in the wall's ``(s, z)`` parameterisation —
distance along the wall from one edge, height above its base — plus
``intersect_ray`` / ``project_point``. None of them care whether ``s`` follows
an arc or a straight line; installers measure both the same way. The only
genuinely cylinder-specific behaviour is:

1. full-circle seam unwrapping when the sweep reaches 360°,
2. the array solver's oversized "measurement wall" used while iterating,
3. the chord-based seed distance and the "lens passes through the axis"
   standoff warning.

## Decision

Introduce an abstract base class `Surface` in `core/surfaces.py` owning the
shared ``(s, z)`` contract (`point_at`, `normal_at_s`, `intersect_ray`,
`project_point`, `arc_length`, `height`, `area`, `center_point`), with four
generic hooks replacing direct cylinder-field access:

| Hook | CylindricalWall | PlanarWall |
| --- | --- | --- |
| `wraps_around` | sweep ≥ 2π − ε | `False` |
| `chord(span)` | `2·R·sin(span / 2R)` | `span` |
| `expanded(pad_s, pad_z)` | wider arc + taller, lower base | wider rectangle + lower base |
| `curvature_radius` | `radius` | `None` |

`PlanarWall` is a frozen dataclass defined by a `base_center` (bottom-centre of
the wall *on the wall face*, not an axis), `width`, `height`, and `facing`
(a unit horizontal normal pointing at the projectors). ``s`` runs 0 → width
from the left edge as seen from the projector side. Back-face ray hits are
rejected exactly as a concave cylinder rejects them.

`CylindricalWall` keeps its entire public API unchanged. All core functions
take `Surface` in place of `CylindricalWall`. `flat_wall_as_cylinder` remains
for backwards compatibility (existing tests pin its behaviour) but its
docstring steers new code to `PlanarWall`.

A Blender-side operator (`projection.create_flat_wall`) creates flat-wall
objects carrying `pj_wall.kind = 'FLAT'` plus `width` and `yaw_deg`;
`visualization.wall_from_object` rebuilds whichever concrete surface the object
declares.

Rejected alternative: parallel code paths (a separate flat-wall pipeline).
Duplicated geometry means duplicated drift risk — the failure mode ADR 0001
exists to prevent.

## Consequences

- **Good:** accurate footprints/coverage on flat walls with no approximation;
  the README limitation goes away; new surface types (inclined planes, later
  arbitrary meshes) have an obvious seam.
- **Cost:** consumers must route cylinder-specific questions through the four
  hooks rather than reading fields directly; the array solver gains one level
  of indirection.
- **Neutral:** `flat_wall_as_cylinder` stays but is no longer the recommended
  way to model a flat wall.

## Related

- ADR 0001 (one canonical product; maths lives in `core/`, bpy-free)
- ADR 0002 (honest claims — this ADR adds capability, it does not resurrect any removed claim)
