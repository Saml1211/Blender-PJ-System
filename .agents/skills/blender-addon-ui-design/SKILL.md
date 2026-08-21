---
name: blender-addon-ui-design
description: Design and implement Blender add-on/plugin user interfaces with strong usability and clean `bpy` UI code. Use when building or refactoring add-on UI panels, menus, popovers, preferences, UILists, operator dialogs, icon/layout polish, or Blender 4.x/5.x UI compatibility updates.
---

# Blender Add-on UI Design

## Quick Start

1. Read `references/ui_design_principles.md`.
2. Pick UI surfaces to implement: sidebar panel, header menu, popover, dialog, addon preferences, or UIList.
3. Generate baseline files with `scripts/scaffold_ui_module.py` when needed.
4. Apply layout and interaction patterns from `references/ui_code_patterns.md`.
5. Check Blender 4/5 UI API changes in `references/ui_compat_4_5.md`.

## Workflow

### 1) Scope the UI

- Define target users and primary workflows.
- Define placement:
  - `VIEW_3D` sidebar (`bl_region_type = "UI"`) for tool-centric tasks.
  - Topbar/header menus for global actions.
  - Popup dialogs for short, high-focus forms.
  - Preferences for defaults and persistent configuration.
- Keep one panel focused on one job.

### 2) Build structure first, styling second

- Establish hierarchy:
  - Primary actions at top, secondary actions below.
  - Group related controls with `layout.box()` or labeled sections.
  - Use progressive disclosure with `layout.prop(..., text=...)` toggles and `if` blocks.
- Minimize eye travel by keeping dependent controls close.
- Keep labels short and action-oriented.

### 3) Implement robust UI behavior

- Use `poll()` to hide invalid actions.
- Disable controls when prerequisites are missing (`row.enabled = False`).
- Use operator reports for immediate feedback.
- Keep draw code pure: no heavy scene mutation inside `draw()`.
- Keep expensive computations out of UI redraw paths.

### 4) Validate and iterate

- Run `python3 -m py_compile` on edited files.
- Confirm register/unregister order and class IDs.
- Test with realistic scenes and edge states (missing data, empty selection, wrong mode).
- Verify panel layout on both narrow and wide sidebar widths.

## UI Design Rules

- Prefer consistency over novelty; match Blender visual conventions.
- Keep controls discoverable:
  - Prefer explicit labels over icon-only controls unless icon meaning is standard.
  - Use `icon` only when it adds clarity, not decoration.
- Reduce cognitive load:
  - Show only relevant controls for current mode/context.
  - Collapse advanced settings by default.
- Preserve user trust:
  - Confirm destructive actions with dialogs.
  - Keep undo behavior predictable via operator options.
- Design for speed:
  - Expose common actions first.
  - Avoid deep nesting in panel layout.

## UI Implementation Rules

- Keep module split clear:
  - `ui.py` for panels/menus/UILists.
  - `operators.py` for actions.
  - `properties.py` for state.
  - `preferences.py` for addon settings.
- Keep class naming stable and explicit:
  - `MYADDON_PT_*`, `MYADDON_MT_*`, `MYADDON_UL_*`, `MYADDON_OT_*`.
- Unregister classes in reverse order.
- Use `bl_parent_id` for subpanels when hierarchy is needed.
- Guard version differences in helper functions instead of scattered checks.

## Compatibility Rules for Blender 4.x and 5.x

- Avoid removed UI enum/value usage in new code:
  - `UIList.layout_type` no longer supports `GRID` in 5.0.
  - `UILayout.emboss` value `RADIAL_MENU` is renamed to `PIE_MENU`.
- Avoid removed asset template API in new UI:
  - `UILayout.template_asset_view()` is removed in 5.0.
- Prefer `context.asset` over legacy asset file handles.
- Treat `scene.use_nodes` as deprecated; do not rely on it for UI state logic.

## Resources

### scripts/

- `scripts/scaffold_ui_module.py`: Generate UI-oriented add-on modules (`ui.py`, `operators.py`, `properties.py`, `preferences.py`, `__init__.py`).

### references/

- `references/ui_design_principles.md`: UX and information-architecture guidance for Blender add-on UIs.
- `references/ui_code_patterns.md`: Reusable `bpy` UI patterns and templates.
- `references/ui_compat_4_5.md`: UI-relevant Blender 4.0 to 5.0 compatibility notes.
