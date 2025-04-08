bl_info = {
    "name": "Projection Planner MVP",
    "author": "Your Name & AI Assistant",
    "version": (0, 1, 0),
    "blender": (4, 2, 0), # Minimum Blender version
    "location": "View3D > Sidebar > Projection Tab",
    "description": "MVP for calculating and visualizing projector setups.",
    "warning": "",
    "doc_url": "", # Optional: link to documentation
    "category": "3D View",
}

import bpy

# Import modules
from . import properties
from . import ui
from . import operators
from . import visualization
# from . import utils # Will be added later

modules = [
    properties,
    ui,
    operators,
    visualization,
    # utils,
]

def register():
    for mod in modules:
        mod.register()

def unregister():
    # Unregister in reverse order
    for mod in reversed(modules):
        mod.unregister()

if __name__ == "__main__":
    register() 