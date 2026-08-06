# Getting started

## Requirements

- **Blender 4.2 LTS or newer.** The add-on uses the 4.x extension and property
  APIs and will not work on 3.x.
- Nothing else. The add-on is pure Python and has no dependencies beyond
  Blender's bundled interpreter.

## Install

Build a Blender extension zip whose manifest and `__init__.py` are at the
archive root:

```bash
git clone https://github.com/Saml1211/Blender-PJ-System.git
cd Blender-PJ-System
blender --background --factory-startup --command extension build \
  --source-dir blender_projection_system \
  --output-filepath projection_planner.zip
```

In Blender: **Edit ▸ Preferences ▸ Get Extensions ▸ ▾ ▸ Install from Disk…**,
choose the zip, then enable **Projection Planner** under Add-ons if needed.

Open the 3D viewport sidebar with <kbd>N</kbd> and select the **Projection**
tab.

### Developing on it

Symlink the package instead, so edits apply on **F3 ▸ Reload Scripts**:

```powershell
# Windows, administrator PowerShell
New-Item -ItemType SymbolicLink `
  -Path "$env:APPDATA\Blender Foundation\Blender\4.2\scripts\addons\blender_projection_system" `
  -Target "$PWD\blender_projection_system"
```

```bash
# macOS
ln -s "$PWD/blender_projection_system" \
  ~/Library/Application\ Support/Blender/4.2/scripts/addons/

# Linux
ln -s "$PWD/blender_projection_system" ~/.config/blender/4.2/scripts/addons/
```

Enabling and disabling repeatedly is safe — this is covered by the headless
smoke test, which cycles registration four times.

## Your first design in four clicks

1. **Create Curved Wall** — accept the defaults (8 m radius, 3 m high, 90°).
2. Set **Projectors** to `3` and **Overlap** to `0.15`.
3. **Plan Projector Array**.
4. **Calculate Coverage**.

Read panel **4. Report**. You now have mount coordinates, throw distances,
image sizes, blend widths and a brightness estimate.

The [README](../../README.md) walks the same example with every number spelled
out, including the lens-shift warning it deliberately triggers and how to
resolve it.

## Interface at a glance

| Panel | Use it to |
|---|---|
| **1. Projection Target** | Create or choose the wall |
| **2. Projectors** | Set the lens, the mount, and lay out the array |
| **3. Analysis** | Run the calculation and tune its resolution |
| **4. Report** | Read the results and copy them out |
| **Lens Calculator** | Quick throw sums, independent of the scene |

Full detail for every control is in the [user manual](index.md).

## What to expect from the numbers

Throw formulae and analytic ray/cylinder intersections are deterministic to
floating-point precision. Footprint interiors, coverage, gaps, and blend widths
are sampled estimates whose resolution is controlled in the Analysis panel.

**Brightness is a first-order estimate** that assumes zero ambient light, full
rated lumens, uniform intensity across the frustum, and a Lambertian screen.
The assumptions print with every report. A real room will be dimmer; derate
deliberately rather than trusting the headline nit figure.
