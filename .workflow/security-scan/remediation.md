# Security diff remediation

The manual diff scan identified three medium candidates and all three were
fixed before commit:

- Material-name collision: visualization materials are now owner-tagged and
  same-named user materials are neither adopted nor mutated.
- Resource exhaustion: wall-band tessellation is capped at 4,096 segments.
- Unowned deletion: array replacement now requires the add-on owner marker.

Blender 4.2.3 smoke coverage exercises each boundary. A final sink scan found
no code execution, filesystem, process, network, deserialization, or credential
handling paths in the runtime package. Remaining Blender datablock removals are
limited to explicit error cleanup, superseded owned meshes, and objects carrying
the add-on owner marker in the current scene's owned collection.
