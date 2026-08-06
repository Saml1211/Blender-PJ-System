# Feature reference

What each capability actually computes, and where it stops. Every entry maps to
a module in `blender_projection_system/core/` and to tests that import it.

---

## Throw geometry — `core/throw.py`

`TR = D / W`, with `W = D / TR`, `D = W · TR`, and `H = W / aspect`.

Field of view comes from the same relationship: `tan(θ_h) = 1 / (2·TR)`, and
the vertical half-angle divides that by the aspect ratio.

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
- Cylinders only. Flat walls are approximated with a large radius
  (`flat_wall_as_cylinder`); domes and arbitrary meshes are unsupported.
- Rotated walls and walls with unapplied object scale are rejected. Translation
  is supported; the surface remains a vertical circular cylinder.
- No occlusion. If a column stands between projector and wall, this add-on
  does not know.

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
|---|---|---|
| **Level + Lens Shift** | Optical axis stays horizontal; lens shift moves the image down. | No keystone, even focus. Fails when the required shift exceeds the lens. |
| **Tilt to Target** | Projector tilts to aim at the target point. | Always geometrically possible; introduces keystone that costs pixels to correct. |

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
   corners; ANSI 9-point uniformity of 70–90% is typical, so corner figures
   here are optimistic by roughly that margin.
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

## What is not here

Phase synchronisation, thermal modelling, ambient-light AI, VR/AR, and CAD
import were advertised by v0.1 and do not exist. See
[ADR 0002](../adr/0002-removed-claims.md).
