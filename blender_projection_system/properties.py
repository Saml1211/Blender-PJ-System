import bpy

# Global variable to track update state
_updating_projection_params = False

# Update functions for bidirectional parameter linking
def update_throw_distance(self, context):
    # Prevent recursive updates by checking if we're already updating
    global _updating_projection_params
    if _updating_projection_params:
        return

    _updating_projection_params = True
    # When throw distance changes, update throw ratio (TR = D/W)
    if self.pj_image_width > 0:
        self.pj_throw_ratio = self.pj_throw_distance / self.pj_image_width
    _updating_projection_params = False

def update_image_width(self, context):
    # Prevent recursive updates
    global _updating_projection_params
    if _updating_projection_params:
        return

    _updating_projection_params = True
    # When image width changes, update throw ratio (TR = D/W)
    if self.pj_image_width > 0:
        self.pj_throw_ratio = self.pj_throw_distance / self.pj_image_width
    _updating_projection_params = False

def update_throw_ratio(self, context):
    # Prevent recursive updates
    global _updating_projection_params
    if _updating_projection_params:
        return

    _updating_projection_params = True
    # When throw ratio changes, update image width (W = D/TR)
    if self.pj_throw_ratio > 0:
        self.pj_image_width = self.pj_throw_distance / self.pj_throw_ratio
    _updating_projection_params = False

# Collection functionality
def update_active_collection(self, context):
    # Callback for when active collection changes
    pass

def get_collection_items(self, context):
    # Get list of collections for dropdown menu
    items = []

    if hasattr(context.scene, 'pj_projector_collections'):
        for i, coll in enumerate(context.scene.pj_projector_collections):
            items.append((coll.name, coll.name, f"Projector Collection: {coll.name}", i))

    # Always add option for no collection
    if not items:
        items.append(("", "No Collections", "No projector collections available", 0))

    return items

# Property group for projector collections
class PJ_PG_ProjectorCollectionV2(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(
        name="Collection Name",
        description="Name of the projector collection",
        default=""
    )

def register():
    # Register the property group first
    try:
        bpy.utils.register_class(PJ_PG_ProjectorCollectionV2)
    except ValueError as e:
        # Class is already registered, which can happen if the addon wasn't properly unregistered
        if "already registered" in str(e):
            print("PJ_PG_ProjectorCollectionV2 already registered, skipping registration")
        else:
            raise e

    # Scene property for unit system
    bpy.types.Scene.pj_unit_system = bpy.props.EnumProperty(
        name="Unit System",
        description="Unit system for display",
        items=[
            ('METRIC', "Metric", "Use Metric units (meters)"),
            ('IMPERIAL', "Imperial", "Use Imperial units (feet/inches)")
        ],
        default='METRIC'
    )

    # Custom properties for projector objects
    bpy.types.Object.pj_is_projector = bpy.props.BoolProperty(
        name="Is Projector",
        description="Identifies this object as a projector",
        default=False
    )

    bpy.types.Object.pj_throw_distance = bpy.props.FloatProperty(
        name="Throw Distance",
        description="Distance from projector to projection surface (in meters)",
        min=0.1,
        default=4.0,
        precision=3,
        unit='LENGTH',
        update=update_throw_distance
    )

    bpy.types.Object.pj_image_width = bpy.props.FloatProperty(
        name="Image Width",
        description="Width of the projected image (in meters)",
        min=0.1,
        default=2.0,
        precision=3,
        unit='LENGTH',
        update=update_image_width
    )

    bpy.types.Object.pj_throw_ratio = bpy.props.FloatProperty(
        name="Throw Ratio",
        description="Ratio of throw distance to image width",
        min=0.1,
        default=2.0,
        precision=3,
        update=update_throw_ratio
    )

    bpy.types.Object.pj_aspect_ratio_w = bpy.props.IntProperty(
        name="Aspect Width",
        description="Width component of aspect ratio (e.g., 16 for 16:9)",
        min=1,
        default=16
    )

    bpy.types.Object.pj_aspect_ratio_h = bpy.props.IntProperty(
        name="Aspect Height",
        description="Height component of aspect ratio (e.g., 9 for 16:9)",
        min=1,
        default=9
    )

    bpy.types.Object.pj_show_cone = bpy.props.BoolProperty(
        name="Show Projection Cone",
        description="Toggle visibility of the projection cone",
        default=True
    )

    # Environment object property
    bpy.types.Object.pj_is_environment = bpy.props.BoolProperty(
        name="Is Environment",
        description="Identifies this object as part of the projection environment",
        default=False
    )

    # Multi-projector support properties

    # Projector collection property
    bpy.types.Object.pj_collection = bpy.props.StringProperty(
        name="Projector Collection",
        description="Collection this projector belongs to",
        default=""
    )

    # Overlapping projection property
    bpy.types.Object.pj_overlaps_with = bpy.props.StringProperty(
        name="Overlaps With",
        description="Name of projector this one overlaps with",
        default=""
    )

    # Edge blend amount
    bpy.types.Object.pj_edge_blend_amount = bpy.props.FloatProperty(
        name="Edge Blend Amount",
        description="Amount of edge blending for overlapping projections",
        min=0.0,
        max=1.0,
        default=0.2
    )

    # Multi-projector activation toggle
    bpy.types.Object.pj_is_active_projector = bpy.props.BoolProperty(
        name="Active Projector",
        description="Whether this projector is active in the group",
        default=True
    )

    # Scene properties for collection management

    # List to store projector collections
    bpy.types.Scene.pj_projector_collections = bpy.props.CollectionProperty(
        type=PJ_PG_ProjectorCollectionV2,
        name="Projector Collections",
        description="Collections of projectors for grouped management"
    )

    # Active collection index
    bpy.types.Scene.pj_active_collection_index = bpy.props.IntProperty(
        name="Active Collection Index",
        description="Index of the active projector collection",
        default=0,
        update=update_active_collection
    )

    # Collection selector for UI
    bpy.types.Scene.pj_collection_selector = bpy.props.EnumProperty(
        name="Projector Collection",
        description="Select projector collection to work with",
        items=get_collection_items
    )

def unregister():
    del bpy.types.Scene.pj_unit_system

    # Remove custom properties
    del bpy.types.Object.pj_is_projector
    del bpy.types.Object.pj_throw_distance
    del bpy.types.Object.pj_image_width
    del bpy.types.Object.pj_throw_ratio
    del bpy.types.Object.pj_aspect_ratio_w
    del bpy.types.Object.pj_aspect_ratio_h
    del bpy.types.Object.pj_show_cone
    del bpy.types.Object.pj_is_environment

    # Remove multi-projector properties
    del bpy.types.Object.pj_collection
    del bpy.types.Object.pj_overlaps_with
    del bpy.types.Object.pj_edge_blend_amount
    del bpy.types.Object.pj_is_active_projector

    # Remove scene collection properties
    del bpy.types.Scene.pj_projector_collections
    del bpy.types.Scene.pj_active_collection_index
    del bpy.types.Scene.pj_collection_selector

    # Unregister the property group last
    try:
        bpy.utils.unregister_class(PJ_PG_ProjectorCollectionV2)
    except ValueError as e:
        # Class might not be registered, which can happen if it wasn't registered properly
        if "not registered" in str(e):
            print("PJ_PG_ProjectorCollectionV2 not registered, skipping unregistration")
        else:
            raise e

if __name__ == "__main__":
    register()