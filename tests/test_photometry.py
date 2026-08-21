"""Tests for the brightness / illuminance estimates."""

from __future__ import annotations

import math

import pytest

from blender_projection_system.core import photometry as ph
from blender_projection_system.core.errors import ProjectionError
from blender_projection_system.core.throw import ProjectorSpec, image_size


def test_solid_angle_matches_the_rectangular_pyramid_formula():
    spec = ProjectorSpec(throw_ratio=1.5, aspect_w=16, aspect_h=9)
    th, tv = 0.0, 0.0
    from blender_projection_system.core.throw import half_angles

    th, tv = half_angles(spec)
    expected = 4.0 * math.asin(math.sin(th) * math.sin(tv))
    assert ph.frustum_solid_angle(spec) == pytest.approx(expected)


def test_a_wider_lens_subtends_a_larger_solid_angle():
    wide = ProjectorSpec(throw_ratio=0.8)
    tele = ProjectorSpec(throw_ratio=4.0)
    assert ph.frustum_solid_angle(wide) > ph.frustum_solid_angle(tele)


def test_intensity_is_flux_over_solid_angle():
    spec = ProjectorSpec(throw_ratio=1.5, lumens=7000.0)
    assert ph.axial_intensity(spec) == pytest.approx(
        7000.0 / ph.frustum_solid_angle(spec)
    )


def test_illuminance_follows_the_inverse_square_law():
    spec = ProjectorSpec(throw_ratio=1.5, lumens=5000.0)
    near = ph.illuminance_at(spec, 3.0)
    far = ph.illuminance_at(spec, 6.0)
    assert near / far == pytest.approx(4.0)


def test_illuminance_falls_off_with_the_cosine_of_incidence():
    spec = ProjectorSpec(throw_ratio=1.5, lumens=5000.0)
    square_on = ph.illuminance_at(spec, 5.0, incidence=0.0)
    oblique = ph.illuminance_at(spec, 5.0, incidence=math.radians(60.0))
    assert oblique / square_on == pytest.approx(math.cos(math.radians(60.0)))


def test_a_surface_facing_away_receives_nothing():
    spec = ProjectorSpec(throw_ratio=1.5, lumens=5000.0)
    assert ph.illuminance_at(spec, 5.0, incidence=math.radians(120.0)) == 0.0


@pytest.mark.parametrize("throw_ratio", [1.2, 2.0, 4.0, 8.0])
def test_axial_illuminance_exceeds_the_flat_average_by_the_predicted_ratio(throw_ratio):
    """The physical cross-check between the two ways of computing brightness.

    ``lumens / area`` is the *mean* over a flat screen; ``I / d^2`` is the
    on-axis value. They differ by exactly :func:`center_to_mean_ratio`, which
    is pure geometry: corners are further away and struck obliquely.
    """
    spec = ProjectorSpec(throw_ratio=throw_ratio, lumens=6000.0)
    distance = 8.0
    size = image_size(distance, spec)
    mean = ph.nominal_screen_illuminance(spec, size.area)
    axial = ph.illuminance_at(spec, distance, 0.0)
    assert axial == pytest.approx(mean * ph.center_to_mean_ratio(spec), rel=1e-9)
    assert axial > mean


@pytest.mark.parametrize(
    "throw_ratio, max_excess",
    [(1.2, 0.12), (2.0, 0.05), (4.0, 0.02), (8.0, 0.005)],
)
def test_the_centre_hot_spot_shrinks_as_the_lens_gets_longer(throw_ratio, max_excess):
    ratio = ph.center_to_mean_ratio(ProjectorSpec(throw_ratio=throw_ratio))
    assert 1.0 < ratio <= 1.0 + max_excess


def test_lambertian_luminance_conversion():
    assert ph.luminance_nits(314.159265, screen_gain=1.0) == pytest.approx(100.0, rel=1e-6)
    assert ph.luminance_nits(100.0, screen_gain=2.0) == pytest.approx(
        2.0 * ph.luminance_nits(100.0, 1.0)
    )


def test_unit_conversions_round_trip():
    assert ph.nits_to_foot_lamberts(ph.NITS_PER_FOOTLAMBERT) == pytest.approx(1.0)
    assert ph.lux_to_foot_candles(ph.LUX_PER_FOOTCANDLE) == pytest.approx(1.0)


def test_cinema_white_reference_is_about_sixteen_foot_lamberts():
    assert ph.nits_to_foot_lamberts(ph.CINEMA_WHITE_NITS) == pytest.approx(16.0, abs=0.1)


def test_negative_and_empty_inputs_are_rejected():
    with pytest.raises(ProjectionError):
        ph.luminance_nits(-1.0)
    with pytest.raises(ProjectionError):
        ph.luminance_nits(10.0, screen_gain=0.0)
    with pytest.raises(ProjectionError):
        ph.summarize_brightness([])
    with pytest.raises(ProjectionError):
        ph.illuminance_at(ProjectorSpec(), 0.0)


def test_summary_reports_range_and_uniformity():
    report = ph.summarize_brightness([100.0, 200.0, 300.0], screen_gain=1.0)
    assert report.sample_count == 3
    assert report.min_lux == 100.0 and report.max_lux == 300.0
    assert report.mean_lux == pytest.approx(200.0)
    assert report.uniformity == pytest.approx(1 / 3)
    assert report.mean_nits == pytest.approx(200.0 / math.pi)
    assert report.assumptions  # every report carries its assumptions


def test_uniform_samples_report_perfect_uniformity():
    assert ph.summarize_brightness([250.0] * 5).uniformity == pytest.approx(1.0)


def test_warnings_flag_a_dim_image():
    dim = ph.summarize_brightness([50.0, 55.0])
    warnings = ph.brightness_warnings(dim)
    assert any("cinema-white" in w for w in warnings)


def test_warnings_flag_poor_uniformity():
    uneven = ph.summarize_brightness([100.0, 2000.0])
    assert any("uniformity" in w for w in ph.brightness_warnings(uneven))


def test_a_bright_even_image_produces_no_warnings():
    good = ph.summarize_brightness([1000.0, 1050.0, 1100.0])
    assert ph.brightness_warnings(good) == []


def test_a_realistic_room_lands_in_a_believable_range():
    """A 7000 lm projector on a 4 m wide 16:9 image should read as a normal
    bright-room presentation level, not a nonsense number."""
    spec = ProjectorSpec(throw_ratio=1.5, lumens=7000.0)
    distance = 6.0
    size = image_size(distance, spec)
    assert size.width == pytest.approx(4.0)
    nits = ph.luminance_nits(ph.nominal_screen_illuminance(spec, size.area))
    assert 200.0 < nits < 350.0


def test_shifted_frustum_uses_the_off_axis_solid_angle():
    spec = ProjectorSpec(
        throw_ratio=1.2,
        aspect_w=16.0,
        aspect_h=9.0,
        lens_shift_v=0.6,
    )
    assert ph.frustum_solid_angle(spec) == pytest.approx(0.3183614979, rel=1e-9)


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_non_finite_photometric_inputs_are_rejected(value):
    with pytest.raises(ProjectionError):
        ph.luminance_nits(value)
    with pytest.raises(ProjectionError):
        ph.summarize_brightness([value])
