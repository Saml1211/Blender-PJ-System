import bpy
from bpy.types import Operator
import math

def setup_projection_cone_nodes(obj):
    """
    Setup Geometry Nodes for projection cone visualization.

    Args:
        obj: The projector object to attach the visualization to
    """
    # Check if object has a Geometry Nodes modifier already
    if "ProjectionCone" in obj.modifiers:
        return

    # Create a new node group for projection cone if it doesn't exist
    node_group_name = "ProjectionConeNodeGroup"
    if node_group_name not in bpy.data.node_groups:
        create_projection_cone_node_group(node_group_name)

    # Add the Geometry Nodes modifier to the object
    try:
        # In Blender 4.x, the type is 'GEOMETRY_NODES' not 'NODES'
        modifier = obj.modifiers.new(name="ProjectionCone", type='GEOMETRY_NODES')
        if modifier is None:
            # Try the older type name as fallback
            modifier = obj.modifiers.new(name="ProjectionCone", type='NODES')

        if modifier is None:
            print("Error: Could not create Geometry Nodes modifier")
            return

        modifier.node_group = bpy.data.node_groups[node_group_name]
    except Exception as e:
        print(f"Error setting up projection cone: {e}")

    # Setup drivers from custom properties to node group inputs
    setup_cone_drivers(obj, modifier)

def create_projection_cone_node_group(node_group_name):
    """
    Create the node group for projection cone visualization.

    Args:
        node_group_name: Name for the new node group
    """
    # Create a new node group
    node_group = bpy.data.node_groups.new(name=node_group_name, type='GeometryNodeTree')

    # Create group input/output nodes
    group_in = node_group.nodes.new('NodeGroupInput')
    group_in.location = (-500, 0)
    group_out = node_group.nodes.new('NodeGroupOutput')
    group_out.location = (500, 0)

    # Add inputs for the cone parameters using the interface
    try:
        # For Blender 4.x
        throw_distance = node_group.interface.new_socket(name='Throw Distance', in_out='INPUT', socket_type='NodeSocketFloat')
        throw_distance.default_value = 4.0

        image_width = node_group.interface.new_socket(name='Image Width', in_out='INPUT', socket_type='NodeSocketFloat')
        image_width.default_value = 2.0

        aspect_ratio = node_group.interface.new_socket(name='Aspect Ratio', in_out='INPUT', socket_type='NodeSocketFloat')
        aspect_ratio.default_value = 16.0 / 9.0

        visible = node_group.interface.new_socket(name='Visible', in_out='INPUT', socket_type='NodeSocketBool')
        visible.default_value = True

        # Add output for the resulting geometry
        node_group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    except Exception as e:
        print(f"Error setting up node group interface: {e}")
        # Fallback for older Blender versions
        try:
            node_group.inputs.new('NodeSocketFloat', 'Throw Distance')
            node_group.inputs.new('NodeSocketFloat', 'Image Width')
            node_group.inputs.new('NodeSocketFloat', 'Aspect Ratio')
            node_group.inputs.new('NodeSocketBool', 'Visible')

            # Set default values
            node_group.inputs['Throw Distance'].default_value = 4.0
            node_group.inputs['Image Width'].default_value = 2.0
            node_group.inputs['Aspect Ratio'].default_value = 16.0 / 9.0
            node_group.inputs['Visible'].default_value = True

            # Add output for the resulting geometry
            node_group.outputs.new('NodeSocketGeometry', 'Geometry')
        except Exception as e:
            print(f"Error setting up node group inputs/outputs: {e}")

    # Add geometry nodes to create a cone shape
    mesh_line = node_group.nodes.new('GeometryNodeMeshLine')
    mesh_line.mode = 'END_POINTS'
    mesh_line.count_mode = 'TOTAL'
    mesh_line.count = 4  # We need 4 points for a rectangular base
    mesh_line.location = (-300, 0)

    # Position node - will be used to place the points in a rectangle
    position = node_group.nodes.new('GeometryNodeInputPosition')
    position.location = (-400, -100)

    # Set position node - to position the points in a rectangle
    set_position = node_group.nodes.new('GeometryNodeSetPosition')
    set_position.location = (-150, 0)

    # Math nodes to calculate rectangle corners
    combine_xyz1 = node_group.nodes.new('ShaderNodeCombineXYZ')
    combine_xyz1.location = (-300, -200)

    combine_xyz2 = node_group.nodes.new('ShaderNodeCombineXYZ')
    combine_xyz2.location = (-300, -300)

    combine_xyz3 = node_group.nodes.new('ShaderNodeCombineXYZ')
    combine_xyz3.location = (-300, -400)

    combine_xyz4 = node_group.nodes.new('ShaderNodeCombineXYZ')
    combine_xyz4.location = (-300, -500)

    # Math nodes for calculations
    divide_aspect = node_group.nodes.new('ShaderNodeMath')
    divide_aspect.operation = 'DIVIDE'
    divide_aspect.location = (-450, -250)

    multiply_half_width = node_group.nodes.new('ShaderNodeMath')
    multiply_half_width.operation = 'MULTIPLY'
    multiply_half_width.inputs[1].default_value = 0.5
    multiply_half_width.location = (-450, -350)

    multiply_half_height = node_group.nodes.new('ShaderNodeMath')
    multiply_half_height.operation = 'MULTIPLY'
    multiply_half_height.inputs[1].default_value = 0.5
    multiply_half_height.location = (-450, -450)

    # Join geometry node to create triangle faces
    join_geometry = node_group.nodes.new('GeometryNodeMeshFillGrid')
    join_geometry.location = (0, 0)

    # Mesh to points node
    mesh_to_points = node_group.nodes.new('GeometryNodeMeshToPoints')
    mesh_to_points.location = (-50, -200)

    # Extrude mesh node to create the cone
    extrude = node_group.nodes.new('GeometryNodeExtrudeMesh')
    extrude.mode = 'VERTICES'
    extrude.location = (150, 0)

    # Vector for extrusion
    combine_xyz_extrude = node_group.nodes.new('ShaderNodeCombineXYZ')
    combine_xyz_extrude.location = (0, -100)
    combine_xyz_extrude.inputs[1].default_value = -1.0  # Extrude along Y axis (projector forward)

    # Set material node
    set_material = node_group.nodes.new('GeometryNodeSetMaterial')
    set_material.location = (300, 0)

    # Create a simple material for the cone
    if "ProjectionConeMaterial" not in bpy.data.materials:
        create_cone_material()

    set_material.inputs[2].default_value = bpy.data.materials["ProjectionConeMaterial"]

    # Switch node to enable/disable the visualization
    switch = node_group.nodes.new('GeometryNodeSwitch')
    switch.input_type = 'GEOMETRY'
    switch.location = (400, 100)

    # Connect nodes

    # Input connections
    node_group.links.new(multiply_half_width.inputs[0], group_in.outputs['Image Width'])
    node_group.links.new(divide_aspect.inputs[0], group_in.outputs['Image Width'])
    node_group.links.new(divide_aspect.inputs[1], group_in.outputs['Aspect Ratio'])
    node_group.links.new(multiply_half_height.inputs[0], divide_aspect.outputs[0])
    node_group.links.new(combine_xyz_extrude.inputs[0], group_in.outputs['Throw Distance'])
    node_group.links.new(switch.inputs[1], group_in.outputs['Visible'])

    # Rectangle corner positions
    node_group.links.new(combine_xyz1.inputs[0], multiply_half_width.outputs[0])   # +half_width
    node_group.links.new(combine_xyz1.inputs[2], multiply_half_height.outputs[0])  # +half_height

    node_group.links.new(combine_xyz2.inputs[0], multiply_half_width.outputs[0])   # +half_width
    node_group.links.new(combine_xyz2.inputs[2], multiply_half_height.outputs[0])  # -half_height
    node_group.links.new(combine_xyz2.inputs[2].default_value, -multiply_half_height.outputs[0].default_value)

    node_group.links.new(combine_xyz3.inputs[0], multiply_half_width.outputs[0])   # -half_width
    node_group.links.new(combine_xyz3.inputs[2], multiply_half_height.outputs[0])  # -half_height
    node_group.links.new(combine_xyz3.inputs[0].default_value, -multiply_half_width.outputs[0].default_value)
    node_group.links.new(combine_xyz3.inputs[2].default_value, -multiply_half_height.outputs[0].default_value)

    node_group.links.new(combine_xyz4.inputs[0], multiply_half_width.outputs[0])   # -half_width
    node_group.links.new(combine_xyz4.inputs[2], multiply_half_height.outputs[0])  # +half_height
    node_group.links.new(combine_xyz4.inputs[0].default_value, -multiply_half_width.outputs[0].default_value)

    # Position setting
    node_group.links.new(set_position.inputs[0], mesh_line.outputs[0])
    node_group.links.new(mesh_to_points.inputs[0], set_position.outputs[0])

    # Extrusion
    node_group.links.new(extrude.inputs[0], join_geometry.outputs[0])
    node_group.links.new(extrude.inputs[2], combine_xyz_extrude.outputs[0])

    # Material
    node_group.links.new(set_material.inputs[0], extrude.outputs[0])

    # Switch for visibility
    node_group.links.new(switch.inputs[0], set_material.outputs[0])

    # Output
    node_group.links.new(group_out.inputs[0], switch.outputs[0])

    return node_group

def create_cone_material():
    """Create a semi-transparent material for the projection cone"""
    mat = bpy.data.materials.new(name="ProjectionConeMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default nodes
    for node in nodes:
        nodes.remove(node)

    # Create nodes
    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (400, 0)

    principled = nodes.new(type='ShaderNodeBsdfPrincipled')
    principled.location = (0, 0)
    principled.inputs['Base Color'].default_value = (0.0, 0.8, 1.0, 1.0)  # Light blue
    principled.inputs['Alpha'].default_value = 0.3  # Mostly transparent
    principled.inputs['Specular'].default_value = 0.0  # No specular
    principled.inputs['Roughness'].default_value = 1.0  # No reflections

    # Connect nodes
    links.new(principled.outputs['BSDF'], output.inputs['Surface'])

    # Set material properties
    mat.blend_method = 'BLEND'  # Enable transparency
    mat.shadow_method = 'NONE'  # Don't cast shadows

    return mat

def setup_cone_drivers(obj, modifier):
    """
    Setup drivers to link projector properties to geometry nodes inputs

    Args:
        obj: The projector object
        modifier: The Geometry Nodes modifier
    """
    # Check if modifier is valid
    if modifier is None:
        print("Error: Cannot setup drivers - modifier is None")
        return

    try:
        # For Blender 4.x, the path is different
        # Try to find the correct path for the inputs
        try:
            # First try the Blender 4.x path
            throw_distance_path = 'nodes["Group Inputs"].inputs[1].default_value'
            # Just to test if the path is valid
            _ = eval(f"modifier.{throw_distance_path}")
        except Exception:
            try:
                # Try alternative path for Blender 4.x
                throw_distance_path = 'nodes["Group Inputs"].inputs["Throw Distance"].default_value'
                # Just to test if the path is valid
                _ = eval(f"modifier.{throw_distance_path}")
            except Exception:
                # Fallback to a more generic approach
                print("Using fallback driver path for Throw Distance")
                throw_distance_path = 'node_group.interface.items_tree[1].default_value'

        # Driver for throw distance
        throw_distance_driver = modifier.driver_add(throw_distance_path).driver
        throw_distance_driver.type = 'SCRIPTED'
        throw_distance_driver.expression = "var"
        var = throw_distance_driver.variables.new()
        var.name = "var"
        var.type = 'SINGLE_PROP'
        var.targets[0].id = obj
        var.targets[0].data_path = "pj_throw_distance"
    except Exception as e:
        print(f"Error setting up throw distance driver: {e}")

    try:
        # For Blender 4.x, the path is different
        # Try to find the correct path for the inputs
        try:
            # First try the Blender 4.x path
            image_width_path = 'nodes["Group Inputs"].inputs[2].default_value'
            # Just to test if the path is valid
            _ = eval(f"modifier.{image_width_path}")
        except Exception:
            try:
                # Try alternative path for Blender 4.x
                image_width_path = 'nodes["Group Inputs"].inputs["Image Width"].default_value'
                # Just to test if the path is valid
                _ = eval(f"modifier.{image_width_path}")
            except Exception:
                # Fallback to a more generic approach
                print("Using fallback driver path for Image Width")
                image_width_path = 'node_group.interface.items_tree[2].default_value'

        # Driver for image width
        image_width_driver = modifier.driver_add(image_width_path).driver
        image_width_driver.type = 'SCRIPTED'
        image_width_driver.expression = "var"
        var = image_width_driver.variables.new()
        var.name = "var"
        var.type = 'SINGLE_PROP'
        var.targets[0].id = obj
        var.targets[0].data_path = "pj_image_width"
    except Exception as e:
        print(f"Error setting up image width driver: {e}")

    try:
        # For Blender 4.x, the path is different
        # Try to find the correct path for the inputs
        try:
            # First try the Blender 4.x path
            aspect_ratio_path = 'nodes["Group Inputs"].inputs[3].default_value'
            # Just to test if the path is valid
            _ = eval(f"modifier.{aspect_ratio_path}")
        except Exception:
            try:
                # Try alternative path for Blender 4.x
                aspect_ratio_path = 'nodes["Group Inputs"].inputs["Aspect Ratio"].default_value'
                # Just to test if the path is valid
                _ = eval(f"modifier.{aspect_ratio_path}")
            except Exception:
                # Fallback to a more generic approach
                print("Using fallback driver path for Aspect Ratio")
                aspect_ratio_path = 'node_group.interface.items_tree[3].default_value'

        # Driver for aspect ratio
        aspect_ratio_driver = modifier.driver_add(aspect_ratio_path).driver
        aspect_ratio_driver.type = 'SCRIPTED'
        aspect_ratio_driver.expression = "width/height"

        var_width = aspect_ratio_driver.variables.new()
        var_width.name = "width"
        var_width.type = 'SINGLE_PROP'
        var_width.targets[0].id = obj
        var_width.targets[0].data_path = "pj_aspect_ratio_w"

        var_height = aspect_ratio_driver.variables.new()
        var_height.name = "height"
        var_height.type = 'SINGLE_PROP'
        var_height.targets[0].id = obj
        var_height.targets[0].data_path = "pj_aspect_ratio_h"
    except Exception as e:
        print(f"Error setting up aspect ratio driver: {e}")

    try:
        # For Blender 4.x, the path is different
        # Try to find the correct path for the inputs
        try:
            # First try the Blender 4.x path
            visibility_path = 'nodes["Group Inputs"].inputs[4].default_value'
            # Just to test if the path is valid
            _ = eval(f"modifier.{visibility_path}")
        except Exception:
            try:
                # Try alternative path for Blender 4.x
                visibility_path = 'nodes["Group Inputs"].inputs["Visible"].default_value'
                # Just to test if the path is valid
                _ = eval(f"modifier.{visibility_path}")
            except Exception:
                # Fallback to a more generic approach
                print("Using fallback driver path for Visibility")
                visibility_path = 'node_group.interface.items_tree[4].default_value'

        # Driver for visibility
        visibility_driver = modifier.driver_add(visibility_path).driver
        visibility_driver.type = 'SCRIPTED'
        visibility_driver.expression = "var"
        var = visibility_driver.variables.new()
        var.name = "var"
        var.type = 'SINGLE_PROP'
        var.targets[0].id = obj
        var.targets[0].data_path = "pj_show_cone"
    except Exception as e:
        print(f"Error setting up visibility driver: {e}")

class PJ_OT_add_projection_cone(Operator):
    """Add projection cone visualization to the selected projector"""
    bl_idname = "projection.add_projection_cone"
    bl_label = "Add Projection Cone"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object

        if not (obj and obj.pj_is_projector):
            self.report({'ERROR'}, "No projector selected")
            return {'CANCELLED'}

        # Setup the projection cone visualization
        setup_projection_cone_nodes(obj)

        # Report success
        self.report({'INFO'}, "Projection cone added to projector")
        return {'FINISHED'}

class PJ_OT_create_test_surface(Operator):
    """Create a test surface at the projection distance"""
    bl_idname = "projection.create_test_surface"
    bl_label = "Create Test Surface"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object

        if not (obj and obj.pj_is_projector):
            self.report({'ERROR'}, "No projector selected")
            return {'CANCELLED'}

        # Get projection parameters
        throw_distance = obj.pj_throw_distance
        image_width = obj.pj_image_width
        aspect_ratio = obj.pj_aspect_ratio_w / obj.pj_aspect_ratio_h
        image_height = image_width / aspect_ratio

        # Create a plane at the projection distance
        bpy.ops.mesh.primitive_plane_add(size=1.0)
        surface = context.active_object
        surface.name = f"Projection_Surface_{obj.name}"

        # Position the plane at the projection distance
        surface.location = (0, -throw_distance, 0)  # Assuming projector points along -Y axis

        # Scale the plane to match the projection size
        surface.scale = (image_width/2, 1.0, image_height/2)

        # Parent the surface to the projector for easier manipulation
        surface.parent = obj

        # Create a material for the surface
        if "ProjectionSurfaceMaterial" not in bpy.data.materials:
            create_surface_material()

        # Apply the material
        if len(surface.data.materials) == 0:
            surface.data.materials.append(bpy.data.materials["ProjectionSurfaceMaterial"])
        else:
            surface.data.materials[0] = bpy.data.materials["ProjectionSurfaceMaterial"]

        # Report success
        self.report({'INFO'}, "Test surface created at projection distance")
        return {'FINISHED'}

def create_surface_material():
    """Create a material for the projection surface"""
    mat = bpy.data.materials.new(name="ProjectionSurfaceMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default nodes
    for node in nodes:
        nodes.remove(node)

    # Create nodes
    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (400, 0)

    principled = nodes.new(type='ShaderNodeBsdfPrincipled')
    principled.location = (0, 0)
    principled.inputs['Base Color'].default_value = (0.9, 0.9, 0.9, 1.0)  # Light gray
    principled.inputs['Specular'].default_value = 0.1  # Low specular
    principled.inputs['Roughness'].default_value = 0.8  # Mostly rough

    # Add a grid texture for better visualization
    checker = nodes.new(type='ShaderNodeTexChecker')
    checker.location = (-300, 0)
    checker.inputs['Scale'].default_value = 5.0
    checker.inputs['Color1'].default_value = (0.9, 0.9, 0.9, 1.0)  # Light gray
    checker.inputs['Color2'].default_value = (0.7, 0.7, 0.7, 1.0)  # Darker gray

    # Connect nodes
    links.new(checker.outputs['Color'], principled.inputs['Base Color'])
    links.new(principled.outputs['BSDF'], output.inputs['Surface'])

    return mat

class PJ_OT_setup_projection_mapping(Operator):
    """Setup projection mapping on selected objects"""
    bl_idname = "projection.setup_projection_mapping"
    bl_label = "Setup Projection Mapping"
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

        # Find the projector's camera
        projector_camera = None
        for child in projector.children:
            if child.type == 'CAMERA':
                projector_camera = child
                break

        if not projector_camera:
            self.report({'ERROR'}, "Projector camera not found")
            return {'CANCELLED'}

        # Create a default projection image if it doesn't exist
        if "projection_test_grid" not in bpy.data.images:
            create_projection_test_grid()

        # Create a projection material if it doesn't exist
        if "ProjectionMaterial" not in bpy.data.materials:
            create_projection_material()

        # Set up projection on selected objects
        mapped_count = 0
        for obj in context.selected_objects:
            if obj != projector and obj.type == 'MESH':
                # Add the projection material to the object
                if len(obj.material_slots) == 0:
                    obj.data.materials.append(bpy.data.materials["ProjectionMaterial"])
                else:
                    obj.material_slots[0].material = bpy.data.materials["ProjectionMaterial"]

                # Set up the projector as the texture coordinate source
                set_projector_as_mapping_source(obj, projector_camera)

                mapped_count += 1

        self.report({'INFO'}, f"Set up projection mapping on {mapped_count} objects")

        return {'FINISHED'}

def create_projection_test_grid():
    """Create a test grid image for projection"""
    size = 1024
    image = bpy.data.images.new("projection_test_grid", width=size, height=size)

    # Create a test grid pattern
    pixels = [None] * size * size * 4

    for y in range(size):
        for x in range(size):
            # Create a grid pattern
            grid_lines = ((x % 128 < 2) or (y % 128 < 2))

            # Colored corners for orientation
            red_corner = (x < 100 and y < 100)
            green_corner = (x > size - 100 and y < 100)
            blue_corner = (x < 100 and y > size - 100)
            yellow_corner = (x > size - 100 and y > size - 100)

            i = (y * size + x) * 4

            if red_corner:
                pixels[i] = 1.0
                pixels[i+1] = 0.0
                pixels[i+2] = 0.0
                pixels[i+3] = 1.0
            elif green_corner:
                pixels[i] = 0.0
                pixels[i+1] = 1.0
                pixels[i+2] = 0.0
                pixels[i+3] = 1.0
            elif blue_corner:
                pixels[i] = 0.0
                pixels[i+1] = 0.0
                pixels[i+2] = 1.0
                pixels[i+3] = 1.0
            elif yellow_corner:
                pixels[i] = 1.0
                pixels[i+1] = 1.0
                pixels[i+2] = 0.0
                pixels[i+3] = 1.0
            elif grid_lines:
                pixels[i] = 1.0
                pixels[i+1] = 1.0
                pixels[i+2] = 1.0
                pixels[i+3] = 1.0
            else:
                pixels[i] = 0.1
                pixels[i+1] = 0.1
                pixels[i+2] = 0.1
                pixels[i+3] = 1.0

    # Flatten the list
    pixels = [chan for px in pixels for chan in (px if px else (0, 0, 0, 1))]

    # Apply pixels to the image
    image.pixels = pixels
    image.update()

    return image

def create_projection_material():
    """Create a material for projection mapping"""
    mat = bpy.data.materials.new(name="ProjectionMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default nodes
    for node in nodes:
        nodes.remove(node)

    # Create nodes
    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (400, 0)

    principled = nodes.new(type='ShaderNodeBsdfPrincipled')
    principled.location = (200, 0)

    texture = nodes.new(type='ShaderNodeTexImage')
    texture.location = (0, 0)
    texture.image = bpy.data.images["projection_test_grid"]
    texture.projection = 'FLAT'

    texcoord = nodes.new(type='ShaderNodeTexCoord')
    texcoord.location = (-200, 0)

    # Connect nodes
    links.new(principled.outputs[0], output.inputs[0])
    links.new(texture.outputs[0], principled.inputs['Base Color'])
    links.new(texcoord.outputs['Camera'], texture.inputs['Vector'])

    return mat

def set_projector_as_mapping_source(obj, camera):
    """Set the projector's camera as the texture coordinate source"""
    # Ensure object has the projection material
    mat = bpy.data.materials["ProjectionMaterial"]

    # Get the texcoord node
    texcoord = None
    for node in mat.node_tree.nodes:
        if node.type == 'TEX_COORD':
            texcoord = node
            break

    if texcoord:
        # Set the object and camera references
        texcoord.object = camera

        # Ensure the camera is enabled for texture projection
        camera.data.type = 'PERSP'

def register():
    bpy.utils.register_class(PJ_OT_add_projection_cone)
    bpy.utils.register_class(PJ_OT_create_test_surface)
    bpy.utils.register_class(PJ_OT_setup_projection_mapping)

def unregister():
    bpy.utils.unregister_class(PJ_OT_setup_projection_mapping)
    bpy.utils.unregister_class(PJ_OT_create_test_surface)
    bpy.utils.unregister_class(PJ_OT_add_projection_cone)

if __name__ == "__main__":
    register()