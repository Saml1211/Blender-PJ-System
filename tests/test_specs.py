"""Tests for the projector & lens spec library (core/specs.py, increment #2).

The library is pure data + validation: no bpy, no maths duplication. These
tests load the bundled starter database and exercise the loaders, the range
validation (warn, never clamp), and the ProjectorSpec metadata round trip.
"""

from __future__ import annotations

import json

import pytest

from blender_projection_system.core.errors import ProjectionError
from blender_projection_system.core.specs import (
    CSV_COLUMNS,
    LensSpec,
    ProjectorModel,
    SpecLibrary,
    load_builtin_library,
    load_library_from_csv,
    load_library_from_json,
)
from blender_projection_system.core.throw import ProjectorSpec

# -- bundled starter library ---------------------------------------------------


def test_the_builtin_library_loads_and_cites_sources():
    library = load_builtin_library()
    assert len(library.models) >= 6
    for model in library.models:
        assert model.source_url.startswith("http"), f"{model.full_name} needs a source"
        assert model.lumens > 0
        assert model.lenses, f"{model.full_name} must list its lenses"
        for lens in model.lenses:
            assert 0.0 < lens.throw_ratio_min <= lens.throw_ratio_max
            assert 0.0 < lens.transmission_factor <= 1.0


def test_builtin_rows_flag_verification():
    library = load_builtin_library()
    for model in library.models:
        assert model.verified is True, (
            f"{model.full_name} ships in the starter set only if transcribed from its cited source"
        )


def test_builtin_manufacturers_and_lookups():
    library = load_builtin_library()
    manufacturers = library.all_manufacturers()
    assert set(manufacturers) >= {"Christie", "Panasonic", "Barco", "Epson"}

    panasonic_models = library.models_for_manufacturer("panasonic")
    assert {m.model for m in panasonic_models} >= {"PT-REQ12", "PT-MZ20K"}

    model = library.get_model("Christie", "m 4k25 rgb")
    assert model is not None
    assert model.lumens == 25000.0

    lens = library.find_lens(model, "ILS4 1.2-1.6")
    assert lens is not None
    assert lens.throw_ratio_min == 1.2
    assert library.find_lens(model, "nonexistent") is None
    assert library.get_model("Nobody", "Nothing") is None


# -- range validation: warn, never clamp (ADR 0002) -----------------------------


@pytest.fixture
def lens_pair() -> tuple[ProjectorModel, LensSpec]:
    library = load_builtin_library()
    model = library.get_model("Christie", "M 4K25 RGB")
    assert model is not None
    lens = library.find_lens(model, "ILS4 1.2-1.6")
    assert lens is not None
    return model, lens


def test_in_range_throw_and_shift_produce_no_warnings(lens_pair):
    _model, lens = lens_pair
    assert SpecLibrary().validate_throw(_model, lens, 1.4) == []
    assert SpecLibrary().validate_throw(_model, lens, 1.4, shift_v=0.4, shift_h=0.1) == []


def test_throw_ratio_below_the_lens_minimum_warns_with_both_numbers(lens_pair):
    _model, lens = lens_pair
    warnings = SpecLibrary().validate_throw(_model, lens, 0.9)
    assert warnings == ["Throw ratio 0.900 is below lens minimum 1.200"]


def test_throw_ratio_above_the_lens_maximum_warns_with_both_numbers(lens_pair):
    _model, lens = lens_pair
    warnings = SpecLibrary().validate_throw(_model, lens, 2.0)
    assert warnings == ["Throw ratio 2.000 is above lens maximum 1.600"]


def test_shift_beyond_the_lens_limit_warns_and_is_never_clamped(lens_pair):
    _model, lens = lens_pair
    warnings = SpecLibrary().validate_throw(_model, lens, 1.4, shift_v=0.9)
    assert len(warnings) == 1
    assert "0.900" in warnings[0] and "0.500" in warnings[0]

    h_warnings = SpecLibrary().validate_throw(_model, lens, 1.4, shift_h=0.5)
    assert len(h_warnings) == 1
    assert "Horizontal" in h_warnings[0]


def test_every_violation_is_reported_at_once(lens_pair):
    _model, lens = lens_pair
    warnings = SpecLibrary().validate_throw(_model, lens, 0.5, shift_v=1.0, shift_h=1.0)
    assert len(warnings) == 3


def test_fixed_lens_only_accepts_its_own_ratio():
    library = load_builtin_library()
    model = library.get_model("Panasonic", "PT-MZ20K")
    assert model is not None
    fixed = library.find_lens(model, "ET-EMU100")
    assert fixed is not None and fixed.is_fixed
    assert SpecLibrary().validate_throw(model, fixed, 0.33) == []
    assert len(SpecLibrary().validate_throw(model, fixed, 0.5)) == 1


# -- JSON loading ----------------------------------------------------------------


def _minimal_model(**overrides) -> dict:
    entry = {
        "manufacturer": "TestCo",
        "model": "Tiny 1",
        "lumens": 5000.0,
        "aspect_w": 16,
        "aspect_h": 9,
        "lenses": [
            {
                "model": "Zoom A",
                "throw_ratio_min": 1.0,
                "throw_ratio_max": 2.0,
                "max_lens_shift_v": 0.5,
                "max_lens_shift_h": 0.15,
            }
        ],
        "source_url": "https://example.com",
        "verified": True,
    }
    entry.update(overrides)
    return entry


def test_json_loading_from_string():
    library = load_library_from_json(
        json.dumps({"schema_version": 1, "models": [_minimal_model()]})
    )
    model = library.get_model("TestCo", "Tiny 1")
    assert model is not None
    assert model.verified is True
    assert model.lenses[0].throw_ratio_max == 2.0


def test_json_loading_from_file(tmp_path):
    path = tmp_path / "library.json"
    path.write_text(
        json.dumps({"schema_version": 1, "models": [_minimal_model()]}), encoding="utf-8"
    )
    library = load_library_from_json(path)
    assert library.get_model("TestCo", "Tiny 1") is not None


def test_json_from_path_string_round_trip(tmp_path):
    path = tmp_path / "library.json"
    path.write_text(
        json.dumps({"schema_version": 1, "models": [_minimal_model()]}), encoding="utf-8"
    )
    library = load_library_from_json(str(path))
    assert len(library.models) == 1


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version": 2, "models": []}',
        "not json at all",
        '{"schema_version": 1, "models": [{"manufacturer": "X", "model": "Y", '
        '"lumens": -5, "aspect_w": 16, "aspect_h": 9}]}',
        '{"schema_version": 1, "models": [{"manufacturer": "", "model": "Y", '
        '"lumens": 5, "aspect_w": 16, "aspect_h": 9}]}',
        '{"schema_version": 1, "models": [{"manufacturer": "X", "model": "Y", '
        '"lumens": 5, "aspect_w": 16, "aspect_h": 9, "lenses": '
        '[{"model": "L", "throw_ratio_min": 2.0, "throw_ratio_max": 1.0, '
        '"max_lens_shift_v": 0.5, "max_lens_shift_h": 0.1}]}]}',
        '{"schema_version": 1, "models": [{"manufacturer": "X", "model": "Y", '
        '"lumens": 5, "aspect_w": 16, "aspect_h": 9, "lenses": '
        '[{"model": "L", "throw_ratio_min": 1.0, "throw_ratio_max": 2.0, '
        '"max_lens_shift_v": 0.5, "max_lens_shift_h": 0.1, '
        '"transmission_factor": 1.5}]}]}',
    ],
)
def test_corrupt_json_is_rejected_loudly(payload):
    with pytest.raises(ProjectionError):
        load_library_from_json(payload)


# -- CSV loading ------------------------------------------------------------------

CSV_BODY = (
    "manufacturer,model,lumens,aspect_w,aspect_h,contrast,weight,lens_model,"
    "tr_min,tr_max,shift_v,shift_h,transmission,source_url,verified\n"
    "TestCo,Tiny 1,5000,16,9,2000,10,Zoom A,1.0,2.0,0.5,0.15,0.95,https://example.com,true\n"
    "TestCo,Tiny 1,5000,16,9,2000,10,Zoom B,2.0,4.0,0.4,0.1,0.95,https://example.com,true\n"
    "OtherCo,Box 2,3000,16,10,,,,,,https://example.com,false\n"
)


def test_csv_loading_merges_lens_rows_into_one_model():
    library = load_library_from_csv(CSV_BODY)
    model = library.get_model("TestCo", "Tiny 1")
    assert model is not None
    assert len(model.lenses) == 2
    assert model.lenses[0].transmission_factor == 0.95
    assert model.lenses[1].model == "Zoom B"

    body_only = library.get_model("OtherCo", "Box 2")
    assert body_only is not None
    assert body_only.lenses == ()
    assert body_only.verified is False


def test_csv_loading_from_file(tmp_path):
    path = tmp_path / "library.csv"
    path.write_text(CSV_BODY, encoding="utf-8-sig")  # BOM, as Excel exports do
    library = load_library_from_csv(path)
    assert len(library.models) == 2


def test_csv_with_a_missing_column_is_rejected_by_name():
    headerless = CSV_BODY.replace("tr_min,", "")
    with pytest.raises(ProjectionError, match="tr_min"):
        load_library_from_csv(headerless)


def test_csv_partial_lens_row_is_rejected():
    broken = CSV_BODY.replace("Zoom B,2.0,4.0", "Zoom B,2.0,")
    with pytest.raises(ProjectionError, match="line 3"):
        load_library_from_csv(broken)


def test_csv_non_numeric_lumens_are_rejected():
    broken = CSV_BODY.replace(",5000,16,9,", ",five thousand,16,9,", 1)
    with pytest.raises(ProjectionError):
        load_library_from_csv(broken)


def test_csv_columns_are_the_documented_contract():
    assert CSV_COLUMNS == (
        "manufacturer",
        "model",
        "lumens",
        "aspect_w",
        "aspect_h",
        "contrast",
        "weight",
        "lens_model",
        "tr_min",
        "tr_max",
        "shift_v",
        "shift_h",
        "transmission",
        "source_url",
        "verified",
    )


# -- ProjectorSpec metadata round trip ---------------------------------------------


def test_projector_spec_accepts_library_metadata():
    library = load_builtin_library()
    model = library.get_model("Barco", "UDX-4K32")
    assert model is not None
    lens = library.find_lens(model, "TLD+ 1.40-1.87")
    assert lens is not None

    spec = ProjectorSpec(
        throw_ratio=1.6,
        aspect_w=model.aspect_w,
        aspect_h=model.aspect_h,
        lumens=model.lumens,
        max_lens_shift_v=lens.max_lens_shift_v,
        max_lens_shift_h=lens.max_lens_shift_h,
        throw_ratio_min=lens.throw_ratio_min,
        throw_ratio_max=lens.throw_ratio_max,
        manufacturer=model.manufacturer,
        model=model.model,
        lens_model=lens.model,
        native_contrast=model.native_contrast,
        lens_transmission=lens.transmission_factor,
        weight_kg=model.weight_kg,
        source_url=model.source_url,
        verified=model.verified,
    )
    assert spec.manufacturer == "Barco"
    assert spec.lens_model == "TLD+ 1.40-1.87"
    assert spec.verified is True


def test_projector_spec_metadata_defaults_keep_existing_construction_valid():
    spec = ProjectorSpec(throw_ratio=1.5)
    assert spec.manufacturer == ""
    assert spec.lens_transmission == 1.0
    assert spec.verified is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"native_contrast": 0.5},
        {"lens_transmission": 0.0},
        {"lens_transmission": 1.5},
        {"weight_kg": -1.0},
        {"lens_transmission": float("nan")},
    ],
)
def test_projector_spec_rejects_impossible_metadata(kwargs):
    with pytest.raises(ProjectionError):
        ProjectorSpec(**kwargs)


def test_lens_and_model_dataclasses_standalone():
    lens = LensSpec(
        model="F",
        throw_ratio_min=1.0,
        throw_ratio_max=1.0,
        max_lens_shift_v=0.5,
        max_lens_shift_h=0.0,
    )
    assert lens.is_fixed
    model = ProjectorModel(manufacturer="A", model="B", lumens=1.0, aspect_w=16, aspect_h=9)
    assert model.full_name == "A B"
    assert model.lenses == ()
    with pytest.raises(ProjectionError):
        ProjectorModel(manufacturer="A", model="", lumens=1.0, aspect_w=16, aspect_h=9)
