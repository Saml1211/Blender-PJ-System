# Multi-projector arrays

How the add-on lays out several projectors across a wall, and what it can and
cannot tell you about the result.

---

## The layout arithmetic

For `N` projectors covering an arc of length `S` with overlap fraction `f`,
each image must cover arc width `w`:

```text
S = N·w − (N−1)·f·w        →        w = S / (N − (N−1)·f)
```

Image centres are then spaced `w·(1−f)` apart, starting half an image width in
from the wall's start:

```text
s_i = w/2 + i·w·(1−f)
```

This tiles the wall exactly: the first image's left edge sits at `s = 0`, the
last image's right edge at `s = S`, and each neighbouring pair shares exactly
`f` of an image width.

**Worked example** — the wall from the README, `S = 12.57 m`, `N = 3`,
`f = 0.15`:

```text
w   = 12.57 / (3 − 2×0.15) = 12.57 / 2.70 = 4.656 m
s   = 2.328, 6.285, 10.242 m
spans = 0.000–4.656, 3.957–8.613, 7.914–12.570 m
overlaps = 0.70 m each = 15% of image width ✓
```

---

## Solving for where the projectors go

Knowing the required image width is not enough, because a planar image landing
on a cylinder does not have a closed-form arc width. The planner therefore
**solves numerically**: it places a trial projector, ray-casts its frustum onto
the wall, measures the actual arc span, and iterates

```text
D ← D · (1 + 0.85·(target/measured − 1))
```

until the span matches to within a millimetre. Damping the step keeps the
curved-wall feedback from oscillating. It converges in a handful of iterations.

Two details matter for correctness:

- The solve runs against a deliberately **oversized copy of the wall**. Edge
  projectors aim at the very end of the arc, so against the real wall their
  images would be clipped and the measured span would be wrong.
- In **Tilt** mode the axis distance is clamped to exceed the vertical drop —
  the optical axis is the hypotenuse over that drop, so a shorter distance is
  geometrically impossible. A poor starting guess would otherwise abort a solve
  that does have an answer.

If the clamp forces an image more than 50% away from what was asked for, the
planner **raises** with a message naming the constraint rather than returning a
number that ignores the request.

---

## Mounting modes

| | **Level + Lens Shift** | **Tilt to Target** |
|---|---|---|
| Optical axis | Horizontal | Aimed at the target point |
| Keystone | None | Yes — needs electronic correction, which costs pixels |
| Focus uniformity | Better | Worse (wider throw spread) |
| Limit | Required shift may exceed the lens | Avoids lens shift, but the requested width can still be geometrically infeasible |
| Required shift | `−drop / image_height` | n/a (zero) |

Level is the preferred install and the default. The add-on computes the shift
each projector needs and warns when it exceeds the configured lens limit,
naming the three ways out: lower the mount, raise the image centre, or switch
to tilt.

---

## What the coverage report tells you

The wall is rasterised in arc length × height, and each cell tested against
every projector by **back-projecting** the cell through the lens — the exact
inverse of the forward ray cast. (An earlier point-in-polygon test against the
sampled outline understated coverage whenever an image spilled off the wall,
because the outline walk closes across the missing samples.)

| Metric | Meaning |
|---|---|
| **Coverage** | Fraction of total wall *area* lit by at least one projector |
| **Horizontal coverage** | Fraction of the *arc* lit at some height |
| **Lit band** | The height range the images actually reach |
| **Dark bands** | Arc ranges lit by nobody at any height — real holes |
| **Overlap** | Fraction of the wall lit by two or more, and the maximum count |
| **Blend zones** | Per-pair overlap width, in metres and as a fraction of image width |

### Why coverage and horizontal coverage differ

A 4.8 m-wide 16:9 image is about 2.7 m tall (`height = width × 9/16`). On a
3 m wall, horizontal coverage can be 100% while area coverage is ~89%, because
strips at the top and bottom are never lit. That is a normal consequence of a
fixed aspect ratio, **not a gap**, and the report keeps the two separate so a
sound design is not flagged as failing.

If you need the full height, the options are a taller image (wider arc per
projector, fewer projectors, or a shorter lens), a second stacked row, or
accepting the letterbox.

---

## Blend zones — geometry only

The add-on reports **where** images overlap and **how wide** the overlap is. It
does **not** model the soft-edge luminance ramp a blending processor applies.

Guidance it applies:

| Overlap | Verdict |
|---|---|
| < 5% of image width | Flagged — too narrow to blend reliably |
| 10–20% | The usual working range |
| > 50% | Flagged — you are paying for pixels you cannot use |

Triple overlap (three or more projectors on one spot) is flagged separately,
because it is usually a placement error rather than an intentional blend.

---

## Brightness in overlaps

Illuminance from overlapping projectors **adds linearly**, which is correct for
incoherent sources. So a blend zone is roughly twice as bright as the
single-projector areas either side of it — before any blending processor pulls
it back down.

This is why the uniformity figure in the README example is 0.37: the blend
bands are genuinely brighter than the image centres, and the wall ends are
struck at up to 28° incidence. A real installation corrects the first with edge
blending and lives with the second.

All brightness figures carry the assumptions listed in the
[feature reference](index.md#brightness--corephotometrypy) — most importantly
**zero ambient light**.

---

## Limits

- Projectors are laid out **horizontally only**. Stacked rows are not planned
  automatically; add them manually and analyse.
- All projectors in a planned array share one specification. Mixed lenses need
  manual placement.
- No occlusion. A column between projector and wall is invisible to the
  analysis.
- No consideration of sightlines, audience positions, or shadowing by people.
