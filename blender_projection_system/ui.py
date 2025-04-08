import bpy

class PJ_PT_ProjectionPanel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport N-Panel"""
    bl_label = "Projection Planner"
    bl_idname = "PJ_PT_projection_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Projection'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj = context.object

        # Display Unit System Toggle
        row = layout.row()
        row.prop(scene, "pj_unit_system", text="Unit System")
        
        # Add a separator
        layout.separator()
        
        # Environment Models Section
        box = layout.box()
        box.label(text="Environment", icon='WORLD')
        
        # Import Model Button
        row = box.row()
        row.operator("projection.import_model", text="Import Model", icon='IMPORT')
        
        # Create Basic Environment Button
        row = box.row()
        row.operator("projection.create_basic_environment", text="Create Basic Room", icon='HOME')
        
        # Environment object management options
        if context.object and context.object.pj_is_environment:
            row = box.row()
            row.label(text="Environment Object Selected")
            
            # Alignment tools
            if len(context.selected_objects) > 0 and context.active_object and context.active_object.pj_is_projector:
                row = box.row()
                row.operator("projection.align_to_projector", text="Align to Projector", icon='PIVOT_CURSOR')
                
                row = box.row()
                row.operator("projection.position_at_projection_distance", text="Position at Projection Distance", icon='CON_TRACKTO')
        
        # Add a separator
        layout.separator()
        
        # Add Projector Button
        row = layout.row()
        row.operator("projection.add_projector", text="Add Projector", icon='CAMERA_DATA')
        
        # Duplicate Projector Button (if a projector is selected)
        if obj and obj.pj_is_projector:
            row = layout.row()
            row.operator("projection.duplicate_projector", text="Duplicate Projector", icon='DUPLICATE')
        
        # Selected Projector Properties
        if obj and obj.pj_is_projector:
            box = layout.box()
            box.label(text="Selected Projector", icon='CAMERA_DATA')
            
            # Projector collection assignment (if collections exist)
            if hasattr(scene, 'pj_projector_collections') and len(scene.pj_projector_collections) > 0:
                row = box.row()
                row.label(text="Collection:")
                if obj.pj_collection:
                    row.label(text=obj.pj_collection)
                    row.operator("projection.remove_from_collection", text="", icon='X')
                else:
                    row.label(text="None")
                    row.operator("projection.add_to_collection", text="Add to Collection", icon='COLLECTION_NEW')
            
            # Projector parameters
            col = box.column(align=True)
            col.prop(obj, "pj_throw_distance")
            col.prop(obj, "pj_image_width")
            col.prop(obj, "pj_throw_ratio")
            
            # Aspect Ratio as X:Y
            row = box.row(align=True)
            row.label(text="Aspect Ratio:")
            row.prop(obj, "pj_aspect_ratio_w", text="")
            row.label(text=":")
            row.prop(obj, "pj_aspect_ratio_h", text="")
            
            # Multi-projector properties
            if obj.pj_overlaps_with:
                box.separator()
                row = box.row()
                row.label(text=f"Overlaps with: {obj.pj_overlaps_with}", icon='ERROR')
                
                row = box.row()
                row.prop(obj, "pj_edge_blend_amount", text="Edge Blend")
            
            # Visualization section
            box.separator()
            row = box.row()
            row.label(text="Visualization:")
            
            # Show/Hide Cone toggle
            row = box.row()
            row.prop(obj, "pj_show_cone", text="Show Projection Cone")
            
            # Add Projection Cone Button
            row = box.row()
            row.operator("projection.add_projection_cone", text="Add Projection Cone", icon='MESH_CONE')
            
            # Add Test Surface Button
            row = box.row()
            row.operator("projection.create_test_surface", text="Create Test Surface", icon='MESH_PLANE')
            
            # Add Projection Mapping Button
            row = box.row()
            row.operator("projection.setup_projection_mapping", text="Setup Projection Mapping", icon='MATERIAL')
            
            # Add test parameter linking button
            layout.separator()
            box = layout.box()
            box.label(text="Development Tools")
            row = box.row()
            row.operator("projection.test_parameter_linking", text="Test Parameter Linking", icon='VIEWZOOM')
        else:
            # If no projector is selected, show information
            box = layout.box()
            box.label(text="No Projector Selected", icon='INFO')
            box.label(text="Select a projector or add a new one")

class PJ_PT_ProjectorCollectionsPanel(bpy.types.Panel):
    """Panel for managing projector collections"""
    bl_label = "Multi-Projector Setup"
    bl_idname = "PJ_PT_projector_collections_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Projection'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Create a new collection
        box = layout.box()
        box.label(text="Projector Collections", icon='OUTLINER_COLLECTION')
        
        # Create a new projector collection
        row = box.row()
        op = row.operator("projection.create_projector_collection", text="Create Collection", icon='COLLECTION_NEW')
        
        # List existing collections if any
        if hasattr(scene, 'pj_projector_collections') and len(scene.pj_projector_collections) > 0:
            box.separator()
            box.label(text="Available Collections:")
            
            # Display each collection and its controls
            for i, collection in enumerate(scene.pj_projector_collections):
                row = box.row(align=True)
                
                # Highlight active collection
                if i == scene.pj_active_collection_index:
                    row.label(text=collection.name, icon='COLLECTION_COLOR_01')
                else:
                    row.label(text=collection.name, icon='COLLECTION_COLOR_02')
                
                # Set as active
                op = row.operator("projection.set_active_collection", text="", icon='RADIOBUT_ON')
                op.collection_index = i
                
                # Delete collection
                op = row.operator("projection.delete_collection", text="", icon='X')
            
            # Show options for the active collection
            if scene.pj_active_collection_index < len(scene.pj_projector_collections):
                active_collection = scene.pj_projector_collections[scene.pj_active_collection_index].name
                
                box.separator()
                box.label(text=f"Active: {active_collection}")
                
                # Collection management tools
                row = box.row()
                row.operator("projection.add_to_collection", text="Add Selected", icon='COLLECTION_NEW')
                
                row = box.row()
                row.operator("projection.align_group", text="Align Projectors", icon='MOD_ARRAY')
                
                row = box.row()
                row.operator("projection.detect_overlapping", text="Detect Overlapping", icon='MOD_BOOLEAN')
        
        # Display multi-projector stats
        box = layout.box()
        box.label(text="Multi-Projector Stats", icon='INFO')
        
        # Count projectors and collections
        projector_count = len([obj for obj in bpy.data.objects if obj.pj_is_projector])
        collection_count = len(scene.pj_projector_collections) if hasattr(scene, 'pj_projector_collections') else 0
        
        # Display counts
        row = box.row()
        row.label(text=f"Total Projectors: {projector_count}")
        
        row = box.row()
        row.label(text=f"Collections: {collection_count}")
        
        # Count overlapping projectors
        overlapping_count = len([obj for obj in bpy.data.objects 
                              if obj.pj_is_projector and obj.pj_overlaps_with])
        
        row = box.row()
        row.label(text=f"Overlapping Projectors: {overlapping_count}")

# Operator to set the active collection
class PJ_OT_set_active_collection(bpy.types.Operator):
    """Set the active projector collection"""
    bl_idname = "projection.set_active_collection"
    bl_label = "Set Active Collection"
    bl_options = {'REGISTER', 'UNDO'}
    
    collection_index: bpy.props.IntProperty(
        name="Collection Index",
        default=0
    )
    
    def execute(self, context):
        scene = context.scene
        
        if not hasattr(scene, 'pj_projector_collections'):
            self.report({'ERROR'}, "No projector collections available")
            return {'CANCELLED'}
        
        if self.collection_index >= len(scene.pj_projector_collections):
            self.report({'ERROR'}, "Invalid collection index")
            return {'CANCELLED'}
        
        # Set the active collection
        scene.pj_active_collection_index = self.collection_index
        
        collection_name = scene.pj_projector_collections[self.collection_index].name
        self.report({'INFO'}, f"Set active collection to '{collection_name}'")
        
        return {'FINISHED'}

def register():
    bpy.utils.register_class(PJ_PT_ProjectionPanel)
    bpy.utils.register_class(PJ_PT_ProjectorCollectionsPanel)
    bpy.utils.register_class(PJ_OT_set_active_collection)

def unregister():
    bpy.utils.unregister_class(PJ_OT_set_active_collection)
    bpy.utils.unregister_class(PJ_PT_ProjectorCollectionsPanel)
    bpy.utils.unregister_class(PJ_PT_ProjectionPanel)

if __name__ == "__main__":
    register() 