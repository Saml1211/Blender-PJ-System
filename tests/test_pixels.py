"""Pixel, image-size and scenario arithmetic (core/pixels.py), hand-checkable."""

from __future__ import annotations

import csv
import io
import math

import pytest

from blender_projection_system.core.coverage import analyze_coverage, format_report
from blender_projection_system.core.errors import ProjectionError
from blender_projection_system.core.footprint import compute_footprint
from blender_projection_system.core.pixels import (
    ScenarioInputs,
    blended_canvas,
    evaluate_scenario,
    fmt_mm,
    fmt_pitch,
    image_vertical_extent,
    lens_range_warnings,
    one_arcminute_distance,
    pixel_pitch,
    pixels_per_degree,
    pixels_per_metre,
    scenarios_to_csv,
    shift_for_bottom_edge,
    solve_image,
    surface_pitch,
    vertical_fit_warnings,
)
from blender_projection_system.core.pose import level_pose
from blender_projection_system.core.surfaces import PlanarWall
from blender_projection_system.core.throw import ProjectorSpec, default_resolution

# -- pitch and density -------------------------------------------------------


def test_pixel_pitch_of_a_9159_mm_image_at_1920_px_is_4_77_mm():
    assert pixel_pitch(9.159, 1920) * 1000.0 == pytest.approx(4.77, abs=0.005)
    assert fmt_pitch(pixel_pitch(9.159, 1920)) == "4.77 mm/px"


def test_pixels_per_metre_is_the_inverse_of_pitch():
    assert pixels_per_metre(2.0, 1920) == pytest.approx(960.0)


def test_pitch_rejects_zero_pixels():
    with pytest.raises(ProjectionError):
        pixel_pitch(2.0, 0)


# -- solving the throw triangle ------------------------------------------------


def test_throw_3297_mm_at_tr_0_36_gives_9158_mm_width():
    image = solve_image(16 / 10, distance=3.297, throw_ratio=0.36)
    assert fmt_mm(image.width) == "9158 mm"
    assert image.height == pytest.approx(image.width / 1.6)


def test_width_and_distance_give_the_throw_ratio():
    image = solve_image(16 / 9, distance=6.0, width=5.0)
    assert image.throw_ratio == pytest.approx(1.2)


def test_height_and_throw_ratio_give_distance_and_width():
    image = solve_image(16 / 10, throw_ratio=1.0, height=2.0)
    assert image.width == pytest.approx(3.2)
    assert image.distance == pytest.approx(3.2)


def test_a_3_4_5_diagonal_gives_4_by_3():
    image = solve_image(4 / 3, distance=8.0, diagonal=5.0)
    assert image.width == pytest.approx(4.0)
    assert image.height == pytest.approx(3.0)
    assert image.diagonal == pytest.approx(5.0)
    assert image.throw_ratio == pytest.approx(2.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"distance": 3.0},
        {"width": 2.0, "height": 1.0},
        {"distance": 3.0, "throw_ratio": 1.0, "width": 3.0},
    ],
)
def test_solve_needs_exactly_two_independent_quantities(kwargs):
    with pytest.raises(ProjectionError):
        solve_image(16 / 9, **kwargs)


# -- vertical placement --------------------------------------------------------


def test_image_edges_follow_lens_height_and_shift():
    # Lens 3000 mm AFF, image 2000 mm high, shifted down by half the image:
    # the centre lands 1000 mm below the axis.
    extent = image_vertical_extent(3.0, 2.0, -0.5)
    assert extent.centre == pytest.approx(2.0)
    assert extent.bottom == pytest.approx(1.0)
    assert extent.top == pytest.approx(3.0)


def test_shift_for_bottom_edge_inverts_the_extent():
    shift = shift_for_bottom_edge(3.0, 2.0, 1.0)
    assert shift == pytest.approx(-0.5)
    assert image_vertical_extent(3.0, 2.0, shift).bottom == pytest.approx(1.0)


def test_vertical_fit_passes_inside_one_mm_and_reports_mm_otherwise():
    extent = image_vertical_extent(3.0, 2.0, -0.5)
    assert vertical_fit_warnings(extent, 1.0005, 2.0) == []
    warnings = vertical_fit_warnings(extent, 0.8, 2.0)
    assert any("200 mm above the screen bottom edge 800 mm" in w for w in warnings)
    assert any("Image top 3000 mm AFF is 200 mm above the screen top edge 2800 mm" in w
               for w in warnings)


# -- acuity --------------------------------------------------------------------


def test_one_arcminute_distance_for_4_77_mm_pitch_is_about_16_4_m():
    assert one_arcminute_distance(0.00477) == pytest.approx(16.398, abs=0.01)


def test_pixels_per_degree_is_60_at_the_one_arcminute_distance():
    pitch = 0.00477
    assert pixels_per_degree(pitch, one_arcminute_distance(pitch)) == pytest.approx(60.0)


# -- blended canvas ------------------------------------------------------------


def test_two_1920_px_images_with_15_percent_overlap_give_3552_px():
    canvas = blended_canvas(1920, 1200, 2, overlap_fraction=0.15)
    assert canvas.pixels_x == 3552
    assert canvas.pixels_y == 1200
    assert canvas.overlap_px_total == 288


def test_canvas_width_and_density_from_image_width():
    canvas = blended_canvas(1920, 1080, 3, overlap_px=192, image_width=4.0)
    assert canvas.pixels_x == 3 * 1920 - 2 * 192
    assert canvas.width == pytest.approx(4.0 * (3 - 2 * 0.1))
    assert canvas.pixels_per_metre == pytest.approx(canvas.pixels_x / canvas.width)


def test_canvas_overlap_must_be_one_form():
    with pytest.raises(ProjectionError):
        blended_canvas(1920, 1080, 2)
    with pytest.raises(ProjectionError):
        blended_canvas(1920, 1080, 2, overlap_fraction=0.1, overlap_px=10)


def _flat_pair(res=(1920, 1200)):
    """Two level projectors 3 m from a 4 m flat wall, 2.2 m images, 0.4 m overlap."""
    wall = PlanarWall(base_center=(5.0, 0.0, 0.0), width=4.0, height=2.5)
    spec = ProjectorSpec(
        throw_ratio=3.0 / 2.2, aspect_w=16, aspect_h=10, res_x=res[0], res_y=res[1]
    )
    footprints = [
        compute_footprint(
            level_pose((2.0, y, 1.25), (1.0, 0.0, 0.0)), spec, wall, samples=9, name=name
        )
        for name, y in (("A", -0.9), ("B", 0.9))
    ]
    return wall, footprints


def test_surface_pitch_on_a_square_on_flat_wall_is_uniform():
    _wall, footprints = _flat_pair()
    pitch = surface_pitch(footprints[0])
    assert pitch is not None
    assert pitch.mean == pytest.approx(2.2 / 1920)
    assert pitch.minimum == pytest.approx(pitch.mean)
    assert pitch.maximum == pytest.approx(pitch.mean)


def test_report_canvas_uses_measured_blend_zones():
    wall, footprints = _flat_pair()
    report = analyze_coverage(footprints, wall, grid_s=400, grid_z=20)
    canvas = report.canvas
    assert canvas is not None
    assert canvas.projectors == 2
    # 0.4 m of a 2.2 m image overlaps: about 349 px removed. The raster blend
    # zone is quantised to 10 mm cells, so allow a few pixels.
    assert canvas.pixels_x == pytest.approx(2 * 1920 - 0.4 / 2.2 * 1920, abs=15)
    assert canvas.width == pytest.approx(4.0, abs=0.02)
    assert any(line.startswith("Blended canvas:") and " mm " in line
               for line in format_report(report))


# -- lens range and scenarios ----------------------------------------------------


def test_lens_range_warns_without_clamping():
    inp = ScenarioInputs(
        distance=3.0, throw_ratio=0.30, res_x=1920, res_y=1200, lens_shift_v=0.6,
        throw_ratio_min=0.34, throw_ratio_max=0.41, max_lens_shift_v=0.5,
        max_lens_shift_h=0.15,
    )
    warnings = lens_range_warnings(inp)
    assert any("outside the lens range" in w for w in warnings)
    assert any("Vertical shift" in w for w in warnings)
    assert evaluate_scenario(inp).image.throw_ratio == pytest.approx(0.30)


def test_no_lens_selected_skips_the_shift_check():
    inp = ScenarioInputs(distance=3.0, throw_ratio=1.0, res_x=1920, res_y=1080, lens_shift_v=0.4)
    assert lens_range_warnings(inp) == []


def test_scenario_bundles_every_number():
    inp = ScenarioInputs(
        distance=3.297, throw_ratio=0.36, res_x=1920, res_y=1200,
        lens_height=6.0, lens_shift_v=-0.5, viewing_distance=10.0,
        projector_count=2, overlap_fraction=0.15,
    )
    res = evaluate_scenario(inp)
    assert res.pitch * 1000.0 == pytest.approx(4.77, abs=0.005)
    assert res.extent.top == pytest.approx(6.0)
    assert res.canvas.pixels_x == 3552
    assert res.pixels_per_degree < 60.0
    assert any("px/deg" in w for w in res.warnings)


def test_scenarios_csv_has_one_row_per_scenario_in_mm():
    inp = ScenarioInputs(distance=3.297, throw_ratio=0.36, res_x=1920, res_y=1200)
    text = scenarios_to_csv([("A", inp, evaluate_scenario(inp)), ("B", inp, evaluate_scenario(inp))])
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][0] == "Scenario"
    assert [r[0] for r in rows[1:]] == ["A", "B"]
    row = dict(zip(rows[0], rows[1], strict=True))
    assert row["Image W x H"] == "9158 x 5724 mm"
    assert row["Pixel pitch"] == "4.77 mm/px"
    assert " m" not in row["Throw distance"].replace(" mm", "")


def test_default_resolution_assumption():
    assert default_resolution(16, 10) == (1920, 1200)
    assert default_resolution(16, 9) == (1920, 1080)
    assert ProjectorSpec(aspect_w=16, aspect_h=10).resolution == (1920, 1200)
    assert ProjectorSpec(res_x=3840, res_y=2160).resolution == (3840, 2160)


# -- 23538 regression: concave R3750, two level 16:10 projectors, vertical spill ----
# Reference: a per-pixel ray cast of all 1920 columns of each camera onto the same
# cylinder found 675 of 1200 rows on the wall, a 413 px blend per image, and a
# 3427 px canvas over the 11,781 mm arc. The coarse 9-sample estimate reported
# 1200 rows, 276 px blended and an arc longer than the wall.


def _concave_pair():
    from blender_projection_system.core.surfaces import CylindricalWall

    wall = CylindricalWall(
        radius=3.75, height=3.24, angle_start=math.radians(-90.0), angle_end=math.radians(90.0)
    )
    spec = ProjectorSpec(
        throw_ratio=0.36, aspect_w=16, aspect_h=10, lens_shift_v=-0.3841, res_x=1920, res_y=1200
    )
    footprints = []
    for name, y, yaw in (("PJ_01", -0.298, -41.351), ("PJ_02", 0.298, 41.351)):
        direction = (math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), 0.0)
        pose = level_pose((0.3385, y, 2.8), direction)
        footprints.append(compute_footprint(pose, spec, wall, samples=9, name=name))
    return wall, footprints


def test_canvas_rows_count_only_rows_that_land_on_the_wall():
    wall, footprints = _concave_pair()
    canvas = analyze_coverage(footprints, wall, grid_s=120, grid_z=24).canvas
    assert canvas.pixels_y == pytest.approx(675, rel=0.02)


def test_canvas_blend_counts_image_columns_inside_the_overlap():
    wall, footprints = _concave_pair()
    canvas = analyze_coverage(footprints, wall, grid_s=120, grid_z=24).canvas
    assert canvas.overlap_px_total == pytest.approx(413, rel=0.05)
    assert canvas.pixels_x == pytest.approx(3427, rel=0.01)


def test_canvas_arc_never_exceeds_the_wall():
    wall, footprints = _concave_pair()
    # The live 23538 coverage grid; the raster estimate overshot the wall here.
    canvas = analyze_coverage(footprints, wall, grid_s=200, grid_z=54).canvas
    assert canvas.width <= wall.arc_length + 1e-9
    assert canvas.width == pytest.approx(11.781, abs=0.01)


def test_local_pitch_on_the_curved_wall_matches_the_per_pixel_cast():
    _wall, footprints = _concave_pair()
    pitch = surface_pitch(footprints[0])
    assert pitch.minimum * 1000.0 == pytest.approx(1.72, abs=0.02)
    assert pitch.mean * 1000.0 == pytest.approx(3.32, abs=0.02)
    assert pitch.maximum * 1000.0 == pytest.approx(4.77, abs=0.02)
