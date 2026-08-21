# Repository Guidelines

## Project Structure & Module Organization

`blender_projection_system/` is the only shipped product: a Blender 4.2+ extension. Keep projection mathematics in `blender_projection_system/core/`; these modules must remain importable without `bpy`. Blender-facing code lives in `properties.py`, `operators.py`, `ui.py`, and `visualization.py` and should delegate calculations to `core/`. Tests are under `tests/`; `test_*.py` files cover pure-Python behavior and contracts, while `tests/blender_smoke.py` exercises the real add-on. User documentation, feature notes, and architectural decisions live in `docs/manual/`, `docs/features/`, and `docs/adr/`.

## Build, Test, and Development Commands

Install the pinned development tools with `python -m pip install pytest==8.3.5 ruff==0.9.10`.

- `ruff check blender_projection_system tests` checks style, imports, and common bugs.
- `python -m compileall -q blender_projection_system tests` catches syntax errors.
- `pytest -v` runs the CPython suite without requiring Blender.
- `blender -b --factory-startup --python-exit-code 1 --python tests/blender_smoke.py` runs scene-level acceptance.
- `blender --factory-startup --command extension validate blender_projection_system` validates the extension manifest.
- `blender --factory-startup --command extension build --source-dir blender_projection_system --output-filepath projection_planner.zip` builds an installable archive.

## Coding Style & Naming Conventions

Use Python 3.11+, PEP 8, four-space indentation, and a configured 100-character line length. Ruff enforces `E`, `F`, `W`, `I`, `B`, and `UP`; run it before submitting. Follow existing `snake_case` functions, `PascalCase` data types, and Blender `PJ_OT_*`/`PJ_PT_*` class patterns. Use SI units throughout and radians unless a name ends in `_deg`. Document public APIs and non-obvious assumptions.

## Testing Guidelines

Name tests descriptively with `test_...`. Regression tests must call production functions; never duplicate a formula inside a test. Add focused pure-Python tests for `core/` changes and run the Blender smoke test for operators, registration, UI wiring, or generated scene content. No numeric coverage threshold is specified.

## Commit & Pull Request Guidelines

Recent history favors conventional prefixes such as `feat:` and `fix:`. Write imperative, present-tense subjects no longer than 72 characters. Pull requests should explain behavior and assumptions, list verification performed, link relevant issues in the body, and include screenshots for visible UI changes plus the tested Blender version and operating system. Do not put issue numbers in PR titles.

## Agent-Specific Safeguards

Read `README.md`, `CONTRIBUTING.md`, and the relevant ADR before changing behavior. Use pure-Python checks first, then the smallest Blender acceptance test needed. Never overwrite an unrelated open `.blend` file.
