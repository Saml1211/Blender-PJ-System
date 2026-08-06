"""Projection Planner - curved-wall projector planning for Blender 4.2.

The package is importable outside Blender. When ``bpy`` is unavailable only
:mod:`blender_projection_system.core` (the pure projection mathematics) is
loaded, which is what the test suite and any headless tooling use.
"""

bl_info = {
    "name": "Projection Planner",
    "author": "Sam Lyndon",
    "version": (0, 2, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Projection",
    "description": (
        "Plan ceiling-mounted projector arrays against curved and flat walls: "
        "throw geometry, footprints, coverage, blend zones and brightness."
    ),
    "warning": "",
    "doc_url": "https://github.com/Saml1211/Blender-PJ-System",
    "tracker_url": "https://github.com/Saml1211/Blender-PJ-System/issues",
    "category": "3D View",
}

from . import core  # noqa: F401  (pure math, always importable)

try:  # pragma: no cover - exercised only inside Blender
    import bpy
except ImportError:  # pragma: no cover
    bpy = None

if bpy is not None:  # pragma: no cover - requires Blender
    from . import operators, properties, ui

    # Order matters: properties first, since operators and panels read them.
    # ``visualization`` registers nothing - it is a helper module imported by
    # the operators.
    _MODULES = (properties, operators, ui)
    _REGISTERED = False

    def register():
        global _REGISTERED
        if _REGISTERED:
            return
        registered = []
        try:
            for mod in _MODULES:
                mod.register()
                registered.append(mod)
        except Exception:
            # Roll back a partial registration so the add-on can be enabled
            # again after the underlying problem is fixed.
            for mod in reversed(registered):
                try:
                    mod.unregister()
                except Exception:
                    pass
            raise
        _REGISTERED = True

    def unregister():
        global _REGISTERED
        if not _REGISTERED:
            return
        for mod in reversed(_MODULES):
            try:
                mod.unregister()
            except Exception as exc:
                print(f"[Projection Planner] unregister failed for {mod.__name__}: {exc}")
        _REGISTERED = False

else:

    def register():
        raise RuntimeError("Projection Planner requires Blender; bpy is not available")

    def unregister():
        raise RuntimeError("Projection Planner requires Blender; bpy is not available")
