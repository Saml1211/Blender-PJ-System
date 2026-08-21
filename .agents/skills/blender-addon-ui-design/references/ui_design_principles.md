# Blender Add-on UI Design Principles

## 1. Optimize for task flow

- Place the most-used action near the top of each panel.
- Keep one panel dedicated to one workflow.
- Avoid mixed concerns in a single panel.

## 2. Minimize visual noise

- Use section labels only when they add structure.
- Use boxes sparingly to group strongly related controls.
- Avoid repeating labels that are obvious from context.

## 3. Use progressive disclosure

- Show essential controls first.
- Hide advanced controls behind toggles.
- Reveal dependent fields only when prerequisites are enabled.

## 4. Make state and consequences obvious

- Disable unavailable controls with clear status messages nearby.
- Use operator names that imply effects (for example, "Bake Preview", "Export Selected").
- Confirm destructive operations with dialogs.

## 5. Keep interaction responsive

- Avoid heavy data scans in `draw()`.
- Cache computed summaries where practical.
- Trigger expensive work in operators, not panel redraw.

## 6. Respect Blender conventions

- Match existing naming style and capitalization in labels.
- Use standard region placement and categories unless a strong reason exists.
- Prefer familiar iconography and order of controls.

## 7. Design for narrow sidebars

- Test panel layout at minimum useful width.
- Avoid long single-row control chains.
- Use aligned columns for forms with many properties.

## 8. Accessibility and readability

- Keep labels concise and unambiguous.
- Avoid relying on color alone to communicate status.
- Ensure status text still makes sense without icons.
