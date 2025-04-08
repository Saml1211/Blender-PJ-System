import bpy
from bpy.types import Operator
from mathutils import Vector
from . import visualization

class PJ_OT_add_projector(Operator):
    """Add a new projector object to the scene"""
    bl_idname = "projection.add_projector"
    bl_label = "Add Projector"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Create a parent empty for the projector
        projector_empty = bpy.data.objects.new("Projector", None)
        projector_empty.empty_display_type = 'ARROWS'
        projector_empty.empty_display_size = 0.5

        # Link the empty to the scene
        context.collection.objects.link(projector_empty)

        # Create a simple box mesh for the projector body
        bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0, 0, 0))
        projector_body = context.active_object
        projector_body.name = "Projector_Body"
        projector_body.scale = (1, 2, 0.75)  # Make it look more like a projector

        # Create a camera for the projection source
        projection_cam = bpy.data.cameras.new("Projection_Camera")
        projection_cam_obj = bpy.data.objects.new("Projection_Source", projection_cam)
        context.collection.objects.link(projection_cam_obj)

        # Position the camera at the front of the projector body
        projection_cam_obj.location = (0, -0.3, 0)

        # Set up parent relationships
        projector_body.parent = projector_empty
        projection_cam_obj.parent = projector_empty

        # No need to initialize updating flag anymore - we'll use a global variable in properties.py

        # Set up custom properties on the empty
        projector_empty.pj_is_projector = True
        projector_empty.pj_throw_distance = 4.0  # Default 4 meters
        projector_empty.pj_image_width = 2.0     # Default 2 meters
        projector_empty.pj_throw_ratio = 2.0     # Default TR = 2.0
        projector_empty.pj_aspect_ratio_w = 16   # Default 16:9
        projector_empty.pj_aspect_ratio_h = 9

        # Select the projector empty
        bpy.ops.object.select_all(action='DESELECT')
        projector_empty.select_set(True)
        context.view_layer.objects.active = projector_empty

        # Add projection cone visualization
        visualization.setup_projection_cone_nodes(projector_empty)

        return {'FINISHED'}

class PJ_OT_test_parameter_linking(Operator):
    """Test bidirectional parameter linking between throw distance, image width, and throw ratio"""
    bl_idname = "projection.test_parameter_linking"
    bl_label = "Test Parameter Linking"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object

        if not (obj and obj.pj_is_projector):
            self.report({'ERROR'}, "No projector selected")
            return {'CANCELLED'}

        # Store initial values
        initial_throw_distance = obj.pj_throw_distance
        initial_image_width = obj.pj_image_width
        initial_throw_ratio = obj.pj_throw_ratio

        # Get the scene object to store the test results
        scene = context.scene

        # Test 1: Change throw distance
        test_throw_distance = initial_throw_distance * 1.5
        obj.pj_throw_distance = test_throw_distance

        # Test 2: Change image width
        test_image_width = initial_image_width * 0.8
        obj.pj_image_width = test_image_width

        # Test 3: Change throw ratio
        test_throw_ratio = initial_throw_ratio * 1.2
        obj.pj_throw_ratio = test_throw_ratio

        # Report the test results
        self.report({'INFO'}, f"Parameter linking test completed successfully. Check console for results.")

        # Print the test results to the console
        print("\n=== PROJECTOR PARAMETER LINKING TEST ===")
        print(f"Initial state: D={initial_throw_distance:.3f}m, W={initial_image_width:.3f}m, TR={initial_throw_ratio:.3f}")

        print("\nTest 1: Changed throw distance to {:.3f}m".format(test_throw_distance))
        print(f"Expected throw ratio: {test_throw_distance/test_image_width:.3f}")
        print(f"Actual throw ratio: {obj.pj_throw_ratio:.3f}")

        print("\nTest 2: Changed image width to {:.3f}m".format(test_image_width))
        print(f"Expected throw ratio: {obj.pj_throw_distance/test_image_width:.3f}")
        print(f"Actual throw ratio: {obj.pj_throw_ratio:.3f}")

        print("\nTest 3: Changed throw ratio to {:.3f}".format(test_throw_ratio))
        print(f"Expected image width: {obj.pj_throw_distance/test_throw_ratio:.3f}m")
        print(f"Actual image width: {obj.pj_image_width:.3f}m")
        print("========================================\n")

        return {'FINISHED'}

class PJ_OT_import_model(Operator):
    """Import a model for the projection environment"""
    bl_idname = "projection.import_model"
    bl_label = "Import Environment Model"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(
        name="File Path",
        description="Path to the file",
        maxlen=1024,
        default="",
        subtype='FILE_PATH'
    )

    filter_glob: bpy.props.StringProperty(
        default="*.obj;*.fbx",
        options={'HIDDEN'}
    )

    scale: bpy.props.FloatProperty(
        name="Import Scale",
        description="Scale factor for the imported model",
        default=1.0,
        min=0.001,
        max=1000.0
    )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        import os

        # Get the file extension
        _, ext = os.path.splitext(self.filepath)
        ext = ext.lower()

        try:
            # Import the model based on the file extension
            if ext == '.obj':
                bpy.ops.import_scene.obj(filepath=self.filepath, global_scale=self.scale)
            elif ext == '.fbx':
                bpy.ops.import_scene.fbx(filepath=self.filepath, global_scale=self.scale)
            else:
                self.report({'ERROR'}, f"Unsupported file format: {ext}")
                return {'CANCELLED'}

            # Get the imported objects
            imported_objects = context.selected_objects

            # Tag the objects as projection environment
            for obj in imported_objects:
                obj.pj_is_environment = True

            self.report({'INFO'}, f"Imported {len(imported_objects)} objects as environment model")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {str(e)}")
            return {'CANCELLED'}

class PJ_OT_align_to_projector(Operator):
    """Align selected objects to the active projector"""
    bl_idname = "projection.align_to_projector"
    bl_label = "Align to Projector"
    bl_options = {'REGISTER', 'UNDO'}

    distance: bpy.props.FloatProperty(
        name="Distance",
        description="Distance from projector to place objects",
        default=4.0,
        min=0.1,
        unit='LENGTH'
    )

    @classmethod
    def poll(cls, context):
        # Check if there's an active projector and selected objects
        return (context.active_object and
                context.active_object.pj_is_projector and
                len(context.selected_objects) > 1)

    def execute(self, context):
        projector = context.active_object

        if not projector.pj_is_projector:
            self.report({'ERROR'}, "Active object is not a projector")
            return {'CANCELLED'}

        # Get the projector's forward direction (negative Y-axis in local space)
        forward_vec = projector.matrix_world.to_3x3() @ Vector((0, -1, 0))
        forward_vec.normalize()

        # Calculate the target position
        target_pos = projector.matrix_world.translation + (forward_vec * self.distance)

        # Count how many objects were aligned
        aligned_count = 0

        # Process all selected objects except the active projector
        for obj in context.selected_objects:
            if obj != projector:
                # Position the object at the target position
                obj.location = target_pos
                aligned_count += 1

        self.report({'INFO'}, f"Aligned {aligned_count} objects to projector at {self.distance}m distance")

        return {'FINISHED'}

class PJ_OT_position_at_projection_distance(Operator):
    """Position selected objects at the projector's throw distance"""
    bl_idname = "projection.position_at_projection_distance"
    bl_label = "Position at Projection Distance"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Check if there's an active projector and selected objects
        return (context.active_object and
                context.active_object.pj_is_projector and
                len(context.selected_objects) > 1)

    def execute(self, context):
        projector = context.active_object

        if not projector.pj_is_projector:
            self.report({'ERROR'}, "Active object is not a projector")
            return {'CANCELLED'}

        # Get the projector's throw distance
        distance = projector.pj_throw_distance

        # Get the projector's forward direction (negative Y-axis in local space)
        forward_vec = projector.matrix_world.to_3x3() @ Vector((0, -1, 0))
        forward_vec.normalize()

        # Calculate the target position
        target_pos = projector.matrix_world.translation + (forward_vec * distance)

        # Count how many objects were positioned
        positioned_count = 0

        # Process all selected objects except the active projector
        for obj in context.selected_objects:
            if obj != projector:
                # Position the object at the target position
                obj.location = target_pos
                positioned_count += 1

        self.report({'INFO'}, f"Positioned {positioned_count} objects at projection distance ({distance}m)")

        return {'FINISHED'}

class PJ_OT_create_basic_environment(Operator):
    """Create a basic projection environment with walls and floor"""
    bl_idname = "projection.create_basic_environment"
    bl_label = "Create Basic Environment"
    bl_options = {'REGISTER', 'UNDO'}

    room_width: bpy.props.FloatProperty(
        name="Room Width",
        description="Width of the room",
        default=10.0,
        min=1.0,
        unit='LENGTH'
    )

    room_length: bpy.props.FloatProperty(
        name="Room Length",
        description="Length of the room",
        default=10.0,
        min=1.0,
        unit='LENGTH'
    )

    room_height: bpy.props.FloatProperty(
        name="Room Height",
        description="Height of the room",
        default=3.0,
        min=1.0,
        unit='LENGTH'
    )

    def execute(self, context):
        # Create a collection for the environment
        env_col = bpy.data.collections.new("Projection Environment")
        context.scene.collection.children.link(env_col)

        # Create the floor
        bpy.ops.mesh.primitive_plane_add(
            size=1.0,
            location=(0, 0, 0)
        )
        floor = context.active_object
        floor.name = "Floor"
        floor.scale.x = self.room_width / 2
        floor.scale.y = self.room_length / 2

        # Tag as environment object
        floor.pj_is_environment = True

        # Create the walls
        # Back wall
        bpy.ops.mesh.primitive_plane_add(
            size=1.0,
            location=(0, self.room_length/2, self.room_height/2),
            rotation=(1.5708, 0, 0)  # 90 degrees in X
        )
        back_wall = context.active_object
        back_wall.name = "Back_Wall"
        back_wall.scale.x = self.room_width / 2
        back_wall.scale.y = self.room_height / 2
        back_wall.pj_is_environment = True

        # Front wall
        bpy.ops.mesh.primitive_plane_add(
            size=1.0,
            location=(0, -self.room_length/2, self.room_height/2),
            rotation=(1.5708, 0, 0)  # 90 degrees in X
        )
        front_wall = context.active_object
        front_wall.name = "Front_Wall"
        front_wall.scale.x = self.room_width / 2
        front_wall.scale.y = self.room_height / 2
        front_wall.pj_is_environment = True

        # Left wall
        bpy.ops.mesh.primitive_plane_add(
            size=1.0,
            location=(-self.room_width/2, 0, self.room_height/2),
            rotation=(1.5708, 0, 1.5708)  # 90 degrees in X and Z
        )
        left_wall = context.active_object
        left_wall.name = "Left_Wall"
        left_wall.scale.x = self.room_length / 2
        left_wall.scale.y = self.room_height / 2
        left_wall.pj_is_environment = True

        # Right wall
        bpy.ops.mesh.primitive_plane_add(
            size=1.0,
            location=(self.room_width/2, 0, self.room_height/2),
            rotation=(1.5708, 0, 1.5708)  # 90 degrees in X and Z
        )
        right_wall = context.active_object
        right_wall.name = "Right_Wall"
        right_wall.scale.x = self.room_length / 2
        right_wall.scale.y = self.room_height / 2
        right_wall.pj_is_environment = True

        # Move all objects to the environment collection
        for obj in [floor, back_wall, front_wall, left_wall, right_wall]:
            # First remove from current collection
            for col in obj.users_collection:
                col.objects.unlink(obj)
            # Then add to environment collection
            env_col.objects.link(obj)

        self.report({'INFO'}, f"Created basic environment: {self.room_width}m x {self.room_length}m x {self.room_height}m")

        return {'FINISHED'}

class PJ_OT_duplicate_projector(Operator):
    """Create a duplicate of the active projector with the same settings"""
    bl_idname = "projection.duplicate_projector"
    bl_label = "Duplicate Projector"
    bl_options = {'REGISTER', 'UNDO'}

    offset_distance: bpy.props.FloatProperty(
        name="Offset Distance",
        description="Distance to offset the new projector",
        default=1.0,
        min=0.1,
        unit='LENGTH'
    )

    @classmethod
    def poll(cls, context):
        # Check if there's an active projector
        return (context.active_object and
                context.active_object.pj_is_projector)

    def execute(self, context):
        original_projector = context.active_object

        if not original_projector.pj_is_projector:
            self.report({'ERROR'}, "Active object is not a projector")
            return {'CANCELLED'}

        # Store the original projector's settings
        orig_throw_distance = original_projector.pj_throw_distance
        orig_image_width = original_projector.pj_image_width
        orig_throw_ratio = original_projector.pj_throw_ratio
        orig_aspect_ratio_w = original_projector.pj_aspect_ratio_w
        orig_aspect_ratio_h = original_projector.pj_aspect_ratio_h

        # Get the original projector's right direction (X-axis in local space)
        right_vec = original_projector.matrix_world.to_3x3() @ Vector((1, 0, 0))
        right_vec.normalize()

        # Calculate the position for the new projector
        new_position = original_projector.matrix_world.translation + (right_vec * self.offset_distance)

        # Store the original projector's rotation
        original_rotation = original_projector.rotation_euler.copy()

        # Create a new projector
        # Temporarily deselect all objects to make the add_projector operator work properly
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.projection.add_projector()

        # Get the newly created projector (should be the active object)
        new_projector = context.active_object

        # Position and rotate the new projector
        new_projector.location = new_position
        new_projector.rotation_euler = original_rotation

        # Apply the original projector's settings
        new_projector.pj_throw_distance = orig_throw_distance
        new_projector.pj_image_width = orig_image_width
        new_projector.pj_aspect_ratio_w = orig_aspect_ratio_w
        new_projector.pj_aspect_ratio_h = orig_aspect_ratio_h

        # Add it to the same collection as the original
        if original_projector.pj_collection:
            new_projector.pj_collection = original_projector.pj_collection

        # Set a new name based on the original
        new_projector.name = original_projector.name + "_duplicate"

        # Report success
        self.report({'INFO'}, f"Created duplicate projector at {self.offset_distance}m offset")

        return {'FINISHED'}

class PJ_OT_create_projector_collection(Operator):
    """Create a new projector collection and add selected projectors to it"""
    bl_idname = "projection.create_projector_collection"
    bl_label = "Create Projector Collection"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: bpy.props.StringProperty(
        name="Collection Name",
        description="Name for the new projector collection",
        default="Projector Group"
    )

    def execute(self, context):
        scene = context.scene

        # Check if the collection name already exists
        if hasattr(scene, 'pj_projector_collections'):
            for coll in scene.pj_projector_collections:
                if coll.name == self.collection_name:
                    self.report({'WARNING'}, f"Collection '{self.collection_name}' already exists")
                    return {'CANCELLED'}

        # Add the new collection
        new_collection = scene.pj_projector_collections.add()
        new_collection.name = self.collection_name

        # Get the new collection index
        new_collection_index = len(scene.pj_projector_collections) - 1

        # Set the active collection to the new one
        scene.pj_active_collection_index = new_collection_index

        # If there are selected projectors, add them to the collection
        added_count = 0
        for obj in context.selected_objects:
            if obj.pj_is_projector:
                obj.pj_collection = self.collection_name
                added_count += 1

        if added_count > 0:
            self.report({'INFO'}, f"Created collection '{self.collection_name}' with {added_count} projectors")
        else:
            self.report({'INFO'}, f"Created empty collection '{self.collection_name}'")

        return {'FINISHED'}

class PJ_OT_add_to_collection(Operator):
    """Add selected projectors to the active collection"""
    bl_idname = "projection.add_to_collection"
    bl_label = "Add to Collection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Check if there's at least one projector collection and selected projectors
        return (hasattr(context.scene, 'pj_projector_collections') and
                len(context.scene.pj_projector_collections) > 0)

    def execute(self, context):
        scene = context.scene

        # Get the active collection name
        if not hasattr(scene, 'pj_active_collection_index'):
            self.report({'ERROR'}, "No active projector collection")
            return {'CANCELLED'}

        if scene.pj_active_collection_index >= len(scene.pj_projector_collections):
            self.report({'ERROR'}, "Invalid collection index")
            return {'CANCELLED'}

        collection_name = scene.pj_projector_collections[scene.pj_active_collection_index].name

        # Add selected projectors to the collection
        added_count = 0
        for obj in context.selected_objects:
            if obj.pj_is_projector:
                obj.pj_collection = collection_name
                added_count += 1

        if added_count > 0:
            self.report({'INFO'}, f"Added {added_count} projectors to collection '{collection_name}'")
        else:
            self.report({'WARNING'}, "No projectors selected to add to collection")

        return {'FINISHED'}

class PJ_OT_remove_from_collection(Operator):
    """Remove selected projectors from their collection"""
    bl_idname = "projection.remove_from_collection"
    bl_label = "Remove from Collection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Remove selected projectors from their collections
        removed_count = 0
        for obj in context.selected_objects:
            if obj.pj_is_projector and obj.pj_collection:
                obj.pj_collection = ""
                removed_count += 1

        if removed_count > 0:
            self.report({'INFO'}, f"Removed {removed_count} projectors from collections")
        else:
            self.report({'WARNING'}, "No projectors selected that belong to collections")

        return {'FINISHED'}

class PJ_OT_delete_collection(Operator):
    """Delete the active projector collection"""
    bl_idname = "projection.delete_collection"
    bl_label = "Delete Collection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Check if there's at least one projector collection
        return (hasattr(context.scene, 'pj_projector_collections') and
                len(context.scene.pj_projector_collections) > 0)

    def execute(self, context):
        scene = context.scene

        # Get the active collection name
        if not hasattr(scene, 'pj_active_collection_index'):
            self.report({'ERROR'}, "No active projector collection")
            return {'CANCELLED'}

        if scene.pj_active_collection_index >= len(scene.pj_projector_collections):
            self.report({'ERROR'}, "Invalid collection index")
            return {'CANCELLED'}

        collection_name = scene.pj_projector_collections[scene.pj_active_collection_index].name

        # Remove the collection assignment from any projectors in the collection
        removed_count = 0
        for obj in bpy.data.objects:
            if obj.pj_is_projector and obj.pj_collection == collection_name:
                obj.pj_collection = ""
                removed_count += 1

        # Remove the collection from the list
        scene.pj_projector_collections.remove(scene.pj_active_collection_index)

        # Update the active collection index if needed
        if scene.pj_active_collection_index >= len(scene.pj_projector_collections):
            scene.pj_active_collection_index = max(0, len(scene.pj_projector_collections) - 1)

        self.report({'INFO'}, f"Deleted collection '{collection_name}' and removed assignments from {removed_count} projectors")

        return {'FINISHED'}

class PJ_OT_detect_overlapping_projections(Operator):
    """Detect overlapping projection areas between projectors"""
    bl_idname = "projection.detect_overlapping"
    bl_label = "Detect Overlapping Projections"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        projectors = [obj for obj in bpy.data.objects if obj.pj_is_projector]

        if len(projectors) < 2:
            self.report({'WARNING'}, "Need at least two projectors to detect overlapping areas")
            return {'CANCELLED'}

        # Simple implementation: just check if projection distances are similar and projectors are close
        # A more accurate implementation would involve actual geometry calculations
        overlaps_found = 0
        for i, proj1 in enumerate(projectors):
            for proj2 in projectors[i+1:]:
                # Check if they're in the same collection
                same_collection = (proj1.pj_collection != "" and
                                  proj1.pj_collection == proj2.pj_collection)

                # Calculate distance between projectors
                distance = (proj1.matrix_world.translation - proj2.matrix_world.translation).length

                # Check if projection distances are within 20% of each other
                dist_ratio = abs(proj1.pj_throw_distance - proj2.pj_throw_distance) / max(proj1.pj_throw_distance, proj2.pj_throw_distance)
                similar_throw = dist_ratio < 0.2

                # Check projector distance against their throw distances
                projection_distance = min(proj1.pj_throw_distance, proj2.pj_throw_distance)
                close_enough = distance < projection_distance * 0.5

                if same_collection and similar_throw and close_enough:
                    # Mark these projectors as potentially overlapping
                    proj1.pj_overlaps_with = proj2.name
                    proj2.pj_overlaps_with = proj1.name
                    overlaps_found += 1

        if overlaps_found > 0:
            self.report({'INFO'}, f"Detected {overlaps_found} potential overlapping projection areas")
        else:
            self.report({'INFO'}, "No overlapping projection areas detected")

        return {'FINISHED'}

class PJ_OT_align_projector_group(Operator):
    """Align all projectors in the collection to form a horizontal array"""
    bl_idname = "projection.align_group"
    bl_label = "Align Projector Group"
    bl_options = {'REGISTER', 'UNDO'}

    spacing: bpy.props.FloatProperty(
        name="Spacing",
        description="Distance between projectors in the array",
        default=1.0,
        min=0.1,
        unit='LENGTH'
    )

    @classmethod
    def poll(cls, context):
        # Check if there's an active collection with projectors
        return (hasattr(context.scene, 'pj_projector_collections') and
                len(context.scene.pj_projector_collections) > 0)

    def execute(self, context):
        scene = context.scene

        # Get the active collection name
        if not hasattr(scene, 'pj_active_collection_index'):
            self.report({'ERROR'}, "No active projector collection")
            return {'CANCELLED'}

        if scene.pj_active_collection_index >= len(scene.pj_projector_collections):
            self.report({'ERROR'}, "Invalid collection index")
            return {'CANCELLED'}

        collection_name = scene.pj_projector_collections[scene.pj_active_collection_index].name

        # Get all projectors in the collection
        projectors = [obj for obj in bpy.data.objects
                     if obj.pj_is_projector and obj.pj_collection == collection_name]

        if not projectors:
            self.report({'WARNING'}, f"No projectors found in collection '{collection_name}'")
            return {'CANCELLED'}

        # Sort projectors by their x position
        projectors.sort(key=lambda obj: obj.location.x)

        # Calculate the starting position (from the leftmost projector)
        start_position = projectors[0].location.copy()
        start_rotation = projectors[0].rotation_euler.copy()

        # Align all projectors in a row
        for i, proj in enumerate(projectors):
            new_position = start_position.copy()
            new_position.x += i * self.spacing

            # Set the position and rotation
            proj.location = new_position
            proj.rotation_euler = start_rotation

        self.report({'INFO'}, f"Aligned {len(projectors)} projectors in collection '{collection_name}'")

        return {'FINISHED'}

def register():
    bpy.utils.register_class(PJ_OT_add_projector)
    bpy.utils.register_class(PJ_OT_test_parameter_linking)
    bpy.utils.register_class(PJ_OT_import_model)
    bpy.utils.register_class(PJ_OT_align_to_projector)
    bpy.utils.register_class(PJ_OT_position_at_projection_distance)
    bpy.utils.register_class(PJ_OT_create_basic_environment)
    bpy.utils.register_class(PJ_OT_duplicate_projector)
    bpy.utils.register_class(PJ_OT_create_projector_collection)
    bpy.utils.register_class(PJ_OT_add_to_collection)
    bpy.utils.register_class(PJ_OT_remove_from_collection)
    bpy.utils.register_class(PJ_OT_delete_collection)
    bpy.utils.register_class(PJ_OT_detect_overlapping_projections)
    bpy.utils.register_class(PJ_OT_align_projector_group)

def unregister():
    bpy.utils.unregister_class(PJ_OT_align_projector_group)
    bpy.utils.unregister_class(PJ_OT_detect_overlapping_projections)
    bpy.utils.unregister_class(PJ_OT_delete_collection)
    bpy.utils.unregister_class(PJ_OT_remove_from_collection)
    bpy.utils.unregister_class(PJ_OT_add_to_collection)
    bpy.utils.unregister_class(PJ_OT_create_projector_collection)
    bpy.utils.unregister_class(PJ_OT_duplicate_projector)
    bpy.utils.unregister_class(PJ_OT_create_basic_environment)
    bpy.utils.unregister_class(PJ_OT_position_at_projection_distance)
    bpy.utils.unregister_class(PJ_OT_align_to_projector)
    bpy.utils.unregister_class(PJ_OT_import_model)
    bpy.utils.unregister_class(PJ_OT_add_projector)
    bpy.utils.unregister_class(PJ_OT_test_parameter_linking)

if __name__ == "__main__":
    register()