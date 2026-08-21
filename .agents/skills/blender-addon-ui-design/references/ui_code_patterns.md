# Blender UI Code Patterns

## Panel with grouped actions

```python
import bpy


class MYADDON_PT_main(bpy.types.Panel):
    bl_label = "My Add-on"
    bl_idname = "MYADDON_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "My Addon"

    def draw(self, context):
        layout = self.layout
        props = context.scene.my_addon_props

        col = layout.column(align=True)
        col.prop(props, "source_path")
        col.prop(props, "output_path")

        action_box = layout.box()
        action_box.label(text="Actions")
        row = action_box.row(align=True)
        row.operator("myaddon.build_preview", icon="RENDER_STILL")
        row.operator("myaddon.export_result", icon="EXPORT")
```

## Conditional controls

```python
def draw(self, context):
    layout = self.layout
    props = context.scene.my_addon_props

    layout.prop(props, "use_advanced")
    advanced = layout.column()
    advanced.enabled = props.use_advanced
    advanced.prop(props, "max_iterations")
    advanced.prop(props, "tolerance")
```

## Subpanel pattern

```python
class MYADDON_PT_advanced(bpy.types.Panel):
    bl_label = "Advanced"
    bl_idname = "MYADDON_PT_advanced"
    bl_parent_id = "MYADDON_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}
```

## Add-on preferences pattern

```python
class MYADDON_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    default_export_dir: bpy.props.StringProperty(
        name="Default Export Directory",
        subtype="DIR_PATH",
    )

    def draw(self, context):
        self.layout.prop(self, "default_export_dir")
```

## UIList pattern

```python
class MYADDON_UL_items(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            layout.label(text=item.name, icon="OBJECT_DATA")
        else:
            layout.alignment = "CENTER"
            layout.label(text="")
```

## Registration pattern

```python
classes = (
    MYADDON_Preferences,
    MYADDON_PT_main,
    MYADDON_PT_advanced,
    MYADDON_UL_items,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
```
