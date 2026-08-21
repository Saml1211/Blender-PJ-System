# User manual

A panel-by-panel walkthrough of the Projection Planner sidebar. For install and
a worked curved-wall example, start with the [README](../../README.md).

Open the sidebar in the 3D viewport with <kbd>N</kbd> and pick the
**Projection** tab. The panels are numbered in the order you use them.

---

## 1. Projection Target

Defines the surface you are projecting onto. Nothing else works until a target
is set.

| Control | What it does |
|---|---|
| **Create Curved Wall** | Builds a cylindrical wall segment and sets it as the target |
| **Set as Target Wall** | Marks the active object as the target, if it is already a projection wall |
| **Target Wall** | The object analysis runs against |

### Create Curved Wall options

Adjust these in the operator's redo panel (bottom-left) immediately after
running it.

| Option | Meaning |
|---|---|
| **Radius** | Radius of curvature. Larger is flatter — use several thousand metres for an effectively flat wall |
| **Height** | Height of the wall surface |
| **Arc** | Angular sweep in degrees, centred on the +X axis |
| **Segments** | Mesh subdivisions around the arc. Visual only; analysis is analytic |
| **Concave** | Ticked = projectors sit inside the arc. This is the usual curved-wall case |
| **Base Height** | Height of the wall's bottom edge |

Once created, the panel shows the wall's arc length and area, and the radius,
height and arc remain editable. **Edits take effect on the next Calculate
Coverage** — the analysis is not live.

> The wall's **position** comes from its object location, so you can move it in
> the viewport. Rotated walls and walls with unapplied scale or shear are
> rejected by analysis; clear or apply those transforms before calculating
> coverage.

---

## 2. Projectors

### Lens & Output

The specification used when generating an array.

| Field | Meaning |
|---|---|
| **Throw Ratio** | `D / W` for the fitted lens |
| **Aspect** | Image aspect, e.g. 16:9 |
| **Lumens** | Rated output. Derate this yourself for eco mode or lamp age |
| **Max Vertical Shift** | Lens shift limit, as a fraction of image height |

> **Lens shift convention.** A value of `0.5` means the optical axis sits on
> the image edge. Datasheets calling that "100% offset" measure against half
> the image — halve their number for this field.

### Mounting

| Field | Meaning |
|---|---|
| **Mount Mode** | *Level + Lens Shift* keeps the axis horizontal and shifts the lens down — no keystone, but needs shift range. *Tilt to Target* avoids lens shift and aims at the wall, but still raises a projection error when the requested image width is geometrically unreachable; successful tilted layouts introduce keystone |
| **Mount Height** | Height of the mounting point, e.g. the ceiling |
| **Image Centre Above Wall Base** | Local height above the wall's bottom edge where image centres should sit |

### Array Layout

| Field | Meaning |
|---|---|
| **Projectors** | How many to spread across the wall |
| **Overlap** | Fraction of each image shared with its neighbour for blending. 0.10–0.20 is the usual working range |
| **Plan Projector Array** | Generates the projectors and writes the plan to the Report panel |

Planning solves for the standoff distance that produces the required image
width on the curved surface, then places each projector on the radial line
through its target point. Re-running replaces the previously generated array
but leaves manually added projectors alone.

### Single projectors

| Control | What it does |
|---|---|
| **Add Projector** | Adds one at the 3D cursor, snapped to the mount height and aimed at the target wall |
| **Aim at Wall** | Re-aims the selected projectors. With *Spread Selection* ticked, distributes them evenly along the arc |

Projectors are **camera objects**, so you can look through one
(<kbd>Ctrl</kbd>+<kbd>Numpad 0</kbd>) to see its exact framing. Field of view
and lens shift are written to the camera to match the projector spec.

### Selected Projector

A collapsible sub-panel showing the active projector's own lens data —
including per-projector throw ratio limits and horizontal shift — and the
values computed for it by the last analysis. Computed fields are greyed out
because they are consequences of the geometry, not inputs.

---

## 3. Analysis

**Calculate Coverage** casts every visible projector's frustum onto the target
wall and builds the overlay.

| Setting | Meaning |
|---|---|
| **Footprint Samples** | Rays per axis across each image. Higher resolves curved or clipped edges more finely. 9–11 is a practical starting point |
| **Grid Arc / Height** | Resolution of the coverage raster over the wall |
| **Screen Gain** | Gain of the wall finish. 1.0 is matte white |
| **Draw Frustums** | Include the lens-to-corner wireframes |

**Clear Analysis** deletes only owner-tagged overlay objects from the add-on's
analysis collection. Your wall, projectors, and same-named user collections are
never touched.

### Reading the overlay

| Overlay | Meaning |
|---|---|
| Coloured areas | Each projector's image footprint on the wall |
| White bands | Blend zones where two images overlap |
| Near-black bands | Dark gaps no projector reaches |
| Wireframe cones | Lens to image corners |

---

## 4. Report

The results of the last calculation, split into information and warnings.

**Copy Report** puts the whole thing on the clipboard and prints it to the
system console, ready to paste into a design document. The photometric
assumptions travel with it.

**Read the warnings.** They are the point of the tool — an image that
overshoots the wall, a lens shift beyond the lens's range, a blend too narrow
to be usable, or a brightness figure below the cinema-white reference.

---

## Lens Calculator

A standalone scratchpad, independent of the scene. Edit any two of distance,
image width and throw ratio, and the third follows. It also shows image height,
diagonal (in metres and inches), and mean illuminance and luminance for the
lumens set above — for a flat screen with no ambient light.

Useful for a quick sanity check before committing to a lens.

---

## Collections

The add-on organises everything into three collections and never writes
outside them:

| Collection | Contents | Deleted by the add-on? |
|---|---|---|
| `PJ Targets` | Projection walls | No |
| `PJ Projectors` | Projector cameras | Only generated array members, on re-plan |
| `PJ Analysis` | Footprints, blend bands, gap bands, frustums | Yes — rebuilt on every analysis |

---

## Troubleshooting

**"No target wall set."** Run Create Curved Wall, or select a wall object and
use Set as Target Wall.

**"No part of the image lands on the wall."** The projector is aimed away from
the target, or is too close/far for the arc. Use Aim at Wall.

**A projector needs more lens shift than it has.** Raise the image centre
height, lower the mount, fit a lens with more shift, or switch to Tilt to
Target and accept keystone correction.

**The image spills past the wall.** The wall is shorter or narrower than the
image. Expected when the aspect ratio does not match the wall; the report tells
you how much spills.

**Coverage looks low but there are no gaps.** The images do not reach the full
wall height — normal for a fixed aspect ratio on a taller wall. Check the
"lit band" figure and the horizontal coverage percentage.

**Panels missing after enabling.** Check the system console for a registration
error. Re-enabling is safe; the add-on rolls back a partial registration rather
than leaving a half-registered state.
