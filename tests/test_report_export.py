"""Tests for structured handoff export (JSON/CSV) of analysis and rigging schedule."""

from __future__ import annotations

import json

import pytest

import blender_projection_system.core.photometry as ph
from blender_projection_system.core.coverage import analyze_coverage
from blender_projection_system.core.footprint import compute_footprint
from blender_projection_system.core.pose import Pose
from blender_projection_system.core.report_export import (
    RiggingItem,
    export_analysis_to_json,
    export_coverage_summary_to_csv,
    export_rigging_schedule_to_csv,
    report_to_dict,
)
from blender_projection_system.core.surfaces import CylindricalWall
from blender_projection_system.core.throw import ProjectorSpec


@pytest.fixture
def sample_report_and_rigging():
    wall = CylindricalWall(radius=8.0, height=3.0, angle_start=-0.5, angle_end=0.5)
    spec = ProjectorSpec(
        throw_ratio=1.5,
        lumens=6000.0,
        manufacturer="Panasonic",
        model="PT-REQ12",
        lens_model="ET-DLE150",
        native_contrast=25000.0,
        lens_transmission=0.90,
        weight_kg=27.0,
    )
    pose = Pose(
        origin=(0.0, 0.0, 1.5),
        right=(0.0, -1.0, 0.0),
        up=(0.0, 0.0, 1.0),
        forward=(1.0, 0.0, 0.0),
    )
    fp = compute_footprint(pose, spec, wall, samples=15, name="PJ_01")
    derate = ph.DerateChain(production_tolerance=0.80, picture_mode_factor=0.85, aging_factor=0.80)
    report = analyze_coverage(
        [fp],
        wall,
        grid_s=40,
        grid_z=15,
        screen_gain=1.0,
        derate_chain=derate,
        ambient_lux=50.0,
        iscr_category=ph.ISCRCategory.BASIC_DECISION_MAKING,
        target_contrast_ratio=15.0,
        enable_nine_point=True,
    )

    rigging = [
        RiggingItem(
            name="PJ_01",
            manufacturer="Panasonic",
            model="PT-REQ12",
            lens_model="ET-DLE150",
            mount_x=0.0,
            mount_y=0.0,
            mount_z=1.5,
            yaw_deg=0.0,
            pitch_deg=0.0,
            roll_deg=0.0,
            throw_distance=8.0,
            image_width=5.333,
            image_height=3.0,
            lens_shift_v_pct=0.0,
            lens_shift_h_pct=0.0,
            lumens=6000.0,
            weight_kg=27.0,
            corners_world=((1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 9.0), (1.0, 0.0, 1.0)),
        )
    ]
    return report, rigging


def test_report_to_dict_structure(sample_report_and_rigging):
    report, rigging = sample_report_and_rigging
    d = report_to_dict(report, rigging, extra_meta={"author": "Sam Lyndon", "job": "23482"})

    assert d["schema_version"] == 1
    assert d["metadata"]["job"] == "23482"
    assert "wall" in d
    assert d["wall"]["name"] == report.wall_name
    assert d["wall"]["arc_length_m"] > 0.0

    assert "coverage" in d
    assert d["coverage"]["covered_cells"] == report.covered_cells
    assert "covered_fraction" in d["coverage"]

    assert "brightness" in d
    assert "bands" in d["brightness"]
    assert "rated" in d["brightness"]["bands"]
    assert "typical" in d["brightness"]["bands"]
    assert "worst_case" in d["brightness"]["bands"]

    assert "contrast" in d
    assert d["contrast"]["ambient_lux"] == 50.0
    assert d["contrast"]["target_category"] == "basic_decision_making"
    assert "ANSI/AVIXA V201.01:2021" in d["contrast"]["disclaimer"]

    assert "nine_point" in d
    assert len(d["nine_point"]["points"]) == 9
    assert d["nine_point"]["light_output_lumens"] > 0.0

    assert "rigging_schedule" in d
    assert len(d["rigging_schedule"]) == 1
    assert d["rigging_schedule"][0]["model"] == "PT-REQ12"
    assert len(d["rigging_schedule"][0]["corners_world"]) == 4


def test_export_analysis_to_json_round_trip(sample_report_and_rigging):
    report, rigging = sample_report_and_rigging
    json_str = export_analysis_to_json(report, rigging)
    parsed = json.loads(json_str)

    assert parsed["schema_version"] == 1
    assert parsed["wall"]["name"] == report.wall_name
    assert parsed["rigging_schedule"][0]["name"] == "PJ_01"
    assert parsed["contrast"]["ambient_lux"] == 50.0


def test_export_rigging_schedule_to_csv(sample_report_and_rigging):
    _, rigging = sample_report_and_rigging
    csv_str = export_rigging_schedule_to_csv(rigging)
    lines = csv_str.strip().split("\n")

    header = lines[0].split(",")
    assert "Unit" in header
    assert "Manufacturer" in header
    assert "Mount_X_m" in header
    assert "Throw_m" in header

    row = lines[1].split(",")
    assert row[0] == "PJ_01"
    assert row[1] == "Panasonic"
    assert row[2] == "PT-REQ12"


def test_export_coverage_summary_to_csv(sample_report_and_rigging):
    report, rigging = sample_report_and_rigging
    csv_str = export_coverage_summary_to_csv(report, rigging)

    assert "Wall,Name" in csv_str
    assert "Coverage,Covered Area" in csv_str
    assert "Brightness,Mean Illuminance" in csv_str
    assert "Contrast,Ambient Illuminance" in csv_str
    assert "ANSI_9Point,Light Output" in csv_str
    assert "--- RIGGING SCHEDULE ---" in csv_str
    assert "PJ_01,Panasonic,PT-REQ12" in csv_str
