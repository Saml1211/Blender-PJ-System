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


# -- blend ramp modelling -------------------------------------------------


def test_linear_ramp_weights_are_complementary_everywhere():
    """A blending processor ramps one image down as the other comes up, so
    the pair's combined weight stays unity through the zone."""
    zone_start, zone_end = 2.0, 4.0
    positions = [1.0, 1.99, 2.0, 2.5, 3.0, 3.999, 4.0, 5.0]
    for s in positions:
        left = ph.linear_ramp_weight(s, zone_start, zone_end, side="left")
        right = ph.linear_ramp_weight(s, zone_start, zone_end, side="right")
        assert left + right == pytest.approx(1.0)


def test_linear_ramp_clamps_outside_the_zone():
    # Before the zone the left projector runs at full output; after it, the
    # right one does. Weights never leave [0, 1].
    for s in (0.0, 1.5):
        assert ph.linear_ramp_weight(s, 2.0, 4.0, side="left") == pytest.approx(1.0)
        assert ph.linear_ramp_weight(s, 2.0, 4.0, side="right") == pytest.approx(0.0)
    for s in (4.5, 9.0):
        assert ph.linear_ramp_weight(s, 2.0, 4.0, side="left") == pytest.approx(0.0)
        assert ph.linear_ramp_weight(s, 2.0, 4.0, side="right") == pytest.approx(1.0)


def test_linear_ramp_is_halfway_at_the_zone_midpoint():
    assert ph.linear_ramp_weight(3.0, 2.0, 4.0, side="left") == pytest.approx(0.5)
    assert ph.linear_ramp_weight(3.0, 2.0, 4.0, side="right") == pytest.approx(0.5)


def test_linear_ramp_rejects_a_degenerate_zone():
    with pytest.raises(ProjectionError):
        ph.linear_ramp_weight(3.0, 2.0, 2.0, side="left")


def test_assumptions_for_raw_blend_model_keep_the_additive_line():
    assumptions = ph.assumptions_for_blend_model(ph.BlendModel.RAW)
    assert any("add linearly" in a for a in assumptions)
    assert assumptions == ph.ASSUMPTIONS


def test_assumptions_for_linear_ramp_describe_the_ramp():
    assumptions = ph.assumptions_for_blend_model(ph.BlendModel.LINEAR_RAMP)
    assert any("linear" in a.lower() for a in assumptions)
    assert not any("no blend" in a for a in assumptions)


def test_derate_chain_properties_and_bands():
    chain = ph.DerateChain(
        production_tolerance=0.80,
        picture_mode_factor=0.85,
        aging_factor=0.80,
        lens_transmission=0.90,
    )
    assert chain.rated_multiplier == pytest.approx(0.90)
    # typical: 0.90 * 0.85 * 0.90 = 0.6885
    assert chain.typical_multiplier == pytest.approx(0.90 * 0.85 * 0.90)
    # worst-case: 0.90 * 0.80 * 0.85 * 0.80 = 0.4896
    assert chain.worst_case_multiplier == pytest.approx(0.90 * 0.80 * 0.85 * 0.80)

    # effective lumens
    assert chain.effective_lumens(6000.0, "rated") == pytest.approx(5400.0)
    assert chain.effective_lumens(6000.0, "typical") == pytest.approx(4131.0)
    assert chain.effective_lumens(6000.0, "worst_case") == pytest.approx(2937.6)


def test_derate_chain_rejects_invalid_factors():
    with pytest.raises(ProjectionError):
        ph.DerateChain(production_tolerance=-0.5)
    with pytest.raises(ProjectionError):
        ph.DerateChain(picture_mode_factor=0.0)
    with pytest.raises(ProjectionError):
        ph.DerateChain(aging_factor=float("nan"))
    with pytest.raises(ProjectionError):
        ph.DerateChain(lens_transmission=float("inf"))


def test_summarize_brightness_with_derate_chain():
    samples = [1000.0, 2000.0, 3000.0]
    chain = ph.DerateChain(
        production_tolerance=0.80,
        picture_mode_factor=0.85,
        aging_factor=0.80,
    )
    report = ph.summarize_brightness(samples, screen_gain=1.0, derate_chain=chain)
    assert report.derate_chain == chain
    assert report.rated_band is not None
    assert report.typical_band is not None
    assert report.worst_case_band is not None

    assert report.rated_band.mean_lux == pytest.approx(2000.0)
    assert report.typical_band.mean_lux == pytest.approx(2000.0 * chain.operational_typical_factor)
    assert report.worst_case_band.mean_lux == pytest.approx(2000.0 * chain.operational_worst_case_factor)
    assert report.worst_case_band.mean_nits < report.typical_band.mean_nits < report.rated_band.mean_nits


def test_gamma_blend_ramp_weight_and_alias():
    # gamma = 1.0 matches linear
    assert ph.linear_ramp_weight(3.0, 2.0, 4.0, side="left", gamma=1.0) == pytest.approx(0.5)
    assert ph.gamma_ramp_weight(3.0, 2.0, 4.0, side="left", gamma=1.0) == pytest.approx(0.5)

    # gamma = 1.2
    assert ph.linear_ramp_weight(3.0, 2.0, 4.0, side="left", gamma=1.2) == pytest.approx(0.5**1.2)
    assert ph.linear_ramp_weight(3.0, 2.0, 4.0, side="right", gamma=1.2) == pytest.approx(0.5**1.2)

    with pytest.raises(ProjectionError, match="positive"):
        ph.linear_ramp_weight(3.0, 2.0, 4.0, side="left", gamma=-0.5)


def test_blend_ramp_luminance_error():
    assert ph.blend_ramp_luminance_error(1.0) == pytest.approx(0.0)
    assert ph.blend_ramp_luminance_error(0.8) == pytest.approx(2**0.2 - 1.0)
    assert ph.blend_ramp_luminance_error(1.2) == pytest.approx(2**-0.2 - 1.0)


def test_overlap_guidance_tiers():
    assert "<5%" in ph.overlap_guidance(0.03)
    assert "<10%" in ph.overlap_guidance(0.08)
    assert "10-20%" in ph.overlap_guidance(0.15)
    assert ">20%" in ph.overlap_guidance(0.25)


def test_assumptions_mention_derate_chain_and_gamma_ramp():
    chain = ph.DerateChain(production_tolerance=0.80, picture_mode_factor=0.85)
    assumptions = ph.assumptions_for_blend_model(
        ph.BlendModel.GAMMA_RAMP, gamma=1.2, derate_chain=chain
    )
    text = " ".join(assumptions)
    assert "derate chain" in text
    assert "gamma-shaped ramps" in text
    assert "gamma=1.20" in text


def test_veiling_luminance_calculation():
    # L_amb = E_amb * gain / pi
    assert ph.veiling_luminance_nits(50.0, 1.0) == pytest.approx(50.0 / math.pi)
    assert ph.veiling_luminance_nits(100.0, 1.5) == pytest.approx(150.0 / math.pi)

    with pytest.raises(ProjectionError):
        ph.veiling_luminance_nits(-10.0, 1.0)
    with pytest.raises(ProjectionError):
        ph.veiling_luminance_nits(50.0, -1.0)


def test_effective_contrast_ratio_formula():
    # In dark room (ambient = 0), CR = white / black = native
    assert ph.effective_contrast_ratio(2000.0, 1.0, 0.0) == pytest.approx(2000.0)

    # In room with 50 lux ambient: (500 + 50) / (0.25 + 50) = 550 / 50.25 ≈ 10.945
    assert ph.effective_contrast_ratio(500.0, 0.25, 50.0) == pytest.approx(550.0 / 50.25)

    # Completely unlit cell (white = 0) with ambient > 0 -> 1.0 (1:1 washed out)
    assert ph.effective_contrast_ratio(0.0, 0.0, 50.0) == pytest.approx(1.0)

    with pytest.raises(ProjectionError):
        ph.effective_contrast_ratio(-1.0, 1.0, 10.0)


def test_summarize_contrast_and_iscr_disclaimer():
    ratios = [15.0, 20.0, 25.0]
    report = ph.summarize_contrast(
        ratios,
        ambient_lux=50.0,
        screen_gain=1.0,
        target_category=ph.ISCRCategory.BASIC_DECISION_MAKING,
        user_target_ratio=15.0,
    )
    assert report.min_contrast == 15.0
    assert report.max_contrast == 25.0
    assert report.mean_contrast == 20.0
    assert report.meets_user_target is True
    assert "ANSI/AVIXA V201.01:2021" in report.disclaimer
    assert "not certify compliance" in report.disclaimer

    # Failing target check
    report_fail = ph.summarize_contrast(
        ratios,
        ambient_lux=50.0,
        user_target_ratio=30.0,
    )
    assert report_fail.meets_user_target is False
