# Blender Add-on UI Design Skill

A Codex skill focused on Blender add-on/plugin UI design, including panel architecture, interaction patterns, and Blender 4.x/5.x UI compatibility.

## What This Skill Includes

- `SKILL.md`: Workflow for UI-first add-on design and implementation.
- `scripts/scaffold_ui_module.py`: Generator for a UI-oriented add-on module layout.
- `references/ui_design_principles.md`: Practical UX principles for Blender add-on interfaces.
- `references/ui_code_patterns.md`: Reusable `bpy` UI templates and patterns.
- `references/ui_compat_4_5.md`: Blender 4.x to 5.x UI API compatibility notes.

## Quick Start

Generate a UI-focused add-on scaffold:

```bash
python3 scripts/scaffold_ui_module.py --name "My UI Addon" --output .
```

Optional arguments:

```bash
python3 scripts/scaffold_ui_module.py \
  --name "My UI Addon" \
  --module my_ui_addon \
  --author "Your Name" \
  --version 0.1.0 \
  --blender-min 4.0.0 \
  --category "My Tools" \
  --output .
```

Generated files:

- `__init__.py`
- `compat.py`
- `properties.py`
- `operators.py`
- `ui.py`
- `preferences.py`

## Validation

```bash
python3 -m py_compile scripts/scaffold_ui_module.py
python3 /home/zwhy/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

## Sources

- Blender 4.0 Python API release notes: https://developer.blender.org/docs/release_notes/4.0/python_api/
- Blender 5.0 Python API release notes: https://developer.blender.org/docs/release_notes/5.0/python_api/
- Blender 4.0 API changelog: https://docs.blender.org/api/4.0/change_log.html
- Blender 5.0 API changelog: https://docs.blender.org/api/5.0/change_log.html
