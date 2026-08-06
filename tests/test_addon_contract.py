"""Static checks on the Blender add-on layer.

These run without Blender by parsing the source with :mod:`ast`. They catch the
class of defect that previously shipped: panels calling operator ids that were
never registered, register/unregister lists drifting apart, and ``bpy`` leaking
into the pure-math core.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest
import tomllib

ADDON = pathlib.Path(__file__).resolve().parent.parent / "blender_projection_system"
CORE = ADDON / "core"
ADDON_MODULES = sorted(p for p in ADDON.glob("*.py"))


def _parse(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_defs(tree: ast.Module):
    return [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]


def _string_attr(cls: ast.ClassDef, name: str):
    for node in cls.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    return None


def _class_sequence(tree: ast.Module, name: str = "_CLASSES"):
    """Names in a module-level ``_CLASSES`` tuple/list, in declaration order."""
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
            and isinstance(node.value, (ast.Tuple, ast.List))
        ):
            return [e.id for e in node.value.elts if isinstance(e, ast.Name)]
    return []


def _registered_names(tree: ast.Module, func_name: str):
    """Class names a module registers or unregisters, in order.

    Handles both spellings: explicit ``bpy.utils.register_class(Foo)`` calls,
    and the ``for cls in _CLASSES`` loop this add-on uses. In the loop form the
    order is the tuple order, reversed when the loop iterates ``reversed(...)``.
    """
    out = []
    sequence = _class_sequence(tree)
    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef) and node.name == func_name):
            continue
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            fn = call.func
            if isinstance(fn, ast.Attribute) and fn.attr in {
                "register_class",
                "unregister_class",
            }:
                for arg in call.args:
                    if isinstance(arg, ast.Name):
                        if arg.id == "cls" and sequence:
                            continue  # resolved from the loop below
                        out.append(arg.id)
        for loop in ast.walk(node):
            if not isinstance(loop, ast.For) or not sequence:
                continue
            iter_src = ast.unparse(loop.iter)
            if "_CLASSES" not in iter_src:
                continue
            if not any(
                isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute)
                and c.func.attr in {"register_class", "unregister_class"}
                for c in ast.walk(loop)
            ):
                continue
            out.extend(reversed(sequence) if "reversed" in iter_src else sequence)
    return out


def _all_declared_idnames():
    ids = {}
    for path in ADDON_MODULES:
        for cls in _class_defs(_parse(path)):
            idname = _string_attr(cls, "bl_idname")
            if idname and idname.startswith("projection."):
                ids[idname] = f"{path.name}:{cls.name}"
    return ids


# -- the core stays free of Blender --------------------------------------


@pytest.mark.parametrize("path", sorted(CORE.glob("*.py")), ids=lambda p: p.name)
def test_core_modules_never_import_bpy(path):
    """The whole point of core/: every formula is testable in plain CPython."""
    tree = _parse(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]
        else:
            continue
        for name in names:
            assert name not in {"bpy", "mathutils", "bmesh", "bpy_extras"}, (
                f"{path.name} imports {name}; core must stay Blender-free"
            )


def test_the_package_imports_without_blender():
    import blender_projection_system

    assert blender_projection_system.bl_info["blender"] == (4, 2, 0)
    assert blender_projection_system.core is not None


def test_register_refuses_politely_when_blender_is_absent():
    import blender_projection_system as pkg

    if pkg.bpy is not None:  # pragma: no cover - only when run inside Blender
        pytest.skip("running inside Blender")
    with pytest.raises(RuntimeError, match="requires Blender"):
        pkg.register()


# -- add-on metadata ------------------------------------------------------


def test_bl_info_has_no_placeholder_author():
    import blender_projection_system as pkg

    author = pkg.bl_info["author"]
    assert author and "Your Name" not in author
    assert "AI Assistant" not in author


def test_bl_info_declares_a_real_version_and_location():
    import blender_projection_system as pkg

    assert pkg.bl_info["version"] >= (0, 2, 0)
    assert pkg.bl_info["location"].startswith("View3D")
    assert pkg.bl_info["description"]


def test_the_extension_manifest_agrees_with_bl_info():
    import blender_projection_system as pkg

    manifest = (ADDON / "blender_manifest.toml")
    assert manifest.exists(), "Blender 4.2 extension manifest is missing"
    text = manifest.read_text(encoding="utf-8")
    version = ".".join(str(p) for p in pkg.bl_info["version"])
    assert f'version = "{version}"' in text
    assert 'blender_version_min = "4.2.0"' in text


def test_the_extension_manifest_satisfies_blender_42_schema_basics():
    manifest = tomllib.loads((ADDON / "blender_manifest.toml").read_text(encoding="utf-8"))
    assert len(manifest["tagline"]) <= 64
    assert "permissions" not in manifest


# -- registration wiring --------------------------------------------------


@pytest.mark.parametrize("path", ADDON_MODULES, ids=lambda p: p.name)
def test_every_module_registers_and_unregisters_the_same_classes(path):
    tree = _parse(path)
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if not {"register", "unregister"} <= names:
        pytest.skip(f"{path.name} has no register/unregister pair")

    registered = _registered_names(tree, "register")
    unregistered = _registered_names(tree, "unregister")
    assert sorted(registered) == sorted(unregistered), (
        f"{path.name}: register/unregister class lists differ"
    )


@pytest.mark.parametrize("path", ADDON_MODULES, ids=lambda p: p.name)
def test_classes_are_unregistered_in_reverse_order(path):
    tree = _parse(path)
    registered = _registered_names(tree, "register")
    unregistered = _registered_names(tree, "unregister")
    if not registered:
        pytest.skip(f"{path.name} registers no classes")
    assert unregistered == list(reversed(registered)), (
        f"{path.name}: unregister order must mirror register order"
    )


@pytest.mark.parametrize("path", ADDON_MODULES, ids=lambda p: p.name)
def test_every_declared_operator_class_is_registered(path):
    tree = _parse(path)
    blender_bases = {"Operator", "Panel", "PropertyGroup", "Menu", "UIList", "_Base"}
    declared = {
        cls.name
        for cls in _class_defs(tree)
        if not cls.name.startswith("_")
        and {ast.unparse(b).split(".")[-1] for b in cls.bases} & blender_bases
    }
    if not declared:
        pytest.skip(f"{path.name} declares no Blender classes")
    registered = set(_registered_names(tree, "register"))
    missing = declared - registered
    assert not missing, f"{path.name}: declared but never registered: {sorted(missing)}"


def test_operator_idnames_are_unique():
    ids = {}
    duplicates = []
    for path in ADDON_MODULES:
        for cls in _class_defs(_parse(path)):
            idname = _string_attr(cls, "bl_idname")
            if not idname:
                continue
            if idname in ids:
                duplicates.append((idname, ids[idname], cls.name))
            ids[idname] = cls.name
    assert not duplicates, f"duplicate bl_idname values: {duplicates}"


# -- the defect that shipped in v0.1 --------------------------------------


def test_every_operator_the_ui_calls_actually_exists():
    """v0.1's panel called three operators that were never registered when the
    panel drew, which made the whole sidebar throw. Never again."""
    declared = _all_declared_idnames()
    called = set()
    for path in ADDON_MODULES:
        source = path.read_text(encoding="utf-8")
        called |= set(re.findall(r'operator\(\s*"(projection\.[a-z0-9_]+)"', source))
    missing = called - set(declared)
    assert not missing, f"UI calls operators that do not exist: {sorted(missing)}"


def test_the_ui_exercises_the_operators_it_ships():
    """The inverse check: no dead operators nobody can reach from the panel."""
    declared = set(_all_declared_idnames())
    called = set()
    for path in ADDON_MODULES:
        source = path.read_text(encoding="utf-8")
        called |= set(re.findall(r'operator\(\s*"(projection\.[a-z0-9_]+)"', source))
    unreachable = declared - called
    assert not unreachable, f"operators unreachable from the UI: {sorted(unreachable)}"


def test_no_module_reintroduces_a_recursion_guard_global():
    """v0.1 guarded property updates with a module-level flag that stayed set
    if an update raised. Property callbacks must use the context manager."""
    source = (ADDON / "properties.py").read_text(encoding="utf-8")
    assert "_updating_projection_params = False" not in source


def test_property_update_callbacks_never_call_operators():
    """Blender forbids bpy.ops from a property update callback; it corrupts the
    undo stack and can crash on depsgraph evaluation."""
    tree = _parse(ADDON / "properties.py")
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("update_"):
            continue
        for call in ast.walk(node):
            if isinstance(call, ast.Call):
                src = ast.unparse(call.func)
                assert not src.startswith("bpy.ops"), (
                    f"{node.name} calls {src}; property callbacks must not run operators"
                )
