"""Tests for ANSI/INFOCOMM V202.01 (DISCAS) viewing distance and viewer audit."""

from __future__ import annotations

import math

import pytest

from blender_projection_system.core.coverage import analyze_coverage, format_report
from blender_projection_system.core.discas import (
    DISCAS_DISCLAIMER,
    adm_max_viewing_distance,
    audit_viewers,
    bdm_max_viewing_distance,
    closest_viewer_min_distance,
)
from blender_projection_system.core.errors import ProjectionError
from blender_projection_system.core.surfaces import CylindricalWall
from blender_projection_system.core.throw import ProjectorSpec


def test_bdm_max_viewing_distance_formula():
    # 2.0 m height, 3% element height
    # D_max = 2.0 * 0.03 / tan(10 arcmin) ≈ 20.626 m
    d = bdm_max_viewing_distance(2.0, 3.0)
    expected = 0.06 / math.tan(math.radians(10.0 / 60.0))
    assert d == pytest.approx(expected)
    assert 20.6 < d < 20.7

    # 50% smaller text (1.5%) halves max viewing distance
    assert bdm_max_viewing_distance(2.0, 1.5) == pytest.approx(d * 0.5)

    with pytest.raises(ProjectionError):
        bdm_max_viewing_distance(0.0)
    with pytest.raises(ProjectionError):
        bdm_max_viewing_distance(2.0, -1.0)


def test_adm_max_viewing_distance_formula():
    # 2.0 m height, 1080p
    # D_max = (2.0 / 1080) / tan(1 arcmin) ≈ 6.366 m
    d_1080 = adm_max_viewing_distance(2.0, 1080)
    expected = (2.0 / 1080.0) / math.tan(math.radians(1.0 / 60.0))
    assert d_1080 == pytest.approx(expected)
    assert 6.35 < d_1080 < 6.38

    # 4K (2160p) halves max distance for 1-arcminute single-pixel resolution
    d_4k = adm_max_viewing_distance(2.0, 2160)
    assert d_4k == pytest.approx(d_1080 * 0.5)

    with pytest.raises(ProjectionError):
        adm_max_viewing_distance(2.0, 0)


def test_closest_viewer_distance():
    assert closest_viewer_min_distance(2.5) == pytest.approx(2.5)


def test_audit_viewers_conformance_and_angles():
    screen_center = (0.0, 0.0, 1.5)
    screen_normal = (0.0, -1.0, 0.0)  # wall facing -Y (into room +Y)

    # Viewer 1: on-axis at 5 m (in front of screen, +Y direction in room is towards -Y from wall normal)
    # normal points towards -Y, so viewer at (0, -5, 1.5) is directly along screen normal!
    viewers = [
        ("FrontRowCenter", (0.0, -4.0, 1.5)),
        ("BackRowCenter", (0.0, -15.0, 1.5)),
        ("FrontRowSide", (3.0, -4.0, 1.5)),
        ("WayTooFar", (0.0, -35.0, 1.5)),
    ]

    report = audit_viewers(
        viewers=viewers,
        screen_center=screen_center,
        screen_normal=screen_normal,
        image_height=2.0,
        mean_screen_nits=200.0,
        vertical_resolution=1080,
        element_height_pct=3.0,
    )

    # BDM max is ~20.6 m, ADM max is ~6.37 m
    v_dict = {v.name: v for v in report.viewers}

    # FrontRowCenter at 4 m: passes both BDM and ADM
    assert v_dict["FrontRowCenter"].distance == pytest.approx(4.0)
    assert v_dict["FrontRowCenter"].bdm_pass is True
    assert v_dict["FrontRowCenter"].adm_pass is True
    assert v_dict["FrontRowCenter"].off_axis_deg == pytest.approx(0.0, abs=1e-3)
    assert v_dict["FrontRowCenter"].perceived_nits == pytest.approx(200.0)

    # BackRowCenter at 15 m: passes BDM (15 < 20.6), fails ADM (15 > 6.37)
    assert v_dict["BackRowCenter"].bdm_pass is True
    assert v_dict["BackRowCenter"].adm_pass is False

    # FrontRowSide at (3, -4, 1.5): distance = 5 m, off-axis angle = atan(3/4) = 36.87 deg
    assert v_dict["FrontRowSide"].distance == pytest.approx(5.0)
    assert v_dict["FrontRowSide"].off_axis_deg == pytest.approx(math.degrees(math.atan(3.0 / 4.0)))
    assert v_dict["FrontRowSide"].off_axis_pass is True
    assert v_dict["FrontRowSide"].perceived_nits == pytest.approx(200.0 * (4.0 / 5.0))

    # WayTooFar at 35 m: fails both BDM and ADM
    assert v_dict["WayTooFar"].bdm_pass is False
    assert v_dict["WayTooFar"].adm_pass is False

    assert report.bdm_conforms is False
    assert report.adm_conforms is False
    assert report.farthest_distance == pytest.approx(35.0)
    assert DISCAS_DISCLAIMER in report.disclaimer


def test_coverage_report_with_discas():
    wall = CylindricalWall(radius=8.0, height=3.0, angle_start=-0.5, angle_end=0.5)
    spec = ProjectorSpec(throw_ratio=1.5, lumens=6000.0)
    from tests.test_coverage import _projector_at

    proj = _projector_at(wall, wall.arc_length * 0.5, 4.5, spec, "PJ_01")
    viewers = [
        ("Seat_A1", (0.0, 5.0, 1.5)),
        ("Seat_F10", (0.0, 12.0, 1.5)),
    ]
    report = analyze_coverage(
        [proj],
        wall,
        grid_s=40,
        grid_z=10,
        viewers=viewers,
        discas_element_height_pct=3.0,
        discas_vertical_resolution=1080,
    )
    assert report.discas is not None
    assert len(report.discas.viewers) == 2
    assert report.discas.bdm_max_distance > 0.0

    lines = format_report(report)
    text = "\n".join(lines)
    assert "DISCAS Viewer Audit" in text
    assert "ANSI/INFOCOMM V202.01" in text
    assert "Seat_A1" in text
