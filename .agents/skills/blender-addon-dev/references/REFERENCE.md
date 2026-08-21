# Blender Add-on Property Types Reference

## Custom Properties (PropertyGroup)

```python
import bpy

class MySettings(bpy.types.PropertyGroup):
    my_bool: bpy.props.BoolProperty(
        name="Enable Feature",
        default=False
    )
    my_int: bpy.props.IntProperty(
        name="Count",
        default=5,
        min=1,
        max=100
    )
    my_float: bpy.props.FloatProperty(
        name="Factor",
        default=1.0,
        min=0.0,
        max=10.0,
        step=10,             # UI step (value * 0.01)
        precision=2
    )
    my_string: bpy.props.StringProperty(
        name="Label",
        default="",
        maxlen=256
    )
    my_enum: bpy.props.EnumProperty(
        name="Mode",
        items=[
            ('OPT_A', "Option A", "First option"),
            ('OPT_B', "Option B", "Second option"),
            ('OPT_C', "Option C", "Third option"),
        ],
        default='OPT_A'
    )
    my_color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        size=4,
        default=(1.0, 0.5, 0.0, 1.0),
        min=0.0,
        max=1.0
    )
    my_path: bpy.props.StringProperty(
        name="File Path",
        subtype='FILE_PATH'
    )

def register():
    bpy.utils.register_class(MySettings)
    bpy.types.Scene.my_settings = bpy.props.PointerProperty(type=MySettings)

def unregister():
    del bpy.types.Scene.my_settings
    bpy.utils.unregister_class(MySettings)
```

Access in panels: `context.scene.my_settings.my_bool`.

## All Property Types

- `BoolProperty` — checkbox
- `IntProperty` — integer input
- `FloatProperty` — float input with step/precision
- `StringProperty` — text input (subtypes: `FILE_PATH`, `DIR_PATH`, `NONE`)
- `EnumProperty` — dropdown/radio selector
- `FloatVectorProperty` — multi-float (subtypes: `COLOR`, `TRANSLATION`, `DIRECTION`, `XYZ`)
- `IntVectorProperty` — multi-int
- `PointerProperty` — reference to a PropertyGroup or Blender type
- `CollectionProperty` — list of PropertyGroup items
