#!/usr/bin/env python3
"""Generate a Blender add-on package focused on UI design patterns."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from textwrap import dedent


def normalize_module_name(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        raise ValueError("Module name cannot be empty after normalization.")
    return value


def parse_version(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"Invalid version '{value}'. Use MAJOR.MINOR.PATCH.")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def version_literal(version: tuple[int, int, int]) -> str:
    return f"({version[0]}, {version[1]}, {version[2]})"


def class_prefix(module_name: str) -> str:
    return "".join(part.capitalize() for part in module_name.split("_"))


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_compat_py() -> str:
    return dedent(
        """\
        import bpy


        def blender_50_or_newer():
            return bpy.app.version >= (5, 0, 0)


        def ui_emboss_pie_value():
            return "PIE_MENU" if blender_50_or_newer() else "RADIAL_MENU"
        """
    )


def build_properties_py(prefix: str) -> str:
    return dedent(
        f"""\
        import bpy


        class {prefix}_PG_settings(bpy.types.PropertyGroup):
            source_path: bpy.props.StringProperty(
                name="Source Path",
                subtype="FILE_PATH",
            )
            output_path: bpy.props.StringProperty(
                name="Output Path",
                subtype="DIR_PATH",
            )
            use_advanced: bpy.props.BoolProperty(
                name="Advanced",
                default=False,
            )
            quality: bpy.props.IntProperty(
                name="Quality",
                default=75,
                min=1,
                max=100,
            )


        classes = (
            {prefix}_PG_settings,
        )


        def register():
            for cls in classes:
                bpy.utils.register_class(cls)
            bpy.types.Scene.{prefix.lower()}_settings = bpy.props.PointerProperty(
                type={prefix}_PG_settings
            )


        def unregister():
            del bpy.types.Scene.{prefix.lower()}_settings
            for cls in reversed(classes):
                bpy.utils.unregister_class(cls)
        """
    )


def build_operators_py(module_name: str, prefix: str) -> str:
    return dedent(
        f"""\
        import bpy


        class {prefix}_OT_preview(bpy.types.Operator):
            bl_idname = "{module_name}.preview"
            bl_label = "Build Preview"
            bl_options = {{"REGISTER", "UNDO"}}

            @classmethod
            def poll(cls, context):
                return context is not None

            def execute(self, context):
                self.report({{"INFO"}}, "Preview generated")
                return {{"FINISHED"}}


        class {prefix}_OT_export(bpy.types.Operator):
            bl_idname = "{module_name}.export"
            bl_label = "Export"
            bl_options = {{"REGISTER"}}

            @classmethod
            def poll(cls, context):
                return context is not None

            def execute(self, context):
                self.report({{"INFO"}}, "Export complete")
                return {{"FINISHED"}}


        classes = (
            {prefix}_OT_preview,
            {prefix}_OT_export,
        )
        """
    )


def build_ui_py(module_name: str, prefix: str, panel_label: str, category: str) -> str:
    pointer_name = f"{prefix.lower()}_settings"
    return dedent(
        f"""\
        import bpy


        class {prefix}_PT_main(bpy.types.Panel):
            bl_label = "{panel_label}"
            bl_idname = "{prefix}_PT_main"
            bl_space_type = "VIEW_3D"
            bl_region_type = "UI"
            bl_category = "{category}"

            def draw(self, context):
                layout = self.layout
                settings = context.scene.{pointer_name}

                col = layout.column(align=True)
                col.prop(settings, "source_path")
                col.prop(settings, "output_path")

                layout.separator()
                layout.prop(settings, "use_advanced")
                advanced = layout.column()
                advanced.enabled = settings.use_advanced
                advanced.prop(settings, "quality")

                row = layout.row(align=True)
                row.operator("{module_name}.preview", icon="RENDER_STILL")
                row.operator("{module_name}.export", icon="EXPORT")


        class {prefix}_PT_advanced(bpy.types.Panel):
            bl_label = "Advanced"
            bl_idname = "{prefix}_PT_advanced"
            bl_parent_id = "{prefix}_PT_main"
            bl_space_type = "VIEW_3D"
            bl_region_type = "UI"
            bl_options = {{"DEFAULT_CLOSED"}}

            def draw(self, context):
                layout = self.layout
                settings = context.scene.{pointer_name}
                layout.label(text="Advanced Configuration")
                layout.prop(settings, "quality")


        classes = (
            {prefix}_PT_main,
            {prefix}_PT_advanced,
        )
        """
    )


def build_preferences_py(prefix: str, module_name: str) -> str:
    return dedent(
        f"""\
        import bpy


        class {prefix}_PREFERENCES(bpy.types.AddonPreferences):
            bl_idname = "{module_name}"

            default_output_dir: bpy.props.StringProperty(
                name="Default Output Directory",
                subtype="DIR_PATH",
            )

            def draw(self, context):
                layout = self.layout
                layout.prop(self, "default_output_dir")


        classes = (
            {prefix}_PREFERENCES,
        )
        """
    )


def build_init_py(
    addon_name: str,
    author: str,
    addon_version: tuple[int, int, int],
    blender_min: tuple[int, int, int],
    category: str,
    _module_name: str,
) -> str:
    return dedent(
        f"""\
        bl_info = {{
            "name": "{addon_name}",
            "author": "{author}",
            "version": {version_literal(addon_version)},
            "blender": {version_literal(blender_min)},
            "location": "View3D > Sidebar",
            "description": "UI-focused add-on scaffold generated by scaffold_ui_module.py",
            "warning": "",
            "doc_url": "",
            "category": "{category}",
        }}

        import bpy

        from . import compat, operators, preferences, properties, ui


        def register():
            properties.register()
            for cls in preferences.classes:
                bpy.utils.register_class(cls)
            for cls in operators.classes:
                bpy.utils.register_class(cls)
            for cls in ui.classes:
                bpy.utils.register_class(cls)


        def unregister():
            for cls in reversed(ui.classes):
                bpy.utils.unregister_class(cls)
            for cls in reversed(operators.classes):
                bpy.utils.unregister_class(cls)
            for cls in reversed(preferences.classes):
                bpy.utils.unregister_class(cls)
            properties.unregister()


        if __name__ == "__main__":
            register()
        """
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold a Blender add-on package optimized for UI development."
    )
    parser.add_argument("--name", required=True, help="Human-readable add-on name.")
    parser.add_argument("--module", help="Package/module name. Defaults to normalized --name.")
    parser.add_argument("--author", default="Codex", help="Author for bl_info.")
    parser.add_argument("--version", default="0.1.0", help="Add-on version MAJOR.MINOR.PATCH.")
    parser.add_argument("--blender-min", default="4.0.0", help="Minimum Blender version.")
    parser.add_argument("--category", default="3D View", help="Sidebar tab/category label.")
    parser.add_argument("--output", default=".", help="Target directory for package folder.")
    parser.add_argument("--force", action="store_true", help="Overwrite files if they exist.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    module_name = normalize_module_name(args.module or args.name)
    prefix = class_prefix(module_name)
    addon_version = parse_version(args.version)
    blender_min = parse_version(args.blender_min)

    package_dir = Path(args.output).expanduser().resolve() / module_name
    package_dir.mkdir(parents=True, exist_ok=True)

    targets = [
        package_dir / "__init__.py",
        package_dir / "compat.py",
        package_dir / "properties.py",
        package_dir / "operators.py",
        package_dir / "ui.py",
        package_dir / "preferences.py",
    ]
    if not args.force:
        existing = [target.name for target in targets if target.exists()]
        if existing:
            raise FileExistsError(
                f"Refusing to overwrite existing files: {', '.join(existing)}. Use --force."
            )

    write_file(package_dir / "compat.py", build_compat_py())
    write_file(package_dir / "properties.py", build_properties_py(prefix))
    write_file(package_dir / "operators.py", build_operators_py(module_name, prefix))
    write_file(
        package_dir / "ui.py",
        build_ui_py(module_name, prefix, panel_label=args.name, category=args.category),
    )
    write_file(package_dir / "preferences.py", build_preferences_py(prefix, module_name))
    write_file(
        package_dir / "__init__.py",
        build_init_py(
            addon_name=args.name,
            author=args.author,
            addon_version=addon_version,
            blender_min=blender_min,
            category=args.category,
            _module_name=module_name,
        ),
    )

    print(f"Generated UI add-on scaffold at: {package_dir}")
    print("Files: __init__.py, compat.py, properties.py, operators.py, ui.py, preferences.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
