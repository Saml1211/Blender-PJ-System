---
name: blender-projection-planner
description: Develop and verify this Blender 4.2 projection-planning add-on, using pure-Python tests first and live Blender only for scene-level acceptance.
---

# Blender Projection Planner

Read `README.md`, `CONTRIBUTING.md`, and the relevant ADR before changing behavior.

Use this verification order:

1. `ruff check blender_projection_system tests`
2. `python -m compileall -q blender_projection_system tests`
3. `pytest -v`
4. For Blender-facing changes, run `blender -b --factory-startup --python-exit-code 1 --python tests/blender_smoke.py`.
5. Use Blender MCP only for the smallest live-scene check needed; never overwrite an unrelated open `.blend` file.

Keep formulas in `blender_projection_system/core/`, which must remain importable without `bpy`.
