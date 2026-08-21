# Blender UI Compatibility Notes (4.x to 5.x)

## Sources

- Blender 4.0 Python API release notes: https://developer.blender.org/docs/release_notes/4.0/python_api/
- Blender 5.0 Python API release notes: https://developer.blender.org/docs/release_notes/5.0/python_api/
- Blender 4.0 API change log: https://docs.blender.org/api/4.0/change_log.html
- Blender 5.0 API change log: https://docs.blender.org/api/5.0/change_log.html

## UI-relevant updates to account for

- `bpy.types.UIList.layout_type`:
  - `GRID` is removed in Blender 5.0.
- `bpy.types.UILayout.emboss`:
  - `RADIAL_MENU` is renamed to `PIE_MENU` in Blender 5.0.
- Asset browser UI patterns:
  - `UILayout.template_asset_view()` is removed in Blender 5.0.
  - Prefer asset shelf and `context.asset` usage.
- Asset context:
  - 4.x already moves toward `context.asset` and `AssetRepresentation`.
- Node/compositor UI assumptions:
  - `scene.use_nodes` is deprecated and effectively always true in 5.0.
  - `scene.node_tree` is removed; use `scene.compositing_node_group`.

## Safe version patterns

```python
import bpy


def blender_50_or_newer():
    return bpy.app.version >= (5, 0, 0)


def safe_emboss_pie():
    return "PIE_MENU" if blender_50_or_newer() else "RADIAL_MENU"
```

## Migration checklist

1. Search for removed enum values and template calls.
2. Replace deprecated asset UI paths with `context.asset` flow.
3. Verify panel draw functions avoid deprecated node-tree assumptions.
4. Run smoke tests in both 4.x and 5.x where possible.
