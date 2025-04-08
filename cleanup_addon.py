import bpy

# Try to unregister the addon if it's enabled
try:
    bpy.ops.preferences.addon_disable(module="projection_system")
except Exception as e:
    print(f"Could not disable addon: {e}")

# Try to remove the PropertyGroup class if it's registered
try:
    bpy.utils.unregister_class(bpy.types.PJ_PG_ProjectorCollection)
except Exception as e:
    print(f"Could not unregister PJ_PG_ProjectorCollection: {e}")

# Remove any custom properties that might have been added
for prop in ['pj_unit_system']:
    if hasattr(bpy.types.Scene, prop):
        try:
            delattr(bpy.types.Scene, prop)
            print(f"Removed Scene.{prop}")
        except Exception as e:
            print(f"Could not remove Scene.{prop}: {e}")

# Remove object properties
for prop in ['pj_is_projector', 'pj_throw_distance', 'pj_image_width', 'pj_throw_ratio', 
             'pj_aspect_ratio_w', 'pj_aspect_ratio_h', 'pj_show_cone', 'pj_is_environment',
             'pj_collection', 'pj_overlaps_with', 'pj_edge_blend_amount', 'pj_is_active_projector']:
    if hasattr(bpy.types.Object, prop):
        try:
            delattr(bpy.types.Object, prop)
            print(f"Removed Object.{prop}")
        except Exception as e:
            print(f"Could not remove Object.{prop}: {e}")

# Remove scene collection properties
for prop in ['pj_projector_collections', 'pj_active_collection_index', 'pj_collection_selector']:
    if hasattr(bpy.types.Scene, prop):
        try:
            delattr(bpy.types.Scene, prop)
            print(f"Removed Scene.{prop}")
        except Exception as e:
            print(f"Could not remove Scene.{prop}: {e}")

print("Cleanup completed. Please restart Blender before installing the addon again.")
