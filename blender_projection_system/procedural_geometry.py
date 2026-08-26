"""Owned Geometry Nodes adapters for generated projection-wall geometry.

The node graph is deliberately a display adapter. Projection mathematics stays
in :mod:`blender_projection_system.core`; generated-wall properties drive the
node modifier so Blender's dependency graph keeps the visible surface current.
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Iterable

import bpy

from .core.errors import ProjectionError
from .scene_ids import NODE_ROLE_KEY, OWNER_ID, OWNER_KEY, SCHEMA_VERSION_KEY

NODE_GROUP_NAME = ".PJ Wall Geometry"
MODIFIER_NAME = "Projection Wall Geometry"
NODE_ROLE = "generated_wall_geometry"
SCHEMA_VERSION = 1

_SOCKET_PROPERTY_PREFIX = "pj_socket_"
_SOCKET_SPECS = {
    "is_flat": ("Is Flat", "NodeSocketBool", False),
    "width": ("Width", "NodeSocketFloat", 4.0),
    "yaw_deg": ("Facing Yaw", "NodeSocketFloat", 0.0),
    "radius": ("Radius", "NodeSocketFloat", 8.0),
    "height": ("Height", "NodeSocketFloat", 3.0),
    "arc_start_deg": ("Arc Start", "NodeSocketFloat", -45.0),
    "arc_end_deg": ("Arc End", "NodeSocketFloat", 45.0),
    "segments": ("Segments", "NodeSocketInt", 48),
    "concave": ("Concave", "NodeSocketBool", True),
}


def _preferred_name(base: str, existing: Iterable[str]) -> str:
    names = set(existing)
    return base if base not in names else f"{base} (Projection Planner)"


def _new_input(
    tree: bpy.types.NodeTree,
    key: str,
    *,
    minimum: float | int | None = None,
    maximum: float | int | None = None,
):
    name, socket_type, default = _SOCKET_SPECS[key]
    socket = tree.interface.new_socket(
        name=name,
        description="Driven by Projection Planner; edit in the Projection sidebar",
        in_out="INPUT",
        socket_type=socket_type,
    )
    socket.default_value = default
    socket.hide_in_modifier = True
    if hasattr(socket, "force_non_field"):
        socket.force_non_field = True
    if minimum is not None:
        socket.min_value = minimum
    if maximum is not None:
        socket.max_value = maximum
    tree[_SOCKET_PROPERTY_PREFIX + key] = socket.identifier
    return socket


def _node_input(node, name: str):
    socket = node.inputs.get(name)
    if socket is None:
        raise ProjectionError(
            f"Blender {bpy.app.version_string} changed the '{node.bl_idname}' node interface; "
            f"expected an input named '{name}'. Update Projection Planner before creating walls."
        )
    return socket


def _node_output(node, name: str):
    socket = node.outputs.get(name)
    if socket is None:
        raise ProjectionError(
            f"Blender {bpy.app.version_string} changed the '{node.bl_idname}' node interface; "
            f"expected an output named '{name}'. Update Projection Planner before creating walls."
        )
    return socket


def _math(nodes, operation: str, name: str, *, constant: float | None = None):
    node = nodes.new("ShaderNodeMath")
    node.name = name
    node.label = name
    node.operation = operation
    if constant is not None:
        node.inputs[1].default_value = constant
    return node


def _combine_xyz(nodes, name: str):
    node = nodes.new("ShaderNodeCombineXYZ")
    node.name = name
    node.label = name
    return node


def _build_wall_node_group() -> bpy.types.NodeTree:
    name = _preferred_name(NODE_GROUP_NAME, bpy.data.node_groups.keys())
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    tree[OWNER_KEY] = OWNER_ID
    tree[NODE_ROLE_KEY] = NODE_ROLE
    tree[SCHEMA_VERSION_KEY] = SCHEMA_VERSION
    tree.use_fake_user = True

    output_geometry = tree.interface.new_socket(
        name="Geometry",
        description="Generated projection-wall surface",
        in_out="OUTPUT",
        socket_type="NodeSocketGeometry",
    )
    inputs = {
        "is_flat": _new_input(tree, "is_flat"),
        "width": _new_input(tree, "width", minimum=0.01),
        "yaw_deg": _new_input(tree, "yaw_deg", minimum=-360.0, maximum=360.0),
        "radius": _new_input(tree, "radius", minimum=0.01),
        "height": _new_input(tree, "height", minimum=0.01),
        "arc_start_deg": _new_input(
            tree, "arc_start_deg", minimum=-360.0, maximum=360.0
        ),
        "arc_end_deg": _new_input(
            tree, "arc_end_deg", minimum=-360.0, maximum=360.0
        ),
        "segments": _new_input(tree, "segments", minimum=2, maximum=512),
        "concave": _new_input(tree, "concave"),
    }

    nodes = tree.nodes
    links = tree.links
    group_in = nodes.new("NodeGroupInput")
    group_in.name = "Projection Wall Inputs"
    group_in.location = (-1100.0, 120.0)
    group_out = nodes.new("NodeGroupOutput")
    group_out.name = "Projection Wall Output"
    group_out.location = (900.0, 120.0)

    def source(key: str):
        return _node_output(group_in, inputs[key].identifier)

    # Shared vertical profile. On a horizontal path, profile -Y maps to world
    # +Z. The direction also gives the curved branch inward-facing normals.
    negative_height = _math(nodes, "MULTIPLY", "Negative Height", constant=-1.0)
    negative_height.location = (-900.0, -420.0)
    links.new(source("height"), negative_height.inputs[0])
    profile_end = _combine_xyz(nodes, "Profile End")
    profile_end.location = (-700.0, -420.0)
    links.new(negative_height.outputs[0], _node_input(profile_end, "Y"))
    profile = nodes.new("GeometryNodeCurvePrimitiveLine")
    profile.name = "Vertical Profile"
    profile.label = "Vertical Profile"
    profile.mode = "POINTS"
    profile.location = (-500.0, -420.0)
    _node_input(profile, "Start").default_value = (0.0, 0.0, 0.0)
    links.new(_node_output(profile_end, "Vector"), _node_input(profile, "End"))

    segment_points = _math(nodes, "ADD", "Segment Points", constant=1.0)
    segment_points.location = (-900.0, 360.0)
    links.new(source("segments"), segment_points.inputs[0])

    # Flat branch: a resampled horizontal line, swept vertically and then
    # rotated around Z by the configured facing yaw.
    flat_start_y = _math(nodes, "MULTIPLY", "Flat Start Y", constant=-0.5)
    flat_end_y = _math(nodes, "MULTIPLY", "Flat End Y", constant=0.5)
    flat_start_y.location = (-900.0, 40.0)
    flat_end_y.location = (-900.0, -100.0)
    links.new(source("width"), flat_start_y.inputs[0])
    links.new(source("width"), flat_end_y.inputs[0])
    flat_start = _combine_xyz(nodes, "Flat Start")
    flat_end = _combine_xyz(nodes, "Flat End")
    flat_start.location = (-700.0, 40.0)
    flat_end.location = (-700.0, -100.0)
    links.new(flat_start_y.outputs[0], _node_input(flat_start, "Y"))
    links.new(flat_end_y.outputs[0], _node_input(flat_end, "Y"))
    flat_path = nodes.new("GeometryNodeCurvePrimitiveLine")
    flat_path.name = "Flat Path"
    flat_path.label = "Flat Path"
    flat_path.mode = "POINTS"
    flat_path.location = (-500.0, 40.0)
    links.new(_node_output(flat_start, "Vector"), _node_input(flat_path, "Start"))
    links.new(_node_output(flat_end, "Vector"), _node_input(flat_path, "End"))
    flat_resample = nodes.new("GeometryNodeResampleCurve")
    flat_resample.name = "Flat Segments"
    flat_resample.label = "Flat Segments"
    flat_resample.mode = "COUNT"
    flat_resample.location = (-280.0, 40.0)
    links.new(_node_output(flat_path, "Curve"), _node_input(flat_resample, "Curve"))
    links.new(segment_points.outputs[0], _node_input(flat_resample, "Count"))
    flat_mesh = nodes.new("GeometryNodeCurveToMesh")
    flat_mesh.name = "Flat Wall"
    flat_mesh.label = "Flat Wall"
    flat_mesh.location = (-40.0, 40.0)
    links.new(_node_output(flat_resample, "Curve"), _node_input(flat_mesh, "Curve"))
    links.new(_node_output(profile, "Curve"), _node_input(flat_mesh, "Profile Curve"))

    degrees_to_radians = math.pi / 180.0
    yaw_radians = _math(
        nodes, "MULTIPLY", "Yaw Radians", constant=degrees_to_radians
    )
    yaw_radians.location = (-260.0, -180.0)
    links.new(source("yaw_deg"), yaw_radians.inputs[0])
    yaw_rotation = _combine_xyz(nodes, "Yaw Rotation")
    yaw_rotation.location = (-40.0, -180.0)
    links.new(yaw_radians.outputs[0], _node_input(yaw_rotation, "Z"))
    rotate_flat = nodes.new("GeometryNodeTransform")
    rotate_flat.name = "Rotate Flat Wall"
    rotate_flat.label = "Rotate Flat Wall"
    rotate_flat.location = (180.0, 40.0)
    links.new(_node_output(flat_mesh, "Mesh"), _node_input(rotate_flat, "Geometry"))
    links.new(_node_output(yaw_rotation, "Vector"), _node_input(rotate_flat, "Rotation"))

    # Curved branch: the core angles are degrees in RNA and radians in maths;
    # convert in nodes so the driver expressions remain simple property reads.
    start_radians = _math(
        nodes, "MULTIPLY", "Arc Start Radians", constant=degrees_to_radians
    )
    start_radians.location = (-900.0, 700.0)
    links.new(source("arc_start_deg"), start_radians.inputs[0])
    sweep_degrees = _math(nodes, "SUBTRACT", "Arc Sweep Degrees")
    sweep_degrees.location = (-900.0, 560.0)
    links.new(source("arc_end_deg"), sweep_degrees.inputs[0])
    links.new(source("arc_start_deg"), sweep_degrees.inputs[1])
    sweep_radians = _math(
        nodes, "MULTIPLY", "Arc Sweep Radians", constant=degrees_to_radians
    )
    sweep_radians.location = (-700.0, 560.0)
    links.new(sweep_degrees.outputs[0], sweep_radians.inputs[0])

    arc = nodes.new("GeometryNodeCurveArc")
    arc.name = "Curved Path"
    arc.label = "Curved Path"
    arc.mode = "RADIUS"
    arc.location = (-480.0, 620.0)
    links.new(segment_points.outputs[0], _node_input(arc, "Resolution"))
    links.new(source("radius"), _node_input(arc, "Radius"))
    links.new(start_radians.outputs[0], _node_input(arc, "Start Angle"))
    links.new(sweep_radians.outputs[0], _node_input(arc, "Sweep Angle"))

    curved_mesh = nodes.new("GeometryNodeCurveToMesh")
    curved_mesh.name = "Curved Wall"
    curved_mesh.label = "Curved Wall"
    curved_mesh.location = (-40.0, 620.0)
    links.new(_node_output(arc, "Curve"), _node_input(curved_mesh, "Curve"))
    links.new(_node_output(profile, "Curve"), _node_input(curved_mesh, "Profile Curve"))
    flipped_curved = nodes.new("GeometryNodeFlipFaces")
    flipped_curved.name = "Convex Curved Wall"
    flipped_curved.label = "Convex Curved Wall"
    flipped_curved.location = (180.0, 700.0)
    links.new(_node_output(curved_mesh, "Mesh"), _node_input(flipped_curved, "Mesh"))
    curved_facing = nodes.new("GeometryNodeSwitch")
    curved_facing.name = "Concave Facing"
    curved_facing.label = "Concave Facing"
    curved_facing.input_type = "GEOMETRY"
    curved_facing.location = (400.0, 580.0)
    links.new(source("concave"), _node_input(curved_facing, "Switch"))
    links.new(_node_output(flipped_curved, "Mesh"), _node_input(curved_facing, "False"))
    links.new(_node_output(curved_mesh, "Mesh"), _node_input(curved_facing, "True"))

    wall_kind = nodes.new("GeometryNodeSwitch")
    wall_kind.name = "Wall Kind"
    wall_kind.label = "Wall Kind"
    wall_kind.input_type = "GEOMETRY"
    wall_kind.location = (650.0, 160.0)
    links.new(source("is_flat"), _node_input(wall_kind, "Switch"))
    links.new(_node_output(curved_facing, "Output"), _node_input(wall_kind, "False"))
    links.new(_node_output(rotate_flat, "Geometry"), _node_input(wall_kind, "True"))
    links.new(_node_output(wall_kind, "Output"), group_out.inputs[output_geometry.identifier])
    return tree


def ensure_wall_node_group() -> bpy.types.NodeTree:
    """Return the current owned wall group, creating it when required."""
    group = next(
        (
            candidate
            for candidate in bpy.data.node_groups
            if candidate.bl_idname == "GeometryNodeTree"
            and candidate.get(OWNER_KEY) == OWNER_ID
            and candidate.get(NODE_ROLE_KEY) == NODE_ROLE
            and candidate.get(SCHEMA_VERSION_KEY) == SCHEMA_VERSION
        ),
        None,
    )
    return group if group is not None else _build_wall_node_group()


def _socket_identifier(tree: bpy.types.NodeTree, key: str) -> str:
    identifier = tree.get(_SOCKET_PROPERTY_PREFIX + key)
    if not isinstance(identifier, str) or not identifier:
        raise ProjectionError(
            f"Owned Geometry Nodes group '{tree.name}' is missing its '{key}' socket mapping"
        )
    return identifier


def _remove_driver(modifier: bpy.types.NodesModifier, identifier: str) -> None:
    path = f'["{identifier}"]'
    with contextlib.suppress(TypeError, RuntimeError):
        modifier.driver_remove(path)


def _bind_property_driver(
    modifier: bpy.types.NodesModifier,
    identifier: str,
    obj: bpy.types.Object,
    data_path: str,
) -> None:
    _remove_driver(modifier, identifier)
    fcurve = modifier.driver_add(f'["{identifier}"]')
    variable = fcurve.driver.variables.new()
    variable.name = "value"
    variable.type = "SINGLE_PROP"
    target = variable.targets[0]
    target.id_type = "OBJECT"
    target.id = obj
    target.data_path = data_path
    fcurve.driver.expression = variable.name


def ensure_wall_modifier(obj: bpy.types.Object) -> bpy.types.NodesModifier:
    """Attach and bind the owned procedural-wall modifier idempotently."""
    tree = ensure_wall_node_group()
    owned = [
        modifier
        for modifier in obj.modifiers
        if modifier.type == "NODES"
        and (
            (
                modifier.get(OWNER_KEY) == OWNER_ID
                and modifier.get(NODE_ROLE_KEY) == NODE_ROLE
            )
            or (
                modifier.node_group is not None
                and modifier.node_group.get(OWNER_KEY) == OWNER_ID
                and modifier.node_group.get(NODE_ROLE_KEY) == NODE_ROLE
            )
        )
    ]
    modifier = owned[0] if owned else None
    for duplicate in owned[1:]:
        obj.modifiers.remove(duplicate)
    if modifier is None:
        name = _preferred_name(MODIFIER_NAME, (candidate.name for candidate in obj.modifiers))
        modifier = obj.modifiers.new(name, "NODES")
    # Assigning a node group initializes its socket ID-properties and clears
    # unrelated modifier ID-properties, so ownership metadata must be written
    # afterwards.
    modifier.node_group = tree
    modifier[OWNER_KEY] = OWNER_ID
    modifier[NODE_ROLE_KEY] = NODE_ROLE
    modifier[SCHEMA_VERSION_KEY] = SCHEMA_VERSION

    props = obj.pj_wall
    for key, (_name, _socket_type, default) in _SOCKET_SPECS.items():
        identifier = _socket_identifier(tree, key)
        value = props.kind == "FLAT" if key == "is_flat" else getattr(props, key, default)
        modifier[identifier] = value
        if key == "is_flat":
            _remove_driver(modifier, identifier)
        else:
            _bind_property_driver(modifier, identifier, obj, f"pj_wall.{key}")
    obj.update_tag(refresh={"OBJECT"})
    return modifier


def is_procedural_wall(obj: bpy.types.Object) -> bool:
    """Whether ``obj`` has the current owned procedural-wall modifier."""
    return any(
        modifier.type == "NODES"
        and modifier.node_group is not None
        and modifier.node_group.get(OWNER_KEY) == OWNER_ID
        and modifier.node_group.get(NODE_ROLE_KEY) == NODE_ROLE
        and modifier.node_group.get(SCHEMA_VERSION_KEY) == SCHEMA_VERSION
        for modifier in obj.modifiers
    )
