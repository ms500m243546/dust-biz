"""Phase R.1 — AP-42 physics module tests."""

from __future__ import annotations

import pytest

from app.domain.ap42_emission import (
    AP42_K_PM10,
    AP42_K_PM25,
    METRIC_TONNE_TO_SHORT_TON,
    WATERING_BASE_REDUCTION,
    emission_factor_lb_per_vmt,
    speed_reduction_factor,
    watering_decay_curve,
)


def test_emission_factor_returns_zero_on_nonpositive_inputs() -> None:
    assert emission_factor_lb_per_vmt(silt_content_pct=0, vehicle_weight_metric_tonnes=200) == 0.0
    assert emission_factor_lb_per_vmt(silt_content_pct=10, vehicle_weight_metric_tonnes=0) == 0.0
    assert emission_factor_lb_per_vmt(silt_content_pct=-1, vehicle_weight_metric_tonnes=200) == 0.0


def test_emission_factor_pm10_at_published_reference_point() -> None:
    # Hand-computed sanity: silt=12%, weight=3 short tons → both
    # bracketed terms collapse to 1, so E should equal k.
    weight_metric = 3.0 / METRIC_TONNE_TO_SHORT_TON  # ~2.72 metric tonnes
    e = emission_factor_lb_per_vmt(
        silt_content_pct=12.0,
        vehicle_weight_metric_tonnes=weight_metric,
        particle="pm10",
    )
    assert pytest.approx(e, rel=1e-6) == AP42_K_PM10


def test_emission_factor_pm25_smaller_than_pm10() -> None:
    e10 = emission_factor_lb_per_vmt(
        silt_content_pct=8.0,
        vehicle_weight_metric_tonnes=400.0,
        particle="pm10",
    )
    e25 = emission_factor_lb_per_vmt(
        silt_content_pct=8.0,
        vehicle_weight_metric_tonnes=400.0,
        particle="pm25",
    )
    assert e25 < e10
    # By the published k ratio the PM2.5 emission is exactly 10% of PM10.
    assert pytest.approx(e25 / e10, rel=1e-6) == AP42_K_PM25 / AP42_K_PM10


def test_emission_factor_grows_with_weight_and_silt() -> None:
    base = emission_factor_lb_per_vmt(silt_content_pct=8, vehicle_weight_metric_tonnes=300)
    heavier = emission_factor_lb_per_vmt(silt_content_pct=8, vehicle_weight_metric_tonnes=450)
    siltier = emission_factor_lb_per_vmt(silt_content_pct=15, vehicle_weight_metric_tonnes=300)
    assert heavier > base
    assert siltier > base


def test_speed_reduction_factor_zero_when_after_geq_before() -> None:
    assert speed_reduction_factor(speed_before_kmh=30, speed_after_kmh=30) == 0.0
    assert speed_reduction_factor(speed_before_kmh=30, speed_after_kmh=40) == 0.0


def test_speed_reduction_factor_typical_haul_road_cut() -> None:
    # 50 -> 25 km/h: ratio 0.5, exponent 0.5 → 1 - sqrt(0.5) ≈ 0.293.
    f = speed_reduction_factor(speed_before_kmh=50, speed_after_kmh=25)
    assert 0.28 <= f <= 0.30


def test_speed_reduction_factor_handles_zero_inputs_gracefully() -> None:
    assert speed_reduction_factor(speed_before_kmh=0, speed_after_kmh=10) == 0.0
    assert speed_reduction_factor(speed_before_kmh=10, speed_after_kmh=0) == 0.0


def test_watering_decay_returns_base_at_t_zero_default_meteo() -> None:
    # At t=0 with default meteorology, the curve hits the empirical
    # base reduction (no decay yet).
    assert watering_decay_curve(minutes_since_watering=0) == pytest.approx(
        WATERING_BASE_REDUCTION, rel=1e-6
    )


def test_watering_decay_drops_with_time() -> None:
    early = watering_decay_curve(minutes_since_watering=30)
    later = watering_decay_curve(minutes_since_watering=180)
    assert early > later
    assert later >= 0


def test_watering_decay_faster_under_dry_windy_hot_conditions() -> None:
    moderate = watering_decay_curve(
        minutes_since_watering=60,
        wind_speed_ms=5,
        humidity_pct=50,
        temperature_c=15,
    )
    arid = watering_decay_curve(
        minutes_since_watering=60,
        wind_speed_ms=12,
        humidity_pct=15,
        temperature_c=30,
    )
    assert arid < moderate


def test_watering_decay_negative_time_clamps_to_zero() -> None:
    assert watering_decay_curve(minutes_since_watering=-10) == 0.0


def test_watering_decay_caps_at_base_reduction() -> None:
    f = watering_decay_curve(minutes_since_watering=0, wind_speed_ms=0)
    assert f <= WATERING_BASE_REDUCTION + 1e-9
